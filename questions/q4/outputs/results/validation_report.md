# 第四问输出验证报告

- 检查总数：27
- 通过：27
- 失败：0
- 总体结论：通过

| 检查项 | 状态 | 说明 |
| --- | --- | --- |
| required_output_files_exist | 通过 | checked 6 tabular/result files |
| source_metrics_match_q1_q2_q3 | 通过 | summary evidence equals a fresh read of the verified Q1-Q3 outputs |
| source_files_are_traceable | 通过 | every source path recorded in q4_summary.json exists |
| gap_metrics_are_finite | 通过 | finite diagnostic values: 13/13 |
| gap_ids_are_unique | 通过 | unique gaps: 13 |
| gap_sources_are_nonempty | 通过 | each diagnostic row names its Q1-Q3 source |
| diagnostic_count_matches_summary | 通过 | csv=13, summary=13 |
| catalog_has_seven_packages | 通过 | rows=7, unique=7 |
| catalog_fields_are_actionable | 通过 | each package contains multiple explicit fields and a collection granularity |
| catalog_privacy_boundaries_are_explicit | 通过 | each package has a nonempty privacy or confidentiality boundary |
| coverage_matrix_is_binary | 通过 | unique values=[np.int64(0), np.int64(1)] |
| coverage_matrix_dimensions_match_catalog | 通过 | shape=(7, 8) |
| base_portfolio_is_unique | 通过 | minimum solutions=1 |
| base_portfolio_has_five_packages | 通过 | package count=5 |
| base_portfolio_is_feasible | 通过 | all seven base capability requirements are met |
| base_portfolio_is_deletion_minimal | 通过 | removing any selected package breaks at least one capability |
| all_scenarios_have_minimum_solution | 通过 | covered scenarios=7/7 |
| all_reported_portfolios_are_feasible | 通过 | every exported portfolio satisfies its named scenario |
| all_reported_portfolios_are_deletion_minimal | 通过 | every exported portfolio fails after any one selected package is removed |
| sensitivity_rates_are_bounded | 通过 | all inclusion frequencies lie in [0,1] |
| priority_tiers_match_structural_sensitivity | 通过 | tiers follow all-scenario inclusion, base inclusion, then extension-only status |
| no_invented_information_value_parameters | 通过 | Q4 reports no assumed r_j, EVSI, cost, or benefit coefficient |
| q2_error_relationship_is_normal | 通过 | demand WAPE exceeds positive cost WAPE, consistent with Q2 diagnostics |
| q2_rates_are_in_probability_range | 通过 | all Q2 rate metrics lie in [0,1] |
| q3_base_lies_inside_sensitivity_ranges | 通过 | Q3 main service and profit are contained in exported one-factor ranges |
| q3_tail_profit_is_conservative | 通过 | lower-tail profit remains below expected-profit outcomes |
| all_figures_nonempty | 通过 | nonempty figures=6/6 |
