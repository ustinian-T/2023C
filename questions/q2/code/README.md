# 代码目录

## 文件

- `q2_model.py`：完整求解入口，负责数据读取、弹性估计、需求与成本预测、联合场景生成、周级定价补货优化及结果导出；
- `test_q2_model.py`：以 13 项手算用例检验周级尾部风险聚合、商誉成本分段梯度、参考正则、价格响应回退、加价平滑和决策边界；
- `validate_q2_outputs.py`：对 42 条主策略及全部衍生结果执行确定性一致性检查。

## 求解流程

`q2_model.py` 只读取 `data/processed/processed_daily_category.csv`，不会修改原始附件。固定随机种子为 `20230907`，默认生成 600 条七日联合残差场景。三档风险权重为 `0`、`0.25` 和 `0.50`，其中 `0.25` 为提交策略。

优化采用两阶段结构：逐日 Differential Evolution 与 SLSQP 产生满足历史区间和日变动约束的强初值；随后对七天共 84 个加价率与补货量变量进行周级 SLSQP 联合精修。周级目标的梯度由各场景利润的分段解析次梯度计算，分别处理库存/需求约束状态以及商誉成本中正毛利/非正毛利状态。主方案后继续计算 8 组完整敏感性策略。

## 运行命令

```powershell
python questions\q2\code\q2_model.py
python -m unittest discover -s questions\q2\code -p "test_q2_model.py"
python questions\q2\code\validate_q2_outputs.py
```

一次完整复算通常需要约 2—3 分钟，具体取决于 CPU。验证脚本成功时退出码为 0，并在 `outputs/results/q2_validation.json` 保存 36 项逐项结果。
