# 数据层梳理报告

## 目标

在生成 Word 报告之前，先把杂乱表格整理成可追溯、可联表、可审查的数据层设计。

## 结论先行

- 四大国际排名、指标权重、学科映射、国内评估这四类核心数据都已具备。
- 软科、QS、US News 是多年度多文件；THE 有一个 2022-2026 总库，可作为历史主源。
- 后续不要直接让 agent 在 Excel 中随意检索，应先转成统一事实表和维表。
- 论文实力和研究前沿两部分数据颗粒度不足，需要提前设定口径或补数据。

## 数据源分级

### core

- `教育部学科与四大国际学科排名映射关系.xlsx`：subject_crosswalk；状态 `use`；教育部一级学科到软科、QS、US News、THE榜单学科的主映射表。
- `同济大学学院+学科映射关系20260509.xlsx`：tongji_subject_crosswalk；状态 `use`；同济学院、学位点、一级学科、第五轮评估、双一流、高峰高原、四大榜单名称之间的映射。
- `四大世界学科2025指标权重.xlsx`：indicator_weight；状态 `use`；四大榜单指标体系和权重的主数据源。
- `世界大学学科排名THE（2022-2026年）20260123.xlsx`：ranking_detail_history；状态 `use`；THE 2022-2026 学科排名总库，含同济、同济历史、排名方法。
- `全国双一流学科明细表2022&2017.v2.xlsx`：peer_scope；状态 `use`；确定双一流高校和学科范围，用于对标高校筛选。
- `第五轮评估结果（不完全）20260508.xlsx`：domestic_evaluation；状态 `use_with_caveat`；第五轮评估结果主表，但数据不完全。
- `同济大学第五轮学科评估结果+双一流+高峰高原.xlsx`：tongji_domestic_status；状态 `use`；同济各学科第五轮评估、双一流、高峰高原状态。

### current

- `2021-2026年软科世界一流学科排名（20260915已更新）.xlsx`：ranking_detail_history；状态 `use`；软科 2021-2026 学科排名总库，作为当前排名、历史趋势和分项指标的主数据源。
- `2026年QS世界学科排名20260326.xlsx`：ranking_detail；状态 `use`；QS 最新可用学科排名明细。
- `2026年THE世界学科排名20260123.xlsx`：ranking_detail；状态 `use`；THE 2026 学科排名明细。
- `2025-2026年度US News世界学科排名20251124.xlsx`：ranking_detail；状态 `use`；US News 最新可用学科排名明细。

### historical

- `2023年软科世界一流学科排名-20231030.xlsx`：ranking_detail；状态 `use`；软科 2023 发布年度学科排名明细。
- `2024年软科世界一流学科排名-20241111.xlsx`：ranking_detail；状态 `use`；软科 2024 发布年度学科排名明细。
- `2025年软科世界一流学科排名20251118.xlsx`：ranking_detail；状态 `use`；软科 2025 发布年度学科排名明细。
- `2023年QS世界学科排名.xlsx`：ranking_detail；状态 `use`；QS 2023 学科排名明细。
- `2024年QS世界学科排名-20240412.xlsx`：ranking_detail；状态 `use`；QS 2024 学科排名明细。
- `2025年QS世界大学学科排名20250313.xlsx`：ranking_detail；状态 `use`；QS 2025 学科排名明细。
- `2021US News世界学科排名2020年发布.xlsx`：ranking_detail；状态 `use`；US News 2021/2020发布口径历史数据。
- `2022US News世界学科排名20211026.xlsx`：ranking_detail；状态 `use`；US News 2022 学科排名历史数据。
- `2023US News世界学科排名20221026.xlsx`：ranking_detail；状态 `use`；US News 2023 学科排名历史数据。
- `2024-2025年US News世界学科排名明细数据-2024年6月27日.xlsx`：ranking_detail；状态 `use`；US News 2024-2025 学科排名明细。

### support

- `1.研究生教育学科专业目录（2022年）.xlsx`：official_subject_directory；状态 `use_when_needed`；官方学科门类、一级学科代码和名称校验。
- `世界大学学科排名2025指标权重.xlsx`：indicator_weight；状态 `validate_or_fallback`；指标权重备份/旧版来源。
- `全国高校第四轮&第三轮学科评估结果.xlsx`：domestic_evaluation；状态 `use`；第三轮、第四轮学科评估对比。
- `副本第五轮评估结果（不完全）20260508(分析).xlsx`：domestic_evaluation_enriched；状态 `validate_or_fallback`；第五轮评估分析副本，含第四轮、第三轮、省份、层次等扩展字段。

### optional

- `同济大学学院十五五学科建设目标-指标X7学科国际排名.xlsx`：planning_target；状态 `use_when_needed`；学院十五五建设目标与指标名称。

## 需要谨慎处理的数据

- `世界大学学科排名2025指标权重.xlsx`：如与主权重表冲突，先人工确认，不自动混用。
- `第五轮评估结果（不完全）20260508.xlsx`：报告必须注明数据不完全，避免过度结论。
- `副本第五轮评估结果（不完全）20260508(分析).xlsx`：可用于更丰富的国内评估图表，但需和主表校验。

## 未注册 Excel 文件

- `2021-2025年软科世界一流学科排名（20260603已更新）.xlsx`
- `2021-2026年中国内地QS&US世界学科排名数据（20260603更新）.xlsx`
- `2021年软科世界一流学科排名-20211119.xlsx`
- `2022THE学科领域排名.xlsx`
- `2022年QS学科排名202203.xlsx`
- `2022年软科世界一流学科排名-20220720.xlsx`
- `2023-2026年THE世界大学学科排名（20260603更新）.xlsx`
- `2026年US News世界学科排名20260616.xlsx`
- `37所一流高校学科论文数据（web of science）20260511.xlsx`
- `同济大学学院+学科映射关系（20260603更新）.xlsx`
- `四大世界学科2025指标权重（20260603更新）.xlsx`

## 缺失文件检查

- 注册表中的 Excel 文件均存在。

## 下一步数据处理建议

1. 建立 `processed/ranking.duckdb` 或等价中间库。
2. 先落 `dim_subject`，解决学科名称对齐。
3. 再落 `fact_ranking`，统一四大榜单的排名、年份、学校字段。
4. 再落 `fact_ranking_indicator` 和 `fact_indicator_weight`，支撑分项指标图。
5. 最后落国内评估和对标高校范围表，支撑 peer 分析。
