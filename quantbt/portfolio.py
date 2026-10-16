"""CNY account: prior-close scores, open rebalance, close valuation and final exit."""
import numpy as np
import pandas as pd


def simulate(scores, open_prices, close_prices, eligible, eval_indices, dates, config, status=None):
    shares = np.zeros(open_prices.shape[1])
    cash = prior_equity = config.initial_cash
    mark = np.ones_like(shares)
    first_day = int(eval_indices[0])
    for day in range(first_day):
        mark = np.where(np.isfinite(close_prices[day]), close_prices[day], mark)
    commission_rate = config.commission_bps / 10000
    stamp_rate = config.stamp_duty_bps / 10000
    rows = []
    for row, day in enumerate(eval_indices):
        op, cl = open_prices[day], close_prices[day]
        state = np.ones_like(shares) if status is None else status[day]
        trading = (state == 1) | (state == 3)
        open_available = np.isfinite(op) & (op > 0) & trading
        at_open = np.where(np.isfinite(op) & (op > 0), op, mark)
        equity_open = cash + shares @ at_open
        frozen_value = (shares * at_open * ~open_available).sum()
        buy_notional = sell_notional = 0.0
        buys = np.zeros_like(shares)
        final_day = config.liquidate_at_end and row == len(eval_indices) - 1
        if not final_day:
            signal = scores[row]
            valid = np.isfinite(signal) & eligible[day - 1] & (state == 1)
            selected = np.empty(0, dtype=int)
            if valid.sum() >= 3 and np.ptp(signal[valid]) > 1e-12:
                indices = np.flatnonzero(valid)
                size = max(1, int(len(indices) * config.top_fraction))
                selected = indices[np.argsort(-signal[indices], kind="stable")[:size]]
            target = np.zeros_like(shares)
            if len(selected):
                target[selected] = max(equity_open - frozen_value, 0) / len(selected)
            current = shares * at_open
            sells = np.where(open_available, np.maximum(current - target, 0), 0)
            shares = np.maximum(shares - sells / at_open, 0)
            cash += sells.sum() * (1 - commission_rate - stamp_rate)
            buys = np.where(open_available & (state == 1), np.maximum(target - current, 0), 0)
            needed = buys.sum() * (1 + commission_rate)
            if needed > 0:
                buys *= min(1.0, max(cash, 0) / needed)
            shares += buys / at_open
            cash -= buys.sum() * (1 + commission_rate)
            buy_notional, sell_notional = float(buys.sum()), float(sells.sum())
        mark = np.where(np.isfinite(cl) & (cl > 0), cl, at_open)
        if final_day:
            closing = np.isfinite(cl) & (cl > 0) & trading
            sell_notional = float((shares * mark * closing).sum())
            cash += sell_notional * (1 - commission_rate - stamp_rate)
            shares[closing] = 0
        cash = max(cash, 0.0)
        market_value = float(shares @ mark)
        equity = cash + market_value
        traded = buy_notional + sell_notional
        commission = traded * commission_rate
        stamp_duty = sell_notional * stamp_rate
        rows.append({"date": dates[day], "return": equity / prior_equity - 1,
                     "nav": equity / config.initial_cash, "equity": equity, "cash": cash,
                     "market_value": market_value, "buy_notional": buy_notional,
                     "sell_notional": sell_notional, "commission": commission, "stamp_duty": stamp_duty,
                     "turnover": traded / equity_open, "cost": (commission + stamp_duty) / equity_open,
                     "exposure": market_value / equity, "holdings": int((shares > 1e-8).sum()),
                     "stale_weight": (shares * mark * ~np.isfinite(cl)).sum() / equity,
                     "frozen_open_weight": frozen_value / equity_open,
                     "st_holdings": int(((shares > 1e-8) & (state >= 2)).sum()),
                     "st_buy_notional": float(buys[state >= 2].sum()),
                     "unknown_status_buy_notional": float(buys[state < 0].sum()),
                     "non_st_candidates": int((eligible[day - 1] & (state == 1)).sum())})
        prior_equity = equity
    return pd.DataFrame(rows).set_index("date")
