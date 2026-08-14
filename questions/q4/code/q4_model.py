"""Question 4: auditable data-gap diagnosis and collection-portfolio model.

The model deliberately does not assign hypothetical distributions, acquisition
costs, or information-value coefficients to data that have not been collected.
It extracts evidence from the checked Q1-Q3 outputs, maps candidate data packages
to identifiable modeling capabilities, enumerates minimum-cardinality feasible
portfolios, and measures priority stability across explicit structural scenarios.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = ROOT / "questions" / "q4" / "outputs"

PACKAGE_ORDER = [
    "inventory_stockout",
    "batch_loss_quality",
    "supplier_quote_fulfillment",
    "promotion_display_traffic",
    "anonymous_basket",
    "weather_calendar",
    "competitor_price",
]

PACKAGE_SHORT_NAMES = {
    "inventory_stockout": "库存与缺货",
    "batch_loss_quality": "批次损耗与品质",
    "supplier_quote_fulfillment": "供应商报价与履约",
    "promotion_display_traffic": "促销陈列与客流",
    "anonymous_basket": "匿名购物篮",
    "weather_calendar": "天气与日历",
    "competitor_price": "竞争价格",
}

CAPABILITY_NAMES = {
    "latent_demand": "识别被缺货截断的真实需求",
    "price_response": "控制促销曝光后的价格响应",
    "dynamic_loss": "估计批次动态损耗",
    "supply_cost": "刻画报价和供货不确定性",
    "assortment_substitution": "识别可售集合下的替代与份额",
    "external_demand": "解释客流与外部需求冲击",
    "realized_validation": "核算实际利润和服务水平",
    "competitive_context": "补充相对市场价格背景",
}


@dataclass(frozen=True)
class Requirement:
    """A capability is met when any alternative package set is contained."""

    capability: str
    alternatives: tuple[frozenset[str], ...]

    def is_met(self, selected: set[str]) -> bool:
        return any(alternative.issubset(selected) for alternative in self.alternatives)


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    scenario_name: str
    rationale: str
    requirements: tuple[Requirement, ...]

    def is_feasible(self, packages: Iterable[str]) -> bool:
        selected = set(packages)
        return all(requirement.is_met(selected) for requirement in self.requirements)

    @property
    def capabilities(self) -> tuple[str, ...]:
        return tuple(requirement.capability for requirement in self.requirements)


REQ = {
    "latent_demand": Requirement(
        "latent_demand", (frozenset({"inventory_stockout"}),)
    ),
    "price_response": Requirement(
        "price_response",
        (frozenset({"inventory_stockout", "promotion_display_traffic"}),),
    ),
    "dynamic_loss": Requirement(
        "dynamic_loss", (frozenset({"batch_loss_quality"}),)
    ),
    "supply_cost": Requirement(
        "supply_cost", (frozenset({"supplier_quote_fulfillment"}),)
    ),
    "assortment_substitution": Requirement(
        "assortment_substitution",
        (frozenset({"inventory_stockout", "anonymous_basket"}),),
    ),
    "external_demand": Requirement(
        "external_demand",
        (
            frozenset({"promotion_display_traffic"}),
            frozenset({"weather_calendar"}),
        ),
    ),
    "realized_validation": Requirement(
        "realized_validation",
        (
            frozenset(
                {
                    "inventory_stockout",
                    "batch_loss_quality",
                    "supplier_quote_fulfillment",
                }
            ),
        ),
    ),
    "weather_context": Requirement(
        "external_demand", (frozenset({"weather_calendar"}),)
    ),
    "competitive_context": Requirement(
        "competitive_context", (frozenset({"competitor_price"}),)
    ),
}

BASE_SCENARIO = Scenario(
    "base_core",
    "完整核心链路",
    "同时修复需求、价格、损耗、供给、单品替代与决策验证缺口。",
    (
        REQ["latent_demand"],
        REQ["price_response"],
        REQ["dynamic_loss"],
        REQ["supply_cost"],
        REQ["assortment_substitution"],
        REQ["external_demand"],
        REQ["realized_validation"],
    ),
)

SCENARIOS = (
    BASE_SCENARIO,
    Scenario(
        "forecast_strict",
        "强化外部预测",
        "在核心链路上要求独立天气和节假日数据，不允许仅由客流代理外部冲击。",
        BASE_SCENARIO.requirements + (REQ["weather_context"],),
    ),
    Scenario(
        "market_strict",
        "强化市场定价背景",
        "在核心链路上增加竞争价格，用于验证相对定价而非替代门店内部价格实验。",
        BASE_SCENARIO.requirements + (REQ["competitive_context"],),
    ),
    Scenario(
        "assortment_light",
        "暂缓替代识别",
        "短期只改进品类补货定价，暂不要求购物篮支持的单品替代建模。",
        tuple(r for r in BASE_SCENARIO.requirements if r.capability != "assortment_substitution"),
    ),
    Scenario(
        "cost_light",
        "暂缓供应端扩展",
        "已有批发价流程暂时维持，先修复需求、价格、损耗和单品份额。",
        tuple(
            r
            for r in BASE_SCENARIO.requirements
            if r.capability not in {"supply_cost", "realized_validation"}
        ),
    ),
    Scenario(
        "loss_light",
        "暂缓批次损耗",
        "先修复需求、价格、供应和选品关系，静态损耗率暂时保留。",
        tuple(
            r
            for r in BASE_SCENARIO.requirements
            if r.capability not in {"dynamic_loss", "realized_validation"}
        ),
    ),
    Scenario(
        "identification_only",
        "只做需求识别试点",
        "以真实需求、价格响应和单品替代三项统计识别为最小试点边界。",
        (REQ["latent_demand"], REQ["price_response"], REQ["assortment_substitution"]),
    ),
)


def _read_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"required source output is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"required source output is missing: {path}")
    return pd.read_csv(path, encoding="utf-8-sig")


def load_source_metrics(root: Path = ROOT) -> dict:
    """Read the exact Q1-Q3 evidence used by Question 4."""

    q1_summary_path = root / "questions/q1/outputs/results/q1_summary.json"
    q1_rel_path = root / "questions/q1/outputs/tables/tab_q1_all_sku_pair_relationships.csv"
    q2_summary_path = root / "questions/q2/outputs/results/q2_summary.json"
    q2_forecast_path = root / "questions/q2/outputs/tables/q2_forecast_metrics.csv"
    q2_elasticity_path = root / "questions/q2/outputs/tables/q2_elasticity_estimates.csv"
    q2_daily_path = root / "questions/q2/outputs/tables/q2_daily_strategy.csv"
    q2_sensitivity_path = root / "questions/q2/outputs/tables/q2_sensitivity_analysis.csv"
    q3_summary_path = root / "questions/q3/outputs/results/q3_summary.json"

    q1 = _read_json(q1_summary_path)
    q1_rel = _read_csv(q1_rel_path)
    q2 = _read_json(q2_summary_path)
    q2_forecast = _read_csv(q2_forecast_path)
    q2_elasticity = _read_csv(q2_elasticity_path)
    q2_daily = _read_csv(q2_daily_path)
    q2_sensitivity = _read_csv(q2_sensitivity_path)
    q3 = _read_json(q3_summary_path)

    if len(q2_forecast) != 6 or len(q2_elasticity) != 6:
        raise ValueError("Q2 category outputs must each contain exactly six categories")

    q2_main_daily = q2_daily[np.isclose(q2_daily["risk_weight"], q2["risk"]["main_risk_weight"])]
    demand_satisfaction = (
        q2_main_daily["expected_sales_kg"].sum()
        / q2_main_daily["expected_demand_kg"].sum()
    )
    goodwill = q2_sensitivity[q2_sensitivity["parameter"] == "goodwill_cost_ratio"]

    metrics = {
        "q1_distribution_objects": int(q1["distribution"]["objects"]),
        "q1_parametric_accepted": int(q1["distribution"]["parametric_accepted"]),
        "q1_kde_fallback": int(q1["distribution"]["kde_fallback"]),
        "q1_all_sku_pairs": int(q1["relationships"]["all_sku_pairs"]),
        "q1_clear_sku_pairs": int((q1_rel["strength_label"] == "clear").sum()),
        "q2_demand_wape": float(q2["forecast_metrics"]["demand_weighted_wape"]),
        "q2_cost_wape": float(q2["forecast_metrics"]["cost_weighted_wape"]),
        "q2_80pct_coverage": float(q2["forecast_metrics"]["mean_80pct_coverage"]),
        "q2_pooled_fallback_categories": int(
            q2["penalty_parameters"]["categories_with_pooled_fallback"]
        ),
        "q2_clearly_negative_elasticity_categories": int(
            (q2_elasticity["identification_label"] == "negative_and_interval_below_zero").sum()
        ),
        "q2_mean_stockout_probability": float(q2["main_strategy"]["mean_stockout_probability"]),
        "q2_demand_satisfaction": float(demand_satisfaction),
        "q2_goodwill_replenishment_min_kg": float(goodwill["weekly_replenishment_kg"].min()),
        "q2_goodwill_replenishment_max_kg": float(goodwill["weekly_replenishment_kg"].max()),
        "q2_goodwill_stockout_min": float(goodwill["mean_stockout_probability"].min()),
        "q2_goodwill_stockout_max": float(goodwill["mean_stockout_probability"].max()),
        "q3_candidate_sku_count": int(q3["candidate_sku_count"]),
        "q3_q1_candidate_coverage": int(q3["q1_diagnostics"]["q1_candidate_sku_coverage"]),
        "q3_clear_candidate_pairs": int(q3["q1_diagnostics"]["q1_pair_strength_counts"]["clear"]),
        "q3_candidate_pairs_covered": int(q3["q1_diagnostics"]["q1_candidate_pairs_covered"]),
        "q3_mean_demand_satisfaction": float(q3["main_strategy"]["mean_demand_satisfaction"]),
        "q3_lower10pct_profit_yuan": float(q3["main_strategy"]["lower10pct_profit_yuan"]),
        "q3_minimum_selection_jaccard": float(q3["sensitivity"]["minimum_selection_jaccard"]),
        "q3_service_satisfaction_min": float(q3["sensitivity"]["service_satisfaction_range"][0]),
        "q3_service_satisfaction_max": float(q3["sensitivity"]["service_satisfaction_range"][1]),
        "q3_expected_profit_min_yuan": float(q3["sensitivity"]["expected_profit_range_yuan"][0]),
        "q3_expected_profit_max_yuan": float(q3["sensitivity"]["expected_profit_range_yuan"][1]),
        "source_files": {
            "q1_summary": str(q1_summary_path.relative_to(root)).replace("\\", "/"),
            "q1_relationships": str(q1_rel_path.relative_to(root)).replace("\\", "/"),
            "q2_summary": str(q2_summary_path.relative_to(root)).replace("\\", "/"),
            "q2_forecast": str(q2_forecast_path.relative_to(root)).replace("\\", "/"),
            "q2_elasticity": str(q2_elasticity_path.relative_to(root)).replace("\\", "/"),
            "q2_daily": str(q2_daily_path.relative_to(root)).replace("\\", "/"),
            "q2_sensitivity": str(q2_sensitivity_path.relative_to(root)).replace("\\", "/"),
            "q3_summary": str(q3_summary_path.relative_to(root)).replace("\\", "/"),
        },
    }
    return metrics


def build_gap_diagnostics(metrics: dict) -> pd.DataFrame:
    source = metrics["source_files"]
    rows = [
        (
            "G01",
            "问题1",
            "参数分布接受率",
            metrics["q1_parametric_accepted"] / metrics["q1_distribution_objects"],
            "比例",
            "仅部分对象可由候选参数分布充分描述，非参数回退占比较高。",
            source["q1_summary"],
        ),
        (
            "G02",
            "问题1",
            "全单品明确关系占比",
            metrics["q1_clear_sku_pairs"] / metrics["q1_all_sku_pairs"],
            "比例",
            "日销量共变证据稀疏，不能据此直接声称因果替代或互补。",
            source["q1_relationships"],
        ),
        (
            "G03",
            "问题2",
            "需求预测加权WAPE",
            metrics["q2_demand_wape"],
            "比例",
            "需求预测误差显著高于成本预测误差，销售量中的缺货截断和外部冲击需要补充观测。",
            source["q2_summary"],
        ),
        (
            "G04",
            "问题2",
            "成本预测加权WAPE",
            metrics["q2_cost_wape"],
            "比例",
            "仅凭历史批发价仍存在成本不确定性，缺少报价时点、可供量和履约信息。",
            source["q2_summary"],
        ),
        (
            "G05",
            "问题2",
            "80%需求区间实际覆盖率",
            metrics["q2_80pct_coverage"],
            "比例",
            "实际覆盖低于名义80%，表明部分需求冲击未被现有信息集解释。",
            source["q2_forecast"],
        ),
        (
            "G06",
            "问题2",
            "价格响应明确为负的品类占比",
            metrics["q2_clearly_negative_elasticity_categories"] / 6,
            "比例",
            "只有两个品类的置信区间完全小于零，促销、陈列和库存混杂尚未分离。",
            source["q2_elasticity"],
        ),
        (
            "G07",
            "问题2",
            "主策略平均缺货概率",
            metrics["q2_mean_stockout_probability"],
            "比例",
            "模拟缺货概率较高，但缺少真实缺货时点，无法用实际运营数据校准。",
            source["q2_summary"],
        ),
        (
            "G08",
            "问题2",
            "主策略期望需求满足率",
            metrics["q2_demand_satisfaction"],
            "比例",
            "满足率由模拟需求计算，现有流水无法直接检验未成交需求。",
            source["q2_daily"],
        ),
        (
            "G09",
            "问题2",
            "商誉系数灵敏度下补货极差",
            metrics["q2_goodwill_replenishment_max_kg"]
            - metrics["q2_goodwill_replenishment_min_kg"],
            "kg/周",
            "管理参数变化会明显改变补货量，需将实际缺货损失与管理偏好分开报告。",
            source["q2_sensitivity"],
        ),
        (
            "G10",
            "问题3",
            "候选单品第一问覆盖率",
            metrics["q3_q1_candidate_coverage"] / metrics["q3_candidate_sku_count"],
            "比例",
            "接近一半候选单品缺少稳定的长期关系画像，关联结果只能用于诊断。",
            source["q3_summary"],
        ),
        (
            "G11",
            "问题3",
            "历史份额扰动下满足率极差",
            metrics["q3_service_satisfaction_max"] - metrics["q3_service_satisfaction_min"],
            "比例",
            "单品份额是第三问最敏感输入，需要可售集合和缺货替代数据。",
            source["q3_summary"],
        ),
        (
            "G12",
            "问题3",
            "历史份额扰动下期望利润极差",
            metrics["q3_expected_profit_max_yuan"] - metrics["q3_expected_profit_min_yuan"],
            "元/日",
            "份额设定改变会导致利润跨越正负区间，表明继续改进求解器不能替代新增行为数据。",
            source["q3_summary"],
        ),
        (
            "G13",
            "问题3",
            "最差10%平均利润",
            metrics["q3_lower10pct_profit_yuan"],
            "元/日",
            "尾部仍为亏损，供应、损耗和真实需求联合数据是校准风险场景的关键。",
            source["q3_summary"],
        ),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "gap_id",
            "question",
            "metric_name",
            "metric_value",
            "unit",
            "interpretation",
            "source_file",
        ],
    )


def build_data_catalog() -> pd.DataFrame:
    rows = [
        {
            "package_id": "inventory_stockout",
            "data_name": "库存与缺货事件",
            "fields": "单品编码、时间戳、期初库存、到货量、上架量、销售量、期末库存、首次缺货时间、缺货原因",
            "collection_granularity": "每次库存变动事件；无法事件化时至少按小时快照",
            "helps_questions": "Q1/Q2/Q3",
            "main_use": "识别删失需求、校准缺货与满足率、构造真实可售集合",
            "privacy_boundary": "仅记录商品和库存事件，不采集顾客身份信息",
        },
        {
            "package_id": "batch_loss_quality",
            "data_name": "批次损耗与品质",
            "fields": "批次号、供应商、到货时间、验收等级、报损量、报损原因、折价时间、折价价格、期末剩余量",
            "collection_granularity": "每批次及每次报损或折价事件",
            "helps_questions": "Q2/Q3",
            "main_use": "由库存平衡估计随货龄和供应来源变化的动态损耗率",
            "privacy_boundary": "供应商字段采用内部编码，合同敏感价格按权限分级",
        },
        {
            "package_id": "supplier_quote_fulfillment",
            "data_name": "供应商报价与履约",
            "fields": "报价时间、供应来源、报价、可供数量、最小订购量、订货量、实到量、到货时间、拒收量",
            "collection_granularity": "每次询价、下单、到货与验收事件",
            "helps_questions": "Q2/Q3",
            "main_use": "改进成本场景，建立真实供货上限、提前期和履约风险",
            "privacy_boundary": "供应商身份和合同条款仅用于内部建模，不对外披露",
        },
        {
            "package_id": "promotion_display_traffic",
            "data_name": "促销、陈列与客流",
            "fields": "原价、实际价、调价原因、促销类型、陈列位置、陈列面数、活动起止、分时客流",
            "collection_granularity": "价格或陈列变动事件；客流按小时汇总",
            "helps_questions": "Q1/Q2/Q3",
            "main_use": "控制价格混杂和曝光差异，解释异常需求并支持小幅对照调价",
            "privacy_boundary": "客流只保留聚合计数，不保留人脸、轨迹或可识别影像",
        },
        {
            "package_id": "anonymous_basket",
            "data_name": "匿名购物篮",
            "fields": "匿名小票编号、时间戳、单品编码、数量、成交价、折扣标记、当时可售集合",
            "collection_granularity": "每笔交易明细",
            "helps_questions": "Q1/Q3",
            "main_use": "区分共同购买与缺货替代，估计给定可售集合的单品需求份额",
            "privacy_boundary": "不采集姓名、电话、会员身份和支付账号；小票编号不可逆匿名化",
        },
        {
            "package_id": "weather_calendar",
            "data_name": "天气、节假日与本地事件",
            "fields": "温度、降雨、湿度、极端天气、节假日、周末、本地大型活动",
            "collection_granularity": "天气按小时或日；事件按起止日期",
            "helps_questions": "Q1/Q2",
            "main_use": "解释外部需求冲击，提高短期预测与区间校准",
            "privacy_boundary": "全部为公开或门店级信息，无个人隐私",
        },
        {
            "package_id": "competitor_price",
            "data_name": "竞争价格",
            "fields": "门店区域、可比商品、价格、促销状态、采集时间、规格换算",
            "collection_granularity": "核心可比单品每日一次或价格变更时",
            "helps_questions": "Q2",
            "main_use": "验证相对价格位置；不能替代本店促销和库存数据",
            "privacy_boundary": "仅采集公开展示价格，遵守平台条款和最小化采集原则",
        },
    ]
    frame = pd.DataFrame(rows)
    frame["package_order"] = frame["package_id"].map(
        {package: idx + 1 for idx, package in enumerate(PACKAGE_ORDER)}
    )
    return frame.sort_values("package_order").reset_index(drop=True)


def build_coverage_matrix() -> pd.DataFrame:
    direct = {
        "inventory_stockout": {"latent_demand", "price_response", "assortment_substitution", "realized_validation"},
        "batch_loss_quality": {"dynamic_loss", "realized_validation"},
        "supplier_quote_fulfillment": {"supply_cost", "realized_validation"},
        "promotion_display_traffic": {"price_response", "external_demand"},
        "anonymous_basket": {"assortment_substitution"},
        "weather_calendar": {"external_demand"},
        "competitor_price": {"competitive_context"},
    }
    columns = list(CAPABILITY_NAMES)
    frame = pd.DataFrame(0, index=PACKAGE_ORDER, columns=columns, dtype=int)
    for package, capabilities in direct.items():
        for capability in capabilities:
            frame.loc[package, capability] = 1
    frame.index.name = "package_id"
    return frame


def enumerate_minimum_portfolios(scenario: Scenario) -> list[tuple[str, ...]]:
    """Enumerate every minimum-cardinality feasible package set."""

    packages = tuple(sorted(PACKAGE_ORDER))
    for size in range(len(packages) + 1):
        feasible = [
            tuple(sorted(combo))
            for combo in itertools.combinations(packages, size)
            if scenario.is_feasible(combo)
        ]
        if feasible:
            return sorted(feasible)
    raise RuntimeError(f"scenario has no feasible portfolio: {scenario.scenario_id}")


def _is_deletion_minimal(scenario: Scenario, portfolio: tuple[str, ...]) -> bool:
    selected = set(portfolio)
    return all(not scenario.is_feasible(selected - {package}) for package in selected)


def build_minimum_portfolio_table() -> pd.DataFrame:
    rows = []
    for scenario in SCENARIOS:
        portfolios = enumerate_minimum_portfolios(scenario)
        for solution_id, portfolio in enumerate(portfolios, start=1):
            rows.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "scenario_name": scenario.scenario_name,
                    "rationale": scenario.rationale,
                    "solution_id": solution_id,
                    "portfolio_size": len(portfolio),
                    "package_ids": "|".join(portfolio),
                    "package_names": "、".join(PACKAGE_SHORT_NAMES[p] for p in portfolio),
                    "capability_count": len(scenario.requirements),
                    "is_feasible": scenario.is_feasible(portfolio),
                    "is_deletion_minimal": _is_deletion_minimal(scenario, portfolio),
                }
            )
    return pd.DataFrame(rows)


def build_sensitivity_analysis() -> pd.DataFrame:
    table = build_minimum_portfolio_table()
    rows = []
    base_packages = set(enumerate_minimum_portfolios(BASE_SCENARIO)[0])
    scenario_count = table["scenario_id"].nunique()
    for package in PACKAGE_ORDER:
        included_scenarios = []
        for scenario_id, group in table.groupby("scenario_id", sort=False):
            if any(package in ids.split("|") for ids in group["package_ids"]):
                included_scenarios.append(scenario_id)
        if len(included_scenarios) == scenario_count:
            tier = "一级：所有情景必选"
            reason = "在全部结构情景的最小解中均出现，结论不依赖情景取舍。"
        elif package in base_packages:
            tier = "二级：核心情景必选"
            reason = "完整核心链路必需，但在明确暂缓相应用途时可阶段性后置。"
        else:
            tier = "三级：扩展情景采用"
            reason = "不影响核心缺口闭环，仅在强化外部或市场背景时增加。"
        rows.append(
            {
                "package_id": package,
                "data_name": PACKAGE_SHORT_NAMES[package],
                "included_scenario_count": len(included_scenarios),
                "scenario_count": scenario_count,
                "inclusion_rate": len(included_scenarios) / scenario_count,
                "included_scenarios": "|".join(included_scenarios),
                "selected_in_base": package in base_packages,
                "priority_tier": tier,
                "tier_reason": reason,
            }
        )
    return pd.DataFrame(rows)


def _configure_plotting():
    plt.rcParams.update(
        {
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"],
            "axes.unicode_minus": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "font.size": 10,
        }
    )


def _save_figure(fig, output: Path, name: str):
    output.mkdir(parents=True, exist_ok=True)
    fig.savefig(output / f"{name}.png", dpi=300, bbox_inches="tight")
    fig.savefig(output / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)


def plot_gap_evidence(metrics: dict, output: Path):
    _configure_plotting()
    labels = [
        "Q1参数分布接受率",
        "Q1明确单品关系占比",
        "Q2需求WAPE",
        "Q2成本WAPE",
        "Q2区间覆盖率",
        "Q2平均缺货概率",
        "Q2需求满足率",
        "Q3候选单品覆盖率",
        "Q3需求满足率",
        "Q3选品最小Jaccard",
    ]
    values = np.array(
        [
            metrics["q1_parametric_accepted"] / metrics["q1_distribution_objects"],
            metrics["q1_clear_sku_pairs"] / metrics["q1_all_sku_pairs"],
            metrics["q2_demand_wape"],
            metrics["q2_cost_wape"],
            metrics["q2_80pct_coverage"],
            metrics["q2_mean_stockout_probability"],
            metrics["q2_demand_satisfaction"],
            metrics["q3_q1_candidate_coverage"] / metrics["q3_candidate_sku_count"],
            metrics["q3_mean_demand_satisfaction"],
            metrics["q3_minimum_selection_jaccard"],
        ]
    )
    colors = ["#2A9D8F", "#2A9D8F", "#E76F51", "#E9C46A", "#457B9D", "#E76F51", "#457B9D", "#2A9D8F", "#457B9D", "#264653"]
    fig, ax = plt.subplots(figsize=(9.2, 5.4))
    y = np.arange(len(labels))
    ax.barh(y, values * 100, color=colors, edgecolor="white", height=0.68)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("比例或误差（%）")
    ax.set_title("前三问可核验诊断证据（原始指标，不合成为主观总分）", fontweight="bold")
    ax.grid(axis="x", color="#D9E2E8", linewidth=0.7, alpha=0.8)
    ax.set_axisbelow(True)
    for idx, value in enumerate(values * 100):
        ax.text(min(value + 1.2, 96), idx, f"{value:.1f}%", va="center", fontsize=9)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    _save_figure(fig, output, "fig_q4_gap_evidence")


def plot_coverage_matrix(matrix: pd.DataFrame, output: Path):
    _configure_plotting()
    fig, ax = plt.subplots(figsize=(10.4, 5.2))
    image = ax.imshow(matrix.to_numpy(), cmap="Blues", vmin=0, vmax=1, aspect="auto")
    del image
    ax.set_xticks(np.arange(len(matrix.columns)), [CAPABILITY_NAMES[c] for c in matrix.columns], rotation=34, ha="right")
    ax.set_yticks(np.arange(len(matrix.index)), [PACKAGE_SHORT_NAMES[p] for p in matrix.index])
    for row in range(matrix.shape[0]):
        for col in range(matrix.shape[1]):
            value = int(matrix.iat[row, col])
            ax.text(col, row, "●" if value else "", ha="center", va="center", color="white", fontsize=12, fontweight="bold")
    ax.set_title("新增数据包与可识别建模能力的直接覆盖关系", fontweight="bold")
    ax.set_xticks(np.arange(-0.5, matrix.shape[1], 1), minor=True)
    ax.set_yticks(np.arange(-0.5, matrix.shape[0], 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.2)
    ax.tick_params(which="minor", bottom=False, left=False)
    fig.tight_layout()
    _save_figure(fig, output, "fig_q4_data_gap_matrix")


def plot_priority_robustness(sensitivity: pd.DataFrame, output: Path):
    _configure_plotting()
    ordered = sensitivity.set_index("package_id").loc[PACKAGE_ORDER].reset_index()
    palette = {
        "一级：所有情景必选": "#264653",
        "二级：核心情景必选": "#2A9D8F",
        "三级：扩展情景采用": "#E9C46A",
    }
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    bars = ax.barh(
        np.arange(len(ordered)),
        ordered["inclusion_rate"] * 100,
        color=[palette[t] for t in ordered["priority_tier"]],
        edgecolor="white",
        height=0.68,
    )
    ax.set_yticks(np.arange(len(ordered)), ordered["data_name"])
    ax.invert_yaxis()
    ax.set_xlim(0, 105)
    ax.set_xlabel("进入七个结构情景最小组合的比例（%）")
    ax.set_title("采集优先级的结构情景稳健性", fontweight="bold")
    ax.grid(axis="x", color="#D9E2E8", linewidth=0.7)
    ax.set_axisbelow(True)
    for bar, count in zip(bars, ordered["included_scenario_count"]):
        ax.text(bar.get_width() + 1.0, bar.get_y() + bar.get_height() / 2, f"{count}/7", va="center", fontsize=9)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    _save_figure(fig, output, "fig_q4_priority_robustness")


def run_model(root: Path = ROOT, output_root: Path | None = None) -> dict:
    output_root = Path(output_root) if output_root is not None else root / "questions/q4/outputs"
    tables = output_root / "tables"
    results = output_root / "results"
    figures = output_root / "figures"
    for directory in (tables, results, figures):
        directory.mkdir(parents=True, exist_ok=True)

    metrics = load_source_metrics(root)
    diagnostics = build_gap_diagnostics(metrics)
    catalog = build_data_catalog()
    coverage = build_coverage_matrix()
    portfolios = build_minimum_portfolio_table()
    sensitivity = build_sensitivity_analysis()

    diagnostics.to_csv(tables / "q4_gap_diagnostics.csv", index=False, encoding="utf-8-sig")
    catalog.to_csv(tables / "q4_data_catalog.csv", index=False, encoding="utf-8-sig")
    coverage.reset_index().to_csv(tables / "q4_coverage_matrix.csv", index=False, encoding="utf-8-sig")
    portfolios.to_csv(tables / "q4_minimum_portfolios.csv", index=False, encoding="utf-8-sig")
    sensitivity.to_csv(tables / "q4_sensitivity_analysis.csv", index=False, encoding="utf-8-sig")

    plot_gap_evidence(metrics, figures)
    plot_coverage_matrix(coverage, figures)
    plot_priority_robustness(sensitivity, figures)

    base_portfolio = enumerate_minimum_portfolios(BASE_SCENARIO)[0]
    summary = {
        "model": "Q1-Q3 evidence audit + logical capability coverage + minimum-cardinality portfolio + structural scenario sensitivity",
        "principle": "No ex-ante value is assigned before new data exist; future value is measured by same-window incremental backtesting.",
        "invented_value_parameter_count": 0,
        "diagnostic_metric_count": int(len(diagnostics)),
        "candidate_data_package_count": int(len(catalog)),
        "base_capability_count": int(len(BASE_SCENARIO.requirements)),
        "sensitivity_scenario_count": int(len(SCENARIOS)),
        "base_portfolio": {
            "package_count": len(base_portfolio),
            "package_ids": list(base_portfolio),
            "package_names": [PACKAGE_SHORT_NAMES[p] for p in base_portfolio],
            "is_feasible": BASE_SCENARIO.is_feasible(base_portfolio),
            "is_deletion_minimal": _is_deletion_minimal(BASE_SCENARIO, base_portfolio),
        },
        "priority_tiers": {
            tier: group["package_id"].tolist()
            for tier, group in sensitivity.groupby("priority_tier", sort=False)
        },
        "key_evidence": {
            key: value for key, value in metrics.items() if key != "source_files"
        },
        "source_files": metrics["source_files"],
        "post_collection_evaluation": {
            "method": "rolling-origin incremental backtest with unchanged Q1-Q3 model boundaries",
            "metrics": [
                "demand_wape_reduction",
                "cost_wape_reduction",
                "coverage_calibration_improvement",
                "realized_profit_change",
                "demand_satisfaction_change",
                "lower10pct_profit_change",
            ],
            "ranking_rule": "Pareto dominance; use net value only after actual acquisition cost is observed",
        },
    }
    (results / "q4_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    result = run_model()
    print(json.dumps(result, ensure_ascii=False, indent=2))
