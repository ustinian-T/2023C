#!/usr/bin/env python3
"""Q1: MSTL detrending -> approximate MIC screening -> Graphical Lasso network.

All numerical modeling is implemented in Python. Plotting is delegated to
``code/plot_q1_matlab.m``.
"""

from __future__ import annotations

import argparse
import json
import math
import warnings
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

import networkx as nx
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.covariance import GraphicalLasso
from sklearn.exceptions import ConvergenceWarning
from statsmodels.tsa.seasonal import MSTL


@dataclass(frozen=True)
class Config:
    random_seed: int = 20230907
    min_span_days: int = 730
    min_sales_days: int = 180
    min_coverage: float = 0.35
    min_total_qty: float = 200.0
    weekly_period: int = 7
    annual_period: int = 365
    mic_alpha: float = 0.60
    mic_max_bins: int = 12
    mic_null_draws_sku: int = 2000
    mic_null_draws_category: int = 1500
    mic_null_quantile: float = 0.99
    ebic_gamma: float = 0.50
    alpha_grid_size: int = 30
    alpha_min_ratio: float = 0.02
    alpha_max_ratio: float = 0.95
    bootstrap_reps_sku: int = 100
    bootstrap_reps_category: int = 200
    bootstrap_block_length: int = 14
    bootstrap_stability_cutoff: float = 0.70
    edge_zero_tol: float = 1e-6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="Directory containing processed_daily_sku.csv and processed_daily_category.csv",
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
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
    missing = [name for name in required if not (candidate / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing {', '.join(missing)} in shared data directory {candidate}"
        )
    return candidate


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig", float_format="%.10g")


def save_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def join_reasons(flags: Iterable[tuple[bool, str]]) -> str:
    reasons = [label for passed, label in flags if not passed]
    return "included" if not reasons else ";".join(reasons)


def validate_inputs(sku: pd.DataFrame, category: pd.DataFrame) -> dict[str, Any]:
    required_sku = {
        "date",
        "sku_code",
        "sku_name",
        "category_name",
        "gross_sales_qty",
    }
    required_category = {"date", "category_name", "gross_sales_qty"}
    missing_sku = sorted(required_sku - set(sku.columns))
    missing_category = sorted(required_category - set(category.columns))
    if missing_sku or missing_category:
        raise ValueError(f"Missing columns: sku={missing_sku}, category={missing_category}")
    duplicate_sku = int(sku.duplicated(["date", "sku_code"]).sum())
    duplicate_category = int(category.duplicated(["date", "category_name"]).sum())
    negative_sku = int((sku["gross_sales_qty"] < 0).sum())
    negative_category = int((category["gross_sales_qty"] < 0).sum())
    if duplicate_sku or duplicate_category or negative_sku or negative_category:
        raise ValueError(
            "Input integrity failure: "
            f"duplicate_sku={duplicate_sku}, duplicate_category={duplicate_category}, "
            f"negative_sku={negative_sku}, negative_category={negative_category}"
        )
    return {
        "duplicate_sku_day_keys": duplicate_sku,
        "duplicate_category_day_keys": duplicate_category,
        "negative_sku_qty_rows": negative_sku,
        "negative_category_qty_rows": negative_category,
        "sku_date_min": str(sku["date"].min().date()),
        "sku_date_max": str(sku["date"].max().date()),
        "category_date_min": str(category["date"].min().date()),
        "category_date_max": str(category["date"].max().date()),
    }


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
    activity["span_days"] = (activity["last_date"] - activity["first_date"]).dt.days + 1
    activity["coverage"] = activity["record_days"] / activity["span_days"]
    conditions = pd.DataFrame(
        {
            "span_pass": activity["span_days"] >= cfg.min_span_days,
            "sales_days_pass": activity["sales_days"] >= cfg.min_sales_days,
            "coverage_pass": activity["coverage"] >= cfg.min_coverage,
            "total_qty_pass": activity["total_qty_kg"] >= cfg.min_total_qty,
        }
    )
    activity["included"] = conditions.all(axis=1)
    activity["selection_reason"] = [
        join_reasons(
            [
                (row.span_pass, f"span<{cfg.min_span_days}"),
                (row.sales_days_pass, f"sales_days<{cfg.min_sales_days}"),
                (row.coverage_pass, f"coverage<{cfg.min_coverage:.2f}"),
                (row.total_qty_pass, f"total_qty<{cfg.min_total_qty:g}"),
            ]
        )
        for row in conditions.itertuples(index=False)
    ]
    return activity


def decompose_mstl(values: pd.Series, cfg: Config) -> pd.DataFrame:
    series = pd.Series(values.to_numpy(dtype=float), index=values.index, name="log_sales")
    fit = MSTL(
        series,
        periods=(cfg.weekly_period, cfg.annual_period),
        iterate=2,
        stl_kwargs={"robust": True},
    ).fit()
    seasonal = fit.seasonal
    if isinstance(seasonal, pd.Series):
        seasonal = seasonal.to_frame(f"seasonal_{cfg.weekly_period}")
    seasonal = pd.DataFrame(seasonal, index=series.index)
    if seasonal.shape[1] != 2:
        raise RuntimeError(f"Expected two MSTL seasonal components, got {seasonal.shape[1]}")
    seasonal.columns = [f"seasonal_{cfg.weekly_period}", f"seasonal_{cfg.annual_period}"]
    out = pd.DataFrame(
        {
            "log_sales": series,
            "trend": np.asarray(fit.trend, dtype=float),
            f"seasonal_{cfg.weekly_period}": seasonal.iloc[:, 0].to_numpy(),
            f"seasonal_{cfg.annual_period}": seasonal.iloc[:, 1].to_numpy(),
            "residual": np.asarray(fit.resid, dtype=float),
        },
        index=series.index,
    )
    if not np.isfinite(out.to_numpy()).all():
        raise RuntimeError("MSTL produced non-finite components")
    return out


def build_sku_matrices(
    sku: pd.DataFrame, activity: pd.DataFrame, cfg: Config
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    selected = activity.loc[activity["included"]].copy()
    if selected.shape[0] < 3:
        raise RuntimeError(f"Only {selected.shape[0]} SKUs passed activity filter")
    common_start = selected["first_date"].max()
    common_end = selected["last_date"].min()
    if common_start > common_end:
        raise RuntimeError("Selected SKUs have no common active interval")
    common_index = pd.date_range(common_start, common_end, freq="D")
    residuals: dict[str, pd.Series] = {}
    raw_common: dict[str, pd.Series] = {}
    decompositions: dict[str, pd.DataFrame] = {}
    selected_codes = set(selected["sku_code"])
    for code, group in sku.loc[sku["sku_code"].isin(selected_codes)].groupby("sku_code"):
        first, last = group["date"].min(), group["date"].max()
        index = pd.date_range(first, last, freq="D")
        daily = group.set_index("date")["gross_sales_qty"].reindex(index, fill_value=0.0)
        parts = decompose_mstl(np.log1p(daily), cfg)
        residuals[str(code)] = parts["residual"].reindex(common_index)
        raw_common[str(code)] = daily.reindex(common_index)
        decompositions[str(code)] = parts
    residual_df = pd.DataFrame(residuals, index=common_index)
    raw_df = pd.DataFrame(raw_common, index=common_index)
    if residual_df.isna().any().any() or raw_df.isna().any().any():
        raise RuntimeError("Common-window SKU matrices contain missing values")
    exemplar = selected.sort_values("total_qty_kg", ascending=False).iloc[0]
    example_parts = decompositions[str(exemplar["sku_code"])].copy()
    example_group = sku.loc[sku["sku_code"] == exemplar["sku_code"]]
    example_daily = (
        example_group.set_index("date")["gross_sales_qty"]
        .reindex(example_parts.index, fill_value=0.0)
        .rename("sales_qty_kg")
    )
    example = pd.concat([example_daily, example_parts], axis=1).reset_index(names="date")
    example.insert(1, "sku_code", str(exemplar["sku_code"]))
    example.insert(2, "sku_name", exemplar["sku_name"])
    example.insert(3, "category_name", exemplar["category_name"])
    metadata = selected[
        ["sku_code", "sku_name", "category_name", "first_date", "last_date", "total_qty_kg"]
    ].copy()
    return residual_df, raw_df, example, metadata


def build_category_matrices(
    category: pd.DataFrame, cfg: Config
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    full_index = pd.date_range(category["date"].min(), category["date"].max(), freq="D")
    raw = (
        category.pivot(index="date", columns="category_name", values="gross_sales_qty")
        .reindex(full_index)
        .fillna(0.0)
        .sort_index(axis=1)
    )
    residual = {}
    decomposition = {}
    for name in raw.columns:
        parts = decompose_mstl(np.log1p(raw[name]), cfg)
        residual[str(name)] = parts["residual"]
        decomposition[str(name)] = parts
    residual_df = pd.DataFrame(residual, index=full_index)
    return residual_df, raw, decomposition


def fit_candidate_distributions(values: np.ndarray) -> list[dict[str, Any]]:
    positive = np.asarray(values, dtype=float)
    positive = positive[np.isfinite(positive) & (positive > 0)]
    if positive.size < 30:
        return []
    candidates: list[tuple[str, Any, tuple[float, ...], int]] = []
    candidates.append(("Normal", stats.norm, stats.norm.fit(positive), 2))
    candidates.append(("Lognormal", stats.lognorm, stats.lognorm.fit(positive, floc=0), 2))
    candidates.append(("Gamma", stats.gamma, stats.gamma.fit(positive, floc=0), 2))
    candidates.append(("Weibull", stats.weibull_min, stats.weibull_min.fit(positive, floc=0), 2))
    rows: list[dict[str, Any]] = []
    for name, dist, params, k in candidates:
        logpdf = dist.logpdf(positive, *params)
        finite = np.isfinite(logpdf)
        log_likelihood = float(logpdf[finite].sum()) if finite.all() else -np.inf
        aic = float(2 * k - 2 * log_likelihood) if np.isfinite(log_likelihood) else np.inf
        ks_stat, ks_p = stats.kstest(positive, dist.cdf, args=params)
        # Standardize parameter columns for MATLAB plotting.
        if name == "Normal":
            p1, p2, p3 = float(params[0]), float(params[1]), np.nan
        else:
            p1, p2, p3 = float(params[0]), float(params[-1]), float(params[1])
        rows.append(
            {
                "distribution": name,
                "n_positive": int(positive.size),
                "parameter_1": p1,
                "parameter_2": p2,
                "parameter_3": p3,
                "log_likelihood": log_likelihood,
                "aic": aic,
                "ks_statistic": float(ks_stat),
                "ks_p_value": float(ks_p),
            }
        )
    return rows


def distribution_analysis(
    series_map: dict[tuple[str, str, str], pd.Series]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    candidate_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for (level, code, name), series in series_map.items():
        values = series.to_numpy(dtype=float)
        rows = fit_candidate_distributions(values)
        base = {
            "level": level,
            "item_code": str(code),
            "item_name": name,
            "n_days": int(values.size),
            "zero_share": float(np.mean(values <= 0)),
            "mean_qty_kg": float(np.mean(values)),
            "median_qty_kg": float(np.median(values)),
        }
        if not rows:
            summary_rows.append(
                {
                    **base,
                    "best_distribution": "insufficient",
                    "best_aic": np.nan,
                    "delta_aic_second": np.nan,
                    "best_ks_p_value": np.nan,
                    "fit_conclusion": "insufficient",
                }
            )
            continue
        for row in rows:
            candidate_rows.append({**base, **row})
        ranked = sorted(rows, key=lambda r: r["aic"])
        best = ranked[0]
        summary_rows.append(
            {
                **base,
                "best_distribution": best["distribution"],
                "best_aic": best["aic"],
                "delta_aic_second": ranked[1]["aic"] - best["aic"],
                "best_ks_p_value": best["ks_p_value"],
                "fit_conclusion": "parametric_accepted"
                if best["ks_p_value"] >= 0.05
                else "kde_fallback",
            }
        )
    return pd.DataFrame(candidate_rows), pd.DataFrame(summary_rows)


def quantile_labels(x: np.ndarray, bins: int) -> np.ndarray:
    # Average ranks keep equal residual values in the same bin.  Using ordinal
    # ranks would break zero/tied sales by time order and create spurious MIC.
    ranks = stats.rankdata(x, method="average") - 1
    labels = np.floor(ranks * bins / len(x)).astype(np.int16)
    return np.minimum(labels, bins - 1)


def mutual_information_labels(x: np.ndarray, y: np.ndarray, nx: int, ny: int) -> float:
    counts = np.bincount(x.astype(np.int64) * ny + y.astype(np.int64), minlength=nx * ny)
    table = counts.reshape(nx, ny).astype(float)
    total = table.sum()
    if total <= 0:
        return 0.0
    pxy = table / total
    px = pxy.sum(axis=1, keepdims=True)
    py = pxy.sum(axis=0, keepdims=True)
    expected = px @ py
    mask = pxy > 0
    return float(np.sum(pxy[mask] * np.log(pxy[mask] / expected[mask])))


def mic_approx_from_cache(
    cache_x: dict[int, np.ndarray],
    cache_y: dict[int, np.ndarray],
    n: int,
    cfg: Config,
) -> float:
    budget = max(4, int(math.floor(n**cfg.mic_alpha)))
    max_bins = min(cfg.mic_max_bins, budget // 2)
    best = 0.0
    for bx in range(2, max_bins + 1):
        max_by = min(cfg.mic_max_bins, budget // bx)
        for by in range(2, max_by + 1):
            mi = mutual_information_labels(cache_x[bx], cache_y[by], bx, by)
            denom = math.log(min(bx, by))
            if denom > 0:
                best = max(best, mi / denom)
    return float(min(max(best, 0.0), 1.0))


def mic_matrix_and_null(
    x: pd.DataFrame, cfg: Config, null_draws: int, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    values = x.to_numpy(dtype=float)
    n, p = values.shape
    budget = max(4, int(math.floor(n**cfg.mic_alpha)))
    max_bins = min(cfg.mic_max_bins, budget // 2)
    caches = [
        {b: quantile_labels(values[:, j], b) for b in range(2, max_bins + 1)}
        for j in range(p)
    ]
    mic = np.eye(p, dtype=float)
    for i, j in combinations(range(p), 2):
        score = mic_approx_from_cache(caches[i], caches[j], n, cfg)
        mic[i, j] = mic[j, i] = score
    null_scores = np.empty(null_draws, dtype=float)
    for draw in range(null_draws):
        i, j = rng.choice(p, size=2, replace=False)
        # A circular-shift surrogate preserves the marginal serial dependence
        # of the second series while destroying contemporaneous alignment.
        min_shift = min(14, max(1, n // 4))
        shift = int(rng.integers(min_shift, n - min_shift + 1))
        permuted = np.roll(values[:, j], shift)
        perm_cache = {b: quantile_labels(permuted, b) for b in range(2, max_bins + 1)}
        null_scores[draw] = mic_approx_from_cache(caches[i], perm_cache, n, cfg)
    return mic, null_scores


def gaussian_copula(x: pd.DataFrame) -> np.ndarray:
    n = x.shape[0]
    z = np.empty(x.shape, dtype=float)
    for j, col in enumerate(x.columns):
        rank = stats.rankdata(x[col].to_numpy(dtype=float), method="average")
        u = (rank - 0.5) / n
        z[:, j] = stats.norm.ppf(np.clip(u, 1e-6, 1 - 1e-6))
    z -= z.mean(axis=0, keepdims=True)
    scale = z.std(axis=0, ddof=1, keepdims=True)
    if np.any(scale <= 0):
        raise RuntimeError("Constant residual column after rank-Gaussian transform")
    return z / scale


def partial_correlation(precision: np.ndarray) -> np.ndarray:
    diag = np.sqrt(np.diag(precision))
    partial = -precision / np.outer(diag, diag)
    np.fill_diagonal(partial, 1.0)
    return partial


def fit_graphical_lasso_path(
    z: np.ndarray, cfg: Config
) -> tuple[GraphicalLasso, pd.DataFrame, float]:
    n, p = z.shape
    covariance = np.cov(z, rowvar=False, ddof=1)
    off_diag = covariance - np.diag(np.diag(covariance))
    alpha_max = float(np.max(np.abs(off_diag)))
    if alpha_max <= 0:
        raise RuntimeError("All off-diagonal covariances are zero")
    alphas = np.geomspace(
        alpha_max * cfg.alpha_min_ratio,
        alpha_max * cfg.alpha_max_ratio,
        cfg.alpha_grid_size,
    )
    path_rows: list[dict[str, Any]] = []
    models: list[GraphicalLasso | None] = []
    for alpha in alphas:
        model = GraphicalLasso(
            alpha=float(alpha),
            max_iter=500,
            tol=1e-4,
            assume_centered=True,
        )
        converged = True
        error = ""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ConvergenceWarning)
            try:
                model.fit(z)
                converged = not any(issubclass(w.category, ConvergenceWarning) for w in caught)
            except Exception as exc:  # Numerical failure is recorded, not hidden.
                converged = False
                error = f"{type(exc).__name__}: {exc}"
        if not converged and error:
            models.append(None)
            path_rows.append(
                {
                    "alpha": alpha,
                    "edge_count": np.nan,
                    "log_likelihood": np.nan,
                    "ebic": np.inf,
                    "converged": False,
                    "error": error,
                }
            )
            continue
        precision = model.precision_
        edge_count = int(np.count_nonzero(np.triu(np.abs(precision) > cfg.edge_zero_tol, 1)))
        log_likelihood = float(n * model.score(z))
        parameter_count = p + edge_count
        ebic = float(
            -2 * log_likelihood
            + parameter_count * np.log(n)
            + 4 * cfg.ebic_gamma * edge_count * np.log(p)
        )
        models.append(model)
        path_rows.append(
            {
                "alpha": alpha,
                "edge_count": edge_count,
                "log_likelihood": log_likelihood,
                "ebic": ebic,
                "converged": converged,
                "error": error,
            }
        )
    path = pd.DataFrame(path_rows)
    valid = path["ebic"].replace([np.inf, -np.inf], np.nan).notna()
    if not valid.any():
        raise RuntimeError("No valid Graphical Lasso fit on alpha path")
    best_idx = int(path.loc[valid, "ebic"].idxmin())
    best_model = models[best_idx]
    if best_model is None:
        raise RuntimeError("Internal error selecting Graphical Lasso model")
    return best_model, path, float(path.loc[best_idx, "alpha"])


def moving_block_indices(n: int, block: int, rng: np.random.Generator) -> np.ndarray:
    block = min(block, n)
    n_blocks = int(math.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=n_blocks)
    return np.concatenate([np.arange(s, s + block) for s in starts])[:n]


def bootstrap_edges(
    z: np.ndarray,
    alpha: float,
    base_partial: np.ndarray,
    cfg: Config,
    reps: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, int]:
    p = z.shape[1]
    active_count = np.zeros((p, p), dtype=int)
    same_sign_count = np.zeros((p, p), dtype=int)
    success = 0
    for _ in range(reps):
        idx = moving_block_indices(len(z), cfg.bootstrap_block_length, rng)
        model = GraphicalLasso(alpha=alpha, max_iter=500, tol=1e-4, assume_centered=True)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ConvergenceWarning)
                model.fit(z[idx])
            part = partial_correlation(model.precision_)
        except Exception:
            continue
        active = np.abs(np.triu(part, 1)) > cfg.edge_zero_tol
        same = active & (np.sign(part) == np.sign(base_partial))
        active_count += active.astype(int)
        same_sign_count += same.astype(int)
        success += 1
    if success == 0:
        raise RuntimeError("All Graphical Lasso bootstrap fits failed")
    active_rate = active_count / success
    same_sign_rate = same_sign_count / success
    active_rate += active_rate.T
    same_sign_rate += same_sign_rate.T
    np.fill_diagonal(active_rate, 1.0)
    np.fill_diagonal(same_sign_rate, 1.0)
    return active_rate, same_sign_rate, success


def pair_long_table(
    columns: list[str],
    raw_spearman: np.ndarray,
    residual_spearman: np.ndarray,
    mic: np.ndarray,
    partial: np.ndarray,
    active_rate: np.ndarray,
    same_sign_rate: np.ndarray,
    mic_threshold: float,
    cfg: Config,
) -> pd.DataFrame:
    rows = []
    for i, j in combinations(range(len(columns)), 2):
        gl_edge = abs(partial[i, j]) > cfg.edge_zero_tol
        mic_candidate = mic[i, j] >= mic_threshold
        stable = same_sign_rate[i, j] >= cfg.bootstrap_stability_cutoff
        rows.append(
            {
                "source_code": str(columns[i]),
                "target_code": str(columns[j]),
                "spearman_raw": raw_spearman[i, j],
                "spearman_residual": residual_spearman[i, j],
                "mic_approx": mic[i, j],
                "mic_candidate": mic_candidate,
                "partial_corr": partial[i, j],
                "graphical_lasso_edge": gl_edge,
                "bootstrap_active_rate": active_rate[i, j],
                "bootstrap_same_sign_rate": same_sign_rate[i, j],
                "final_stable_edge": bool(mic_candidate and gl_edge and stable),
            }
        )
    return pd.DataFrame(rows)


def jaccard(a: set[tuple[str, str]], b: set[tuple[str, str]]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def edge_set_from_mask(table: pd.DataFrame, mask: pd.Series) -> set[tuple[str, str]]:
    return {
        tuple(sorted((str(r.source_code), str(r.target_code))))
        for r in table.loc[mask].itertuples(index=False)
    }


def add_metadata(pair_table: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    meta = metadata.copy()
    meta["item_code"] = meta["item_code"].astype(str)
    left = meta.add_prefix("source_")
    right = meta.add_prefix("target_")
    out = pair_table.merge(left, left_on="source_code", right_on="source_item_code", how="left")
    out = out.merge(right, left_on="target_code", right_on="target_item_code", how="left")
    return out


def build_graph_outputs(
    pair_table: pd.DataFrame, metadata: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    meta = metadata.copy()
    meta["item_code"] = meta["item_code"].astype(str)
    graph = nx.Graph()
    for row in meta.itertuples(index=False):
        graph.add_node(
            str(row.item_code),
            item_name=row.item_name,
            category_name=row.category_name,
        )
    edges = pair_table.loc[pair_table["final_stable_edge"]].copy()
    for row in edges.itertuples(index=False):
        graph.add_edge(
            str(row.source_code),
            str(row.target_code),
            weight=abs(float(row.partial_corr)),
            signed_weight=float(row.partial_corr),
            stability=float(row.bootstrap_same_sign_rate),
        )
    degree = dict(graph.degree())
    weighted_degree = dict(graph.degree(weight="weight"))
    distance_graph = graph.copy()
    for _, _, data in distance_graph.edges(data=True):
        data["distance"] = 1.0 / max(data["weight"], 1e-12)
    betweenness = nx.betweenness_centrality(distance_graph, weight="distance")
    communities: list[set[str]] = []
    if graph.number_of_edges() > 0:
        communities = [set(c) for c in nx.algorithms.community.greedy_modularity_communities(graph, weight="weight")]
    else:
        communities = [{str(node)} for node in graph.nodes]
    community_id = {node: idx + 1 for idx, community in enumerate(communities) for node in community}
    node_rows = []
    for row in meta.itertuples(index=False):
        code = str(row.item_code)
        node_rows.append(
            {
                "item_code": code,
                "item_name": row.item_name,
                "category_name": row.category_name,
                "degree": degree.get(code, 0),
                "weighted_degree": weighted_degree.get(code, 0.0),
                "betweenness": betweenness.get(code, 0.0),
                "community_id": community_id.get(code, 0),
            }
        )
    nodes = pd.DataFrame(node_rows).sort_values(
        ["weighted_degree", "degree", "item_code"], ascending=[False, False, True]
    )
    nodes["core_rank"] = np.arange(1, len(nodes) + 1)
    nodes["is_core_node"] = nodes["core_rank"] <= min(10, len(nodes))
    community_rows = []
    for cid, group in nodes.groupby("community_id"):
        community_rows.append(
            {
                "community_id": int(cid),
                "node_count": int(len(group)),
                "member_names": "、".join(group.sort_values("core_rank")["item_name"].astype(str)),
                "category_composition": "、".join(
                    f"{k}:{v}" for k, v in group["category_name"].value_counts().sort_index().items()
                ),
            }
        )
    return edges, nodes, pd.DataFrame(community_rows)


def category_edge_summary(edges: pd.DataFrame) -> pd.DataFrame:
    if edges.empty:
        return pd.DataFrame(
            columns=[
                "category_pair",
                "edge_count",
                "positive_edges",
                "negative_edges",
                "mean_abs_partial_corr",
                "mean_stability",
            ]
        )
    work = edges.copy()
    work["category_pair"] = [
        "--".join(sorted((str(a), str(b))))
        for a, b in zip(work["source_category_name"], work["target_category_name"])
    ]
    return (
        work.groupby("category_pair", as_index=False)
        .agg(
            edge_count=("partial_corr", "size"),
            positive_edges=("partial_corr", lambda x: int((x > 0).sum())),
            negative_edges=("partial_corr", lambda x: int((x < 0).sum())),
            mean_abs_partial_corr=("partial_corr", lambda x: float(np.abs(x).mean())),
            mean_stability=("bootstrap_same_sign_rate", "mean"),
        )
        .sort_values(["edge_count", "mean_abs_partial_corr"], ascending=[False, False])
    )


def network_analysis(
    level: str,
    residual_df: pd.DataFrame,
    raw_df: pd.DataFrame,
    metadata: pd.DataFrame,
    cfg: Config,
    rng: np.random.Generator,
    null_draws: int,
    bootstrap_reps: int,
) -> dict[str, Any]:
    columns = [str(c) for c in residual_df.columns]
    residual_df = residual_df.copy()
    raw_df = raw_df.copy()
    residual_df.columns = columns
    raw_df.columns = columns
    raw_spearman = stats.spearmanr(raw_df.to_numpy(), axis=0).statistic
    residual_spearman = stats.spearmanr(residual_df.to_numpy(), axis=0).statistic
    mic, null_scores = mic_matrix_and_null(residual_df, cfg, null_draws, rng)
    mic_threshold = float(np.quantile(null_scores, cfg.mic_null_quantile))
    z = gaussian_copula(residual_df)
    best_model, alpha_path, selected_alpha = fit_graphical_lasso_path(z, cfg)
    precision = best_model.precision_
    eig_min = float(np.linalg.eigvalsh(precision).min())
    partial = partial_correlation(precision)
    active_rate, same_sign_rate, bootstrap_success = bootstrap_edges(
        z, selected_alpha, partial, cfg, bootstrap_reps, rng
    )
    pairs = pair_long_table(
        columns,
        np.asarray(raw_spearman),
        np.asarray(residual_spearman),
        mic,
        partial,
        active_rate,
        same_sign_rate,
        mic_threshold,
        cfg,
    )
    pairs = add_metadata(pairs, metadata)
    edges, nodes, communities = build_graph_outputs(pairs, metadata)
    if not edges.empty:
        edges = edges.copy()
        edges["association_type"] = np.where(
            edges["partial_corr"] > 0, "潜在互补/同步", "潜在替代"
        )
        edges = edges.sort_values(
            ["bootstrap_same_sign_rate", "partial_corr"],
            key=lambda s: np.abs(s) if s.name == "partial_corr" else s,
            ascending=False,
        )
    raw_abs = np.abs(pairs["spearman_raw"].to_numpy())
    if len(edges) > 0:
        baseline_cut = float(np.partition(raw_abs, -len(edges))[-len(edges)])
    else:
        baseline_cut = float(np.quantile(raw_abs, 0.95))
    baseline_set = edge_set_from_mask(pairs, np.abs(pairs["spearman_raw"]) >= baseline_cut)
    final_set = edge_set_from_mask(pairs, pairs["final_stable_edge"])
    baseline_comparison = pd.DataFrame(
        [
            {
                "level": level,
                "baseline_method": "raw_spearman_equal_density",
                "baseline_abs_threshold": baseline_cut,
                "baseline_edge_count": len(baseline_set),
                "final_edge_count": len(final_set),
                "edge_jaccard": jaccard(baseline_set, final_set),
            }
        ]
    )
    sensitivity_rows = []
    base_pre_set = edge_set_from_mask(
        pairs, pairs["mic_candidate"] & pairs["graphical_lasso_edge"]
    )
    for factor in (0.8, 1.0, 1.2):
        model = GraphicalLasso(
            alpha=selected_alpha * factor,
            max_iter=500,
            tol=1e-4,
            assume_centered=True,
        ).fit(z)
        part = partial_correlation(model.precision_)
        mask = []
        for row in pairs.itertuples(index=False):
            i, j = columns.index(str(row.source_code)), columns.index(str(row.target_code))
            mask.append(row.mic_approx >= mic_threshold and abs(part[i, j]) > cfg.edge_zero_tol)
        current = edge_set_from_mask(pairs, pd.Series(mask, index=pairs.index))
        sensitivity_rows.append(
            {
                "level": level,
                "parameter": "alpha_factor",
                "value": factor,
                "threshold": selected_alpha * factor,
                "edge_count": len(current),
                "jaccard_vs_base": jaccard(base_pre_set, current),
            }
        )
    for q in (0.975, 0.99, 0.995):
        threshold = float(np.quantile(null_scores, q))
        mask = (
            (pairs["mic_approx"] >= threshold)
            & pairs["graphical_lasso_edge"]
            & (pairs["bootstrap_same_sign_rate"] >= cfg.bootstrap_stability_cutoff)
        )
        current = edge_set_from_mask(pairs, mask)
        sensitivity_rows.append(
            {
                "level": level,
                "parameter": "mic_null_quantile",
                "value": q,
                "threshold": threshold,
                "edge_count": len(current),
                "jaccard_vs_base": jaccard(final_set, current),
            }
        )
    for cutoff in (0.60, 0.70, 0.80):
        mask = (
            pairs["mic_candidate"]
            & pairs["graphical_lasso_edge"]
            & (pairs["bootstrap_same_sign_rate"] >= cutoff)
        )
        current = edge_set_from_mask(pairs, mask)
        sensitivity_rows.append(
            {
                "level": level,
                "parameter": "bootstrap_stability_cutoff",
                "value": cutoff,
                "threshold": cutoff,
                "edge_count": len(current),
                "jaccard_vs_base": jaccard(final_set, current),
            }
        )
    return {
        "pairs": pairs,
        "edges": edges,
        "nodes": nodes,
        "communities": communities,
        "alpha_path": alpha_path,
        "null_scores": pd.DataFrame({"mic_null_score": null_scores}),
        "baseline_comparison": baseline_comparison,
        "sensitivity": pd.DataFrame(sensitivity_rows),
        "category_edge_summary": category_edge_summary(edges),
        "summary": {
            "level": level,
            "n_days": int(residual_df.shape[0]),
            "n_nodes": int(residual_df.shape[1]),
            "mic_threshold": mic_threshold,
            "selected_alpha": selected_alpha,
            "precision_min_eigenvalue": eig_min,
            "bootstrap_requested": bootstrap_reps,
            "bootstrap_success": bootstrap_success,
            "graphical_lasso_edges": int(pairs["graphical_lasso_edge"].sum()),
            "mic_candidates": int(pairs["mic_candidate"].sum()),
            "final_stable_edges": int(pairs["final_stable_edge"].sum()),
            "positive_final_edges": int((edges.get("partial_corr", pd.Series(dtype=float)) > 0).sum()),
            "negative_final_edges": int((edges.get("partial_corr", pd.Series(dtype=float)) < 0).sum()),
            "community_count": int(communities.shape[0]),
            "raw_final_edge_jaccard": float(baseline_comparison.iloc[0]["edge_jaccard"]),
        },
    }


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    cfg = Config()
    outputs = root / "outputs"
    tables = outputs / "tables"
    results = outputs / "results"
    tables.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)
    input_dir = find_input_dir(root, args.input_dir)
    sku = pd.read_csv(input_dir / "processed_daily_sku.csv", dtype={"sku_code": "string"})
    category = pd.read_csv(input_dir / "processed_daily_category.csv")
    sku["date"] = pd.to_datetime(sku["date"], errors="raise")
    category["date"] = pd.to_datetime(category["date"], errors="raise")
    sku["sku_code"] = sku["sku_code"].astype(str)
    integrity = validate_inputs(sku, category)
    activity = build_activity_table(sku, cfg)
    write_csv(activity, tables / "tab_q1_sku_activity_filter.csv")

    sku_residual, sku_raw, stl_example, sku_meta = build_sku_matrices(sku, activity, cfg)
    category_residual, category_raw, _ = build_category_matrices(category, cfg)
    write_csv(stl_example, tables / "tab_q1_stl_example.csv")
    write_csv(sku_residual.reset_index(names="date"), tables / "tab_q1_sku_residual_matrix.csv")
    write_csv(sku_raw.reset_index(names="date"), tables / "tab_q1_sku_common_sales.csv")
    write_csv(category_raw.reset_index(names="date"), tables / "tab_q1_category_daily_sales.csv")
    write_csv(category_residual.reset_index(names="date"), tables / "tab_q1_category_residual_matrix.csv")

    series_map: dict[tuple[str, str, str], pd.Series] = {}
    for name in category_raw.columns:
        series_map[("category", str(name), str(name))] = category_raw[name]
    selected_codes = set(activity.loc[activity["included"], "sku_code"].astype(str))
    for row in activity.loc[activity["included"]].itertuples(index=False):
        group = sku.loc[sku["sku_code"] == str(row.sku_code)]
        index = pd.date_range(group["date"].min(), group["date"].max(), freq="D")
        series = group.set_index("date")["gross_sales_qty"].reindex(index, fill_value=0.0)
        series_map[("sku", str(row.sku_code), str(row.sku_name))] = series
    candidates, distribution_summary = distribution_analysis(series_map)
    write_csv(candidates, tables / "tab_q1_distribution_candidates.csv")
    write_csv(distribution_summary, tables / "tab_q1_distribution_summary.csv")

    sku_metadata = sku_meta.rename(
        columns={"sku_code": "item_code", "sku_name": "item_name"}
    )[["item_code", "item_name", "category_name"]]
    category_metadata = pd.DataFrame(
        {
            "item_code": [str(c) for c in category_residual.columns],
            "item_name": [str(c) for c in category_residual.columns],
            "category_name": [str(c) for c in category_residual.columns],
        }
    )
    rng = np.random.default_rng(cfg.random_seed)
    sku_net = network_analysis(
        "sku",
        sku_residual,
        sku_raw,
        sku_metadata,
        cfg,
        rng,
        cfg.mic_null_draws_sku,
        cfg.bootstrap_reps_sku,
    )
    category_net = network_analysis(
        "category",
        category_residual,
        category_raw,
        category_metadata,
        cfg,
        rng,
        cfg.mic_null_draws_category,
        cfg.bootstrap_reps_category,
    )

    output_map = {
        "tab_q1_sku_pair_measures.csv": sku_net["pairs"],
        "tab_q1_sku_network_edges.csv": sku_net["edges"],
        "tab_q1_sku_node_metrics.csv": sku_net["nodes"],
        "tab_q1_sku_communities.csv": sku_net["communities"],
        "tab_q1_sku_alpha_path.csv": sku_net["alpha_path"],
        "tab_q1_sku_mic_null.csv": sku_net["null_scores"],
        "tab_q1_sku_baseline_comparison.csv": sku_net["baseline_comparison"],
        "tab_q1_sku_sensitivity.csv": sku_net["sensitivity"],
        "tab_q1_sku_category_edge_summary.csv": sku_net["category_edge_summary"],
        "tab_q1_category_pair_measures.csv": category_net["pairs"],
        "tab_q1_category_network_edges.csv": category_net["edges"],
        "tab_q1_category_node_metrics.csv": category_net["nodes"],
        "tab_q1_category_communities.csv": category_net["communities"],
        "tab_q1_category_alpha_path.csv": category_net["alpha_path"],
        "tab_q1_category_mic_null.csv": category_net["null_scores"],
        "tab_q1_category_baseline_comparison.csv": category_net["baseline_comparison"],
        "tab_q1_category_sensitivity.csv": category_net["sensitivity"],
    }
    for filename, frame in output_map.items():
        write_csv(frame, tables / filename)

    summary = {
        "model": "MSTL(7,365) -> approximate MIC circular-shift null screen -> EBIC Graphical Lasso -> moving-block bootstrap",
        "input_directory": input_dir.name,
        "config": asdict(cfg),
        "integrity": integrity,
        "all_sku_count": int(activity.shape[0]),
        "selected_sku_count": int(activity["included"].sum()),
        "sku_common_start": str(sku_residual.index.min().date()),
        "sku_common_end": str(sku_residual.index.max().date()),
        "distribution": {
            "objects": int(distribution_summary.shape[0]),
            "kde_fallback_count": int((distribution_summary["fit_conclusion"] == "kde_fallback").sum()),
            "parametric_accepted_count": int(
                (distribution_summary["fit_conclusion"] == "parametric_accepted").sum()
            ),
        },
        "sku_network": sku_net["summary"],
        "category_network": category_net["summary"],
        "top_sku_core_nodes": sku_net["nodes"].head(10)[
            ["item_code", "item_name", "category_name", "degree", "weighted_degree"]
        ].to_dict(orient="records"),
    }
    save_json(summary, results / "q1_summary.json")
    save_json({"config": asdict(cfg)}, results / "q1_config.json")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
