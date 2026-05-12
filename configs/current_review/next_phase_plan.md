# 下一阶段计划：结构化入库与首个闭环

## 阶段目标

把当前已经梳理清楚的数据依赖，落成可查询、可复用、可审计的 `processed/` 数据层。完成后，后续每个图表不再直接读一堆 Excel，而是从统一事实表/维表中取数。

## 建议产物

```text
processed/
  ranking.duckdb
  dim_subject.csv
  dim_university.csv
  dim_indicator.csv
  fact_ranking.csv
  fact_ranking_indicator.csv
  fact_indicator_weight.csv
  fact_domestic_evaluation.csv
  fact_domestic_status.csv
  qa/
    field_mapping_report.md
    ranking_parse_exceptions.csv
    source_trace_summary.csv
```

## 执行顺序

### 1. 先做 `dim_subject`

目的：解决所有后续图表的入口问题。

输入：

- `教育部学科与四大国际学科排名映射关系.xlsx`
- `同济大学学院+学科映射关系20260509.xlsx`
- `1.研究生教育学科专业目录（2022年）.xlsx`

验收：

- 每个同济学科都能得到教育部一级学科、学院、软科/QS/US News/THE 对应名称。
- 数学这类参考学科可以完整解析。

### 2. 再做 `fact_ranking`

目的：支撑排名概览、四大排名历史、对标高校整体分析。

输入：

- 软科 2023-2025
- QS 2023-2026
- US News 2021-2026
- THE 2022-2026 总库和2026明细

关键处理：

- 统一学校字段。
- 统一学科字段。
- 分开保存 `release_year` 和 `ranking_year`。
- 解析 `rank_raw`、`rank_min`、`rank_max`、`rank_midpoint`。
- 保留 `source_file`、`source_sheet`、`source_row`。

验收：

- `figure_01_tongji_subject_ranking_overview` 可以直接查询。
- `figure_07_all_rankings_history` 可以直接查询。
- 排名区间解析异常有单独 QA 文件。

### 3. 做 `fact_indicator_weight`

目的：支撑四大指标权重图和指标共性图。

输入：

- `四大世界学科2025指标权重.xlsx`

关键处理：

- 单独处理软科、QS、US News、THE 的多级表头。
- 指标转成长表。
- 增加 `indicator_group`，但人工映射要可审查。

验收：

- 四大权重图可以从该表生成。
- 每个榜单/学科权重合计可核验。

### 4. 做 `fact_ranking_indicator`

目的：支撑分项指标相对排名图。

输入：

- 最新四大排名明细
- 必要时纳入历史明细

关键处理：

- 得分字段和排名字段分开。
- 软科/QS/THE 若只有得分，按同榜单、同学科、同年度重算相对排名。
- US News 当前表多为指标排名，直接保留排名字段。

验收：

- `figure_09_arwu_peer_indicator_relative_rank`
- `figure_10_qs_peer_indicator_relative_rank`
- `figure_11_usnews_peer_indicator_relative_rank`
- `figure_12_the_peer_indicator_relative_rank`

### 5. 做国内评估和 peer scope

目的：支撑国内评估、对标高校筛选。

输入：

- 双一流明细
- 第五轮评估结果（不完全）
- 第五轮分析副本
- 第三/四轮评估结果

验收：

- 能生成目标学科的双一流高校列表。
- 能生成第五轮/第四轮/第三轮对比表。
- 报告中自动带出“不完全数据”说明。

## 推荐第一个闭环

先做：

```text
figure_01_tongji_subject_ranking_overview
figure_07_all_rankings_history
```

原因：

- 只依赖 `dim_subject` + `fact_ranking`。
- 能验证最关键的跨表逻辑。
- 一旦跑通，后续对标高校整体表也能自然扩展。

## 暂不建议马上做的内容

- 论文实力四张图：先标成代理指标，等 `fact_ranking_indicator` 稳定后再做。
- 研究前沿及学科交叉：当前缺数据，不建议硬生成。
