# 输出目录

所有文件均由 `questions/q2/code/q2_model.py` 确定性生成。

## tables

- `q2_daily_strategy.csv`：主风险权重下 42 条最终日—品类策略；
- `q2_strategy_all_risk_weights.csv`：三档风险权重的全部策略；
- `q2_daily_risk_summary.csv`：各风险权重的逐日利润诊断；
- `q2_weekly_risk_summary.csv`：以七日联合场景直接计算的周级期望、下尾利润和目标值；
- `q2_baseline_summary.csv`：历史中位加价与中位需求补货基线；
- `q2_elasticity_estimates.csv`：原始、Bootstrap、收缩及最终使用的条件价格响应系数（历史文件名保留 `elasticity` 以兼容代码）；
- `q2_forecast_metrics.csv`：需求和成本滚动验证指标及融合权重；
- `q2_decision_bounds.csv`：历史数据生成的加价、日变动和补货边界；
- `q2_optimizer_checks.csv`：周级求解收敛、双初值稳定性及约束违规量。
- `q2_sensitivity_analysis.csv`：4 档商誉成本系数与 4 档参考正则权重的完整重优化结果；
- `q2_model_comparison.csv`：主策略与历史中位加价—中位需求补货基线的同口径比较。

## results

- `q2_summary.json`：论文和程序可直接读取的核心结果；
- `q2_validation.json`：36 项输出一致性验证明细。
- `q2_strict_review.md`：题意、模型、代码、复现性与风险的严格审查报告。

## figures

- `fig_q2_daily_replenishment_pricing.*`：未来一周日补货与定价策略；
- `fig_q2_strategy_heatmaps.*`：42 条“日期—品类”补货与售价决策矩阵；
- `fig_q2_price_response_forest.*`：条件价格响应估计、置信区间、采用值与回退边界；
- `fig_q2_profit_dumbbell.*`：历史中位基线与主策略的同口径收益哑铃对比；
- `fig_q2_risk_return_tradeoff.*`：三档风险权重下的期望—下尾权衡；
- `fig_q2_management_sensitivity.*`：商誉成本与参考加价正则的四联敏感性分析。

利润字段严格区分经营利润、扣除商誉成本后的服务调整利润、再扣除参考正则后的模型评价值以及风险目标。只有经营利润是销售收入减采购成本的会计口径，其余指标用于比较服务与稳定性。CSV 使用 UTF-8 with BOM，便于在中文版 Excel 中直接打开。结果不应手工修改；参数或代码变化后应重新运行模型和验证脚本。
