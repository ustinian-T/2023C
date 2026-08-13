# 输出目录

`tables/` 包含：

- `q3_daily_strategy.csv`：最终 33 个单品的价格、订货量、场景销售与利润指标；
- `q3_k_frontier.csv`：K=27-33 的服务—利润前沿；
- `q3_candidate_diagnostics.csv`：49 个候选的成本、损耗、动态份额和 Q1 覆盖；
- `q3_price_grid.csv`：全部离散价格备选及历史来源；
- `q3_category_summary.csv`：六品类汇总；
- `q3_model_comparison.csv`：主模型与近期销量基线的同场景比较。
- `q3_sensitivity_analysis.csv`：风险权重、弹性、SKU 份额和采购上限的 9 组重求解结果；
- `q3_model_validation.csv`：代表场景泛化、六折稳定性和基线检验明细。

`results/q3_summary.json` 保存核心参数、模型指纹、检验和灵敏度摘要；`results/q3_validation.json` 保存 77 项独立校验结果。CSV 使用 UTF-8 BOM，金额单位为元，重量单位为 kg，价格单位为元/kg。
