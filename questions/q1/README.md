# Q1 模型实现与复现说明

## 1. 已完成内容

本目录已按指定动线完成问题 1：

> 多季节 STL 去趋势 → 近似 MIC 非线性筛选 → Graphical Lasso 稀疏条件关联网络 → 移动块 Bootstrap 稳定性检验。

除作图脚本 `code/plot_q1_matlab.m` 外，所有数据读取、筛选、分布拟合、模型估计、网络计算和验证均由 Python 的 `code/q1_model.py` 完成。输入直接采用仓库共享的 `data/processed/` 数据，不重复清洗附件。

## 2. 逻辑链条

1. **活动度筛选**：251 个单品中，要求时间跨度不少于 730 日、正销售日不少于 180 日、记录覆盖率不少于 35%、累计销量不少于 200 kg，保留 47 个高活跃单品。
2. **两部分布**：销量含大量零值，因此先估计零销量概率，再对正销量比较 Normal、Lognormal、Gamma 和 Weibull；AIC 选相对最优，KS 检验不通过则标记 KDE 回退。
3. **MSTL 去时间结构**：对 `log1p(销量)` 分解 7 日周期、365 日周期与长期趋势，关联分析只用残差。
4. **MIC 筛选**：用等频网格近似最大信息系数；并列零值取平均秩。通过随机循环移位形成保留自相关的零分布，取 99% 分位作阈值。
5. **Graphical Lasso**：残差经秩高斯变换后估计精度矩阵，以 EBIC 选择正则强度，从精度矩阵计算条件相关。
6. **稳定性检验**：采用 14 日移动块、单品 100 次和品类 200 次 Bootstrap；最终边必须同时通过 MIC、非零精度和 70% 同号稳定率。
7. **网络解释**：正边记为潜在互补/同步，负边记为潜在替代；不使用“因果”“必然替代”等越界措辞。

## 3. 核心结果

- 单品层：47 个节点、587 个共同日期，MIC 候选 18 对，最终稳定边 10 条，其中正边 6 条、负边 4 条。
- 47 个节点中 12 个进入连通网络，35 个为孤立节点；网络图为可读性不绘制孤立节点。
- 最强正边为姬菇(1)--海鲜菇(1)，条件相关 0.3125，稳定率 100%。
- 较强负边为海鲜菇(1)--长线茄，条件相关 -0.1746，稳定率 100%。
- 品类层：花菜类--辣椒类和花菜类--食用菌为两条稳定正边。
- 六个品类的正销量条件分布均通过 KS 检验：4 类选 Gamma，2 类选 Lognormal。
- Graphical Lasso 正则强度上下浮动 20% 时最终候选交集不变；MIC 阈值分位是最敏感的参数。

完整数字与来源见 `outputs/results/validation_report.md` 和 `outputs/results/q1_summary.json`。

## 4. 运行方法

Python 依赖列于 `requirements.txt`。在当前目录运行：

```powershell
python questions\q1\code\q1_model.py
```

该命令会覆盖 `questions/q1/outputs/tables/tab_q1_*.csv` 与 `questions/q1/outputs/results/q1_*.json`。固定随机种子为 20230907，完整运行约需数分钟。

随后用 MATLAB R2023b 或兼容版本绘图：

```powershell
matlab -batch "run('questions/q1/code/plot_q1_matlab.m')"
```

MATLAB 只读取 Python 结果表并绘图，不重新拟合模型。每幅图同时输出 600 dpi PNG 与矢量 PDF。

## 5. 目录说明

- `code/q1_model.py`：Python 主模型与验证。
- `code/plot_q1_matlab.m`：MATLAB 学术作图。
- `modeling/q1_modeling_idea.md`：逐步推导、代码映射和模型边界。
- `outputs/tables/`：筛选、分布、MIC、精度矩阵边、节点、社群与敏感性结果。
- `outputs/figures/`：6 组 PNG/PDF 学术图。
- `outputs/results/q1_summary.json`：机器可读的关键结果。
- `outputs/results/validation_report.md`：结果追踪、验证与局限。
- `outputs/workbooks/q1_model_results.xlsx`：格式化结果总表；其中数字 SKU 以 `SKU-` 前缀显示，避免 Excel 将标识符转成科学计数法。
- `report/main.tex`：Q1 论文式正文。
- `code/validate_q1_outputs.py`：跨文件一致性校验；本次 38 项检查全部通过。

## 6. 模型优点

1. STL 先去除共同星期、年度季节和长期趋势，显著减少伪相关。
2. MIC 对非线性敏感，Graphical Lasso 又能控制其他商品，二者回答的问题互补。
3. EBIC、循环移位零分布和时间块 Bootstrap 都是数据驱动阈值，减少主观挑边。
4. 稀疏网络把 47×47 的关系压缩为 10 条稳定边，论文可解释性强。
5. 输出含参数路径、失败状态、最小特征值、敏感性与完整边表，便于复核。

## 7. 模型缺点与适用边界

1. 无销售记录可能来自缺货或未上架，不能完全等同于零需求。
2. 实现的是透明、可复现的 `mic_approx`，不是 MINE 的严格 MICe。
3. Graphical Lasso 仍是同期统计关联，无法排除价格、促销、天气、客流与陈列等混杂。
4. 活动度门槛会排除大量短生命周期单品，网络只代表长期活跃 SKU。
5. 99% MIC 阈值较严格；在 97.5% 阈值下边数增至 15，在 99.5% 下减至 3，因此弱边结论不稳定。
6. 最终网络可给后续补货组合提供候选关系，但不能直接充当需求弹性或因果替代系数。

## 8. 图形规范

所有主图为白底，坐标与图例字号不低于 12--16 pt，图例和说明位于右上区域；统一使用 `#DDF2F0`、`#D6F6F1`、`#A6EBDD`、`#88C9D0`、`#929ED2`、`#5E8CBE`、`#3E5682`、`#0F1633` 青绿—蓝紫 SCI 色板。彩色电子版同时以实线/虚线/点线、空心圆/上三角/下三角、圆/方/三角/菱形节点、明度、深色边框和数值正负号作冗余编码，使黑白打印不依赖色相仍可辨认；`outputs/figures/print_preview/` 保存 MATLAB 自动生成的灰度打印预览。主图 PNG 为 600 dpi，PDF 保留矢量文本。图形已经逐张检查，无明显重叠、截断或工具栏残留。

当前机器未安装 XeLaTeX、LuaLaTeX 或 tectonic，故 `report/main.tex` 未在本机编译；安装任一支持中文的 TeX 引擎后可直接编译。MATLAB 导出的六组矢量 PDF 图不受此限制。
