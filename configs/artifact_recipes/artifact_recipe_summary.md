# Artifact Recipe 阶段摘要

## 本阶段目标

把参考报告中的图、表，以及目标模板中新增的数据分析位置，拆到字段级数据依赖和处理步骤。

## 产物

- `reference_artifact_index.yaml`：参考报告图题、表题、物理表格和图片索引。
- `artifact_data_recipes.yaml`：每个图表/表格的数据源、字段、联表键、过滤、转换和验证规则。
- `artifact_gaps.md`：缺口、风险和谨慎口径。
- `artifact_priority.md`：实现优先级。
- `recipe_validation.json`：数据源、sheet、字段的自动核验结果。

## 覆盖情况

- 参考报告 caption artifact 数：22
- 参考报告物理表格数：8
- 参考报告物理图片数：14
- 当前 recipe 数：27

## 状态统计

- ready_after_fact_ranking: 9
- partial_needs_indicator_grouping: 1
- ready_after_weight_cleaning: 4
- ready_after_fact_ranking_indicator: 7
- partial_proxy_only: 4
- ready_with_caveat: 1
- data_gap: 1

## 自动核验

- 缺失文件数：0
- 缺失 sheet 数：0
- 字段提示数：0

recipe 中引用的文件、sheet 和字段都已在原始表前几行中找到。下一步应该进入结构化入库脚本，把字段别名、多级表头规则和排名区间解析固化。
