# 目标学科解析规则

## 目的

后续 agent 不能写死“数学”。它需要根据用户输入的学院、一级学科或学科代码，稳定解析到四大国际榜单中的学科名称，并知道哪些榜单是一对一、哪些榜单是领域口径。

## 入口

推荐输入优先级：

1. `target_subject_code`：教育部一级学科代码，最稳定。
2. `target_subject`：教育部一级学科名称，例如 `数学`。
3. `target_college`：学院名称，需要通过同济学院学科映射表反查，可能对应多个一级学科。

## 解析流程

```text
用户输入
→ dim_subject 中定位 subject_id
→ dim_subject_alias 中查该 subject_id 的四大榜单别名
→ fact_ranking 使用 ranking_source + ranking_subject_norm 连接
→ 得到该学科在各榜单中的学校排名记录
```

## 为什么不能只用 fact_ranking.subject_id

`fact_ranking.subject_id` 只在一对一映射时可靠。THE 等榜单是领域排名，一个领域可能覆盖多个教育部一级学科，例如：

```text
数学 → THE 理学 / 物理学 / Physical Sciences 领域
物理学 → THE 理学 / 物理学 / Physical Sciences 领域
化学 → THE 理学 / 物理学 / Physical Sciences 领域
```

这种情况下，不能把 THE `理学` 强行写成某一个 subject_id。正确做法是：

```text
dim_subject_alias:
  subject_id = subject_0701
  ranking_source = THE
  ranking_subject_alias = 理学
```

查询时通过 alias 连接。

## 查询约定

后续查询某个目标学科时，必须使用：

```sql
SELECT f.*
FROM fact_ranking f
JOIN dim_subject_alias a
  ON f.ranking_source = a.ranking_source
 AND f.ranking_subject_norm = a.ranking_subject_norm
WHERE a.subject_id = :target_subject_id
```

而不是只写：

```sql
WHERE f.subject_id = :target_subject_id
```

## THE 口径

THE 是领域排名，报告中必须说明：

- THE 对应的是领域而不是教育部一级学科。
- 对数学等理学学科，THE 使用 `理学/Physical Sciences` 领域数据。
- 图表标题或注释中需要保留该口径说明。

## 缺口处理

如果某个目标学科在某榜单中没有 alias：

1. 不要猜。
2. 在 `subject_resolution_issues.csv` 中记录。
3. 报告生成时该榜单标为缺失或待确认。

如果某个 alias 对应多个 subject_id：

1. 这是领域口径或交叉学科的正常现象。
2. 不要强行去重到一个 subject_id。
3. 查询目标学科时通过 `subject_id + alias` 限定即可。
