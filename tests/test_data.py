import gc
import weakref

import numpy as np
import pandas as pd
import pytest

from quantbt.data import MarketData


@pytest.fixture
def feather_directory(tmp_path):
    dates = pd.to_datetime(["2020-01-02", "2020-01-03", "2025-01-02", "2026-09-30", "2026-10-16"])
    for name in ("open", "high", "low", "close", "amt", "cumadj"):
        values = np.ones((5, 3)) if name == "cumadj" else np.arange(1, 16).reshape(5, 3).astype(float)
        frame = pd.DataFrame(values, columns=["000001.SZ", "600001.SH", "300001.SZ"])
        frame.insert(0, "date", dates)
        frame.to_feather(tmp_path / (name + ".feather"))
    frame = pd.DataFrame(1, index=range(len(dates)), columns=["000001.SZ", "600001.SH", "300001.SZ"])
    frame.insert(0, "date", dates)
    frame.to_feather(tmp_path / "state.feather")
    return tmp_path


def test_end_cutoff_and_future_rows_cannot_affect_adjustment(feather_directory):
    data = MarketData(feather_directory, status_path=feather_directory / "state.feather")
    before = data.feature("close").copy()
    assert data.dates[-1] == pd.Timestamp("2026-09-30")
    for name in ("close", "cumadj"):
        path = feather_directory / (name + ".feather")
        frame = pd.read_feather(path)
        frame.iloc[-1, 1:] = 1e100
        frame.to_feather(path)
    after = MarketData(feather_directory, status_path=feather_directory / "state.feather").feature("close")
    np.testing.assert_allclose(before, after)


def test_caches_release_when_data_object_is_released(feather_directory):
    data = MarketData(feather_directory, status_path=feather_directory / "state.feather")
    data.feature("vwap")
    reference = weakref.ref(data)
    del data
    gc.collect()
    assert reference() is None


def test_mismatched_axes_fail_without_silent_alignment(feather_directory):
    path = feather_directory / "open.feather"
    frame = pd.read_feather(path)
    frame = frame[["date", "300001.SZ", "600001.SH", "000001.SZ"]]
    frame.to_feather(path)
    with pytest.raises(ValueError, match="different dates or stock columns"):
        MarketData(feather_directory, status_path=feather_directory / "state.feather").feature("open")


def test_strict_proxy_refusal(feather_directory):
    with pytest.raises(ValueError, match="unavailable"):
        MarketData(feather_directory, strict_features=True, status_path=feather_directory / "state.feather").feature("vwap")


def test_forward_labels_use_next_open_and_actual_exit(feather_directory):
    data = MarketData(feather_directory, status_path=feather_directory / "state.feather")
    op = data.feature("open")
    labels = data.forward_returns(1)
    np.testing.assert_allclose(labels[0], op[2] / op[1] - 1)
    assert np.isnan(labels[-2:]).all()


def test_only_confirmed_non_st_trading_stocks_enter_universe(feather_directory):
    path = feather_directory / "state.feather"
    state = pd.read_feather(path)
    state.iloc[1, 1:] = [1, 3, -1]
    state.iloc[2, 1:] = [0, 2, 1]
    state.to_feather(path)
    data = MarketData(feather_directory, status_path=path)
    np.testing.assert_array_equal(data.eligible(1)[1], [True, False, False])
    np.testing.assert_array_equal(data.eligible(1)[2], [False, False, True])


def test_missing_status_file_is_not_assumed_non_st(feather_directory):
    with pytest.raises(ValueError, match="Historical ST/trading states are required"):
        MarketData(feather_directory, status_path=feather_directory / "absent.feather")


def test_runner_exports_course_account_and_liquidation(feather_directory, monkeypatch):
    import json
    import quantbt.runner as runner
    pool = feather_directory / "pool.json"
    pool.write_text(json.dumps({"exprs": ["$close"], "backtest": {"min_listing_days": 1}}))
    benchmark = feather_directory / "benchmark.csv"
    pd.DataFrame({"date": ["2025-01-02", "2026-09-30"], "open": [10, 11], "close": [10, 12]}).to_csv(benchmark, index=False)
    monkeypatch.setattr(runner, "make_report", lambda *args: None)
    output = feather_directory / "output"
    result = runner.run(pool, feather_directory, benchmark, output, status_path=feather_directory / "state.feather")
    assert result["config"]["initial_cash"] == 1e9
    assert result["actual_start"] == "2025-01-02"
    assert result["actual_end"] == "2026-09-30"
    metrics = json.loads((output / "metrics.json").read_text())["Single factor"]
    assert metrics["total_commission"] > 0 and metrics["total_stamp_duty"] > 0
    assert metrics["final_holdings"] == 0 and metrics["final_market_value"] == 0
    assert metrics["final_equity"] == pytest.approx(metrics["final_cash"])
