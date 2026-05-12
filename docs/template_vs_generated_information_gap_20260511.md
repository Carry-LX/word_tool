# 参考 Word 与当前生成图表的信息差异复盘（2026-05-11）

## 对照对象

- 参考 Word：`data/同济大学XX学科的国际排名发展分析-2026年5月.docx`
- 当前生成结果：`outputs/subject_agent_runs/20260511_134517_0812_计算机科学与技术`

参考 Word 结构读取结果：

- 图片对象：14 个。
- Word 表格：8 个。
- 主要图题/表题段落：与此前槽位清单基本一致。

## 总体判断

当前生成结果已经覆盖参考 Word 的主要槽位，但信息形态还不是完全等价。核心差异不是“缺图”，而是以下四类：

1. 部分参考图是多指标、多高校的纵向折线小图；当前生成图更偏汇总型或相对位次面板。
2. 参考中的对标高校表是多年份历史表；当前 table_05/table_06/table_07/table_08 是最新年榜单表，历史信息主要被放进 table_09 附表。
3. 参考附表是 39 行 x 27 列的宽表，按 US News、软科、THE、QS 分组展示；当前 table_09 是 205 行 x 8 列的长表式附表。
4. 论文指标参考图使用五年 WOS/InCites 类数据；当前使用 CWTS Leiden 2025 宽领域代理数据，信息口径不完全相同。

## 逐项差异

| 参考槽位 | 参考 Word 信息形态 | 当前 artifact | 当前差异 |
| --- | --- | --- | --- |
| 图1 同济大学 xx 学科国际排名 | 四个榜单卡片，含最新排名和若干历史/地区排名信息 | `figure_01_tongji_subject_ranking_overview` | 基本一致；当前卡片更简洁，地区排名/历史最佳等信息不如参考图丰富。 |
| 图2 指标共性 | 桑基/流向图，体现四大榜单指标到科研、声誉、国际化等维度的权重汇聚 | `figure_02_ranking_indicator_commonality` | 当前是网络关系图，信息覆盖接近，但不如参考图清楚表达“权重流量”和总权重占比。 |
| 软科权重图 | 饼图，数学口径，显示软科各指标权重 | `figure_03_arwu_indicator_weight` | 当前为环形图，信息覆盖；但参考是大饼图，强调原始指标名称和比例。 |
| QS 权重图 | 饼图，数学口径 | `figure_04_qs_indicator_weight` | 信息基本一致。参考图标题里编号/文字有误，但图本身是 QS。 |
| US News 权重图 | 树状/分支图，数学口径 | `figure_05_usnews_indicator_weight` | 当前是环形图，不是参考的树状分层结构；信息有权重，但层级表达弱。 |
| THE 权重图 | 树状/分支图，显示一级指标及二级指标 | `figure_06_the_indicator_weight` | 当前是环形图，只显示权重构成；参考强调一级指标 -> 二级指标层级。 |
| 图5 四大排名历史 | 折线图，时间轴 2015-2025，四条榜单线 | `figure_07_all_rankings_history` | 当前只覆盖本地可得年份，计算机多为 2021/2022 后；时间跨度短于参考图。 |
| 表3 软科分项指标历史 | 多年份分项指标历史表 | `table_01_arwu_tongji_indicator_history` | 当前已做口径归并，信息更干净；但参考更偏“相对排名/得分混合”的数学历史表，当前为公开页指标值。 |
| 表2 US News 分项指标历史 | 多年份 US News 指标表，含国际排名、总分、声誉、论文、引用等 | `table_02_usnews_tongji_indicator_history` | 当前覆盖 2023/2025/2026，缺 2024；参考数学表覆盖 2021/2022/2023/2025。年份结构不同。 |
| 图6 US News 历史趋势 | 参考只有图题，没有实际图片对象 | `figure_10_usnews_indicator_history_trend` | 当前补生成了趋势图，属于新增可用对象。 |
| 表4 THE 分项指标历史 | 2023/2024/2025 发布年和 2024/2025/2026 排名年组合 | `table_03_the_tongji_indicator_history` | 当前覆盖 2023-2026 ranking_year，已归并 THE 口径；但没有保留“发布年份/排名年度”两行元信息。 |
| 表5 位次分布 | 四大榜单按前50、51-100、101-150、151-200、前200合计汇总 | `table_04_mainland_rank_band_distribution` | 基本一致，但当前是长表，每个榜单多行；参考是横向矩阵，四榜单为列。 |
| 软科内地高校对标表 | 36 行，列为 2020-2025 多年份排名 | `table_05_arwu_mainland_peer_ranking` | 当前只展示最新排名；多年份历史被移入 table_09，不符合参考表信息形态。 |
| US News 内地高校对标表 | 28 行，列为 2020-2021 至 2025-2026 多年份排名 | `table_06_usnews_mainland_peer_ranking` | 当前只展示最新排名；参考要求多年份历史。 |
| THE 内地高校对标表 | 19 行，列为 2023/2024/2025 年排名 | `table_08_the_mainland_peer_ranking` | 当前只展示最新排名；参考要求多年份历史。 |
| QS 内地高校对标 | 参考正文有 QS 小节，但未发现独立 QS 表格对象 | `table_07_qs_mainland_peer_ranking` | 当前新增 QS 最新排名表；参考正文中 QS 信息存在错位/未完整落表。 |
| 图8 软科前200内地高校分项指标相对排名 | 多个竖向折线小图，横轴高校，纵轴各指标相对排名 | `figure_09_arwu_peer_indicator_relative_rank` | 当前是 5 个横向相对位次面板，只展示同济相对位置；参考展示每个高校在每个指标上的连续折线。 |
| 图7 US News 前200内地高校分项指标相对排名 | 多指标竖向折线小图，覆盖大量指标 | `figure_11_usnews_peer_indicator_relative_rank` | 当前是小面板相对位次，信息更少；缺“所有高校逐校折线”的完整展开。 |
| 图9 THE 前200内地高校分项指标相对排名 | 多指标竖向折线小图 | `figure_12_the_peer_indicator_relative_rank` | 当前同样是相对位次面板，不是逐校折线。 |
| 图10 论文及被引总量 | WOS 2021-2025 五年论文/被引总量，多高校折线 | `figure_13_paper_output_citation_relative_rank` | 当前用 CWTS 2020-2023 宽领域代理，并用横向条形排名；时间、数据源、图形形态均不同。 |
| 图11 CNCI 及篇均被引 | WOS/InCites CNCI、篇均被引，多高校折线 | `figure_14_paper_cnci_cpp_relative_rank` | 当前用 CWTS `MNCS/MCS` 代理，不应直接称为 InCites CNCI/篇均被引；图形也不同。 |
| 图12 高被引 TOP 论文 | TOP1%、TOP10% 等多高校折线 | `figure_15_paper_highly_cited_relative_rank` | 当前用 CWTS P_top_1/P_top_10 代理，图形为条形排名，非参考折线。 |
| 图13 国际合著 | 国际合著论文占比/数量，多高校折线 | `figure_16_paper_international_collab_relative_rank` | 当前用 CWTS P_int_collab/PP_int_collab 代理，图形为条形排名，非参考折线。 |
| 附表 对标高校历史 | 39 行 x 27 列，学校、省份、四榜单多年份、平均位次 | `table_09_peer_full_ranking_history_appendix` | 当前是 205 行 x 8 列，按榜单拆成长表；缺省份列、平均位次列、四榜单分组宽表结构。 |

## 当前最需要补齐的信息差

1. 对标高校表需要改成“多年份历史表”，而不是只展示最新年。
2. 附表需要输出参考 Word 的 27 列宽表结构，包含省份和排名平均位次。
3. 三张 peer 分指标图需要从“同济相对位次面板”升级为“逐校多指标折线/点线图”，才能接近参考图的信息密度。
4. 论文类四张图如果要严格复刻，需要补 WOS/InCites/ESI 原始五年论文指标；当前 CWTS 只能作为公开代理口径。
5. US News 趋势图是参考文档中只有图题、无图片对象的槽位；当前已补图，但后续进入 Word 时需要确认是否插入。

## 已生成的分析产物

- `outputs/template_analysis/template_structure.json`
- `outputs/template_analysis/template_structure.md`
- `outputs/template_analysis/template_image_contact_sheet.png`
- `outputs/template_analysis/template_media.json`
