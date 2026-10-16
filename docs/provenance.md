# 代码来源

核心公式与组合流程取自用户指定的 `cf` 工程，源提交 `a694074d6f35090bc5814c9f0db102a508c8b15b`，遵循 MIT License，保留根目录 LICENSE。

| 原文件 | 本项目 | 复用内容 |
|---|---|---|
| `alphagen/data/expression.py` | `quantbt/expressions.py` | 算子公式、窗口和表达式语法 |
| `alphagen/utils/pytorch_utils.py` | `quantbt/metrics.py` | 截面标准化 |
| `alphagen/utils/correlation.py` | `quantbt/metrics.py` | 相关系数与绩效公式 |
| 原 `run_adaptive_combination.py` | `quantbt/combine.py` | 历史 Rank IC 筛选、滚动回归 |
| `plot_profit_curve.py` | `quantbt/report.py` | 真实日期对齐与曲线展示 |

计算核适配为 NumPy/Bottleneck；表达式使用受限 AST。账户、分项费用、历史 ST 状态与最终退出集中于数据和持仓模块。原入口和三个 pool 保存在初始 Git 提交 `26b5f60`。

历史状态先复用原工程的 BaoStock `isst`、`tradestatus` 文件，再通过同一数据源补齐日期，生成 `market_status/state.feather`。原工程目录保持不变。
