# 2023 年高教社杯 C 题建模求解

本仓库用于求解 2023 年全国大学生数学建模竞赛 C 题“蔬菜类商品的自动定价与补货决策”。项目按四个问题分别组织代码、建模说明、解题报告和输出结果，题面与数据由四问共享。

## 当前进度

| 问题 | 主题 | 状态 | 入口 |
| --- | --- | --- | --- |
| 问题 1 | 销量分布与品类/单品关联关系 | ✅ 已完成（重构：季节画像 + K-means 聚类 + 分层关系分析） | [questions/q1/README.md](questions/q1/README.md) |
| 问题 2 | 品类级未来一周补货与定价 | 目录已建立，求解尚未开始 | [questions/q2/README.md](questions/q2/README.md) |
| 问题 3 | 单品级 7 月 1 日补货与定价 | 目录已建立，求解尚未开始 | [questions/q3/README.md](questions/q3/README.md) |
| 问题 4 | 建议补充采集的数据及其作用 | 目录已建立，求解尚未开始 | [questions/q4/README.md](questions/q4/README.md) |

## 项目结构

```text
problem/          竞赛题面与四问任务说明
data/raw/         四个原始 Excel 附件（共享且保持原样）
data/processed/   可供各问复用的预处理数据
questions/q1/     第一问代码、模型、报告与完整输出
questions/q2/     第二问独立工作区
questions/q3/     第三问独立工作区
questions/q4/     第四问独立工作区
docs/             仓库设计与实施计划
```

每问内部统一使用：

- `code/`：数据处理、模型、绘图及验证代码；
- `modeling/`：假设、变量、推导、方案比较与敏感性设计；
- `report/`：该问的解题报告或论文正文；
- `outputs/`：运行产生的表格、图片、结果文件和工作簿。

## 第一问复现

建议使用独立 Python 虚拟环境并从仓库根目录运行：

```powershell
python -m pip install -r requirements.txt
python questions\q1\code\q1_model.py
matlab -batch "run('questions/q1/code/plot_q1_matlab.m')"
python questions\q1\code\validate_q1_outputs.py
```

Python 完成数据读取、模型估计和表格导出；MATLAB 只读取 Python 结果并生成学术图，不重新拟合模型。输出统一写入 `questions/q1/outputs/`。

## 数据约定

四个原始附件只在 `data/raw/` 保存一份，任何代码都不应覆盖或原地修改它们。清洗后的共享数据写入 `data/processed/`；仅属于某一问的衍生结果写入该问自己的 `outputs/`。

第一问的网络边仅解释为潜在同步、互补或替代关系，不作因果推断。
