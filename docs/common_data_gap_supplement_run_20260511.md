# 共性数据缺口补充运行记录（2026-05-11）

## 目标

本次不是给单一学科打补丁，而是补充后续学科迁移都会复用的共性数据层：

1. 软科 GRAS 多年公开页面数据，用于恢复 `table_01_arwu_tongji_indicator_history`。
2. CWTS Leiden 五大宽领域论文指标代理，用于恢复 `figure_13` 至 `figure_16`。

## 新增/更新脚本

- `scripts/acquire_arwu_gras_public_pages.py`
  - 显式变量：`YEARS_TO_FETCH = [2023, 2024, 2025]`。
  - 从 ShanghaiRanking GRAS 年度页发现所有学科代码。
  - 下载并缓存 Nuxt `payload.js`。
  - 解析为宽表、长表、同济命中历史表和采集注册表。

- `scripts/process_external_cwts_sources.py`
  - 将原先数学/计算机专用处理扩展为五大 CWTS 宽领域。
  - 输出 181 个教育部学科到 CWTS 宽领域的映射。
  - 输出所有中国高校在五大领域的最新论文指标。

- `scripts/subject_artifact_builders.py`
  - 论文类图表不再只认数学/计算机，而是按当前学科查 `cwts_subject_field_crosswalk.csv`。
  - 软科同济分项历史表优先使用 `arwu_gras_public_tongji_history_2023_2025_long.csv`。

- `scripts/run_subject_agent.py`
  - readiness 逻辑已识别软科公开页补源。
  - paper metric source scan 已识别 CWTS 通用宽领域补源。

## 生成数据

### 软科 GRAS 公开页

- `external_data/processed/arwu_gras_public_subject_catalog.csv`
- `external_data/processed/arwu_gras_public_rankings_2023_2025_wide.csv`
- `external_data/processed/arwu_gras_public_rankings_2023_2025_long.csv`
- `external_data/processed/arwu_gras_public_tongji_history_2023_2025_wide.csv`
- `external_data/processed/arwu_gras_public_tongji_history_2023_2025_long.csv`
- `external_data/reports/arwu_gras_public_acquisition_registry.csv`
- `external_data/reports/arwu_gras_public_acquisition_summary.json`

运行结果：

- 年份：2023、2024、2025
- 学科页：167 个，全部下载成功
- 排名宽表：57,750 行
- 指标长表：866,250 行
- 同济命中学科-年份：111 行

### CWTS Leiden 宽领域代理

- `external_data/processed/cwts_subject_field_crosswalk.csv`
- `external_data/processed/cwts_traditional_2025_china_latest_all_fields.csv`
- `external_data/processed/cwts_traditional_2025_china_field_<field>_latest.csv`
- `external_data/processed/cwts_traditional_2025_tongji_all_fields_history.csv`
- `external_data/reports/cwts_processing_summary.json`

运行结果：

- 教育部学科映射：181 个
- 中国高校最新宽领域记录：2,136 行
- 每个 CWTS 领域：中国高校 356 行
- 同济历史记录：180 行

## 验证

用土木工程重新跑了一次 agent：

- 输出目录：`outputs/subject_agent_runs/20260511_102908_0814_土木工程`
- 生成 artifact：21 个
- artifact audit：21 pass / 0 fail
- 当前剩余缺口：3 个

已被补上的共性缺口：

- `table_01_arwu_tongji_indicator_history`
- `figure_13_paper_output_citation_relative_rank`
- `figure_14_paper_cnci_cpp_relative_rank`
- `figure_15_paper_highly_cited_relative_rank`
- `figure_16_paper_international_collab_relative_rank`

仍然保留的共性缺口：

- `figure_05_usnews_indicator_weight`
- `table_02_usnews_tongji_indicator_history`
- `figure_10_usnews_indicator_history_trend`

这些继续保留为缺口是合理的，因为当前没有稳定官方公开入口可以批量补齐 US News 学科权重和多年分项指标。

## 数据口径说明

软科 GRAS 公开页是正式网页公开数据，可以作为软科历史分项表补源。CWTS 是 Web of Science 口径的公开论文计量代理，但它是五大宽领域，不是教育部一级学科精确口径。生成报告时必须在 `source_trace`、图题或脚注里保留“CWTS 宽领域代理”的说明。

## 已核验来源

- [ShanghaiRanking GRAS 2025](https://www.shanghairanking.com/rankings/gras/2025)
- [ShanghaiRanking GRAS 2025 Methodology](https://www.shanghairanking.com/methodology/gras/2025)
- [CWTS Leiden Ranking fields](https://traditional.leidenranking.com/information/fields)
- [CWTS Leiden Traditional 2025 Zenodo record](https://zenodo.org/records/17473109)
