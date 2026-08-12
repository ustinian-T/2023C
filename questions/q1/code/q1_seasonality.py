#!/usr/bin/env python3
"""Q1 seasonality: monthly/seasonal profiles, seasonal indices, and clustering features.

Meteorological seasons: Spring (3-5), Summer (6-8), Autumn (9-11), Winter (12-2).
Sales years run July–June to keep winter seasons intact.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Season definitions
# ---------------------------------------------------------------------------

MONTH_TO_SEASON: dict[int, str] = {
    1: "冬季", 2: "冬季",
    3: "春季", 4: "春季", 5: "春季",
    6: "夏季", 7: "夏季", 8: "夏季",
    9: "秋季", 10: "秋季", 11: "秋季",
    12: "冬季",
}

SEASON_ORDER = ["春季", "夏季", "秋季", "冬季"]
MONTH_ORDER = list(range(1, 13))

# Days in each month (non-leap year)
DAYS_IN_MONTH = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
                 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}


def _sales_year(date: pd.Timestamp) -> int:
    """Return the sales year for a date (July–June convention)."""
    if date.month >= 7:
        return date.year
    else:
        return date.year - 1


def compute_monthly_profile(
    df: pd.DataFrame,
    entity_col: str,
    date_col: str = "date",
    qty_col: str = "gross_sales_qty",
) -> pd.DataFrame:
    """Compute 12-month profile for each entity.

    For each entity and month (1–12), computes across all available sales years:
      - avg_daily_sales: mean daily sales (kg/day), normalized by month length
      - sales_proportion: month's total / annual total (averaged over sales years)
      - active_rate: fraction of days with positive sales
      - seasonal_index: month's avg daily sales / overall avg daily sales

    Within each sales year, daily sales are summed per month then divided by
    the number of days in that month.  The resulting monthly rates are averaged
    across sales years so that large-volume years do not dominate.

    Returns
    -------
    pd.DataFrame with columns:
        entity, month, avg_daily_sales, sales_proportion, active_rate, seasonal_index
    """
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df["_month"] = df[date_col].dt.month
    df["_year"] = df[date_col].dt.year
    df["_sales_year"] = df[date_col].apply(_sales_year)

    # Daily sales already; sum by entity, sales_year, month
    monthly_totals = (
        df.groupby([entity_col, "_sales_year", "_month"], as_index=False)[qty_col]
        .sum()
    )

    # Normalize by days in month → avg daily sales for that entity-year-month
    monthly_totals["_days"] = monthly_totals["_month"].map(DAYS_IN_MONTH)
    monthly_totals["avg_daily_sales"] = monthly_totals[qty_col] / monthly_totals["_days"]

    # Annual totals per entity-sales_year (for proportion)
    annual_totals = (
        monthly_totals.groupby([entity_col, "_sales_year"])[qty_col]
        .sum()
        .reset_index(name="_annual_qty")
    )
    monthly_totals = monthly_totals.merge(
        annual_totals, on=[entity_col, "_sales_year"], how="left"
    )
    monthly_totals["sales_proportion"] = monthly_totals[qty_col] / monthly_totals["_annual_qty"]

    # Average across sales years for each entity-month
    profile = (
        monthly_totals.groupby([entity_col, "_month"], as_index=False)
        .agg(
            avg_daily_sales=("avg_daily_sales", "mean"),
            sales_proportion=("sales_proportion", "mean"),
        )
        .rename(columns={"_month": "month"})
    )

    # Active rate: fraction of entity-day records with positive sales
    daily_positive = (
        df.groupby([entity_col, "_sales_year", "_month"], as_index=False)
        .agg(
            active_days=("gross_sales_qty", lambda x: int((x > 0).sum())),
            total_days=("gross_sales_qty", "size"),
        )
    )
    daily_positive["active_rate"] = daily_positive["active_days"] / daily_positive["total_days"]
    active_profile = (
        daily_positive.groupby([entity_col, "_month"], as_index=False)["active_rate"]
        .mean()
        .rename(columns={"_month": "month"})
    )

    profile = profile.merge(active_profile, on=[entity_col, "month"], how="left")

    # Ensure all 12 months present for each entity (fill missing with 0)
    all_months = pd.DataFrame({"month": MONTH_ORDER})
    entities = profile[entity_col].unique()
    full_index = pd.MultiIndex.from_product(
        [entities, MONTH_ORDER], names=[entity_col, "month"]
    )
    profile = profile.set_index([entity_col, "month"]).reindex(full_index).reset_index()
    profile[["avg_daily_sales", "sales_proportion", "active_rate"]] = (
        profile[["avg_daily_sales", "sales_proportion", "active_rate"]].fillna(0.0)
    )

    # Seasonal index: month's avg daily sales / overall avg daily sales per entity
    entity_avg = profile.groupby(entity_col)["avg_daily_sales"].transform("mean")
    # Avoid division by zero
    entity_avg = entity_avg.replace(0.0, np.nan)
    profile["seasonal_index"] = profile["avg_daily_sales"] / entity_avg
    profile["seasonal_index"] = profile["seasonal_index"].fillna(0.0)

    # Sort
    profile = profile.sort_values([entity_col, "month"]).reset_index(drop=True)
    profile["month"] = profile["month"].astype(int)

    return profile


def compute_seasonal_profile(monthly: pd.DataFrame, entity_col: str) -> pd.DataFrame:
    """Aggregate monthly profile to four meteorological seasons.

    Parameters
    ----------
    monthly : pd.DataFrame
        Output from compute_monthly_profile.
    entity_col : str
        Entity column name.

    Returns
    -------
    pd.DataFrame with columns:
        entity, season, avg_daily_sales, sales_proportion, active_rate, seasonal_index
    """
    monthly = monthly.copy()
    monthly["season"] = monthly["month"].map(MONTH_TO_SEASON)

    seasonal = (
        monthly.groupby([entity_col, "season"], as_index=False)
        .agg(
            avg_daily_sales=("avg_daily_sales", "mean"),
            sales_proportion=("sales_proportion", "sum"),
            active_rate=("active_rate", "mean"),
            seasonal_index=("seasonal_index", "mean"),
        )
    )

    # Set categorical order
    seasonal["season"] = pd.Categorical(
        seasonal["season"], categories=SEASON_ORDER, ordered=True
    )
    seasonal = seasonal.sort_values([entity_col, "season"]).reset_index(drop=True)

    return seasonal


def compute_peak_metrics(monthly: pd.DataFrame, entity_col: str) -> pd.DataFrame:
    """Compute peak month, peak season, and concentration metrics per entity.

    Returns
    -------
    pd.DataFrame with columns:
        entity, peak_month, peak_season, peak_month_index,
        season_concentration (max season proportion / min season proportion)
    """
    peak_month_idx = monthly.loc[
        monthly.groupby(entity_col)["seasonal_index"].idxmax()
    ][[entity_col, "month", "seasonal_index"]].rename(
        columns={"month": "peak_month", "seasonal_index": "peak_month_index"}
    )
    peak_month_idx["peak_season"] = peak_month_idx["peak_month"].map(MONTH_TO_SEASON)

    # Concentration: max/min season proportion ratio
    seasonal = compute_seasonal_profile(monthly, entity_col)
    conc = (
        seasonal.groupby(entity_col)["sales_proportion"]
        .agg(lambda x: x.max() / (x.min() + 1e-12))
        .reset_index(name="season_concentration")
    )

    result = peak_month_idx.merge(conc, on=entity_col, how="left")
    return result


def build_seasonal_index_table(
    monthly: pd.DataFrame, entity_col: str, entity_name_col: str | None = None
) -> pd.DataFrame:
    """Pivot monthly profile to a wide table of 12-month seasonal indices.

    Returns
    -------
    pd.DataFrame with columns: entity [, entity_name], month_1 ... month_12
    """
    wide = monthly.pivot(
        index=entity_col, columns="month", values="seasonal_index"
    ).reset_index()
    wide.columns = [str(c) for c in wide.columns]
    wide.columns = [
        f"month_{c}" if c.isdigit() else c for c in wide.columns
    ]

    if entity_name_col and entity_name_col in monthly.columns:
        names = monthly[[entity_col, entity_name_col]].drop_duplicates()
        wide = wide.merge(names, on=entity_col, how="left")

    return wide


def build_clustering_features(monthly: pd.DataFrame, entity_col: str) -> tuple[pd.DataFrame, np.ndarray]:
    """Build 24-dimensional standardized features for K-means clustering.

    Features: 12 monthly sales proportions + 12 monthly active rates,
    standardized to zero mean and unit variance across entities.

    Returns
    -------
    feature_df : pd.DataFrame
        Entity-indexed DataFrame of 24 raw features.
    feature_matrix : np.ndarray
        Standardized feature matrix (n_entities × 24).
    """
    # Pivot sales proportions
    prop = monthly.pivot(index=entity_col, columns="month", values="sales_proportion")
    prop.columns = [f"prop_month_{int(c)}" for c in prop.columns]

    # Pivot active rates
    active = monthly.pivot(index=entity_col, columns="month", values="active_rate")
    active.columns = [f"active_month_{int(c)}" for c in active.columns]

    features = pd.concat([prop, active], axis=1)
    # Ensure all 24 columns
    expected = [f"prop_month_{m}" for m in MONTH_ORDER] + [f"active_month_{m}" for m in MONTH_ORDER]
    for col in expected:
        if col not in features.columns:
            features[col] = 0.0
    features = features[expected]

    # Standardize
    feature_matrix = (features.to_numpy(dtype=float) - features.mean().to_numpy()) / features.std(ddof=0).to_numpy()
    # Handle constant columns (unlikely but safe)
    feature_matrix = np.nan_to_num(feature_matrix, nan=0.0)

    return features, feature_matrix


def compute_entity_daily_sales(
    df: pd.DataFrame,
    entity_col: str,
    date_col: str = "date",
    qty_col: str = "gross_sales_qty",
) -> pd.DataFrame:
    """Build entity × date pivot table of daily sales quantities.

    Returns
    -------
    pd.DataFrame with date index and entity columns.
    """
    pivot = df.pivot_table(
        index=date_col, columns=entity_col, values=qty_col,
        aggfunc="sum", fill_value=0.0,
    )
    pivot.index = pd.to_datetime(pivot.index)
    return pivot.sort_index()


def get_entities_in_month(
    daily: pd.DataFrame, month: int
) -> set[str]:
    """Return set of entities that have any sales record in a given month."""
    mask = daily.index.month == month
    cols = daily.columns[(daily.loc[mask] > 0).any(axis=0)]
    return set(cols.tolist())
