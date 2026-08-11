# 2023C — 问题一建模复现

本仓库实现 2023 年 C 题问题一的完整建模流程：多季节 STL 去趋势、MIC 非线性筛选、Graphical Lasso 稀疏条件关联网络，以及移动块 Bootstrap 稳定性检验。

- Python：数据读取、模型估计、筛选、验证与结果导出
- MATLAB：学术规范作图（600 dpi PNG 与矢量 PDF）
- 数据：直接使用已经预处理的数据，不重复执行原始数据审计
- 复现与模型说明：参见 [README_Q1.md](README_Q1.md)

主要入口：

```powershell
python src\q1_model.py
matlab -batch "run('src/plot_q1_matlab.m')"
python src\validate_q1_outputs.py
```

模型仅用于统计关联分析；网络中的正负边分别解释为潜在同步/互补关系与潜在替代关系，不作因果推断。
