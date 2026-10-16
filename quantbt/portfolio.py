"""Long-only, daily open rebalance, close NAV, self-financing cash accounting."""
import numpy as np
import pandas as pd


def simulate(scores, open_prices, close_prices, eligible, eval_indices, dates, config):
    """Only yesterday's scores/eligibility and today's open can affect orders.

    Missing open freezes an existing position. Missing close is marked at the last
    known price; it is never used to discard a losing holding retrospectively.
    Scores with no cross-sectional dispersion produce cash targets.
    """
    shares = np.zeros(open_prices.shape[1])
    cash, prior_nav = 1.0, 1.0
    mark = np.ones_like(shares)
    # First-day valuation of zero positions is immaterial; seed only past marks.
    first_day = int(eval_indices[0])
    for day in range(first_day):
        mark = np.where(np.isfinite(close_prices[day]), close_prices[day], mark)
    cost = config.cost_bps / 10000
    rows = []
    for row, day in enumerate(eval_indices):
        op, cl = open_prices[day], close_prices[day]
        tradable = np.isfinite(op) & (op > 0)
        at_open = np.where(tradable, op, mark)
        nav_open = cash + shares @ at_open
        frozen_value = (shares * at_open * ~tradable).sum()
        signal = scores[row]
        valid = np.isfinite(signal) & eligible[day - 1]
        selected = np.empty(0, dtype=int)
        if valid.sum() >= 3 and np.ptp(signal[valid]) > 1e-12:
            indices = np.flatnonzero(valid)
            size = max(1, int(len(indices) * config.top_fraction))
            # Stable sorting makes ties reproducible by the original column order.
            selected = indices[np.argsort(-signal[indices], kind="stable")[:size]]
        target = np.zeros_like(shares)
        if len(selected):
            target[selected] = max(nav_open - frozen_value, 0) / len(selected)
        current = shares * at_open
        sells = np.where(tradable, np.maximum(current - target, 0), 0)
        shares -= sells / at_open
        cash += sells.sum() * (1 - cost)
        buys = np.where(tradable, np.maximum(target - current, 0), 0)
        needed = buys.sum() * (1 + cost)
        if needed > 0:
            buys *= min(1.0, max(cash, 0) / needed)
        shares += buys / at_open
        cash -= buys.sum() * (1 + cost)
        cash = max(cash, 0.0)  # Only guards floating point roundoff after cash scaling.
        traded = sells.sum() + buys.sum()
        mark = np.where(np.isfinite(cl) & (cl > 0), cl, at_open)
        nav = cash + shares @ mark
        missing_close = ~np.isfinite(cl)
        rows.append({"date": dates[day], "return": nav / prior_nav - 1, "nav": nav,
                     "turnover": traded / nav_open, "cost": traded * cost / nav_open,
                     "exposure": (shares @ mark) / nav, "holdings": int((shares > 1e-14).sum()),
                     "stale_weight": (shares * mark * missing_close).sum() / nav,
                     "frozen_open_weight": frozen_value / nav_open})
        prior_nav = nav
    return pd.DataFrame(rows).set_index("date")
