# 同济 49 个学科学位点联网补全记录

日期：2026-05-12

## 结论

本次补全后，`data/同济大学学院+学科映射关系20260509.xlsx` 中的 49 个学科学位点都已经可以进入生成逻辑：

- 41 个学科：原表已有一级学科代码，且当前数据层可完整生成。
- 4 个学科：原表缺少一级学科代码，本次按公开榜单学科体系和相邻一级学科做了代理补齐，当前可完整生成，但报告中必须披露代理口径。
- 4 个学科：已经通过联网和别名规则补到可用记录，但四大榜单/论文指标覆盖仍不足，只能按“部分来源”生成，不建议包装成完整对标结论。

补全后的覆盖审计文件：

- `outputs/subject_coverage_audit/tongji_49_academic_degree_generation_coverage_after_supplement.csv`
- `outputs/subject_coverage_audit/tongji_49_academic_degree_generation_coverage_after_supplement.summary.json`

## 新增代理口径

| 原表学科 | 补充到的一级学科 | 代理强度 | 使用建议 |
| --- | --- | --- | --- |
| 智能电动车辆 | 0802 机械工程 | broad_proxy | 可生成。正文需说明按车辆工程/机械工程方向代理。 |
| 低空技术与工程 | 0825 航空宇航科学与技术 | broad_proxy | 可生成。交通运输工程可作为辅助解释，但主口径先按航空宇航。 |
| 光电科学与技术 | 0803 光学工程 | close_proxy | 可生成。该代理相对接近，可在图表注释中标出。 |
| 知识产权学 | 0301 法学 | broad_proxy | 可生成。国际榜单没有独立知识产权学，必须说明按法学/Law 代理。 |

配置文件：

- `configs/runtime/tongji_subject_proxy_supplement.csv`

## 仍需谨慎的 4 个学科

| 学科 | 当前状态 | 已有来源 | 建议处理 |
| --- | --- | --- | --- |
| 集成电路科学与工程 | partial_with_indicators | US News，CWTS 代理论文指标 | 可以生成，但更适合写成“相关方向参考”，避免做四榜单完整横向结论。 |
| 区域国别学 | partial_ranking_only | US News，CWTS 代理论文指标 | 可以生成框架页，但图表应减少排名对比，更多用文字说明数据不足。 |
| 公共管理 | partial_ranking_only | US News，CWTS 代理论文指标 | 可用 US News/公共管理相关口径作为参考，不宜宣称多源一致。 |
| 马克思主义理论 | partial_ranking_only | US News，CWTS 代理论文指标 | 国际榜单没有稳定独立口径，只能做政治学/哲学/社会科学相邻参考。 |

## 代码接入点

- `scripts/build_processed_core.py`
  - 新增读取 `tongji_subject_proxy_supplement.csv` 的逻辑。
  - 构建 `dim_subject` 前，将原表中缺失代码的学科补成代理一级学科。
- `scripts/build_data_layer_v2.py`
  - 修复手工别名规则兼容 `subject_id` 单数字段的问题，避免新增补充规则被静默跳过。
- `configs/runtime/manual_subject_aliases.json`
  - 新增集成电路科学与工程、公共管理、区域国别学、马克思主义理论、光学工程/光电等代理别名。

## 主要参考来源

- QS Subject Rankings: https://www.topuniversities.com/subject-rankings
- ShanghaiRanking GRAS: https://www.shanghairanking.com/rankings/gras/2025
- U.S. News / Clarivate 2025-2026 Best Global Universities: https://clarivate.com/news/u-s-news-releases-2025-2026-best-global-universities-rankings/
- THE World University Rankings 2026 methodology: https://www.timeshighereducation.com/sites/default/files/breaking_news_files/the_world_university_rankings_2026_methodology.pdf

## 生成逻辑建议

后续生成 49 个学科 Word 时，建议把 `generation_status_code_after_supplement` 作为分流字段：

- `full_ready_exact_or_existing`：按正常完整模板生成。
- `full_ready_via_subject_proxy`：按完整模板生成，但在标题页或图表脚注标出“代理学科口径”。
- `partial_sources_after_supplement`：使用降级模板，减少多榜单排名图，重点说明可用来源、缺失来源和谨慎解释。
