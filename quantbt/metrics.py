"""Correlation and performance formulas adapted from cf (MIT), with compounding."""
import numpy as np
import pandas as pd


def normalize(values, eligible):
    """Daily population z-score, clipped at +/-5; missing values remain missing."""
    valid = np.isfinite(values) & eligible
    count = valid.sum(axis=1, keepdims=True)
    filled = np.where(valid, values, 0.0)
    # z-score must not depend on the feature's units; scale before squaring to
    # handle illiquidity ratios near 1e-12 and extreme GP powers without overflow.
    scale = np.max(np.abs(filled), axis=1, keepdims=True)
    scaled = np.divide(filled, scale, out=np.zeros_like(filled), where=scale > 0)
    mean = scaled.sum(axis=1, keepdims=True) / np.maximum(count, 1)
    centered = np.where(valid, scaled - mean, 0.0)
    std = np.sqrt((centered ** 2).sum(axis=1, keepdims=True) / np.maximum(count, 1))
    out = np.full(values.shape, np.nan, dtype=float)
    np.divide(centered, std, out=out, where=valid & (count >= 3) & (std > 1e-12))
    return np.clip(out, -5, 5)


def daily_corr(x, y, ranked=False):
    valid = np.isfinite(x) & np.isfinite(y)
    a, b = np.where(valid, x, np.nan), np.where(valid, y, np.nan)
    if ranked:
        a = pd.DataFrame(a).rank(axis=1, method="average").to_numpy()
        b = pd.DataFrame(b).rank(axis=1, method="average").to_numpy()
    n = valid.sum(axis=1, keepdims=True)
    a = np.where(valid, a, 0.0)
    b = np.where(valid, b, 0.0)
    a = np.where(valid, a - a.sum(axis=1, keepdims=True) / np.maximum(n, 1), 0)
    b = np.where(valid, b - b.sum(axis=1, keepdims=True) / np.maximum(n, 1), 0)
    denom = np.sqrt((a * a).sum(axis=1) * (b * b).sum(axis=1))
    return np.divide((a * b).sum(axis=1), denom, out=np.full(len(x), np.nan),
                     where=(denom > 1e-14) & (n[:, 0] >= 3))


def ratio(a, b):
    return float(a / b) if np.isfinite(b) and b > 1e-14 else np.nan


def performance(returns, benchmark, turnover=None, ic=None, ric=None, exposure=None):
    returns, benchmark = np.asarray(returns), np.asarray(benchmark)
    if not np.isfinite(returns).all() or np.any(returns <= -1):
        raise ValueError("Returns must be finite and > -100%")
    nav = np.cumprod(1 + returns)
    peaks = np.maximum.accumulate(np.r_[1.0, nav])[1:]
    dd = nav / peaks - 1
    mean, std = returns.mean(), returns.std(ddof=1)
    annual = nav[-1] ** (252 / len(nav)) - 1
    active = returns - benchmark
    result = dict(total_return=float(nav[-1] - 1), annual_return=float(annual),
                  annual_volatility=float(std * np.sqrt(252)), sharpe=ratio(mean * np.sqrt(252), std),
                  max_drawdown=float(-dd.min()), calmar=ratio(annual, -dd.min()),
                  daily_win_rate=float((returns > 0).mean()),
                  excess_total_return=float(nav[-1] / np.prod(1 + benchmark) - 1),
                  information_ratio=ratio(active.mean() * np.sqrt(252), active.std(ddof=1)),
                  avg_turnover=float(np.mean(turnover)) if turnover is not None else np.nan,
                  avg_exposure=float(np.mean(exposure)) if exposure is not None else np.nan)
    for label, values in (("ic", ic), ("rank_ic", ric)):
        values = np.asarray([] if values is None else values)
        values = values[np.isfinite(values)]
        result[label] = float(values.mean()) if len(values) else np.nan
        result[label + "ir"] = ratio(values.mean(), values.std(ddof=1)) if len(values) > 1 else np.nan
        result[label + "_days"] = len(values)
    return result
