# Data Gap Report

- generated_at: 2026-05-10T21:38:22
- hard_data_gap_count: 5
- 口径：这里的 5 个缺口是会阻断图表可靠绘制的硬缺口；软科/US News 分项历史的单年问题另列为 partial constraints。

## 5 个硬性数据缺口

| slot | artifact | 对象 | 缺口 | 需要补什么 |
| --- | --- | --- | --- | --- |
| L005 | figure_05_usnews_indicator_weight | US News 数学学科指标权重图 | missing_usnews_math_weight | US News 数学学科指标体系及权重表，至少包含指标名、权重、适用学科/年份、来源文件。 |
| L019 | figure_13_paper_output_citation_relative_rank | 论文及被引总量相对排名图 | missing_paper_metric_source | 37 所对标高校论文总量、被引总量及统计口径字段。 |
| L020 | figure_14_paper_cnci_cpp_relative_rank | CNCI 及篇均被引相对排名图 | missing_paper_quality_source | 37 所对标高校 CNCI、篇均被引数、统计年份/窗口。 |
| L021 | figure_15_paper_highly_cited_relative_rank | 高被引 TOP 论文量相对排名图 | missing_highly_cited_source | 37 所对标高校高被引论文数量及 TOP 口径。 |
| L022 | figure_16_paper_international_collab_relative_rank | 国际合著论文占比相对排名图 | missing_international_collab_source | 37 所对标高校国际合著论文数、论文总数或国际合著占比。 |

## 非硬缺口但影响趋势完整性的约束

| slot | artifact | 状态 | 说明 |
| --- | --- | --- | --- |
| L008 | table_01_arwu_tongji_indicator_history | partial_only_latest_year | 软科数学同济分项指标当前主要只有 2025；若模板坚持多年历史，需要补历史分项指标。 |
| L009 | table_02_usnews_tongji_indicator_history | partial_only_latest_year | US News 数学同济分项指标当前主要只有 2026；若模板坚持多年历史，需要补历史分项指标。 |
| L010 | figure_10_usnews_indicator_history_trend | partial_only_latest_year | US News 分项指标趋势图需要多年分项指标，当前不可生成可靠趋势。 |
