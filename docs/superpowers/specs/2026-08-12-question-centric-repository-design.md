# 2023 C 题按问题组织的仓库结构设计

## 1. 目标

将当前以技术产物类型为主的根目录结构，调整为以四个赛题问题为核心的模块化结构。每一问独立保存代码、建模说明、解题报告和输出产物；题面、原始附件及通用预处理数据由四问共享。

本次重构只迁移和整理已经完成的第一问，不新增第二至四问的求解结论。第二至四问建立可继续开发的统一目录骨架，并明确标注当前状态。

## 2. 目标目录

```text
2023C/
├─ README.md
├─ requirements.txt
├─ problem/
│  ├─ C题.pdf
│  └─ README.md
├─ data/
│  ├─ raw/
│  │  ├─ 附件1.xlsx
│  │  ├─ 附件2.xlsx
│  │  ├─ 附件3.xlsx
│  │  └─ 附件4.xlsx
│  └─ processed/
│     ├─ README.md
│     └─ 第一问当前使用的预处理文件
├─ questions/
│  ├─ q1/
│  │  ├─ README.md
│  │  ├─ code/
│  │  ├─ modeling/
│  │  ├─ report/
│  │  └─ outputs/
│  │     ├─ figures/
│  │     ├─ tables/
│  │     ├─ results/
│  │     └─ workbooks/
│  ├─ q2/
│  │  ├─ README.md
│  │  ├─ code/
│  │  ├─ modeling/
│  │  ├─ report/
│  │  └─ outputs/
│  ├─ q3/
│  │  └─ 与 q2 相同的标准骨架
│  └─ q4/
│     └─ 与 q2 相同的标准骨架
└─ docs/
   └─ superpowers/
      ├─ specs/
      └─ plans/
```

Git 不跟踪空目录，因此第二至四问的 `code`、`modeling`、`report` 和 `outputs` 目录各保存一份简短的 `README.md`，说明该目录将承载的内容和当前未求解状态。

## 3. 第一问迁移映射

| 当前路径 | 目标路径 |
| --- | --- |
| `src/` | `questions/q1/code/` |
| `modeling/` | `questions/q1/modeling/` |
| `paper/` | `questions/q1/report/` |
| `figures/` | `questions/q1/outputs/figures/` |
| `tables/` | `questions/q1/outputs/tables/` |
| `results/` | `questions/q1/outputs/results/` |
| `outputs/q1_model/` | `questions/q1/outputs/workbooks/` |
| `README_Q1.md` | `questions/q1/README.md` |
| `problem/problem_parse.md` | `questions/q1/modeling/problem_scope.md` |
| `蔬菜数据预处理结果包/` | `data/processed/` |

迁移优先使用 `git mv`，使 Git 能最大限度识别文件历史。迁移完成后删除已变空的旧目录。

## 4. 共享题面与数据

- 将用户提供的 `C题.pdf` 复制到 `problem/C题.pdf`，作为仓库内的正式题面。
- 将四个 Excel 附件各保存一份到 `data/raw/`，不在每一问中重复复制。
- 将当前已跟踪的预处理 CSV、图片和摘要迁移到 `data/processed/`。
- `problem/README.md` 记录四问的准确任务边界和附件用途。
- `data/README.md` 说明 `raw` 与 `processed` 的区别、数据来源及共享原则。
- 原始附件总量约 40 MB，其中 `附件2.xlsx` 约 39 MB，仍低于 GitHub 单文件 100 MB 限制，因此采用普通 Git 跟踪，不引入 Git LFS。

## 5. 路径与运行约定

第一问运行根目录定义为 `questions/q1/`：

- Python 主模型从 `questions/q1/code/q1_model.py` 启动。
- 默认输入为仓库根目录下的 `data/processed/`。
- `--input-dir` 参数继续保留，以支持显式指定其他预处理数据目录。
- 表格、JSON、图片和工作簿分别写入第一问的 `outputs/tables`、`outputs/results`、`outputs/figures` 和 `outputs/workbooks`。
- MATLAB 绘图脚本根据自身位置定位 `questions/q1/`，不依赖调用者的当前工作目录。
- 第一问验证脚本根据自身位置定位全部输出目录。
- LaTeX 报告从 `questions/q1/report/main.tex` 引用 `../outputs/figures/` 中的矢量图。

顶层 `README.md` 提供项目导航、四问状态表、共享数据说明和第一问完整复现命令。第一问 `README.md` 保存模型细节、结果摘要和该问内部目录说明。

## 6. 第二至四问骨架

第二至四问采用与第一问一致的职责边界：

- `code/`：模型、数据处理、绘图和验证代码。
- `modeling/`：假设、变量、模型推导、方案比较和敏感性设计。
- `report/`：该问可直接用于论文的正文或独立报告。
- `outputs/`：运行产生的图片、表格、机器可读结果和工作簿。

每问 `README.md` 写明题目要求、预期输入、预期输出和当前状态。第二至四问当前状态统一为“目录已建立，求解尚未开始”，避免将骨架误解为已经完成的模型实现。

## 7. 验证标准

结构迁移完成后必须满足以下条件：

1. `git status` 只显示本次结构优化相关文件。
2. 四个原始附件均存在于 `data/raw/`，文件大小与用户提供的源文件一致。
3. 第一问所有当前已跟踪代码、文档和输出均能在新目录中找到，不丢失文件。
4. 第一问 Python 主模型可以从仓库根目录按 README 命令读取 `data/processed/` 并生成新路径下的输出。
5. 第一问输出验证脚本通过全部一致性检查。
6. Markdown、Python、MATLAB 和 LaTeX 中不存在指向旧根目录结构的失效引用。
7. `git diff --check` 无空白错误。
8. 提交前复核大文件大小和 GitHub 单文件限制；提交后推送到 `origin/main`，再确认本地 `main` 与 `origin/main` 一致。

## 8. 非目标

- 不在本次重构中求解第二、第三或第四问。
- 不改变第一问的统计模型、参数、结论或既有数值结果。
- 不把共享附件复制到各问目录。
- 不引入新的公共代码框架、打包系统、Git LFS 或持续集成服务。
- 不修改用户提供的原始 PDF 和 Excel 文件内容。
