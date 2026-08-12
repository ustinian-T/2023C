#!/usr/bin/env python3
"""Deterministic cross-file validation for the Q1 delivery."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import pandas as pd
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
TABLES = OUTPUTS / "tables"
FIGURES = OUTPUTS / "figures"
RESULTS = OUTPUTS / "results"
WORKBOOKS = OUTPUTS / "workbooks"
REPORT = ROOT / "report" / "main.tex"


def check(condition: bool, message: str, checks: list[dict]) -> None:
    checks.append({"check": message, "passed": bool(condition)})
    if not condition:
        raise AssertionError(message)


def main() -> None:
    checks: list[dict] = []
    summary = json.loads((RESULTS / "q1_summary.json").read_text(encoding="utf-8"))
    edges = pd.read_csv(TABLES / "tab_q1_sku_network_edges.csv")
    pairs = pd.read_csv(TABLES / "tab_q1_sku_pair_measures.csv")
    nodes = pd.read_csv(TABLES / "tab_q1_sku_node_metrics.csv")
    activity = pd.read_csv(TABLES / "tab_q1_sku_activity_filter.csv")
    sensitivity = pd.read_csv(TABLES / "tab_q1_sku_sensitivity.csv")
    category_edges = pd.read_csv(TABLES / "tab_q1_category_network_edges.csv")

    check(len(activity) == summary["all_sku_count"], "all SKU count agrees", checks)
    check(int(activity["included"].sum()) == summary["selected_sku_count"], "selected SKU count agrees", checks)
    check(len(edges) == summary["sku_network"]["final_stable_edges"], "final SKU edge count agrees", checks)
    check(int((edges["partial_corr"] > 0).sum()) == summary["sku_network"]["positive_final_edges"], "positive edge count agrees", checks)
    check(int((edges["partial_corr"] < 0).sum()) == summary["sku_network"]["negative_final_edges"], "negative edge count agrees", checks)
    check(edges["final_stable_edge"].astype(bool).all(), "edge table contains only final edges", checks)
    check((edges["mic_approx"] >= summary["sku_network"]["mic_threshold"] - 1e-12).all(), "all edges pass MIC threshold", checks)
    check((edges["bootstrap_same_sign_rate"] >= summary["config"]["bootstrap_stability_cutoff"]).all(), "all edges pass bootstrap threshold", checks)
    check(int(pairs["mic_candidate"].sum()) == summary["sku_network"]["mic_candidates"], "MIC candidate count agrees", checks)
    check(int((nodes["degree"] > 0).sum()) == 12, "connected SKU node count is 12", checks)
    check(len(category_edges) == summary["category_network"]["final_stable_edges"], "category edge count agrees", checks)
    check(summary["sku_network"]["precision_min_eigenvalue"] > 0, "SKU precision matrix is positive definite", checks)
    check(summary["category_network"]["precision_min_eigenvalue"] > 0, "category precision matrix is positive definite", checks)

    alpha_rows = sensitivity.loc[sensitivity["parameter"] == "alpha_factor"]
    check((alpha_rows["edge_count"] == 10).all(), "alpha +/-20% keeps 10 candidate intersections", checks)
    check((alpha_rows["jaccard_vs_base"] == 1).all(), "alpha +/-20% Jaccard equals 1", checks)

    figure_bases = [
        "fig_q1_stl_decomposition",
        "fig_q1_category_distributions",
        "fig_q1_mic_graphical_lasso",
        "fig_q1_sku_network",
        "fig_q1_category_partial_matrix",
        "fig_q1_robustness",
    ]
    image_details = []
    for base in figure_bases:
        png = FIGURES / f"{base}.png"
        pdf = FIGURES / f"{base}.pdf"
        check(png.exists() and png.stat().st_size > 50_000, f"{base} PNG exists and is nontrivial", checks)
        check(pdf.exists() and pdf.stat().st_size > 10_000, f"{base} PDF exists and is nontrivial", checks)
        with Image.open(png) as image:
            width, height = image.size
            dpi = image.info.get("dpi", (0, 0))
        check(width >= 3000 and height >= 1800, f"{base} raster dimensions are publication grade", checks)
        image_details.append({"base": base, "width": width, "height": height, "dpi": dpi})

    workbook = WORKBOOKS / "q1_model_results.xlsx"
    check(workbook.exists() and workbook.stat().st_size > 20_000, "archived result workbook exists", checks)
    check(zipfile.is_zipfile(workbook), "archived result workbook is a valid XLSX zip container", checks)
    with zipfile.ZipFile(workbook) as archive:
        check("xl/workbook.xml" in archive.namelist(), "archived result workbook contains workbook.xml", checks)

    paper = REPORT
    check(paper.exists() and paper.stat().st_size > 5_000, "report/main.tex exists and is substantive", checks)
    paper_text = paper.read_text(encoding="utf-8")
    check("待补充" not in paper_text and "TODO" not in paper_text, "paper has no placeholders", checks)

    tex_engines = [name for name in ("xelatex", "lualatex", "tectonic") if shutil.which(name)]
    report = {
        "status": "PASS",
        "check_count": len(checks),
        "checks": checks,
        "image_details": image_details,
        "report_compilation": {
            "checked": False,
            "available_engines": tex_engines,
            "note": "LaTeX compilation is outside this validator; compile report/main.tex separately with a Chinese-capable engine.",
        },
    }
    (RESULTS / "output_validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"status": report["status"], "check_count": report["check_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
