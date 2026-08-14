from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import subprocess
import sys

import pandas as pd

from questions.q4.code.q4_model import (
    BASE_SCENARIO,
    build_coverage_matrix,
    build_data_catalog,
    build_gap_diagnostics,
    build_sensitivity_analysis,
    enumerate_minimum_portfolios,
    load_source_metrics,
    run_model,
)
from questions.q4.code.validate_q4_outputs import validate_outputs


ROOT = Path(__file__).resolve().parents[3]


class SourceMetricTests(unittest.TestCase):
    def test_load_source_metrics_matches_verified_q1_q2_q3_outputs(self):
        metrics = load_source_metrics(ROOT)

        self.assertEqual(metrics["q1_distribution_objects"], 70)
        self.assertEqual(metrics["q1_parametric_accepted"], 45)
        self.assertEqual(metrics["q1_all_sku_pairs"], 2016)
        self.assertEqual(metrics["q1_clear_sku_pairs"], 18)
        self.assertAlmostEqual(metrics["q2_demand_wape"], 0.358849784930296)
        self.assertAlmostEqual(metrics["q2_cost_wape"], 0.15282047420040587)
        self.assertEqual(metrics["q2_pooled_fallback_categories"], 2)
        self.assertAlmostEqual(metrics["q3_mean_demand_satisfaction"], 0.778185107091021)
        self.assertAlmostEqual(metrics["q3_lower10pct_profit_yuan"], -423.2096107493048)
        self.assertAlmostEqual(metrics["q3_minimum_selection_jaccard"], 0.8333333333333334)

    def test_load_source_metrics_rejects_missing_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                load_source_metrics(Path(tmp))

    def test_gap_diagnostics_are_finite_and_source_traceable(self):
        diagnostics = build_gap_diagnostics(load_source_metrics(ROOT))

        required = {
            "gap_id",
            "question",
            "metric_name",
            "metric_value",
            "unit",
            "interpretation",
            "source_file",
        }
        self.assertTrue(required.issubset(diagnostics.columns))
        self.assertGreaterEqual(len(diagnostics), 10)
        self.assertTrue(pd.to_numeric(diagnostics["metric_value"], errors="coerce").notna().all())
        self.assertTrue(diagnostics["source_file"].str.len().gt(0).all())


class DataCatalogTests(unittest.TestCase):
    def test_catalog_has_seven_auditable_packages_and_privacy_boundaries(self):
        catalog = build_data_catalog()

        self.assertEqual(len(catalog), 7)
        self.assertEqual(catalog["package_id"].nunique(), 7)
        self.assertTrue(
            {
                "package_id",
                "data_name",
                "fields",
                "collection_granularity",
                "helps_questions",
                "privacy_boundary",
            }.issubset(catalog.columns)
        )
        basket = catalog.set_index("package_id").loc["anonymous_basket"]
        self.assertIn("不采集姓名", basket["privacy_boundary"])

    def test_coverage_matrix_is_binary_and_uses_known_packages(self):
        catalog = build_data_catalog()
        matrix = build_coverage_matrix()

        self.assertEqual(set(matrix.index), set(catalog["package_id"]))
        self.assertTrue(set(matrix.to_numpy().ravel()).issubset({0, 1}))
        self.assertEqual(matrix.loc["inventory_stockout", "latent_demand"], 1)
        self.assertEqual(matrix.loc["anonymous_basket", "assortment_substitution"], 1)


class PortfolioTests(unittest.TestCase):
    def test_base_scenario_has_expected_unique_minimum_portfolio(self):
        portfolios = enumerate_minimum_portfolios(BASE_SCENARIO)

        self.assertEqual(
            portfolios,
            [
                (
                    "anonymous_basket",
                    "batch_loss_quality",
                    "inventory_stockout",
                    "promotion_display_traffic",
                    "supplier_quote_fulfillment",
                )
            ],
        )

    def test_each_base_package_is_necessary_for_base_capabilities(self):
        portfolio = set(enumerate_minimum_portfolios(BASE_SCENARIO)[0])
        for package in sorted(portfolio):
            reduced = tuple(sorted(portfolio - {package}))
            self.assertFalse(BASE_SCENARIO.is_feasible(reduced), package)

    def test_sensitivity_has_stable_tiers_without_subjective_weights(self):
        sensitivity = build_sensitivity_analysis()
        tiers = sensitivity.set_index("package_id")["priority_tier"].to_dict()

        self.assertEqual(tiers["inventory_stockout"], "一级：所有情景必选")
        self.assertEqual(tiers["promotion_display_traffic"], "一级：所有情景必选")
        self.assertEqual(tiers["batch_loss_quality"], "二级：核心情景必选")
        self.assertEqual(tiers["supplier_quote_fulfillment"], "二级：核心情景必选")
        self.assertEqual(tiers["anonymous_basket"], "二级：核心情景必选")
        self.assertEqual(tiers["weather_calendar"], "三级：扩展情景采用")
        self.assertEqual(tiers["competitor_price"], "三级：扩展情景采用")


class EndToEndTests(unittest.TestCase):
    def test_run_model_writes_complete_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_model(ROOT, output_root=Path(tmp))
            output_root = Path(tmp)

            self.assertEqual(summary["invented_value_parameter_count"], 0)
            self.assertTrue(summary["base_portfolio"]["is_feasible"])
            self.assertTrue(summary["base_portfolio"]["is_deletion_minimal"])
            for relative in (
                "tables/q4_gap_diagnostics.csv",
                "tables/q4_data_catalog.csv",
                "tables/q4_coverage_matrix.csv",
                "tables/q4_minimum_portfolios.csv",
                "tables/q4_sensitivity_analysis.csv",
                "results/q4_summary.json",
                "figures/fig_q4_gap_evidence.png",
                "figures/fig_q4_data_gap_matrix.png",
                "figures/fig_q4_priority_robustness.png",
            ):
                self.assertTrue((output_root / relative).is_file(), relative)

    def test_independent_validator_confirms_required_model_properties(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            run_model(ROOT, output_root=output_root)
            report = validate_outputs(ROOT, output_root=output_root)

            self.assertTrue(report["all_checks_passed"])
            self.assertGreaterEqual(report["check_count"], 20)
            required_checks = {
                "source_metrics_match_q1_q2_q3",
                "gap_metrics_are_finite",
                "base_portfolio_is_feasible",
                "base_portfolio_is_deletion_minimal",
                "all_scenarios_have_minimum_solution",
                "priority_tiers_match_structural_sensitivity",
                "all_figures_nonempty",
            }
            check_names = {check["name"] for check in report["checks"]}
            self.assertTrue(required_checks.issubset(check_names))

    def test_validator_runs_as_direct_script_with_explicit_output_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            run_model(ROOT, output_root=output_root)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "questions/q4/code/validate_q4_outputs.py"),
                    "--output-root",
                    str(output_root),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(
                completed.returncode,
                0,
                (completed.stdout or "") + (completed.stderr or ""),
            )


if __name__ == "__main__":
    unittest.main()
