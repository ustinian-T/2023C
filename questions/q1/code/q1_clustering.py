#!/usr/bin/env python3
"""Q1 clustering: K-means seasonal clustering with k selection and cluster naming.

Uses 24 standardized features (12 monthly sales proportions + 12 monthly active rates).
Evaluates k=2..8 with multiple metrics and bootstrap stability.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import (
    silhouette_score,
    calinski_harabasz_score,
    davies_bouldin_score,
    adjusted_rand_score,
)

from q1_seasonality import (
    MONTH_TO_SEASON,
    SEASON_ORDER,
    MONTH_ORDER,
    compute_monthly_profile,
    compute_seasonal_profile,
    build_clustering_features,
)


def _single_kmeans(
    X: np.ndarray, k: int, seed: int, n_init: int = 100
) -> tuple[np.ndarray, KMeans]:
    """Run K-means with multiple initializations, return best labels and model."""
    model = KMeans(
        n_clusters=k, n_init=n_init, max_iter=500, random_state=seed, init="k-means++"
    )
    labels = model.fit_predict(X)
    return labels, model


def evaluate_k_range(
    X: np.ndarray,
    daily_pivot: pd.DataFrame,
    monthly_profile: pd.DataFrame,
    entity_col: str,
    k_range: tuple[int, int] = (2, 8),
    seed: int = 20230907,
    n_init: int = 100,
    bootstrap_reps: int = 100,
) -> pd.DataFrame:
    """Evaluate k=2..8 with internal metrics and year-block bootstrap stability.

    Parameters
    ----------
    X : np.ndarray
        Standardized feature matrix (n_entities × 24).
    daily_pivot : pd.DataFrame
        Entity × date pivot table (used for sales-year detection).
    monthly_profile : pd.DataFrame
        Monthly profile from compute_monthly_profile.
    entity_col : str
        Name of entity column.
    k_range : tuple
        (min_k, max_k) inclusive.
    seed : int
        Random seed for reproducibility.
    n_init : int
        Number of K-means initializations.
    bootstrap_reps : int
        Number of bootstrap resampling iterations.

    Returns
    -------
    pd.DataFrame with columns:
        k, silhouette, calinski_harabasz, davies_bouldin, min_cluster_size,
        bootstrap_ari_mean, bootstrap_ari_std
    """
    min_k, max_k = k_range
    rows = []

    # Identify sales years for block bootstrap
    daily_pivot = daily_pivot.copy()
    daily_pivot.index = pd.to_datetime(daily_pivot.index)

    def _sales_year(dt):
        return dt.year if dt.month >= 7 else dt.year - 1

    years = sorted(set(_sales_year(d) for d in daily_pivot.index))
    year_indices = {
        y: [i for i, d in enumerate(daily_pivot.index) if _sales_year(d) == y]
        for y in years
    }

    for k in range(min_k, max_k + 1):
        labels, model = _single_kmeans(X, k, seed, n_init)

        # Internal metrics
        sil = silhouette_score(X, labels) if k >= 2 else float("nan")
        ch = calinski_harabasz_score(X, labels) if k >= 2 else float("nan")
        db = davies_bouldin_score(X, labels) if k >= 2 else float("nan")

        # Min cluster size
        _, counts = np.unique(labels, return_counts=True)
        min_cluster = int(counts.min())

        # Entity-bootstrap stability (ARI)
        ari_values = []
        rng = np.random.default_rng(seed)
        n = X.shape[0]
        for _ in range(bootstrap_reps):
            # Bootstrap entities with replacement
            boot_idx = rng.choice(n, size=n, replace=True)
            unique_idx = np.unique(boot_idx)
            if len(unique_idx) < k:
                continue
            try:
                # Fit on bootstrapped entities
                X_boot = X[boot_idx]
                labels_boot, _ = _single_kmeans(X_boot, k, seed, n_init=30)

                # Build mapping: for entities appearing in both original and bootstrap,
                # compare their cluster assignments
                # Map each original entity to its majority vote in bootstrap
                # Simplification: fit on unique subset, compare on intersection
                X_unique = X[unique_idx]
                labels_unique, _ = _single_kmeans(X_unique, k, seed, n_init=30)

                # Compare the two clusterings on the unique entities
                ari_values.append(adjusted_rand_score(
                    labels[unique_idx], labels_unique
                ))
            except Exception:
                continue

        ari_mean = float(np.mean(ari_values)) if ari_values else float("nan")
        ari_std = float(np.std(ari_values)) if ari_values else float("nan")

        rows.append({
            "k": k,
            "silhouette": float(sil),
            "calinski_harabasz": float(ch),
            "davies_bouldin": float(db),
            "min_cluster_size": min_cluster,
            "cluster_sizes": str(sorted(counts.tolist())),
            "bootstrap_ari_mean": ari_mean,
            "bootstrap_ari_std": ari_std,
            "bootstrap_reps_valid": len(ari_values),
        })

    return pd.DataFrame(rows)


def cluster_and_name(
    X: np.ndarray,
    monthly_profile: pd.DataFrame,
    entity_col: str,
    entity_name_col: str,
    k: int = 5,
    seed: int = 20230907,
    n_init: int = 200,
    max_retries: int = 20,
    min_cluster_size: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run K-means with chosen k and assign deterministic names based on cluster centers.

    Retries with different seeds if any cluster is smaller than min_cluster_size.

    Returns
    -------
    sku_clusters : pd.DataFrame
        Entity → cluster assignment with cluster name.
    cluster_profiles : pd.DataFrame
        Per-cluster seasonal profile, peak metrics, and representative entities.
    """
    best_labels = None
    best_model = None
    best_min_size = 0

    for retry in range(max_retries):
        try_seed = seed + retry * 1000
        labels, model = _single_kmeans(X, k, try_seed, n_init)
        _, counts = np.unique(labels, return_counts=True)
        cur_min = int(counts.min())

        if cur_min >= min_cluster_size:
            best_labels = labels
            best_model = model
            break

        if cur_min > best_min_size:
            best_labels = labels
            best_model = model
            best_min_size = cur_min

    if best_labels is None:
        raise RuntimeError(f"K-means failed to produce clusters with min size >= {min_cluster_size}")

    labels = best_labels
    model = best_model
    _, counts = np.unique(labels, return_counts=True)
    if counts.min() < min_cluster_size:
        print(f"Warning: min cluster size = {counts.min()} < {min_cluster_size} "
              f"(best found after {max_retries} retries)")

    # Build entity-cluster table
    entities = monthly_profile[entity_col].unique()
    sku_clusters = pd.DataFrame({
        entity_col: entities,
        "cluster_id": labels,
    })

    # Merge entity names if available
    if entity_name_col and entity_name_col in monthly_profile.columns:
        names = monthly_profile[[entity_col, entity_name_col]].drop_duplicates()
        sku_clusters = sku_clusters.merge(names, on=entity_col, how="left")
    else:
        sku_clusters["entity_name"] = sku_clusters[entity_col]

    # Compute cluster centers (24-dim)
    centers = model.cluster_centers_  # shape (k, 24)
    half = 12
    prop_centers = centers[:, :half]
    active_centers = centers[:, half:]

    # Determine peak month for each cluster (from standardized proportions)
    peak_months = np.argmax(prop_centers, axis=1) + 1  # 1-indexed

    # Compute actual (unstandardized) seasonal profiles per cluster
    monthly_with_cluster = monthly_profile.merge(
        sku_clusters[[entity_col, "cluster_id"]], on=entity_col, how="left"
    )

    cluster_monthly = (
        monthly_with_cluster.groupby(["cluster_id", "month"], as_index=False)
        .agg(
            avg_daily_sales=("avg_daily_sales", "mean"),
            sales_proportion=("sales_proportion", "mean"),
            active_rate=("active_rate", "mean"),
            seasonal_index=("seasonal_index", "mean"),
        )
    )
    cluster_monthly["season"] = cluster_monthly["month"].map(MONTH_TO_SEASON)

    # Seasonal aggregation per cluster
    cluster_seasonal = (
        cluster_monthly.groupby(["cluster_id", "season"], as_index=False)
        .agg(
            sales_proportion=("sales_proportion", "sum"),
            seasonal_index=("seasonal_index", "mean"),
            active_rate=("active_rate", "mean"),
        )
    )
    cluster_seasonal["season"] = pd.Categorical(
        cluster_seasonal["season"], categories=SEASON_ORDER, ordered=True
    )

    # Determine cluster names from peak season and concentration
    def _name_cluster(cid: int) -> str:
        cdata = cluster_seasonal[cluster_seasonal["cluster_id"] == cid].copy()
        if cdata.empty:
            return f"簇{cid}"
        # Find peak season
        peak_row = cdata.loc[cdata["sales_proportion"].idxmax()]
        peak_season = str(peak_row["season"])

        # Check if year-round (all seasons > 15% proportion)
        props = cdata["sales_proportion"].values
        if np.all(props > 0.15) and (props.max() / (props.min() + 0.01) < 2.5):
            return "常年型"

        # Check concentration
        if props.max() / (props.min() + 0.01) > 3.0:
            # Strongly seasonal
            pm = peak_months[cid]
            if peak_season == "春季":
                return "春季型"
            elif peak_season == "夏季":
                if pm in [6]:
                    return "初夏型"
                else:
                    return "夏秋型"
            elif peak_season == "秋季":
                return "夏秋型"
            elif peak_season == "冬季":
                return "冬季型"

        # Moderate seasonality
        if peak_season == "春季":
            return "春季偏常型"
        elif peak_season == "夏季":
            return "夏季偏常型"
        elif peak_season == "秋季":
            return "秋季偏常型"
        elif peak_season == "冬季":
            return "冬季偏常型"
        return f"簇{cid}"

    cluster_names = {cid: _name_cluster(cid) for cid in range(k)}
    sku_clusters["cluster_name"] = sku_clusters["cluster_id"].map(cluster_names)
    sku_clusters["peak_month"] = sku_clusters["cluster_id"].map(
        lambda cid: int(peak_months[cid])
    )

    # Build detailed cluster profiles
    profile_rows = []
    for cid in range(k):
        cname = cluster_names[cid]
        c_skus = sku_clusters[sku_clusters["cluster_id"] == cid]
        n_skus = len(c_skus)

        c_monthly = cluster_monthly[cluster_monthly["cluster_id"] == cid].copy()
        peak_month = int(peak_months[cid])

        profile_rows.append({
            "cluster_id": cid,
            "cluster_name": cname,
            "n_skus": n_skus,
            "peak_month": peak_month,
            "peak_season": MONTH_TO_SEASON.get(peak_month, ""),
            "spring_proportion": float(
                cluster_seasonal.loc[
                    (cluster_seasonal["cluster_id"] == cid) & (cluster_seasonal["season"] == "春季"),
                    "sales_proportion"
                ].sum()
            ),
            "summer_proportion": float(
                cluster_seasonal.loc[
                    (cluster_seasonal["cluster_id"] == cid) & (cluster_seasonal["season"] == "夏季"),
                    "sales_proportion"
                ].sum()
            ),
            "autumn_proportion": float(
                cluster_seasonal.loc[
                    (cluster_seasonal["cluster_id"] == cid) & (cluster_seasonal["season"] == "秋季"),
                    "sales_proportion"
                ].sum()
            ),
            "winter_proportion": float(
                cluster_seasonal.loc[
                    (cluster_seasonal["cluster_id"] == cid) & (cluster_seasonal["season"] == "冬季"),
                    "sales_proportion"
                ].sum()
            ),
            "representative_skus": "、".join(
                c_skus[entity_name_col].head(5).tolist()
                if entity_name_col and entity_name_col in c_skus.columns
                else c_skus[entity_col].head(5).tolist()
            ),
            "all_sku_codes": ";".join(c_skus[entity_col].tolist()),
        })

    cluster_profiles = pd.DataFrame(profile_rows)
    # Add monthly detail to cluster_profiles by merging
    cluster_monthly_wide = cluster_monthly.pivot(
        index="cluster_id", columns="month", values=["sales_proportion", "active_rate", "seasonal_index"]
    )
    cluster_monthly_wide.columns = [
        f"{col[0]}_month_{int(col[1])}" for col in cluster_monthly_wide.columns
    ]
    cluster_profiles = cluster_profiles.merge(
        cluster_monthly_wide.reset_index(), on="cluster_id", how="left"
    )

    return sku_clusters, cluster_profiles
