"""Question 3 SKU assortment, price, and replenishment optimization.

The public helper functions are intentionally small and testable.  The real-data
pipeline and MILP are built on top of these contracts further below.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import inspect
import json
import math
from pathlib import Path
import sys
import time
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix


ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "processed"
Q2_TABLES = ROOT / "questions" / "q2" / "outputs" / "tables"
OUT = ROOT / "questions" / "q3" / "outputs"
TABLES = OUT / "tables"
RESULTS = OUT / "results"

DECISION_DATE = pd.Timestamp("2023-07-01")
CANDIDATE_START = pd.Timestamp("2023-06-24")
CANDIDATE_END = pd.Timestamp("2023-06-30")
MINIMUM_ORDER_KG = 2.5
SEED = 2023
FULL_SCENARIO_COUNT = 600
OPTIMIZATION_SCENARIO_COUNT = 60
RISK_WEIGHT = 0.25
LOWER_TAIL_PROBABILITY = 0.10
BASE_MODEL_VERSION = "2026-08-13-v1"


def _as_dates(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["date"] = pd.to_datetime(result["date"], errors="raise")
    return result


def identify_candidates(
    daily_sku: pd.DataFrame,
    start: str | pd.Timestamp = CANDIDATE_START,
    end: str | pd.Timestamp = CANDIDATE_END,
) -> pd.DataFrame:
    """Return SKUs with strictly positive retail sales in the candidate week.

    Candidate membership is based only on ``gross_sales_qty``.  Wholesale-price
    records without a retail sale therefore cannot accidentally enter Q3.
    """

    required = {
        "date",
        "sku_code",
        "sku_name",
        "category_name",
        "gross_sales_qty",
        "gross_revenue",
        "wholesale_price",
        "loss_rate_pct",
    }
    missing = required.difference(daily_sku.columns)
    if missing:
        raise ValueError(f"candidate input is missing columns: {sorted(missing)}")
    frame = _as_dates(daily_sku)
    mask = frame["date"].between(pd.Timestamp(start), pd.Timestamp(end), inclusive="both")
    recent = frame.loc[mask & (frame["gross_sales_qty"] > 0)].copy()
    if recent.empty:
        return pd.DataFrame(
            columns=[
                "sku_code",
                "sku_name",
                "category_name",
                "recent_sales_qty_kg",
                "recent_sales_days",
                "recent_revenue_yuan",
                "reference_price_yuan_per_kg",
                "latest_wholesale_price_yuan_per_kg",
                "loss_rate",
            ]
        )

    recent = recent.sort_values(["sku_code", "date"])
    grouped = recent.groupby("sku_code", sort=True, observed=True)
    rows: list[dict] = []
    for sku_code, part in grouped:
        qty = float(part["gross_sales_qty"].sum())
        revenue = float(part["gross_revenue"].sum())
        latest = part.iloc[-1]
        loss_weights = part["gross_sales_qty"].to_numpy(dtype=float)
        loss_rate = float(
            np.average(part["loss_rate_pct"].to_numpy(dtype=float), weights=loss_weights) / 100.0
        )
        rows.append(
            {
                "sku_code": str(sku_code),
                "sku_name": str(latest["sku_name"]),
                "category_name": str(latest["category_name"]),
                "recent_sales_qty_kg": qty,
                "recent_sales_days": int(part["date"].nunique()),
                "recent_revenue_yuan": revenue,
                "reference_price_yuan_per_kg": revenue / qty,
                "latest_wholesale_price_yuan_per_kg": float(latest["wholesale_price"]),
                "loss_rate": loss_rate,
            }
        )
    return pd.DataFrame(rows).sort_values("sku_code", kind="stable").reset_index(drop=True)


def empirical_bayes_shares(
    table: pd.DataFrame,
    kappa_by_category: Mapping[str, float],
    *,
    category_col: str = "category_name",
    recent_col: str = "recent_qty",
    long_col: str = "long_share",
) -> pd.DataFrame:
    """Shrink recent within-category SKU shares toward a long-run prior."""

    result = table.copy()
    shares = np.zeros(len(result), dtype=float)
    kappas = np.zeros(len(result), dtype=float)
    for category, indices in result.groupby(category_col, sort=False, observed=True).groups.items():
        idx = np.asarray(list(indices), dtype=int)
        recent = np.clip(result.loc[idx, recent_col].to_numpy(dtype=float), 0.0, None)
        prior = np.clip(result.loc[idx, long_col].to_numpy(dtype=float), 0.0, None)
        prior = prior / prior.sum() if prior.sum() > 0 else np.full(len(idx), 1.0 / len(idx))
        kappa = float(kappa_by_category[category])
        if not np.isfinite(kappa) or kappa < 0:
            raise ValueError(f"invalid kappa for {category}: {kappa}")
        denominator = recent.sum() + kappa
        posterior = (recent + kappa * prior) / denominator if denominator > 0 else prior
        shares[idx] = posterior / posterior.sum()
        kappas[idx] = kappa
    result["long_share"] = result[long_col].astype(float)
    result["recent_share"] = result.groupby(category_col, observed=True)[recent_col].transform(
        lambda values: values.clip(lower=0) / values.clip(lower=0).sum()
        if values.clip(lower=0).sum() > 0
        else 1.0 / len(values)
    )
    result["eb_share"] = shares
    result["share_kappa"] = kappas
    return result


def _normalized_candidate_shares(
    frame: pd.DataFrame,
    sku_codes: Sequence[str],
) -> np.ndarray:
    quantities = _candidate_quantities(frame, sku_codes)
    return quantities / quantities.sum() if quantities.sum() > 0 else np.full(len(sku_codes), 1.0 / len(sku_codes))


def _candidate_quantities(frame: pd.DataFrame, sku_codes: Sequence[str]) -> np.ndarray:
    return (
        frame.groupby(frame["sku_code"].astype(str), observed=True)["gross_sales_qty"]
        .sum()
        .reindex([str(code) for code in sku_codes], fill_value=0.0)
        .clip(lower=0)
        .to_numpy(dtype=float)
    )


def select_share_kappa(
    history: pd.DataFrame,
    sku_codes: Sequence[str],
    category: str,
    target_date: str | pd.Timestamp,
    *,
    grid: Sequence[float] = (0.0, 2.5, 5.0, 10.0, 20.0, 40.0, 80.0),
) -> tuple[float, int]:
    """Choose shrinkage strength by rolling one-day-ahead multinomial log loss."""

    target = pd.Timestamp(target_date)
    frame = _as_dates(history)
    frame = frame.loc[
        (frame["date"] < target)
        & (frame["category_name"] == category)
        & frame["sku_code"].astype(str).isin([str(code) for code in sku_codes])
    ].copy()
    validation_dates = sorted(frame.loc[frame["date"] >= target - pd.Timedelta(days=84), "date"].unique())
    validation_dates = [pd.Timestamp(date) for date in validation_dates if pd.Timestamp(date).weekday() == target.weekday()]
    records: list[tuple[np.ndarray, np.ndarray, np.ndarray, float]] = []
    for date in validation_dates:
        recent = frame.loc[frame["date"].between(date - pd.Timedelta(days=7), date - pd.Timedelta(days=1))]
        prior = frame.loc[
            frame["date"].between(date - pd.Timedelta(days=365), date - pd.Timedelta(days=8))
            & (frame["date"].dt.weekday == target.weekday())
        ]
        observed = frame.loc[frame["date"] == date]
        observed_qty = float(observed["gross_sales_qty"].clip(lower=0).sum())
        if observed_qty <= 0 or prior.empty:
            continue
        records.append(
            (
                _candidate_quantities(recent, sku_codes),
                _normalized_candidate_shares(prior, sku_codes),
                _normalized_candidate_shares(observed, sku_codes),
                observed_qty,
            )
        )
    if len(records) < 3:
        return 10.0, len(records)
    scores = []
    for kappa in grid:
        weighted_loss = 0.0
        total_weight = 0.0
        for recent_qty, prior_share, observed_share, weight in records:
            denominator = recent_qty.sum() + float(kappa)
            posterior = (
                (recent_qty + float(kappa) * prior_share) / denominator
                if denominator > 0
                else prior_share
            )
            weighted_loss += weight * float(-np.sum(observed_share * np.log(np.maximum(posterior, 1e-12))))
            total_weight += weight
        scores.append(weighted_loss / total_weight)
    return float(grid[int(np.argmin(scores))]), len(records)


def estimate_dynamic_shares(
    history: pd.DataFrame,
    candidates: pd.DataFrame,
    target_date: str | pd.Timestamp = DECISION_DATE,
) -> pd.DataFrame:
    """Estimate target-day SKU shares using recent sales and comparable weekdays."""

    target = pd.Timestamp(target_date)
    frame = _as_dates(history)
    frame["sku_code"] = frame["sku_code"].astype(str)
    candidate = candidates.copy()
    candidate["sku_code"] = candidate["sku_code"].astype(str)
    frame = frame.loc[(frame["date"] < target) & frame["sku_code"].isin(candidate["sku_code"])].copy()
    rows: list[dict] = []
    kappa_map: dict[str, float] = {}
    validation_map: dict[str, int] = {}
    for category, part in candidate.groupby("category_name", sort=False, observed=True):
        codes = part["sku_code"].tolist()
        recent = frame.loc[
            (frame["category_name"] == category)
            & frame["date"].between(target - pd.Timedelta(days=7), target - pd.Timedelta(days=1))
        ]
        comparable = frame.loc[
            (frame["category_name"] == category)
            & frame["date"].between(target - pd.Timedelta(days=3 * 365), target - pd.Timedelta(days=8))
            & (frame["date"].dt.weekday == target.weekday())
        ]
        recent_qty = (
            recent.groupby("sku_code")["gross_sales_qty"].sum().reindex(codes, fill_value=0.0).clip(lower=0)
        )
        long_share = _normalized_candidate_shares(comparable, codes)
        kappa, validation_count = select_share_kappa(frame, codes, str(category), target)
        kappa_map[str(category)] = kappa
        validation_map[str(category)] = validation_count
        for code, quantity, prior in zip(codes, recent_qty.to_numpy(dtype=float), long_share):
            rows.append(
                {
                    "sku_code": code,
                    "category_name": str(category),
                    "recent_qty": float(quantity),
                    "long_share": float(prior),
                }
            )
    result = empirical_bayes_shares(pd.DataFrame(rows), kappa_map)
    result["share_validation_days"] = result["category_name"].map(validation_map).astype(int)
    return candidate.merge(result, on=["sku_code", "category_name"], how="left", validate="one_to_one")


def build_share_scenarios(
    history: pd.DataFrame,
    share_table: pd.DataFrame,
    scenario_count: int,
    target_date: str | pd.Timestamp = DECISION_DATE,
    *,
    historical_weight: float = 0.50,
    seed: int = SEED,
) -> np.ndarray:
    """Bootstrap whole comparable days and shrink each draw toward EB shares."""

    target = pd.Timestamp(target_date)
    frame = _as_dates(history)
    frame["sku_code"] = frame["sku_code"].astype(str)
    table = share_table.reset_index(drop=True).copy()
    table["sku_code"] = table["sku_code"].astype(str)
    pool = frame.loc[
        (frame["date"] < target)
        & frame["date"].between(target - pd.Timedelta(days=3 * 365), target - pd.Timedelta(days=8))
        & (frame["date"].dt.weekday == target.weekday())
        & frame["sku_code"].isin(table["sku_code"])
    ].copy()
    dates = np.array(sorted(pool["date"].unique()))
    if len(dates) == 0:
        return np.repeat(table["eb_share"].to_numpy(dtype=float)[None, :], scenario_count, axis=0)
    rng = np.random.default_rng(seed)
    sampled_dates = rng.choice(dates, size=int(scenario_count), replace=True)
    result = np.zeros((int(scenario_count), len(table)), dtype=float)
    for w, sampled_date in enumerate(sampled_dates):
        day = pool.loc[pool["date"] == sampled_date]
        for category, indices in table.groupby("category_name", sort=False, observed=True).groups.items():
            idx = np.asarray(list(indices), dtype=int)
            codes = table.loc[idx, "sku_code"].tolist()
            observed = _normalized_candidate_shares(day.loc[day["category_name"] == category], codes)
            posterior = table.loc[idx, "eb_share"].to_numpy(dtype=float)
            mixed = historical_weight * observed + (1.0 - historical_weight) * posterior
            result[w, idx] = mixed / mixed.sum()
    return result


def _weighted_quantile(values: np.ndarray, quantiles: Iterable[float], weights: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not valid.any():
        raise ValueError("weighted quantile has no positive-weight observations")
    order = np.argsort(values[valid], kind="stable")
    sorted_values = values[valid][order]
    sorted_weights = weights[valid][order]
    positions = (np.cumsum(sorted_weights) - 0.5 * sorted_weights) / sorted_weights.sum()
    return np.interp(np.asarray(list(quantiles), dtype=float), positions, sorted_values)


def build_price_grid(
    history: pd.DataFrame,
    candidates: pd.DataFrame,
    category_bounds: pd.DataFrame,
    *,
    min_sku_days: int = 30,
    min_unique_prices: int = 5,
    quantiles: Sequence[float] = (0.10, 0.30, 0.50, 0.70, 0.90),
) -> pd.DataFrame:
    """Build observed-markup price choices, with a category fallback for sparse SKUs."""

    hist = _as_dates(history)
    hist = hist.loc[
        (hist["gross_sales_qty"] > 0)
        & (hist["gross_weighted_avg_price"] > 0)
        & (hist["wholesale_price"] > 0)
    ].copy()
    hist["markup"] = hist["gross_weighted_avg_price"] / hist["wholesale_price"] - 1.0
    bounds = category_bounds.set_index("category_name")
    rows: list[dict] = []
    for candidate in candidates.itertuples(index=False):
        sku_hist = hist.loc[hist["sku_code"].astype(str) == str(candidate.sku_code)]
        category_hist = hist.loc[hist["category_name"] == candidate.category_name]
        enough = (
            sku_hist["date"].nunique() >= min_sku_days
            and sku_hist["gross_weighted_avg_price"].nunique() >= min_unique_prices
        )
        source = sku_hist if enough else category_hist
        source_name = "sku_history" if enough else "category_fallback"
        if source.empty:
            raise ValueError(f"no price history for {candidate.sku_code}/{candidate.category_name}")
        raw = _weighted_quantile(
            source["markup"].to_numpy(), quantiles, source["gross_sales_qty"].to_numpy()
        )
        lower = float(bounds.loc[candidate.category_name, "markup_p05"])
        upper = float(bounds.loc[candidate.category_name, "markup_upper"])
        markups = np.clip(raw, lower, upper)
        cost = float(candidate.predicted_cost_yuan_per_kg)
        minimum_price = math.ceil(cost * (1.0 + lower) * 10.0 - 1e-9) / 10.0
        maximum_price = math.floor(cost * (1.0 + upper) * 10.0 + 1e-9) / 10.0
        if maximum_price < minimum_price:
            minimum_price = maximum_price = round(cost * (1.0 + (lower + upper) / 2.0), 1)
        prices = np.clip(np.round(cost * (1.0 + markups), 1), minimum_price, maximum_price)
        unique_pairs: list[tuple[float, float]] = []
        for markup, price in zip(markups, prices):
            realized_markup = float(price / float(candidate.predicted_cost_yuan_per_kg) - 1.0)
            if not unique_pairs or not math.isclose(price, unique_pairs[-1][1], abs_tol=1e-12):
                unique_pairs.append((realized_markup, float(price)))
        if len(unique_pairs) < 3:
            median = float(np.clip(bounds.loc[candidate.category_name, "markup_median"], lower, upper))
            fallback_markups = np.array([lower, median, upper], dtype=float)
            fallback_prices = np.clip(
                np.round(cost * (1.0 + fallback_markups), 1), minimum_price, maximum_price
            )
            unique_pairs = []
            for price in fallback_prices:
                realized_markup = float(price / float(candidate.predicted_cost_yuan_per_kg) - 1.0)
                if not unique_pairs or not math.isclose(price, unique_pairs[-1][1], abs_tol=1e-12):
                    unique_pairs.append((realized_markup, float(price)))
        for level, (markup, price) in enumerate(unique_pairs, start=1):
            rows.append(
                {
                    "sku_code": str(candidate.sku_code),
                    "sku_name": str(candidate.sku_name),
                    "category_name": str(candidate.category_name),
                    "price_level": level,
                    "markup_rate": markup,
                    "price_yuan_per_kg": price,
                    "grid_source": source_name,
                    "history_days": int(sku_hist["date"].nunique()),
                    "history_unique_prices": int(sku_hist["gross_weighted_avg_price"].nunique()),
                }
            )
    return pd.DataFrame(rows)


def select_representative_scenarios(category_demand: np.ndarray, count: int) -> np.ndarray:
    """Select deterministic total-demand quantiles, including both extremes."""

    values = np.asarray(category_demand, dtype=float)
    if values.ndim != 2 or len(values) == 0:
        raise ValueError("category_demand must be a nonempty scenarios-by-categories matrix")
    count = min(int(count), len(values))
    if count <= 0:
        raise ValueError("scenario count must be positive")
    order = np.argsort(values.sum(axis=1), kind="stable")
    positions = np.rint(np.linspace(0, len(order) - 1, count)).astype(int)
    return order[positions]


def build_sku_demand_scenarios(
    shares: np.ndarray,
    category_demand: np.ndarray,
    prices: np.ndarray,
    reference_prices: np.ndarray,
    elasticities: np.ndarray,
) -> np.ndarray:
    """Allocate category demand to SKUs and apply a constant-elasticity price response."""

    shares = np.asarray(shares, dtype=float)
    category_demand = np.asarray(category_demand, dtype=float)
    prices = np.asarray(prices, dtype=float)
    reference_prices = np.asarray(reference_prices, dtype=float)
    elasticities = np.asarray(elasticities, dtype=float)
    if shares.ndim != 2 or category_demand.shape != (shares.shape[0],):
        raise ValueError("share and category-demand scenario dimensions do not align")
    if prices.shape != (shares.shape[1],) or reference_prices.shape != prices.shape:
        raise ValueError("price vectors must have one entry per SKU")
    if elasticities.shape != prices.shape:
        raise ValueError("elasticities must have one entry per SKU")
    if (shares < 0).any() or (category_demand < 0).any() or (prices <= 0).any() or (reference_prices <= 0).any():
        raise ValueError("shares/demand must be nonnegative and prices must be positive")
    response = np.power(prices / reference_prices, elasticities)
    return shares * category_demand[:, None] * response[None, :]


def compute_big_m(
    sku_demand: np.ndarray,
    loss_rates: np.ndarray,
    *,
    minimum_order: float = MINIMUM_ORDER_KG,
    quantile: float = 0.99,
    safety_factor: float = 1.20,
) -> np.ndarray:
    """Return data-scaled replenishment bounds in pre-loss kilograms."""

    demand = np.asarray(sku_demand, dtype=float)
    losses = np.asarray(loss_rates, dtype=float)
    if demand.ndim != 2 or losses.shape != (demand.shape[1],):
        raise ValueError("demand must be scenarios-by-SKUs and losses one per SKU")
    if not np.isfinite(demand).all() or not np.isfinite(losses).all() or (losses < 0).any() or (losses >= 1).any():
        raise ValueError("demand and loss rates must be finite with 0 <= loss < 1")
    bounds = safety_factor * np.quantile(np.clip(demand, 0, None), quantile, axis=0) / (1.0 - losses)
    return np.maximum(float(minimum_order), bounds)


def lower_tail_mean(values: np.ndarray, probability: float = 0.10) -> float:
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or len(values) == 0 or not 0 < probability <= 1:
        raise ValueError("values must be nonempty and probability must be in (0, 1]")
    count = max(1, int(math.ceil(probability * len(values))))
    return float(np.mean(np.partition(values, count - 1)[:count]))


def summarize_scenario_folds(
    service_loss: np.ndarray,
    profit: np.ndarray,
    *,
    folds: int = 6,
    lower_tail_probability: float = LOWER_TAIL_PROBABILITY,
) -> pd.DataFrame:
    """Summarize fixed-strategy outcomes over deterministic scenario folds."""

    losses = np.asarray(service_loss, dtype=float)
    profits = np.asarray(profit, dtype=float)
    if losses.ndim != 1 or profits.shape != losses.shape or len(losses) == 0:
        raise ValueError("service loss and profit must be aligned nonempty vectors")
    if not np.isfinite(losses).all() or not np.isfinite(profits).all():
        raise ValueError("scenario outcomes must be finite")
    if (losses < 0).any() or (losses > 1).any():
        raise ValueError("service loss must lie in [0, 1]")
    if not 1 <= int(folds) <= len(losses):
        raise ValueError("fold count must be between one and the scenario count")
    rows = []
    for fold, indices in enumerate(np.array_split(np.arange(len(losses)), int(folds)), start=1):
        rows.append(
            {
                "fold": fold,
                "scenario_count": int(len(indices)),
                "mean_demand_satisfaction": float(1.0 - losses[indices].mean()),
                "expected_profit_yuan": float(profits[indices].mean()),
                "lower10pct_profit_yuan": lower_tail_mean(
                    profits[indices], lower_tail_probability
                ),
            }
        )
    return pd.DataFrame(rows)


def selection_jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    """Return assortment overlap, treating two empty assortments as identical."""

    left_set = {str(value) for value in left}
    right_set = {str(value) for value in right}
    union = left_set | right_set
    return 1.0 if not union else len(left_set & right_set) / len(union)


def build_sensitivity_variants() -> list[dict]:
    """Return the approved one-factor-at-a-time grid with one shared baseline."""

    baseline = {
        "variant_id": "baseline",
        "parameter_group": "baseline",
        "parameter_value": 1.0,
        "risk_weight": RISK_WEIGHT,
        "elasticity_scale": 1.0,
        "historical_share_weight": 0.50,
        "order_cap_factor": 1.0,
    }
    variants = [baseline]
    for value in (0.0, 0.50):
        variants.append(
            {**baseline, "variant_id": f"risk_weight_{value:.2f}", "parameter_group": "risk_weight", "parameter_value": value, "risk_weight": value}
        )
    for value in (0.80, 1.20):
        variants.append(
            {**baseline, "variant_id": f"elasticity_scale_{value:.2f}", "parameter_group": "elasticity_scale", "parameter_value": value, "elasticity_scale": value}
        )
    for value in (0.25, 0.75):
        variants.append(
            {**baseline, "variant_id": f"historical_share_weight_{value:.2f}", "parameter_group": "historical_share_weight", "parameter_value": value, "historical_share_weight": value}
        )
    for value in (0.85, 0.925):
        variants.append(
            {**baseline, "variant_id": f"order_cap_factor_{value:.3f}", "parameter_group": "order_cap_factor", "parameter_value": value, "order_cap_factor": value}
        )
    if len(variants) != 9 or len({item["variant_id"] for item in variants}) != 9:
        raise RuntimeError("sensitivity grid must contain exactly nine unique variants")
    return variants


def evaluate_strategy(
    strategy: pd.DataFrame,
    sku_codes: Sequence[str],
    sku_demand: np.ndarray,
    sku_cost: np.ndarray,
    category_demand: np.ndarray,
    categories: Sequence[str],
) -> dict[str, np.ndarray | float]:
    """Evaluate fixed decisions on scenarios using the exact accounting identities."""

    codes = [str(code) for code in sku_codes]
    indexed = strategy.assign(sku_code=strategy["sku_code"].astype(str)).set_index("sku_code")
    if set(codes).difference(indexed.index):
        raise ValueError("strategy is missing scenario SKU codes")
    indexed = indexed.loc[codes]
    demand = np.asarray(sku_demand, dtype=float)
    costs = np.asarray(sku_cost, dtype=float)
    cat_demand = np.asarray(category_demand, dtype=float)
    if demand.shape != costs.shape or demand.shape[1] != len(codes):
        raise ValueError("SKU demand and cost scenario dimensions do not align")
    if cat_demand.shape != (demand.shape[0], len(categories)):
        raise ValueError("category demand dimensions do not align")

    selected = indexed["selected"].to_numpy(dtype=float)
    prices = indexed["price_yuan_per_kg"].to_numpy(dtype=float)
    orders = indexed["order_qty_kg"].to_numpy(dtype=float) * selected
    losses = indexed["loss_rate"].to_numpy(dtype=float)
    available = orders * (1.0 - losses)
    sales = np.minimum(np.clip(demand, 0, None), available[None, :]) * selected[None, :]
    profit = (sales * prices[None, :]).sum(axis=1) - (costs * orders[None, :]).sum(axis=1)

    served = np.zeros_like(cat_demand)
    category_to_position = {category: idx for idx, category in enumerate(categories)}
    for sku_idx, category in enumerate(indexed["category_name"]):
        served[:, category_to_position[str(category)]] += sales[:, sku_idx]
    unmet = np.maximum(cat_demand - served, 0.0)
    normalized_unmet = unmet / np.maximum(cat_demand, 1e-9)
    service_loss = normalized_unmet.mean(axis=1)
    return {
        "sales_by_scenario": sales,
        "profit_by_scenario": profit,
        "unmet_by_scenario_category": unmet,
        "service_loss_by_scenario": service_loss,
        "expected_profit": float(profit.mean()),
        "lower_tail_profit": lower_tail_mean(profit),
        "expected_service_loss": float(service_loss.mean()),
    }


def solve_lexicographic_milp(
    candidates: pd.DataFrame,
    price_grid: pd.DataFrame,
    alternative_demand: np.ndarray,
    category_demand: np.ndarray,
    sku_cost: np.ndarray,
    categories: Sequence[str],
    *,
    assortment_size: int,
    minimum_order: float = MINIMUM_ORDER_KG,
    risk_weight: float = 0.25,
    lower_tail_probability: float = 0.10,
    service_tolerance: float | None = None,
    total_order_upper: float | None = None,
    stage1_reference: Mapping[str, float] | None = None,
    time_limit_seconds: float = 120.0,
) -> dict:
    """Solve service first, then maximize risk-adjusted profit at that service level.

    ``alternative_demand`` has one column per row of ``price_grid``.  SKU costs
    are scenario-specific and charged on ordered (pre-loss) kilograms.
    """

    candidate = candidates.copy().reset_index(drop=True)
    grid = price_grid.copy().reset_index(drop=True)
    candidate["sku_code"] = candidate["sku_code"].astype(str)
    grid["sku_code"] = grid["sku_code"].astype(str)
    categories = [str(category) for category in categories]
    demand_alt = np.asarray(alternative_demand, dtype=float)
    demand_cat = np.asarray(category_demand, dtype=float)
    costs = np.asarray(sku_cost, dtype=float)
    n_i, n_j = len(candidate), len(grid)
    n_w, n_c = demand_cat.shape if demand_cat.ndim == 2 else (0, 0)
    if (
        demand_alt.shape != (n_w, n_j)
        or costs.shape != (n_w, n_i)
        or n_c != len(categories)
    ):
        raise ValueError("MILP input dimensions do not align")
    if not 1 <= assortment_size <= n_i:
        raise ValueError("assortment_size must be between one and the number of candidates")
    if not 0 <= risk_weight <= 1 or not 0 < lower_tail_probability <= 1:
        raise ValueError("risk parameters are outside their valid ranges")
    if total_order_upper is not None and total_order_upper < assortment_size * minimum_order:
        raise ValueError("total order upper bound is below the mandatory minimum orders")
    if not np.isfinite(demand_alt).all() or not np.isfinite(demand_cat).all() or not np.isfinite(costs).all():
        raise ValueError("MILP inputs must be finite")

    sku_position = {code: idx for idx, code in enumerate(candidate["sku_code"])}
    if len(sku_position) != n_i or set(grid["sku_code"]).difference(sku_position):
        raise ValueError("candidate/grid SKU keys are not one-to-one")
    alt_to_sku = np.array([sku_position[code] for code in grid["sku_code"]], dtype=int)
    cat_position = {category: idx for idx, category in enumerate(categories)}
    if set(candidate["category_name"].astype(str)).difference(cat_position):
        raise ValueError("candidate categories are missing from categories")
    sku_to_cat = np.array(
        [cat_position[str(category)] for category in candidate["category_name"]], dtype=int
    )
    alternatives_by_sku = [np.flatnonzero(alt_to_sku == i) for i in range(n_i)]
    if any(len(items) == 0 for items in alternatives_by_sku):
        raise ValueError("every candidate must have at least one price alternative")

    big_m = candidate["big_m_kg"].to_numpy(dtype=float)
    losses = candidate["loss_rate"].to_numpy(dtype=float)
    prices = grid["price_yuan_per_kg"].to_numpy(dtype=float)
    if (
        (big_m < minimum_order).any()
        or (losses < 0).any()
        or (losses >= 1).any()
        or (prices <= 0).any()
    ):
        raise ValueError("invalid big-M, loss, or price values")

    def build_problem(include_tail: bool, service_cap: float | None = None):
        x0 = 0
        y0 = x0 + n_i
        q0 = y0 + n_j
        s0 = q0 + n_i
        u0 = s0 + n_w * n_j
        eta0 = u0 + n_w * n_c
        xi0 = eta0 + (1 if include_tail else 0)
        n_var = xi0 + (n_w if include_tail else 0)

        lower = np.zeros(n_var)
        upper = np.full(n_var, np.inf)
        upper[x0:y0] = 1.0
        upper[y0:q0] = 1.0
        upper[q0:s0] = big_m
        if include_tail:
            lower[eta0] = -np.inf
        integrality = np.zeros(n_var, dtype=np.uint8)
        integrality[x0:y0] = 1
        integrality[y0:q0] = 1

        rows: list[int] = []
        cols: list[int] = []
        values: list[float] = []
        constraint_lower: list[float] = []
        constraint_upper: list[float] = []

        def add(entries: Iterable[tuple[int, float]], low: float, high: float) -> None:
            row = len(constraint_lower)
            for column, value in entries:
                if value != 0:
                    rows.append(row)
                    cols.append(int(column))
                    values.append(float(value))
            constraint_lower.append(float(low))
            constraint_upper.append(float(high))

        add(((x0 + i, 1.0) for i in range(n_i)), assortment_size, assortment_size)
        if total_order_upper is not None:
            add(((q0 + i, 1.0) for i in range(n_i)), -np.inf, float(total_order_upper))
        for i, alternatives in enumerate(alternatives_by_sku):
            add(
                [(y0 + int(j), 1.0) for j in alternatives] + [(x0 + i, -1.0)],
                0.0,
                0.0,
            )
            add([(q0 + i, 1.0), (x0 + i, -minimum_order)], 0.0, np.inf)
            add([(q0 + i, 1.0), (x0 + i, -big_m[i])], -np.inf, 0.0)
        for w in range(n_w):
            for j in range(n_j):
                add(
                    [(s0 + w * n_j + j, 1.0), (y0 + j, -demand_alt[w, j])],
                    -np.inf,
                    0.0,
                )
            for i, alternatives in enumerate(alternatives_by_sku):
                add(
                    [(s0 + w * n_j + int(j), 1.0) for j in alternatives]
                    + [(q0 + i, -(1.0 - losses[i]))],
                    -np.inf,
                    0.0,
                )
            for c in range(n_c):
                category_alternatives = np.flatnonzero(sku_to_cat[alt_to_sku] == c)
                add(
                    [(u0 + w * n_c + c, 1.0)]
                    + [(s0 + w * n_j + int(j), 1.0) for j in category_alternatives],
                    demand_cat[w, c],
                    np.inf,
                )

        service_coefficients = np.zeros(n_var)
        for w in range(n_w):
            for c in range(n_c):
                service_coefficients[u0 + w * n_c + c] = 1.0 / (
                    n_w * n_c * max(demand_cat[w, c], 1e-9)
                )
        if service_cap is not None:
            add(
                ((idx, value) for idx, value in enumerate(service_coefficients) if value),
                -np.inf,
                service_cap,
            )
        if include_tail:
            for w in range(n_w):
                entries = [(xi0 + w, 1.0), (eta0, -1.0)]
                entries.extend((q0 + i, -costs[w, i]) for i in range(n_i))
                entries.extend(
                    (s0 + w * n_j + j, prices[j]) for j in range(n_j)
                )
                add(entries, 0.0, np.inf)

        matrix = coo_matrix((values, (rows, cols)), shape=(len(constraint_lower), n_var)).tocsr()
        objective = service_coefficients.copy()
        if include_tail:
            objective.fill(0.0)
            expected_weight = 1.0 - risk_weight
            objective[q0:s0] = expected_weight * costs.mean(axis=0)
            for w in range(n_w):
                objective[s0 + w * n_j:s0 + (w + 1) * n_j] = (
                    -expected_weight * prices / n_w
                )
            objective[eta0] = -risk_weight
            objective[xi0:xi0 + n_w] = risk_weight / (lower_tail_probability * n_w)
        return {
            "objective": objective,
            "bounds": Bounds(lower, upper),
            "integrality": integrality,
            "constraint": LinearConstraint(
                matrix, np.asarray(constraint_lower), np.asarray(constraint_upper)
            ),
            "offsets": {"x": x0, "y": y0, "q": q0, "s": s0, "u": u0},
            "service_coefficients": service_coefficients,
        }

    options = {"time_limit": float(time_limit_seconds), "mip_rel_gap": 1e-7, "presolve": True}
    if stage1_reference is None:
        stage1_problem = build_problem(False)
        stage1_started = time.perf_counter()
        stage1 = milp(
            stage1_problem["objective"],
            integrality=stage1_problem["integrality"],
            bounds=stage1_problem["bounds"],
            constraints=stage1_problem["constraint"],
            options=options,
        )
        stage1_seconds = time.perf_counter() - stage1_started
        if not stage1.success or stage1.x is None:
            raise RuntimeError(f"stage-1 MILP failed: {stage1.message}")
        stage1_service = float(stage1_problem["service_coefficients"] @ stage1.x)
        if service_tolerance is None:
            u_start = stage1_problem["offsets"]["u"]
            unmet = stage1.x[u_start:u_start + n_w * n_c].reshape(n_w, n_c)
            loss_by_scenario = (unmet / np.maximum(demand_cat, 1e-9)).mean(axis=1)
            tolerance = float(loss_by_scenario.std(ddof=1) / math.sqrt(n_w)) if n_w > 1 else 0.0
        else:
            tolerance = max(0.0, float(service_tolerance))
        stage1_status = int(stage1.status)
        stage1_message = str(stage1.message)
    else:
        required_reference = {"service_loss", "service_tolerance"}
        missing_reference = required_reference.difference(stage1_reference)
        if missing_reference:
            raise ValueError(f"stage1_reference is missing: {sorted(missing_reference)}")
        stage1_service = float(stage1_reference["service_loss"])
        tolerance = float(stage1_reference["service_tolerance"])
        if not np.isfinite([stage1_service, tolerance]).all() or stage1_service < 0 or tolerance < 0:
            raise ValueError("stage1_reference values must be finite and nonnegative")
        stage1_seconds = 0.0
        stage1_status = 0
        stage1_message = "reused identical Stage-1 service optimum"

    stage2_problem = build_problem(True, stage1_service + tolerance + 1e-9)
    stage2_started = time.perf_counter()
    stage2 = milp(
        stage2_problem["objective"],
        integrality=stage2_problem["integrality"],
        bounds=stage2_problem["bounds"],
        constraints=stage2_problem["constraint"],
        options=options,
    )
    stage2_seconds = time.perf_counter() - stage2_started
    if not stage2.success or stage2.x is None:
        raise RuntimeError(f"stage-2 MILP failed: {stage2.message}")
    offsets = stage2_problem["offsets"]
    x_values = stage2.x[offsets["x"]:offsets["y"]]
    y_values = stage2.x[offsets["y"]:offsets["q"]]
    q_values = stage2.x[offsets["q"]:offsets["s"]]
    chosen = grid.loc[y_values > 0.5].copy()
    chosen_price = chosen.set_index("sku_code")["price_yuan_per_kg"].to_dict()
    strategy = candidate[["sku_code", "sku_name", "category_name", "loss_rate"]].copy()
    strategy["selected"] = (x_values > 0.5).astype(int)
    strategy["price_yuan_per_kg"] = strategy["sku_code"].map(chosen_price).fillna(0.0)
    strategy["order_qty_kg"] = np.where(strategy["selected"] == 1, q_values, 0.0)
    stage2_service = float(stage2_problem["service_coefficients"] @ stage2.x)
    return {
        "strategy": strategy,
        "chosen_price_rows": chosen.reset_index(drop=True),
        "stage1_service_loss": stage1_service,
        "stage2_service_loss": stage2_service,
        "service_tolerance": tolerance,
        "stage1_status": stage1_status,
        "stage2_status": int(stage2.status),
        "stage1_message": stage1_message,
        "stage2_message": str(stage2.message),
        "stage2_objective": float(stage2.fun),
        "stage1_seconds": stage1_seconds,
        "stage2_seconds": stage2_seconds,
    }


def load_q2_scenario_bundle() -> dict:
    """Recreate Q2's deterministic 600 correlated scenarios for 2023-07-01."""

    module_path = ROOT / "questions" / "q2" / "code" / "q2_model.py"
    spec = importlib.util.spec_from_file_location("q2_model_for_q3", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Q2 model from {module_path}")
    q2 = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = q2
    spec.loader.exec_module(q2)

    elasticity_table = pd.read_csv(Q2_TABLES / "q2_elasticity_estimates.csv")
    elasticity_map = elasticity_table.set_index("category_name")["elasticity_used"].to_dict()
    frames = q2.prepare_category_frames()
    categories = sorted(frames)
    if set(categories) != set(elasticity_map):
        raise RuntimeError("Q2 elasticity categories do not match Q2 prepared frames")
    forecasts = {
        category: q2.rolling_forecast_category(frames[category], float(elasticity_map[category]), category)
        for category in categories
    }
    demand_residual, cost_residual, scenario_info = q2.build_joint_scenarios(forecasts, categories)
    if demand_residual.shape != (FULL_SCENARIO_COUNT, 7, len(categories)):
        raise RuntimeError(f"unexpected Q2 demand scenario shape: {demand_residual.shape}")

    q2_strategy = pd.read_csv(Q2_TABLES / "q2_daily_strategy.csv")
    q2_strategy["date"] = pd.to_datetime(q2_strategy["date"])
    target_rows = q2_strategy.loc[
        (q2_strategy["date"] == DECISION_DATE)
        & np.isclose(q2_strategy["risk_weight"], RISK_WEIGHT)
    ].copy()
    if len(target_rows) != len(categories) or target_rows["category_name"].nunique() != len(categories):
        raise RuntimeError("Q2 main strategy does not contain one 2023-07-01 row per category")
    target_rows = target_rows.set_index("category_name").loc[categories]
    reference_price = target_rows["price_yuan_per_kg"].to_numpy(dtype=float)
    theta = np.array([float(elasticity_map[category]) for category in categories])
    alpha = np.array([float(forecasts[category].alpha_future[0]) for category in categories])
    base_cost = np.array([float(np.exp(forecasts[category].log_cost_future[0])) for category in categories])
    category_demand = np.maximum(
        0.0,
        np.expm1(
            np.clip(
                alpha[None, :]
                + theta[None, :] * np.log(reference_price)[None, :]
                + demand_residual[:, 0, :],
                -12,
                8,
            )
        ),
    )
    category_cost = np.exp(np.log(base_cost)[None, :] + cost_residual[:, 0, :])
    return {
        "categories": categories,
        "elasticity": theta,
        "reference_price": reference_price,
        "base_cost": base_cost,
        "category_demand": category_demand,
        "category_cost": category_cost,
        "cost_residual": cost_residual[:, 0, :],
        "scenario_info": scenario_info,
        "target_strategy": target_rows.reset_index(),
    }


def _build_alternative_demand(
    share_scenarios: np.ndarray,
    category_demand: np.ndarray,
    candidates: pd.DataFrame,
    price_grid: pd.DataFrame,
    categories: Sequence[str],
    elasticity: np.ndarray,
) -> np.ndarray:
    sku_position = {str(code): idx for idx, code in enumerate(candidates["sku_code"].astype(str))}
    category_position = {str(category): idx for idx, category in enumerate(categories)}
    reference_price = candidates["reference_price_yuan_per_kg"].to_numpy(dtype=float)
    result = np.zeros((share_scenarios.shape[0], len(price_grid)), dtype=float)
    for j, row in enumerate(price_grid.itertuples(index=False)):
        i = sku_position[str(row.sku_code)]
        c = category_position[str(row.category_name)]
        response = (float(row.price_yuan_per_kg) / reference_price[i]) ** float(elasticity[c])
        result[:, j] = share_scenarios[:, i] * category_demand[:, c] * response
    return result


def _chosen_sku_demand(
    strategy: pd.DataFrame,
    candidates: pd.DataFrame,
    price_grid: pd.DataFrame,
    alternative_demand: np.ndarray,
) -> np.ndarray:
    sku_position = {str(code): idx for idx, code in enumerate(candidates["sku_code"].astype(str))}
    result = np.zeros((alternative_demand.shape[0], len(candidates)), dtype=float)
    grid_lookup = {
        (str(row.sku_code), round(float(row.price_yuan_per_kg), 6)): j
        for j, row in enumerate(price_grid.itertuples(index=False))
    }
    for row in strategy.loc[strategy["selected"] == 1].itertuples(index=False):
        key = (str(row.sku_code), round(float(row.price_yuan_per_kg), 6))
        if key not in grid_lookup:
            raise RuntimeError(f"chosen SKU/price is absent from grid: {key}")
        result[:, sku_position[str(row.sku_code)]] = alternative_demand[:, grid_lookup[key]]
    return result


def _add_q1_diagnostics(candidates: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    result = candidates.copy()
    cluster_path = ROOT / "questions" / "q1" / "outputs" / "tables" / "tab_q1_sku_clusters.csv"
    pair_path = ROOT / "questions" / "q1" / "outputs" / "tables" / "tab_q1_all_sku_pair_relationships.csv"
    clusters = pd.read_csv(cluster_path, dtype={"sku_code": str})
    cluster_columns = clusters[["sku_code", "cluster_id", "cluster_name", "peak_month"]]
    result = result.merge(cluster_columns, on="sku_code", how="left", validate="one_to_one")
    result["q1_covered"] = result["cluster_id"].notna().astype(int)
    pairs = pd.read_csv(pair_path, dtype={"source": str, "target": str})
    codes = set(result["sku_code"])
    candidate_pairs = pairs.loc[pairs["source"].isin(codes) & pairs["target"].isin(codes)]
    counts = candidate_pairs["strength_label"].value_counts().to_dict()
    diagnostics = {
        "q1_candidate_sku_coverage": int(result["q1_covered"].sum()),
        "q1_candidate_sku_total": int(len(result)),
        "q1_candidate_pairs_covered": int(len(candidate_pairs)),
        "q1_pair_strength_counts": {str(key): int(value) for key, value in counts.items()},
        "q1_used_in_primary_objective": False,
    }
    return result, diagnostics


def _strategy_metrics(
    strategy: pd.DataFrame,
    candidates: pd.DataFrame,
    price_grid: pd.DataFrame,
    alternative_demand: np.ndarray,
    sku_cost_scenarios: np.ndarray,
    category_demand: np.ndarray,
    categories: Sequence[str],
) -> tuple[dict, np.ndarray, dict]:
    chosen_demand = _chosen_sku_demand(strategy, candidates, price_grid, alternative_demand)
    evaluation = evaluate_strategy(
        strategy,
        candidates["sku_code"].astype(str).tolist(),
        chosen_demand,
        sku_cost_scenarios,
        category_demand,
        categories,
    )
    metric = {
        "selected_sku_count": int(strategy["selected"].sum()),
        "expected_service_loss": float(evaluation["expected_service_loss"]),
        "mean_demand_satisfaction": float(1.0 - evaluation["expected_service_loss"]),
        "expected_profit_yuan": float(evaluation["expected_profit"]),
        "lower10pct_profit_yuan": float(evaluation["lower_tail_profit"]),
        "risk_adjusted_profit_yuan": float(
            (1.0 - RISK_WEIGHT) * evaluation["expected_profit"]
            + RISK_WEIGHT * evaluation["lower_tail_profit"]
        ),
        "total_order_qty_kg": float(strategy["order_qty_kg"].sum()),
    }
    return metric, chosen_demand, evaluation


def solve_sensitivity_variant(
    variant: Mapping[str, float | str],
    candidates: pd.DataFrame,
    price_grid: pd.DataFrame,
    alternative_demand: np.ndarray,
    category_demand: np.ndarray,
    sku_cost_scenarios: np.ndarray,
    categories: Sequence[str],
    representative_indices: np.ndarray,
    *,
    assortment_size: int,
    total_order_upper: float,
    baseline_selected: Iterable[str],
    stage1_reference: Mapping[str, float] | None = None,
) -> dict:
    """Re-solve and fully evaluate one sensitivity configuration."""

    representative = np.asarray(representative_indices, dtype=int)
    risk_weight = float(variant["risk_weight"])
    solved = solve_lexicographic_milp(
        candidates,
        price_grid,
        np.asarray(alternative_demand)[representative],
        np.asarray(category_demand)[representative],
        np.asarray(sku_cost_scenarios)[representative],
        categories,
        assortment_size=assortment_size,
        risk_weight=risk_weight,
        lower_tail_probability=LOWER_TAIL_PROBABILITY,
        service_tolerance=None,
        total_order_upper=float(total_order_upper),
        stage1_reference=stage1_reference,
        time_limit_seconds=180.0,
    )
    metric, chosen_demand, evaluation = _strategy_metrics(
        solved["strategy"],
        candidates,
        price_grid,
        alternative_demand,
        sku_cost_scenarios,
        category_demand,
        categories,
    )
    metric["risk_adjusted_profit_yuan"] = float(
        (1.0 - risk_weight) * metric["expected_profit_yuan"]
        + risk_weight * metric["lower10pct_profit_yuan"]
    )
    selected_strategy = solved["strategy"].loc[solved["strategy"]["selected"] == 1]
    selected_codes = set(selected_strategy["sku_code"].astype(str))
    if len(selected_codes) != assortment_size:
        raise RuntimeError(f"{variant['variant_id']} selected {len(selected_codes)} SKUs")
    if (selected_strategy["order_qty_kg"] < MINIMUM_ORDER_KG - 1e-7).any():
        raise RuntimeError(f"{variant['variant_id']} violates the minimum order")
    if metric["total_order_qty_kg"] > float(total_order_upper) + 1e-6:
        raise RuntimeError(f"{variant['variant_id']} violates its replenishment cap")
    row = {
        "variant_id": str(variant["variant_id"]),
        "parameter_group": str(variant["parameter_group"]),
        "parameter_value": float(variant["parameter_value"]),
        "risk_weight": risk_weight,
        "elasticity_scale": float(variant["elasticity_scale"]),
        "historical_share_weight": float(variant["historical_share_weight"]),
        "order_cap_factor": float(variant["order_cap_factor"]),
        "order_cap_kg": float(total_order_upper),
        **metric,
        "assortment_size": int(assortment_size),
        "selection_jaccard_vs_baseline": selection_jaccard(selected_codes, baseline_selected),
        "optimization_stage1_service_loss": float(solved["stage1_service_loss"]),
        "optimization_stage2_service_loss": float(solved["stage2_service_loss"]),
        "service_tolerance": float(solved["service_tolerance"]),
    }
    if not np.isfinite([value for value in row.values() if isinstance(value, (int, float))]).all():
        raise RuntimeError(f"{variant['variant_id']} produced non-finite metrics")
    return {
        "row": row,
        "strategy": solved["strategy"],
        "chosen_demand": chosen_demand,
        "evaluation": evaluation,
        "solved": solved,
    }


def run_sensitivity_analysis(
    daily: pd.DataFrame,
    candidates: pd.DataFrame,
    price_grid: pd.DataFrame,
    q2_bundle: Mapping[str, object],
    sku_cost_scenarios: np.ndarray,
    representative_indices: np.ndarray,
    q2_total_order_upper: float,
    base_solution: Mapping[str, object],
    base_share_scenarios: np.ndarray,
    base_alternative_demand: np.ndarray,
) -> tuple[pd.DataFrame, dict[str, dict]]:
    """Re-solve the approved nine one-factor-at-a-time sensitivity variants."""

    categories = list(q2_bundle["categories"])
    category_demand = np.asarray(q2_bundle["category_demand"], dtype=float)
    elasticity = np.asarray(q2_bundle["elasticity"], dtype=float)
    baseline_strategy = base_solution["solved"]["strategy"]
    baseline_selected = set(
        baseline_strategy.loc[baseline_strategy["selected"] == 1, "sku_code"].astype(str)
    )
    rows: list[dict] = []
    details: dict[str, dict] = {}
    variants = build_sensitivity_variants()
    for variant in variants:
        variant_id = str(variant["variant_id"])
        if variant_id == "baseline":
            metric = dict(base_solution["metric"])
            solved = base_solution["solved"]
            row = {
                **variant,
                "order_cap_kg": float(q2_total_order_upper),
                **metric,
                "selection_jaccard_vs_baseline": 1.0,
                "optimization_stage1_service_loss": float(solved["stage1_service_loss"]),
                "optimization_stage2_service_loss": float(solved["stage2_service_loss"]),
                "service_tolerance": float(solved["service_tolerance"]),
            }
            result = {
                "row": row,
                "strategy": baseline_strategy,
                "chosen_demand": base_solution["chosen_demand"],
                "evaluation": base_solution["evaluation"],
                "solved": solved,
            }
        else:
            share_weight = float(variant["historical_share_weight"])
            if math.isclose(share_weight, 0.50):
                share_scenarios = base_share_scenarios
            else:
                share_scenarios = build_share_scenarios(
                    daily,
                    candidates,
                    FULL_SCENARIO_COUNT,
                    DECISION_DATE,
                    historical_weight=share_weight,
                )
            alternative_demand = _build_alternative_demand(
                share_scenarios,
                category_demand,
                candidates,
                price_grid,
                categories,
                elasticity * float(variant["elasticity_scale"]),
            )
            candidate_variant = candidates.copy()
            maximum_sku_demand = np.zeros((FULL_SCENARIO_COUNT, len(candidates)), dtype=float)
            for i, code in enumerate(candidate_variant["sku_code"].astype(str)):
                alternatives = np.flatnonzero(price_grid["sku_code"].astype(str).to_numpy() == code)
                maximum_sku_demand[:, i] = alternative_demand[:, alternatives].max(axis=1)
            candidate_variant["big_m_kg"] = compute_big_m(
                maximum_sku_demand,
                candidate_variant["loss_rate"].to_numpy(dtype=float),
            )
            result = solve_sensitivity_variant(
                variant,
                candidate_variant,
                price_grid,
                alternative_demand,
                category_demand,
                sku_cost_scenarios,
                categories,
                representative_indices,
                assortment_size=33,
                total_order_upper=q2_total_order_upper * float(variant["order_cap_factor"]),
                baseline_selected=baseline_selected,
                stage1_reference=(
                    {
                        "service_loss": float(base_solution["solved"]["stage1_service_loss"]),
                        "service_tolerance": float(base_solution["solved"]["service_tolerance"]),
                    }
                    if str(variant["parameter_group"]) == "risk_weight"
                    else None
                ),
            )
        rows.append(dict(result["row"]))
        details[variant_id] = result
        print(
            f"sensitivity {variant_id}: service="
            f"{result['row']['mean_demand_satisfaction']:.4f}, "
            f"expected_profit={result['row']['expected_profit_yuan']:.2f}, "
            f"solve_seconds={result['solved']['stage1_seconds'] + result['solved']['stage2_seconds']:.1f}"
        )
    table = pd.DataFrame(rows)
    if len(table) != 9 or table["variant_id"].nunique() != 9:
        raise RuntimeError("sensitivity analysis did not produce nine unique variants")
    return table, details


def build_model_validation_table(
    main_evaluation: Mapping[str, object],
    representative_evaluation: Mapping[str, object],
    baseline_evaluation: Mapping[str, object],
) -> tuple[pd.DataFrame, dict]:
    """Build generalization, fold-stability, and same-scenario baseline diagnostics."""

    full_loss = float(main_evaluation["expected_service_loss"])
    representative_loss = float(representative_evaluation["expected_service_loss"])
    gap = full_loss - representative_loss
    folds = summarize_scenario_folds(
        np.asarray(main_evaluation["service_loss_by_scenario"], dtype=float),
        np.asarray(main_evaluation["profit_by_scenario"], dtype=float),
        folds=6,
    )
    service_std = float(folds["mean_demand_satisfaction"].std(ddof=1))
    rows = [
        {
            "validation_type": "representative_generalization",
            "item": "service_loss_full_minus_representative",
            "fold": np.nan,
            "scenario_count": 600,
            "mean_demand_satisfaction": 1.0 - full_loss,
            "expected_profit_yuan": float(main_evaluation["expected_profit"]),
            "lower10pct_profit_yuan": float(main_evaluation["lower_tail_profit"]),
            "value": full_loss,
            "reference_value": representative_loss,
            "absolute_difference": abs(gap),
            "threshold": 0.03,
            "passed": abs(gap) <= 0.03,
        }
    ]
    for row in folds.itertuples(index=False):
        rows.append(
            {
                "validation_type": "scenario_fold",
                "item": f"fold_{int(row.fold)}",
                "fold": int(row.fold),
                "scenario_count": int(row.scenario_count),
                "mean_demand_satisfaction": float(row.mean_demand_satisfaction),
                "expected_profit_yuan": float(row.expected_profit_yuan),
                "lower10pct_profit_yuan": float(row.lower10pct_profit_yuan),
                "value": np.nan,
                "reference_value": np.nan,
                "absolute_difference": np.nan,
                "threshold": np.nan,
                "passed": True,
            }
        )
    rows.extend(
        [
            {
                "validation_type": "fold_stability",
                "item": "service_satisfaction_standard_deviation",
                "fold": np.nan,
                "scenario_count": 600,
                "mean_demand_satisfaction": float(folds["mean_demand_satisfaction"].mean()),
                "expected_profit_yuan": float(folds["expected_profit_yuan"].mean()),
                "lower10pct_profit_yuan": float(folds["lower10pct_profit_yuan"].mean()),
                "value": service_std,
                "reference_value": 0.0,
                "absolute_difference": service_std,
                "threshold": 0.05,
                "passed": service_std <= 0.05,
            },
            {
                "validation_type": "baseline_comparison",
                "item": "mean_demand_satisfaction_improvement",
                "fold": np.nan,
                "scenario_count": 600,
                "mean_demand_satisfaction": 1.0 - full_loss,
                "expected_profit_yuan": float(main_evaluation["expected_profit"]),
                "lower10pct_profit_yuan": float(main_evaluation["lower_tail_profit"]),
                "value": 1.0 - full_loss,
                "reference_value": 1.0 - float(baseline_evaluation["expected_service_loss"]),
                "absolute_difference": np.nan,
                "threshold": 0.0,
                "passed": full_loss < float(baseline_evaluation["expected_service_loss"]),
            },
            {
                "validation_type": "baseline_comparison",
                "item": "expected_profit_improvement_yuan",
                "fold": np.nan,
                "scenario_count": 600,
                "mean_demand_satisfaction": 1.0 - full_loss,
                "expected_profit_yuan": float(main_evaluation["expected_profit"]),
                "lower10pct_profit_yuan": float(main_evaluation["lower_tail_profit"]),
                "value": float(main_evaluation["expected_profit"]),
                "reference_value": float(baseline_evaluation["expected_profit"]),
                "absolute_difference": np.nan,
                "threshold": 0.0,
                "passed": float(main_evaluation["expected_profit"]) > float(baseline_evaluation["expected_profit"]),
            },
            {
                "validation_type": "baseline_comparison",
                "item": "lower10pct_profit_change_yuan",
                "fold": np.nan,
                "scenario_count": 600,
                "mean_demand_satisfaction": 1.0 - full_loss,
                "expected_profit_yuan": float(main_evaluation["expected_profit"]),
                "lower10pct_profit_yuan": float(main_evaluation["lower_tail_profit"]),
                "value": float(main_evaluation["lower_tail_profit"]),
                "reference_value": float(baseline_evaluation["lower_tail_profit"]),
                "absolute_difference": np.nan,
                "threshold": np.nan,
                "passed": True,
            },
        ]
    )
    table = pd.DataFrame(rows)
    summary = {
        "representative_service_loss": representative_loss,
        "full_service_loss": full_loss,
        "signed_service_loss_gap": gap,
        "absolute_service_loss_gap": abs(gap),
        "generalization_threshold": 0.03,
        "fold_count": 6,
        "fold_scenario_count": 100,
        "fold_service_satisfaction_mean": float(folds["mean_demand_satisfaction"].mean()),
        "fold_service_satisfaction_std": service_std,
        "fold_service_satisfaction_min": float(folds["mean_demand_satisfaction"].min()),
        "fold_service_satisfaction_max": float(folds["mean_demand_satisfaction"].max()),
        "fold_expected_profit_std_yuan": float(folds["expected_profit_yuan"].std(ddof=1)),
        "all_required_checks_passed": bool(table.loc[table["threshold"].notna(), "passed"].all()),
    }
    return table, summary


def compute_base_model_signature() -> str:
    """Fingerprint exact base-model inputs and core function implementations."""

    digest = hashlib.sha256()
    digest.update(BASE_MODEL_VERSION.encode("utf-8"))
    digest.update(
        json.dumps(
            {
                "decision_date": str(DECISION_DATE.date()),
                "candidate_start": str(CANDIDATE_START.date()),
                "candidate_end": str(CANDIDATE_END.date()),
                "full_scenarios": FULL_SCENARIO_COUNT,
                "optimization_scenarios": OPTIMIZATION_SCENARIO_COUNT,
                "risk_weight": RISK_WEIGHT,
                "lower_tail_probability": LOWER_TAIL_PROBABILITY,
                "minimum_order_kg": MINIMUM_ORDER_KG,
            },
            sort_keys=True,
        ).encode("utf-8")
    )
    for function in (
        identify_candidates,
        estimate_dynamic_shares,
        build_share_scenarios,
        build_price_grid,
        _build_alternative_demand,
        compute_big_m,
        solve_lexicographic_milp,
        load_q2_scenario_bundle,
    ):
        digest.update(inspect.getsource(function).encode("utf-8"))
    for path in (
        DATA / "processed_daily_sku.csv",
        ROOT / "questions" / "q2" / "code" / "q2_model.py",
        Q2_TABLES / "q2_elasticity_estimates.csv",
        Q2_TABLES / "q2_decision_bounds.csv",
        Q2_TABLES / "q2_daily_strategy.csv",
    ):
        digest.update(str(path.relative_to(ROOT)).encode("utf-8"))
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def reconstruct_cached_base_solution(
    candidates: pd.DataFrame,
    cached_selected_strategy: pd.DataFrame,
    cached_frontier: pd.DataFrame,
    price_grid: pd.DataFrame,
    alternative_demand: np.ndarray,
    sku_cost_scenarios: np.ndarray,
    category_demand: np.ndarray,
    categories: Sequence[str],
    *,
    total_order_upper: float,
    tolerance: float = 1e-6,
) -> dict:
    """Rebuild and verify the cached K=33 base solution on current scenarios."""

    candidate = candidates.copy().reset_index(drop=True)
    candidate["sku_code"] = candidate["sku_code"].astype(str)
    cached = cached_selected_strategy.copy()
    cached["sku_code"] = cached["sku_code"].astype(str)
    if cached["sku_code"].duplicated().any() or not set(cached["sku_code"]).issubset(set(candidate["sku_code"])):
        raise ValueError("cached strategy contains duplicate or non-candidate SKU codes")
    frontier = cached_frontier.copy()
    base_rows = frontier.loc[frontier["assortment_size"].astype(int) == 33]
    if len(base_rows) != 1 or len(cached) != 33:
        raise ValueError("cached base outputs must contain one K=33 row and 33 selected SKUs")
    base_row = base_rows.iloc[0]
    strategy = candidate[["sku_code", "sku_name", "category_name", "loss_rate"]].copy()
    strategy["selected"] = 0
    strategy["price_yuan_per_kg"] = 0.0
    strategy["order_qty_kg"] = 0.0
    cached_map = cached.set_index("sku_code")
    selected_mask = strategy["sku_code"].isin(cached_map.index)
    strategy.loc[selected_mask, "selected"] = 1
    strategy.loc[selected_mask, "price_yuan_per_kg"] = strategy.loc[selected_mask, "sku_code"].map(
        cached_map["price_yuan_per_kg"]
    )
    strategy.loc[selected_mask, "order_qty_kg"] = strategy.loc[selected_mask, "sku_code"].map(
        cached_map["order_qty_kg"]
    )
    if strategy["order_qty_kg"].sum() > total_order_upper + tolerance:
        raise ValueError("cached base solution exceeds the current Q2 replenishment cap")
    if (strategy.loc[selected_mask, "order_qty_kg"] < MINIMUM_ORDER_KG - tolerance).any():
        raise ValueError("cached base solution violates the minimum order")
    grid_keys = set(
        zip(price_grid["sku_code"].astype(str), np.round(price_grid["price_yuan_per_kg"], 6))
    )
    selected_keys = set(
        zip(
            strategy.loc[selected_mask, "sku_code"],
            np.round(strategy.loc[selected_mask, "price_yuan_per_kg"], 6),
        )
    )
    if not selected_keys.issubset(grid_keys):
        raise ValueError("cached base solution contains prices outside the current grid")
    metric, chosen_demand, evaluation = _strategy_metrics(
        strategy,
        candidate,
        price_grid,
        alternative_demand,
        sku_cost_scenarios,
        category_demand,
        categories,
    )
    comparisons = {
        "expected_service_loss": metric["expected_service_loss"],
        "mean_demand_satisfaction": metric["mean_demand_satisfaction"],
        "expected_profit_yuan": metric["expected_profit_yuan"],
        "lower10pct_profit_yuan": metric["lower10pct_profit_yuan"],
        "total_order_qty_kg": metric["total_order_qty_kg"],
    }
    for column, current_value in comparisons.items():
        if not math.isclose(float(base_row[column]), float(current_value), abs_tol=tolerance, rel_tol=1e-9):
            raise ValueError(
                f"cached base metric {column} is stale: stored={base_row[column]}, current={current_value}"
            )
    metric.update(
        {
            "assortment_size": 33,
            "optimization_stage1_service_loss": float(base_row["optimization_stage1_service_loss"]),
            "optimization_stage2_service_loss": float(base_row["optimization_stage2_service_loss"]),
            "service_tolerance": float(base_row["service_tolerance"]),
        }
    )
    solved = {
        "strategy": strategy,
        "stage1_service_loss": float(base_row["optimization_stage1_service_loss"]),
        "stage2_service_loss": float(base_row["optimization_stage2_service_loss"]),
        "service_tolerance": float(base_row["service_tolerance"]),
        "stage1_status": 0,
        "stage2_status": 0,
        "stage1_message": "reused verified base frontier",
        "stage2_message": "reused verified base frontier",
        "stage2_objective": np.nan,
        "stage1_seconds": 0.0,
        "stage2_seconds": 0.0,
    }
    return {
        "solved": solved,
        "chosen_demand": chosen_demand,
        "evaluation": evaluation,
        "metric": metric,
    }


def run_real_pipeline(*, reuse_base: bool = True) -> dict:
    """Run the complete Q3 workflow and write validated intermediate outputs."""

    TABLES.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    daily = pd.read_csv(DATA / "processed_daily_sku.csv", dtype={"sku_code": str, "category_code": str})
    daily["date"] = pd.to_datetime(daily["date"])
    candidates = identify_candidates(daily, CANDIDATE_START, CANDIDATE_END)
    if len(candidates) != 49:
        raise RuntimeError(f"expected 49 positive-sale Q3 candidates, found {len(candidates)}")
    if candidates[["sku_code", "sku_name", "category_name"]].isna().any().any():
        raise RuntimeError("candidate identity/category join contains missing values")

    q2 = load_q2_scenario_bundle()
    categories = q2["categories"]
    if set(candidates["category_name"]) != set(categories):
        raise RuntimeError("Q3 candidate categories do not match Q2 categories")
    category_position = {category: idx for idx, category in enumerate(categories)}
    q2_total_order_upper = float(q2["target_strategy"]["replenishment_kg"].sum())

    week = daily.loc[daily["date"].between(CANDIDATE_START, CANDIDATE_END)].copy()
    positive_week = week.loc[week["gross_sales_qty"] > 0]
    recent_category_cost = (
        positive_week.assign(weighted_cost=lambda x: x["gross_sales_qty"] * x["wholesale_price"])
        .groupby("category_name", observed=True)
        .agg(weighted_cost=("weighted_cost", "sum"), quantity=("gross_sales_qty", "sum"))
    )
    recent_category_cost["recent_category_cost"] = recent_category_cost["weighted_cost"] / recent_category_cost["quantity"]
    latest_cost = (
        week.loc[week["sku_code"].isin(candidates["sku_code"]) & week["wholesale_price"].notna()]
        .sort_values(["sku_code", "date"])
        .groupby("sku_code", observed=True)
        .tail(1)
        .set_index("sku_code")["wholesale_price"]
    )
    candidates["latest_wholesale_price_yuan_per_kg"] = candidates["sku_code"].map(latest_cost)
    candidates["q2_category_cost_yuan_per_kg"] = candidates["category_name"].map(
        {category: q2["base_cost"][idx] for category, idx in category_position.items()}
    )
    candidates["recent_category_cost_yuan_per_kg"] = candidates["category_name"].map(
        recent_category_cost["recent_category_cost"]
    )
    candidates["predicted_cost_yuan_per_kg"] = (
        candidates["latest_wholesale_price_yuan_per_kg"]
        * candidates["q2_category_cost_yuan_per_kg"]
        / candidates["recent_category_cost_yuan_per_kg"]
    )
    if not np.isfinite(candidates["predicted_cost_yuan_per_kg"]).all() or (candidates["predicted_cost_yuan_per_kg"] <= 0).any():
        raise RuntimeError("SKU cost scaling produced missing or nonpositive costs")

    share_table = estimate_dynamic_shares(daily, candidates, DECISION_DATE)
    if share_table["eb_share"].isna().any():
        raise RuntimeError("dynamic share estimation produced missing values")
    share_sums = share_table.groupby("category_name", observed=True)["eb_share"].sum()
    if not np.allclose(share_sums.to_numpy(), 1.0, atol=1e-10):
        raise RuntimeError("dynamic SKU shares do not sum to one within category")
    share_scenarios = build_share_scenarios(daily, share_table, FULL_SCENARIO_COUNT)
    for category, indices in share_table.groupby("category_name", observed=True).groups.items():
        if not np.allclose(share_scenarios[:, list(indices)].sum(axis=1), 1.0, atol=1e-10):
            raise RuntimeError(f"scenario shares do not sum to one for {category}")

    bounds = pd.read_csv(Q2_TABLES / "q2_decision_bounds.csv")
    price_history = daily.loc[
        daily["date"].between(DECISION_DATE - pd.Timedelta(days=365), DECISION_DATE - pd.Timedelta(days=1))
    ]
    price_grid = build_price_grid(price_history, share_table, bounds)
    if set(price_grid["sku_code"]) != set(share_table["sku_code"]):
        raise RuntimeError("not every candidate received a price grid")

    alternative_demand = _build_alternative_demand(
        share_scenarios,
        q2["category_demand"],
        share_table,
        price_grid,
        categories,
        q2["elasticity"],
    )
    sku_cost_scenarios = np.zeros((FULL_SCENARIO_COUNT, len(share_table)), dtype=float)
    for i, row in enumerate(share_table.itertuples(index=False)):
        c = category_position[str(row.category_name)]
        sku_cost_scenarios[:, i] = float(row.predicted_cost_yuan_per_kg) * np.exp(q2["cost_residual"][:, c])
    alt_to_sku = {code: np.flatnonzero(price_grid["sku_code"].to_numpy() == code) for code in share_table["sku_code"]}
    maximum_sku_demand = np.column_stack(
        [alternative_demand[:, alt_to_sku[code]].max(axis=1) for code in share_table["sku_code"]]
    )
    share_table["big_m_kg"] = compute_big_m(maximum_sku_demand, share_table["loss_rate"].to_numpy(dtype=float))

    representative = select_representative_scenarios(q2["category_demand"], OPTIMIZATION_SCENARIO_COUNT)
    base_signature = compute_base_model_signature()
    base_frontier_reused = False
    solutions: dict[int, dict] = {}
    frontier_path = TABLES / "q3_k_frontier.csv"
    cached_strategy_path = TABLES / "q3_daily_strategy.csv"
    cached_summary_path = RESULTS / "q3_summary.json"
    if reuse_base and frontier_path.exists() and cached_strategy_path.exists():
        cache_signature_matches = True
        if cached_summary_path.exists():
            cached_summary = json.loads(cached_summary_path.read_text(encoding="utf-8"))
            stored_signature = cached_summary.get("base_model_signature")
            cache_signature_matches = stored_signature in (None, base_signature)
        if cache_signature_matches:
            try:
                frontier = pd.read_csv(frontier_path)
                final = reconstruct_cached_base_solution(
                    share_table,
                    pd.read_csv(cached_strategy_path, dtype={"sku_code": str}),
                    frontier,
                    price_grid,
                    alternative_demand,
                    sku_cost_scenarios,
                    q2["category_demand"],
                    categories,
                    total_order_upper=q2_total_order_upper,
                )
                solutions[33] = final
                base_frontier_reused = True
                print("base frontier cache: verified hit (K=27..33 MILPs skipped)")
            except (ValueError, KeyError, pd.errors.ParserError) as error:
                print(f"base frontier cache: rejected ({error}); recomputing")
    if not base_frontier_reused:
        frontier_rows: list[dict] = []
        for assortment_size in range(27, 34):
            solved = solve_lexicographic_milp(
                share_table,
                price_grid,
                alternative_demand[representative],
                q2["category_demand"][representative],
                sku_cost_scenarios[representative],
                categories,
                assortment_size=assortment_size,
                risk_weight=RISK_WEIGHT,
                lower_tail_probability=LOWER_TAIL_PROBABILITY,
                service_tolerance=None,
                total_order_upper=q2_total_order_upper,
                time_limit_seconds=180.0,
            )
            metric, chosen_demand, evaluation = _strategy_metrics(
                solved["strategy"], share_table, price_grid, alternative_demand,
                sku_cost_scenarios, q2["category_demand"], categories,
            )
            metric.update(
                {
                    "assortment_size": assortment_size,
                    "optimization_stage1_service_loss": solved["stage1_service_loss"],
                    "optimization_stage2_service_loss": solved["stage2_service_loss"],
                    "service_tolerance": solved["service_tolerance"],
                }
            )
            frontier_rows.append(metric)
            solutions[assortment_size] = {
                "solved": solved,
                "chosen_demand": chosen_demand,
                "evaluation": evaluation,
                "metric": metric,
            }
            print(
                f"K={assortment_size}: service={metric['mean_demand_satisfaction']:.4f}, "
                f"expected_profit={metric['expected_profit_yuan']:.2f}, "
                f"stage1_seconds={solved['stage1_seconds']:.1f}, stage2_seconds={solved['stage2_seconds']:.1f}"
            )
        frontier = pd.DataFrame(frontier_rows).sort_values("assortment_size")
    best_service = float(frontier["expected_service_loss"].min())
    eligible = frontier.loc[frontier["expected_service_loss"] <= best_service + 1e-8]
    final_k = int(eligible.sort_values(["risk_adjusted_profit_yuan", "assortment_size"], ascending=[False, True]).iloc[0]["assortment_size"])
    if final_k != 33:
        raise RuntimeError(f"approved sensitivity design expects the service-first main solution at K=33, got K={final_k}")
    final = solutions[final_k]
    full_strategy = final["solved"]["strategy"].copy()
    full_strategy = full_strategy.merge(
        share_table.drop(columns=["sku_name", "category_name", "loss_rate"]),
        on="sku_code",
        how="left",
        validate="one_to_one",
    )

    # Transparent operational baseline: top-K recent sellers, median feasible price, recent daily order.
    baseline = share_table[["sku_code", "sku_name", "category_name", "loss_rate"]].copy()
    top_codes = set(
        share_table.nlargest(final_k, ["recent_sales_qty_kg", "eb_share"])["sku_code"]
    )
    baseline["selected"] = baseline["sku_code"].isin(top_codes).astype(int)
    median_prices = price_grid.groupby("sku_code", observed=True)["price_yuan_per_kg"].median()
    baseline["price_yuan_per_kg"] = baseline["sku_code"].map(median_prices)
    baseline["order_qty_kg"] = np.where(
        baseline["selected"] == 1,
        np.maximum(
            MINIMUM_ORDER_KG,
            share_table["recent_sales_qty_kg"].to_numpy(dtype=float) / 7.0
            / (1.0 - share_table["loss_rate"].to_numpy(dtype=float)),
        ),
        0.0,
    )
    # Map median prices to an actual discrete alternative.
    for idx, row in baseline.loc[baseline["selected"] == 1].iterrows():
        sku_grid = price_grid.loc[price_grid["sku_code"] == row["sku_code"]]
        nearest = (sku_grid["price_yuan_per_kg"] - row["price_yuan_per_kg"]).abs().idxmin()
        baseline.loc[idx, "price_yuan_per_kg"] = price_grid.loc[nearest, "price_yuan_per_kg"]
    baseline_metric, _, baseline_evaluation = _strategy_metrics(
        baseline, share_table, price_grid, alternative_demand, sku_cost_scenarios,
        q2["category_demand"], categories,
    )

    _, _, representative_evaluation = _strategy_metrics(
        final["solved"]["strategy"],
        share_table,
        price_grid,
        alternative_demand[representative],
        sku_cost_scenarios[representative],
        q2["category_demand"][representative],
        categories,
    )
    sensitivity, sensitivity_details = run_sensitivity_analysis(
        daily,
        share_table,
        price_grid,
        q2,
        sku_cost_scenarios,
        representative,
        q2_total_order_upper,
        solutions[33],
        share_scenarios,
        alternative_demand,
    )
    model_validation, model_validation_summary = build_model_validation_table(
        final["evaluation"], representative_evaluation, baseline_evaluation
    )
    if not model_validation_summary["all_required_checks_passed"]:
        raise RuntimeError("Q3 representative-scenario or fold-stability validation failed")

    evaluation = final["evaluation"]
    chosen_demand = final["chosen_demand"]
    sales = evaluation["sales_by_scenario"]
    selected_strategy = full_strategy.loc[full_strategy["selected"] == 1].copy()
    selected_indices = [share_table.index[share_table["sku_code"] == code][0] for code in selected_strategy["sku_code"]]
    selected_strategy["date"] = str(DECISION_DATE.date())
    selected_strategy["markup_rate"] = (
        selected_strategy["price_yuan_per_kg"] / selected_strategy["predicted_cost_yuan_per_kg"] - 1.0
    )
    selected_strategy["expected_demand_kg"] = chosen_demand[:, selected_indices].mean(axis=0)
    selected_strategy["expected_sales_kg"] = sales[:, selected_indices].mean(axis=0)
    selected_strategy["expected_unsold_or_loss_kg"] = (
        selected_strategy["order_qty_kg"].to_numpy() - selected_strategy["expected_sales_kg"].to_numpy()
    )
    selected_strategy["stockout_probability"] = np.mean(
        chosen_demand[:, selected_indices]
        > selected_strategy["order_qty_kg"].to_numpy()[None, :]
        * (1.0 - selected_strategy["loss_rate"].to_numpy()[None, :]),
        axis=0,
    )
    contribution = (
        sales[:, selected_indices] * selected_strategy["price_yuan_per_kg"].to_numpy()[None, :]
        - sku_cost_scenarios[:, selected_indices] * selected_strategy["order_qty_kg"].to_numpy()[None, :]
    )
    selected_strategy["expected_profit_yuan"] = contribution.mean(axis=0)
    selected_strategy["lower10pct_profit_yuan"] = [
        lower_tail_mean(contribution[:, j], LOWER_TAIL_PROBABILITY)
        for j in range(contribution.shape[1])
    ]
    selected_strategy = selected_strategy.sort_values(
        ["category_name", "expected_sales_kg"], ascending=[True, False]
    )

    category_rows = []
    for c, category in enumerate(categories):
        indices = np.flatnonzero(share_table["category_name"].to_numpy() == category)
        selected_mask = full_strategy["selected"].to_numpy(dtype=bool)[indices]
        category_sales = sales[:, indices].sum(axis=1)
        category_unmet = evaluation["unmet_by_scenario_category"][:, c]
        category_profit = (
            sales[:, indices] * full_strategy.loc[indices, "price_yuan_per_kg"].to_numpy()[None, :]
            - sku_cost_scenarios[:, indices] * full_strategy.loc[indices, "order_qty_kg"].to_numpy()[None, :]
        ).sum(axis=1)
        category_rows.append(
            {
                "category_name": category,
                "candidate_sku_count": int(len(indices)),
                "selected_sku_count": int(selected_mask.sum()),
                "expected_category_demand_kg": float(q2["category_demand"][:, c].mean()),
                "expected_sales_kg": float(category_sales.mean()),
                "expected_unmet_kg": float(category_unmet.mean()),
                "mean_demand_satisfaction": float(
                    1.0 - np.mean(category_unmet / np.maximum(q2["category_demand"][:, c], 1e-9))
                ),
                "order_qty_kg": float(full_strategy.loc[indices, "order_qty_kg"].sum()),
                "expected_profit_yuan": float(category_profit.mean()),
            }
        )
    category_summary = pd.DataFrame(category_rows)

    diagnostics, q1_info = _add_q1_diagnostics(share_table)
    comparison = pd.DataFrame(
        [
            {"model": "recent_sales_baseline", **baseline_metric},
            {"model": "lexicographic_scenario_milp", **final["metric"]},
        ]
    )
    summary = {
        "model": "dynamic SKU empirical-Bayes shares + Q2 category response/scenarios + lexicographic scenario MILP",
        "decision_date": str(DECISION_DATE.date()),
        "candidate_window": [str(CANDIDATE_START.date()), str(CANDIDATE_END.date())],
        "candidate_sku_count": int(len(share_table)),
        "selected_sku_count": final_k,
        "optimization_scenario_count": OPTIMIZATION_SCENARIO_COUNT,
        "evaluation_scenario_count": FULL_SCENARIO_COUNT,
        "risk_weight": RISK_WEIGHT,
        "lower_tail_probability": LOWER_TAIL_PROBABILITY,
        "q2_total_replenishment_upper_kg": q2_total_order_upper,
        "base_model_signature": base_signature,
        "base_frontier_reused": base_frontier_reused,
        "main_strategy": final["metric"],
        "baseline": baseline_metric,
        "improvement_vs_baseline": {
            "demand_satisfaction_percentage_points": 100.0 * (
                final["metric"]["mean_demand_satisfaction"] - baseline_metric["mean_demand_satisfaction"]
            ),
            "expected_profit_yuan": final["metric"]["expected_profit_yuan"] - baseline_metric["expected_profit_yuan"],
            "lower10pct_profit_yuan": final["metric"]["lower10pct_profit_yuan"] - baseline_metric["lower10pct_profit_yuan"],
        },
        "q2_scenario": q2["scenario_info"],
        "q1_diagnostics": q1_info,
        "model_validation": model_validation_summary,
        "sensitivity": {
            "variant_count": int(len(sensitivity)),
            "minimum_selection_jaccard": float(sensitivity["selection_jaccard_vs_baseline"].min()),
            "service_satisfaction_range": [
                float(sensitivity["mean_demand_satisfaction"].min()),
                float(sensitivity["mean_demand_satisfaction"].max()),
            ],
            "expected_profit_range_yuan": [
                float(sensitivity["expected_profit_yuan"].min()),
                float(sensitivity["expected_profit_yuan"].max()),
            ],
            "lower10pct_profit_range_yuan": [
                float(sensitivity["lower10pct_profit_yuan"].min()),
                float(sensitivity["lower10pct_profit_yuan"].max()),
            ],
        },
    }

    diagnostics.to_csv(TABLES / "q3_candidate_diagnostics.csv", index=False, encoding="utf-8-sig")
    price_grid.to_csv(TABLES / "q3_price_grid.csv", index=False, encoding="utf-8-sig")
    frontier.to_csv(TABLES / "q3_k_frontier.csv", index=False, encoding="utf-8-sig")
    selected_strategy.to_csv(TABLES / "q3_daily_strategy.csv", index=False, encoding="utf-8-sig")
    category_summary.to_csv(TABLES / "q3_category_summary.csv", index=False, encoding="utf-8-sig")
    comparison.to_csv(TABLES / "q3_model_comparison.csv", index=False, encoding="utf-8-sig")
    sensitivity.to_csv(TABLES / "q3_sensitivity_analysis.csv", index=False, encoding="utf-8-sig")
    model_validation.to_csv(TABLES / "q3_model_validation.csv", index=False, encoding="utf-8-sig")
    with (RESULTS / "q3_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force-base",
        action="store_true",
        help="Re-solve the K=27..33 base frontier even when current outputs verify exactly.",
    )
    arguments = parser.parse_args()
    run_real_pipeline(reuse_base=not arguments.force_base)
