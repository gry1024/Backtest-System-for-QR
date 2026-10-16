# Backtest System for Quantitative Researchers

把你的策略因子表示成一个 `pool.json` ，运行回测，变成一份 A 股因子回测报告。适合每天提出因子、需要快速验证、以及多因子组合方法的策略研究者。

单因子直接回测；多因子默认使用历史 Rank IC 筛选和滚动岭回归，并加上**全部因子等权合成**的对照。**沪深 300 价格指数**为baseline。净值、回撤、年度收益、换手和指标都有。

![六因子组合：滚动组合、全部因子等权和沪深300同图对比](docs/example_report.png)

## 三分钟开始

在项目目录运行，推荐 Python 3.11 与 uv：

```powershell
uv sync --extra dev
uv run python run_adaptive_combination.py factors/single_factor/reversal_5d.json
uv run python run_adaptive_combination.py factors/multi_classic.json
```

不使用 uv 也可以：

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python run_adaptive_combination.py factors/multi_classic.json
```

回测数据默认读取项目下的 `feathers/`。数据集样例覆盖2020-2026.10，来自 [features](https://github.com/aslan9/pku_quantllm/releases/download/data-backtest-20261016/feathers.zip)。

产物： `results/<pool名>_<运行时间>/report.png`。

## 只写 pool.json

单因子最小示例：

```json
{
  "name": "五日反转",
  "exprs": ["Mul(-1,TsPctChange($close,6))"]
}
```

这里 `TsPctChange(x,6)` 表示最近六个观测首尾之间、也就是五个交易日的涨跌幅。算子具体见[完整算子手册](docs/operators.md)。所有因子都按**分数越高越优先买入**解释；反向因子在表达式外乘 `-1`。

多因子只需增加表达式：

```json
{
  "name": "价格与成交行为组合",
  "exprs": [
    "Mul(-1,TsPctChange($close,6))",
    "TsPctChange($close,61)",
    "Mul(-1,TsStd(TsPctChange($close,2),20))"
  ]
}
```


运行入口三选一，功能相同：

```powershell
uv run python run_adaptive_combination.py my_pool.json
uv run python -m quantbt my_pool.json
uv run poolbench my_pool.json
```

兼容旧参数 `--expressions_file my_pool.json`。

## 常见研究操作

先检查格式、特征文件和指数日历，不进行表达式数值计算或回测：

```powershell
uv run python -m quantbt factors/multi_factors_1/pool_10.json --check
```

为实验指定独立输出目录：

```powershell
uv run python -m quantbt factors/multi_classic.json --output results/classic_w252
```

只允许使用真实已有字段，拒绝 VWAP/成交量代理：

```powershell
uv run python -m quantbt factors/multi_classic.json --strict-features
```

只做等权组合、提高成本，或者改变组合更新频率：

```powershell
uv run python -m quantbt factors/multi_classic.json --method equal
uv run python -m quantbt factors/multi_classic.json --cost-bps 20
uv run python -m quantbt factors/multi_classic.json --refit-every 5 --window 252
```

固定权重组合：在 pool 中加入 `"weights": [0.5, -0.2, 0.3]`，再加 `"backtest": {"method": "fixed"}`，或传 `--method fixed`。系统按绝对权重和归一化。权重表示因子分数合成系数，不是股票资金权重。`adaptive` 自己学习权重，`equal` 对全部输入因子用 `1/K`；这两种模式忽略 pool 的 `weights` 并明确提示。单因子 `auto` 模式下，若提供单个负权重则反转方向，正权重的大小不影响选股。

可以把参数写在 pool 中，便于复现实验：

```json
{
  "name": "低波动",
  "exprs": ["Mul(-1,TsStd(TsPctChange($close,2),20))"],
  "backtest": {"top_fraction": 0.1, "cost_bps": 10}
}
```

命令行优先于 pool 中的 `backtest`，最后才使用默认值。日期不开放配置：**唯一评价区间为 2021-01-01 至 2026-10-01，含两端，遇非交易日使用区间内交易日**。本数据实际为 2021-01-04 至 2026-09-30，共 1,393 个交易日。2020 年只参与表达式预热与成熟标签训练；2021 年起的历史会继续进入之后的滚动窗口。2026-10-01 之后的股票数据会在任何计算之前截掉。

## 怎样看报告

多因子图中的三条曲线：

- `Adaptive combination`：历史筛选、滚动回归产生合成分数，再按分数选股。
- `Equal factor blend`：同一池的所有标准化因子直接等权相加，然后独立选股与模拟持仓。它不是各单因子净值的平均，也不是只等权自适应选中的因子。
- `CSI 300 index`：真实沪深 300 价格指数，第一天从开盘建仓，其后以收盘点位计算净值。无交易成本，不含股息再投资。

单因子展示因子策略与指数。股票策略都使用同一交易时序、选股比例与成本，因此自适应组合和等权组合可以直接比较。沪深 300 是市场背景对照，本系统股票范围是提供数据中的全 A 股，**没有假定这些股票属于沪深 300 成分股**。

报告中不只看收益；同时检查换手、回撤、IC/Rank IC、有效 IC 天数和数据覆盖。如果提高组合复杂度只增加换手而没有提高净收益，等权曲线会帮助识别这一点。示例不保证盈利。

| 文件 | 用途 |
|---|---|
| `report.png` / `report.svg` | 同一张大图：净值、回撤、年度收益、换手与完整指标表 |
| `metrics.json` / `metrics.csv` | 每条曲线的全部汇总指标；无定义项在 JSON 中为 `null` |
| `daily.csv` | 每日收益、净值；策略另含双边换手、成本比例、持仓数、仓位、冻结与陈旧估值暴露 |
| `annual_returns.csv` | 按自然年复利的区间内收益；2026 年只到 9 月底 |
| `ic.csv` | 按信号日期记录的每日 IC 和 Rank IC |
| `factors.csv` | 每个因子的表达式、特征、代理字段、回溯长度、有效覆盖和单因子 IC |
| `weights.csv` | 更新时点、实际训练首尾、最后标签兑现日、样本数、回归截距、各因子系数与回退原因 |
| `pool.json` | 本次解析后的完整 pool 和生效参数快照 |
| `manifest.json` | 数据/指数/代码 SHA256、软件版本、日期、耗时与重要警告 |

`f000`、`f001` 等编号与 `exprs` 原始顺序一致。系数保留回归原值，其绝对值不是资金敞口。`weights.csv` 只在预定更新日写一行，中间交易日沿用上次权重。非自适应模式也记录固定系数以便核查。

## 数据与缺失特征

输入是每个字段一个宽表：`date` 为严格递增、无重复日期，其余列为证券代码。所有文件的日期与列顺序必须完全相同，发现不一致会停止，不会自动内连接丢行。

| 字段 | 含义与系统使用方式 |
|---|---|
| `$open/$high/$low/$close` | 原始价格乘以相对累计复权因子，用于表达式与股票收益 |
| `$cumadj` | 原始累计复权因子；价格复权比率为当日值/该股首个有效值 |
| `$amt` | 原始成交额，默认假定人民币元；不做复权 |
| `$num_trades` | 原始成交笔数；不做复权，缺失不填零 |
| `$vwap` | **代理字段**：原始 OHLC4 乘以相对复权因子；并非真实成交均价 |
| `$volume` | **代理字段**：成交额/原始 OHLC4，单位约为股；并非真实成交量，也不是成交笔数 |

真正的 VWAP 与 volume 无法由这些字段准确恢复。为让现有 pool 可运行，默认只提供上述明确的代理；它们改变了原表达式的经济含义，尤其影响价量协方差和非线性表达式。控制台、图表、`factors.csv` 与 `manifest.json` 都会披露。要求严格可比时用 `--strict-features`，或者把研究公式改为直接使用 `$amt` 与 OHLC。

不使用未来价格回填原始特征。滚动统计窗口必须有完整有效观测；引用、差分和涨跌幅只检查实际使用的端点。除零、负数取对数、无定义幂和无穷值统一变成缺失值。常量截面和有效样本不足的截面不强行产生股票排名。上市早期默认不参与；只根据截至当日的有效价格观测累计上市交易日。

指数文件不会按股票均值伪造。更换同一指数的数据源时可用 `--benchmark path/to/csi300.csv`；CSV 必须含 `date,open,close`，评价区间交易日必须与股票数据完全一致，缺失时停止。

需要重新下载指数时显式运行：

```powershell
uv sync --extra download --extra dev
uv run python scripts/download_benchmark.py
```

下载来自 BaoStock，代码 `sh.000300`，日线、不复权；下载工具检查起止覆盖和点位后才写入，旁边 `.source.json` 记录来源、抓取时间和文件哈希。股票 Feather 文件始终使用你提供的数据。

## 回测原理

### 1. 每个收盘日生成可交易信号

对当日有有效复权收盘价、成交额大于零、至少累计 60 个有效价格观测的股票计算表达式。每个因子在当日可用截面上做总体标准差的 z-score，再截断至 `[-5,5]`。这让量纲不同的因子可以组合，且不引入跨日期的全样本统计。

缺失因子在合成时贡献为零，仍保留固定的等权分母 K；不是对每只股票临时重新分配权重。如果一只股票所有活跃因子都缺失，其分数也缺失。完整常量因子不参与排名，也不会因为代码顺序形成假信号。有效覆盖见 `factors.csv`。

### 2. 多因子如何学习权重

默认每 20 个交易日重新训练一次，使用最近 252 个**可用标签起点日**：

1. 因子在日期 `t` 收盘产生信号，监督标签为 `open[t+1+h] / open[t+1] - 1`，默认 `h=20`。标签与下一开盘入场时序一致。
2. 在信号日 `c` 收盘训练，只允许 `t+1+h <= c` 的标签进入。筛选使用的历史 Rank IC 也遵守同一个边界。最后 20 个交易日前后尚未到期的标签不进入模型或评价，IC 有效天数因此少于净值天数。
3. 在该历史窗口计算各因子的平均 Rank IC 与日度 Rank ICIR，默认要求绝对值分别至少 0.015 和 0.15。按 `abs(Rank ICIR)` 排序，最多取 10 个因子。没有达阈值时，取有足够有效历史的最佳一个。
4. 将日期×股票作为训练样本，使用截面标准化因子与原始远期收益做带截距的岭回归。目标是均方损失加 `alpha * sum(beta²)`，默认 `alpha=0.001`，不惩罚截距。
5. 中间交易日固定使用已学得系数，在新的因子截面上评分。截距对所有股票相同，不改变排名，所以交易评分不加截距，审计表仍记录它。

至少需要 60 个历史起点日。没有足够样本、可用历史 Rank IC 或可用回归解时，明确回退到全部因子等权；状态记录在 `weights.csv`。岭回归允许共线因子，不沿用原代码按 SVD/QR 随意删训练行、把奇异向量数量当作原列索引的做法。

单因子 `auto` 模式不通过历史 IC 翻转方向，按研究者写出的方向执行。多因子回归可以学到负系数；等权基线的方向始终是表达式自己的方向。

### 3. 开盘调仓，收盘记账

`t` 收盘信号在 `t+1` 开盘执行，买入有效分数最高的前 20% 股票，目标等资金权重。数量向下取整到选股数量，至少一只；分数并列按数据原列顺序稳定处理。持仓每天在开盘重平衡，而组合系数默认每 20 日更新，两者互相独立。

模拟器保存持股数量与现金，先按当日开盘价估值并卖出，再按照可用现金买入。买入资金自动为费用留出空间，不借钱、不做空。交易费用按买卖成交额分别乘以默认 10 bps；一次全部卖出再全部买入约为 20 bps。费用包含佣金、税费和滑点的统一研究假设，不是按历史税制逐笔还原。初次建仓也收费用。

每日净值按收盘标记，包含旧持仓的隔夜收益、新持仓的日内收益和当日费用。区间结束只按收盘估值，不假设强制卖出，不额外收清仓费。无可用信号时目标为空仓；无法交易的既有持仓仍保留。

开盘价缺失的股票不能成交，既有持仓冻结；收盘价缺失时用最近已知价格估值，并披露 `stale_weight`。不会因为未来收益/卖出价格缺失而把股票从当时的选股范围删除。退市或长停牌最终回收价值未知，系统不会假造退出价格，持续陈旧估值可能使净值偏高；必须结合暴露指标判断结果。

### 4. 净值和指标的统一口径

设每日净收益率为 `r`、交易日数为 `N`，每年按 252 个交易日；标准差采用样本标准差：

| 指标 | 定义 |
|---|---|
| 净值 / 总收益 | `NAV = cumprod(1+r)`，总收益为期末 NAV 减 1 |
| 年化收益 | `NAV[-1] ** (252/N) - 1` |
| 年化波动率 | `std(r, ddof=1) * sqrt(252)` |
| Sharpe | `mean(r) / std(r) * sqrt(252)`，无风险利率设为零 |
| 最大回撤 | `max(1 - NAV / running_peak)`，峰值序列包含最初资本 1 |
| Calmar | 年化收益/最大回撤 |
| 正收益天数比例 | `count(r > 0) / N`，不等于逐笔交易胜率 |
| 相对指数累计收益 | `策略期末NAV / 指数期末NAV - 1` |
| 信息比率 | `mean(r_strategy-r_index) / std(r_strategy-r_index) * sqrt(252)` |
| 平均换手 | 每日买入额加卖出额/当日开盘调仓前净值，再取均值；双边口径 |
| 平均仓位 | 每日收盘持仓市值/收盘净值的均值 |
| IC / Rank IC | 信号与 h 日远期开盘收益的每日截面 Pearson / Spearman 相关，再对有效日期取均值 |
| ICIR / Rank ICIR | 对应日度相关系数的均值/样本标准差，不再乘 `sqrt(252)` |

相关性按双方都有有限值的股票计算，至少三只；并列用平均秩。无定义的相关性不会当成零来拉低标准差。最后尚未到期的远期标签不补零。指数不报告因子 IC、策略换手等不适用指标。

## 参数参考

pool 的 `backtest` 使用下划线键，命令行把下划线换成连字符。

| 参数 | 默认值 | 含义 |
|---|---:|---|
| `method` | `auto` | 一个因子直接执行，多个因子滚动组合；也可 `adaptive/equal/fixed` |
| `window` | 252 | 回归与 Rank IC 筛选的历史标签起点日数 |
| `label_days` | 20 | 从下一个开盘开始的监督标签持有天数，不是实际调仓间隔 |
| `refit_every` | 20 | 重新筛选并更新组合系数的间隔 |
| `min_train_days` | 60 | 历史筛选至少需要的有效起点日数 |
| `n_factors` | 10 | 自适应每次最多选取的因子数 |
| `threshold_ric` | 0.015 | 历史平均 Rank IC 的绝对值阈值 |
| `threshold_ricir` | 0.15 | 历史日度 Rank ICIR 的绝对值阈值 |
| `ridge_alpha` | 0.001 | 岭惩罚系数；0 为无惩罚最小二乘，奇异时使用最小范数解 |
| `top_fraction` | 0.2 | 每日买入分数最高的股票比例 |
| `cost_bps` | 10 | 每一侧成交额的统一费率，单位基点 |
| `min_listing_days` | 60 | 至少累计多少个有效收盘观测后进入研究股票范围 |
| `strict_features` | false | 为 true 时禁止缺失字段代理 |

执行 `uv run python -m quantbt --help` 查看路径、检查与输出参数；`--list-operators` 查看可用算子名。

## 示例池

两个 50 因子 pool 与原单因子文件，包括原来的 `expr` 键。九个不依赖 VWAP/volume 代理的单因子，以及一个六因子组合：

| 文件（位于 `factors/`） | 研究角度 |
|---|---|
| `single_factor/reversal_5d.json` | 短期反转 |
| `single_factor/momentum_60d.json` | 中期动量 |
| `single_factor/low_volatility.json` | 低波动 |
| `single_factor/intraday_reversal.json` | 日内反转 |
| `single_factor/range_position.json` | 收盘在日内高低区间的位置 |
| `single_factor/illiquidity.json` | 单位成交额对应的价格变化 |
| `single_factor/trade_size.json` | 平均每笔成交金额 |
| `single_factor/downside_asymmetry.json` | 收益偏度的反向暴露 |
| `single_factor/gap_reversal.json` | 隔夜跳空反转 |
| `multi_classic.json` | 六种价格与成交行为的组合及自动等权对照 |

这些是验证与研究起点，没有按本回测区间事后挑选优胜者。`num_trades` 的历史缺失会反映在对应因子的覆盖率中。

## 模块与维护

```text
pool.json → config → data + expressions → combine → portfolio → metrics + report
```

| 模块 | 单一职责 |
|---|---|
| `quantbt/config.py` | 固定评价日期、pool 兼容、参数校验 |
| `quantbt/data.py` | Feather 轴校验、因果复权、可用股票、标签、指数 |
| `quantbt/expressions.py` | 白名单解析与全部数值算子 |
| `quantbt/combine.py` | 成熟标签筛选、历史窗口、岭回归、等权与固定权重 |
| `quantbt/portfolio.py` | 持仓/现金、开盘交易、费用、收盘估值 |
| `quantbt/metrics.py` | 标准化、相关性与复利绩效指标 |
| `quantbt/report.py` | 单图报告与严格 JSON 输出 |
| `quantbt/runner.py` | 连接上述步骤，保存可复查产物 |

只在一个进程运行，不做分布式、服务化或策略 DSL 扩展。因子立方体使用临时磁盘 memmap，回归分块累计充分统计量；正常结束或异常退出 Python 控制流时关闭并删除临时文件，不依赖隐式跨实验缓存。系统级强制终止可能留下 `results/.cache/poolbench-*`，确认没有正在运行的实验后可手动清理。

五千多只股票、50 个因子的临时立方体约 1.8 GB；还需要若干 GB 可用内存和结果磁盘空间。复杂嵌套表达式会比简单价格因子慢。依赖版本固定在 `uv.lock`，运行记录还保存实际库版本和代码哈希。

新增算子时只改解析白名单与数值核，补充[算子文档](docs/operators.md)和一个可手算的数值测试、一个前缀不变性测试。更换交易假设时只改持仓模拟器，并用现金守恒、成本和缺失成交价测试验证。

```powershell
uv run pytest -q
```

移植关系、原代码提交号、公式兼容差异见[代码来源与适配记录](docs/provenance.md)。测试不依赖私人 Feather 数据；实际数据验收另见[验证记录](docs/validation.md)。



