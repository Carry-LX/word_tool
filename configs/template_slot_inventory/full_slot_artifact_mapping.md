# Full Slot Artifact Mapping

本文件覆盖参考 Word 里的全部候选槽位：14 个图片对象、8 个表格对象、22 个图题/表题类段落。

## Summary

- raw_slots: 44
- image_slots: 14
- table_slots: 8
- caption_slots: 22
- logical_slots_after_pairing: 23
- raw_slots_mapped: 44
- raw_slots_unmapped: 0
- existing_registered_artifacts_used: 9
- planned_new_artifacts: 14
- data_gap_slots: 5

## Files

- `logical_slot_artifact_mapping.csv`：最终逻辑槽位到 artifact 的覆盖表。
- `raw_slot_coverage.csv`：44 个原始槽位逐一映射到逻辑槽位，要求 unmapped 为 0。
- `coverage_summary.json`：覆盖数量摘要。

## Planned New Artifacts

- `figure_02_ranking_indicator_commonality`：图2、XX学科在世界学科排名中指标共性；data_status=available_from_indicator_weight
- `figure_03_arwu_indicator_weight`：图3、软科世界一流学科数学指标权重；data_status=available
- `figure_04_qs_indicator_weight`：图4、QS学科排名数学指标权重；data_status=available
- `figure_05_usnews_indicator_weight`：图3、U.S.News学科排名数学学科指标权重；data_status=data_gap_usnews_math_weight_missing
- `figure_06_the_indicator_weight`：图4、THE世界学科排名自然科学领域指标权重；data_status=available
- `table_01_arwu_tongji_indicator_history`：表3、xx学科在软科排名中的细分指标排名历史；data_status=partial_only_2025_in_processed_indicator_fact
- `table_02_usnews_tongji_indicator_history`：表2、xx学科在U.S.News学科排名中的细分指标排名历史；data_status=partial_only_2026_in_processed_indicator_fact
- `figure_10_usnews_indicator_history_trend`：图6、xx学科在U.S.News学科排名中的历史（趋势图分析）；data_status=partial_only_2026_in_processed_indicator_fact
- `table_03_the_tongji_indicator_history`：表4、xx学科在THE排名中的细分指标排名历史；data_status=available
- `figure_13_paper_output_citation_relative_rank`：图10、37所内地高校论文及被引总量及相对排名；data_status=data_gap_no_wos_or_paper_metric_source_found
- `figure_14_paper_cnci_cpp_relative_rank`：图11、37所内地高校论文CNCI及篇均被引数及相对排名；data_status=data_gap_no_wos_or_paper_metric_source_found
- `figure_15_paper_highly_cited_relative_rank`：图12、37所内地高校高被引TOP论文量及相对排名；data_status=data_gap_no_wos_or_paper_metric_source_found
- `figure_16_paper_international_collab_relative_rank`：图13、37所内地高校国际合著论文占比及相对排名；data_status=data_gap_no_wos_or_paper_metric_source_found
- `table_09_peer_full_ranking_history_appendix`：附表：XX学科对标高校学科排名历史；data_status=available_from_existing_peer_tables

## Data Gaps

- `figure_05_usnews_indicator_weight`：不能硬套其他学科权重。需补 US News 数学权重，或由用户确认使用通用/近似口径。
- `figure_13_paper_output_citation_relative_rank`：必须补论文库或用户提供论文指标表，不能用排名表臆造。
- `figure_14_paper_cnci_cpp_relative_rank`：需要论文指标数据源。
- `figure_15_paper_highly_cited_relative_rank`：需要论文指标数据源。
- `figure_16_paper_international_collab_relative_rank`：需要论文指标数据源。

## Partial Data

- `table_01_arwu_tongji_indicator_history`：参考表要求多年历史。需确认原始软科历史文件是否含分项指标，或接受仅最新年。
- `table_02_usnews_tongji_indicator_history`：参考表要求多年历史。需补历史分项指标或降级为最新年表。
- `figure_10_usnews_indicator_history_trend`：参考中只有图题未发现对应图片对象，仍需作为槽位处理。

## Existing Artifacts That Need Visual Restyle

- `figure_01_tongji_subject_ranking_overview` -> four_ranking_card_panel
- `figure_07_all_rankings_history` -> multi_source_line_chart
- `figure_09_arwu_peer_indicator_relative_rank` -> multi_indicator_small_multiples
- `figure_11_usnews_peer_indicator_relative_rank` -> multi_indicator_small_multiples
- `figure_12_the_peer_indicator_relative_rank` -> multi_indicator_small_multiples
