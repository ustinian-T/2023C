#!/usr/bin/env python3
"""Q1 two-part distribution analysis: zero-inflation + positive-sales distribution fitting.

Compares Normal, Lognormal, Gamma, Weibull for positive daily sales.
Uses AIC for relative selection, KS test for absolute fit quality,
and marks KDE fallback when no parametric distribution passes KS at 5%.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


def fit_candidate_distributions(
    positive: np.ndarray,
) -> list[dict[str, Any]]:
    """Fit candidate parametric distributions to positive values.

    Parameters
    ----------
    positive : np.ndarray
        Strictly positive sales values (zeroes already removed).

    Returns
    -------
    list of dict with keys: distribution, params, log_likelihood, aic,
    ks_statistic, ks_p_value, n_positive
    """
    positive = np.asarray(positive, dtype=float)
    positive = positive[np.isfinite(positive) & (positive > 0)]
    if positive.size < 30:
        return []

    candidates: list[tuple[str, Any, tuple, int]] = [
        ("Normal", stats.norm, stats.norm.fit(positive), 2),
        ("Lognormal", stats.lognorm, stats.lognorm.fit(positive, floc=0), 2),
        ("Gamma", stats.gamma, stats.gamma.fit(positive, floc=0), 2),
        ("Weibull", stats.weibull_min, stats.weibull_min.fit(positive, floc=0), 2),
    ]

    rows: list[dict[str, Any]] = []
    for name, dist, params, k in candidates:
        logpdf = dist.logpdf(positive, *params)
        finite = np.isfinite(logpdf)
        log_likelihood = float(logpdf[finite].sum()) if finite.any() else -np.inf
        aic = float(2 * k - 2 * log_likelihood) if np.isfinite(log_likelihood) else np.inf
        ks_stat, ks_p = stats.kstest(positive, dist.cdf, args=params)

        if name == "Normal":
            p1, p2, p3 = float(params[0]), float(params[1]), np.nan
        else:
            # shape, loc(=0), scale
            p1, p2, p3 = float(params[0]), float(params[-1]), float(params[1])

        rows.append({
            "distribution": name,
            "n_positive": int(positive.size),
            "parameter_1": p1,
            "parameter_2": p2,
            "parameter_3": p3,
            "log_likelihood": log_likelihood,
            "aic": aic,
            "ks_statistic": float(ks_stat),
            "ks_p_value": float(ks_p),
        })
    return rows


def distribution_analysis(
    series_map: dict[tuple[str, str, str], pd.Series],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two-part distribution analysis for a collection of entities.

    Parameters
    ----------
    series_map : dict
        Keys are (level, entity_code, entity_name) tuples.
        Values are pd.Series of daily sales quantities.

    Returns
    -------
    candidates : pd.DataFrame
        All candidate distribution fits (long format).
    summary : pd.DataFrame
        One row per entity with zero share, best distribution, and fit conclusion.
    """
    candidate_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []

    for (level, code, name), series in series_map.items():
        values = series.to_numpy(dtype=float)
        base = {
            "level": level,
            "item_code": str(code),
            "item_name": name,
            "n_days": int(values.size),
            "zero_share": float(np.mean(values <= 0)),
            "mean_qty_kg": float(np.mean(values)),
            "median_qty_kg": float(np.median(values)),
            "std_qty_kg": float(np.std(values, ddof=0)),
            "skewness": float(stats.skew(values[np.isfinite(values)]) if np.any(np.isfinite(values)) else np.nan),
        }
        positive = values[np.isfinite(values) & (values > 0)]
        if positive.size < 30:
            summary_rows.append({
                **base,
                "best_distribution": "insufficient",
                "best_aic": np.nan,
                "delta_aic_second": np.nan,
                "best_ks_p_value": np.nan,
                "fit_conclusion": "insufficient",
            })
            continue

        rows = fit_candidate_distributions(positive)
        if not rows:
            summary_rows.append({
                **base,
                "best_distribution": "insufficient",
                "best_aic": np.nan,
                "delta_aic_second": np.nan,
                "best_ks_p_value": np.nan,
                "fit_conclusion": "insufficient",
            })
            continue

        for row in rows:
            candidate_rows.append({**base, **row})

        ranked = sorted(rows, key=lambda r: r["aic"])
        best = ranked[0]
        delta = ranked[1]["aic"] - best["aic"] if len(ranked) > 1 else np.nan
        summary_rows.append({
            **base,
            "best_distribution": best["distribution"],
            "best_aic": best["aic"],
            "delta_aic_second": delta,
            "best_ks_p_value": best["ks_p_value"],
            "fit_conclusion": (
                "parametric_accepted" if best["ks_p_value"] >= 0.05
                else "kde_fallback"
            ),
        })

    return pd.DataFrame(candidate_rows), pd.DataFrame(summary_rows)


def zero_inflated_summary(series_map: dict[tuple[str, str, str], pd.Series]) -> pd.DataFrame:
    """Quick zero-inflation summary across entities.

    Returns
    -------
    pd.DataFrame with zero proportion, positive mean, positive median, positive std.
    """
    rows = []
    for (level, code, name), series in series_map.items():
        values = series.to_numpy(dtype=float)
        positive = values[values > 0]
        rows.append({
            "level": level,
            "item_code": str(code),
            "item_name": name,
            "n_days": len(values),
            "zero_proportion": float(np.mean(values <= 0)),
            "positive_mean": float(np.mean(positive)) if len(positive) > 0 else np.nan,
            "positive_median": float(np.median(positive)) if len(positive) > 0 else np.nan,
            "positive_std": float(np.std(positive, ddof=0)) if len(positive) > 0 else np.nan,
        })
    return pd.DataFrame(rows)
