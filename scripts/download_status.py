"""Build the dated ST/trading mask, optionally seeding from an existing Qlib store."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import time

import baostock as bs
import numpy as np
import pandas as pd

END = "2026-09-30"


def login():
    socket.setdefaulttimeout(45)
    result = bs.login()
    if result.error_code != "0":
        raise RuntimeError(result.error_msg)


def fetch(task):
    stock, start, cache = task
    path = Path(cache) / (stock + ".npz")
    if path.exists():
        with np.load(path) as saved:
            if str(saved["start"]) <= start and str(saved["end"]) >= END:
                return stock, saved["dates"], saved["state"], None
    code, exchange = stock.split(".")
    for attempt in range(3):
        try:
            result = bs.query_history_k_data_plus(exchange.lower() + "." + code, "date,isST,tradestatus",
                                                  start_date=start, end_date=END, frequency="d", adjustflag="3")
            if result.error_code != "0":
                raise RuntimeError(result.error_msg)
            frame = result.get_data()
            if frame.empty:
                dates, state = np.array([], dtype="datetime64[D]"), np.array([], dtype="int8")
                np.savez_compressed(path, dates=dates, state=state, start=start, end=END)
                return stock, dates, state, None
            dates = pd.to_datetime(frame["date"]).to_numpy(dtype="datetime64[D]")
            st = pd.to_numeric(frame["isST"], errors="coerce").to_numpy()
            trading = pd.to_numeric(frame["tradestatus"], errors="coerce").to_numpy()
            valid = np.isin(st, [0, 1]) & np.isin(trading, [0, 1])
            state = (st[valid] * 2 + trading[valid]).astype("int8")
            dates = dates[valid]
            np.savez_compressed(path, dates=dates, state=state, start=start, end=END)
            return stock, dates, state, None
        except Exception as exc:
            if attempt == 2:
                return stock, None, None, str(exc)
            time.sleep(attempt + 1)
            login()


def seed_qlib(directory, dates, stocks, state):
    calendar = pd.DatetimeIndex(pd.to_datetime((directory / "calendars/day.txt").read_text().splitlines()))
    destination = dates.get_indexer(calendar)
    for column, stock in enumerate(stocks):
        code, exchange = stock.split(".")
        folder = directory / "features" / (exchange.lower() + code)
        arrays = []
        for field in ("isst", "tradestatus"):
            path = folder / (field + ".day.bin")
            values = np.full(len(calendar), np.nan)
            if path.exists():
                raw = np.fromfile(path, dtype="<f4")
                if len(raw) > 1 and np.isfinite(raw[0]):
                    offset = int(raw[0])
                    count = min(len(raw) - 1, len(calendar) - offset)
                    if offset >= 0 and count > 0:
                        values[offset:offset + count] = raw[1:count + 1]
            arrays.append(values)
        st, trading = arrays
        valid = (destination >= 0) & (calendar <= END) & np.isin(st, [0, 1]) & np.isin(trading, [0, 1])
        state[destination[valid], column] = (st[valid] * 2 + trading[valid]).astype("int8")
    print(f"Seeded {int((state >= 0).sum()):,} dated stock states", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("feathers"))
    parser.add_argument("--output", type=Path, default=Path("market_status/state.feather"))
    parser.add_argument("--qlib-source", type=Path)
    parser.add_argument("--workers", type=int, default=4, choices=range(1, 5))
    args = parser.parse_args()
    template = pd.read_feather(args.data / "close.feather")
    dates = pd.DatetimeIndex(template["date"])
    stocks = template.columns.drop("date")
    state = np.full((len(dates), len(stocks)), -1, dtype="int8")
    if args.qlib_source:
        seed_qlib(args.qlib_source, dates, stocks, state)
    cache = args.output.resolve().parent.parent / ".cache/status"
    cache.mkdir(parents=True, exist_ok=True)
    tasks = []
    for column, stock in enumerate(stocks):
        known = np.flatnonzero(state[:, column] >= 0)
        start = str((dates[known[-1]] + pd.Timedelta(days=1)).date()) if len(known) else "2020-01-01"
        if start <= END:
            tasks.append((stock, start, str(cache)))
    errors = []
    columns = {stock: i for i, stock in enumerate(stocks)}
    with ProcessPoolExecutor(max_workers=args.workers, initializer=login) as pool:
        futures = [pool.submit(fetch, task) for task in tasks]
        for count, future in enumerate(as_completed(futures), 1):
            stock, observed_dates, observed_state, error = future.result()
            if error:
                errors.append({"stock": stock, "error": error})
            else:
                rows = dates.get_indexer(pd.DatetimeIndex(observed_dates))
                valid = rows >= 0
                state[rows[valid], columns[stock]] = observed_state[valid]
            if count % 100 == 0 or count == len(tasks):
                print(f"Status download {count}/{len(tasks)}, errors={len(errors)}", flush=True)
    if errors:
        raise RuntimeError(f"Retry the downloader to resume: {errors[:5]}")
    frame = pd.DataFrame(state, columns=stocks)
    frame.insert(0, "date", dates)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_feather(args.output)
    prices = template.loc[dates <= END, stocks].to_numpy(dtype=float)
    observed = np.isfinite(prices)
    mask = state[dates <= END]
    meta = {"source": "BaoStock historical isST and tradestatus", "end": END,
            "fields": {"-1": "unknown", "0": "non-ST suspended", "1": "non-ST trading",
                       "2": "ST suspended", "3": "ST trading"},
            "retrieved_utc": datetime.now(timezone.utc).isoformat(),
            "stocks": len(stocks), "known_price_coverage": float(((mask >= 0) & observed).sum() / observed.sum()),
            "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}
    args.output.with_suffix(".source.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
