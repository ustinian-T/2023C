"""Independent structural and accounting checks for generated Q3 outputs."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "processed"
TABLES = ROOT / "questions" / "q3" / "outputs" / "tables"
RESULTS = ROOT / "questions" / "q3" / "outputs" / "results"


def main() -> None:
    checks: list[dict] = []

    def check(name: str, condition: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(condition), "detail": detail})

    required_files = [
        TABLES / "q3_candidate_diagnostics.csv",
        TABLES / "q3_price_grid.csv",
        TABLES / "q3_k_frontier.csv",
        TABLES / "q3_daily_strategy.csv",
        TABLES / "q3_category_summary.csv",
        TABLES / "q3_model_comparison.csv",
        TABLES / "q3_sensitivity_analysis.csv",
        TABLES / "q3_model_validation.csv",
        RESULTS / "q3_summary.json",
    ]
    for path in required_files:
        check(
            f"file:{path.name}",
            path.exists() and path.stat().st_size > 0,
            str(path.relative_to(ROOT)),
        )
    if not all(item["passed"] for item in checks):
        raise SystemExit("required Q3 output files are missing")

    candidate = pd.read_csv(TABLES / "q3_candidate_diagnostics.csv", dtype={"sku_code": str})
    grid = pd.read_csv(TABLES / "q3_price_grid.csv", dtype={"sku_code": str})
    frontier = pd.read_csv(TABLES / "q3_k_frontier.csv")
    strategy = pd.read_csv(TABLES / "q3_daily_strategy.csv", dtype={"sku_code": str})
    category = pd.read_csv(TABLES / "q3_category_summary.csv")
    comparison = pd.read_csv(TABLES / "q3_model_comparison.csv")
    sensitivity = pd.read_csv(TABLES / "q3_sensitivity_analysis.csv")
    model_validation = pd.read_csv(TABLES / "q3_model_validation.csv")
    summary = json.loads((RESULTS / "q3_summary.json").read_text(encoding="utf-8"))

    raw = pd.read_csv(
        DATA / "processed_daily_sku.csv",
        usecols=["date", "sku_code", "gross_sales_qty"],
        dtype={"sku_code": str},
    )
    raw["date"] = pd.to_datetime(raw["date"])
    expected_codes = set(
        raw.loc[
            raw["date"].between("2023-06-24", "2023-06-30")
            & (raw["gross_sales_qty"] > 0),
            "sku_code",
        ]
    )
    check("candidate_count_49", len(candidate) == 49, f"rows={len(candidate)}")
    check("candidate_exact_raw_set", set(candidate["sku_code"]) == expected_codes, f"raw={len(expected_codes)}")
    check("candidate_unique", candidate["sku_code"].is_unique, "SKU codes must be unique")
    check("candidate_complete", not candidate[["sku_name", "category_name", "predicted_cost_yuan_per_kg", "loss_rate"]].isna().any().any(), "identity/cost/loss fields")
    check("candidate_cost_positive", bool((candidate["predicted_cost_yuan_per_kg"] > 0).all()), "yuan/kg")
    check("candidate_loss_range", bool(candidate["loss_rate"].between(0, 1, inclusive="left").all()), "fraction")
    share_sums = candidate.groupby("category_name")["eb_share"].sum()
    check("eb_share_sums", np.allclose(share_sums, 1.0, atol=1e-9), share_sums.to_json(force_ascii=False))
    check("q1_not_forced", int(candidate["q1_covered"].sum()) == 26, "Q1 coverage is diagnostic only")

    check("grid_all_candidates", set(grid["sku_code"]) == expected_codes, f"grid SKUs={grid['sku_code'].nunique()}")
    check("grid_positive_prices", bool((grid["price_yuan_per_kg"] > 0).all()), "yuan/kg")
    check("grid_tenth_yuan", bool(np.allclose(grid["price_yuan_per_kg"] * 10, np.round(grid["price_yuan_per_kg"] * 10))), "0.1 yuan precision")
    check("grid_unique_levels", not grid.duplicated(["sku_code", "price_yuan_per_kg"]).any(), "no duplicate SKU-price choices")
    check("grid_finite", bool(np.isfinite(grid.select_dtypes(include=[np.number])).all().all()), "all numeric grid cells")

    check("frontier_has_27_to_33", frontier["assortment_size"].astype(int).tolist() == list(range(27, 34)), frontier["assortment_size"].tolist())
    check("frontier_count_identity", bool((frontier["selected_sku_count"] == frontier["assortment_size"]).all()), "selected=K")
    check("frontier_service_identity", np.allclose(frontier["expected_service_loss"] + frontier["mean_demand_satisfaction"], 1.0), "loss+satisfaction=1")
    check("frontier_risk_identity", np.allclose(frontier["risk_adjusted_profit_yuan"], 0.75 * frontier["expected_profit_yuan"] + 0.25 * frontier["lower10pct_profit_yuan"]), "gamma=0.25")
    check("frontier_order_cap", bool((frontier["total_order_qty_kg"] <= summary["q2_total_replenishment_upper_kg"] + 1e-6).all()), "Q2 Jul-1 cap")
    check(
        "frontier_order_floor",
        bool((frontier["total_order_qty_kg"] >= summary["q2_total_replenishment_lower_kg"] - 1e-6).all()),
        "+/-0.05% band floor",
    )
    check(
        "frontier_order_band_width",
        math.isclose(
            summary["q2_total_replenishment_upper_kg"] - summary["q2_total_replenishment_lower_kg"],
            2.0 * summary["replenishment_fluctuation"] * summary["q2_total_replenishment_baseline_kg"],
            abs_tol=1e-6,
        ),
        "symmetric +/-0.05% around Q2 total",
    )
    check("frontier_finite", bool(np.isfinite(frontier.select_dtypes(include=[np.number])).all().all()), "all numeric frontier cells")

    selected_count = len(strategy)
    check("strategy_selected_range", 27 <= selected_count <= 33, f"selected={selected_count}")
    check("strategy_selected_summary", selected_count == int(summary["selected_sku_count"]), "CSV/JSON")
    check("strategy_unique", strategy["sku_code"].is_unique, "one row per selected SKU")
    check("strategy_candidate_subset", set(strategy["sku_code"]).issubset(expected_codes), "selected candidates")
    check("strategy_min_order", bool((strategy["order_qty_kg"] >= 2.5 - 1e-8).all()), f"minimum={strategy['order_qty_kg'].min()}")
    check("strategy_order_cap", strategy["order_qty_kg"].sum() <= summary["q2_total_replenishment_upper_kg"] + 1e-6, f"total={strategy['order_qty_kg'].sum()}")
    check(
        "strategy_order_floor",
        strategy["order_qty_kg"].sum() >= summary["q2_total_replenishment_lower_kg"] - 1e-6,
        f"total={strategy['order_qty_kg'].sum()} floor={summary['q2_total_replenishment_lower_kg']}",
    )
    band_deviation = abs(
        strategy["order_qty_kg"].sum() - summary["q2_total_replenishment_baseline_kg"]
    ) / summary["q2_total_replenishment_baseline_kg"]
    check(
        "strategy_order_within_005pct",
        band_deviation <= summary["replenishment_fluctuation"] + 1e-9,
        f"|Q3-Q2|/Q2={100*band_deviation:.5f}%",
    )
    grid_keys = set(zip(grid["sku_code"], np.round(grid["price_yuan_per_kg"], 6)))
    strategy_keys = set(zip(strategy["sku_code"], np.round(strategy["price_yuan_per_kg"], 6)))
    check("strategy_prices_from_grid", strategy_keys.issubset(grid_keys), "all chosen prices are discrete choices")
    check("strategy_date", set(strategy["date"]) == {"2023-07-01"}, str(set(strategy["date"])))
    check("strategy_nonnegative_sales", bool((strategy[["expected_demand_kg", "expected_sales_kg"]] >= 0).all().all()), "kg")
    check("strategy_sales_le_demand", bool((strategy["expected_sales_kg"] <= strategy["expected_demand_kg"] + 1e-8).all()), "scenario-mean inequality")
    check("strategy_unsold_identity", np.allclose(strategy["expected_unsold_or_loss_kg"], strategy["order_qty_kg"] - strategy["expected_sales_kg"]), "order-sales")
    check("strategy_stockout_probability", bool(strategy["stockout_probability"].between(0, 1).all()), "probability")
    check("strategy_numeric_finite", bool(np.isfinite(strategy.select_dtypes(include=[np.number])).all().all()), "all numeric strategy cells")

    check("category_six_rows", len(category) == 6 and category["category_name"].nunique() == 6, f"rows={len(category)}")
    check("category_candidate_total", int(category["candidate_sku_count"].sum()) == 49, f"sum={category['candidate_sku_count'].sum()}")
    check("category_selected_total", int(category["selected_sku_count"].sum()) == selected_count, f"sum={category['selected_sku_count'].sum()}")
    check("category_order_reconcile", math.isclose(category["order_qty_kg"].sum(), strategy["order_qty_kg"].sum(), abs_tol=1e-6), "category/SKU total")
    check("category_profit_reconcile", math.isclose(category["expected_profit_yuan"].sum(), summary["main_strategy"]["expected_profit_yuan"], abs_tol=1e-6), "category/summary total")
    check("category_service_range", bool(category["mean_demand_satisfaction"].between(0, 1).all()), "category service")

    indexed_comparison = comparison.set_index("model")
    main_row = indexed_comparison.loc["lexicographic_scenario_milp"]
    base_row = indexed_comparison.loc["recent_sales_baseline"]
    check("comparison_main_matches_summary", math.isclose(main_row["expected_profit_yuan"], summary["main_strategy"]["expected_profit_yuan"], abs_tol=1e-8), "profit")
    check("comparison_service_improves", main_row["mean_demand_satisfaction"] > base_row["mean_demand_satisfaction"], "MILP vs baseline")
    check("comparison_profit_improves", main_row["expected_profit_yuan"] > base_row["expected_profit_yuan"], "MILP vs baseline")
    check("comparison_tail_improves", main_row["lower10pct_profit_yuan"] > base_row["lower10pct_profit_yuan"], "MILP vs baseline")
    check("summary_scenario_count", int(summary["evaluation_scenario_count"]) == 600, "full Q2 scenario set")
    check("summary_q1_pair_counts", sum(summary["q1_diagnostics"]["q1_pair_strength_counts"].values()) == 325, "covered pairs")
    check("summary_q1_not_objective", summary["q1_diagnostics"]["q1_used_in_primary_objective"] is False, "diagnostic use")

    check("sensitivity_nine_variants", len(sensitivity) == 9 and sensitivity["variant_id"].nunique() == 9, f"rows={len(sensitivity)}")
    check("sensitivity_one_baseline", (sensitivity["variant_id"] == "baseline").sum() == 1, "shared base solve")
    check("sensitivity_selected_33", bool((sensitivity["selected_sku_count"] == 33).all()), "all variants")
    check("sensitivity_cap_compliance", bool((sensitivity["total_order_qty_kg"] <= sensitivity["order_cap_kg"] + 1e-6).all()), "variant cap")
    if "order_floor_kg" in sensitivity.columns:
        finite_floor = sensitivity["order_floor_kg"].replace([np.inf, -np.inf], np.nan).dropna()
        check(
            "sensitivity_floor_compliance",
            bool(
                (
                    sensitivity.loc[finite_floor.index, "total_order_qty_kg"]
                    >= finite_floor - 1e-6
                ).all()
            ),
            "variant +/-0.05% floor",
        )
        nominal = sensitivity["order_cap_kg"] / (1.0 + summary["replenishment_fluctuation"])
        expected_floor = nominal * (1.0 - summary["replenishment_fluctuation"])
        check(
            "sensitivity_band_symmetric",
            bool(np.allclose(sensitivity["order_floor_kg"], expected_floor, atol=1e-6)),
            "floor = nominal*(1-0.0005)",
        )
    check("sensitivity_jaccard_range", bool(sensitivity["selection_jaccard_vs_baseline"].between(0, 1).all()), "[0,1]")
    sensitivity_numeric = sensitivity.select_dtypes(include=[np.number])
    check("sensitivity_finite", bool(np.isfinite(sensitivity_numeric).all().all()), "all numeric cells")
    baseline_sensitivity = sensitivity.set_index("variant_id").loc["baseline"]
    for column, summary_key in [
        ("mean_demand_satisfaction", "mean_demand_satisfaction"),
        ("expected_profit_yuan", "expected_profit_yuan"),
        ("lower10pct_profit_yuan", "lower10pct_profit_yuan"),
        ("total_order_qty_kg", "total_order_qty_kg"),
    ]:
        check(
            f"sensitivity_baseline_{column}",
            math.isclose(float(baseline_sensitivity[column]), float(summary["main_strategy"][summary_key]), abs_tol=1e-8),
            "sensitivity/main summary",
        )
    budget_rows = pd.concat(
        [
            sensitivity.loc[sensitivity["parameter_group"] == "order_cap_factor"],
            sensitivity.loc[sensitivity["variant_id"] == "baseline"],
        ],
        ignore_index=True,
    ).sort_values("order_cap_factor")
    check("sensitivity_budget_levels", np.allclose(budget_rows["order_cap_factor"], [0.85, 0.925, 1.0]), budget_rows["order_cap_factor"].tolist())
    check("sensitivity_budget_service_monotone", bool((budget_rows["expected_service_loss"].diff().dropna() <= 1e-6).all()), budget_rows["expected_service_loss"].tolist())
    check("sensitivity_summary_count", int(summary["sensitivity"]["variant_count"]) == 9, "JSON/CSV")

    generalization = model_validation.loc[
        model_validation["validation_type"] == "representative_generalization"
    ]
    fold_rows = model_validation.loc[model_validation["validation_type"] == "scenario_fold"]
    fold_stability = model_validation.loc[model_validation["validation_type"] == "fold_stability"]
    check("validation_generalization_row", len(generalization) == 1, f"rows={len(generalization)}")
    check("validation_generalization_gap", len(generalization) == 1 and float(generalization["absolute_difference"].iloc[0]) <= 0.03 + 1e-12, "<=0.03")
    check("validation_six_folds", len(fold_rows) == 6 and fold_rows["fold"].nunique() == 6, f"rows={len(fold_rows)}")
    check("validation_fold_sizes", bool((fold_rows["scenario_count"] == 100).all()), fold_rows["scenario_count"].tolist())
    check("validation_fold_service_range", bool(fold_rows["mean_demand_satisfaction"].between(0, 1).all()), "[0,1]")
    check("validation_fold_finite", bool(np.isfinite(fold_rows[["mean_demand_satisfaction", "expected_profit_yuan", "lower10pct_profit_yuan"]]).all().all()), "fold metrics")
    check("validation_fold_stability_row", len(fold_stability) == 1, f"rows={len(fold_stability)}")
    check("validation_fold_service_std", len(fold_stability) == 1 and float(fold_stability["value"].iloc[0]) <= 0.05 + 1e-12, "<=0.05")
    check("validation_required_rows_pass", bool(model_validation.loc[model_validation["threshold"].notna(), "passed"].astype(bool).all()), "threshold rows")
    check("validation_summary_pass", summary["model_validation"]["all_required_checks_passed"] is True, "JSON")

    report = {
        "status": "passed" if all(item["passed"] for item in checks) else "failed",
        "checks_passed": sum(item["passed"] for item in checks),
        "checks_total": len(checks),
        "checks": checks,
    }
    (RESULTS / "q3_validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Q3 validation: {report['checks_passed']}/{report['checks_total']} passed")
    for item in checks:
        print(f"[{'PASS' if item['passed'] else 'FAIL'}] {item['name']}: {item['detail']}")
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
