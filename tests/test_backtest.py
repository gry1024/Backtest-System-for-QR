from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from quantbt.combine import fit_weights, combine
from quantbt.config import Config, load_pool
from quantbt.data import load_benchmark
from quantbt.metrics import daily_corr, normalize, performance
from quantbt.portfolio import simulate


def test_ridge_excludes_unmatured_labels_and_future_metrics():
    rng = np.random.default_rng(3)
    factors = rng.normal(size=(3, 100, 12))
    labels = factors[0] * 0.02 + rng.normal(size=(100, 12)) * 0.01
    eligible = np.ones(labels.shape, dtype=bool)
    rics = rng.uniform(-0.1, 0.3, (100, 3))
    cfg = Config(window=30, min_train_days=10, label_days=5, n_factors=3)
    weights, info = fit_weights(factors, labels, eligible, rics, 50, cfg)
    assert info["train_stop"] == 45
    assert info["train_stop"] - 1 + cfg.label_days + 1 == 50
    labels[45:] = 999
    rics[45:] = -100
    factors[:, 51:] = 777
    other, _ = fit_weights(factors, labels, eligible, rics, 50, cfg)
    np.testing.assert_allclose(weights, other)


def test_ridge_keeps_duplicate_columns_without_deleting_samples():
    rng = np.random.default_rng(9)
    x = rng.normal(size=(1, 90, 10))
    factors = np.repeat(x, 3, axis=0)
    labels = x[0] * 0.03
    cfg = Config(window=30, min_train_days=10, label_days=5, n_factors=3)
    rics = np.tile(np.linspace(.1, .2, 90)[:, None], (1,3))
    weights, info = fit_weights(factors, labels, np.ones(labels.shape, bool), rics, 70, cfg)
    assert info["samples"] == 300
    assert info["status"] == "ridge"
    assert np.isfinite(weights).all()
    np.testing.assert_allclose(weights, weights[0], rtol=1e-7)


@pytest.mark.parametrize("method", ["fixed", "equal"])
def test_fixed_and_equal_modes_use_all_input_factors_as_declared(method):
    x = np.tile(np.array([[-1, 0, 1]], float), (8, 1))
    factors = np.stack([x, -x])
    cfg = Config(method=method, refit_every=2)
    signals, baseline, records, actual = combine(
        factors, np.zeros_like(x), np.ones(x.shape, bool), np.zeros((8, 2)),
        np.array([3, 4, 5]), pd.date_range("2020-01-01", periods=8), cfg,
        {"weights": [1, 0]})
    np.testing.assert_allclose(baseline, 0)
    np.testing.assert_allclose(signals, x[[3,4,5]] if method == "fixed" else np.zeros((3,3)))
    assert actual == method
    assert len(records) == 2


def simulate_small(scores, op, cl, cost=0):
    return simulate(np.asarray(scores, float), np.asarray(op, float), np.asarray(cl, float),
                    np.ones(np.shape(op), bool), np.arange(1, len(op)),
                    pd.date_range("2021-01-01", periods=len(op)),
                    Config(initial_cash=1, commission_bps=cost, stamp_duty_bps=0, liquidate_at_end=False, top_fraction=1/3))


def test_cash_accounting_and_fees_are_self_financing():
    result = simulate_small([[3,2,1], [3,2,1]], [[10]*3, [10]*3, [10]*3], [[10]*3]*3, cost=10)
    expected = 1 / 1.001
    assert result.nav.iloc[0] == pytest.approx(expected)
    assert result.nav.iloc[1] == pytest.approx(expected)
    assert result.exposure.iloc[0] == pytest.approx(1)
    assert result.turnover.iloc[1] == pytest.approx(0)


def test_missing_exit_freezes_instead_of_dropping_losses():
    result = simulate_small([[3,2,1], [1,3,2]],
                            [[10]*3, [10]*3, [np.nan,10,10]],
                            [[10]*3, [8,10,10], [np.nan,10,10]])
    assert result.nav.iloc[0] == pytest.approx(.8)
    assert result.nav.iloc[1] == pytest.approx(.8)
    assert result.frozen_open_weight.iloc[1] == pytest.approx(1)
    assert result.stale_weight.iloc[1] == pytest.approx(1)


def test_ranking_ignores_future_returns_and_same_day_close():
    op = np.full((3,3), 10.0)
    a = simulate_small([[3,2,1], [3,2,1]], op, [[10]*3, [12,10,10], [6,10,10]])
    b = simulate_small([[3,2,1], [3,2,1]], op, [[10]*3, [6,10,10], [12,10,10]])
    assert a.nav.iloc[0] == pytest.approx(1.2)
    assert b.nav.iloc[0] == pytest.approx(.6)
    assert a.nav.iloc[-1] == pytest.approx(.6)
    assert b.nav.iloc[-1] == pytest.approx(1.2)


def test_drawdown_includes_initial_capital_and_compounds():
    result = performance(np.array([-.1,.1]), np.zeros(2))
    assert result["total_return"] == pytest.approx(-.01)
    assert result["max_drawdown"] == pytest.approx(.1)


def test_missing_constant_and_tied_signals():
    x = np.array([[1,2,3,np.nan], [1,1,1,np.nan]], float)
    normalized = normalize(x, np.ones(x.shape, bool))
    assert np.isnan(normalized[1]).all()
    np.testing.assert_allclose(daily_corr(x[:1], x[:1], ranked=True), [1])
    assert np.isnan(daily_corr(x[1:], x[1:])[0])


def test_normalization_is_invariant_to_units_and_avoids_overflow():
    x = np.array([[1, 2, 3, np.nan], [3, 9, 12, 15]], float)
    eligible = np.ones(x.shape, bool)
    expected = normalize(x, eligible)
    np.testing.assert_allclose(normalize(x * 1e-200, eligible), expected, equal_nan=True)
    np.testing.assert_allclose(normalize(x * 1e200, eligible), expected, equal_nan=True)


def test_constant_signals_stay_in_cash():
    result = simulate_small([[1,1,1], [np.nan]*3], [[10]*3]*3, [[10]*3, [12]*3, [15]*3])
    np.testing.assert_allclose(result.nav, 1)
    np.testing.assert_allclose(result.holdings, 0)


def test_billion_yuan_account_fees_and_final_close_liquidation():
    cfg = Config(top_fraction=1/3)
    op = np.full((3,3), 10.0)
    cl = op.copy()
    cl[2, 0] = 12
    frame = simulate(np.array([[3,2,1],[3,2,1]]), op, cl, np.ones(op.shape, bool),
                     np.array([1,2]), pd.date_range("2025-01-01", periods=3), cfg)
    bought = 1e9 / 1.0001
    sold = bought * 1.2
    expected = sold * (1-.0001-.0005)
    assert frame.equity.iloc[0] == pytest.approx(bought)
    assert frame.commission.sum() == pytest.approx((bought+sold)*.0001)
    assert frame.stamp_duty.sum() == pytest.approx(sold*.0005)
    assert frame.equity.iloc[-1] == pytest.approx(expected)
    assert frame.cash.iloc[-1] == pytest.approx(expected)
    assert frame.market_value.iloc[-1] == 0
    assert frame.holdings.iloc[-1] == 0
    assert frame.buy_notional.iloc[-1] == 0
    assert frame.nav.iloc[-1] == pytest.approx(expected/1e9)


def test_st_transition_exits_position_and_blocks_new_st_buy():
    cfg = Config(initial_cash=1000, commission_bps=0, stamp_duty_bps=0,
                 liquidate_at_end=False, top_fraction=.25)
    op = np.full((3,4), 10.0)
    cl = op.copy()
    cl[2,1] = 12
    status = np.ones(op.shape, dtype="int8")
    status[2,0] = 3
    frame = simulate(np.array([[4,3,2,1],[4,3,2,1]]), op, cl, np.ones(op.shape,bool),
                     np.array([1,2]), pd.date_range("2025-01-01",periods=3), cfg, status)
    assert frame.equity.iloc[-1] == pytest.approx(1200)
    assert frame.st_holdings.iloc[-1] == 0
    assert frame.st_buy_notional.sum() == 0
    assert frame.unknown_status_buy_notional.sum() == 0
    assert frame.sell_notional.iloc[-1] == pytest.approx(1000)


def test_suspension_status_freezes_even_when_vendor_has_an_open_price():
    cfg = Config(initial_cash=1000, commission_bps=0, stamp_duty_bps=0,
                 liquidate_at_end=True, top_fraction=1/3)
    prices = np.full((3,3),10.0)
    status = np.ones(prices.shape,dtype="int8")
    status[2,0] = 0
    frame = simulate(np.array([[3,2,1],[3,2,1]]), prices, prices, np.ones(prices.shape,bool),
                     np.array([1,2]), pd.date_range("2025-01-01",periods=3),cfg,status)
    assert frame.holdings.iloc[-1] == 1
    assert frame.frozen_open_weight.iloc[-1] == pytest.approx(1)
    assert frame.cash.iloc[-1] == 0
    assert frame.market_value.iloc[-1] == pytest.approx(1000)


def test_benchmark_requires_complete_calendar(tmp_path):
    path = tmp_path / "index.csv"
    dates = pd.date_range("2021-01-04", periods=3)
    pd.DataFrame({"date": dates, "open": [10,11,12], "close": [11,12,13]}).to_csv(path, index=False)
    returns, nav = load_benchmark(path, dates)
    np.testing.assert_allclose(np.cumprod(1+returns), nav)
    assert returns[0] == pytest.approx(.1)
    with pytest.raises(ValueError, match="calendars differ"):
        load_benchmark(path, dates[[0,2]])
    with pytest.raises(ValueError):
        load_benchmark(path, pd.date_range("2021-01-04", periods=4))


@pytest.mark.parametrize("payload", [
    {"exprs": []}, {"exprs": ["$close"], "expr": ["$close"]},
    {"exprs": ["$close"], "weights": [0]}, {"exprs": ["$close"], "weights": [1,2]},
    {"exprs": ["$close"], "backtest": {"lable_days": 20}},
    {"exprs": ["$close"], "backtest": {"refit_every": 0}},
    {"exprs": ["$close"], "backtest": {"method": "fixed"}},
])
def test_bad_pools_fail_early(tmp_path, payload):
    import json
    path = tmp_path / "pool.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        load_pool(path)
