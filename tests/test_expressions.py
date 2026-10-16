import json
from pathlib import Path

import numpy as np
import pytest

from quantbt.expressions import Expression, OPERATORS


class ArrayData:
    def __init__(self, x, y=None):
        self.shape = x.shape
        self.arrays = {"close": x, "open": x if y is None else y}

    def feature(self, name):
        return self.arrays[name]


@pytest.mark.parametrize("text", ["Ref($close,-1)", "TsMean($close,2.5)", "TsMean($close,True)",
                                  "TsMean($close,0)", "__import__('os').system('whoami')",
                                  "$close[0]", "Unknown($close)", "Log($missing)", "True", "1e309",
                                  "TsCorr($close,$open,20,30)", "($close + $open)"])
def test_reject_unsafe_or_future_expression(text):
    with pytest.raises(ValueError):
        Expression(text)


def test_lagged_and_legacy_conventions():
    x = np.arange(1, 13, dtype=float).reshape(4, 3)
    data = ArrayData(x)
    np.testing.assert_allclose(Expression("TsPctChange($close,3)").evaluate(data)[2], x[2] / x[0] - 1)
    np.testing.assert_allclose(Expression("TsDelta($close,2)").evaluate(data)[2], x[2] - x[0])
    np.testing.assert_allclose(Expression("TsRank($close,3)").evaluate(data)[2:], 1 / 3)
    assert Expression("TsMean(Ref($close,5),20)").lookback == 24


def test_ties_and_invalid_math():
    data = ArrayData(np.array([[1.0, 1.0, 3.0, np.nan], [-1, 0, 4, 4]]))
    np.testing.assert_allclose(Expression("Rank($close)").evaluate(data)[0], [1/6, 1/6, 2/3, np.nan], equal_nan=True)
    np.testing.assert_allclose(Expression("Log($close)").evaluate(data)[1], [np.nan, np.nan, np.log(4), np.log(4)], equal_nan=True)
    assert np.isnan(Expression("Div($close,0)").evaluate(data)).all()


@pytest.mark.parametrize("operator", sorted(OPERATORS))
def test_every_operator_matches_numpy_reference_and_is_causal(operator):
    rng = np.random.default_rng(77)
    x = rng.uniform(1, 5, (25, 5))
    y = rng.uniform(2, 8, (25, 5))
    from quantbt.expressions import UNARY, BINARY, PAIR
    text = (f"{operator}($close)" if operator in UNARY else
            f"{operator}($close,$open)" if operator in BINARY else
            f"{operator}($close,$open,5)" if operator in PAIR else f"{operator}($close,5)")
    expr = Expression(text)
    all_values = expr.evaluate(ArrayData(x, y))
    prefix = expr.evaluate(ArrayData(x[:15], y[:15]))
    np.testing.assert_allclose(prefix, all_values[:15], equal_nan=True, atol=1e-9)
    w = x[-5:]
    v = y[-5:]
    centered = w - w.mean(axis=0)
    expected = {
        "TsMean": w.mean(axis=0), "TsSum": w.sum(axis=0), "TsStd": w.std(axis=0, ddof=1),
        "TsVar": w.var(axis=0, ddof=1), "TsMin": w.min(axis=0), "TsMax": w.max(axis=0),
        "TsMed": np.median(w, axis=0), "TsMad": np.abs(centered).mean(axis=0),
        "TsSkew": (centered**3).mean(axis=0) / (centered**2).mean(axis=0)**1.5,
        "TsKurt": (centered**4).mean(axis=0) / w.var(axis=0, ddof=1)**2 - 3,
        "TsIr": w.mean(axis=0) / w.std(axis=0, ddof=1),
        "TsCov": (centered * (v-v.mean(axis=0))).sum(axis=0) / 4,
        "TsCorr": (centered * (v-v.mean(axis=0))).sum(axis=0) / np.sqrt((centered**2).sum(axis=0)*((v-v.mean(axis=0))**2).sum(axis=0)),
        "TsDiv": w[-1] / w.mean(axis=0), "TsPctChange": w[-1]/w[0]-1,
        "TsWMA": np.einsum("tn,t->n", w, np.arange(5)/10),
        "TsEMA": np.einsum("tn,t->n", w, ((2/3)**np.arange(5,0,-1))/sum((2/3)**np.arange(5,0,-1))),
    }
    if operator in expected:
        np.testing.assert_allclose(all_values[-1], expected[operator], rtol=1e-8, atol=1e-9)


def test_existing_and_example_pools_parse():
    for path in (Path(__file__).resolve().parents[1] / "factors").rglob("*.json"):
        raw = json.loads(path.read_text(encoding="utf-8"))
        for expr in raw.get("exprs", raw.get("expr", [])):
            Expression(expr)
