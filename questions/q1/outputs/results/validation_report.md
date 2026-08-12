# Q1 验证与结果追踪报告

## 1. 运行状态

- 输入：处理后的 `processed_daily_sku.csv` 与 `processed_daily_category.csv`，未重复清洗原始附件。
- 日期范围：2020-07-01 至 2023-06-30。
- 日-单品重复键、日-品类重复键、负销量记录均为 0。
- 随机种子：20230907。
- Python 主程序完整运行成功；MATLAB 六组 PNG/PDF 图完整导出。

## 2. 关键结果及来源

| 结论 | 数值 | 直接证据 |
| --- | ---: | --- |
| 全部/入选单品数 | 251 / 47 | `outputs/tables/tab_q1_sku_activity_filter.csv` |
| 单品公共建模窗口 | 2021-01-30 至 2022-09-08，共 587 天 | `outputs/results/q1_summary.json` |
| 参数分布接受/KDE 回退对象数 | 30 / 23 | `outputs/tables/tab_q1_distribution_summary.csv` |
| 单品 MIC 99% 阈值/候选边数 | 0.7071 / 18 | `outputs/results/q1_summary.json`、`outputs/tables/tab_q1_sku_pair_measures.csv` |
| 单品 Graphical Lasso 最优正则强度 | 0.1137 | `outputs/tables/tab_q1_sku_alpha_path.csv` |
| 精度矩阵最小特征值 | 0.1598 | `outputs/results/q1_summary.json` |
| 单品 Bootstrap 成功数 | 100 / 100 | `outputs/results/q1_summary.json` |
| 最终单品稳定边 | 10 条：6 正、4 负 | `outputs/tables/tab_q1_sku_network_edges.csv` |
| 连通/孤立单品节点 | 12 / 35 | `outputs/tables/tab_q1_sku_node_metrics.csv` |
| 品类层最终稳定边 | 2 条，均为正边 | `outputs/tables/tab_q1_category_network_edges.csv` |

六品类正销量条件分布中，水生根茎类、花叶类、花菜类和茄类的 AIC 最优分布为 Gamma；辣椒类和食用菌为 Lognormal，且六个品类的 KS 检验均未在 5% 水平拒绝。47 个入选单品中 24 个接受参数分布，23 个回退为 KDE，说明单品分布异质性明显。

绝对条件相关最大的稳定边为“姬菇(1)--海鲜菇(1)”（0.3125，稳定率 100%）。较强负边包括“海鲜菇(1)--长线茄”（-0.1746，100%）、“枝江红菜苔--灯笼椒(1)”（-0.1198，100%）和“姬菇(1)--长线茄”（-0.1157，100%）。品类层稳定正边为“花菜类--辣椒类”（0.3311，100%）与“花菜类--食用菌”（0.0562，75.5%）。这些边只表示潜在同步/互补或潜在替代，不构成因果结论。

## 3. 验证结果

### 3.1 基线比较

按与最终网络相同边数截取原始销量 Spearman 强边，和最终稳定边的 Jaccard 为 0。该结果表明：原始销量的强相关主要受共同季节、趋势或全局经营节奏影响；去除时间结构并控制其他商品后，保留下来的直接条件关联完全不同。证据见 `outputs/tables/tab_q1_sku_baseline_comparison.csv`。

### 3.2 MIC 零分布

MIC 采用平均秩处理并列零值，避免把时间先后顺序编码为虚假非线性。零分布通过随机循环移位构造，在保留各序列自相关的同时破坏同期对齐。单品层 2000 个替代得分的 99% 分位为 0.7071，最终 18 对超过阈值。证据见 `outputs/tables/tab_q1_sku_mic_null.csv` 和 `outputs/figures/fig_q1_mic_graphical_lasso.png`。

### 3.3 Graphical Lasso 与正定性

EBIC 在正则强度 0.1137 处最小；对应精度矩阵最小特征值为 0.1598，大于 0，满足正定要求。正则路径见 `outputs/tables/tab_q1_sku_alpha_path.csv` 与 `outputs/figures/fig_q1_robustness.png`。

### 3.4 时间块 Bootstrap

单品层 100 次、品类层 200 次移动块 Bootstrap 全部拟合成功；块长 14 天用于保留局部时间依赖。最终边要求同号出现率至少 70%。稳定率门槛从 0.70 提高到 0.80 后，单品边数由 10 降至 8，保留 80% 的基准边；降低到 0.60 时边集合不变。

### 3.5 参数敏感性

- Graphical Lasso 正则强度乘以 0.8、1.0、1.2 时，MIC 与非零精度交集均保持 10 条，Jaccard 为 1。
- MIC 零分布分位由 0.990 调到 0.975 时边数为 15，调到 0.995 时为 3；MIC 阈值是当前结论最敏感的参数，论文应报告此点。
- 品类层在 0.975 分位时得到 5 条边，在 0.990 与 0.995 时均为 2 条；第二条较弱品类边的 Bootstrap 稳定率为 75.5%，不宜过度强调。

证据见 `outputs/tables/tab_q1_sku_sensitivity.csv` 与 `outputs/tables/tab_q1_category_sensitivity.csv`。

## 4. 官方 benchmark 对照

中国大学生在线提供 2023 C 题官方讲评入口（https://dxs.moe.gov.cn/zx/a/hd_sxjm_sxjmstjp_2023sxjmstjp/231207/1869893.shtml）以及“建模好论文的若干特征”课程入口。官方讲评正文以图片形式发布，本次不复制其图像内容，也不据此虚构具体评分标准；仅将其作为题意覆盖和竞赛论文可读性的参照。当前方案具有基线、机制、验证、图表和结果追踪，但因缺货状态不可观测且 MIC 为可复现近似值，不能称为严格因果模型或保证一等奖的方案。

## 5. 局限与结论边界

1. 单品在首末记录之间没有记录的日期被视为零销量，可能混合“无需求”和“未上架/缺货”。
2. `mic_approx` 是等频网格近似，不等同于 MINE 软件的 MICe；因此文件和论文均保留“近似”字样。
3. Graphical Lasso 在秩高斯残差上给出条件关联，但无法排除促销、陈列位置、价格变化、天气和客流等未观测混杂。
4. 高活跃度筛选提高了协方差稳定性，但结论不覆盖大量短生命周期或低频单品。
5. 网络适合作为后续补货组合的候选约束或场景输入，不应直接作为替代弹性参数。

综合判断：核心机制、验证和追踪链条已闭合，数值结果可复现；主要结论应表述为“稳定潜在关联”，不能升级为因果或真实购物篮互补结论。

## 6. 交付文件自动校验

`code/validate_q1_outputs.py` 已执行，38 项跨文件检查全部通过，报告保存于 `outputs/results/output_validation.json`。检查覆盖边数与符号、MIC/Bootstrap 阈值、正定性、敏感性、六组 PNG/PDF 成对导出、PNG 尺寸、归档 XLSX 容器完整性和论文占位符。该验证器不编译 LaTeX；`report/main.tex` 需另行使用支持中文的 TeX 引擎编译。`outputs/workbooks/q1_model_results.xlsx` 是第一问完成时保留的归档总表，当前模型流水线不自动重建它，可复现结果源为 `outputs/tables/` 与 `outputs/results/`。
