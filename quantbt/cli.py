import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from .config import Config
from .expressions import OPERATORS
from .runner import run

ROOT = Path(__file__).resolve().parent.parent


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="PoolBench: pool.json -> one report; fixed 2021-01-01..2026-10-01")
    parser.add_argument("pool", type=Path, nargs="?", help="single-factor or multi-factor pool.json")
    parser.add_argument("--expressions_file", type=Path, help="legacy alias for positional pool")
    parser.add_argument("--data", type=Path, default=ROOT / "feathers")
    parser.add_argument("--benchmark", type=Path, default=ROOT / "benchmarks/csi300.csv")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true", help="validate pool, feature schema and benchmark without backtesting")
    parser.add_argument("--list-operators", action="store_true")
    defaults = Config()
    for name in ("window", "label_days", "refit_every", "min_train_days", "n_factors", "min_listing_days"):
        parser.add_argument("--" + name.replace("_", "-"), type=int, help=f"default {getattr(defaults, name)}")
    for name in ("threshold_ric", "threshold_ricir", "ridge_alpha", "top_fraction", "cost_bps"):
        parser.add_argument("--" + name.replace("_", "-"), type=float, help=f"default {getattr(defaults, name)}")
    parser.add_argument("--strict-features", action="store_true", default=None)
    parser.add_argument("--method", choices=["auto", "adaptive", "equal", "fixed"])
    args = parser.parse_args()
    if args.list_operators:
        print("\n".join(sorted(OPERATORS)))
        return
    pool = args.pool or args.expressions_file
    if pool is None or (args.pool and args.expressions_file):
        parser.error("provide one pool path, positional or --expressions_file")
    output = args.output or ROOT / "results" / f"{pool.stem}_{datetime.now():%Y%m%d_%H%M%S_%f}"
    overrides = {name: getattr(args, name) for name in Config.__dataclass_fields__}
    try:
        result = run(pool, args.data, args.benchmark, output, overrides, args.check)
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(2, f"Error: {exc}\n")
    if args.check:
        print(json.dumps(result, indent=2, ensure_ascii=False))
