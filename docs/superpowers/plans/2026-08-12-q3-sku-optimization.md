# Question 3 SKU Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible 2023-07-01 SKU selection, pricing, and replenishment model that uses the existing Q1/Q2 results correctly, satisfies the 27–33 SKU and 2.5 kg constraints, and produces validated decision tables.

**Architecture:** A single Q3 model module owns candidate extraction, empirical-Bayes SKU allocation, discrete price-grid construction, scenario conversion, lexicographic MILP solving, and out-of-sample strategy evaluation. It imports Q2 forecasting/scenario functions as the category-level source of truth, treats Q1 only as an optional diagnostic, and writes machine-checkable CSV/JSON outputs plus a validator.

**Tech Stack:** Python 3, pandas, NumPy, SciPy `optimize.milp`/HiGHS, unittest, existing Q2 forecasting code.

## Global Constraints

- Use only SKUs with positive retail sales from 2023-06-24 through 2023-06-30; wholesale-only activity cannot create a candidate.
- Reuse Q2 category elasticities and correlated residual scenarios. Do not fit unstable SKU-level elasticity.
- Do not put the sparse Q1 association graph in the primary objective; report it only as a diagnostic/sensitivity item.
- Demand satisfaction has lexicographic priority over profit. Order cost is charged on ordered quantity, while loss reduces sellable quantity.
- Every derived table must retain SKU code, SKU name, category, units, and calculation provenance.

---

## Task 1: Lock helper contracts with failing tests

**Files:**
- Create: `questions/q3/code/test_q3_model.py`
- Create: `questions/q3/code/q3_model.py`

- [ ] Write tests proving candidate dates and positive-sale filtering.
- [ ] Write tests proving empirical-Bayes shares are nonnegative and sum to one by category.
- [ ] Write tests proving sparse-SKU price grids fall back to category information and remain inside Q2 bounds.
- [ ] Write tests for deterministic representative-scenario selection and tight finite big-M values.
- [ ] Run `python -m unittest questions/q3/code/test_q3_model.py` and record the expected initial import failures.

## Task 2: Implement data preparation and scenario construction

**Files:**
- Modify: `questions/q3/code/q3_model.py`
- Test: `questions/q3/code/test_q3_model.py`

- [ ] Implement `identify_candidates`, `estimate_dynamic_shares`, and leakage-free rolling selection of the shrinkage strength.
- [ ] Implement `build_price_grid` from SKU markup quantiles with category fallback and Q2 decision bounds.
- [ ] Implement SKU reference price and cost forecasts, loss-rate joins, whole-day share bootstrap, and category-to-SKU demand conversion.
- [ ] Implement deterministic representative-scenario selection while retaining lower/median/upper aggregate-demand regimes.
- [ ] Run the helper test subset until green.

## Task 3: Implement and test the lexicographic MILP

**Files:**
- Modify: `questions/q3/code/q3_model.py`
- Test: `questions/q3/code/test_q3_model.py`

- [ ] Build indexed variables for selection, price choice, order quantity, price-level scenario sales, unmet category demand, VaR, and tail-loss excess.
- [ ] Enforce fixed assortment size, exactly one price for selected SKUs, 2.5 kg minimum order, data-derived upper bounds, scenario demand limits, and loss-adjusted inventory limits.
- [ ] Stage 1 minimizes equal-category normalized unmet demand.
- [ ] Stage 2 constrains service to the Stage-1 optimum plus one scenario standard error and maximizes expected/lower-tail profit.
- [ ] Add tiny-fixture tests for assortment size, minimum order, price linking, loss accounting, and lower-tail profit.
- [ ] Run all Q3 unit tests until green.

## Task 4: Integrate the real project data

**Files:**
- Modify: `questions/q3/code/q3_model.py`
- Create outputs under: `questions/q3/outputs/`

- [ ] Import Q2 forecasts, elasticities, joint demand/cost residual scenarios, and price-bound tables.
- [ ] Assert the real candidate population is 49 and all joins are one-to-one with no missing category, cost, price, or loss-rate fields.
- [ ] Solve the 27–33 SKU frontier on representative scenarios and evaluate every fixed strategy on the full Q2 scenario set.
- [ ] Select the final assortment by lexicographic service, then risk-adjusted profit, with deterministic tie-breaking.
- [ ] Write candidate diagnostics, price grid, K frontier, daily strategy, category summary, comparison, sensitivity, summary JSON, and validation JSON.

## Task 5: Validate outputs and document usage

**Files:**
- Create: `questions/q3/code/validate_q3_outputs.py`
- Modify: `questions/q3/README.md`
- Modify: `questions/q3/code/README.md`
- Modify: `questions/q3/modeling/README.md`
- Modify: `questions/q3/outputs/README.md`
- Modify: `questions/q3/report/README.md`
- Modify: `README.md`

- [ ] Validate 27–33 selections, one price per SKU, all selected quantities at least 2.5 kg, price-grid membership, finite outputs, scenario identities, category totals, and profit/service reconciliations.
- [ ] Compare against a transparent recent-sales baseline under identical full scenarios.
- [ ] Document assumptions, formulas, commands, file schema, and interpretation without claiming unsupported Q1 effects.
- [ ] Run Q1, Q2, and Q3 validators and all unit tests.
- [ ] Run `git diff --check` and inspect the final diff for accidental data or unrelated changes.
