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
        # Two anti-correlated daily outcomes: every weekly outcome is 100,
        # although the sum of the two separate daily lower tails would be 0.
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


if __name__ == "__main__":
    unittest.main()
