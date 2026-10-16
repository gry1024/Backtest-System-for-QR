"""Historical RankIC screening + rolling ridge, adapted from the supplied runner.

Only labels whose exit open is known by the signal close enter screening or fit.
Ridge handles dependent columns; no observations are discarded by an SVD heuristic.
"""
import numpy as np
import pandas as pd


def weighted_score(factors, day, weights):
    active = np.flatnonzero(weights)
    if not len(active):
        return np.full(factors.shape[2], np.nan)
    values = np.asarray(factors[active, day], dtype=float)
    score = np.nan_to_num(values).T @ weights[active]
    score[~np.isfinite(values).any(axis=0)] = np.nan
    return score


def fit_weights(factors, labels, eligible, rics, cur, config):
    count = factors.shape[0]
    stop = cur - config.label_days
    begin = max(0, stop - config.window)
    fallback = np.ones(count) / count
    info = {"train_begin": begin, "train_stop": stop, "samples": 0, "intercept": 0.0}
    if stop - begin < config.min_train_days:
        return fallback, info | {"status": "equal_fallback_short_history"}
    history = rics[begin:stop]
    valid = np.isfinite(history)
    n = valid.sum(axis=0)
    mean = np.where(valid, history, 0).sum(axis=0) / np.maximum(n, 1)
    std = np.sqrt(np.where(valid, history - mean, 0).__pow__(2).sum(axis=0) / np.maximum(n - 1, 1))
    ir = np.divide(mean, std, out=np.zeros_like(mean), where=std > 1e-12)
    candidates = np.flatnonzero((n >= config.min_train_days) & (std > 1e-12))
    candidates = candidates[np.argsort(-np.abs(ir[candidates]), kind="stable")]
    selected = candidates[(np.abs(mean[candidates]) >= config.threshold_ric)
                          & (np.abs(ir[candidates]) >= config.threshold_ricir)][:config.n_factors]
    if not len(selected):
        selected = candidates[:1]
    if not len(selected):
        return fallback, info | {"status": "equal_fallback_no_valid_rankic"}
    # Accumulate sufficient statistics in small blocks instead of retaining all X.
    k = len(selected)
    xx, xy, sx = np.zeros((k, k)), np.zeros(k), np.zeros(k)
    sy, samples = 0.0, 0
    for start in range(begin, stop, 20):
        end = min(start + 20, stop)
        values = np.asarray(factors[selected, start:end], dtype=float).transpose(1, 2, 0)
        valid = np.isfinite(labels[start:end]) & eligible[start:end] & np.isfinite(values).any(axis=2)
        x = np.nan_to_num(values[valid])
        y = labels[start:end][valid]
        xx += x.T @ x
        xy += x.T @ y
        sx += x.sum(axis=0)
        sy += y.sum()
        samples += len(y)
    if samples < max(k + 2, 30):
        return fallback, info | {"status": "equal_fallback_short_samples"}
    gram = (xx - np.outer(sx, sx) / samples) / samples
    target = (xy - sx * sy / samples) / samples
    system = gram + config.ridge_alpha * np.eye(k)
    try:
        coef = np.linalg.solve(system, target)
    except np.linalg.LinAlgError:
        coef = np.linalg.lstsq(system, target, rcond=1e-10)[0]
    if not np.isfinite(coef).all() or np.abs(coef).sum() < 1e-14:
        return fallback, info | {"status": "equal_fallback_degenerate_fit"}
    weights = np.zeros(count)
    weights[selected] = coef
    return weights, info | {"status": "ridge", "samples": samples,
                            "intercept": float((sy - sx @ coef) / samples)}


def combine(factors, labels, eligible, rics, signal_indices, dates, config, pool):
    count = factors.shape[0]
    equal_weights = np.ones(count) / count
    equal = np.stack([weighted_score(factors, int(t), equal_weights) for t in signal_indices])
    method = config.method
    if method == "auto":
        method = "single" if count == 1 else "adaptive"
    if method == "fixed":
        weights = np.asarray(pool["weights"], dtype=float)
        weights /= np.abs(weights).sum()
    elif method == "single":
        weights = np.array([np.sign(pool["weights"][0]) if pool["weights"] else 1.0])
    else:
        weights = equal_weights.copy()
    scores, records = [], []
    for offset, cur in enumerate(signal_indices):
        cur = int(cur)
        info = {"status": method, "train_begin": None, "train_stop": None, "samples": 0, "intercept": 0.0}
        refit = offset % config.refit_every == 0
        if method == "adaptive" and refit:
            weights, info = fit_weights(factors, labels, eligible, rics, cur, config)
        if refit:
            start, stop = info.pop("train_begin"), info.pop("train_stop")
            records.append({"signal_date": dates[cur], **info,
                            "train_start": dates[start] if start is not None and stop > start else None,
                            "train_end": dates[stop - 1] if stop is not None and stop > start else None,
                            "last_label_exit": dates[stop - 1 + config.label_days + 1]
                            if stop is not None and stop > start else None,
                            **{f"f{i:03d}": float(w) for i, w in enumerate(weights)}})
        scores.append(weighted_score(factors, cur, weights))
    return np.stack(scores), equal, pd.DataFrame(records), method
