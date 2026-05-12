# 图表/表格实现优先级

## P1：优先做，支撑主闭环

- `figure_01_tongji_subject_ranking_overview`：图1、同济大学xx学科国际排名；状态 `ready_after_fact_ranking`
- `figure_02_indicator_commonality`：图2、XX学科在世界学科排名中指标共性；状态 `partial_needs_indicator_grouping`
- `figure_03_arwu_indicator_weight`：图3、软科世界一流学科数学指标权重；状态 `ready_after_weight_cleaning`
- `figure_04_qs_indicator_weight`：图4、软科世界一流学科数学指标权重（参考报告疑似标题误写，实际应为QS指标权重）；状态 `ready_after_weight_cleaning`
- `figure_05_usnews_indicator_weight`：图3、U.S.News学科排名数学学科指标权重；状态 `ready_after_weight_cleaning`
- `figure_06_the_indicator_weight`：图4、THE世界学科排名自然科学领域指标权重；状态 `ready_after_weight_cleaning`
- `figure_07_all_rankings_history`：图5、同济xx学科在世界学科排名中的历史（排名区间的取值中间位次）；状态 `ready_after_fact_ranking`
- `table_04_mainland_rank_band_distribution`：表5、2025年发布的四大国际排名中内地高校位次分布；状态 `ready_after_fact_ranking`
- `figure_09_arwu_peer_indicator_relative_rank`：图8、软科排名前200位内地高校分项指标相对排名；状态 `ready_after_fact_ranking_indicator`
- `figure_11_usnews_peer_indicator_relative_rank`：图7、U.S.News排名前200位内地高校分项指标相对排名；状态 `ready_after_fact_ranking_indicator`
- `figure_12_the_peer_indicator_relative_rank`：图9、THE排名前200位内地高校分项指标相对排名；状态 `ready_after_fact_ranking_indicator`

## P2：第二批，扩展历史表和国内评估

- `table_01_arwu_history_detail`：表3、xx学科在软科排名中的细分指标排名历史（待更新）；状态 `ready_after_fact_ranking_indicator`
- `table_02_usnews_history_detail`：表2、xx学科在U.S.News学科排名中的细分指标排名历史（待更新）；状态 `ready_after_fact_ranking_indicator`
- `figure_08_usnews_history_trend`：图6、xx学科在U.S.News学科排名中的历史（趋势图分析）；状态 `ready_after_fact_ranking`
- `table_03_the_history_detail`：表4、xx学科在THE排名中的细分指标排名历史（待更新）；状态 `ready_after_fact_ranking_indicator`
- `table_05_arwu_mainland_peer_ranking`：表7、软科排名中内地高校位于前列的比较；状态 `ready_after_fact_ranking`
- `table_06_usnews_mainland_peer_ranking`：表6、U.S.News排名中内地高校位于前列的比较；状态 `ready_after_fact_ranking`
- `table_07_qs_mainland_peer_ranking`：表：QS排名中内地高校位于前列的比较（参考报告表7样式）；状态 `ready_after_fact_ranking`
- `table_08_the_mainland_peer_ranking`：表8、THE排名中内地高校位于前列的比较；状态 `ready_after_fact_ranking`
- `figure_10_qs_peer_indicator_relative_rank`：QS排名前列内地高校分项指标相对排名（参考报告QS段落缺图题）；状态 `ready_after_fact_ranking_indicator`
- `table_10_domestic_evaluation_peer_comparison`：双一流高校第五轮学科评估结果对比（目标模板新增）；状态 `ready_with_caveat`

## P3：第三批，注意版面或代理口径

- `table_09_combined_peer_ranking_matrix`：参考报告物理表8：四大榜单合并对标矩阵；状态 `ready_after_fact_ranking`
- `figure_13_paper_quantity_citation_proxy`：图10、37所内地高校论文及被引总量及相对排名；状态 `partial_proxy_only`
- `figure_14_paper_quality_proxy`：图11、37所内地高校论文CNCI及篇均被引数及相对排名；状态 `partial_proxy_only`
- `figure_15_highly_cited_proxy`：图12、37所内地高校高被引TOP论文量及相对排名；状态 `partial_proxy_only`
- `figure_16_international_collaboration_proxy`：图13、37所内地高校国际合著论文占比及相对排名；状态 `partial_proxy_only`

## P4：暂缓，除非补数据

- `text_or_table_11_research_frontier_gap`：研究前沿及学科交叉（目标模板标黄）；状态 `data_gap`

## 推荐第一个闭环

先做 `figure_07_all_rankings_history`，同时带上 `figure_01_tongji_subject_ranking_overview`。

原因：这两个图共用 `fact_ranking`，能优先验证学科映射、学校别名、年份口径、排名区间解析和多榜单联表。
