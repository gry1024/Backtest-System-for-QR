"""Optional, explicit download; the backtest itself never accesses the network."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

import baostock as bs
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quantbt.data import sha256
from quantbt.report import write_json


def main():
    parser = argparse.ArgumentParser(description="Download the CSI 300 open/close benchmark from BaoStock")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "benchmarks/csi300.csv")
    args = parser.parse_args()
    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(login.error_msg)
    try:
        result = bs.query_history_k_data_plus("sh.000300", "date,code,open,close", start_date="2020-01-01",
                                              end_date="2026-10-01", frequency="d", adjustflag="3")
        if result.error_code != "0":
            raise RuntimeError(result.error_msg)
        frame = result.get_data()
        dates = pd.to_datetime(frame["date"])
        if frame.empty or dates.min() > pd.Timestamp("2020-01-10") or dates.max() < pd.Timestamp("2026-09-30"):
            raise ValueError("Download does not cover the full required period; existing benchmark was not replaced")
        if dates.duplicated().any() or not dates.is_monotonic_increasing:
            raise ValueError("Benchmark calendar is not unique and increasing")
        prices = frame[["open", "close"]].astype(float)
        if prices.isna().any().any() or (prices <= 0).any().any():
            raise ValueError("Benchmark contains invalid prices")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.output, index=False, lineterminator="\n")
        write_json(args.output.with_suffix(".source.json"), {
            "source": "BaoStock query_history_k_data_plus", "code": "sh.000300", "adjustflag": "3",
            "retrieved_utc": datetime.now(timezone.utc).isoformat(), "rows": len(frame),
            "start": str(dates.min().date()), "end": str(dates.max().date()), "sha256": sha256(args.output)})
        print(args.output.resolve())
    finally:
        bs.logout()


if __name__ == "__main__":
    main()
