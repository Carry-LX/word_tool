# 当前数据复核与整体逻辑

## 复核结论

当前数据部分已经达到“可进入结构化入库”的清晰度：源文件已注册、参考报告图表已索引、每个主要图表已有字段级 recipe，且 recipe 引用的文件、sheet、字段均通过自动核验。

但还没有完成真正的数据入库和清洗。因此下一阶段的重点不是继续加文档，而是把统一数据模型落成 `processed/` 中的事实表和维表。

## 机器核验结果

- Excel 文件数：25
- Excel sheet 数：37
- 注册 Excel 源：25
- 未注册 Excel：0
- Artifact recipe 数：27
- 缺失文件：0
- 缺失 sheet：0
- 缺失字段：0

## 核心数据源

### core

- `教育部学科与四大国际学科排名映射关系.xlsx`：subject_crosswalk；教育部一级学科到软科、QS、US News、THE榜单学科的主映射表。
- `同济大学学院+学科映射关系20260509.xlsx`：tongji_subject_crosswalk；同济学院、学位点、一级学科、第五轮评估、双一流、高峰高原、四大榜单名称之间的映射。
- `四大世界学科2025指标权重.xlsx`：indicator_weight；四大榜单指标体系和权重的主数据源。
- `世界大学学科排名THE（2022-2026年）20260123.xlsx`：ranking_detail_history；THE 2022-2026 学科排名总库，含同济、同济历史、排名方法。
- `全国双一流学科明细表2022&2017.v2.xlsx`：peer_scope；确定双一流高校和学科范围，用于对标高校筛选。
- `第五轮评估结果（不完全）20260508.xlsx`：domestic_evaluation；第五轮评估结果主表，但数据不完全。
- `同济大学第五轮学科评估结果+双一流+高峰高原.xlsx`：tongji_domestic_status；同济各学科第五轮评估、双一流、高峰高原状态。

### current

- `2025年软科世界一流学科排名20251118.xlsx`：ranking_detail；软科最新可用学科排名明细。
- `2026年QS世界学科排名20260326.xlsx`：ranking_detail；QS 最新可用学科排名明细。
- `2026年THE世界学科排名20260123.xlsx`：ranking_detail；THE 2026 学科排名明细。
- `2025-2026年度US News世界学科排名20251124.xlsx`：ranking_detail；US News 最新可用学科排名明细。

## Recipe 状态分布

- `ready_after_fact_ranking`：9
- `partial_needs_indicator_grouping`：1
- `ready_after_weight_cleaning`：4
- `ready_after_fact_ranking_indicator`：7
- `partial_proxy_only`：4
- `ready_with_caveat`：1
- `data_gap`：1

## 优先级分布

- `P1`：11
- `P2`：10
- `P3`：5
- `P4`：1

## 数据层到图表的依赖

### fact_ranking

- `figure_01_tongji_subject_ranking_overview`
- `figure_07_all_rankings_history`
- `figure_08_usnews_history_trend`
- `table_04_mainland_rank_band_distribution`
- `table_05_arwu_mainland_peer_ranking`
- `table_06_usnews_mainland_peer_ranking`
- `table_07_qs_mainland_peer_ranking`
- `table_08_the_mainland_peer_ranking`
- `table_09_combined_peer_ranking_matrix`

### fact_indicator_weight + indicator_group_mapping

- `figure_02_indicator_commonality`

### fact_indicator_weight

- `figure_03_arwu_indicator_weight`
- `figure_04_qs_indicator_weight`
- `figure_05_usnews_indicator_weight`
- `figure_06_the_indicator_weight`

### fact_ranking_indicator

- `table_01_arwu_history_detail`
- `table_02_usnews_history_detail`
- `table_03_the_history_detail`
- `figure_09_arwu_peer_indicator_relative_rank`
- `figure_10_qs_peer_indicator_relative_rank`
- `figure_11_usnews_peer_indicator_relative_rank`
- `figure_12_the_peer_indicator_relative_rank`

### proxy_metrics

- `figure_13_paper_quantity_citation_proxy`
- `figure_14_paper_quality_proxy`
- `figure_15_highly_cited_proxy`
- `figure_16_international_collaboration_proxy`

### fact_domestic_evaluation

- `table_10_domestic_evaluation_peer_comparison`

### missing_external_data

- `text_or_table_11_research_frontier_gap`

## 最常被使用的数据源

- `map_ministry_rankings`：26 个 artifact
- `rank_usnews_2025_2026`：12 个 artifact
- `weights_four_rankings_2025`：12 个 artifact
- `rank_arwu_2025`：11 个 artifact
- `rank_qs_2026`：7 个 artifact
- `rank_the_2026`：6 个 artifact
- `rank_usnews_2021`：5 个 artifact
- `rank_usnews_2022`：5 个 artifact
- `rank_usnews_2023`：5 个 artifact
- `rank_usnews_2024_2025`：5 个 artifact
- `rank_the_2022_2026_history`：5 个 artifact
- `map_tongji_college_subject`：4 个 artifact

## 当前仍需人工确认的口径

1. 对标高校范围：默认建议先做 `mainland_top200_by_ranking`，再支持双一流、第五轮同档、用户指定名单。
2. 目标学科输入方式：建议支持“一级学科名称”优先，其次支持“学院名称”，通过 `dim_subject` 解析到四大榜单学科。
3. 排名年份口径：报告中必须同时记录发布年度和排名年度，图题按实际数据口径写。
4. 论文实力：当前只能做榜单代理指标，除非补 WOS/Scopus 论文数据。
5. 研究前沿：当前是明确缺口，不能生成强结论。
