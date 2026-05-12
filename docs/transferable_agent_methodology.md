# 学科报告 Agent 可迁移方法论

## 目标

后续 agent 的任务不是“专门生成数学报告”，而是根据用户输入的学校、学院或一级学科，自动解析数据、生成图表、写分析文字，并最终填入 Word 模板。

数学只是当前 smoke test，因为参考报告是数学。所有核心数据层和查询协议都应支持迁移到其他同济学科。

## 总体链路

```text
用户输入
→ 目标学科解析
→ 统一数据层查询
→ artifact recipe 执行
→ 图表数据/图像/文字/来源追踪
→ Word 模板插入
→ 渲染核验
```

## 1. 用户输入层

后续 agent 应按 `configs/runtime/subject_request_schema.yaml` 接收请求。

最小输入：

```yaml
target_university: "同济大学"
target_subject: "数学"
report_year: 2026
peer_scope: "mainland_top200_by_ranking"
```

如果用户只给学院，则通过 `dim_subject` 反查可能的一级学科。如果一个学院对应多个一级学科，agent 应先列出候选项，而不是擅自选择。

## 2. 学科解析层

学科解析必须经过：

```text
dim_subject
dim_subject_alias
```

不要只依赖 `fact_ranking.subject_id`。原因是 THE 等榜单是领域排名，可能一对多覆盖多个教育部一级学科。

标准查询方式：

```sql
SELECT f.*
FROM fact_ranking f
JOIN dim_subject_alias a
  ON f.ranking_source = a.ranking_source
 AND f.ranking_subject_norm = a.ranking_subject_norm
WHERE a.subject_id = :target_subject_id;
```

学科解析核验结果见：

```text
processed/qa/subject_resolution/
```

其中：

- `subject_resolution_matrix.csv`：每个同济学科在四大榜单中的可用性。
- `subject_resolution_issues.csv`：缺 alias、未上榜、无排名记录等问题。
- `subject_latest_tongji_rankings.csv`：每个学科最新可查同济排名。

## 3. 数据层

当前已完成的主数据层：

```text
processed/dim_subject.csv
processed/dim_subject_alias.csv
processed/fact_ranking.csv
processed/fact_indicator_weight.csv
processed/dim_indicator.csv
processed/fact_ranking_indicator.csv
processed/ranking.sqlite
```

它们分别承担：

- `dim_subject`：一级学科、学院、同济学科、榜单学科主映射。
- `dim_subject_alias`：榜单学科别名、一对多领域映射、人工补充 alias。
- `fact_ranking`：四大榜单整体排名事实。
- `fact_indicator_weight`：四大榜单指标权重。
- `fact_ranking_indicator`：四大榜单分项指标得分/排名。

## 4. Artifact Recipe 层

每个图、表、文字块都应先查：

```text
configs/artifact_recipes/artifact_data_recipes.yaml
```

该文件定义：

- artifact id
- 数据源
- 字段
- 联表键
- 筛选条件
- 转换步骤
- 输出数据
- 风险和校验规则

后续不要临时决定某张图用哪些 Excel。

## 5. 单个 Artifact 标准输出

每个图表闭环应输出：

```text
outputs/artifacts/<artifact_id>/
  chart_data.csv
  chart_spec.json
  chart.svg 或 chart.png
  narrative.md
  source_trace.csv
  run_log.md
```

含义：

- `chart_data.csv`：可复画的数据。
- `chart_spec.json`：图表意图、编码、口径。
- `chart.svg/png`：可插入报告的图。
- `narrative.md`：分析文字草稿。
- `source_trace.csv`：来源文件、sheet、行号。
- `run_log.md`：本次生成过程留档。

## 6. 迁移到其他学科的步骤

以“物理学”为例：

1. 在 `dim_subject` 中找到 `subject_id`。
2. 在 `subject_resolution_matrix.csv` 中确认四大榜单状态。
3. 对 `ok` 的榜单执行对应 recipe。
4. 对 `has_peer_records_no_tongji` 写“未上榜/未检索到记录”。
5. 对 `missing_alias` 或 `has_alias_no_ranking_records` 先补 alias 或人工确认。
6. 生成 artifact 输出包。
7. 最后再进入 Word 插入和渲染核验。

## 7. 当前边界

已具备：

- 四大榜单整体排名。
- 四大榜单指标权重。
- 四大榜单分项指标。
- 同济全学科解析矩阵。

仍需谨慎：

- 论文实力目前是榜单代理指标，不是独立 WOS/Scopus 论文库。
- 研究前沿及学科交叉缺专门数据。
- THE 是领域排名，必须说明领域口径。
- 部分学科仍需补 alias 或确认不参与某榜单。
