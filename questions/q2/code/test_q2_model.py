"""Unit tests for the weekly risk and operational constraints in Question 2."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from q2_model import (
    apply_reference_penalty,
    build_weekly_decision_bounds,
    count_category_upper_bound_hits,
    goodwill_penalty_terms,
    maximum_markup_change_violation,
    select_constrained_elasticity,
    weekly_risk_statistics,
)


class WeeklyRiskStatisticsTests(unittest.TestCase):
    def test_tail_is_computed_after_aggregating_all_seven_days(self) -> None:
        """Catches the bug that adds daily tails instead of tailing weekly profit."""
        profit_by_day = np.array([[100.0, 0.0], [0.0, 100.0]])

        result = weekly_risk_statistics(profit_by_day, gamma=1.0, tail_probability=0.5)

        self.assertAlmostEqual(result["weekly_expected_profit"], 100.0)
        self.assertAlmostEqual(result["weekly_lower_tail_mean"], 100.0)
        self.assertAlmostEqual(result["risk_adjusted_objective"], 100.0)


class MarkupSmoothingTests(unittest.TestCase):
    def test_reports_first_day_and_interday_change_violations(self) -> None:
        """Catches missing enforcement of the historical daily markup-change cap."""
        markup = np.array([[0.60, 0.20], [0.75, 0.31], [0.70, 0.45]])
        reference = np.array([0.50, 0.20])
        delta = np.array([0.10, 0.10])

        violation = maximum_markup_change_violation(markup, reference, delta)

        self.assertAlmostEqual(violation, 0.05)

    def test_weekly_bounds_tighten_only_the_first_day_markup(self) -> None:
        """Catches scalar shadowing or incorrect repetition in weekly bounds."""
        bounds = build_weekly_decision_bounds(
            categories=["A", "B"],
            markup_global={"A": (0.10, 0.90), "B": (0.15, 0.80)},
            reference=np.array([0.50, 0.40]),
            delta=np.array([0.10, 0.20]),
            q_upper=np.array([100.0, 200.0]),
            n_days=3,
        )

        np.testing.assert_allclose(bounds[:2], [(0.40, 0.60), (0.20, 0.60)])
        np.testing.assert_allclose(bounds[2:6], [(0.10, 0.90), (0.15, 0.80)] * 2)
        np.testing.assert_allclose(bounds[6:], [(0.0, 100.0), (0.0, 200.0)] * 3)


class GoodwillPenaltyTests(unittest.TestCase):
    def test_margin_inactive_branch_has_zero_penalty_and_zero_gradient(self) -> None:
        """Catches differentiating max(0, price-cost) on its inactive branch."""
        penalty, markup_grad, q_grad = goodwill_penalty_terms(
            price=np.array([[[5.0]]]),
            scenario_cost=np.array([[[6.0]]]),
            demand=np.array([[[12.0]]]),
            available=np.array([[[10.0]]]),
            demand_markup_derivative=np.array([[[-0.8]]]),
            price_markup_derivative=np.array([[[4.0]]]),
            saleable_fraction=np.array([0.9]),
            ratio=0.1,
        )

        np.testing.assert_allclose(penalty, 0.0)
        np.testing.assert_allclose(markup_grad, 0.0)
        np.testing.assert_allclose(q_grad, 0.0)

    def test_active_branch_derivatives_match_hand_calculation(self) -> None:
        """Catches sign errors in goodwill-cost derivatives used by SLSQP."""
        penalty, markup_grad, q_grad = goodwill_penalty_terms(
            price=np.array([[[10.0]]]),
            scenario_cost=np.array([[[6.0]]]),
            demand=np.array([[[12.0]]]),
            available=np.array([[[10.0]]]),
            demand_markup_derivative=np.array([[[-1.5]]]),
            price_markup_derivative=np.array([[[5.0]]]),
            saleable_fraction=np.array([0.9]),
            ratio=0.1,
        )

        np.testing.assert_allclose(penalty, 0.8)
        np.testing.assert_allclose(markup_grad, 0.4)
        np.testing.assert_allclose(q_grad, -0.36)

    def test_positive_penalty_when_demand_exceeds_available(self) -> None:
        """Goodwill penalty should be strictly positive when stockout occurs."""
        price = np.array([10.0])
        cost = np.array([6.0])
        demand = np.array([120.0])
        available = np.array([100.0])
        q_val = np.array([105.0])
        goodwill_ratio = 0.30

        penalty, _, _ = goodwill_penalty_terms(
            price[None, None, :], cost[None, None, :], demand[None, None, :],
            available[None, None, :], np.zeros((1, 1, 1)), np.ones((1, 1, 1)),
            np.array([1.0]), goodwill_ratio,
        )

        self.assertGreater(float(penalty[0, 0, 0]), 0.0)
        expected_penalty = 0.30 * (10.0 - 6.0) * 20.0
        self.assertAlmostEqual(float(penalty[0, 0, 0]), expected_penalty)

    def test_zero_penalty_when_available_exceeds_demand(self) -> None:
        """No goodwill penalty when stock is sufficient."""
        price = np.array([10.0])
        cost = np.array([6.0])
        demand = np.array([80.0])
        available = np.array([100.0])
        goodwill_ratio = 0.30

        penalty, _, _ = goodwill_penalty_terms(
            price[None, None, :], cost[None, None, :], demand[None, None, :],
            available[None, None, :], np.zeros((1, 1, 1)), np.ones((1, 1, 1)),
            np.array([1.0]), goodwill_ratio,
        )

        self.assertAlmostEqual(float(penalty[0, 0, 0]), 0.0)

    def test_higher_goodwill_ratio_increases_replenishment_incentive(self) -> None:
        """With higher goodwill cost, the expected marginal benefit of ordering more increases."""
        price = 10.0
        cost = 6.0
        demand = np.array([120.0, 80.0])
        available = 100.0

        def expected_penalty(ratio: float) -> float:
            penalty, _, _ = goodwill_penalty_terms(
                np.full((2, 1, 1), price), np.full((2, 1, 1), cost),
                demand[:, None, None], np.full((2, 1, 1), available),
                np.zeros((2, 1, 1)), np.ones((2, 1, 1)), np.array([1.0]), ratio,
            )
            return float(penalty.mean())

        p_low = expected_penalty(0.15)
        p_high = expected_penalty(0.50)
        self.assertGreater(p_high, p_low)


class ReferencePricePenaltyTests(unittest.TestCase):
    def test_adjustment_keeps_operating_profit_separate(self) -> None:
        """Catches reporting the regularizer as if it were operating profit."""
        operating = np.array([[100.0, 120.0], [80.0, 140.0]])
        markup = np.array([[0.6], [0.7]])
        reference = np.array([0.5])

        adjusted, penalty = apply_reference_penalty(operating, markup, reference, weight=10.0)

        np.testing.assert_allclose(operating, [[100.0, 120.0], [80.0, 140.0]])
        self.assertAlmostEqual(penalty, 0.5)
        np.testing.assert_allclose(adjusted.sum(axis=1), operating.sum(axis=1) - 0.5)

    def test_penalty_grows_with_deviation(self) -> None:
        """Reference price penalty is quadratic in markup deviation."""
        markup = np.array([0.70, 0.90])
        ref = np.array([0.50, 0.50])
        weight = 0.02

        _, penalty_small = apply_reference_penalty(
            np.zeros((1, 1)), np.array([[0.55, 0.55]]), ref, weight
        )
        _, penalty_large = apply_reference_penalty(
            np.zeros((1, 1)), markup[None, :], ref, weight
        )

        self.assertGreater(penalty_large, penalty_small)

    def test_zero_penalty_at_reference(self) -> None:
        """Zero penalty when markup equals reference."""
        markup = np.array([0.50, 0.60])
        ref = np.array([0.50, 0.60])
        weight = 0.02

        _, penalty = apply_reference_penalty(
            np.zeros((1, 1)), markup[None, :], ref, weight
        )
        self.assertAlmostEqual(penalty, 0.0)


class ConservativeElasticityTests(unittest.TestCase):
    def test_nonnegative_raw_estimate_uses_data_driven_pooled_fallback(self) -> None:
        """Catches an arbitrary hard-coded elasticity masquerading as IV estimation."""
        selected, adjusted = select_constrained_elasticity(
            raw=0.27,
            shrunk=0.11,
            pooled=-0.245,
            bounds=(-3.0, -0.05),
        )

        self.assertTrue(adjusted)
        self.assertAlmostEqual(selected, -0.245)

class SensitivitySummaryTests(unittest.TestCase):
    def test_upper_bound_hits_are_counted_against_each_category_bound(self) -> None:
        """Catches comparing every category with the single global maximum markup."""
        strategy = pd.DataFrame({
            "category_name": ["A", "A", "B", "B"],
            "markup_rate": [0.70, 0.65, 1.20, 1.10],
        })
        upper = {"A": 0.70, "B": 1.20}

        self.assertEqual(count_category_upper_bound_hits(strategy, upper), 2)


if __name__ == "__main__":
    unittest.main()
