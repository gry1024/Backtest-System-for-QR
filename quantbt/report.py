"""One large research figure: curves, drawdown, yearly returns and metric tables."""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
from matplotlib import font_manager
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

COLORS = ["#D36938", "#397BA8", "#454C56"]
PERCENT = {"total_return", "annual_return", "annual_volatility", "max_drawdown", "daily_win_rate",
           "excess_total_return", "avg_turnover", "avg_exposure"}
LABELS = {"total_return": "Total return", "annual_return": "Annualized return", "annual_volatility": "Annualized volatility",
          "sharpe": "Sharpe (RF=0)", "max_drawdown": "Maximum drawdown", "calmar": "Calmar",
          "daily_win_rate": "Positive days", "excess_total_return": "Relative return vs index",
          "information_ratio": "Information ratio", "avg_turnover": "Daily turnover (two-way)",
          "avg_exposure": "Average invested capital", "ic": "IC / forward open return",
          "icir": "ICIR (daily)", "rank_ic": "Rank IC", "rank_icir": "Rank ICIR (daily)",
          "ic_days": "Valid IC sessions", "rank_ic_days": "Valid Rank IC sessions"}


def write_json(path, value):
    def convert(item):
        if isinstance(item, dict):
            return {str(k): convert(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [convert(v) for v in item]
        if isinstance(item, (float, np.floating)):
            return float(item) if np.isfinite(item) else None
        if isinstance(item, np.integer):
            return int(item)
        return item
    path.write_text(json.dumps(convert(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def make_report(output, daily, metrics, title, config, proxy_names, method):
    available = {f.name for f in font_manager.fontManager.ttflist}
    font = next((f for f in ("Microsoft YaHei", "Noto Sans CJK SC", "SimHei", "DejaVu Sans") if f in available), "DejaVu Sans")
    plt.rcParams.update({"font.family": font, "font.size": 10, "axes.unicode_minus": False,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#D5DBE0", "text.color": "#283746", "axes.labelcolor": "#52616F",
                         "xtick.color": "#52616F", "ytick.color": "#52616F", "figure.facecolor": "#F6F8FA",
                         "axes.facecolor": "white", "grid.color": "#E6EBEF"})
    fig = plt.figure(figsize=(22, 17), layout="constrained")
    grid = fig.add_gridspec(4, 2, height_ratios=[3.5, 1.3, 1.6, 2.4], hspace=0.08)
    nav_ax, dd_ax = fig.add_subplot(grid[0, :]), fig.add_subplot(grid[1, :])
    annual_ax, exposure_ax = fig.add_subplot(grid[2, 0]), fig.add_subplot(grid[2, 1])
    table_axes = [fig.add_subplot(grid[3, 0]), fig.add_subplot(grid[3, 1])]
    names = list(daily)
    colors = [COLORS[0]] + ([COLORS[1]] if len(names) == 3 else []) + [COLORS[2]]
    dates = next(iter(daily.values())).index
    for color, (name, frame) in zip(colors, daily.items()):
        nav = frame["nav"].to_numpy()
        nav_ax.plot(dates, nav, label=name, color=color, linewidth=1.7 if name != names[-1] else 1.4)
        dd = nav / np.maximum.accumulate(np.r_[1.0, nav])[1:] - 1
        dd_ax.plot(dates, dd * 100, color=color, linewidth=1.0)
    nav_ax.axhline(1, color="#8B98A5", lw=0.7, linestyle="--")
    nav_ax.set_title("NET ASSET VALUE  /  compounded, after trading costs", loc="left", fontsize=13, pad=14)
    nav_ax.set_ylabel("NAV / initial capital = 1")
    nav_ax.legend(loc="upper left", ncols=len(names), frameon=False)
    dd_ax.set_ylabel("Drawdown (%)")
    for axis in (nav_ax, dd_ax):
        ticks = pd.DatetimeIndex([dates[0]]).union(pd.date_range(dates[0], dates[-1], freq="MS"))
        axis.set_xticks(ticks)
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        axis.tick_params(axis="x", labelrotation=65, labelsize=7)
        axis.set_xlim(dates[0], dates[-1])
        axis.grid(True, alpha=0.8, linewidth=0.5)
    yearly = pd.DataFrame({name: frame["return"] for name, frame in daily.items()})
    yearly = (1 + yearly).groupby(yearly.index.year).prod() - 1
    x = np.arange(len(yearly))
    width = 0.8 / len(names)
    for index, (name, color) in enumerate(zip(names, colors)):
        annual_ax.bar(x + (index - (len(names) - 1) / 2) * width, yearly[name] * 100,
                      width=width, color=color, label=name)
    annual_ax.set_xticks(x, [str(y) + ("*" if y == dates[-1].year else "") for y in yearly.index])
    annual_ax.set_title("CALENDAR YEAR RETURN  /  * final year through September", loc="left", fontsize=11)
    annual_ax.set_ylabel("Return (%)")
    annual_ax.axhline(0, color="#8B98A5", linewidth=0.6)
    annual_ax.grid(axis="y", linewidth=0.5)
    for color, (name, frame) in zip(colors, daily.items()):
        if "turnover" in frame:
            exposure_ax.plot(dates, frame["turnover"].rolling(20, min_periods=1).mean() * 100,
                             color=color, linewidth=1.0, label=name)
    exposure_ax.set_title("TRADING ACTIVITY  /  20-session mean turnover", loc="left", fontsize=11)
    exposure_ax.set_ylabel("Traded notional / NAV (%)")
    exposure_ax.xaxis.set_major_locator(mdates.YearLocator())
    exposure_ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    exposure_ax.set_xlim(dates[0], dates[-1])
    exposure_ax.grid(linewidth=0.5)
    groups = [list(LABELS)[:9], list(LABELS)[9:]]
    for axis, keys in zip(table_axes, groups):
        axis.axis("off")
        cells = []
        for key in keys:
            row = [LABELS[key]]
            for name in names:
                value = metrics[name].get(key, np.nan)
                row.append("—" if value is None or not np.isfinite(value) else
                           f"{value:.1%}" if key in PERCENT else
                           str(int(value)) if key.endswith("_days") else f"{value:.3f}")
            cells.append(row)
        table = axis.table(cellText=cells, colLabels=["Metric", *names], cellLoc="right",
                           loc="center", bbox=[0, 0.04, 1, 0.9], colWidths=[0.4] + [0.6 / len(names)] * len(names))
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        for (r, c), cell in table.get_celld().items():
            cell.set_edgecolor("#E1E7ED")
            cell.set_linewidth(0.5)
            cell.set_facecolor("#E8EEF3" if r == 0 else "white" if r % 2 else "#F5F8FA")
            if c == 0:
                cell.set_text_props(ha="left")
            if r == 0:
                cell.set_text_props(weight="bold", color="#283746" if c == 0 else colors[c - 1])
    proxy = ", ".join("$" + x for x in sorted(proxy_names)) or "none"
    stale = max(frame["stale_weight"].iloc[-1] for frame in daily.values() if "stale_weight" in frame)
    fig.suptitle(f"POOLBENCH  |  {title}\n"
                 f"{dates[0]:%Y-%m-%d} — {dates[-1]:%Y-%m-%d}  ·  {len(dates):,} sessions  ·  "
                 f"{method}  ·  top {config.top_fraction:.0%}  ·  cost {config.cost_bps:g} bps/side  ·  proxies: {proxy}\n"
                 f"Research fills: no price-limit / ST / lot / capacity model. Final stale-price exposure: {stale:.2%}.",
                 x=0.02, ha="left", fontsize=16, fontweight="bold")
    fig.savefig(output / "report.png", dpi=150)
    fig.savefig(output / "report.svg")
    plt.close(fig)
