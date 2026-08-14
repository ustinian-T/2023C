"""Independent consistency checks for Question 4 generated outputs."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from questions.q4.code.q4_model import BASE_SCENARIO, SCENARIOS, load_source_metrics


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_csv(path, encoding="utf-8-sig")


def _read_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def validate_outputs(root: Path = ROOT, output_root: Path | None = None) -> dict:
    output_root = Path(output_root) if output_root is not None else root / "questions/q4/outputs"
    tables = output_root / "tables"
    results = output_root / "results"
    figures = output_root / "figures"

    diagnostics = _read_csv(tables / "q4_gap_diagnostics.csv")
    catalog = _read_csv(tables / "q4_data_catalog.csv")
    coverage = _read_csv(tables / "q4_coverage_matrix.csv").set_index("package_id")
    portfolios = _read_csv(tables / "q4_minimum_portfolios.csv")
    sensitivity = _read_csv(tables / "q4_sensitivity_analysis.csv")
    summary = _read_json(results / "q4_summary.json")
    source_metrics = load_source_metrics(root)

    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    required_outputs = [
        tables / "q4_gap_diagnostics.csv",
        tables / "q4_data_catalog.csv",
        tables / "q4_coverage_matrix.csv",
        tables / "q4_minimum_portfolios.csv",
        tables / "q4_sensitivity_analysis.csv",
        results / "q4_summary.json",
    ]
    check(
        "required_output_files_exist",
        all(path.is_file() for path in required_outputs),
        f"checked {len(required_outputs)} tabular/result files",
    )
    source_values = {key: value for key, value in source_metrics.items() if key != "source_files"}
    check(
        "source_metrics_match_q1_q2_q3",
        summary.get("key_evidence") == source_values,
        "summary evidence equals a fresh read of the verified Q1-Q3 outputs",
    )
    check(
        "source_files_are_traceable",
        all((root / relative).is_file() for relative in summary.get("source_files", {}).values()),
        "every source path recorded in q4_summary.json exists",
    )
    numeric = pd.to_numeric(diagnostics["metric_value"], errors="coerce")
    check(
        "gap_metrics_are_finite",
        numeric.notna().all() and all(math.isfinite(value) for value in numeric),
        f"finite diagnostic values: {numeric.notna().sum()}/{len(numeric)}",
    )
    check(
        "gap_ids_are_unique",
        diagnostics["gap_id"].is_unique,
        f"unique gaps: {diagnostics['gap_id'].nunique()}",
    )
    check(
        "gap_sources_are_nonempty",
        diagnostics["source_file"].fillna("").str.len().gt(0).all(),
        "each diagnostic row names its Q1-Q3 source",
    )
    check(
        "diagnostic_count_matches_summary",
        len(diagnostics) == summary.get("diagnostic_metric_count"),
        f"csv={len(diagnostics)}, summary={summary.get('diagnostic_metric_count')}",
    )
    check(
        "catalog_has_seven_packages",
        len(catalog) == 7 and catalog["package_id"].nunique() == 7,
        f"rows={len(catalog)}, unique={catalog['package_id'].nunique()}",
    )
    check(
        "catalog_fields_are_actionable",
        catalog["fields"].fillna("").str.contains("、").all()
        and catalog["collection_granularity"].fillna("").str.len().gt(4).all(),
        "each package contains multiple explicit fields and a collection granularity",
    )
    check(
        "catalog_privacy_boundaries_are_explicit",
        catalog["privacy_boundary"].fillna("").str.len().gt(8).all(),
        "each package has a nonempty privacy or confidentiality boundary",
    )
    matrix_values = coverage.to_numpy()
    check(
        "coverage_matrix_is_binary",
        set(matrix_values.ravel()).issubset({0, 1}),
        f"unique values={sorted(set(matrix_values.ravel()))}",
    )
    check(
        "coverage_matrix_dimensions_match_catalog",
        coverage.shape == (7, 8) and set(coverage.index) == set(catalog["package_id"]),
        f"shape={coverage.shape}",
    )

    base_rows = portfolios[portfolios["scenario_id"] == "base_core"]
    base_packages = tuple(sorted(base_rows.iloc[0]["package_ids"].split("|"))) if len(base_rows) == 1 else ()
    check(
        "base_portfolio_is_unique",
        len(base_rows) == 1,
        f"minimum solutions={len(base_rows)}",
    )
    check(
        "base_portfolio_has_five_packages",
        len(base_packages) == 5,
        f"package count={len(base_packages)}",
    )
    check(
        "base_portfolio_is_feasible",
        bool(base_packages) and BASE_SCENARIO.is_feasible(base_packages),
        "all seven base capability requirements are met",
    )
    deletion_minimal = bool(base_packages) and all(
        not BASE_SCENARIO.is_feasible(set(base_packages) - {package})
        for package in base_packages
    )
    check(
        "base_portfolio_is_deletion_minimal",
        deletion_minimal,
        "removing any selected package breaks at least one capability",
    )
    scenario_ids = {scenario.scenario_id for scenario in SCENARIOS}
    check(
        "all_scenarios_have_minimum_solution",
        set(portfolios["scenario_id"]) == scenario_ids
        and portfolios.groupby("scenario_id").size().ge(1).all(),
        f"covered scenarios={portfolios['scenario_id'].nunique()}/{len(scenario_ids)}",
    )
    scenario_lookup = {scenario.scenario_id: scenario for scenario in SCENARIOS}
    all_feasible = True
    all_minimal = True
    for row in portfolios.itertuples(index=False):
        packages = tuple(sorted(str(row.package_ids).split("|")))
        scenario = scenario_lookup[row.scenario_id]
        all_feasible &= scenario.is_feasible(packages)
        all_minimal &= all(
            not scenario.is_feasible(set(packages) - {package}) for package in packages
        )
    check(
        "all_reported_portfolios_are_feasible",
        all_feasible,
        "every exported portfolio satisfies its named scenario",
    )
    check(
        "all_reported_portfolios_are_deletion_minimal",
        all_minimal and portfolios["is_deletion_minimal"].astype(bool).all(),
        "every exported portfolio fails after any one selected package is removed",
    )
    check(
        "sensitivity_rates_are_bounded",
        sensitivity["inclusion_rate"].between(0, 1).all()
        and (sensitivity["included_scenario_count"] <= sensitivity["scenario_count"]).all(),
        "all inclusion frequencies lie in [0,1]",
    )
    tier_map = sensitivity.set_index("package_id")["priority_tier"].to_dict()
    expected_tiers = {
        "inventory_stockout": "一级：所有情景必选",
        "promotion_display_traffic": "一级：所有情景必选",
        "batch_loss_quality": "二级：核心情景必选",
        "supplier_quote_fulfillment": "二级：核心情景必选",
        "anonymous_basket": "二级：核心情景必选",
        "weather_calendar": "三级：扩展情景采用",
        "competitor_price": "三级：扩展情景采用",
    }
    check(
        "priority_tiers_match_structural_sensitivity",
        tier_map == expected_tiers,
        "tiers follow all-scenario inclusion, base inclusion, then extension-only status",
    )
    check(
        "no_invented_information_value_parameters",
        summary.get("invented_value_parameter_count") == 0,
        "Q4 reports no assumed r_j, EVSI, cost, or benefit coefficient",
    )
    check(
        "q2_error_relationship_is_normal",
        source_metrics["q2_demand_wape"] > source_metrics["q2_cost_wape"] > 0,
        "demand WAPE exceeds positive cost WAPE, consistent with Q2 diagnostics",
    )
    check(
        "q2_rates_are_in_probability_range",
        all(
            0 <= source_metrics[key] <= 1
            for key in (
                "q2_demand_wape",
                "q2_cost_wape",
                "q2_80pct_coverage",
                "q2_mean_stockout_probability",
                "q2_demand_satisfaction",
            )
        ),
        "all Q2 rate metrics lie in [0,1]",
    )
    check(
        "q3_base_lies_inside_sensitivity_ranges",
        source_metrics["q3_service_satisfaction_min"]
        <= source_metrics["q3_mean_demand_satisfaction"]
        <= source_metrics["q3_service_satisfaction_max"]
        and source_metrics["q3_expected_profit_min_yuan"]
        <= 163.57378808978714
        <= source_metrics["q3_expected_profit_max_yuan"],
        "Q3 main service and profit are contained in exported one-factor ranges",
    )
    check(
        "q3_tail_profit_is_conservative",
        source_metrics["q3_lower10pct_profit_yuan"] < source_metrics["q3_expected_profit_max_yuan"],
        "lower-tail profit remains below expected-profit outcomes",
    )
    expected_figures = [
        figures / f"{stem}.{suffix}"
        for stem in (
            "fig_q4_gap_evidence",
            "fig_q4_data_gap_matrix",
            "fig_q4_priority_robustness",
        )
        for suffix in ("png", "pdf")
    ]
    check(
        "all_figures_nonempty",
        all(path.is_file() and path.stat().st_size > 1_000 for path in expected_figures),
        f"nonempty figures={sum(path.is_file() and path.stat().st_size > 1_000 for path in expected_figures)}/{len(expected_figures)}",
    )

    report = {
        "model": summary.get("model"),
        "check_count": len(checks),
        "passed_count": sum(check["passed"] for check in checks),
        "failed_count": sum(not check["passed"] for check in checks),
        "all_checks_passed": all(check["passed"] for check in checks),
        "checks": checks,
    }
    results.mkdir(parents=True, exist_ok=True)
    (results / "q4_validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# 第四问输出验证报告",
        "",
        f"- 检查总数：{report['check_count']}",
        f"- 通过：{report['passed_count']}",
        f"- 失败：{report['failed_count']}",
        f"- 总体结论：{'通过' if report['all_checks_passed'] else '未通过'}",
        "",
        "| 检查项 | 状态 | 说明 |",
        "| --- | --- | --- |",
    ]
    for item in checks:
        lines.append(
            f"| {item['name']} | {'通过' if item['passed'] else '失败'} | {item['detail']} |"
        )
    (results / "validation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate Question 4 outputs")
    parser.add_argument("--output-root", type=Path, default=None)
    args = parser.parse_args()
    result = validate_outputs(output_root=args.output_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["all_checks_passed"] else 1)
