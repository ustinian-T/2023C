# 数据目录

本目录保存四个问题共享的数据。各问题代码应读取这里的单一数据副本，不在 `questions/q1` 至 `questions/q4` 中重复复制附件。

## `raw/`

`raw/` 保存竞赛原始附件：

- `附件1.xlsx`：商品与品类信息；
- `附件2.xlsx`：销售流水；
- `附件3.xlsx`：批发价格；
- `附件4.xlsx`：近期损耗率。

这些文件保持用户提供时的原始字节内容。模型不得覆盖或原地修改它们；清洗和衍生结果应写入 `processed/` 或相应问题的 `outputs/`。

## `processed/`

`processed/` 是当前第一问直接使用的预处理数据包，主要入口为：

- `processed_daily_category.csv`：日-品类汇总数据；
- `processed_daily_sku.csv`：日-单品汇总数据；
- `scenario_supplement_2023-07-01_to_07.csv`：未来一周情景补充表；
- `data_quality_summary.csv` 与 `summary.json`：预处理质量摘要。

箱线图用于追踪销售量、售价、批发价和损耗率的预处理分布。第一问默认只读取两张日汇总 CSV，不重新清洗原始附件。
