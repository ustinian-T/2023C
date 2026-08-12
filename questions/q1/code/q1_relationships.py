#!/usr/bin/env python3
"""Q1 relationship analysis: four complementary indicators across four analysis levels.

Indicators:
  1. Seasonal index correlation (Pearson on 12-month seasonal indices)
  2. Seasonal sales correlation (Spearman on log1p-detrended daily sales, per season)
  3. Sales share correlation (Spearman on daily share of total, per season)
  4. Active-day Jaccard overlap

Analysis levels:
  A. Six problem-defined categories (15 pairs, full matrix)
  B. Within each category (representative SKU pairs)
  C. Between five seasonal clusters (aggregated sales)
  D. Within each cluster (all SKU pairs, representative for paper)

Confidence: 7-day block bootstrap 95% CI + Benjamini-Hochberg correction.
All relationships retained; |rho|>=0.30 with CI not crossing 0 is highlighted.
"""

from __future__ import annotations

import math
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from q1_seasonality import (
    MONTH_TO_SEASON,
    SEASON_ORDER,
)

# ---------------------------------------------------------------------------
# Utility: block bootstrap
# ---------------------------------------------------------------------------


def _block_bootstrap_ci(
    x: np.ndarray,
    y: np.ndarray,
    corr_func,
    block_length: int = 7,
    reps: int = 500,
    ci: float = 0.95,
    seed: int = 20230907,
) -> dict[str, float]:
    """Compute block bootstrap confidence interval for a correlation function.

    Returns dict with keys: estimate, ci_lower, ci_upper, n_valid_blocks.
    """
    n = len(x)
    if n < block_length * 2:
        est = corr_func(x, y)
        return {"estimate": est, "ci_lower": est, "ci_upper": est, "n_valid_blocks": n}

    rng = np.random.default_rng(seed)
    estimates = []
    n_blocks = int(math.ceil(n / block_length))

    for _ in range(reps):
        starts = rng.integers(0, n - block_length + 1, size=n_blocks)
        indices = np.concatenate([np.arange(s, s + block_length) for s in starts])[:n]
        try:
            est = corr_func(x[indices], y[indices])
            if np.isfinite(est):
                estimates.append(est)
        except Exception:
            continue

    if len(estimates) < 50:
        alpha = 1 - ci
        est = corr_func(x, y)
        return {"estimate": est, "ci_lower": est, "ci_upper": est, "n_valid_blocks": len(estimates)}

    estimates = np.array(estimates)
    alpha = 1 - ci
    est = corr_func(x, y)
    return {
        "estimate": float(est),
        "ci_lower": float(np.percentile(estimates, 100 * alpha / 2)),
        "ci_upper": float(np.percentile(estimates, 100 * (1 - alpha / 2))),
        "n_valid_blocks": len(estimates),
    }


# ---------------------------------------------------------------------------
# Indicator 1: seasonal index correlation
# ---------------------------------------------------------------------------


def seasonal_index_correlation(
    monthly_profiles: dict[str, np.ndarray],
) -> dict[tuple[str, str], float]:
    """Pearson correlation of 12-month seasonal index vectors between entity pairs.

    Parameters
    ----------
    monthly_profiles : dict
        entity_name → 12-element array of seasonal indices.

    Returns
    -------
    dict: (entity_a, entity_b) → pearson_r
    """
    entities = sorted(monthly_profiles.keys())
    result = {}
    for a, b in combinations(entities, 2):
        x = monthly_profiles[a]
        y = monthly_profiles[b]
        r, _ = stats.pearsonr(x, y)
        result[(a, b)] = float(r) if np.isfinite(r) else 0.0
    return result


# ---------------------------------------------------------------------------
# Indicator 2: seasonal sales correlation (detrended within year-month)
# ---------------------------------------------------------------------------


def _detrend_log_sales(daily: pd.DataFrame) -> pd.DataFrame:
    """Remove year-month mean from log1p sales for each entity column."""
    result = daily.copy()
    result.index = pd.to_datetime(result.index)

    for col in result.columns:
        series = result[col].copy()
        series[series < 0] = 0.0
        log_series = np.log1p(series)
        # Group by year-month and subtract the mean
        ym = pd.Series(
            result.index.to_period("M"), index=result.index, dtype="period[M]"
        )
        ym_mean = log_series.groupby(ym).transform("mean")
        result[col] = log_series - ym_mean

    return result


def seasonal_sales_correlation(
    daily: pd.DataFrame,
    season: str | None = None,
    use_bootstrap: bool = True,
    bootstrap_reps: int = 200,
    seed: int = 20230907,
) -> pd.DataFrame:
    """Spearman correlation of detrended log1p daily sales, optionally by season.

    Parameters
    ----------
    daily : pd.DataFrame
        Entity × date pivot of daily sales quantities.
    season : str or None
        If provided, filter to dates in that season. None for all dates.
    use_bootstrap : bool
        If True, compute bootstrap 95% CI.

    Returns
    -------
    pd.DataFrame with columns:
        source, target, season, spearman_r, ci_lower, ci_upper, n_pairs
    """
    detrended = _detrend_log_sales(daily)

    if season:
        months = [m for m, s in MONTH_TO_SEASON.items() if s == season]
        detrended = detrended[detrended.index.month.isin(months)]

    if detrended.empty or detrended.shape[1] < 2:
        return pd.DataFrame(
            columns=["source", "target", "season", "spearman_r", "ci_lower", "ci_upper", "n_pairs"]
        )

    columns = list(detrended.columns)
    rows = []

    for i, j in combinations(range(len(columns)), 2):
        x = detrended.iloc[:, i].to_numpy(dtype=float)
        y = detrended.iloc[:, j].to_numpy(dtype=float)
        mask = np.isfinite(x) & np.isfinite(y)
        x, y = x[mask], y[mask]
        if len(x) < 30:
            continue

        def spearman_func(a, b):
            r, _ = stats.spearmanr(a, b)
            return r if np.isfinite(r) else 0.0

        r, p = stats.spearmanr(x, y)

        ci = {"estimate": float(r), "ci_lower": float(r), "ci_upper": float(r), "n_valid_blocks": 0}
        if use_bootstrap and len(x) >= 14:
            ci = _block_bootstrap_ci(x, y, spearman_func, block_length=7, reps=bootstrap_reps, seed=seed)

        rows.append({
            "source": str(columns[i]),
            "target": str(columns[j]),
            "season": season if season else "全年",
            "spearman_r": float(r) if np.isfinite(r) else 0.0,
            "p_value": float(p) if np.isfinite(p) else 1.0,
            "ci_lower": ci["ci_lower"],
            "ci_upper": ci["ci_upper"],
            "n_pairs": int(len(x)),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Indicator 3: sales share correlation
# ---------------------------------------------------------------------------


def sales_share_correlation(
    daily: pd.DataFrame,
    season: str | None = None,
    use_bootstrap: bool = True,
    bootstrap_reps: int = 200,
    seed: int = 20230907,
) -> pd.DataFrame:
    """Spearman correlation of daily sales share (entity / daily total), by season.

    Negative values suggest structural substitution (one's gain is another's loss
    in share), but cannot be interpreted as causal price substitution.
    """
    # Compute daily row totals
    daily = daily.copy()
    daily.index = pd.to_datetime(daily.index)
    row_total = daily.sum(axis=1)
    shares = daily.div(row_total.replace(0, np.nan), axis=0).fillna(0.0)

    if season:
        months = [m for m, s in MONTH_TO_SEASON.items() if s == season]
        shares = shares[shares.index.month.isin(months)]

    if shares.empty or shares.shape[1] < 2:
        return pd.DataFrame(
            columns=["source", "target", "season", "spearman_r", "ci_lower", "ci_upper", "n_pairs"]
        )

    columns = list(shares.columns)
    rows = []

    for i, j in combinations(range(len(columns)), 2):
        x = shares.iloc[:, i].to_numpy(dtype=float)
        y = shares.iloc[:, j].to_numpy(dtype=float)
        mask = np.isfinite(x) & np.isfinite(y)
        x, y = x[mask], y[mask]
        if len(x) < 30:
            continue

        def spearman_func(a, b):
            r, _ = stats.spearmanr(a, b)
            return r if np.isfinite(r) else 0.0

        r, p = stats.spearmanr(x, y)

        ci = {"estimate": float(r), "ci_lower": float(r), "ci_upper": float(r), "n_valid_blocks": 0}
        if use_bootstrap and len(x) >= 14:
            ci = _block_bootstrap_ci(x, y, spearman_func, block_length=7, reps=bootstrap_reps, seed=seed)

        rows.append({
            "source": str(columns[i]),
            "target": str(columns[j]),
            "season": season if season else "全年",
            "spearman_r": float(r) if np.isfinite(r) else 0.0,
            "p_value": float(p) if np.isfinite(p) else 1.0,
            "ci_lower": ci["ci_lower"],
            "ci_upper": ci["ci_upper"],
            "n_pairs": int(len(x)),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Indicator 4: active-day Jaccard overlap
# ---------------------------------------------------------------------------


def active_day_jaccard(daily: pd.DataFrame) -> pd.DataFrame:
    """Jaccard coefficient of active (positive-sales) days between entity pairs.

    J(A,B) = |A ∩ B| / |A ∪ B| where A = days with sales > 0 for entity A.
    """
    daily = daily.copy()
    daily.index = pd.to_datetime(daily.index)
    active = (daily > 0).astype(int)

    columns = list(active.columns)
    rows = []

    for i, j in combinations(range(len(columns)), 2):
        a = active.iloc[:, i].to_numpy(dtype=int)
        b = active.iloc[:, j].to_numpy(dtype=int)
        intersection = int(np.sum(a & b))
        union = int(np.sum(a | b))
        jaccard = intersection / union if union > 0 else 0.0

        rows.append({
            "source": str(columns[i]),
            "target": str(columns[j]),
            "intersection_days": intersection,
            "union_days": union,
            "jaccard": float(jaccard),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# BH correction
# ---------------------------------------------------------------------------


def apply_bh_correction(df: pd.DataFrame, p_col: str = "p_value") -> pd.DataFrame:
    """Append Benjamini-Hochberg corrected q-values to a DataFrame.

    Adds a column 'q_value' based on sorting p_col in ascending order.
    """
    df = df.copy()
    p_vals = df[p_col].to_numpy(dtype=float)
    n = len(p_vals)
    if n == 0:
        df["q_value"] = []
        return df

    sorted_idx = np.argsort(p_vals)
    sorted_p = p_vals[sorted_idx]
    ranks = np.arange(1, n + 1)
    q_vals = np.minimum(1.0, sorted_p * n / ranks)
    # Ensure monotonicity
    for i in range(n - 2, -1, -1):
        q_vals[i] = min(q_vals[i], q_vals[i + 1])
    result_q = np.empty(n)
    result_q[sorted_idx] = q_vals
    df["q_value"] = result_q
    return df


# ---------------------------------------------------------------------------
# Highlight rules
# ---------------------------------------------------------------------------


def add_highlight(df: pd.DataFrame, r_col: str = "spearman_r") -> pd.DataFrame:
    """Add strength label based on |r| and CI crossing zero.

    Labels:
      - 'clear': |rho| >= 0.30 and CI does not cross 0
      - 'weak': 0.15 <= |rho| < 0.30
      - 'retained': otherwise
    """
    df = df.copy()
    df["abs_r"] = df[r_col].abs()

    def _label(row):
        abs_r = abs(row.get(r_col, 0))
        ci_lower = row.get("ci_lower", 0)
        ci_upper = row.get("ci_upper", 0)
        ci_crosses_zero = (ci_lower <= 0 <= ci_upper) if "ci_lower" in row.index else True

        if abs_r >= 0.30 and not ci_crosses_zero:
            return "clear"
        elif 0.15 <= abs_r < 0.30:
            return "weak"
        else:
            return "retained"

    df["strength_label"] = df.apply(_label, axis=1)
    return df


# ---------------------------------------------------------------------------
# Combined relationship computation for a set of entities
# ---------------------------------------------------------------------------


def compute_entity_relationships(
    daily: pd.DataFrame,
    monthly_profiles: dict[str, np.ndarray],
    entity_names: list[str] | None = None,
    level: str = "unknown",
    bootstrap_reps: int = 200,
    seed: int = 20230907,
    bootstrap_only_full_year: bool = True,
) -> pd.DataFrame:
    """Compute all four relationship indicators for a set of entities.

    Parameters
    ----------
    daily : pd.DataFrame
        Entity × date pivot.
    monthly_profiles : dict
        entity → 12-month seasonal index array.
    entity_names : list[str] or None
        Subset of columns to analyze. None = all columns.
    level : str
        Analysis level label (e.g., 'category', 'within_花叶类', 'cluster_0').

    Returns
    -------
    pd.DataFrame in long format with all four indicators.
    """
    if entity_names:
        daily = daily[[c for c in daily.columns if c in entity_names]]
        monthly_profiles = {
            k: v for k, v in monthly_profiles.items() if k in entity_names
        }

    columns = [str(c) for c in daily.columns]
    if len(columns) < 2:
        return pd.DataFrame()

    # 1. Seasonal index correlation
    si_corr = seasonal_index_correlation(monthly_profiles)

    # 2-3. Seasonal sales and share correlations (all seasons + full year)
    sales_rows = []
    share_rows = []
    for season in SEASON_ORDER + [None]:
        use_bs = (
            not bootstrap_only_full_year or season is None
        )
        s_df = seasonal_sales_correlation(
            daily, season=season, use_bootstrap=use_bs,
            bootstrap_reps=bootstrap_reps, seed=seed
        )
        if not s_df.empty:
            sales_rows.append(s_df)

        sh_df = sales_share_correlation(
            daily, season=season, use_bootstrap=use_bs,
            bootstrap_reps=bootstrap_reps, seed=seed
        )
        if not sh_df.empty:
            share_rows.append(sh_df)

    sales_all = pd.concat(sales_rows, ignore_index=True) if sales_rows else pd.DataFrame()
    share_all = pd.concat(share_rows, ignore_index=True) if share_rows else pd.DataFrame()

    # 4. Jaccard
    jaccard_df = active_day_jaccard(daily)

    # Merge all into one long table
    # Build base pair list
    pair_rows = []
    for i, j in combinations(range(len(columns)), 2):
        a, b = columns[i], columns[j]
        key = (a, b) if a < b else (b, a)
        si_val = si_corr.get(key, si_corr.get((b, a), 0.0))
        jac_row = jaccard_df[
            ((jaccard_df["source"] == a) & (jaccard_df["target"] == b))
            | ((jaccard_df["source"] == b) & (jaccard_df["target"] == a))
        ]
        jac = float(jac_row["jaccard"].iloc[0]) if not jac_row.empty else 0.0

        pair_rows.append({
            "level": level,
            "source": a,
            "target": b,
            "seasonal_index_corr": si_val,
            "active_jaccard": jac,
        })

    pairs = pd.DataFrame(pair_rows)

    # Merge sales correlations by season
    if not sales_all.empty:
        sales_all["season"] = sales_all["season"].fillna("全年")
        for _, s_row in sales_all.iterrows():
            season = s_row["season"]
            a, b = s_row["source"], s_row["target"]
            mask = ((pairs["source"] == a) & (pairs["target"] == b)) | (
                (pairs["source"] == b) & (pairs["target"] == a)
            )
            pairs.loc[mask, f"sales_corr_{season}"] = s_row["spearman_r"]
            pairs.loc[mask, f"sales_ci_lower_{season}"] = s_row["ci_lower"]
            pairs.loc[mask, f"sales_ci_upper_{season}"] = s_row["ci_upper"]
            pairs.loc[mask, f"sales_p_{season}"] = s_row["p_value"]

    # Merge share correlations by season
    if not share_all.empty:
        share_all["season"] = share_all["season"].fillna("全年")
        for _, s_row in share_all.iterrows():
            season = s_row["season"]
            a, b = s_row["source"], s_row["target"]
            mask = ((pairs["source"] == a) & (pairs["target"] == b)) | (
                (pairs["source"] == b) & (pairs["target"] == a)
            )
            pairs.loc[mask, f"share_corr_{season}"] = s_row["spearman_r"]
            pairs.loc[mask, f"share_ci_lower_{season}"] = s_row["ci_lower"]
            pairs.loc[mask, f"share_ci_upper_{season}"] = s_row["ci_upper"]
            pairs.loc[mask, f"share_p_{season}"] = s_row["p_value"]

    # Apply BH correction to sales and share p-values for each season
    for season in SEASON_ORDER + ["全年"]:
        p_col = f"sales_p_{season}"
        if p_col in pairs.columns:
            pairs = apply_bh_correction(pairs, p_col)
            pairs.rename(columns={"q_value": f"sales_q_{season}"}, inplace=True)

        p_col = f"share_p_{season}"
        if p_col in pairs.columns:
            pairs = apply_bh_correction(pairs, p_col)
            pairs.rename(columns={"q_value": f"share_q_{season}"}, inplace=True)

    # Add strength labels for 全年
    sales_col = "sales_corr_全年"
    if sales_col in pairs.columns:
        ci_lower_col = "sales_ci_lower_全年"
        ci_upper_col = "sales_ci_upper_全年"
        # Temporarily rename for add_highlight
        temp = pairs.rename(columns={sales_col: "spearman_r", ci_lower_col: "ci_lower", ci_upper_col: "ci_upper"})
        temp = add_highlight(temp, "spearman_r")
        pairs["strength_label"] = temp["strength_label"]

    return pairs


# ---------------------------------------------------------------------------
# Level A: Six categories
# ---------------------------------------------------------------------------


def compute_category_relationships(
    category_daily: pd.DataFrame,
    category_monthly: pd.DataFrame,
    bootstrap_reps: int = 200,
    seed: int = 20230907,
    bootstrap_only_full_year: bool = True,
) -> pd.DataFrame:
    """Compute all 15 category pairs with full relationship indicators."""
    # Build monthly profile dict
    entity_col = category_monthly.columns[0]  # entity column is first per convention
    monthly_dict = {}
    for ent in category_monthly[entity_col].unique():
        ent_data = category_monthly[category_monthly[entity_col] == ent]
        indices = np.zeros(12)
        for _, row in ent_data.iterrows():
            m = int(row["month"]) - 1
            indices[m] = row.get("seasonal_index", 1.0)
        monthly_dict[str(ent)] = indices

    return compute_entity_relationships(
        category_daily, monthly_dict,
        level="category",
        bootstrap_reps=bootstrap_reps, seed=seed,
        bootstrap_only_full_year=bootstrap_only_full_year,
    )


# ---------------------------------------------------------------------------
# Level B: Within each category (SKU pairs)
# ---------------------------------------------------------------------------


def compute_within_category_relationships(
    sku_daily: pd.DataFrame,
    sku_monthly: pd.DataFrame,
    category_assignments: dict[str, str],
    bootstrap_reps: int = 200,
    seed: int = 20230907,
    bootstrap_only_full_year: bool = True,
) -> dict[str, pd.DataFrame]:
    """For each category, compute relationships among its SKUs."""
    entity_col = sku_monthly.columns[0]
    results = {}
    for cat, skus in _group_by_category(category_assignments):
        cat_skus = [s for s in skus if s in sku_daily.columns]
        if len(cat_skus) < 2:
            continue
        cat_daily = sku_daily[cat_skus]

        monthly_dict = {}
        for sku in cat_skus:
            sku_data = sku_monthly[sku_monthly[entity_col] == sku]
            indices = np.zeros(12)
            for _, row in sku_data.iterrows():
                m = int(row["month"]) - 1
                indices[m] = row.get("seasonal_index", 1.0)
            monthly_dict[sku] = indices

        results[cat] = compute_entity_relationships(
            cat_daily, monthly_dict,
            level=f"within_{cat}",
            bootstrap_reps=bootstrap_reps, seed=seed,
            bootstrap_only_full_year=bootstrap_only_full_year,
        )
    return results


def _group_by_category(assignments: dict[str, str]) -> list[tuple[str, list[str]]]:
    """Group SKU codes by their assigned category."""
    groups: dict[str, list[str]] = {}
    for sku, cat in assignments.items():
        groups.setdefault(cat, []).append(sku)
    return sorted(groups.items())


# ---------------------------------------------------------------------------
# Level C: Between clusters
# ---------------------------------------------------------------------------


def compute_cluster_relationships(
    sku_daily: pd.DataFrame,
    cluster_assignments: dict[str, int],
    sku_monthly: pd.DataFrame,
    bootstrap_reps: int = 200,
    seed: int = 20230907,
    bootstrap_only_full_year: bool = True,
) -> pd.DataFrame:
    """Aggregate SKU daily sales by cluster, then compute all cluster-pair relationships."""
    # Build cluster aggregates
    cluster_daily = {}
    for sku, cid in cluster_assignments.items():
        if sku not in sku_daily.columns:
            continue
        cid_str = f"cluster_{cid}"
        if cid_str not in cluster_daily:
            cluster_daily[cid_str] = pd.Series(0.0, index=sku_daily.index)
        cluster_daily[cid_str] += sku_daily[sku].fillna(0.0)

    cluster_pivot = pd.DataFrame(cluster_daily)

    # Build monthly profiles for each cluster
    entity_col = sku_monthly.columns[0]
    monthly_dict = {}
    for cid_str in cluster_pivot.columns:
        # Aggregate monthly profile across SKUs in this cluster
        cid = int(cid_str.split("_")[1])
        cluster_skus = [s for s, c in cluster_assignments.items() if c == cid]
        cluster_monthly = sku_monthly[sku_monthly[entity_col].isin(cluster_skus)]
        profile = (
            cluster_monthly.groupby("month")["seasonal_index"]
            .mean()
            .reindex(range(1, 13), fill_value=1.0)
            .to_numpy()
        )
        monthly_dict[cid_str] = profile

    return compute_entity_relationships(
        cluster_pivot, monthly_dict,
        level="cluster",
        bootstrap_reps=bootstrap_reps, seed=seed,
        bootstrap_only_full_year=bootstrap_only_full_year,
    )


# ---------------------------------------------------------------------------
# Level D: Within each cluster
# ---------------------------------------------------------------------------


def compute_within_cluster_relationships(
    sku_daily: pd.DataFrame,
    sku_monthly: pd.DataFrame,
    cluster_assignments: dict[str, int],
    bootstrap_reps: int = 200,
    seed: int = 20230907,
    bootstrap_only_full_year: bool = True,
) -> dict[int, pd.DataFrame]:
    """For each cluster, compute relationships among its member SKUs."""
    results = {}
    clusters: dict[int, list[str]] = {}
    for sku, cid in cluster_assignments.items():
        clusters.setdefault(cid, []).append(sku)

    entity_col = sku_monthly.columns[0]
    for cid, skus in clusters.items():
        if len(skus) < 2:
            continue
        cid_skus = [s for s in skus if s in sku_daily.columns]
        if len(cid_skus) < 2:
            continue

        cid_daily = sku_daily[cid_skus]
        monthly_dict = {}
        for sku in cid_skus:
            sku_data = sku_monthly[sku_monthly[entity_col] == sku]
            indices = np.zeros(12)
            for _, row in sku_data.iterrows():
                m = int(row["month"]) - 1
                indices[m] = row.get("seasonal_index", 1.0)
            monthly_dict[sku] = indices

        results[cid] = compute_entity_relationships(
            cid_daily, monthly_dict,
            level=f"within_cluster_{cid}",
            bootstrap_reps=bootstrap_reps, seed=seed,
            bootstrap_only_full_year=bootstrap_only_full_year,
        )
    return results


# ---------------------------------------------------------------------------
# Matrix builders for heatmap output
# ---------------------------------------------------------------------------


def build_correlation_matrix(
    pairs: pd.DataFrame,
    value_col: str,
    entity_order: list[str],
) -> pd.DataFrame:
    """Build a square correlation matrix from long-format pairs.

    Parameters
    ----------
    pairs : pd.DataFrame
        Must have 'source', 'target', and value_col columns.
    value_col : str
        Column name for the value to fill the matrix.
    entity_order : list[str]
        Ordered list of entity names for rows/columns.

    Returns
    -------
    pd.DataFrame with entity_order as both index and columns.
    """
    n = len(entity_order)
    arr = np.zeros((n, n))
    np.fill_diagonal(arr, 1.0 if "corr" in value_col else 1.0)
    mat = pd.DataFrame(arr, index=entity_order, columns=entity_order)

    for _, row in pairs.iterrows():
        src, tgt = str(row["source"]), str(row["target"])
        if src in mat.index and tgt in mat.columns:
            mat.loc[src, tgt] = row[value_col]
            mat.loc[tgt, src] = row[value_col]

    return mat


def build_seasonal_matrices(
    pairs: pd.DataFrame,
    entity_order: list[str],
) -> dict[str, pd.DataFrame]:
    """Build four seasonal correlation matrices from long-format pairs.

    Returns dict with keys: sales_春, sales_夏, sales_秋, sales_冬, share_春, ...
    """
    matrices = {}
    for season in SEASON_ORDER:
        col = f"sales_corr_{season}"
        if col in pairs.columns:
            matrices[f"sales_{season}"] = build_correlation_matrix(pairs, col, entity_order)

        col = f"share_corr_{season}"
        if col in pairs.columns:
            matrices[f"share_{season}"] = build_correlation_matrix(pairs, col, entity_order)

    return matrices
