# 策略结果

2025-01-02 至 2026-09-30，424 个交易日；初始资金 10 亿元。

| 策略 | 指标对应曲线 | 累计净收益 | 年化收益 | Sharpe | 最大回撤 | 文件 |
|---|---|---:|---:|---:|---:|---|
| 非流动性 | 单因子 | 79.24% | 41.46% | 1.570 | 22.41% | [报告](illiquidity/report.png) · [pool](illiquidity/pool.json) · [指标](illiquidity/metrics.json) |
| 低波动 | 单因子 | 28.22% | 15.92% | 0.971 | 18.90% | [报告](low_volatility/report.png) · [pool](low_volatility/pool.json) · [指标](low_volatility/metrics.json) |
| 收益偏度 | 单因子 | 34.65% | 19.34% | 0.922 | 21.82% | [报告](downside_asymmetry/report.png) · [pool](downside_asymmetry/pool.json) · [指标](downside_asymmetry/metrics.json) |
| 50因子组合 pool_9999 | 滚动组合 | 58.50% | 31.49% | 1.273 | 20.06% | [报告](pool_9999/report.png) · [pool](pool_9999/pool.json) · [指标](pool_9999/metrics.json) |
| 50因子组合 pool_10 | 滚动组合 | 42.56% | 23.46% | 0.993 | 23.39% | [报告](pool_10/report.png) · [pool](pool_10/pool.json) · [指标](pool_10/metrics.json) |
| 六因子组合 | 因子等权 | 40.98% | 22.65% | 0.895 | 28.23% | [报告](classic/report.png) · [pool](classic/pool.json) · [指标](classic/metrics.json) |

每个目录保存完整的 pool、PNG/SVG 合并图、指标、每日人民币账户、年度收益、因子评价、权重与运行配置，共 11 个文件。

表格中的曲线对应原报告的系列名称；六因子组合展示 Equal factor blend，其余多因子展示 Adaptive combination。

复现示例：

```powershell
uv run poolbench showcase/illiquidity/pool.json
uv run poolbench showcase/pool_9999/pool.json
```

[全部实验和全部对照曲线指标](all_experiments.csv) · [使用指南](../README.md)
