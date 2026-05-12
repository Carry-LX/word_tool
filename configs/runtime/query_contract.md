# 查询契约

## 总原则

后续图表和文字生成不得直接临时翻 Excel。应优先查询 `processed/ranking.sqlite` 或 `processed/*.csv`。

## 必须保留的追踪字段

所有事实表必须保留：

- `source_file`
- `source_sheet`
- `source_row`

报告中的关键数字需要能够追溯到这些字段。

## 学科查询

目标学科查询必须经过 `dim_subject_alias`：

```sql
SELECT f.*
FROM fact_ranking f
JOIN dim_subject_alias a
  ON f.ranking_source = a.ranking_source
 AND f.ranking_subject_norm = a.ranking_subject_norm
WHERE a.subject_id = :target_subject_id;
```

## 排名字段

排名必须同时保留：

- `rank_raw`
- `rank_min`
- `rank_max`
- `rank_midpoint`
- `rank_note`

趋势图可以使用 `rank_midpoint`，但表格和正文要保留 `rank_raw`。

## 年份字段

必须区分：

- `release_year`
- `ranking_year`

不要混成一个 `year`。

## THE 领域口径

当 `ranking_source = THE` 且 alias 是领域时，图表和正文必须说明领域口径。

## 代理指标

论文实力若使用榜单代理指标，必须在输出中记录：

- `proxy_source`
- `proxy_metric`
- `proxy_limitations`

不能写成独立 WOS/Scopus 论文统计结论。
