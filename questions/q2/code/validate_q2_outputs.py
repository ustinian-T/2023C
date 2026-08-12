"""Deterministic consistency checks for Question 2 outputs."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
TABLES = ROOT / "questions" / "q2" / "outputs" / "tables"
RESULTS = ROOT / "questions" / "q2" / "outputs" / "results"


def check(name: str, condition: bool, details: str = "") -> dict:
    return {"name": name, "status": "PASS" if bool(condition) else "FAIL", "details": details}


strategy = pd.read_csv(TABLES / "q2_daily_strategy.csv")
bounds = pd.read_csv(TABLES / "q2_decision_bounds.csv").set_index("category_name")
elasticity = pd.read_csv(TABLES / "q2_elasticity_estimates.csv")
metrics = pd.read_csv(TABLES / "q2_forecast_metrics.csv")
optimizer = pd.read_csv(TABLES / "q2_optimizer_checks.csv")
weekly = pd.read_csv(TABLES / "q2_weekly_risk_summary.csv")
daily = pd.read_csv(TABLES / "q2_daily_risk_summary.csv")
summary = json.loads((RESULTS / "q2_summary.json").read_text(encoding="utf-8"))

tests = []
tests.append(check("42 category-day decisions", len(strategy) == 42, str(len(strategy))))
tests.append(check("7 forecast dates", strategy["date"].nunique() == 7, str(strategy["date"].nunique())))
tests.append(check("6 categories", strategy["category_name"].nunique() == 6, str(strategy["category_name"].nunique())))
tests.append(check("3 weekly risk solutions", len(weekly) == 3, str(len(weekly))))
tests.append(check("all finite", np.isfinite(strategy.select_dtypes(include=[np.number]).to_numpy()).all()))
tests.append(check("positive prices", (strategy["price_yuan_per_kg"] > 0).all()))
tests.append(check("nonnegative replenishment", (strategy["replenishment_kg"] >= 0).all()))
tests.append(check("price-cost identity", np.allclose(
    strategy["price_yuan_per_kg"],
    strategy["forecast_wholesale_cost_yuan_per_kg"] * (1 + strategy["markup_rate"]),
    rtol=1e-10, atol=1e-10,
)))
markup_ok = []
q_ok = []
for _, row in strategy.iterrows():
    b = bounds.loc[row["category_name"]]
    markup_ok.append(b["markup_p05"] - 1e-9 <= row["markup_rate"] <= b["markup_upper"] + 1e-9)
    q_ok.append(row["replenishment_kg"] <= b["replenishment_upper_kg"] + 1e-9)
tests.append(check("markup bounds", all(markup_ok)))
tests.append(check("replenishment bounds", all(q_ok)))
markup_change_ok = []
for category, part in strategy.groupby("category_name"):
    part = part.sort_values("date")
    b = bounds.loc[category]
    values = part["markup_rate"].to_numpy()
    changes = np.r_[abs(values[0] - b["markup_median"]), np.abs(np.diff(values))]
    markup_change_ok.append(np.max(changes) <= b["markup_daily_change_p90"] + 1e-6)
tests.append(check("first-day and interday markup smoothing", all(markup_change_ok)))
tests.append(check("economic monotonicity", (elasticity["elasticity_used"] <= -0.05 + 1e-12).all()))
tests.append(check("forecast rows complete", len(metrics) == 6 and metrics.notna().all().all()))
tests.append(check("zero optimizer bound violation", optimizer["max_bound_violation"].max() <= 1e-10))
tests.append(check("zero material markup-change violation", optimizer["max_markup_change_violation"].max() <= 1e-6))
tests.append(check("SLSQP converged", optimizer["slsqp_success"].all()))
tests.append(check("two-seed main stability", summary["checks"]["main_two_seed_max_relative_gap"] < 1e-5))
tests.append(check(
    "joint demand-cost scenario correlation preserved",
    summary["scenario"]["max_abs_joint_demand_cost_corr_difference"] < 0.10,
))
main_weekly = weekly[np.isclose(weekly["risk_weight"], summary["risk"]["main_risk_weight"])].iloc[0]
main_daily = daily[np.isclose(daily["risk_weight"], summary["risk"]["main_risk_weight"])]
tests.append(check("weekly operating profit equals daily operating-profit sum", np.isclose(
    main_weekly["weekly_expected_profit_yuan"],
    main_daily["expected_operating_profit_yuan"].sum(), atol=1e-6,
)))
tests.append(check("weekly operating profit equals category contribution sum", np.isclose(
    main_weekly["weekly_expected_profit_yuan"], strategy["expected_profit_yuan"].sum(), atol=1e-6,
)))
tests.append(check("weekly service-adjusted profit equals category contribution sum", np.isclose(
    main_weekly["weekly_expected_service_adjusted_profit_yuan"],
    strategy["expected_service_adjusted_profit_yuan"].sum(), atol=1e-6,
)))
tests.append(check("regularized profit subtracts reference penalty exactly once", np.isclose(
    main_weekly["weekly_expected_regularized_profit_yuan"],
    main_weekly["weekly_expected_service_adjusted_profit_yuan"]
    - main_weekly["reference_penalty_yuan"],
    atol=1e-6,
)))
tests.append(check("weekly tail is evaluated after seven-day aggregation", not np.isclose(
    main_weekly["weekly_worst10pct_regularized_profit_yuan"],
    main_daily["worst10pct_regularized_profit_yuan"].sum(),
    atol=1e-6,
)))
tests.append(check("summary uses joint weekly regularized tail", np.isclose(
    summary["main_strategy"]["weekly_worst10pct_regularized_profit_yuan"],
    main_weekly["weekly_worst10pct_regularized_profit_yuan"],
    atol=1e-6,
)))
tests.append(check("risk tradeoff direction", (
    summary["risk_neutral"]["weekly_expected_regularized_profit_yuan"]
    >= summary["main_strategy"]["weekly_expected_regularized_profit_yuan"]
    >= summary["high_risk_aversion"]["weekly_expected_regularized_profit_yuan"]
    and summary["risk_neutral"]["weekly_worst10pct_regularized_profit_yuan"]
    <= summary["main_strategy"]["weekly_worst10pct_regularized_profit_yuan"]
    <= summary["high_risk_aversion"]["weekly_worst10pct_regularized_profit_yuan"]
)))

# New checks for improved model
tests.append(check("stockout probability is a valid nondegenerate probability", (
    0.0 < strategy["stockout_probability"].mean() < 0.90
), str(strategy["stockout_probability"].mean())))
at_bound_count = 0
for _, row in strategy.iterrows():
    b = bounds.loc[row["category_name"]]
    if abs(row["markup_rate"] - b["markup_upper"]) < 1e-6:
        at_bound_count += 1
total_decisions = len(strategy)
tests.append(check(
    "not all markups at upper bound (reference penalty effective)",
    at_bound_count < total_decisions * 0.85,
    f"{at_bound_count}/{total_decisions} at upper bound",
))
fallback_rows = elasticity[elasticity["elasticity_raw"] >= 0]
tests.append(check("nonnegative category responses use empirical pooled fallback", (
    len(fallback_rows) > 0
    and fallback_rows["pooled_fallback_applied"].eq(1).all()
    and np.allclose(fallback_rows["elasticity_used"], fallback_rows["pooled_elasticity"])
)))
tests.append(check(
    "operating profit at least 1.2x operating baseline",
    summary["main_strategy"]["weekly_expected_profit_yuan"]
    >= 1.2 * summary["baseline"]["weekly_expected_profit_yuan"],
))
tests.append(check(
    "service-adjusted comparison uses same accounting basis",
    summary["main_strategy"]["weekly_expected_service_adjusted_profit_yuan"]
    >= 1.2 * summary["baseline"]["weekly_expected_service_adjusted_profit_yuan"],
))
tests.append(check(
    "improved two-seed stability gap < 1e-4",
    summary["checks"]["main_two_seed_max_relative_gap"] < 1e-4,
))

# Check sensitivity and comparison files exist
sens_path = TABLES / "q2_sensitivity_analysis.csv"
comp_path = TABLES / "q2_model_comparison.csv"
tests.append(check("sensitivity analysis file exists", sens_path.exists()))
tests.append(check("model comparison file exists", comp_path.exists()))
if sens_path.exists():
    sens = pd.read_csv(sens_path)
    tests.append(check(
        "complete sensitivity grid",
        len(sens) == 8
        and sens.loc[sens["parameter"].eq("goodwill_cost_ratio"), "value"].nunique() == 4
        and sens.loc[sens["parameter"].eq("reference_penalty_weight"), "value"].nunique() == 4,
        str(len(sens)),
    ))
    main_sensitivity = sens[
        sens["parameter"].eq("reference_penalty_weight")
        & np.isclose(sens["value"], summary["penalty_parameters"]["reference_penalty_weight"])
    ]
    tests.append(check("sensitivity upper-bound count uses category bounds", (
        len(main_sensitivity) == 1
        and int(main_sensitivity["markups_at_upper_bound"].iloc[0]) == at_bound_count
    ), f"{int(main_sensitivity['markups_at_upper_bound'].iloc[0]) if len(main_sensitivity) else 'missing'}/{at_bound_count}"))
if "penalty_parameters" in summary:
    pp = summary["penalty_parameters"]
    tests.append(check(
        "penalty parameters in summary",
        "goodwill_cost_ratio" in pp and "reference_penalty_weight" in pp,
    ))

passed = sum(t["status"] == "PASS" for t in tests)
report = {"passed": passed, "total": len(tests), "tests": tests}
(RESULTS / "q2_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
if passed != len(tests):
    raise SystemExit(1)
