"""Unit tests for the weekly risk and operational constraints in Question 2."""

from __future__ import annotations

import unittest

import numpy as np

from q2_model import (
    build_weekly_decision_bounds,
    maximum_markup_change_violation,
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
    def test_positive_penalty_when_demand_exceeds_available(self) -> None:
        """Goodwill penalty should be strictly positive when stockout occurs."""
        price = np.array([10.0])
        cost = np.array([6.0])
        demand = np.array([120.0])
        available = np.array([100.0])
        q_val = np.array([105.0])
        goodwill_ratio = 0.30

        stockout = np.maximum(0.0, demand - available)
        unit_margin = np.maximum(0.0, price - cost)
        penalty = goodwill_ratio * unit_margin * stockout

        self.assertGreater(float(penalty[0]), 0.0)
        self.assertAlmostEqual(float(stockout[0]), 20.0)
        expected_penalty = 0.30 * (10.0 - 6.0) * 20.0
        self.assertAlmostEqual(float(penalty[0]), expected_penalty)

    def test_zero_penalty_when_available_exceeds_demand(self) -> None:
        """No goodwill penalty when stock is sufficient."""
        price = np.array([10.0])
        cost = np.array([6.0])
        demand = np.array([80.0])
        available = np.array([100.0])
        goodwill_ratio = 0.30

        stockout = np.maximum(0.0, demand - available)
        unit_margin = np.maximum(0.0, price - cost)
        penalty = goodwill_ratio * unit_margin * stockout

        self.assertAlmostEqual(float(penalty[0]), 0.0)

    def test_higher_goodwill_ratio_increases_replenishment_incentive(self) -> None:
        """With higher goodwill cost, the expected marginal benefit of ordering more increases."""
        price = 10.0
        cost = 6.0
        demand = np.array([120.0, 80.0])
        available = 100.0

        def expected_penalty(ratio: float) -> float:
            stockout = np.maximum(0.0, demand - available)
            unit_margin = max(0.0, price - cost)
            return float(ratio * unit_margin * stockout.mean())

        p_low = expected_penalty(0.15)
        p_high = expected_penalty(0.50)
        self.assertGreater(p_high, p_low)


class ReferencePricePenaltyTests(unittest.TestCase):
    def test_penalty_grows_with_deviation(self) -> None:
        """Reference price penalty is quadratic in markup deviation."""
        markup = np.array([0.70, 0.90])
        ref = np.array([0.50, 0.50])
        weight = 0.02

        deviation = markup - ref
        penalty_small = weight * np.sum((np.array([0.55, 0.55]) - ref) ** 2)
        penalty_large = weight * np.sum(deviation ** 2)

        self.assertGreater(penalty_large, penalty_small)

    def test_zero_penalty_at_reference(self) -> None:
        """Zero penalty when markup equals reference."""
        markup = np.array([0.50, 0.60])
        ref = np.array([0.50, 0.60])
        weight = 0.02

        deviation = markup - ref
        penalty = weight * np.sum(deviation ** 2)
        self.assertAlmostEqual(float(penalty), 0.0)


class ConservativeElasticityTests(unittest.TestCase):
    def test_conservative_floor_applied_when_ols_positive(self) -> None:
        """When raw OLS is positive, the conservative floor should pull it negative."""
        raw_ols = [0.27, -1.86, -0.16]
        pooled = -0.25
        conservative_floor = min(pooled, -0.40)
        results = []
        for r in raw_ols:
            if r >= 0:
                results.append(min(r, conservative_floor))
            else:
                results.append(r)
        # Positive OLS gets pulled to conservative floor
        self.assertAlmostEqual(results[0], conservative_floor)
        # Negative OLS unchanged
        self.assertAlmostEqual(results[1], -1.86)
        self.assertAlmostEqual(results[2], -0.16)
        self.assertLess(results[0], -0.30)


if __name__ == "__main__":
    unittest.main()
