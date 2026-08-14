# Question 4 Data-Value Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a reproducible Question 4 model that diagnoses data gaps from the verified Q1-Q3 outputs, selects a minimum nonredundant collection portfolio without invented value weights, validates robustness, and produces a detailed Chinese modeling paper in Markdown and Word.

**Architecture:** `q4_model.py` reads only checked Q1-Q3 result files, builds a traceable diagnostic evidence table, evaluates explicit logical capability constraints over candidate data packages, enumerates minimum-cardinality portfolios, and performs scenario-based inclusion sensitivity. A separate validator checks source consistency, portfolio feasibility/minimality, output completeness, and numeric ranges. The paper source consumes generated tables and figures; `build_q4_paper.py` turns the checked Markdown into a polished A4 DOCX.

**Tech Stack:** Python 3.10+, standard library, pandas, numpy, matplotlib, unittest, python-docx; existing repository CSV/JSON outputs; Git.

## Global Constraints

- Reuse Q1-Q3 outputs; do not retrain or alter the first three questions.
- Do not fabricate observations for data that have not yet been collected.
- Do not use Sobol, AHP, TOPSIS, subjective benefit weights, assumed acquisition costs, or ex-ante EVSI as the main model.
- Priority must come from transparent capability constraints, minimum-cardinality coverage, dominance, and scenario sensitivity.
- Preserve the unrelated untracked `.claude/` directory and stage only Q4-related files and this plan.
- Generate one final DOCX and render every page before delivery.

---

### Task 1: Define tested diagnostics and portfolio interfaces

**Files:**
- Create: `questions/q4/code/test_q4_model.py`
- Create: `questions/q4/code/q4_model.py`

**Interfaces:**
- Produces: `load_source_metrics(root: Path) -> dict`, `build_gap_diagnostics(metrics: dict) -> pandas.DataFrame`, `build_data_catalog() -> pandas.DataFrame`, `build_coverage_matrix() -> pandas.DataFrame`, `enumerate_minimum_portfolios(packages, capabilities, scenario) -> list[tuple[str, ...]]`, and `run_model(root: Path) -> dict`.

- [ ] **Step 1: Write failing tests for exact Q1-Q3 metric extraction, required catalog columns, and missing-source errors.**
- [ ] **Step 2: Run `python -m unittest questions.q4.code.test_q4_model -v` and verify failures are caused by the absent implementation.**
- [ ] **Step 3: Implement the minimal loaders and deterministic catalog definitions.**
- [ ] **Step 4: Re-run the focused tests and confirm they pass.**

### Task 2: Implement minimum coverage and sensitivity analysis

**Files:**
- Modify: `questions/q4/code/test_q4_model.py`
- Modify: `questions/q4/code/q4_model.py`

**Interfaces:**
- Consumes: deterministic data packages and logical capabilities from Task 1.
- Produces: exact minimum portfolios, package inclusion frequencies, dominance flags, and a JSON summary with no assumed information-value parameters.

- [ ] **Step 1: Add failing tests for base-portfolio feasibility, deletion minimality, dominated optional packages, and scenario inclusion rates.**
- [ ] **Step 2: Run focused tests and verify the new assertions fail.**
- [ ] **Step 3: Implement exhaustive subset enumeration and scenario sensitivity.**
- [ ] **Step 4: Run the full Q4 unit test module and confirm all tests pass.**
- [ ] **Step 5: Run `q4_model.py` to generate CSV/JSON outputs and three figures under `questions/q4/outputs/`.**

### Task 3: Add independent output validation

**Files:**
- Create: `questions/q4/code/validate_q4_outputs.py`
- Modify: `questions/q4/code/test_q4_model.py`

**Interfaces:**
- Consumes: generated Q4 CSV/JSON/PNG/PDF outputs and original Q1-Q3 sources.
- Produces: `questions/q4/outputs/results/q4_validation.json` and `validation_report.md` with named checks and pass/fail status.

- [ ] **Step 1: Add a failing integration test that expects validation checks for source integrity, finite metrics, complete gap coverage, minimal portfolios, stable tier assignment, and figure existence.**
- [ ] **Step 2: Verify the test fails because the validator is absent.**
- [ ] **Step 3: Implement the validator with independent recomputation of key values.**
- [ ] **Step 4: Run unit tests, the model, and the validator; confirm zero failures.**

### Task 4: Write the detailed mathematical modeling paper source

**Files:**
- Create: `questions/q4/report/第四问建模论文.md`
- Modify: `questions/q4/modeling/README.md`
- Modify: `questions/q4/README.md`
- Modify: `questions/q4/code/README.md`
- Modify: `questions/q4/report/README.md`
- Modify: `questions/q4/outputs/README.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: Q4 generated metrics, figures, sensitivity outputs, the approved model design, and verified 2021-2022 primary literature.
- Produces: complete Chinese sections for problem restatement, analysis, assumptions, symbols, model construction, solution, result analysis, validation, sensitivity, evaluation, and references.

- [ ] **Step 1: Draft source-backed problem restatement and 2-3 subproblems without copying the prompt.**
- [ ] **Step 2: Write total-to-part problem analysis and a textual flowchart.**
- [ ] **Step 3: Write 3-5 assumptions with rationale and model impact, plus a three-line symbol table.**
- [ ] **Step 4: Derive the censored-demand correction, logical coverage model, minimum portfolio model, incremental backtest protocol, and Pareto rule.**
- [ ] **Step 5: Insert exact generated results, validation evidence, sensitivity interpretation, and evidence-backed strengths/limitations.**
- [ ] **Step 6: Update all Q4 README files with reproduction commands and boundaries.**

### Task 5: Generate and visually verify the Word paper

**Files:**
- Create: `questions/q4/report/build_q4_paper.py`
- Create: `questions/q4/report/第四问建模论文.docx`

**Interfaces:**
- Consumes: the checked Markdown paper and Q4 figures/tables.
- Produces: one A4 Chinese academic DOCX using the `narrative_proposal` preset with named A4/Chinese typography overrides.

- [ ] **Step 1: Mark one DOCX creation operation using the bundled artifact marker.**
- [ ] **Step 2: Implement the DOCX builder with explicit styles, real list numbering, exact table geometry, equations, captions, page numbers, and embedded figures.**
- [ ] **Step 3: Generate the DOCX with the bundled Python runtime.**
- [ ] **Step 4: Render it with the packaged `render_docx.py`, inspect every page PNG, and fix any clipping, table, spacing, font, or page-break defect.**
- [ ] **Step 5: Run structural checks for headings, tables, images, metadata, and placeholder text.**

### Task 6: Final verification, commit, and GitHub synchronization

**Files:**
- Verify all Task 1-5 files; do not stage `.claude/`.

**Interfaces:**
- Produces: a task-scoped commit on `codex/q4-data-value-model`, a pushed remote branch, and a draft pull request when GitHub authentication permits.

- [ ] **Step 1: Run Q4 unit tests, model generation, independent validation, DOCX generation, render QA, `git diff --check`, and inspect `git diff --stat`.**
- [ ] **Step 2: Review every changed path against the requested scope and stage explicit Q4/plan/root README paths only.**
- [ ] **Step 3: Commit with a concise Q4 description.**
- [ ] **Step 4: Verify `gh --version` and `gh auth status`, then push the current branch with tracking.**
- [ ] **Step 5: Open a draft PR to the remote default branch when authenticated; otherwise report the exact authentication blocker after the branch push attempt.**

