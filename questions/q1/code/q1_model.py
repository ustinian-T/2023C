#!/usr/bin/env python3
"""Q1 redesign: distribution → seasonal profiling → K-means clustering → hierarchical relationships.

Pipeline:
  1. Two-part distribution analysis (zero-inflation + positive-sales fit)
  2. Monthly & seasonal profiles (12-month indices, proportions, active rates)
  3. K-means clustering (k=2..8 evaluation, k=5 selected, deterministic naming)
  4. Four-level relationship analysis with 4 complementary indicators
  5. Bootstrap 95% CI + BH correction as credibility marks

All numerical modeling in Python. MATLAB handles academic plotting only.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=".*constant.*")

# Local modules (imported after path setup)
# We add the code directory to sys.path so imports work when run from anywhere
_code_dir = Path(__file__).resolve().parent
if str(_code_dir) not in sys.path:
    sys.path.insert(0, str(_code_dir))

from q1_distribution import distribution_analysis  # noqa: E402
from q1_seasonality import (  # noqa: E402
    compute_monthly_profile,
    compute_seasonal_profile,
    compute_peak_metrics,
    build_seasonal_index_table,
    build_clustering_features,
)
from q1_clustering import (  # noqa: E402
    evaluate_k_range,
    cluster_and_name,
)
from q1_relationships import (  # noqa: E402
    compute_category_relationships,
    compute_within_category_relationships,
    compute_cluster_relationships,
    compute_within_cluster_relationships,
    build_correlation_matrix,
    build_seasonal_matrices,
    seasonal_index_correlation,
    active_day_jaccard,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    random_seed: int = 20230907
    # SKU activity filter (new: relaxed for seasonal products)
    min_span_days: int = 730
    min_sales_days: int = 90
    min_total_qty_kg: float = 100.0  # no coverage threshold
    # Clustering
    k_min: int = 2
    k_max: int = 8
    k_selected: int = 5
    k_n_init: int = 100
    k_bootstrap_reps: int = 100
    # Relationship bootstrap
    relationship_bootstrap_reps: int = 200
    bootstrap_block_length: int = 7
    bootstrap_only_full_year: bool = True  # Only bootstrap full-year for speed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir", type=Path, default=None,
        help="Directory containing processed_daily_sku.csv and processed_daily_category.csv",
    )
    parser.add_argument(
        "--root", type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    return parser.parse_args()


def find_input_dir(root: Path, supplied: Path | None) -> Path:
    if supplied is not None:
        candidate = supplied.resolve()
        if not (candidate / "processed_daily_sku.csv").exists():
            raise FileNotFoundError(f"Missing processed_daily_sku.csv in {candidate}")
        return candidate
    repository_root = root.parents[1]
    candidate = repository_root / "data" / "processed"
    required = ("processed_daily_sku.csv", "processed_daily_category.csv")
    missing = [n for n in required if not (candidate / n).exists()]
    if missing:
        raise FileNotFoundError(f"Missing {missing} in {candidate}")
    return candidate


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig", float_format="%.10g")


def save_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def join_reasons(flags: list[tuple[bool, str]]) -> str:
    reasons = [label for passed, label in flags if not passed]
    return "included" if not reasons else ";".join(reasons)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def validate_inputs(sku: pd.DataFrame, category: pd.DataFrame) -> dict[str, Any]:
    required_sku = {"date", "sku_code", "sku_name", "category_name", "gross_sales_qty"}
    required_category = {"date", "category_name", "gross_sales_qty"}
    missing_sku = sorted(required_sku - set(sku.columns))
    missing_category = sorted(required_category - set(category.columns))
    if missing_sku or missing_category:
        raise ValueError(f"Missing columns: sku={missing_sku}, category={missing_category}")
    dup_sku = int(sku.duplicated(["date", "sku_code"]).sum())
    dup_cat = int(category.duplicated(["date", "category_name"]).sum())
    neg_sku = int((sku["gross_sales_qty"] < 0).sum())
    neg_cat = int((category["gross_sales_qty"] < 0).sum())
    if dup_sku or dup_cat or neg_sku or neg_cat:
        raise ValueError(
            f"Integrity failure: dup_sku={dup_sku}, dup_cat={dup_cat}, "
            f"neg_sku={neg_sku}, neg_cat={neg_cat}"
        )
    return {
        "dup_sku_day_keys": dup_sku,
        "dup_cat_day_keys": dup_cat,
        "neg_sku_rows": neg_sku,
        "neg_cat_rows": neg_cat,
        "sku_date_min": str(sku["date"].min().date()),
        "sku_date_max": str(sku["date"].max().date()),
        "cat_date_min": str(category["date"].min().date()),
        "cat_date_max": str(category["date"].max().date()),
    }


# ---------------------------------------------------------------------------
# SKU activity filter (new criteria)
# ---------------------------------------------------------------------------


def build_activity_table(sku: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    activity = (
        sku.groupby(["sku_code", "sku_name", "category_name"], as_index=False)
        .agg(
            record_days=("date", "size"),
            first_date=("date", "min"),
            last_date=("date", "max"),
            sales_days=("gross_sales_qty", lambda x: int((x > 0).sum())),
            total_qty_kg=("gross_sales_qty", "sum"),
        )
        .sort_values(["category_name", "sku_code"])
        .reset_index(drop=True)
    )
    activity["span_days"] = (
        activity["last_date"] - activity["first_date"]
    ).dt.days + 1
    activity["coverage"] = activity["record_days"] / activity["span_days"]

    conditions = pd.DataFrame({
        "span_pass": activity["span_days"] >= cfg.min_span_days,
        "sales_days_pass": activity["sales_days"] >= cfg.min_sales_days,
        "total_qty_pass": activity["total_qty_kg"] >= cfg.min_total_qty_kg,
    })
    activity["included"] = conditions.all(axis=1)
    activity["selection_reason"] = [
        join_reasons([
            (row.span_pass, f"span<{cfg.min_span_days}"),
            (row.sales_days_pass, f"sales_days<{cfg.min_sales_days}"),
            (row.total_qty_pass, f"total_qty<{cfg.min_total_qty_kg:g}"),
        ])
        for row in conditions.itertuples(index=False)
    ]
    return activity


# ---------------------------------------------------------------------------
# Build daily pivot tables
# ---------------------------------------------------------------------------


def build_sku_daily_pivot(sku: pd.DataFrame, selected_codes: set[str]) -> pd.DataFrame:
    """Build SKU × date pivot for selected SKUs over full date range."""
    full_index = pd.date_range(sku["date"].min(), sku["date"].max(), freq="D")
    sku_filtered = sku[sku["sku_code"].isin(selected_codes)]
    pivot = sku_filtered.pivot_table(
        index="date", columns="sku_code", values="gross_sales_qty",
        aggfunc="sum", fill_value=0.0,
    )
    pivot = pivot.reindex(full_index, fill_value=0.0)
    pivot.index = pd.to_datetime(pivot.index)
    return pivot.sort_index()


def build_category_daily_pivot(category: pd.DataFrame) -> pd.DataFrame:
    """Build category × date pivot over full date range."""
    full_index = pd.date_range(
        category["date"].min(), category["date"].max(), freq="D"
    )
    pivot = category.pivot_table(
        index="date", columns="category_name", values="gross_sales_qty",
        aggfunc="sum", fill_value=0.0,
    )
    pivot = pivot.reindex(full_index, fill_value=0.0)
    pivot.index = pd.to_datetime(pivot.index)
    return pivot.sort_index()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    cfg = Config()
    outputs = root / "outputs"
    tables = outputs / "tables"
    results = outputs / "results"
    tables.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)

    # ---- Load data ----
    input_dir = find_input_dir(root, args.input_dir)
    sku = pd.read_csv(
        input_dir / "processed_daily_sku.csv", dtype={"sku_code": "string"}
    )
    category = pd.read_csv(input_dir / "processed_daily_category.csv")
    sku["date"] = pd.to_datetime(sku["date"], errors="raise")
    category["date"] = pd.to_datetime(category["date"], errors="raise")
    sku["sku_code"] = sku["sku_code"].astype(str)
    integrity = validate_inputs(sku, category)

    # ---- SKU activity filter ----
    activity = build_activity_table(sku, cfg)
    write_csv(activity, tables / "tab_q1_sku_activity_filter.csv")

    selected_codes = set(
        activity.loc[activity["included"], "sku_code"].astype(str)
    )
    n_selected = len(selected_codes)
    print(f"SKU activity filter: {n_selected}/{len(activity)} selected")

    if n_selected < 3:
        raise RuntimeError(f"Only {n_selected} SKUs pass activity filter")

    # ---- Daily pivot tables ----
    sku_daily = build_sku_daily_pivot(sku, selected_codes)
    category_daily = build_category_daily_pivot(category)
    write_csv(
        sku_daily.reset_index(names="date"),
        tables / "tab_q1_sku_daily_pivot.csv",
    )
    write_csv(
        category_daily.reset_index(names="date"),
        tables / "tab_q1_category_daily_sales.csv",
    )

    # ---- Distribution analysis ----
    series_map: dict[tuple[str, str, str], pd.Series] = {}
    for cat_name in category_daily.columns:
        series_map[("category", str(cat_name), str(cat_name))] = category_daily[
            cat_name
        ]
    for row in activity.loc[activity["included"]].itertuples(index=False):
        group = sku[sku["sku_code"] == str(row.sku_code)]
        idx = pd.date_range(group["date"].min(), group["date"].max(), freq="D")
        series = (
            group.set_index("date")["gross_sales_qty"]
            .reindex(idx, fill_value=0.0)
        )
        series_map[("sku", str(row.sku_code), str(row.sku_name))] = series

    candidates, dist_summary = distribution_analysis(series_map)
    write_csv(candidates, tables / "tab_q1_distribution_candidates.csv")
    write_csv(dist_summary, tables / "tab_q1_distribution_summary.csv")

    dist_counts = dist_summary["fit_conclusion"].value_counts()
    print(
        f"Distribution: {dist_counts.get('parametric_accepted', 0)} parametric, "
        f"{dist_counts.get('kde_fallback', 0)} KDE fallback, "
        f"{dist_counts.get('insufficient', 0)} insufficient"
    )

    # ---- Monthly & seasonal profiles ----
    # Category profiles
    cat_monthly = compute_monthly_profile(category, "category_name")
    cat_seasonal = compute_seasonal_profile(cat_monthly, "category_name")
    cat_peak = compute_peak_metrics(cat_monthly, "category_name")
    cat_seasonal_index = build_seasonal_index_table(
        cat_monthly, "category_name"
    )
    write_csv(cat_monthly, tables / "tab_q1_monthly_category_profile.csv")
    write_csv(cat_seasonal_index, tables / "tab_q1_category_seasonal_index.csv")
    write_csv(cat_peak, tables / "tab_q1_category_peak_metrics.csv")

    # SKU profiles
    sku_filtered = sku[sku["sku_code"].isin(selected_codes)]
    sku_monthly = compute_monthly_profile(sku_filtered, "sku_code")
    sku_seasonal = compute_seasonal_profile(sku_monthly, "sku_code")
    sku_peak = compute_peak_metrics(sku_monthly, "sku_code")
    sku_seasonal_index = build_seasonal_index_table(
        sku_monthly, "sku_code", "sku_name"
    )
    write_csv(sku_monthly, tables / "tab_q1_monthly_sku_profile.csv")
    write_csv(sku_seasonal_index, tables / "tab_q1_sku_seasonal_index.csv")
    write_csv(sku_peak, tables / "tab_q1_sku_peak_metrics.csv")

    # Merge SKU names into monthly for clustering label readability
    sku_monthly_named = sku_monthly.merge(
        sku_filtered[["sku_code", "sku_name"]].drop_duplicates(),
        on="sku_code", how="left",
    )

    # ---- Clustering ----
    features_df, feature_matrix = build_clustering_features(
        sku_monthly, "sku_code"
    )

    # K evaluation
    k_eval = evaluate_k_range(
        feature_matrix,
        sku_daily,
        sku_monthly,
        "sku_code",
        k_range=(cfg.k_min, cfg.k_max),
        seed=cfg.random_seed,
        n_init=cfg.k_n_init,
        bootstrap_reps=cfg.k_bootstrap_reps,
    )
    write_csv(k_eval, tables / "tab_q1_cluster_k_selection.csv")

    # Cluster with k=5 (use named monthly for readable representative SKUs)
    sku_clusters, cluster_profiles = cluster_and_name(
        feature_matrix,
        sku_monthly_named,
        "sku_code",
        "sku_name",
        k=cfg.k_selected,
        seed=cfg.random_seed,
        n_init=cfg.k_n_init,
    )
    write_csv(sku_clusters, tables / "tab_q1_sku_clusters.csv")
    write_csv(cluster_profiles, tables / "tab_q1_cluster_profiles.csv")

    print(
        f"Clustering k={cfg.k_selected}: "
        f"silhouette={k_eval.loc[k_eval['k'] == cfg.k_selected, 'silhouette'].values[0]:.4f}, "
        f"sizes={k_eval.loc[k_eval['k'] == cfg.k_selected, 'cluster_sizes'].values[0]}"
    )

    # ---- Relationships ----
    # (sku_monthly_named already created before clustering above)

    # Level A: Six categories
    print("Computing category relationships...")
    cat_rels = compute_category_relationships(
        category_daily, cat_monthly,
        bootstrap_reps=cfg.relationship_bootstrap_reps,
        seed=cfg.random_seed,
        bootstrap_only_full_year=cfg.bootstrap_only_full_year,
    )
    write_csv(cat_rels, tables / "tab_q1_category_pair_relationships.csv")

    # Build category matrices for heatmaps
    cat_order = sorted(category_daily.columns.tolist())
    cat_matrices = build_seasonal_matrices(cat_rels, cat_order)
    for key, mat in cat_matrices.items():
        write_csv(mat.reset_index(names="entity"), tables / f"tab_q1_category_matrix_{key}.csv")

    # Seasonal index matrix
    cat_si_dict = {}
    for _, row in cat_monthly.iterrows():
        cat = str(row["category_name"])
        if cat not in cat_si_dict:
            cat_si_dict[cat] = np.zeros(12)
        m = int(row["month"]) - 1
        cat_si_dict[cat][m] = row["seasonal_index"]
    cat_si_corr = seasonal_index_correlation(cat_si_dict)
    si_rows = [
        {"source": a, "target": b, "seasonal_index_corr": r}
        for (a, b), r in cat_si_corr.items()
    ]
    write_csv(
        pd.DataFrame(si_rows),
        tables / "tab_q1_category_seasonal_index_corr.csv",
    )

    # Active Jaccard
    cat_jaccard = active_day_jaccard(category_daily)
    write_csv(cat_jaccard, tables / "tab_q1_category_active_jaccard.csv")

    # Level B: Within each category
    print("Computing within-category relationships...")
    cat_assignments = {
        str(row.sku_code): str(row.category_name)
        for row in activity.loc[activity["included"]].itertuples(index=False)
    }
    within_cat_rels = compute_within_category_relationships(
        sku_daily, sku_monthly_named, cat_assignments,
        bootstrap_reps=cfg.relationship_bootstrap_reps,
        seed=cfg.random_seed,
        bootstrap_only_full_year=cfg.bootstrap_only_full_year,
    )
    all_within_cat = []
    for cat, df in within_cat_rels.items():
        if not df.empty:
            all_within_cat.append(df)
    if all_within_cat:
        write_csv(
            pd.concat(all_within_cat, ignore_index=True),
            tables / "tab_q1_within_category_pair_relationships.csv",
        )

    # Level C: Between clusters
    print("Computing cluster relationships...")
    cluster_assignments = dict(
        zip(sku_clusters["sku_code"], sku_clusters["cluster_id"])
    )
    cluster_rels = compute_cluster_relationships(
        sku_daily, cluster_assignments,
        sku_monthly_named,
        bootstrap_reps=cfg.relationship_bootstrap_reps,
        seed=cfg.random_seed,
        bootstrap_only_full_year=cfg.bootstrap_only_full_year,
    )
    write_csv(cluster_rels, tables / "tab_q1_cluster_pair_relationships.csv")

    # Cluster matrices
    cluster_order = sorted(
        [f"cluster_{cid}" for cid in sorted(set(cluster_assignments.values()))]
    )
    cluster_matrices = build_seasonal_matrices(cluster_rels, cluster_order)
    for key, mat in cluster_matrices.items():
        write_csv(
            mat.reset_index(names="entity"),
            tables / f"tab_q1_cluster_matrix_{key}.csv",
        )

    # Level D: Within each cluster
    print("Computing within-cluster relationships...")
    within_cluster_rels = compute_within_cluster_relationships(
        sku_daily, sku_monthly_named, cluster_assignments,
        bootstrap_reps=cfg.relationship_bootstrap_reps,
        seed=cfg.random_seed,
        bootstrap_only_full_year=cfg.bootstrap_only_full_year,
    )
    all_within_cluster = []
    for cid, df in within_cluster_rels.items():
        if not df.empty:
            all_within_cluster.append(df)
    if all_within_cluster:
        write_csv(
            pd.concat(all_within_cluster, ignore_index=True),
            tables / "tab_q1_within_cluster_pair_relationships.csv",
        )

    # ---- Summary JSON ----
    try:
        rel_path = str(input_dir.relative_to(root.parents[1])).replace("\\", "/")
    except ValueError:
        rel_path = str(input_dir)
    summary = {
        "model": "Two-part distribution + seasonal profiling + K-means clustering + 4-level relationship analysis",
        "input_directory": rel_path,
        "config": asdict(cfg),
        "integrity": integrity,
        "all_sku_count": int(activity.shape[0]),
        "selected_sku_count": n_selected,
        "distribution": {
            "objects": int(dist_summary.shape[0]),
            "parametric_accepted": int(
                (dist_summary["fit_conclusion"] == "parametric_accepted").sum()
            ),
            "kde_fallback": int(
                (dist_summary["fit_conclusion"] == "kde_fallback").sum()
            ),
            "insufficient": int(
                (dist_summary["fit_conclusion"] == "insufficient").sum()
            ),
        },
        "clustering": {
            "k_selected": cfg.k_selected,
            "silhouette": float(
                k_eval.loc[k_eval["k"] == cfg.k_selected, "silhouette"].values[0]
            ),
            "calinski_harabasz": float(
                k_eval.loc[k_eval["k"] == cfg.k_selected, "calinski_harabasz"].values[0]
            ),
            "davies_bouldin": float(
                k_eval.loc[k_eval["k"] == cfg.k_selected, "davies_bouldin"].values[0]
            ),
            "bootstrap_ari_mean": float(
                k_eval.loc[k_eval["k"] == cfg.k_selected, "bootstrap_ari_mean"].values[0]
            ),
            "cluster_sizes": k_eval.loc[
                k_eval["k"] == cfg.k_selected, "cluster_sizes"
            ].values[0],
            "cluster_names": cluster_profiles["cluster_name"].tolist(),
        },
        "relationships": {
            "category_pairs": int(len(cat_rels)),
            "within_category_categories": list(within_cat_rels.keys()),
            "cluster_pairs": int(len(cluster_rels)),
            "within_cluster_ids": list(within_cluster_rels.keys()),
        },
    }
    save_json(summary, results / "q1_summary.json")
    save_json({"config": asdict(cfg)}, results / "q1_config.json")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
