# 代码来源与精简适配

源目录为用户指定的 `\\wsl.localhost\Ubuntu-22.04\home\groy\cf`，读取时 Git 提交为：

```text
a694074d6f35090bc5814c9f0db102a508c8b15b
```

源工程采用 MIT License，Copyright (c) 2026 Roy Gao。项目根目录保留原 LICENSE。未修改源目录，没有复制其 `.env`、数据集、模型、挖掘算法、论文或运行日志。

## 实际选取部分

| 源文件 | 本项目去向 | 保留和适配内容 |
|---|---|---|
| `src/alphagen/data/expression.py` | `quantbt/expressions.py` | 先选取复制，再保留算子公式与窗口约定，改成 NumPy/Bottleneck；重写受限解析与数组求值，移除 Torch/Qlib 类层级和编辑距离 |
| `src/alphagen/utils/pytorch_utils.py` | `quantbt/metrics.py` | 每日截面均值/总体标准差归一化；增加无信号与缺失规则、±5 截断 |
| `src/alphagen/utils/correlation.py` | `quantbt/metrics.py` | 先复制原文件，保留相关系数与风险指标思路，改成有限值掩码、平均秩、复利净值和初始资本回撤 |
| 用户目录原 `run_adaptive_combination.py` | `quantbt/combine.py` + 兼容入口 | 保留历史 Rank IC 筛选、滚动回归结构；明确标签成熟边界、排序、真正生效的岭惩罚和可审计回退 |
| `plot_profit_curve.py` | `quantbt/report.py` | 参考带真实日期的曲线注册与绘图方式；重写为同图净值、回撤、年收益、换手、指标，逐月年-月刻度 |

这里没有整包保留 `alphagen`：其 Qlib 数据接口、GPU 运算、搜索组件不是这个回测系统的必要依赖。新的 `portfolio.py` 专门负责持仓与现金，避免原来的“当日分数直接乘未来收益”评价与可执行时序混淆。

原入口与三个输入 pool 在本地 Git 的首个提交 `26b5f60` 中完整保存；最终入口只有调用新系统的兼容层。原表达式文件不改写，缺失特征通过显式数据适配处理。

## 源文件快照校验

读取的文件可能包含源工程尚未提交的工作，所以同时记录文件本身的 SHA256，而不只依赖源提交号：

```text
src/alphagen/data/expression.py
3ee391c1119633bceb56572e88d9ed5fda584b63ad4b4f87c3e2150b3876df48

src/alphagen/utils/correlation.py
475209d633ef368bc101c03a6f93c66198c3240903ed163ad11c7dc71cfa1458

src/alphagen/utils/pytorch_utils.py
1907f6bf58ce69736ce2dc184f8ffcd7fd698b98228ae0d41941a94511db942c

用户提供的原 run_adaptive_combination.py
337db672806d70343f98cb2bcdd31de8b90770d06bcfdc7717b52b988a1700b1
```

## 有意调整的行为

1. 唯一评价期固定为 2021-01-01 至 2026-10-01；不继承旧验证/测试年份与 Qlib 路径。
2. 任何特征计算前截断到结束日；回归和筛选都只读已兑现标签。
3. 监督标签按下一开盘入场；资金收益按真实持仓日频记账，不把 20 日远期收益当每日收益。
4. 默认有限历史 252 日、20 日重新训练，而非每天对无限历史重新拟合。参数仍允许更短更新间隔。
5. 不进行错误的 SVD 删行/列启发式；用小规模岭回归稳定处理共线性，并保留全部训练样本。
6. 净值、最大回撤与年度收益使用复利；不继承原图 `1+cumsum(ret)` 的口径。
7. 单因子尊重作者写出的方向，适应性回归只在指定或多因子默认模式使用；等权对照始终包含全部输入因子。
8. 代理字段和算子边界差异全部显式记录，详见[算子手册](operators.md)。
