# 后续数据处理路线

## 第一阶段：只读建模

目标：把源文件逻辑理顺，不生成报告。

- 已完成：`configs/stage1_inventory/`
- 已完成：`configs/data_governance/`

## 第二阶段：结构化入库

目标：把核心 Excel 转成统一中间库。

建议输出：

- `processed/ranking.duckdb`
- `processed/dim_subject.csv`
- `processed/dim_university.csv`
- `processed/fact_ranking.csv`
- `processed/fact_ranking_indicator.csv`
- `processed/fact_indicator_weight.csv`
- `processed/fact_domestic_evaluation.csv`

## 第三阶段：单 slot 数据闭环

目标：先选一个 slot 跑通数据、图、文字、插入 Word。

建议第一个 slot：

- `tongji_ranking_history`

原因：

- 数据源完整。
- 联表逻辑清楚。
- 参考报告里有对应表格和趋势图样式。
- 能检验学科映射、年度口径、排名区间处理。

## 第四阶段：扩展到整份报告

目标：按 `report_slots.yaml` 逐个生成章节。

顺序建议：

1. `tongji_ranking_history`
2. `ranking_indicator_system`
3. `double_first_class_peer_comparison`
4. `indicator_detail_comparison`
5. `domestic_evaluation_comparison`
6. `paper_strength_analysis`
7. `overview_competitive_summary`
8. `opportunities_challenges`
9. `research_frontier_interdiscipline`
