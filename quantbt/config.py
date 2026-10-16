"""The complete research configuration and the legacy pool compatibility boundary."""
from dataclasses import asdict, dataclass, fields
import json
from pathlib import Path

import numpy as np

START = "2025-01-01"
END = "2026-09-30"
WARMUP = "2020-01-01"


@dataclass(frozen=True)
class Config:
    window: int = 252
    label_days: int = 20
    refit_every: int = 20
    min_train_days: int = 60
    n_factors: int = 10
    threshold_ric: float = 0.015
    threshold_ricir: float = 0.15
    ridge_alpha: float = 0.001
    top_fraction: float = 0.2
    initial_cash: float = 1_000_000_000.0
    commission_bps: float = 1.0
    stamp_duty_bps: float = 5.0
    liquidate_at_end: bool = True
    min_listing_days: int = 60
    strict_features: bool = False
    method: str = "auto"

    def __post_init__(self):
        for name in ("window", "label_days", "refit_every", "min_train_days", "n_factors", "min_listing_days"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.window < self.min_train_days:
            raise ValueError("window must be >= min_train_days")
        for name in ("threshold_ric", "threshold_ricir", "ridge_alpha", "commission_bps", "stamp_duty_bps", "initial_cash", "top_fraction"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not np.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if not 0 < self.top_fraction <= 1 or self.commission_bps + self.stamp_duty_bps >= 10000 or self.initial_cash <= 0:
            raise ValueError("top_fraction must be in (0,1]; initial_cash > 0; sell fees < 10000 bps")
        if not isinstance(self.strict_features, bool) or not isinstance(self.liquidate_at_end, bool):
            raise ValueError("strict_features and liquidate_at_end must be boolean")
        if self.method not in {"auto", "adaptive", "equal", "fixed"}:
            raise ValueError("method must be auto/adaptive/equal/fixed")


def load_pool(path: Path, overrides=None):
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError("pool.json must be an object")
    if "exprs" in raw and "expr" in raw:
        raise ValueError("Use either exprs or legacy expr, not both")
    exprs = raw.get("exprs", raw.get("expr"))
    if isinstance(exprs, str):
        exprs = [exprs]
    if not isinstance(exprs, list) or not exprs or not all(isinstance(e, str) and e.strip() for e in exprs):
        raise ValueError("pool needs a nonempty exprs list (legacy expr is also accepted)")
    if len(set(exprs)) != len(exprs):
        raise ValueError("Duplicate expressions: remove duplicates so the equal baseline is meaningful")
    weights = raw.get("weights")
    if weights is not None:
        weights = np.asarray(weights, dtype=float)
        if weights.shape != (len(exprs),) or not np.isfinite(weights).all() or not np.any(weights):
            raise ValueError("weights must contain one finite number per factor, and cannot all be zero")
    options = raw.get("backtest", {})
    if not isinstance(options, dict):
        raise ValueError("backtest must be an object")
    unknown = options.keys() - {f.name for f in fields(Config)}
    if unknown:
        raise ValueError(f"Unknown backtest options: {sorted(unknown)}")
    config = Config(**(options | {k: v for k, v in (overrides or {}).items() if v is not None}))
    if config.method == "fixed" and weights is None:
        raise ValueError("method=fixed requires weights in the pool")
    return {"name": raw.get("name", path.stem), "exprs": exprs,
            "weights": None if weights is None else weights.tolist(), "backtest": asdict(config)}, config
