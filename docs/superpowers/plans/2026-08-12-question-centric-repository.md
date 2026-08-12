# Question-Centric Repository Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the 2023 C problem repository so each of the four questions has an isolated code, modeling, report, and output area while all questions share one canonical problem statement and data tree.

**Architecture:** The repository root owns shared inputs under `problem/` and `data/`; `questions/q1` through `questions/q4` own question-specific implementation and artifacts. Existing Q1 files move without changing the statistical model, and Q1 scripts resolve their question root from `__file__` plus the repository data root explicitly.

**Tech Stack:** Git, Python 3, pandas/scikit-learn scientific stack, MATLAB, LaTeX, Markdown, XLSX/PDF source files.

## Global Constraints

- Preserve all existing Q1 code, numerical results, figures, tables, workbook, modeling notes, and report content.
- Do not modify the contents of the user-provided PDF or four Excel attachments.
- Track exactly one copy of each raw attachment in `data/raw/`.
- Keep Q2-Q4 explicitly marked as unsolved; do not fabricate implementations or results.
- Use `git mv` for tracked-file migrations whenever possible.
- Push the completed work to `origin/main` only after fresh verification succeeds.

---

### Task 1: Add shared problem and raw-data sources

**Files:**
- Create: `problem/C题.pdf`
- Create: `problem/README.md`
- Create: `data/README.md`
- Create: `data/raw/附件1.xlsx`
- Create: `data/raw/附件2.xlsx`
- Create: `data/raw/附件3.xlsx`
- Create: `data/raw/附件4.xlsx`
- Move: `蔬菜数据预处理结果包/*` to `data/processed/*`

**Interfaces:**
- Consumes: Source files in `H:/2026暑期数学建模培训/2023C/C题/` and the tracked preprocessing bundle.
- Produces: Canonical shared inputs at `problem/C题.pdf`, `data/raw/*.xlsx`, and `data/processed/*`.

- [ ] **Step 1: Record source sizes and hashes**

Run:

```powershell
Get-FileHash 'H:\2026暑期数学建模培训\2023C\C题\C题.pdf','H:\2026暑期数学建模培训\2023C\C题\附件1.xlsx','H:\2026暑期数学建模培训\2023C\C题\附件2.xlsx','H:\2026暑期数学建模培训\2023C\C题\附件3.xlsx','H:\2026暑期数学建模培训\2023C\C题\附件4.xlsx' -Algorithm SHA256
```

Expected: five SHA-256 records with no missing-file error.

- [ ] **Step 2: Create canonical directories and copy immutable sources**

Run `New-Item -ItemType Directory -Force` for `problem`, `data/raw`, and `data/processed`; use `Copy-Item -LiteralPath` for the PDF and four workbooks. Do not transform or open-save any source file.

- [ ] **Step 3: Move the tracked preprocessing bundle**

Run:

```powershell
git mv -- '蔬菜数据预处理结果包/*' 'data/processed/'
```

If shell wildcard handling prevents this form, move each tracked file with explicit `git mv` commands generated from `git ls-files '蔬菜数据预处理结果包/*'`.

- [ ] **Step 4: Document shared inputs**

Create `problem/README.md` with the exact four task statements and attachment roles. Create `data/README.md` explaining that `raw/` is immutable competition input and `processed/` is the current Q1-ready dataset.

- [ ] **Step 5: Verify byte identity and file size**

Run `Get-FileHash` for source and destination pairs and assert equal SHA-256 values. Confirm `data/raw/附件2.xlsx` is below GitHub's 100 MB single-file limit.

- [ ] **Step 6: Commit shared inputs**

```powershell
git add -- problem data
git commit -m "chore: centralize problem statement and shared data"
```

---

### Task 2: Move Q1 into its isolated question module

**Files:**
- Move: `src/*` to `questions/q1/code/*`
- Move: `modeling/*` to `questions/q1/modeling/*`
- Move: `paper/*` to `questions/q1/report/*`
- Move: `figures/*` to `questions/q1/outputs/figures/*`
- Move: `tables/*` to `questions/q1/outputs/tables/*`
- Move: `results/*` to `questions/q1/outputs/results/*`
- Move: `outputs/q1_model/q1_model_results.xlsx` to `questions/q1/outputs/workbooks/q1_model_results.xlsx`
- Move: `README_Q1.md` to `questions/q1/README.md`
- Move: `problem/problem_parse.md` to `questions/q1/modeling/problem_scope.md`
- Modify: `questions/q1/code/q1_model.py`
- Modify: `questions/q1/code/plot_q1_matlab.m`
- Modify: `questions/q1/code/validate_q1_outputs.py`
- Modify: `questions/q1/report/main.tex`
- Modify: `questions/q1/README.md`
- Modify: `questions/q1/modeling/q1_modeling_idea.md`

**Interfaces:**
- Consumes: `data/processed/processed_daily_sku.csv` and `data/processed/processed_daily_category.csv`.
- Produces: Q1 artifacts beneath `questions/q1/outputs/{tables,results,figures,workbooks}`.

- [ ] **Step 1: Capture the tracked Q1 file inventory**

Run `git ls-files` for every source directory and save the expected counts in the terminal log. This provides a before/after loss check without adding a generated inventory file.

- [ ] **Step 2: Create Q1 destinations and move tracked files**

Use explicit `git mv` operations for the eight source groups and two standalone Markdown files. Remove old directories only after they are confirmed empty.

- [ ] **Step 3: Update Python path resolution**

In `q1_model.py`, retain `--root` but define its default as the Q1 directory. Change default input discovery to prefer `<repository>/data/processed`. Define output paths as:

```python
outputs = root / "outputs"
tables = outputs / "tables"
results = outputs / "results"
```

In `validate_q1_outputs.py`, define:

```python
ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
TABLES = OUTPUTS / "tables"
FIGURES = OUTPUTS / "figures"
RESULTS = OUTPUTS / "results"
WORKBOOKS = OUTPUTS / "workbooks"
REPORT = ROOT / "report" / "main.tex"
```

- [ ] **Step 4: Update MATLAB and LaTeX paths**

Set MATLAB `tableDir` and `figureDir` below `<q1>/outputs`. Change every LaTeX image reference from `../figures/` to `../outputs/figures/`.

- [ ] **Step 5: Update Q1 documentation links and commands**

Use repository-root commands:

```powershell
python questions\q1\code\q1_model.py
matlab -batch "run('questions/q1/code/plot_q1_matlab.m')"
python questions\q1\code\validate_q1_outputs.py
```

Replace old `src/`, `tables/`, `results/`, `figures/`, `paper/`, and `outputs/q1_model/` references with their Q1 module paths or Q1-relative equivalents.

- [ ] **Step 6: Run Q1 regression validation**

Run:

```powershell
C:\Windows\py.exe -3 questions\q1\code\validate_q1_outputs.py
```

Expected: JSON containing `"status": "PASS"` and `"check_count": 38`.

- [ ] **Step 7: Commit Q1 isolation**

```powershell
git add -- questions/q1
git commit -m "refactor: isolate question one implementation"
```

---

### Task 3: Add Q2-Q4 scaffolds and root navigation

**Files:**
- Modify: `README.md`
- Create: `questions/q2/README.md`
- Create: `questions/q2/code/README.md`
- Create: `questions/q2/modeling/README.md`
- Create: `questions/q2/report/README.md`
- Create: `questions/q2/outputs/README.md`
- Create: corresponding five files under `questions/q3/`
- Create: corresponding five files under `questions/q4/`

**Interfaces:**
- Consumes: Exact problem statements from `problem/README.md`.
- Produces: Navigable question modules with unambiguous status and responsibilities.

- [ ] **Step 1: Write the root project guide**

Replace the Q1-only root README with a four-question status table, tree overview, shared-data contract, Q1 quick-start commands, and links to each question README.

- [ ] **Step 2: Write each question overview**

For Q2, Q3, and Q4, state the exact problem objective, expected shared inputs, expected artifact classes, and `目录已建立，求解尚未开始` status. Q2 documents the seven-day category replenishment/pricing horizon; Q3 documents the 27-33 SKU and 2.5 kg constraints; Q4 documents the additional-data recommendation deliverable.

- [ ] **Step 3: Add responsibility markers for empty functional directories**

Each child README explains what belongs in that directory and repeats that no implementation or result currently exists. Do not include placeholder markers, invented filenames, or invented conclusions.

- [ ] **Step 4: Validate navigation links**

Run a Python Markdown-link check over repository-local links and assert all referenced paths exist.

- [ ] **Step 5: Commit navigation and scaffolds**

```powershell
git add -- README.md questions/q2 questions/q3 questions/q4
git commit -m "docs: scaffold remaining modeling questions"
```

---

### Task 4: Verify and publish the complete restructure

**Files:**
- Modify if needed: `.gitignore`
- Verify: all tracked and untracked repository paths

**Interfaces:**
- Consumes: Completed Tasks 1-3.
- Produces: A clean, validated `main` branch synchronized to `origin/main`.

- [ ] **Step 1: Remove only agent-generated temporary PDF previews**

Resolve and verify that `tmp/pdfs/c_problem_page_1.png` is inside the repository `tmp/` directory, then remove it. Do not delete any user-authored files.

- [ ] **Step 2: Check obsolete paths and repository structure**

Search tracked text for old root-level path references. Assert the existence of Q1-Q4 module READMEs, four raw workbooks, the problem PDF, Q1 code, Q1 report, and each Q1 output class.

- [ ] **Step 3: Run full Q1 model when dependencies are available**

Run:

```powershell
C:\Windows\py.exe -3 questions\q1\code\q1_model.py
C:\Windows\py.exe -3 questions\q1\code\validate_q1_outputs.py
```

Expected: the model exits zero and validation reports PASS with 38 checks. If a required runtime dependency is unavailable, report the exact missing package and still run the non-mutating output validator against migrated artifacts.

- [ ] **Step 4: Run repository integrity checks**

Run `git diff --check`, the Markdown-link check, file hash comparison, `git status --short`, and a largest-tracked-file size check. Review the complete diff before committing any small corrective changes.

- [ ] **Step 5: Commit final corrections if present**

Stage only task-related files and use a narrowly scoped commit message such as `fix: complete repository structure migration`. Skip this commit when there are no remaining changes.

- [ ] **Step 6: Rebase and push**

Run:

```powershell
git pull --rebase origin main
git push origin main
```

Expected: push exits zero without rejection.

- [ ] **Step 7: Verify remote synchronization**

Run `git fetch origin main`, compare `git rev-parse main` with `git rev-parse origin/main`, and confirm a clean worktree.
