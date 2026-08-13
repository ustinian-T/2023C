import unittest

import numpy as np
import pandas as pd

import q3_model as q3


class CandidateAndShareTests(unittest.TestCase):
    def test_candidates_use_positive_retail_sales_in_exact_week(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    ["2023-06-23", "2023-06-24", "2023-06-25", "2023-06-30", "2023-07-01"]
                ),
                "sku_code": ["A", "A", "B", "C", "D"],
                "sku_name": ["甲", "甲", "乙", "丙", "丁"],
                "category_name": ["花叶类", "花叶类", "辣椒类", "食用菌", "花菜类"],
                "gross_sales_qty": [9.0, 2.0, 0.0, 3.0, 8.0],
                "gross_revenue": [90.0, 24.0, 0.0, 45.0, 96.0],
                "wholesale_price": [5.0, 6.0, 4.0, 8.0, 5.0],
                "loss_rate_pct": [10.0, 10.0, 8.0, 2.0, 9.0],
            }
        )

        candidates = q3.identify_candidates(frame, "2023-06-24", "2023-06-30")

        self.assertEqual(candidates["sku_code"].tolist(), ["A", "C"])
        self.assertAlmostEqual(candidates.loc[0, "recent_sales_qty_kg"], 2.0)
        self.assertAlmostEqual(candidates.loc[0, "reference_price_yuan_per_kg"], 12.0)
        self.assertNotIn("B", candidates["sku_code"].tolist())

    def test_empirical_bayes_shares_sum_to_one_and_shrink_sparse_sku(self):
        table = pd.DataFrame(
            {
                "sku_code": ["A", "B", "C"],
                "category_name": ["花叶类", "花叶类", "花叶类"],
                "recent_qty": [1.0, 9.0, 0.0],
                "long_share": [0.50, 0.25, 0.25],
            }
        )

        result = q3.empirical_bayes_shares(table, kappa_by_category={"花叶类": 10.0})

        self.assertAlmostEqual(result["eb_share"].sum(), 1.0, places=12)
        self.assertTrue((result["eb_share"] >= 0).all())
        sparse = result.set_index("sku_code").loc["C", "eb_share"]
        self.assertGreater(sparse, 0.0)
        self.assertAlmostEqual(sparse, 0.125, places=12)


class PriceAndScenarioTests(unittest.TestCase):
    def test_price_grid_uses_category_fallback_for_sparse_sku_and_respects_bounds(self):
        history = pd.DataFrame(
            {
                "date": pd.to_datetime(["2023-06-01", "2023-06-02", "2023-06-03", "2023-06-04"]),
                "sku_code": ["A", "A", "B", "B"],
                "category_name": ["花叶类"] * 4,
                "gross_sales_qty": [2.0, 3.0, 5.0, 4.0],
                "gross_weighted_avg_price": [10.0, 11.0, 12.0, 13.0],
                "wholesale_price": [6.0, 6.0, 6.0, 6.0],
            }
        )
        candidates = pd.DataFrame(
            {
                "sku_code": ["A"],
                "sku_name": ["甲"],
                "category_name": ["花叶类"],
                "predicted_cost_yuan_per_kg": [6.0],
            }
        )
        bounds = pd.DataFrame(
            {
                "category_name": ["花叶类"],
                "markup_p05": [0.20],
                "markup_median": [0.50],
                "markup_upper": [0.80],
            }
        )

        grid = q3.build_price_grid(history, candidates, bounds, min_sku_days=30, min_unique_prices=5)

        self.assertEqual(grid["grid_source"].unique().tolist(), ["category_fallback"])
        self.assertGreaterEqual(grid["markup_rate"].min(), 0.20 - 1e-12)
        self.assertLessEqual(grid["markup_rate"].max(), 0.80 + 1e-12)
        self.assertTrue(np.allclose(grid["price_yuan_per_kg"] * 10, np.round(grid["price_yuan_per_kg"] * 10)))
        self.assertGreaterEqual(len(grid), 3)

    def test_representative_scenarios_are_deterministic_and_keep_extremes(self):
        category_demand = np.array(
            [[1.0, 2.0], [2.0, 2.0], [10.0, 1.0], [3.0, 3.0], [4.0, 4.0], [20.0, 2.0]]
        )

        first = q3.select_representative_scenarios(category_demand, 3)
        second = q3.select_representative_scenarios(category_demand, 3)

        np.testing.assert_array_equal(first, second)
        self.assertIn(0, first.tolist())
        self.assertIn(5, first.tolist())
        self.assertEqual(len(np.unique(first)), 3)

    def test_sku_demand_reconciles_to_category_demand_at_reference_price(self):
        shares = np.array([[0.25, 0.75], [0.40, 0.60]])
        category_demand = np.array([100.0, 80.0])
        prices = np.array([10.0, 20.0])
        reference_prices = np.array([10.0, 20.0])
        elasticities = np.array([-0.5, -0.5])

        demand = q3.build_sku_demand_scenarios(
            shares, category_demand, prices, reference_prices, elasticities
        )

        np.testing.assert_allclose(demand.sum(axis=1), category_demand)
        self.assertTrue((demand >= 0).all())

    def test_big_m_is_finite_loss_adjusted_and_not_smaller_than_minimum_order(self):
        demand = np.array([[2.0, 5.0], [4.0, 10.0], [3.0, 8.0]])
        result = q3.compute_big_m(demand, np.array([0.0, 0.20]), minimum_order=2.5)

        self.assertTrue(np.isfinite(result).all())
        self.assertTrue((result >= 2.5).all())
        self.assertGreater(result[1], 10.0)
        self.assertLess(result[1], 20.0)


class EvaluationTests(unittest.TestCase):
    def test_evaluation_charges_order_cost_and_applies_loss_before_sales(self):
        strategy = pd.DataFrame(
            {
                "sku_code": ["A"],
                "category_name": ["花叶类"],
                "selected": [1],
                "price_yuan_per_kg": [10.0],
                "order_qty_kg": [10.0],
                "loss_rate": [0.20],
            }
        )
        sku_codes = ["A"]
        demand = np.array([[20.0], [5.0]])
        costs = np.array([[4.0], [6.0]])
        category_demand = np.array([[20.0], [5.0]])

        result = q3.evaluate_strategy(
            strategy, sku_codes, demand, costs, category_demand, ["花叶类"]
        )

        np.testing.assert_allclose(result["sales_by_scenario"].ravel(), [8.0, 5.0])
        np.testing.assert_allclose(result["profit_by_scenario"], [40.0, -10.0])
        self.assertAlmostEqual(result["expected_profit"], 15.0)
        self.assertAlmostEqual(result["service_loss_by_scenario"][0], 0.60)

    def test_lower_tail_mean_uses_worst_outcomes(self):
        self.assertAlmostEqual(q3.lower_tail_mean(np.array([10.0, -5.0, 3.0, -1.0]), 0.5), -3.0)

    def test_replenishment_band_is_symmetric_005pct(self):
        lower, upper = q3.replenishment_band(1000.0)

        self.assertAlmostEqual(lower, 999.5, places=12)
        self.assertAlmostEqual(upper, 1000.5, places=12)
        self.assertAlmostEqual(upper - lower, 1.0, places=12)

    def test_scenario_fold_summary_is_deterministic_complete_and_finite(self):
        service_loss = np.linspace(0.10, 0.30, 12)
        profit = np.array([10.0, -1.0, 4.0, 3.0, 8.0, 2.0, -2.0, 9.0, 1.0, 7.0, 6.0, 5.0])

        first = q3.summarize_scenario_folds(service_loss, profit, folds=3)
        second = q3.summarize_scenario_folds(service_loss, profit, folds=3)

        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(first["fold"].tolist(), [1, 2, 3])
        self.assertEqual(first["scenario_count"].sum(), 12)
        self.assertTrue(np.isfinite(first.select_dtypes(include=[np.number])).all().all())
        self.assertTrue(first["mean_demand_satisfaction"].between(0, 1).all())

    def test_sensitivity_variants_have_nine_unique_rows_and_one_baseline(self):
        variants = q3.build_sensitivity_variants()
        labels = [item["variant_id"] for item in variants]

        self.assertEqual(len(variants), 9)
        self.assertEqual(len(set(labels)), 9)
        self.assertEqual(labels.count("baseline"), 1)
        baseline = next(item for item in variants if item["variant_id"] == "baseline")
        self.assertEqual(baseline["risk_weight"], 0.25)
        self.assertEqual(baseline["elasticity_scale"], 1.0)
        self.assertEqual(baseline["historical_share_weight"], 0.50)
        self.assertEqual(baseline["order_cap_factor"], 1.0)

    def test_selection_jaccard_handles_overlap_and_two_empty_sets(self):
        self.assertAlmostEqual(q3.selection_jaccard({"A", "B"}, {"B", "C"}), 1.0 / 3.0)
        self.assertEqual(q3.selection_jaccard(set(), set()), 1.0)

    def test_cached_base_is_recomputed_and_stale_metrics_are_rejected(self):
        codes = [f"S{i:02d}" for i in range(33)]
        candidates = pd.DataFrame(
            {
                "sku_code": codes,
                "sku_name": codes,
                "category_name": ["花叶类"] * 33,
                "loss_rate": [0.0] * 33,
            }
        )
        grid = pd.DataFrame(
            {
                "sku_code": codes,
                "sku_name": codes,
                "category_name": ["花叶类"] * 33,
                "price_level": [1] * 33,
                "price_yuan_per_kg": [8.0] * 33,
            }
        )
        cached = candidates.copy()
        cached["selected"] = 1
        cached["price_yuan_per_kg"] = 8.0
        cached["order_qty_kg"] = 2.5
        demand = np.full((2, 33), 2.0)
        costs = np.ones((2, 33))
        category_demand = np.full((2, 1), 66.0)
        metric, _, _ = q3._strategy_metrics(
            cached, candidates, grid, demand, costs, category_demand, ["花叶类"]
        )
        frontier = pd.DataFrame(
            [
                {
                    **metric,
                    "assortment_size": 33,
                    "optimization_stage1_service_loss": 0.0,
                    "optimization_stage2_service_loss": 0.0,
                    "service_tolerance": 0.0,
                }
            ]
        )

        rebuilt = q3.reconstruct_cached_base_solution(
            candidates, cached, frontier, grid, demand, costs, category_demand,
            ["花叶类"], total_order_upper=82.5,
        )
        self.assertEqual(int(rebuilt["solved"]["strategy"]["selected"].sum()), 33)
        stale = frontier.copy()
        stale.loc[0, "expected_profit_yuan"] += 1.0
        with self.assertRaisesRegex(ValueError, "stale"):
            q3.reconstruct_cached_base_solution(
                candidates, cached, stale, grid, demand, costs, category_demand,
                ["花叶类"], total_order_upper=82.5,
            )


class LexicographicMilpTests(unittest.TestCase):
    def test_solver_prioritizes_service_and_enforces_selection_links(self):
        candidates = pd.DataFrame(
            {
                "sku_code": ["A", "B"],
                "sku_name": ["甲", "乙"],
                "category_name": ["花叶类", "花叶类"],
                "loss_rate": [0.0, 0.0],
                "big_m_kg": [12.0, 12.0],
            }
        )
        price_grid = pd.DataFrame(
            {
                "sku_code": ["A", "B"],
                "sku_name": ["甲", "乙"],
                "category_name": ["花叶类", "花叶类"],
                "price_level": [1, 1],
                "price_yuan_per_kg": [5.0, 20.0],
            }
        )
        alternative_demand = np.array([[10.0, 2.0], [8.0, 2.0]])
        category_demand = np.array([[10.0], [8.0]])
        sku_cost = np.array([[1.0, 1.0], [1.0, 1.0]])

        result = q3.solve_lexicographic_milp(
            candidates,
            price_grid,
            alternative_demand,
            category_demand,
            sku_cost,
            ["花叶类"],
            assortment_size=1,
            risk_weight=0.25,
            service_tolerance=0.0,
        )

        strategy = result["strategy"].set_index("sku_code")
        self.assertEqual(int(strategy["selected"].sum()), 1)
        self.assertEqual(int(strategy.loc["A", "selected"]), 1)
        self.assertEqual(int(strategy.loc["B", "selected"]), 0)
        self.assertGreaterEqual(strategy.loc["A", "order_qty_kg"], 2.5 - 1e-8)
        self.assertAlmostEqual(result["stage1_service_loss"], 0.0, places=8)
        self.assertLessEqual(result["stage2_service_loss"], 1e-8)
        self.assertEqual(int(result["chosen_price_rows"].shape[0]), 1)

    def test_solver_rejects_inconsistent_dimensions(self):
        candidates = pd.DataFrame(
            {
                "sku_code": ["A"],
                "sku_name": ["甲"],
                "category_name": ["花叶类"],
                "loss_rate": [0.0],
                "big_m_kg": [10.0],
            }
        )
        grid = pd.DataFrame(
            {
                "sku_code": ["A"],
                "sku_name": ["甲"],
                "category_name": ["花叶类"],
                "price_level": [1],
                "price_yuan_per_kg": [5.0],
            }
        )
        with self.assertRaisesRegex(ValueError, "dimensions"):
            q3.solve_lexicographic_milp(
                candidates,
                grid,
                np.ones((2, 2)),
                np.ones((2, 1)),
                np.ones((2, 1)),
                ["花叶类"],
                assortment_size=1,
            )

    def test_solver_respects_q2_total_replenishment_cap(self):
        candidates = pd.DataFrame(
            {
                "sku_code": ["A", "B"],
                "sku_name": ["甲", "乙"],
                "category_name": ["花叶类", "花叶类"],
                "loss_rate": [0.0, 0.0],
                "big_m_kg": [20.0, 20.0],
            }
        )
        grid = pd.DataFrame(
            {
                "sku_code": ["A", "B"],
                "sku_name": ["甲", "乙"],
                "category_name": ["花叶类", "花叶类"],
                "price_level": [1, 1],
                "price_yuan_per_kg": [8.0, 8.0],
            }
        )
        result = q3.solve_lexicographic_milp(
            candidates,
            grid,
            np.full((2, 2), 20.0),
            np.full((2, 1), 40.0),
            np.ones((2, 2)),
            ["花叶类"],
            assortment_size=2,
            total_order_upper=7.0,
            service_tolerance=0.0,
        )
        self.assertLessEqual(result["strategy"]["order_qty_kg"].sum(), 7.0 + 1e-8)
        self.assertTrue((result["strategy"]["order_qty_kg"] >= 2.5 - 1e-8).all())

    def test_solver_enforces_replenishment_floor_when_demand_is_satiated(self):
        # Demand is small (4 kg total) so service is already perfect well below
        # the cap; without a floor the profit stage trims orders to what demand
        # absorbs. A 6.0 kg floor forces total orders up to at least 6.0 kg.
        candidates = pd.DataFrame(
            {
                "sku_code": ["A", "B"],
                "sku_name": ["甲", "乙"],
                "category_name": ["花叶类", "花叶类"],
                "loss_rate": [0.0, 0.0],
                "big_m_kg": [20.0, 20.0],
            }
        )
        grid = pd.DataFrame(
            {
                "sku_code": ["A", "B"],
                "sku_name": ["甲", "乙"],
                "category_name": ["花叶类", "花叶类"],
                "price_level": [1, 1],
                "price_yuan_per_kg": [8.0, 8.0],
            }
        )
        common = dict(
            alternative_demand=np.array([[2.0, 2.0], [2.0, 2.0]]),
            category_demand=np.full((2, 1), 4.0),
            sku_cost=np.ones((2, 2)),
            categories=["花叶类"],
            assortment_size=2,
            service_tolerance=0.0,
        )
        unconstrained = q3.solve_lexicographic_milp(
            candidates, grid, total_order_upper=10.0, total_order_lower=5.0, **common
        )
        self.assertLess(
            unconstrained["strategy"]["order_qty_kg"].sum(), 6.0 - 1e-7
        )

        banded = q3.solve_lexicographic_milp(
            candidates, grid, total_order_upper=10.0, total_order_lower=6.0, **common
        )
        total = banded["strategy"]["order_qty_kg"].sum()
        self.assertGreaterEqual(total, 6.0 - 1e-7)
        self.assertLessEqual(total, 10.0 + 1e-7)
        self.assertTrue((banded["strategy"]["order_qty_kg"] >= 2.5 - 1e-8).all())

    def test_solver_rejects_inverted_replenishment_band(self):
        candidates = pd.DataFrame(
            {
                "sku_code": ["A", "B"],
                "sku_name": ["甲", "乙"],
                "category_name": ["花叶类", "花叶类"],
                "loss_rate": [0.0, 0.0],
                "big_m_kg": [10.0, 10.0],
            }
        )
        grid = pd.DataFrame(
            {
                "sku_code": ["A", "B"],
                "sku_name": ["甲", "乙"],
                "category_name": ["花叶类", "花叶类"],
                "price_level": [1, 1],
                "price_yuan_per_kg": [8.0, 8.0],
            }
        )
        with self.assertRaisesRegex(ValueError, "lower bound exceeds"):
            q3.solve_lexicographic_milp(
                candidates,
                grid,
                np.full((2, 2), 5.0),
                np.full((2, 1), 10.0),
                np.ones((2, 2)),
                ["花叶类"],
                assortment_size=2,
                total_order_upper=5.0,
                total_order_lower=6.0,
            )

    def test_sensitivity_variant_is_resolved_with_configured_risk_and_cap(self):
        candidates = pd.DataFrame(
            {
                "sku_code": ["A", "B"],
                "sku_name": ["甲", "乙"],
                "category_name": ["花叶类", "花叶类"],
                "loss_rate": [0.0, 0.0],
                "big_m_kg": [10.0, 10.0],
            }
        )
        grid = pd.DataFrame(
            {
                "sku_code": ["A", "B"],
                "sku_name": ["甲", "乙"],
                "category_name": ["花叶类", "花叶类"],
                "price_level": [1, 1],
                "price_yuan_per_kg": [8.0, 9.0],
            }
        )
        variant = {
            "variant_id": "risk_weight_0.50",
            "parameter_group": "risk_weight",
            "parameter_value": 0.50,
            "risk_weight": 0.50,
            "elasticity_scale": 1.0,
            "historical_share_weight": 0.50,
            "order_cap_factor": 1.0,
        }

        result = q3.solve_sensitivity_variant(
            variant,
            candidates,
            grid,
            np.array([[8.0, 5.0], [7.0, 4.0]]),
            np.array([[13.0], [11.0]]),
            np.ones((2, 2)),
            ["花叶类"],
            np.array([0, 1]),
            assortment_size=2,
            total_order_upper=7.0,
            baseline_selected={"A", "B"},
        )

        self.assertEqual(result["row"]["risk_weight"], 0.50)
        self.assertEqual(result["row"]["selected_sku_count"], 2)
        self.assertEqual(result["row"]["assortment_size"], 2)
        self.assertLessEqual(result["row"]["total_order_qty_kg"], 7.0 + 1e-8)
        self.assertEqual(result["row"]["selection_jaccard_vs_baseline"], 1.0)

    def test_solver_can_reuse_identical_stage1_without_changing_stage2_result(self):
        candidates = pd.DataFrame(
            {
                "sku_code": ["A", "B"],
                "sku_name": ["甲", "乙"],
                "category_name": ["花叶类", "花叶类"],
                "loss_rate": [0.0, 0.0],
                "big_m_kg": [10.0, 10.0],
            }
        )
        grid = pd.DataFrame(
            {
                "sku_code": ["A", "B"],
                "sku_name": ["甲", "乙"],
                "category_name": ["花叶类", "花叶类"],
                "price_level": [1, 1],
                "price_yuan_per_kg": [8.0, 9.0],
            }
        )
        demand = np.array([[8.0, 5.0], [7.0, 4.0]])
        category_demand = np.array([[13.0], [11.0]])
        costs = np.ones((2, 2))
        original = q3.solve_lexicographic_milp(
            candidates, grid, demand, category_demand, costs, ["花叶类"],
            assortment_size=2, total_order_upper=7.0,
        )
        reused = q3.solve_lexicographic_milp(
            candidates, grid, demand, category_demand, costs, ["花叶类"],
            assortment_size=2, total_order_upper=7.0,
            stage1_reference={
                "service_loss": original["stage1_service_loss"],
                "service_tolerance": original["service_tolerance"],
            },
        )
        self.assertEqual(reused["stage1_seconds"], 0.0)
        self.assertAlmostEqual(reused["stage2_service_loss"], original["stage2_service_loss"], places=8)
        self.assertAlmostEqual(reused["stage2_objective"], original["stage2_objective"], places=8)


if __name__ == "__main__":
    unittest.main()
