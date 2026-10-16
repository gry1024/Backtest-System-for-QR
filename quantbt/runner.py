"""One pool in, an auditable report directory out."""
from dataclasses import asdict
from datetime import datetime, timezone
import importlib.metadata
from pathlib import Path
import platform
import tempfile
import time

import numpy as np
import pandas as pd

from .combine import combine
from .config import END, START, load_pool
from .data import MarketData, load_benchmark, sha256
from .expressions import Expression
from .metrics import daily_corr, normalize, performance
from .portfolio import simulate
from .report import make_report, write_json


def run(pool_path, data_path, benchmark_path, output, overrides=None, check=False):
    started = time.perf_counter()
    code_snapshot = {p.name: sha256(p) for p in sorted(Path(__file__).parent.glob("*.py"))}
    pool_path, output = Path(pool_path), Path(output)
    pool, config = load_pool(pool_path, overrides)
    expressions = []
    for i, text in enumerate(pool["exprs"]):
        try:
            expressions.append(Expression(text))
        except ValueError as exc:
            raise ValueError(f"Factor f{i:03d}: {text}\n{exc}") from exc
    data = MarketData(data_path, config.strict_features)
    days = data.eval_indices
    signal_days = days - 1
    if signal_days.min() < 0:
        raise ValueError("Missing session before the start for lagged signals")
    dates = data.dates[days]
    benchmark_returns, benchmark_nav = load_benchmark(benchmark_path, dates)
    for name in sorted(set.union(*(e.features for e in expressions)) | {"open", "close", "amt"}):
        data.feature(name)
    print(f"Data: {data.shape[1]:,} stocks; {data.dates[0]:%Y-%m-%d}..{data.dates[-1]:%Y-%m-%d}", flush=True)
    print(f"Backtest: {dates[0]:%Y-%m-%d}..{dates[-1]:%Y-%m-%d}; {len(days):,} sessions; {len(expressions)} factors", flush=True)
    for name, explanation in data.proxies.items():
        print(f"PROXY ${name}: {explanation}", flush=True)
    if check:
        return {"valid": True, "factors": len(expressions), "sessions": len(days),
                "max_lookback": max(e.lookback for e in expressions), "proxies": data.proxies}
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"Output directory is not empty: {output}; choose a new directory")
    output.mkdir(parents=True, exist_ok=True)
    eligible = data.eligible(config.min_listing_days)
    labels = data.forward_returns(config.label_days)
    labels[~eligible] = np.nan
    cache = output.parent / ".cache"
    cache.mkdir(exist_ok=True)
    diagnostics = []
    rics = np.full((data.shape[0], len(expressions)), np.nan)
    # The factor cube is temporary disk storage, never an unversioned reusable cache.
    with tempfile.TemporaryDirectory(prefix="poolbench-", dir=cache) as temp:
        factors = np.memmap(Path(temp) / "factors.bin", dtype="float32", mode="w+",
                            shape=(len(expressions), *data.shape))
        try:
            for i, expr in enumerate(expressions):
                print(f"[{i + 1}/{len(expressions)}] f{i:03d}: {expr.text}", flush=True)
                values = expr.evaluate(data)
                normalized = normalize(values, eligible)
                factors[i] = normalized
                ric = daily_corr(normalized, labels, ranked=True)
                rics[:, i] = ric
                ic = daily_corr(normalized[signal_days], labels[signal_days])
                test_ric = ric[signal_days]
                valid_ic, valid_ric = ic[np.isfinite(ic)], test_ric[np.isfinite(test_ric)]
                coverage = np.isfinite(normalized[signal_days]) & eligible[signal_days]
                diagnostics.append({"factor": f"f{i:03d}", "expression": expr.text,
                                    "lookback": expr.lookback, "features": ",".join(sorted(expr.features)),
                                    "proxies": ",".join(sorted(expr.features & data.proxies.keys())),
                                    "coverage": float(coverage.sum() / max(eligible[signal_days].sum(), 1)),
                                    "usable_sessions": int(coverage.any(axis=1).sum()),
                                    "ic": float(valid_ic.mean()) if len(valid_ic) else np.nan,
                                    "rank_ic": float(valid_ric.mean()) if len(valid_ric) else np.nan})
                del values, normalized
            if not any(row["usable_sessions"] for row in diagnostics):
                raise ValueError("All expressions are missing or constant in the backtest; inspect features and operators")
            print("Combining signals with matured-label rolling regression...", flush=True)
            strategy, equal, weights, method = combine(factors, labels, eligible, rics, signal_days,
                                                       data.dates, config, pool)
        finally:
            factors.flush()
            factors._mmap.close()
            del factors
    strategy_name = {"single": "Single factor", "adaptive": "Adaptive combination", "equal": "Equal strategy", "fixed": "Fixed combination"}[method]
    scores = {strategy_name: strategy}
    if len(expressions) > 1:
        scores["Equal factor blend"] = equal
    daily, metrics, all_ics = {}, {}, {}
    print("Simulating daily open orders and closing NAV...", flush=True)
    for name, score in scores.items():
        frame = simulate(score, data.feature("open"), data.feature("close"), eligible, days, data.dates, config)
        ic = daily_corr(score, labels[signal_days])
        ric = daily_corr(score, labels[signal_days], ranked=True)
        metrics[name] = performance(frame["return"], benchmark_returns, frame["turnover"], ic, ric, frame["exposure"])
        frame["drawdown"] = frame["nav"] / np.maximum.accumulate(np.r_[1.0, frame["nav"]])[1:] - 1
        daily[name] = frame
        all_ics[name + " IC"] = ic
        all_ics[name + " RankIC"] = ric
    daily["CSI 300 index"] = pd.DataFrame({"return": benchmark_returns, "nav": benchmark_nav}, index=dates)
    metrics["CSI 300 index"] = performance(benchmark_returns, benchmark_returns)
    warnings = []
    if data.proxies:
        warnings.append("Missing VWAP/volume use declared OHLC4 proxies. Results are not evaluations of the original fields.")
    if pool["weights"] is not None and method in {"adaptive", "equal"}:
        warnings.append(f"Pool weights are ignored in {method} mode; use method=fixed to apply explicit weights.")
    inactive = [d["factor"] for d in diagnostics if not d["usable_sessions"]]
    if inactive:
        warnings.append(f"No usable signal in factors: {', '.join(inactive)}. Zero contribution, retained in equal blend denominator.")
    for name, frame in daily.items():
        if "stale_weight" in frame and frame["stale_weight"].max() > 0:
            warnings.append(f"{name}: stale price exposure max={frame['stale_weight'].max():.2%}, final={frame['stale_weight'].iloc[-1]:.2%}; no delisting recovery data.")
    write_json(output / "pool.json", pool)
    write_json(output / "metrics.json", metrics)
    pd.DataFrame(metrics).T.to_csv(output / "metrics.csv", index_label="series")
    pd.concat(daily, axis=1).to_csv(output / "daily.csv", index_label="date")
    pd.DataFrame(all_ics, index=data.dates[signal_days]).to_csv(output / "ic.csv", index_label="signal_date")
    pd.DataFrame(diagnostics).to_csv(output / "factors.csv", index=False)
    weights.to_csv(output / "weights.csv", index=False)
    returns = pd.DataFrame({k: v["return"] for k, v in daily.items()})
    ((1 + returns).groupby(returns.index.year).prod() - 1).to_csv(output / "annual_returns.csv", index_label="year")
    manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "requested_start": START, "requested_end": END,
                "actual_start": str(dates[0].date()), "actual_end": str(dates[-1].date()), "sessions": len(days),
                "method": method, "config": asdict(config), "data": data.manifest(),
                "benchmark": {"name": "CSI 300 price index", "path": str(Path(benchmark_path).resolve()), "sha256": sha256(benchmark_path)},
                "pool_sha256": sha256(pool_path), "warnings": warnings,
                "execution": "t close signal; t+1 open rebalance; daily close mark; long-only; no limit/ST/lot/capacity model",
                "python": platform.python_version(),
                "versions": {name: importlib.metadata.version(name) for name in ("numpy", "pandas", "pyarrow", "bottleneck", "matplotlib")},
                "code": code_snapshot}
    print("Rendering consolidated report...", flush=True)
    make_report(output, daily, metrics, pool["name"], config, data.proxies, method)
    manifest["elapsed_seconds"] = round(time.perf_counter() - started, 2)
    write_json(output / "manifest.json", manifest)
    for warning in warnings:
        print("WARNING: " + warning, flush=True)
    print(pd.DataFrame(metrics).T[["total_return", "annual_return", "sharpe", "max_drawdown", "rank_ic"]].round(4).to_string(), flush=True)
    print(f"Report: {(output / 'report.png').resolve()} ({manifest['elapsed_seconds']:.1f}s)", flush=True)
    return manifest
