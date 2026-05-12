# Artifact 执行契约

## 目标

本项目后续不把图表当作一次性分析结果，而是把每个图、表、文字块都视为一个可独立复现的 artifact。

每个 artifact 必须满足：

```text
固定脚本
→ 固定输入数据层
→ 固定输出目录
→ 固定产物文件
→ 固定核验规则
→ 固定过程留档
```

这样后续 Word agent 不需要重新猜 Excel 或临时分析，只需要按注册表运行脚本、读取产物、插入模板、渲染核验。

## 命名规则

artifact id 使用稳定英文蛇形命名：

```text
figure_01_tongji_subject_ranking_overview
figure_07_all_rankings_history
table_04_mainland_rank_band_distribution
```

脚本放在：

```text
scripts/build_artifact_<短名>.py
```

输出放在：

```text
outputs/artifacts/<artifact_id>/
```

## 脚本规则

每个 artifact 脚本应显式定义运行变量，不使用命令行参数：

```python
TARGET_UNIVERSITY = "同济大学"
TARGET_SUBJECT = "数学"
TARGET_SUBJECT_CODE = "0701"
REPORT_YEAR = 2026
```

后续迁移其他学科时，先改这些显式变量，或再抽象成统一 runner 配置。不要在脚本内部临时猜学科、猜文件、猜 sheet。

脚本读取数据时优先使用：

```text
processed/ranking.sqlite
processed/*.csv
configs/runtime/*.yaml|json|md
configs/artifact_recipes/artifact_data_recipes.yaml
```

不要覆盖 `data/` 原始文件。

## 图类 artifact 必需输出

图类 artifact 必须至少输出：

```text
chart_data.csv
chart_spec.json
chart.png
source_trace.csv
narrative.md
run_log.md
```

字段含义：

- `chart_data.csv`：真正用于绘图的数据。应尽量一行对应一个绘图点或一个图形元素。
- `chart_spec.json`：图表意图、字段口径、筛选规则、输出路径、核验摘要。
- `chart.png`：当前可视化预览，用于人工检查和 Word 插图。
- `source_trace.csv`：来源文件、sheet、行号、alias 命中痕迹。
- `narrative.md`：可放入报告的分析文字草稿。
- `run_log.md`：本次运行过程和核心统计。

## 表类 artifact 必需输出

表类 artifact 必须至少输出：

```text
table_data.csv
table_spec.json
table.png
source_trace.csv
narrative.md
run_log.md
```

推荐额外输出：

```text
table_matrix.csv
table.md
peer_records_top200.csv
```

字段含义：

- `table_data.csv`：长表形式的可复算统计数据。
- `table_matrix.csv`：报告中可直接展示的宽表或矩阵表。
- `table_spec.json`：统计口径、分组规则、筛选规则、校验结果。
- `table.png`：表格预览图。
- `table.md`：Markdown 表格，方便人工查看或复制到文档处理流程。
- `peer_records_top200.csv`：如果涉及对标高校，保留每个统计数量背后的高校明细。

## 数据与口径规则

所有 artifact 必须保留来源追踪：

```text
source_file
source_sheet
source_row
```

涉及学科映射时，查询必须经过：

```text
dim_subject
dim_subject_alias
```

不要只依赖 `fact_ranking.subject_id`，因为 THE 等榜单存在领域排名口径，一条榜单领域可能映射多个教育部一级学科。

涉及排名区间时，必须同时保留：

```text
rank_raw
rank_midpoint
```

正文和表格优先展示原始排名字符串，绘图或分档可使用 `rank_midpoint`。

## 去重规则

同一个榜单学科可能通过多个 alias 命中同一条事实记录。artifact 在计数、绘图、汇总前必须先合并 alias 命中。

推荐做法：

```text
原始 alias 命中记录
→ 按榜单、年份、学校、学科、原始排名、来源行去重
→ 保留 alias_type / ranking_subject_alias 合并痕迹
→ 再执行绘图或统计
```

如果同一榜单、同一学校、同一最新年度出现多个候选排名点，脚本应报错并要求人工核验，而不是自动选一个。

## 审计规则

每次新增 artifact 后，必须更新：

```text
configs/artifact_registry.yaml
```

然后运行：

```text
scripts/audit_artifact_outputs.py
```

审计脚本检查：

- 注册表是否可读。
- 脚本是否存在。
- 输出目录是否存在。
- 必需输出文件是否齐全。
- spec JSON 是否可解析。
- spec 中的 `artifact_id` 是否与注册表一致。
- 数据文件是否非空。
- source_trace 是否存在且非空。

审计输出放在：

```text
configs/artifact_audit/
logs/artifact_audit_run_log.md
```

## 当前已完成 artifact

```text
figure_01_tongji_subject_ranking_overview
figure_07_all_rankings_history
table_04_mainland_rank_band_distribution
```

它们是后续复制模式的基准样例。
