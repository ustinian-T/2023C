# 第一问论文 Word 成稿实施计划

> **For agentic workers:** 按本计划在当前会话内逐项执行；不得改动原始附件，不得将相关关系解释为因果关系。

**Goal:** 依据项目已完成的第一问模型、真实输出表与验证记录，生成包含“问题重述、问题分析、模型假设、符号说明、模型建立与求解及结果分析、模型检验、模型评价、参考文献、附录”的中文 Word 论文稿。

**Architecture:** 以 `problem/C题.pdf` 界定题意，以 `questions/q1/outputs/` 为唯一数值证据源，以既有季节画像、K-means 聚类和分层关系分析为模型主线。正文采用数学建模竞赛论文体例，图表从既有结果中筛选，附录给出复现命令、输出索引和关键算法伪代码。

**Tech Stack:** Python 3.11、pandas/numpy/scipy/scikit-learn、python-docx、LibreOffice/Poppler 渲染工具、项目既有 PNG/PDF/CSV/JSON 结果。

## Global Constraints

- 只求解第一问，不延伸第二至第四问。
- 数据范围固定为 2020-07-01 至 2023-06-30；活动单品口径固定为跨度不少于 730 天、正销售日不少于 90 天、累计销量不少于 100 kg。
- 主模型固定为“两部分布—季节画像—K-means 季节型聚类—四层级四指标关系分析”。
- 关系结论只解释为统计共变、季节同步、结构竞争或活跃期重合，不作因果推断。
- 所有关键数字必须能追溯至 CSV/JSON 或重新运行的验证结果。
- 最终仅交付一个 `.docx`；临时脚本、渲染图和中间 PDF 不作为交付件。

---

### Task 1: 题意、数据与结果取证

**Files:**
- Read: `problem/C题.pdf`
- Read: `data/processed/summary.json`
- Read: `questions/q1/outputs/results/q1_summary.json`
- Read: `questions/q1/outputs/tables/*.csv`
- Run: `questions/q1/code/validate_q1_outputs.py`

- [ ] 核对第一问题面、附件口径与研究边界。
- [ ] 汇总数据规模、日期范围、活动度筛选和数据质量指标。
- [ ] 从结果表提取分布、聚类、关系、Bootstrap 和敏感性数值。
- [ ] 运行现有验证脚本并记录 PASS/FAIL。

### Task 2: 文献与论证框架

**Files:**
- Create: `tmp/q1_paper/evidence_summary.json`

- [ ] 检索 2021-2025 年生鲜需求、间歇性需求、季节聚类或零售销量关系研究，选择 1-2 篇用于问题理解深化。
- [ ] 核对 K-means、Silhouette、CH、DB、Bootstrap 和 BH-FDR 的原始/权威文献条目。
- [ ] 形成论文各节的证据映射，消除项目旧文稿中的数字冲突。

### Task 3: 论文内容撰写

**Files:**
- Create: `tmp/q1_paper/paper_content.md`

- [ ] 撰写原创“问题重述、问题分析、模型假设、符号说明”。
- [ ] 按“分布规律子问题—季节型划分子问题—分层关系识别子问题”分别撰写模型构建、求解、结果和检验。
- [ ] 撰写模型评价、参考文献和附录，优缺点均绑定项目数据。
- [ ] 检查公式编号、符号一致性、结论边界和文献引用。

### Task 4: Word 构建与版式实现

**Files:**
- Create: `tmp/q1_paper/build_q1_paper.py`
- Create: `outputs/第一问论文_销量分布与相互关系.docx`

- [ ] 采用学术长报告版式：A4、中文正文宋体、标题黑体、公式居中、三线表、图题表题和页码。
- [ ] 插入必要的模型流程图、关键结果表和项目已有论文图。
- [ ] 设置标题层级、目录字段、图表编号、参考文献和附录层级。
- [ ] 导出单一最终 DOCX。

### Task 5: 结构与视觉验证

**Files:**
- Run: `questions/q1/code/validate_q1_outputs.py`
- Run: document renderer on final DOCX
- Inspect: rendered `page-*.png`

- [ ] 检查 DOCX 可打开、正文包含全部用户要求章节、无占位符或工具标记。
- [ ] 核对关键数字与证据摘要一致。
- [ ] 渲染全部页面并逐页检查字体、公式、表格、图形、分页和页眉页脚。
- [ ] 修复发现的问题后重新渲染，直至通过。
