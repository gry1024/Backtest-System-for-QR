"""Local wide Feather data; all date filtering happens before feature evaluation."""
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from .config import END, START, WARMUP


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class MarketData:
    def __init__(self, directory, strict_features=False, status_path=None):
        self.directory = Path(directory)
        self.strict_features = strict_features
        self.used_files = set()
        self.proxies = {}
        self._raw_cache = {}
        self._feature_cache = {}
        close = pd.read_feather(self.directory / "close.feather")
        if "date" not in close:
            raise ValueError("Feathers must be wide tables with a date column")
        full_dates = pd.DatetimeIndex(close["date"])
        if full_dates.has_duplicates or not full_dates.is_monotonic_increasing:
            raise ValueError("Feather dates must be unique and increasing")
        if full_dates.min() > pd.Timestamp("2020-01-10") or full_dates.max() < pd.Timestamp("2026-09-30"):
            raise ValueError("Data must cover warmup in 2020 through 2026-09-30")
        self._all_dates = full_dates
        self._rows = (full_dates >= WARMUP) & (full_dates <= END)
        self.dates = full_dates[self._rows]
        self.stocks = pd.Index(close.columns.drop("date"))
        if self.stocks.has_duplicates or not len(self.stocks):
            raise ValueError("Stock columns must be nonempty and unique")
        self.shape = (len(self.dates), len(self.stocks))
        self.eval_indices = np.flatnonzero((self.dates >= START) & (self.dates <= END))
        self._raw_close = close.loc[self._rows, self.stocks].to_numpy(dtype=float)
        self._raw_close[(self._raw_close <= 0) | ~np.isfinite(self._raw_close)] = np.nan
        self.used_files.add(self.directory / "close.feather")
        adj = self.raw("cumadj")
        first = np.argmax(np.isfinite(adj) & (adj > 0), axis=0)
        base = adj[first, np.arange(self.shape[1])]
        self.adjustment = np.divide(adj, base, out=np.full_like(adj, np.nan), where=(base > 0) & (adj > 0))
        # Listing age counts observed sessions, never future membership.
        self.age = np.cumsum(np.isfinite(self._raw_close), axis=0)
        status_path = Path(status_path) if status_path else self.directory.parent / "market_status/state.feather"
        if not status_path.exists():
            raise ValueError("Historical ST/trading states are required; run scripts/download_status.py or pass --status")
        status = pd.read_feather(status_path).set_index("date")
        if status.index.has_duplicates or not status.index.is_monotonic_increasing:
            raise ValueError("Status dates must be unique and increasing")
        if not self.stocks.isin(status.columns).all() or not self.dates.isin(status.index).all():
            raise ValueError("Status data must cover the stock columns and research calendar")
        state = status.reindex(index=self.dates, columns=self.stocks).to_numpy()
        if not np.isin(state, [-1, 0, 1, 2, 3]).all():
            raise ValueError("Status values must be -1/0/1/2/3; see state.source.json")
        self.state = state.astype("int8")
        self.used_files.add(status_path)

    def raw(self, name):
        if name == "close":
            return self._raw_close
        if name in self._raw_cache:
            return self._raw_cache[name]
        path = self.directory / f"{name}.feather"
        if not path.exists():
            raise ValueError(f"Required feature file is missing: {path}")
        frame = pd.read_feather(path)
        if not pd.DatetimeIndex(frame["date"]).equals(self._all_dates) or not frame.columns.drop("date").equals(self.stocks):
            raise ValueError(f"{name}.feather has different dates or stock columns from close.feather")
        values = frame.loc[self._rows, self.stocks].to_numpy(dtype=float)
        values[~np.isfinite(values)] = np.nan
        if name in {"open", "high", "low", "cumadj"}:
            values[values <= 0] = np.nan
        elif name in {"amt", "num_trades"}:
            values[values < 0] = np.nan
        self.used_files.add(path)
        self._raw_cache[name] = values
        return values

    def feature(self, name):
        if name in self._feature_cache:
            return self._feature_cache[name]
        if name in {"open", "high", "low", "close"}:
            values = self.raw(name) * self.adjustment
        elif name in {"vwap", "volume"}:
            if self.strict_features:
                raise ValueError(f"${name} is unavailable: use OHLC/amt formulas or disable strict_features for explicit proxies")
            typical = sum(self.raw(key) for key in ("open", "high", "low", "close")) / 4
            if name == "vwap":
                self.proxies[name] = "OHLC4 * relative_cumadj"
                values = typical * self.adjustment
            else:
                self.proxies[name] = "amt / raw_OHLC4"
                values = np.divide(self.raw("amt"), typical, out=np.full_like(typical, np.nan), where=typical > 0)
        else:
            values = self.raw(name)
        self._feature_cache[name] = values
        return values

    def eligible(self, min_listing_days):
        return (np.isfinite(self.feature("close")) & (self.raw("amt") > 0)
                & (self.age >= min_listing_days) & (self.state == 1))

    def forward_returns(self, horizon):
        """Signal at t; entry at t+1 open; exit at t+1+h open."""
        op = self.feature("open")
        result = np.full(self.shape, np.nan)
        if len(op) > horizon + 1:
            result[:-(horizon + 1)] = op[horizon + 1:] / op[1:-horizon] - 1
        return result

    def manifest(self):
        observed = np.isfinite(self._raw_close)
        return {"data_start": str(self.dates[0].date()), "data_end": str(self.dates[-1].date()),
                "stocks": len(self.stocks), "sessions": len(self.dates), "proxies": self.proxies,
                "status_known_coverage": float(((self.state >= 0) & observed).sum() / max(observed.sum(), 1)),
                "universe": "daily historical non-ST; unknown status excluded",
                "files": {p.name: sha256(p) for p in sorted(self.used_files)}}


def load_benchmark(path, dates):
    frame = pd.read_csv(path, parse_dates=["date"]).set_index("date")
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("Benchmark dates must be unique and increasing")
    if not {"open", "close"} <= set(frame):
        raise ValueError("Benchmark CSV requires date,open,close")
    expected = frame.index[(frame.index >= dates[0]) & (frame.index <= dates[-1])]
    if not expected.equals(dates):
        raise ValueError("Stock and index trading calendars differ; repair the data instead of silently dropping sessions")
    aligned = frame.reindex(dates)[["open", "close"]]
    if not np.isfinite(aligned.to_numpy()).all() or (aligned <= 0).any().any():
        missing = aligned.index[aligned.isna().any(axis=1)].strftime("%Y-%m-%d").tolist()
        raise ValueError(f"Benchmark has missing/invalid prices; no filling allowed. Missing dates: {missing[:8]}")
    nav = aligned["close"] / aligned["open"].iloc[0]
    returns = nav.pct_change()
    returns.iloc[0] = nav.iloc[0] - 1
    return returns.to_numpy(), nav.to_numpy()
