"""Question 2: category-level pricing and replenishment under uncertainty.

The implementation follows a practical five-layer pipeline:
1. cross-fitted partially-linear price elasticity estimation;
2. leakage-free aligned-lag demand and wholesale-cost forecasting;
3. joint 7-day moving-block residual scenarios across all six categories;
4. per-day mean/lower-CVaR optimization of cost-plus markups and replenishment;
5. rolling-origin, scenario, constraint, sensitivity, and optimizer checks.

All source workbooks remain read-only. Outputs are written under questions/q2/outputs.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import LinearConstraint, differential_evolution, minimize
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit


ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "processed" / "processed_daily_category.csv"
OUT = ROOT / "questions" / "q2" / "outputs"
TABLES = OUT / "tables"
RESULTS = OUT / "results"

SEED = 20230907
FORECAST_START = pd.Timestamp("2023-07-01")
FORECAST_DATES = pd.date_range(FORECAST_START, periods=7, freq="D")
SCENARIO_COUNT = 600
BLOCK_LENGTH = 7
LOWER_TAIL_PROB = 0.10
MAIN_RISK_WEIGHT = 0.25
RISK_WEIGHTS = (0.00, MAIN_RISK_WEIGHT, 0.50)
ELASTICITY_BOUNDS = (-3.0, -0.05)


@dataclass
class CategoryForecast:
    category: str
    alpha_future: np.ndarray
    log_cost_future: np.ndarray
    demand_residual: pd.Series
    cost_residual: pd.Series
    demand_metrics: dict[str, float]
    cost_metrics: dict[str, float]


def hgb_model(seed: int = SEED) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        learning_rate=0.045,
        max_iter=300,
        max_leaf_nodes=15,
        min_samples_leaf=20,
        l2_regularization=1.0,
        random_state=seed,
    )


def wape(y: np.ndarray, yhat: np.ndarray) -> float:
    denominator = float(np.sum(np.abs(y)))
    return float(np.sum(np.abs(y - yhat)) / denominator) if denominator > 0 else float("nan")


def prepare_category_frames() -> dict[str, pd.DataFrame]:
    raw = pd.read_csv(DATA)
    raw["date"] = pd.to_datetime(raw["date"])
    last = raw["date"].max()
    all_dates = pd.date_range(raw["date"].min(), FORECAST_DATES[-1], freq="D")
    frames: dict[str, pd.DataFrame] = {}
    for category, part in raw.groupby("category_name", sort=True):
        part = part.sort_values("date").set_index("date").reindex(all_dates)
        part.index.name = "date"
        part["category_name"] = category
        part["is_history"] = part.index <= last
        history = part["is_history"]
        for col in ["gross_sales_qty", "gross_revenue", "net_sales_qty", "active_sku_count", "available_sku_count"]:
            part.loc[history, col] = part.loc[history, col].fillna(0.0)
        for col in ["gross_weighted_avg_price", "sales_weighted_wholesale_price", "sales_weighted_loss_rate_pct"]:
            hist_values = part.loc[history, col].ffill().bfill()
            part.loc[history, col] = hist_values
        part["logq"] = np.where(history, np.log1p(part["gross_sales_qty"].clip(lower=0)), np.nan)
        part["logp"] = np.where(history, np.log(part["gross_weighted_avg_price"].clip(lower=1e-6)), np.nan)
        part["logw"] = np.where(history, np.log(part["sales_weighted_wholesale_price"].clip(lower=1e-6)), np.nan)
        frames[category] = part.reset_index()
    return frames


def add_calendar_features(g: pd.DataFrame) -> pd.DataFrame:
    g = g.copy()
    doy = g["date"].dt.dayofyear.to_numpy()
    dow = g["date"].dt.dayofweek.to_numpy()
    month = g["date"].dt.month.to_numpy()
    g["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    g["dow_cos"] = np.cos(2 * np.pi * dow / 7)
    g["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    g["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    g["month_sin"] = np.sin(2 * np.pi * month / 12)
    g["month_cos"] = np.cos(2 * np.pi * month / 12)
    g["trend"] = np.arange(len(g), dtype=float) / max(1, len(g) - 1)
    return g


def add_dml_features(g: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    g = add_calendar_features(g)
    for lag in (1, 7, 14, 28):
        g[f"logq_lag{lag}"] = g["logq"].shift(lag)
    for lag in (1, 7):
        g[f"logp_lag{lag}"] = g["logp"].shift(lag)
        g[f"logw_lag{lag}"] = g["logw"].shift(lag)
    g["logq_ma7_s1"] = g["logq"].shift(1).rolling(7).mean()
    g["logq_ma28_s1"] = g["logq"].shift(1).rolling(28).mean()
    g["logq_sd28_s1"] = g["logq"].shift(1).rolling(28).std()
    g["active_lag1"] = g["active_sku_count"].shift(1)
    g["active_lag7"] = g["active_sku_count"].shift(7)
    cols = [
        "dow_sin", "dow_cos", "doy_sin", "doy_cos", "month_sin", "month_cos", "trend",
        "logw", "logq_lag1", "logq_lag7", "logq_lag14", "logq_lag28",
        "logp_lag1", "logp_lag7", "logw_lag1", "logw_lag7",
        "logq_ma7_s1", "logq_ma28_s1", "logq_sd28_s1", "active_lag1", "active_lag7",
    ]
    return g, cols


def moving_block_slopes(rx: np.ndarray, ry: np.ndarray, reps: int = 400, block: int = 7) -> np.ndarray:
    rng = np.random.default_rng(SEED)
    n = len(rx)
    starts = np.arange(max(1, n - block + 1))
    values = []
    blocks_needed = math.ceil(n / block)
    for _ in range(reps):
        chosen = rng.choice(starts, size=blocks_needed, replace=True)
        idx = np.concatenate([np.arange(s, min(s + block, n)) for s in chosen])[:n]
        denom = float(np.dot(rx[idx], rx[idx]))
        if denom > 1e-12:
            values.append(float(np.dot(rx[idx], ry[idx]) / denom))
    return np.asarray(values)


def estimate_elasticities(frames: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict[str, float]]:
    raw_rows = []
    residual_pairs: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for category, frame in frames.items():
        g, cols = add_dml_features(frame)
        use = g[g["is_history"]].dropna(subset=cols + ["logq", "logp"]).reset_index(drop=True)
        X = use[cols].to_numpy()
        y = use["logq"].to_numpy()
        x = use["logp"].to_numpy()
        ry = np.full(len(use), np.nan)
        rx = np.full(len(use), np.nan)
        for fold, (train, test) in enumerate(TimeSeriesSplit(n_splits=5).split(X)):
            my = hgb_model(SEED + fold)
            mx = hgb_model(SEED + 100 + fold)
            my.fit(X[train], y[train])
            mx.fit(X[train], x[train])
            ry[test] = y[test] - my.predict(X[test])
            rx[test] = x[test] - mx.predict(X[test])
        ok = np.isfinite(ry) & np.isfinite(rx)
        rx_c, ry_c = rx[ok], ry[ok]
        theta = float(np.dot(rx_c, ry_c) / np.dot(rx_c, rx_c))
        boot = moving_block_slopes(rx_c, ry_c)
        se = float(np.std(boot, ddof=1))
        ci_low, ci_high = np.quantile(boot, [0.025, 0.975])
        residual_pairs[category] = (rx_c, ry_c)
        raw_rows.append({
            "category_name": category,
            "n_crossfit": int(ok.sum()),
            "elasticity_raw": theta,
            "bootstrap_se": se,
            "ci_lower": float(ci_low),
            "ci_upper": float(ci_high),
            "price_residual_sd": float(np.std(rx_c, ddof=1)),
        })

    all_rx = np.concatenate([v[0] for v in residual_pairs.values()])
    all_ry = np.concatenate([v[1] for v in residual_pairs.values()])
    pooled = float(np.dot(all_rx, all_ry) / np.dot(all_rx, all_rx))
    raw_values = np.array([r["elasticity_raw"] for r in raw_rows])
    se_values = np.array([r["bootstrap_se"] for r in raw_rows])
    tau2 = max(float(np.var(raw_values, ddof=1) - np.mean(se_values**2)), 0.01**2)
    used: dict[str, float] = {}
    for row in raw_rows:
        weight = tau2 / (tau2 + row["bootstrap_se"] ** 2)
        shrunk = weight * row["elasticity_raw"] + (1 - weight) * pooled
        projected = float(np.clip(shrunk, ELASTICITY_BOUNDS[0], ELASTICITY_BOUNDS[1]))
        row["pooled_elasticity"] = pooled
        row["shrinkage_weight"] = weight
        row["elasticity_shrunk"] = shrunk
        row["elasticity_used"] = projected
        row["sign_constraint_active"] = int(not np.isclose(shrunk, projected))
        row["identification_label"] = (
            "negative_and_interval_below_zero" if row["ci_upper"] < 0
            else "negative_but_interval_crosses_zero" if row["elasticity_raw"] < 0
            else "nonnegative_raw_use_pooled_monotone_projection"
        )
        used[row["category_name"]] = projected
    return pd.DataFrame(raw_rows), used


def add_forecast_features(g: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
    g = add_calendar_features(g)
    for lag in (7, 14, 21, 28, 56):
        g[f"logq_lag{lag}"] = g["logq"].shift(lag)
    for lag in (7, 14, 21, 28):
        g[f"logw_lag{lag}"] = g["logw"].shift(lag)
        g[f"logp_lag{lag}"] = g["logp"].shift(lag)
    g["logq_ma7_s7"] = g["logq"].shift(7).rolling(7).mean()
    g["logq_ma28_s7"] = g["logq"].shift(7).rolling(28).mean()
    g["logq_sd28_s7"] = g["logq"].shift(7).rolling(28).std()
    g["logw_ma7_s7"] = g["logw"].shift(7).rolling(7).mean()
    g["logw_ma28_s7"] = g["logw"].shift(7).rolling(28).mean()
    g["active_lag7"] = g["active_sku_count"].shift(7)
    demand_cols = [
        "dow_sin", "dow_cos", "doy_sin", "doy_cos", "month_sin", "month_cos", "trend",
        "logq_lag7", "logq_lag14", "logq_lag21", "logq_lag28", "logq_lag56",
        "logq_ma7_s7", "logq_ma28_s7", "logq_sd28_s7", "logp_lag7", "logw_lag7", "active_lag7",
    ]
    cost_cols = [
        "dow_sin", "dow_cos", "doy_sin", "doy_cos", "month_sin", "month_cos", "trend",
        "logw_lag7", "logw_lag14", "logw_lag21", "logw_lag28",
        "logw_ma7_s7", "logw_ma28_s7", "logq_lag7", "active_lag7",
    ]
    return g, demand_cols, cost_cols


def choose_blend(y_level: np.ndarray, pred_model: np.ndarray, pred_naive: np.ndarray, to_level) -> tuple[float, np.ndarray]:
    ok = np.isfinite(y_level) & np.isfinite(pred_model) & np.isfinite(pred_naive)
    best_weight, best_score = 1.0, float("inf")
    best = pred_model.copy()
    for weight in np.linspace(0, 1, 21):
        pred = weight * pred_model + (1 - weight) * pred_naive
        pred_level = to_level(pred)
        score = wape(y_level[ok], pred_level[ok])
        if score < best_score:
            best_weight, best_score, best = float(weight), float(score), pred
    return best_weight, best


def rolling_forecast_category(frame: pd.DataFrame, theta: float, category: str) -> CategoryForecast:
    g, demand_cols, cost_cols = add_forecast_features(frame)
    g["alpha"] = g["logq"] - theta * g["logp"]
    g["alpha_lag7"] = g["alpha"].shift(7)
    g["logw_naive"] = g["logw"].shift(7)

    demand_use = g[g["is_history"]].dropna(subset=demand_cols + ["alpha", "alpha_lag7", "logp", "logq"]).copy()
    cost_use = g[g["is_history"]].dropna(subset=cost_cols + ["logw", "logw_naive"]).copy()

    def crossfit(use: pd.DataFrame, cols: list[str], target: str, seed_offset: int) -> np.ndarray:
        pred = np.full(len(use), np.nan)
        X = use[cols].to_numpy()
        y = use[target].to_numpy()
        for fold, (train, test) in enumerate(TimeSeriesSplit(n_splits=5).split(X)):
            model = hgb_model(SEED + seed_offset + fold)
            model.fit(X[train], y[train])
            pred[test] = model.predict(X[test])
        return pred

    alpha_gbdt = crossfit(demand_use, demand_cols, "alpha", 200)
    logw_gbdt = crossfit(cost_use, cost_cols, "logw", 300)

    logq_actual = demand_use["logq"].to_numpy()
    logp_actual = demand_use["logp"].to_numpy()
    alpha_naive = demand_use["alpha_lag7"].to_numpy()

    def demand_level(alpha_values: np.ndarray) -> np.ndarray:
        return np.maximum(0.0, np.expm1(alpha_values + theta * logp_actual))

    demand_actual = np.expm1(logq_actual)
    alpha_weight, alpha_blend = choose_blend(demand_actual, alpha_gbdt, alpha_naive, demand_level)
    demand_pred = demand_level(alpha_blend)
    seasonal_naive = np.maximum(0.0, np.expm1(alpha_naive + theta * logp_actual))
    demand_ok = np.isfinite(demand_pred)

    logw_actual = cost_use["logw"].to_numpy()
    logw_naive = cost_use["logw_naive"].to_numpy()
    cost_actual = np.exp(logw_actual)
    cost_weight, logw_blend = choose_blend(cost_actual, logw_gbdt, logw_naive, np.exp)
    cost_pred = np.exp(logw_blend)
    cost_ok = np.isfinite(cost_pred)

    demand_resid_values = logq_actual - (alpha_blend + theta * logp_actual)
    cost_resid_values = logw_actual - logw_blend
    demand_resid = pd.Series(demand_resid_values, index=demand_use["date"], name=category).dropna()
    cost_resid = pd.Series(cost_resid_values, index=cost_use["date"], name=category).dropna()

    split = max(1, int(0.7 * len(demand_resid)))
    calibration = demand_resid.iloc[:split].to_numpy()
    test = demand_resid.iloc[split:].to_numpy()
    q10, q90 = np.quantile(calibration, [0.10, 0.90])
    coverage80 = float(np.mean((test >= q10) & (test <= q90))) if len(test) else float("nan")

    demand_metrics = {
        "category_name": category,
        "demand_cv_n": int(demand_ok.sum()),
        "demand_blend_weight_gbdt": alpha_weight,
        "demand_wape": wape(demand_actual[demand_ok], demand_pred[demand_ok]),
        "demand_rmse_kg": float(np.sqrt(mean_squared_error(demand_actual[demand_ok], demand_pred[demand_ok]))),
        "demand_r2": float(r2_score(demand_actual[demand_ok], demand_pred[demand_ok])),
        "seasonal_naive_wape": wape(demand_actual[demand_ok], seasonal_naive[demand_ok]),
        "demand_residual_80pct_coverage": coverage80,
    }
    cost_metrics = {
        "category_name": category,
        "cost_cv_n": int(cost_ok.sum()),
        "cost_blend_weight_gbdt": cost_weight,
        "cost_wape": wape(cost_actual[cost_ok], cost_pred[cost_ok]),
        "cost_rmse_yuan_per_kg": float(np.sqrt(mean_squared_error(cost_actual[cost_ok], cost_pred[cost_ok]))),
        "cost_r2": float(r2_score(cost_actual[cost_ok], cost_pred[cost_ok])),
        "cost_seasonal_naive_wape": wape(cost_actual[cost_ok], np.exp(logw_naive[cost_ok])),
    }

    demand_model = hgb_model(SEED + 400)
    demand_model.fit(demand_use[demand_cols].to_numpy(), demand_use["alpha"].to_numpy())
    cost_model = hgb_model(SEED + 500)
    cost_model.fit(cost_use[cost_cols].to_numpy(), cost_use["logw"].to_numpy())
    future = g[g["date"].isin(FORECAST_DATES)].copy()
    alpha_future_gbdt = demand_model.predict(future[demand_cols].to_numpy())
    alpha_future = alpha_weight * alpha_future_gbdt + (1 - alpha_weight) * future["alpha_lag7"].to_numpy()
    logw_future_gbdt = cost_model.predict(future[cost_cols].to_numpy())
    logw_future = cost_weight * logw_future_gbdt + (1 - cost_weight) * future["logw_naive"].to_numpy()

    return CategoryForecast(
        category=category,
        alpha_future=alpha_future,
        log_cost_future=logw_future,
        demand_residual=demand_resid,
        cost_residual=cost_resid,
        demand_metrics=demand_metrics,
        cost_metrics=cost_metrics,
    )


def load_loss_rates(frames: dict[str, pd.DataFrame]) -> dict[str, float]:
    rates: dict[str, float] = {}
    for category, frame in frames.items():
        recent = frame[frame["is_history"]].tail(30).copy()
        qty = recent["gross_sales_qty"].clip(lower=0).to_numpy()
        daily_loss = (recent["sales_weighted_loss_rate_pct"].clip(0, 95) / 100).to_numpy()
        valid = np.isfinite(qty) & np.isfinite(daily_loss)
        if valid.any() and qty[valid].sum() > 0:
            rates[category] = float(np.average(daily_loss[valid], weights=qty[valid]))
        else:
            rates[category] = float(np.nanmedian(daily_loss[valid]))
    return rates


def build_joint_scenarios(forecasts: dict[str, CategoryForecast], categories: list[str]) -> tuple[np.ndarray, np.ndarray, dict]:
    demand = pd.concat({c: forecasts[c].demand_residual for c in categories}, axis=1).dropna()
    cost = pd.concat({c: forecasts[c].cost_residual for c in categories}, axis=1).dropna()
    common = demand.index.intersection(cost.index)
    demand, cost = demand.loc[common], cost.loc[common]
    for df in (demand, cost):
        for c in categories:
            low, high = df[c].quantile([0.01, 0.99])
            df[c] = df[c].clip(low, high) - df[c].clip(low, high).mean()
    dates = pd.DatetimeIndex(common)
    valid_starts = []
    for i in range(0, len(dates) - BLOCK_LENGTH + 1):
        if (dates[i + BLOCK_LENGTH - 1] - dates[i]).days == BLOCK_LENGTH - 1:
            valid_starts.append(i)
    if not valid_starts:
        raise RuntimeError("No complete 7-day residual blocks are available")
    rng = np.random.default_rng(SEED)
    starts = rng.choice(valid_starts, size=SCENARIO_COUNT, replace=True)
    d_values, w_values = demand[categories].to_numpy(), cost[categories].to_numpy()
    d_scen = np.stack([d_values[s:s + BLOCK_LENGTH] for s in starts], axis=0)
    w_scen = np.stack([w_values[s:s + BLOCK_LENGTH] for s in starts], axis=0)
    hist_corr = demand[categories].corr().to_numpy()
    scen_corr = np.corrcoef(d_scen.reshape(-1, len(categories)), rowvar=False)
    joint_history = np.concatenate(
        [demand[categories].to_numpy(), cost[categories].to_numpy()], axis=1
    )
    joint_scenarios = np.concatenate([d_scen, w_scen], axis=2)
    joint_hist_corr = np.corrcoef(joint_history, rowvar=False)
    joint_scen_corr = np.corrcoef(
        joint_scenarios.reshape(-1, 2 * len(categories)), rowvar=False
    )
    info = {
        "residual_pool_days": int(len(common)),
        "valid_7day_blocks": int(len(valid_starts)),
        "scenario_count": SCENARIO_COUNT,
        "max_abs_cross_category_corr_difference": float(np.max(np.abs(hist_corr - scen_corr))),
        "max_abs_joint_demand_cost_corr_difference": float(
            np.max(np.abs(joint_hist_corr - joint_scen_corr))
        ),
    }
    return d_scen, w_scen, info


def lower_tail_mean(values: np.ndarray, probability: float = LOWER_TAIL_PROB) -> float:
    k = max(1, int(math.ceil(probability * len(values))))
    return float(np.mean(np.partition(values, k - 1)[:k]))


def weekly_risk_statistics(
    profit_by_day: np.ndarray,
    gamma: float,
    tail_probability: float = LOWER_TAIL_PROB,
) -> dict[str, float]:
    """Aggregate scenario profit over days before evaluating downside risk."""
    values = np.asarray(profit_by_day, dtype=float)
    if values.ndim != 2:
        raise ValueError("profit_by_day must have shape (scenario, day)")
    weekly_profit = values.sum(axis=1)
    expected = float(weekly_profit.mean())
    tail = lower_tail_mean(weekly_profit, tail_probability)
    return {
        "weekly_expected_profit": expected,
        "weekly_lower_tail_mean": tail,
        "risk_adjusted_objective": (1 - gamma) * expected + gamma * tail,
    }


def maximum_markup_change_violation(
    markup: np.ndarray,
    reference: np.ndarray,
    delta: np.ndarray,
) -> float:
    """Return the largest first-day or interday markup-change violation."""
    markup = np.asarray(markup, dtype=float)
    reference = np.asarray(reference, dtype=float)
    delta = np.asarray(delta, dtype=float)
    if markup.ndim != 2 or markup.shape[1] != len(reference) or len(reference) != len(delta):
        raise ValueError("markup, reference and delta have incompatible shapes")
    first = np.abs(markup[0] - reference) - delta
    later = np.abs(np.diff(markup, axis=0)) - delta[None, :]
    return float(max(0.0, np.max(first), np.max(later)))


def build_weekly_decision_bounds(
    categories: list[str],
    markup_global: dict[str, tuple[float, float]],
    reference: np.ndarray,
    delta: np.ndarray,
    q_upper: np.ndarray,
    n_days: int,
) -> list[tuple[float, float]]:
    """Construct time-ordered markup bounds followed by replenishment bounds."""
    bounds: list[tuple[float, float]] = []
    for h in range(n_days):
        for j, category in enumerate(categories):
            low, high = markup_global[category]
            if h == 0:
                low = max(low, float(reference[j] - delta[j]))
                high = min(high, float(reference[j] + delta[j]))
            bounds.append((float(low), float(high)))
    bounds.extend(
        [(0.0, float(q_upper[j])) for _ in range(n_days) for j in range(len(categories))]
    )
    return bounds


def optimize_week(
    gamma: float,
    categories: list[str],
    alpha_future: np.ndarray,
    cost_future: np.ndarray,
    theta: np.ndarray,
    loss: np.ndarray,
    demand_scen: np.ndarray,
    cost_scen_resid: np.ndarray,
    markup_global: dict[str, tuple[float, float]],
    markup_change: dict[str, float],
    markup_reference: dict[str, float],
    q_upper: np.ndarray,
    double_seed_main: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict]]:
    """Optimize all seven days jointly, using daywise DE only as a robust initializer."""
    n_days = len(FORECAST_DATES)
    n_categories = len(categories)
    reference = np.array([markup_reference[c] for c in categories], dtype=float)
    delta = np.array([markup_change[c] for c in categories], dtype=float)
    previous_markup = reference.copy()
    initial_markup: list[np.ndarray] = []
    initial_q: list[np.ndarray] = []
    de_success_flags: list[bool] = []

    # Stage 1: solve small daily subproblems to obtain a strong feasible start.
    for h, date in enumerate(FORECAST_DATES):
        m_bounds = []
        for j, c in enumerate(categories):
            global_low, global_high = markup_global[c]
            daily_delta = markup_change[c]
            low = max(global_low, previous_markup[j] - daily_delta)
            high = min(global_high, previous_markup[j] + daily_delta)
            if high <= low + 1e-6:
                low, high = global_low, global_high
            m_bounds.append((float(low), float(high)))
        bounds = m_bounds + [(0.0, float(q_upper[j])) for j in range(len(categories))]
        cost_base = cost_future[h]
        scenario_cost = np.exp(np.log(cost_base)[None, :] + cost_scen_resid[:, h, :])

        def evaluate(z: np.ndarray) -> tuple[float, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
            markup = z[:len(categories)]
            q = z[len(categories):]
            price = cost_base * (1 + markup)
            logd = alpha_future[h][None, :] + theta[None, :] * np.log(price)[None, :] + demand_scen[:, h, :]
            demand = np.maximum(0.0, np.expm1(np.clip(logd, -12, 8)))
            available = (1 - loss)[None, :] * q[None, :]
            sales = np.minimum(demand, available)
            category_profit = price[None, :] * sales - scenario_cost * q[None, :]
            profit = category_profit.sum(axis=1)
            score = (1 - gamma) * float(profit.mean()) + gamma * lower_tail_mean(profit)
            return score, profit, sales, demand, category_profit

        def objective(z: np.ndarray) -> float:
            return -evaluate(z)[0]

        de = differential_evolution(
            objective, bounds=bounds, seed=SEED + h * 17 + int(gamma * 1000),
            maxiter=65, popsize=8, tol=1e-6, atol=1e-4, polish=False,
            updating="immediate", workers=1,
        )
        local = minimize(
            objective, de.x, method="SLSQP", bounds=bounds,
            options={"maxiter": 500, "ftol": 1e-9, "disp": False},
        )
        z = local.x if local.fun <= de.fun else de.x
        markup = z[:n_categories]
        q = z[n_categories:]
        previous_markup = markup.copy()
        initial_markup.append(markup)
        initial_q.append(q)
        de_success_flags.append(bool(de.success))

    markup0 = np.vstack(initial_markup)
    q0 = np.vstack(initial_q)
    z0 = np.concatenate([markup0.ravel(), q0.ravel()])

    # Stage 2: refine the complete 7-day decision vector against weekly profit.
    scenario_cost = np.exp(np.log(cost_future)[None, :, :] + cost_scen_resid)

    def evaluate_weekly(z: np.ndarray, need_gradient: bool = False):
        markup = z[:n_days * n_categories].reshape(n_days, n_categories)
        q = z[n_days * n_categories:].reshape(n_days, n_categories)
        price = cost_future * (1 + markup)
        raw_logd = (
            alpha_future[None, :, :]
            + theta[None, None, :] * np.log(price)[None, :, :]
            + demand_scen
        )
        clipped_logd = np.clip(raw_logd, -12, 8)
        demand = np.maximum(0.0, np.expm1(clipped_logd))
        available = (1 - loss)[None, None, :] * q[None, :, :]
        stock_limited = demand >= available
        sales = np.minimum(demand, available)
        category_profit = price[None, :, :] * sales - scenario_cost * q[None, :, :]
        profit_by_day = category_profit.sum(axis=2)
        stats = weekly_risk_statistics(profit_by_day, gamma, LOWER_TAIL_PROB)
        if not need_gradient:
            return stats, profit_by_day, sales, demand, category_profit

        active_exp = (raw_logd > -12) & (raw_logd < 8)
        demand_dm = (
            (demand + 1)
            * theta[None, None, :]
            / (1 + markup)[None, :, :]
            * active_exp
        )
        markup_gradient = np.where(
            stock_limited,
            cost_future[None, :, :] * available,
            cost_future[None, :, :] * sales + price[None, :, :] * demand_dm,
        )
        q_gradient = np.where(
            stock_limited,
            price[None, :, :] * (1 - loss)[None, None, :] - scenario_cost,
            -scenario_cost,
        )
        scenario_gradient = np.concatenate(
            [markup_gradient.reshape(SCENARIO_COUNT, -1), q_gradient.reshape(SCENARIO_COUNT, -1)],
            axis=1,
        )
        weekly_profit = profit_by_day.sum(axis=1)
        k = max(1, int(math.ceil(LOWER_TAIL_PROB * len(weekly_profit))))
        tail_idx = np.argpartition(weekly_profit, k - 1)[:k]
        score_gradient = (
            (1 - gamma) * scenario_gradient.mean(axis=0)
            + gamma * scenario_gradient[tail_idx].mean(axis=0)
        )
        return stats, profit_by_day, sales, demand, category_profit, score_gradient

    weekly_bounds = build_weekly_decision_bounds(
        categories, markup_global, reference, delta, q_upper, n_days
    )

    smooth_matrix = np.zeros(((n_days - 1) * n_categories, len(z0)))
    smooth_lower = np.empty((n_days - 1) * n_categories)
    smooth_upper = np.empty((n_days - 1) * n_categories)
    row = 0
    for h in range(1, n_days):
        for j in range(n_categories):
            smooth_matrix[row, h * n_categories + j] = 1.0
            smooth_matrix[row, (h - 1) * n_categories + j] = -1.0
            smooth_lower[row] = -delta[j]
            smooth_upper[row] = delta[j]
            row += 1
    smooth_constraint = LinearConstraint(smooth_matrix, smooth_lower, smooth_upper)

    starts = [z0]
    if double_seed_main:
        alternative_markup = reference[None, :] + 0.90 * (markup0 - reference[None, :])
        alternative_q = 0.95 * q0
        starts.append(np.concatenate([alternative_markup.ravel(), alternative_q.ravel()]))

    weekly_candidates = []
    for start in starts:
        cache: dict[str, np.ndarray | float] = {}

        def objective_weekly(z: np.ndarray) -> float:
            if "z" not in cache or not np.array_equal(cache["z"], z):
                result = evaluate_weekly(z, need_gradient=True)
                cache["z"] = z.copy()
                cache["score"] = float(result[0]["risk_adjusted_objective"])
                cache["gradient"] = result[-1]
            return -float(cache["score"])

        def gradient_weekly(z: np.ndarray) -> np.ndarray:
            objective_weekly(z)
            return -np.asarray(cache["gradient"], dtype=float)

        initial_objective = -objective_weekly(start)
        local = minimize(
            objective_weekly,
            start,
            jac=gradient_weekly,
            method="SLSQP",
            bounds=weekly_bounds,
            constraints=[smooth_constraint],
            options={"maxiter": 500, "ftol": 1e-8, "disp": False},
        )
        candidate_z = local.x if np.isfinite(local.fun) and local.fun <= -initial_objective else start
        candidate_score = -objective_weekly(candidate_z)
        weekly_candidates.append((candidate_score, candidate_z, local, initial_objective))

    weekly_candidates.sort(key=lambda item: item[0], reverse=True)
    score, z, weekly_local, initial_objective = weekly_candidates[0]
    stats, profit_by_day, sales, demand, category_profit = evaluate_weekly(z)
    markup = z[:n_days * n_categories].reshape(n_days, n_categories)
    q = z[n_days * n_categories:].reshape(n_days, n_categories)
    price = cost_future * (1 + markup)
    weekly_profit = profit_by_day.sum(axis=1)
    k = max(1, int(math.ceil(LOWER_TAIL_PROB * len(weekly_profit))))
    weekly_tail_idx = np.argpartition(weekly_profit, k - 1)[:k]

    strategy_rows = []
    daily_rows = []
    for h, date in enumerate(FORECAST_DATES):
        daily_profit = profit_by_day[:, h]
        daily_tail = lower_tail_mean(daily_profit)
        for j, c in enumerate(categories):
            strategy_rows.append({
                "risk_weight": gamma,
                "date": str(date.date()),
                "category_name": c,
                "elasticity_used": theta[j],
                "forecast_wholesale_cost_yuan_per_kg": cost_future[h, j],
                "loss_rate": loss[j],
                "markup_rate": markup[h, j],
                "price_yuan_per_kg": price[h, j],
                "replenishment_kg": q[h, j],
                "expected_demand_kg": float(demand[:, h, j].mean()),
                "expected_sales_kg": float(sales[:, h, j].mean()),
                "expected_unsold_or_loss_kg": float(q[h, j] - sales[:, h, j].mean()),
                "expected_profit_yuan": float(category_profit[:, h, j].mean()),
                "worst10pct_weekly_profit_contribution_yuan": float(
                    category_profit[weekly_tail_idx, h, j].mean()
                ),
                "stockout_probability": float(
                    np.mean(demand[:, h, j] > (1 - loss[j]) * q[h, j])
                ),
            })
        daily_rows.append({
            "risk_weight": gamma,
            "date": str(date.date()),
            "daily_risk_adjusted_diagnostic": (
                (1 - gamma) * float(daily_profit.mean()) + gamma * daily_tail
            ),
            "expected_profit_yuan": float(daily_profit.mean()),
            "worst10pct_mean_profit_yuan": daily_tail,
            "profit_std_yuan": float(daily_profit.std(ddof=1)),
        })

    weekly_row = {
        "risk_weight": gamma,
        "risk_adjusted_objective": stats["risk_adjusted_objective"],
        "weekly_expected_profit_yuan": stats["weekly_expected_profit"],
        "weekly_worst10pct_mean_profit_yuan": stats["weekly_lower_tail_mean"],
        "weekly_profit_std_yuan": float(weekly_profit.std(ddof=1)),
    }
    seed_gap = 0.0
    if len(weekly_candidates) > 1:
        seed_gap = abs(weekly_candidates[1][0] - weekly_candidates[0][0]) / max(
            1.0, abs(weekly_candidates[0][0])
        )
    bound_violation = float(max(
        [max(lo - val, 0.0, val - hi) for val, (lo, hi) in zip(z, weekly_bounds)] + [0.0]
    ))
    optimizer_rows = [{
        "risk_weight": gamma,
        "scope": "weekly_joint",
        "de_all_success": bool(all(de_success_flags)),
        "slsqp_success": bool(weekly_local.success),
        "slsqp_message": str(weekly_local.message),
        "initial_objective": initial_objective,
        "best_objective": score,
        "two_seed_relative_gap": seed_gap,
        "max_bound_violation": bound_violation,
        "max_markup_change_violation": maximum_markup_change_violation(markup, reference, delta),
    }]
    return (
        pd.DataFrame(strategy_rows),
        pd.DataFrame(daily_rows),
        pd.DataFrame([weekly_row]),
        optimizer_rows,
    )


def main() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    frames = prepare_category_frames()
    categories = sorted(frames)
    elasticity_table, elasticity_used = estimate_elasticities(frames)
    elasticity_reliable = {
        str(row["category_name"]): bool(row["ci_upper"] < 0)
        for _, row in elasticity_table.iterrows()
    }
    forecasts = {c: rolling_forecast_category(frames[c], elasticity_used[c], c) for c in categories}
    demand_scen, cost_scen_resid, scenario_info = build_joint_scenarios(forecasts, categories)

    loss_map = load_loss_rates(frames)
    loss = np.array([loss_map[c] for c in categories], dtype=float)
    theta = np.array([elasticity_used[c] for c in categories], dtype=float)
    alpha_future = np.column_stack([forecasts[c].alpha_future for c in categories])
    cost_future = np.column_stack([np.exp(forecasts[c].log_cost_future) for c in categories])

    markup_global: dict[str, tuple[float, float]] = {}
    markup_reference: dict[str, float] = {}
    markup_change: dict[str, float] = {}
    q_upper = []
    bound_rows = []
    for j, c in enumerate(categories):
        hist = frames[c][frames[c]["is_history"]].tail(365).copy()
        markup = (hist["gross_weighted_avg_price"] - hist["sales_weighted_wholesale_price"]) / hist["sales_weighted_wholesale_price"]
        markup = markup.replace([np.inf, -np.inf], np.nan).dropna()
        low = max(0.0, float(markup.quantile(0.05)))
        upper_quantile = 0.95 if elasticity_reliable[c] else 0.90
        high = max(low + 0.05, float(markup.quantile(upper_quantile)))
        reference = float(markup.quantile(0.50))
        delta = max(0.04, float(markup.diff().abs().quantile(0.90)))
        markup_global[c] = (low, high)
        markup_reference[c] = float(np.clip(reference, low, high))
        markup_change[c] = delta
        hist_loss = (hist["sales_weighted_loss_rate_pct"].fillna(loss[j] * 100) / 100).clip(0, 0.95)
        proxy_q = hist["gross_sales_qty"] / (1 - hist_loss)
        hist_cap = float(proxy_q.quantile(0.99) * 1.25)
        low_price = cost_future[:, j] * (1 + low)
        demand_low_price = np.maximum(0.0, np.expm1(
            alpha_future[:, j][None, :] + theta[j] * np.log(low_price)[None, :] + demand_scen[:, :, j]
        ))
        scenario_cap = float(np.quantile(demand_low_price / (1 - loss[j]), 0.99) * 1.10)
        upper = max(hist_cap, scenario_cap, 1.0)
        q_upper.append(upper)
        bound_rows.append({
            "category_name": c,
            "markup_p05": low,
            "markup_median": markup_reference[c],
            "markup_upper": high,
            "markup_upper_quantile_used": upper_quantile,
            "markup_daily_change_p90": delta,
            "replenishment_upper_kg": upper,
            "loss_rate": loss[j],
        })
    q_upper = np.array(q_upper)

    all_strategy, all_daily, all_weekly, optimizer_rows = [], [], [], []
    for gamma in RISK_WEIGHTS:
        strategy, daily, weekly, optimizer = optimize_week(
            gamma, categories, alpha_future, cost_future, theta, loss,
            demand_scen, cost_scen_resid, markup_global, markup_change,
            markup_reference, q_upper, double_seed_main=np.isclose(gamma, MAIN_RISK_WEIGHT),
        )
        all_strategy.append(strategy)
        all_daily.append(daily)
        all_weekly.append(weekly)
        optimizer_rows.extend(optimizer)
    strategy_all = pd.concat(all_strategy, ignore_index=True)
    daily_all = pd.concat(all_daily, ignore_index=True)
    weekly_all = pd.concat(all_weekly, ignore_index=True)
    main_strategy = strategy_all[np.isclose(strategy_all["risk_weight"], MAIN_RISK_WEIGHT)].copy()

    # Operational baseline: median historical markup and median scenario demand replenishment.
    baseline_rows = []
    baseline_profit_columns = []
    for h, date in enumerate(FORECAST_DATES):
        prices = np.array([cost_future[h, j] * (1 + markup_reference[c]) for j, c in enumerate(categories)])
        logd = alpha_future[h][None, :] + theta[None, :] * np.log(prices)[None, :] + demand_scen[:, h, :]
        demand = np.maximum(0.0, np.expm1(np.clip(logd, -12, 8)))
        q = np.median(demand, axis=0) / (1 - loss)
        scenario_cost = np.exp(np.log(cost_future[h])[None, :] + cost_scen_resid[:, h, :])
        sales = np.minimum(demand, (1 - loss)[None, :] * q[None, :])
        profit = (prices[None, :] * sales - scenario_cost * q[None, :]).sum(axis=1)
        baseline_profit_columns.append(profit)
        baseline_rows.append({
            "date": str(date.date()),
            "expected_profit_yuan": float(profit.mean()),
            "worst10pct_mean_profit_yuan": lower_tail_mean(profit),
            "profit_std_yuan": float(profit.std(ddof=1)),
        })
    baseline = pd.DataFrame(baseline_rows)
    baseline_weekly_stats = weekly_risk_statistics(
        np.column_stack(baseline_profit_columns), MAIN_RISK_WEIGHT, LOWER_TAIL_PROB
    )

    demand_metrics = pd.DataFrame([forecasts[c].demand_metrics for c in categories])
    cost_metrics = pd.DataFrame([forecasts[c].cost_metrics for c in categories])
    metrics = demand_metrics.merge(cost_metrics, on="category_name")
    bounds = pd.DataFrame(bound_rows)
    optimizer = pd.DataFrame(optimizer_rows)

    strategy_all.to_csv(TABLES / "q2_strategy_all_risk_weights.csv", index=False, encoding="utf-8-sig")
    main_strategy.to_csv(TABLES / "q2_daily_strategy.csv", index=False, encoding="utf-8-sig")
    daily_all.to_csv(TABLES / "q2_daily_risk_summary.csv", index=False, encoding="utf-8-sig")
    weekly_all.to_csv(TABLES / "q2_weekly_risk_summary.csv", index=False, encoding="utf-8-sig")
    baseline.to_csv(TABLES / "q2_baseline_summary.csv", index=False, encoding="utf-8-sig")
    elasticity_table.to_csv(TABLES / "q2_elasticity_estimates.csv", index=False, encoding="utf-8-sig")
    metrics.to_csv(TABLES / "q2_forecast_metrics.csv", index=False, encoding="utf-8-sig")
    bounds.to_csv(TABLES / "q2_decision_bounds.csv", index=False, encoding="utf-8-sig")
    optimizer.to_csv(TABLES / "q2_optimizer_checks.csv", index=False, encoding="utf-8-sig")

    main_weekly = weekly_all[np.isclose(weekly_all["risk_weight"], MAIN_RISK_WEIGHT)].iloc[0]
    risk_neutral = weekly_all[np.isclose(weekly_all["risk_weight"], 0.0)].iloc[0]
    risk_high = weekly_all[np.isclose(weekly_all["risk_weight"], 0.50)].iloc[0]
    summary = {
        "model": "cross-fitted semi-parametric elasticity + aligned-lag GBDT/seasonal blend + joint moving-block scenarios + mean-lower-CVaR optimization",
        "forecast_dates": [str(d.date()) for d in FORECAST_DATES],
        "categories": categories,
        "random_seed": SEED,
        "scenario": scenario_info,
        "risk": {"lower_tail_probability": LOWER_TAIL_PROB, "main_risk_weight": MAIN_RISK_WEIGHT},
        "forecast_metrics": {
            "demand_weighted_wape": float(np.average(metrics["demand_wape"], weights=metrics["demand_cv_n"])),
            "seasonal_naive_weighted_wape": float(np.average(metrics["seasonal_naive_wape"], weights=metrics["demand_cv_n"])),
            "cost_weighted_wape": float(np.average(metrics["cost_wape"], weights=metrics["cost_cv_n"])),
            "cost_naive_weighted_wape": float(np.average(metrics["cost_seasonal_naive_wape"], weights=metrics["cost_cv_n"])),
            "mean_80pct_coverage": float(metrics["demand_residual_80pct_coverage"].mean()),
        },
        "main_strategy": {
            "weekly_replenishment_kg": float(main_strategy["replenishment_kg"].sum()),
            "weekly_expected_sales_kg": float(main_strategy["expected_sales_kg"].sum()),
            "weekly_expected_profit_yuan": float(main_weekly["weekly_expected_profit_yuan"]),
            "weekly_worst10pct_mean_profit_yuan": float(main_weekly["weekly_worst10pct_mean_profit_yuan"]),
            "weekly_risk_adjusted_objective": float(main_weekly["risk_adjusted_objective"]),
            "mean_markup_rate": float(main_strategy["markup_rate"].mean()),
            "price_range_yuan_per_kg": [float(main_strategy["price_yuan_per_kg"].min()), float(main_strategy["price_yuan_per_kg"].max())],
            "replenishment_range_kg": [float(main_strategy["replenishment_kg"].min()), float(main_strategy["replenishment_kg"].max())],
            "mean_stockout_probability": float(main_strategy["stockout_probability"].mean()),
        },
        "baseline": {
            "weekly_expected_profit_yuan": baseline_weekly_stats["weekly_expected_profit"],
            "weekly_worst10pct_mean_profit_yuan": baseline_weekly_stats["weekly_lower_tail_mean"],
        },
        "risk_neutral": {
            "weekly_expected_profit_yuan": float(risk_neutral["weekly_expected_profit_yuan"]),
            "weekly_worst10pct_mean_profit_yuan": float(risk_neutral["weekly_worst10pct_mean_profit_yuan"]),
        },
        "high_risk_aversion": {
            "weekly_expected_profit_yuan": float(risk_high["weekly_expected_profit_yuan"]),
            "weekly_worst10pct_mean_profit_yuan": float(risk_high["weekly_worst10pct_mean_profit_yuan"]),
        },
        "checks": {
            "constraint_max_violation": float(optimizer["max_bound_violation"].max()),
            "markup_change_max_violation": float(optimizer["max_markup_change_violation"].max()),
            "main_two_seed_max_relative_gap": float(optimizer[np.isclose(optimizer["risk_weight"], MAIN_RISK_WEIGHT)]["two_seed_relative_gap"].max()),
            "all_numeric_finite": bool(np.isfinite(main_strategy.select_dtypes(include=[np.number]).to_numpy()).all()),
            "rows_in_main_strategy": int(len(main_strategy)),
        },
    }
    summary["main_strategy"]["expected_profit_improvement_vs_baseline"] = (
        summary["main_strategy"]["weekly_expected_profit_yuan"] / summary["baseline"]["weekly_expected_profit_yuan"] - 1
    )
    summary["main_strategy"]["tail_profit_change_yuan_vs_baseline"] = (
        summary["main_strategy"]["weekly_worst10pct_mean_profit_yuan"]
        - summary["baseline"]["weekly_worst10pct_mean_profit_yuan"]
    )
    (RESULTS / "q2_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
