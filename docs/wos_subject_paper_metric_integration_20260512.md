# WOS 一级学科论文数据接入记录

- 接入时间：2026-05-12
- 原始文件：`data/37所一流高校学科论文数据（web of science）20260511.xlsx`
- 清洗输出：`external_data/processed/wos_37_university_subject_paper_metrics_20260511.csv`
- 统一长表：`processed/fact_paper_metric.csv`
- SQLite 表：`processed/ranking.sqlite::fact_paper_metric`

## 清洗规则

1. 学校中文名去除末尾日期后缀，例如 `同济大学20260511` 清洗为 `同济大学`。
2. `教育部一级学科` 拆分为 `ministry_subject_code`、`ministry_subject_name_en`，并按 `processed/dim_subject.csv` 回填 `subject_id`。
3. CNCI、Top 1%/10%、国际合作 CNCI 等源表空值保留为空，不替换为 0。
4. 原表没有单独统计年份字段，因此统一写为 `period_not_in_source_file`，并在 `proxy_scope_note` 中说明文件日期为 20260511。

## 接入结果

- WOS 清洗宽表：3511 行，37 所高校，97 个教育部一级学科。
- `fact_paper_metric` 当前包含两类来源：
  - `Web of Science subject paper metrics`：47726 行，一级学科口径，优先使用。
  - `CWTS Leiden Ranking 2025`：32040 行，宽领域代理，仅在 WOS 目标学科缺失时兜底。
- 论文类 artifact 合同已改为 `prefer_subject_wos_else_cwts_proxy`。

## 生成逻辑

`scripts/subject_artifact_builders.py` 中论文类四张图现在优先调用清洗后的 WOS 一级学科数据：

- `figure_13_paper_output_citation_relative_rank`：`WOS_documents`、`times_cited`
- `figure_14_paper_cnci_cpp_relative_rank`：`citation_impact`、`CNCI`
- `figure_15_paper_highly_cited_relative_rank`：`documents_top_1`、`highly_cited_papers`
- `figure_16_paper_international_collab_relative_rank`：`international_documents`、`pct_international_documents`

验证 run：`outputs/subject_agent_runs/20260512_094327_0812_计算机科学与技术`。该 run 的四张论文图 `chart_spec.json` 均为 `source_kind=wos`。
