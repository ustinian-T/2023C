# Q3 Validation and Sensitivity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reproducible representative-scenario validation, six-fold stability diagnostics, and four-factor re-optimization sensitivity analysis to the completed Q3 SKU model.

**Architecture:** Keep the MILP and evaluation source of truth in `q3_model.py`. Add pure helpers for fold statistics and variant definitions, then orchestrate nine unique K=33 re-solves from the already constructed 600 scenarios; extend the independent validator to enforce the approved thresholds and write two new CSV tables.

**Tech Stack:** Python 3, pandas, NumPy, SciPy `optimize.milp`/HiGHS, unittest, existing Q1/Q2/Q3 outputs.

## Global Constraints

- Keep the 49-SKU candidate set, K=33 sensitivity comparison, 2.5 kg minimum order, Q2 total replenishment cap, and Q1 diagnostic-only use unchanged.
- Every sensitivity variant must re-solve the two-stage MILP and be evaluated on all 600 Q2 joint scenarios.
- Use nine unique variants: risk weights 0/0.25/0.50, elasticity scales 0.80/1.00/1.20, historical share weights 0.25/0.50/0.75, and order-cap factors 0.85/0.925/1.00, with the common baseline solved once.
- Fail before GitHub push on infeasibility, non-finite values, hard-constraint violations, representative/full service gap above 0.03, or six-fold service standard deviation above 0.05.

---

### Task 1: Pure validation and variant contracts

**Files:**
- Modify: `questions/q3/code/test_q3_model.py`
- Modify: `questions/q3/code/q3_model.py`

**Interfaces:**
- Consumes: `evaluate_strategy(...) -> dict`, scenario-level profit and service arrays.
- Produces: `summarize_scenario_folds(service_loss: np.ndarray, profit: np.ndarray, folds: int = 6) -> pd.DataFrame`; `build_sensitivity_variants() -> list[dict]`; `selection_jaccard(left: Iterable[str], right: Iterable[str]) -> float`.

- [ ] Write tests that require six non-overlapping deterministic folds, finite fold metrics, exact nine-variant labels without duplicate baseline, and correct Jaccard values including two empty sets.
- [ ] Run `python -m unittest discover -s questions\q3\code -p "test_q3_model.py" -v` and confirm failures name the missing helpers.
- [ ] Implement the three pure helpers with input validation; fold rows contain `fold`, `scenario_count`, `mean_demand_satisfaction`, `expected_profit_yuan`, and `lower10pct_profit_yuan`.
- [ ] Rerun the Q3 unit suite and require all tests to pass.

### Task 2: Nine-variant re-optimization

**Files:**
- Modify: `questions/q3/code/q3_model.py`
- Test: `questions/q3/code/test_q3_model.py`

**Interfaces:**
- Consumes: the real pipeline's `share_table`, `q2` bundle, price grid, cost scenarios, representative indices, and `solve_lexicographic_milp(...)`.
- Produces: `run_sensitivity_analysis(...) -> tuple[pd.DataFrame, dict[str, dict]]`, where the table contains parameter group/value, service/profit/order metrics, Jaccard similarity, cap, and solver service fields.

- [ ] Add a small fixture test proving a variant result records the configured risk weight and cap without changing candidate count or bypassing the solver constraints.
- [ ] Implement one-at-a-time perturbations: rebuild share scenarios for share-weight variants, rebuild alternative demand for elasticity variants, pass variant risk weight/cap into the MILP, and evaluate on all 600 matching scenarios.
- [ ] Cache the already solved base K=33 result under the `baseline` variant key; do not solve it a second time.
- [ ] Assert each variant selects 33 SKUs, orders at least 2.5 kg per selected SKU, and stays within its cap before adding its row.
- [ ] Run the Q3 unit suite and require all tests to pass.

### Task 3: Model-validation outputs

**Files:**
- Modify: `questions/q3/code/q3_model.py`
- Create through model execution: `questions/q3/outputs/tables/q3_sensitivity_analysis.csv`
- Create through model execution: `questions/q3/outputs/tables/q3_model_validation.csv`

**Interfaces:**
- Consumes: main solution/evaluation, representative scenarios, baseline evaluation, and nine sensitivity rows.
- Produces: two CSVs and a `model_validation` section in `q3_summary.json`.

- [ ] Compute representative/full service losses for the same fixed main strategy and record signed/absolute gaps.
- [ ] Apply `summarize_scenario_folds` to all 600 main-strategy scenario outcomes and append aggregate mean/std/min/max rows for service, expected profit, and lower-tail profit.
- [ ] Record same-scenario baseline service/profit/tail deltas and Boolean pass flags for the 0.03 gap and 0.05 fold-service standard-deviation thresholds.
- [ ] Run the full model once and confirm all nine sensitivity variants and validation rows are written.

### Task 4: Independent validation and documentation

**Files:**
- Modify: `questions/q3/code/validate_q3_outputs.py`
- Modify: `questions/q3/README.md`
- Modify: `questions/q3/modeling/README.md`
- Modify: `questions/q3/outputs/README.md`
- Modify: `questions/q3/report/README.md`

**Interfaces:**
- Consumes: both new CSVs and `q3_summary.json`.
- Produces: expanded `q3_validation.json` and documented actual sensitivity conclusions.

- [ ] Validate nine unique variants, finite metrics, selected count 33, cap compliance, Jaccard range, baseline/main equality, and non-worsening service as the cap rises within `1e-6`.
- [ ] Validate representative/full absolute service gap at most 0.03, six folds of 100 scenarios, fold service standard deviation at most 0.05, and main service/profit improvements over baseline.
- [ ] Update documentation only with values read from the completed real run, including adverse or non-monotone findings.
- [ ] Run Q3 validation and require every check to pass.

### Task 5: Full regression, commit, and GitHub push

**Files:**
- Verify all changed task files and generated Q3 outputs.

**Interfaces:**
- Consumes: completed implementation and generated outputs.
- Produces: committed branch `codex/q3-sku-optimization` pushed to `origin`.

- [ ] Run Q3 unit tests, Q1 validator, Q2 validator, Q3 validator, `python -m py_compile questions\q3\code\q3_model.py questions\q3\code\validate_q3_outputs.py`, and `git diff --check`.
- [ ] Inspect `git status --short`, generated output sizes, and the staged diff; stage only Q3 implementation, plans/spec, Q3 outputs, and root/Q3 documentation.
- [ ] Commit with a task-specific message after all checks are green.
- [ ] Fetch `origin`, confirm the remote branch has not diverged unexpectedly, then push `codex/q3-sku-optimization` without force.
