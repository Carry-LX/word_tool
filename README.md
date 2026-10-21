## 在另一台电脑运行

代码、原始 Excel 和模板通过 GitHub 私有仓库迁移；中间数据、补充数据、示例报告和 Windows 渲染工具通过同仓库 Release 恢复。新电脑准备好 Python 3.12 x64、GitHub CLI 登录和 Microsoft Word 后，双击 `setup_new_computer.cmd`，完成后双击 `start_report_demo.cmd`。

详细步骤、数据范围和临时文件清理机制见 [docs/MIGRATION.md](docs/MIGRATION.md)。初始化不需要安装 Codex。

## 接手入口

如果由新的 AI 或开发者接手，请先读 `AI_HANDOFF/START_HERE.md`、`HANDOFF.md` 和 `DECISIONS.md`。根目录的 `START_HERE_FOR_NEXT_AGENT.md` 包含历史阶段，当前运行状态以新交接说明和实际配置为准。

## 2026-05-11 全局学科 alias 与可迁移性审计更新

本次已从“数学样例”推进到“全学科数据层”治理：

- `processed/qa/subject_mapping_unmatched.csv` 已清零，原先 82 个未映射原始学科名已通过 alias 拆分规则和 `subject_alias_rules` 处理。
- 新增 `scripts/update_global_subject_alias_rules.py`，用于可复现写入 QS、US News、软科的人工学科别名规则。
- 新增 `scripts/audit_global_subject_data_readiness.py`，输出 181 个学科的可迁移 readiness。
- 新增交接文档：`docs/global_subject_data_readiness_20260511.md`。
- 重要口径：`subject_id_missing_rows` 仍存在，但主要来自 THE/US News/QS 的多学科领域口径，后续 agent 必须通过 `dim_subject_alias` join 查询，不能只看 `fact_ranking.subject_id`。

复现顺序：

```text
C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts/update_global_subject_alias_rules.py
C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts/build_processed_core.py
C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts/build_subject_resolution_report.py
C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts/smoke_test_subject_migration.py
C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts/audit_global_subject_data_readiness.py
```

# 表格数据分析 Agent 项目说明

## 当前目标

本项目的目标是：基于 `data/` 目录中的排名、学科映射、指标权重、国内评估等表格数据，自动生成类似参考报告样式的 Word 学科分析报告。

当前阶段先不急着生成最终 Word，而是先把数据层理清楚：

1. 哪些 Excel 有用，哪些只是参考材料。
2. 每个 Excel 在报告中承担什么角色。
3. 哪些章节必须多表联接才能得到支撑数据。
4. 后续 agent 应该按什么统一数据模型取数、分析、画图、写文字。

## 重要原始文件

原始文件目录：

```text
E:\projects\water\word_tool\data
```

目标报告骨架模板：

```text
data/【标黄】同济大学学科分析报告——理科（2026年）.docx
```

图表和表格样式参考报告：

```text
data/同济大学XX学科的国际排名发展分析-2026年5月.docx
```

这份参考报告里有较完整的图表和表格样式，后续生成报告时应主要参考它的结构和表达方式。

## 已完成的阶段一产物

### 1. 原始资产盘点

位置：

```text
configs/stage1_inventory/
```

核心文件：

- `data_catalog.json`：所有 Excel 的文件、sheet、字段、样例值。
- `target_template_outline.json`：目标标黄模板的段落结构。
- `reference_report_outline.json`：参考报告的段落、表格、图片结构。
- `reference_report_structure.md`：参考报告中章节、图表、表格标题摘录。
- `report_slots.yaml`：报告待生成位置的 slot 定义。
- `slot_data_mapping.yaml`：每个 slot 初步对应哪些数据源。
- `entity_aliases.yaml`：学校、榜单、字段别名初稿。
- `stage1_summary.md`：阶段一摘要。

复现脚本：

```text
scripts/build_stage1_inventory.py
```

### 2. 数据治理与联表设计

位置：

```text
configs/data_governance/
```

核心文件：

- `source_registry.yaml`：25 个 Excel 的分级、角色、用途和状态。
- `source_registry.csv`：更方便人工浏览的数据源注册表。
- `canonical_data_model.yaml`：后续统一数据模型，包含维表和事实表设计。
- `data_relationships.md`：关键分析任务的联表路径。
- `data_cleaning_contract.md`：数据清洗约束，防止后续脚本污染原始数据或混淆口径。
- `data_readiness_report.md`：当前数据完备性、可用性和风险说明。
- `processing_roadmap.md`：后续数据处理路线。

复现脚本：

```text
scripts/build_data_governance.py
```

### 3. 图表/表格级 Recipe

位置：

```text
configs/artifact_recipes/
```

核心文件：

- `reference_artifact_index.yaml`：参考报告中的图题、表题、物理表格和图片索引。
- `artifact_data_recipes.yaml`：每个图表/表格的数据源、字段、联表键、过滤条件、处理步骤和验证规则。
- `artifact_gaps.md`：图表数据缺口和谨慎口径。
- `artifact_priority.md`：后续实现优先级。
- `recipe_validation.json`：自动核验结果，检查 recipe 中引用的文件、sheet 和字段是否存在。
- `artifact_recipe_summary.md`：本阶段摘要。

复现脚本：

```text
scripts/build_artifact_recipes.py
```

当前 recipe 覆盖情况：

- 参考报告 caption artifact：22 个。
- 参考报告物理表格：8 个。
- 参考报告物理图片：14 张。
- 当前 recipe：27 个。
- 自动核验：缺失文件 0、缺失 sheet 0、字段提示 0。

### 3.1. Word 图表槽位完整覆盖映射

位置：

```text
configs/template_slot_inventory/
```

核心文件：

- `reference_blocks.csv`：参考报告按 Word 顺序抽取的段落、图片段落、表格块。
- `reference_slots.csv`：参考报告候选图片、表格、图题/表题槽位。
- `logical_slot_artifact_mapping.csv`：最终逻辑槽位到 artifact 的覆盖表。
- `raw_slot_coverage.csv`：44 个原始槽位逐一映射到逻辑槽位。
- `proposed_new_artifacts.csv`：需要新增的 artifact 清单。
- `full_slot_artifact_mapping.md`：人工可读的完整覆盖总结。
- `coverage_summary.json`：覆盖数量摘要。

复现脚本：

```text
scripts/build_template_slot_inventory.py
scripts/build_full_slot_artifact_mapping.py
```

完整覆盖结论：

- 参考报告原始槽位：44 个。
- 图片对象：14 个。
- 表格对象：8 个。
- 图题/表题类段落：22 个。
- 合并后的真实逻辑槽位：23 个。
- 原始槽位已映射：44 个。
- 原始槽位未映射：0 个。
- 已有注册 artifact 可支撑：9 个逻辑槽位。
- 仍需新增 artifact：14 个逻辑槽位。
- 明确数据缺口：5 个逻辑槽位。

重要边界：

- US News 数学权重当前缺失，不能硬套其他学科权重。
- 软科、US News 的同济分项指标历史当前只入库最新年，不能直接生成多年历史表。
- 论文整体、CNCI/篇均被引、高被引 TOP、国际合著四类图未发现独立论文指标数据源，不能用排名表臆造。

### 4. 当前数据复核与下一阶段计划

位置：

```text
configs/current_review/
```

核心文件：

- `current_data_logic_review.md`：当前数据完整性、核心数据源、recipe状态、数据层到图表的依赖关系。
- `artifact_source_matrix.csv`：每个图表/表格对应的数据源矩阵。
- `next_phase_plan.md`：下一阶段结构化入库和首个闭环的执行计划。

复现脚本：

```text
scripts/build_current_data_review.py
```

当前复核结论：

- Excel 文件：25 个。
- Excel sheet：37 个。
- 注册 Excel 源：25 个。
- 未注册 Excel：0 个。
- Artifact recipe：27 个。
- 缺失文件：0 个。
- 缺失 sheet：0 个。
- 缺失字段：0 个。

数据层到图表的主依赖：

- `fact_ranking`：支撑排名概览、四大排名历史、对标高校整体排名表。
- `fact_indicator_weight`：支撑四大指标权重图和指标共性图。
- `fact_ranking_indicator`：支撑分项指标相对排名图和细分指标历史表。
- `fact_domestic_evaluation`：支撑国内评估对比。
- `proxy_metrics`：暂时支撑论文实力代理分析。
- `missing_external_data`：研究前沿及学科交叉，当前缺专门数据。

## 已完成的首批结构化数据层

位置：

```text
processed/
```

核心文件：

- `dim_subject.csv`：教育部一级学科、同济学院/学科、四大榜单学科名称映射。
- `dim_subject_alias.csv`：榜单学科名到教育部一级学科的别名映射，支持 THE 这类一对多领域映射。
- `fact_ranking.csv`：四大榜单排名事实表，统一学校、学科、年份、排名区间和来源追踪字段。
- `ranking.sqlite`：同样数据的 SQLite 版本，方便后续查询。
- `qa/processed_core_summary.md`：首批数据层 QA 摘要。
- `qa/closed_loop_support_check.md`：验证 `figure_01_tongji_subject_ranking_overview` 和 `figure_07_all_rankings_history` 的数据支撑。
- `qa/closed_loop_tongji_math_fact_ranking.csv`：同济数学四大榜单历史记录。
- `qa/closed_loop_tongji_math_latest_overview.csv`：同济数学四大榜单最新记录。

复现脚本：

```text
scripts/build_processed_core.py
```

过程留档：

```text
logs/processed_core_run_log.md
```

当前核验结果：

- `dim_subject`：181 行。
- `fact_ranking`：260235 行。
- 排名解析异常：0 行。
- 同济大学排名记录：387 行。
- 同济数学闭环记录：13 行。
- 同济数学最新概览覆盖：QS、THE、US News、软科。

口径说明：

- `subject_id` 缺失不完全等于错误。THE 等大领域排名是一对多映射，记录在 `dim_subject_alias.csv` 中，后续查询目标学科时应通过 alias join。
- `subject_alias_no_match_rows` 主要是国际榜单中没有进入教育部一级学科映射表的科目或历史英文科目，详见 `qa/subject_mapping_unmatched.csv`。
- THE 的 `理学` 为领域口径，生成报告时需要在图题或注释中说明。

## Agent 运行时协议与学科解析核验

位置：

```text
configs/runtime/
```

核心文件：

- `subject_request_schema.yaml`：后续 agent 的输入格式，避免写死数学。
- `subject_resolution_rules.md`：如何从学院/一级学科解析到四大榜单学科。
- `query_contract.md`：后续查询必须遵循的规则，尤其是通过 `dim_subject_alias` 查询。
- `peer_scope_rules.yaml`：对标高校范围规则。

学科解析核验输出：

```text
processed/qa/subject_resolution/
```

核心文件：

- `subject_resolution_summary.md`：同济学科解析核验摘要。
- `subject_resolution_matrix.csv`：同济一级学科 x 四大榜单解析矩阵。
- `subject_resolution_issues.csv`：缺 alias、未上榜、无排名记录的问题清单。
- `subject_latest_tongji_rankings.csv`：每个同济学科在四大榜单中最新可查记录。

复现脚本：

```text
scripts/build_subject_resolution_report.py
```

过程留档：

```text
logs/subject_resolution_run_log.md
```

当前核验结果：

- 同济相关一级学科：44 个。
- 学科-榜单解析组合：176 行。
- 可直接查到同济记录：96 行。
- 需要处理或说明的问题行：80 行。
- THE 领域映射：38 行。

这些问题行不是简单失败，主要分三类：

1. `missing_alias`：映射表中没有该榜单学科别名，需要补 alias 或确认该学科不参与该榜单。
2. `has_alias_no_ranking_records`：有 alias，但排名表里没有对应记录，可能是榜单没有该学科或口径不同。
3. `has_peer_records_no_tongji`：榜单里有其他高校记录，但没有同济记录，报告中应标记为未上榜或待确认。

后续 agent 处理原则：

- 输入任一学科时，先查 `subject_resolution_matrix.csv` 判断四大榜单可用性。
- 对 `ok` 的榜单正常生成图表。
- 对 `has_peer_records_no_tongji` 的榜单，生成“同济未上榜/未检索到记录”的说明，不要强行造数。
- 对 `missing_alias` 和 `has_alias_no_ranking_records`，进入人工确认或补 alias 流程。
- THE 相关图表必须说明领域口径。

人工 alias 配置：

```text
configs/runtime/manual_subject_aliases.json
```

该文件用于维护自动映射无法覆盖的榜单学科别名、领域口径和已确认无映射项。例如 THE 原始表中工程领域使用 `工学`，而同济映射表中写作 `工程`，该差异已通过人工 alias 规则处理。

## 已完成的指标权重数据层

位置：

```text
processed/
```

核心文件：

- `fact_indicator_weight.csv`：四大世界学科排名指标权重事实表。
- `dim_indicator.csv`：指标维表。
- `qa/indicator_weights/indicator_weight_summary.md`：指标权重 QA 摘要。
- `qa/indicator_weights/indicator_weight_totals.csv`：各榜单/学科或领域的权重合计。
- `qa/indicator_weights/indicator_weight_total_exceptions.csv`：权重合计异常清单。

复现脚本：

```text
scripts/build_indicator_weights.py
```

过程留档：

```text
logs/indicator_weight_run_log.md
```

当前核验结果：

- `fact_indicator_weight`：1104 行。
- `dim_indicator`：54 行。
- 权重合计异常：0 行。
- 软科、QS、THE 多级/特殊表头已分别处理。
- THE 同时保留一级指标和二级指标，权重合计 QA 使用一级指标，避免重复计数。

## 已完成的分项指标数据层

位置：

```text
processed/
```

核心文件：

- `fact_ranking_indicator.csv`：四大榜单分项指标事实表，已拆成长表。
- `qa/ranking_indicators/ranking_indicator_summary.md`：分项指标 QA 摘要。
- `qa/ranking_indicators/ranking_indicator_coverage.csv`：各榜单指标覆盖情况。
- `qa/ranking_indicators/tongji_ranking_indicators.csv`：同济大学分项指标记录。
- `qa/ranking_indicators/p1_peer_indicator_smoke_test.csv`：P1 分项指标图数据可用性核验。
- `qa/ranking_indicators/p1_tongji_missing_indicators.csv`：P1 样例中同济缺失的指标。

复现脚本：

```text
scripts/build_ranking_indicators.py
```

过程留档：

```text
logs/ranking_indicator_run_log.md
```

当前核验结果：

- `fact_ranking_indicator`：968658 行。
- 同济分项指标记录：1245 行。
- score 指标：493992 行。
- rank 指标：474666 行。
- P1 分项指标图均有数据支撑：软科、QS、US News、THE。

重要口径：

- 软科、QS、THE 的得分字段已按同榜单/同学科/同年度/同指标重算 `relative_rank_in_subject`。
- US News 多数分项为排名字段，保留原排名，并统一写入相对排名字段用于绘图。
- 数学样例中，软科和 QS 的 `总得分` 对同济为空；分项指标可用，后续图表应避免把缺失总得分当作 0。

## 可迁移 Agent 思路

当前项目不应理解成“只生成数学报告”，而应理解成一个可迁移到其他同济学科的报告生成链路。数学只是因为参考报告最完整，所以先作为 smoke test。

完整链路见：

```text
docs/transferable_agent_methodology.md
```

核心流程：

```text
用户输入学校/学院/一级学科
→ 通过 dim_subject 和 dim_subject_alias 解析到统一 subject_id
→ 从 processed/ranking.sqlite 查询事实表
→ 按 artifact recipe 生成图表数据、图片、文字和来源追踪
→ 插入 Word 模板对应位置
→ 渲染核验 Word 版式
```

后续迁移到其他学科时，第一步不是改图，而是先查：

```text
processed/qa/subject_resolution/subject_resolution_matrix.csv
processed/qa/subject_resolution/subject_resolution_issues.csv
processed/qa/subject_resolution/subject_latest_tongji_rankings.csv
```

只有确认该学科在对应榜单中有可解释的数据口径，再进入图表生成。

## Artifact 可复现执行体系

当前项目已经从“一次性数据分析”转为“artifact 级可复现生成”。后续每个图、表、文字块都应有独立脚本、独立输出目录、独立 spec、独立来源追踪和独立日志。

执行契约：

```text
docs/artifact_execution_contract.md
```

artifact 注册表：

```text
configs/artifact_registry.yaml
```

注册表记录每个 artifact 的：

- `artifact_id`
- `artifact_type`
- `script_path`
- `output_dir`
- `required_outputs`
- `optional_outputs`
- `data_dependencies`
- 当前核验状态和摘要

新增 artifact 时，必须按以下流程：

1. 新建 `scripts/build_artifact_xxx.py`。
2. 输出到 `outputs/artifacts/<artifact_id>/`。
3. 至少生成主数据、spec、图片或表格预览、source trace、narrative、run log。
4. 更新 `configs/artifact_registry.yaml`。
5. 运行审计脚本。
6. 将结果写回 README 或过程文档。

审计脚本：

```text
scripts/audit_artifact_outputs.py
```

审计输出：

```text
configs/artifact_audit/artifact_audit_report.md
configs/artifact_audit/artifact_audit_report.json
configs/artifact_audit/artifact_audit_report.csv
logs/artifact_audit_run_log.md
```

当前审计结果：

- 注册 artifact：10 个。
- 审计通过：10 个。
- 审计失败：0 个。
- 已通过：`figure_01_tongji_subject_ranking_overview`、`figure_07_all_rankings_history`、`figure_09_arwu_peer_indicator_relative_rank`、`figure_11_usnews_peer_indicator_relative_rank`、`figure_12_the_peer_indicator_relative_rank`、`table_04_mainland_rank_band_distribution`、`table_05_arwu_mainland_peer_ranking`、`table_06_usnews_mainland_peer_ranking`、`table_07_qs_mainland_peer_ranking`、`table_08_the_mainland_peer_ranking`。

## 首个图件闭环

已完成第一个端到端图件样例：

```text
figure_07_all_rankings_history
```

复现脚本：

```text
scripts/build_artifact_figure_07.py
```

输出目录：

```text
outputs/artifacts/figure_07_all_rankings_history/
```

核心产物：

- `chart_data.csv`：真正用于绘图的数据，一行一个榜单年度点。
- `source_trace.csv`：来源文件、sheet、行号和 alias 命中痕迹。
- `chart_spec.json`：图表意图、字段口径、输出文件路径。
- `chart.png`：当前生成的图。
- `narrative.md`：可填入报告的分析文字草稿。
- `run_log.md`：本次 artifact 运行记录。

本次核验结果：

- alias 去重前匹配行数：37 行。
- alias 去重后绘图点：13 行。
- 覆盖榜单：QS、THE、US News、软科。
- 发现并处理了一个关键问题：同一榜单学科可能被多个 alias 同时命中，后续 artifact 必须先合并 alias 命中，再绘图或汇总，否则会重复计数。

如果要把这张图交给其他 AI 重新绘制，应至少提供：

```text
outputs/artifacts/figure_07_all_rankings_history/chart_data.csv
outputs/artifacts/figure_07_all_rankings_history/chart_spec.json
outputs/artifacts/figure_07_all_rankings_history/source_trace.csv
```

其中 `chart_data.csv` 说明画什么，`chart_spec.json` 说明怎么画和图表意图，`source_trace.csv` 用于核验每个数字来自哪里。

## 第二个图件闭环

已完成排名概览图：

```text
figure_01_tongji_subject_ranking_overview
```

复现脚本：

```text
scripts/build_artifact_figure_01.py
```

输出目录：

```text
outputs/artifacts/figure_01_tongji_subject_ranking_overview/
```

核心产物同样包括：

- `chart_data.csv`：四大榜单最新可用年度的排名概览，一行一个榜单。
- `source_trace.csv`：来源文件、sheet、行号和 alias 命中痕迹。
- `chart_spec.json`：选择最新排名的规则、图表口径、输出路径。
- `chart.png`：概览卡片图。
- `narrative.md`：报告开头可用的分析文字草稿。
- `run_log.md`：本次 artifact 运行记录。

本次核验结果：

- alias 去重前匹配行数：37 行。
- 最新排名概览点：4 行。
- 覆盖榜单：软科、QS、US News、THE。
- 选择规则：每个榜单先取最新 `release_year`，再取最新 `ranking_year`。
- 图中保留各榜单原始排名口径，不把四个榜单做强行等距比较。

如果要把这张图交给其他 AI 重新绘制，应至少提供：

```text
outputs/artifacts/figure_01_tongji_subject_ranking_overview/chart_data.csv
outputs/artifacts/figure_01_tongji_subject_ranking_overview/chart_spec.json
outputs/artifacts/figure_01_tongji_subject_ranking_overview/source_trace.csv
```

## 第一个对标分布表闭环

已完成内地高校位次分布表：

```text
table_04_mainland_rank_band_distribution
```

复现脚本：

```text
scripts/build_artifact_table_04.py
```

输出目录：

```text
outputs/artifacts/table_04_mainland_rank_band_distribution/
```

核心产物：

- `table_data.csv`：长表形式的分档统计，一行一个榜单/位次区间。
- `table_matrix.csv`：报告表格可直接使用的矩阵形式。
- `peer_records_top200.csv`：四大榜单前200内地高校明细，可继续支撑对标高校列表和分项指标分析。
- `source_trace.csv`：来源文件、sheet、行号和 alias 命中痕迹。
- `table_spec.json`：统计口径、分档规则、校验结果和输出路径。
- `table.md`：Markdown 表格。
- `table.png`：表格预览图。
- `narrative.md`：报告中可使用的文字草稿。
- `run_log.md`：本次 artifact 运行记录。

本次核验结果：

- alias 去重前匹配行数：1460 行。
- 最新年度内地高校去重记录：330 行。
- 前200内地高校明细：98 行。
- 前200分布：软科 21 所、QS 16 所、US News 43 所、THE 18 所。
- 分档合计校验全部通过：每个榜单的 `前50 + 51-100 + 101-200` 均等于 `前200合计`。
- 前200明细中，同一榜单内没有高校重复计入。

如果要把这张表交给其他 AI 重新绘制或改样式，应至少提供：

```text
outputs/artifacts/table_04_mainland_rank_band_distribution/table_matrix.csv
outputs/artifacts/table_04_mainland_rank_band_distribution/table_data.csv
outputs/artifacts/table_04_mainland_rank_band_distribution/table_spec.json
outputs/artifacts/table_04_mainland_rank_band_distribution/peer_records_top200.csv
```

其中 `table_matrix.csv` 用于直接绘制表格，`table_data.csv` 说明统计口径，`table_spec.json` 说明分档和校验规则，`peer_records_top200.csv` 可用于复查每个数量背后的高校明细。

## 第二个对标明细表闭环

已完成软科内地高校前列排名比较表：

```text
table_05_arwu_mainland_peer_ranking
```

复现脚本：

```text
scripts/build_artifact_table_05.py
```

输出目录：

```text
outputs/artifacts/table_05_arwu_mainland_peer_ranking/
```

核心产物：

- `table_data.csv`：软科最新年前200内地高校样本的逐年排名长表。
- `table_matrix.csv`：报告展示用宽表，学校为行、年份为列。
- `latest_peer_records.csv`：软科最新年前200内地高校样本。
- `tongji_scope_check.csv`：同济大学是否进入该样本的核验记录。
- `source_trace.csv`：来源文件、sheet、行号和 alias 命中痕迹。
- `table_spec.json`：筛选规则、输出路径和校验结果。
- `table.md`：Markdown 表格。
- `table.png`：表格预览图。
- `narrative.md`：报告中可使用的文字草稿。
- `run_log.md`：本次 artifact 运行记录。

本次核验结果：

- alias 去重前匹配行数：486 行。
- 软科内地高校去重记录：243 行。
- 软科 2025 年数学前200内地高校：21 所。
- `table_matrix.csv` 行数：21 行。
- 最新年前200样本高校唯一性：21 所高校，无重复。
- 同济大学未进入软科 2025 数学前200样本；最新记录为 `401-500`，单独写入 `tongji_scope_check.csv`。
- 注册表已更新，统一审计通过：4 个 artifact 全部 pass。

如果要把这张表交给其他 AI 重新绘制或改样式，应至少提供：

```text
outputs/artifacts/table_05_arwu_mainland_peer_ranking/table_matrix.csv
outputs/artifacts/table_05_arwu_mainland_peer_ranking/table_data.csv
outputs/artifacts/table_05_arwu_mainland_peer_ranking/table_spec.json
outputs/artifacts/table_05_arwu_mainland_peer_ranking/latest_peer_records.csv
outputs/artifacts/table_05_arwu_mainland_peer_ranking/tongji_scope_check.csv
```

其中 `table_matrix.csv` 用于直接绘制表格，`table_data.csv` 用于复算历年变化，`latest_peer_records.csv` 定义最新年前200样本，`tongji_scope_check.csv` 用于说明同济是否进入该对标范围。

## 第三个对标明细表闭环

已完成 US News 内地高校前列排名比较表：

```text
table_06_usnews_mainland_peer_ranking
```

复现脚本：

```text
scripts/build_artifact_table_06.py
```

输出目录：

```text
outputs/artifacts/table_06_usnews_mainland_peer_ranking/
```

核心产物：

- `table_data.csv`：US News 最新排名年度前200内地高校样本的逐排名年度长表。
- `table_matrix.csv`：报告展示用宽表，学校为行、排名年度为列。
- `latest_peer_records.csv`：US News 2026 排名年度前200内地高校样本。
- `tongji_scope_check.csv`：同济大学是否进入该样本的核验记录。
- `source_trace.csv`：来源文件、sheet、行号和 alias 命中痕迹。
- `table_spec.json`：筛选规则、年份口径、校名匹配规则、输出路径和校验结果。
- `table.md`：Markdown 表格。
- `table.png`：表格预览图。
- `narrative.md`：报告中可使用的文字草稿。
- `run_log.md`：本次 artifact 运行记录。

本次核验结果：

- alias 去重前匹配行数：998 行。
- US News 内地高校去重记录：341 行。
- US News 2026 排名年度数学前200内地高校：43 所。
- `table_matrix.csv` 行数：43 行。
- 最新年前200样本高校唯一性：43 所高校，无重复。
- 同济大学未进入 US News 2026 排名年度数学前200样本；最新记录为 `261`，单独写入 `tongji_scope_check.csv`。
- 口径修正：US News 早期数据中 `country_or_region='china'` 被视为中国内地；历史学校匹配优先使用英文名归一化。
- 注册表已更新，统一审计通过：5 个 artifact 全部 pass。

如果要把这张表交给其他 AI 重新绘制或改样式，应至少提供：

```text
outputs/artifacts/table_06_usnews_mainland_peer_ranking/table_matrix.csv
outputs/artifacts/table_06_usnews_mainland_peer_ranking/table_data.csv
outputs/artifacts/table_06_usnews_mainland_peer_ranking/table_spec.json
outputs/artifacts/table_06_usnews_mainland_peer_ranking/latest_peer_records.csv
outputs/artifacts/table_06_usnews_mainland_peer_ranking/tongji_scope_check.csv
```

其中 `table_matrix.csv` 用于直接绘制表格，`table_data.csv` 用于复算历年变化，`table_spec.json` 说明 US News 的双年份与地区口径，`latest_peer_records.csv` 定义最新排名年度前200样本，`tongji_scope_check.csv` 用于说明同济是否进入该对标范围。

## 第四个对标明细表闭环

已完成 QS 内地高校前列排名比较表：

```text
table_07_qs_mainland_peer_ranking
```

复现脚本：

```text
scripts/build_artifact_table_07.py
```

输出目录：

```text
outputs/artifacts/table_07_qs_mainland_peer_ranking/
```

核心产物：

- `table_data.csv`：QS 最新排名年度前200内地高校样本的逐排名年度长表。
- `table_matrix.csv`：报告展示用宽表，学校为行、排名年度为列。
- `latest_peer_records.csv`：QS 2026 排名年度前200内地高校样本。
- `tongji_scope_check.csv`：同济大学是否进入该样本的核验记录。
- `source_trace.csv`：来源文件、sheet、行号和 alias 命中痕迹。
- `table_spec.json`：筛选规则、地区口径、校名匹配规则、输出路径和校验结果。
- `table.md`：Markdown 表格。
- `table.png`：表格预览图。
- `narrative.md`：报告中可使用的文字草稿。
- `run_log.md`：本次 artifact 运行记录。

本次核验结果：

- alias 去重前匹配行数：696 行。
- QS 内地高校去重记录：174 行。
- QS 2026 排名年度数学前200内地高校：16 所。
- `table_matrix.csv` 行数：16 行。
- 最新年前200样本高校唯一性：16 所高校，无重复。
- 同济大学未进入 QS 2026 排名年度数学前200样本；最新记录为 `201-250`，单独写入 `tongji_scope_check.csv`。
- 口径修正：QS 早期数据中 `country_or_region='China (Mainland)'` 被视为中国内地；历史学校匹配同时使用中文名和英文名归一化。
- 注册表已更新，统一审计通过：6 个 artifact 全部 pass。

如果要把这张表交给其他 AI 重新绘制或改样式，应至少提供：

```text
outputs/artifacts/table_07_qs_mainland_peer_ranking/table_matrix.csv
outputs/artifacts/table_07_qs_mainland_peer_ranking/table_data.csv
outputs/artifacts/table_07_qs_mainland_peer_ranking/table_spec.json
outputs/artifacts/table_07_qs_mainland_peer_ranking/latest_peer_records.csv
outputs/artifacts/table_07_qs_mainland_peer_ranking/tongji_scope_check.csv
```

其中 `table_matrix.csv` 用于直接绘制表格，`table_data.csv` 用于复算历年变化，`table_spec.json` 说明 QS 的地区和校名匹配口径，`latest_peer_records.csv` 定义最新排名年度前200样本，`tongji_scope_check.csv` 用于说明同济是否进入该对标范围。

## 第五个对标明细表闭环

已完成 THE 内地高校前列排名比较表：

```text
table_08_the_mainland_peer_ranking
```

复现脚本：

```text
scripts/build_artifact_table_08.py
```

输出目录：

```text
outputs/artifacts/table_08_the_mainland_peer_ranking/
```

核心产物：

- `table_data.csv`：THE 最新排名年度前200内地高校样本的逐排名年度长表。
- `table_matrix.csv`：报告展示用宽表，学校为行、排名年度为列。
- `latest_peer_records.csv`：THE 2026 排名年度理学领域前200内地高校样本。
- `tongji_scope_check.csv`：同济大学是否进入该样本的核验记录。
- `source_trace.csv`：来源文件、sheet、行号和 alias 命中痕迹。
- `table_spec.json`：筛选规则、THE 领域口径、地区修正规则、输出路径和校验结果。
- `table.md`：Markdown 表格。
- `table.png`：表格预览图。
- `narrative.md`：报告中可使用的文字草稿。
- `run_log.md`：本次 artifact 运行记录。

本次核验结果：

- alias 去重前匹配行数：630 行。
- THE 理学领域内地高校去重记录：315 行。
- THE 2026 排名年度理学领域前200内地高校：18 所。
- `table_matrix.csv` 行数：18 行。
- 最新年前200样本高校唯一性：18 所高校，无重复。
- 同济大学进入 THE 2026 排名年度理学领域前200样本；最新记录为 `176-200`，明细写入 `tongji_scope_check.csv`。
- 口径修正：THE 为领域排名，数学按 `理学/Physical Sciences` 处理，不是严格一级学科排名；早期数据中 `country_or_region='china'` 或 `country_or_region='China'` 被视为中国内地。
- 注册表已更新，统一审计通过：7 个 artifact 全部 pass。

如果要把这张表交给其他 AI 重新绘制或改样式，应至少提供：

```text
outputs/artifacts/table_08_the_mainland_peer_ranking/table_matrix.csv
outputs/artifacts/table_08_the_mainland_peer_ranking/table_data.csv
outputs/artifacts/table_08_the_mainland_peer_ranking/table_spec.json
outputs/artifacts/table_08_the_mainland_peer_ranking/latest_peer_records.csv
outputs/artifacts/table_08_the_mainland_peer_ranking/tongji_scope_check.csv
```

其中 `table_matrix.csv` 用于直接绘制表格，`table_data.csv` 用于复算历年变化，`table_spec.json` 说明 THE 的领域映射和地区修正规则，`latest_peer_records.csv` 定义最新排名年度前200样本，`tongji_scope_check.csv` 用于说明同济是否进入该对标范围。

## 第一个分项指标图闭环

已完成软科前200内地高校分项指标相对排名图：

```text
figure_09_arwu_peer_indicator_relative_rank
```

复现脚本：

```text
scripts/build_artifact_figure_09.py
```

输出目录：

```text
outputs/artifacts/figure_09_arwu_peer_indicator_relative_rank/
```

核心产物：

- `chart_data.csv`：绘图摘要，一行一个软科分项指标。
- `peer_indicator_long.csv`：21 所 peer 高校与同济参照点的逐校逐指标长表。
- `tongji_indicator_check.csv`：同济大学分项指标核验记录。
- `indicator_weight_summary.csv`：将软科权重细项汇总到当前事实表五个分项指标。
- `source_trace.csv`：指标事实和权重来源文件、sheet、行号。
- `chart_spec.json`：样本口径、相对排名规则、输出路径和校验结果。
- `chart_table.md`：图中关键数值的 Markdown 表。
- `chart.png`：当前生成的图。
- `narrative.md`：报告中可使用的文字草稿。
- `run_log.md`：本次 artifact 运行记录。

本次核验结果：

- 软科 2025 年数学前200内地高校 peer 样本：21 所。
- 同济大学软科数学最新排名为 `401-500`，不在前200 peer 样本内。
- 图中相对名次按 `21所peer + 同济外部参照` 计算，比较范围为 22 个对象。
- 分项指标数：5 个，分别为高水平研究成果、科研影响力、国际合作、世界一流成果、世界一流教师。
- peer 指标长表：105 行；同济参照指标记录：5 行。
- 软科权重细项均已匹配并汇总到五个可用指标口径。
- 注册表已更新，统一审计通过：8 个 artifact 全部 pass。

如果要把这张图交给其他 AI 重新绘制或改样式，应至少提供：

```text
outputs/artifacts/figure_09_arwu_peer_indicator_relative_rank/chart_data.csv
outputs/artifacts/figure_09_arwu_peer_indicator_relative_rank/peer_indicator_long.csv
outputs/artifacts/figure_09_arwu_peer_indicator_relative_rank/indicator_weight_summary.csv
outputs/artifacts/figure_09_arwu_peer_indicator_relative_rank/chart_spec.json
outputs/artifacts/figure_09_arwu_peer_indicator_relative_rank/tongji_indicator_check.csv
```

其中 `chart_data.csv` 说明图上画什么，`peer_indicator_long.csv` 允许复算每个相对名次，`indicator_weight_summary.csv` 说明权重口径，`chart_spec.json` 说明样本和相对排名规则，`tongji_indicator_check.csv` 用于解释同济为何是外部参照点。

## 第二个分项指标图闭环

已完成 US News 前200内地高校分项指标相对排名图：

```text
figure_11_usnews_peer_indicator_relative_rank
```

复现脚本：

```text
scripts/build_artifact_figure_11.py
```

输出目录：

```text
outputs/artifacts/figure_11_usnews_peer_indicator_relative_rank/
```

核心产物：

- `chart_data.csv`：绘图摘要，一行一个 US News 排名型分项指标。
- `peer_indicator_long.csv`：43 所 peer 高校与同济参照点的逐校逐指标长表。
- `tongji_indicator_check.csv`：同济大学分项指标核验记录。
- `indicator_weight_coverage.csv`：US News 数学权重覆盖情况。
- `source_trace.csv`：指标事实和权重覆盖来源。
- `chart_spec.json`：样本口径、相对排名规则、输出路径和校验结果。
- `chart_table.md`：图中关键数值的 Markdown 表。
- `chart.png`：当前生成的图。
- `narrative.md`：报告中可使用的文字草稿。
- `run_log.md`：本次 artifact 运行记录。

本次核验结果：

- US News 2026 排名年度数学前200内地高校 peer 样本：43 所。
- 该 peer 样本直接复用 `table_06_usnews_mainland_peer_ranking/latest_peer_records.csv`，避免不同 artifact 重新计算 peer 范围导致口径漂移。
- 同济大学 US News 数学最新排名为 `261`，不在前200 peer 样本内。
- 图中相对名次按 `43所peer + 同济外部参照` 计算，比较范围为 44 个对象。
- 分项指标数：11 个，均为 US News 排名字段，数值越小越好。
- peer 指标长表：473 行；同济参照指标记录：11 行。
- 当前 `fact_indicator_weight` 中没有 US News 数学权重行，因此本图不展示权重，也不使用替代学科权重。
- 注册表已更新，统一审计通过：9 个 artifact 全部 pass。

如果要把这张图交给其他 AI 重新绘制或改样式，应至少提供：

```text
outputs/artifacts/figure_11_usnews_peer_indicator_relative_rank/chart_data.csv
outputs/artifacts/figure_11_usnews_peer_indicator_relative_rank/peer_indicator_long.csv
outputs/artifacts/figure_11_usnews_peer_indicator_relative_rank/indicator_weight_coverage.csv
outputs/artifacts/figure_11_usnews_peer_indicator_relative_rank/chart_spec.json
outputs/artifacts/figure_11_usnews_peer_indicator_relative_rank/tongji_indicator_check.csv
```

其中 `chart_data.csv` 说明图上画什么，`peer_indicator_long.csv` 允许复算每个相对名次，`indicator_weight_coverage.csv` 说明 US News 数学权重缺失边界，`chart_spec.json` 说明样本和排名字段规则，`tongji_indicator_check.csv` 用于解释同济为何是外部参照点。

## 第三个分项指标图闭环

已完成 THE 前200内地高校分项指标相对排名图：

```text
figure_12_the_peer_indicator_relative_rank
```

复现脚本：

```text
scripts/build_artifact_figure_12.py
```

输出目录：

```text
outputs/artifacts/figure_12_the_peer_indicator_relative_rank/
```

核心产物：

- `chart_data.csv`：绘图摘要，一行一个 THE 排名型分项指标。
- `peer_indicator_long.csv`：18 所 peer 高校的逐校逐指标长表，保留指标排名和指标得分。
- `tongji_indicator_check.csv`：同济大学分项指标核验记录。
- `indicator_weight_summary.csv`：THE 自然科学一级指标权重映射。
- `source_trace.csv`：指标事实和权重来源。
- `chart_spec.json`：样本口径、相对排名规则、输出路径和校验结果。
- `chart_table.md`：图中关键数值的 Markdown 表。
- `chart.png`：当前生成的图。
- `narrative.md`：报告中可使用的文字草稿。
- `run_log.md`：本次 artifact 运行记录。

本次核验结果：

- THE 2026 排名年度理学/Physical Sciences 前200内地高校 peer 样本：18 所。
- 该 peer 样本直接复用 `table_08_the_mainland_peer_ranking/latest_peer_records.csv`，避免不同 artifact 重新计算 peer 范围导致口径漂移。
- 同济大学 THE 理学最新排名为 `176-200`，已在前200 peer 样本内。
- 分项指标数：5 个，均为 THE 排名字段，数值越小越好，同时保留分项得分。
- peer 指标长表：90 行；同济指标记录：5 行。
- 权重使用 THE `自然科学` 一级指标，5 个分项权重全部匹配。
- 注册表已更新，统一审计通过：10 个 artifact 全部 pass。

如果要把这张图交给其他 AI 重新绘制或改样式，应至少提供：

```text
outputs/artifacts/figure_12_the_peer_indicator_relative_rank/chart_data.csv
outputs/artifacts/figure_12_the_peer_indicator_relative_rank/peer_indicator_long.csv
outputs/artifacts/figure_12_the_peer_indicator_relative_rank/indicator_weight_summary.csv
outputs/artifacts/figure_12_the_peer_indicator_relative_rank/chart_spec.json
outputs/artifacts/figure_12_the_peer_indicator_relative_rank/tongji_indicator_check.csv
```

其中 `chart_data.csv` 说明图上画什么，`peer_indicator_long.csv` 允许复算每个相对名次，`indicator_weight_summary.csv` 说明 THE 自然科学权重映射，`chart_spec.json` 说明 THE 领域口径和排名字段规则，`tongji_indicator_check.csv` 用于复核同济在 peer 样本内的分项表现。

## 当前数据判断

核心数据已经具备：

- 四大国际排名明细：软科、QS、THE、US News。
- 多年度历史数据：软科、QS、US News 为多文件；THE 有 2022-2026 总库。
- 学科映射：教育部一级学科与四大榜单学科映射。
- 同济学科映射：学院、学位点、一级学科、评估结果、双一流、高峰高原、四大榜单名称。
- 指标权重：四大世界学科排名指标权重。
- 国内评估：双一流、第三/四/五轮学科评估、同济本校国内建设状态。

需要谨慎的数据：

- 第五轮评估结果文件标注“不完全”，报告中必须说明数据边界。
- 论文实力章节目前没有独立 WOS/Scopus 论文库；可以先使用排名表中的论文、引用、高被引、国际合作等代理指标，但正文必须说明口径。
- 研究前沿及学科交叉目前没有明确的教师方向或研究主题数据；不应凭空生成强结论。

## 推荐统一数据模型

后续不要让 agent 直接在 Excel 里临时猜表。建议先生成统一中间数据层：

- `dim_subject`：教育部一级学科、同济学院/学位点、四大榜单学科名称映射。
- `dim_university`：高校中文名、英文名、国家/地区、省份、城市、别名。
- `dim_indicator`：榜单指标、指标组、方向、是否得分/排名。
- `fact_ranking`：学校-学科-榜单-年度的整体排名事实。
- `fact_ranking_indicator`：学校-学科-榜单-年度-指标的分项指标事实。
- `fact_indicator_weight`：榜单-学科/领域-指标的权重。
- `fact_domestic_evaluation`：国内学科评估事实。
- `fact_domestic_status`：双一流、高峰高原等国内建设标签。

建议中间产物放到：

```text
processed/
```

原始 `data/` 目录只读，不覆盖、不重命名。

## 关键联表思路

### 目标学科定位

```text
用户输入学院或一级学科
→ 同济大学学院+学科映射关系
→ 教育部学科与四大国际学科排名映射关系
→ 得到软科/QS/US News/THE 对应榜单学科名称
```

### 国际排名历史趋势

```text
dim_subject
→ 各榜单年度排名明细
→ 筛选同济大学
→ 统一发布年度、排名年度、原始排名、排名区间中位数
→ 生成趋势表、趋势图、文字描述
```

### 对标高校分析

```text
dim_subject
→ 双一流表或第五轮评估表确定对标高校范围
→ 连接 fact_ranking
→ 计算内地高校位次分布、同济相对位置、优势/短板
```

### 分项指标分析

```text
fact_ranking_indicator
→ fact_indicator_weight
→ 对标高校范围
→ 同学科同年度内重算相对排名
→ 生成分项指标对比图
```

## 建议的下一步

结构化入库和第一个图件闭环已经跑通。下一步建议继续沿 artifact 粒度推进，而不是直接生成整份 Word：

1. 优先补齐 `logical_slot_artifact_mapping.csv` 中 data_status 为 `available` 或 `available_from_indicator_weight` 的新 artifact：`figure_02`、`figure_03`、`figure_04`、`figure_06`、`table_03`、`table_09`。
2. 对已有 artifact 做模板样式重绘：`figure_01` 改四排名卡片，`figure_07` 改多榜单历史折线，`figure_09/11/12` 改参考图的小面板分项排名样式。
3. 对 partial/data_gap 槽位先停在数据缺口说明：US News 数学权重、软科/US News 多年分项历史、论文指标数据。
4. 等完整槽位的 artifact 文件都稳定后，再设计 Word 写入器：复制模板、定位锚点、插图/插表、渲染核验。
5. 每完成一个 Word 插入动作，都保留 source trace、插入日志和渲染截图，避免后期排版问题不可复现。

## 给后续 agent 的注意事项

1. 不要覆盖 `data/` 中任何原始文件。
2. 不要让 LLM 凭感觉选择数据源，先查 `source_registry.yaml` 和 `slot_data_mapping.yaml`。
3. 每个数字结论都要保留来源文件、sheet、行号。
4. 排名区间要同时保留原始字符串和中位数，不能只留一个数。
5. 发布年度和排名年度不要混用。
6. 涉及“不完全”数据、论文代理指标、研究前沿弱数据时，报告正文要说明边界。
7. 等进入较大脚本开发或批量生成前，建议先初始化本地 Git 仓库做备份。

## 本轮正式图表与数据缺口产物

- generated_at: 2026-05-10T21:38:22
- 新增可审计 artifact：`figure_02`、`figure_03`、`figure_04`、`figure_06`、`table_03`、`table_09`。
- 已重绘正式样式图：`figure_01_tongji_subject_ranking_overview, figure_07_all_rankings_history, figure_09_arwu_peer_indicator_relative_rank, figure_11_usnews_peer_indicator_relative_rank, figure_12_the_peer_indicator_relative_rank`。
- 已输出 5 个硬性缺口：见 `configs/data_gap_report/data_gap_report.md`。
- 软科/US News 分项指标多年历史仍是 partial constraint，未计入 5 个硬性缺口，但后续生成趋势图前需要补数据或降级口径。

## Subject Agent 执行层进展

- 当前单入口：`scripts/run_subject_agent.py`
- 最新自检 run：`outputs/subject_agent_runs/20260510_222443_0701_数学`
- 当前 agent 会自动完成学科解析、readiness 判断、参数化 artifact 生成、subject-run 审计和视觉 contact sheet。
- 本轮已参数化自动生成 16 个 artifact，并通过 subject-run 审计：16 pass / 0 fail。
- 剩余 8 个槽位为数据 blocked/partial，不是执行器漏做。
- 详细交接见：`docs/subject_agent_execution_layer.md`

## 换学科 Agent 入口

现在换学科不应该再让人手动记多步脚本。新的控制入口是：

```powershell
$py='C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py scripts\run_subject_agent.py
```

换学科时只改 `scripts/run_subject_agent.py` 顶部的显式变量：

```python
TARGET_UNIVERSITY = "同济大学"
TARGET_SUBJECT = "数学"
TARGET_SUBJECT_CODE = "0701"
REPORT_YEAR = 2026
```

该 agent 会自动完成：学科解析、四大榜单别名核验、同济排名可用性、内地 peer 样本可用性、权重数据可用性、分项指标可用性、artifact readiness 判断、数据缺口报告生成。

重要边界：当前已有部分旧 artifact 脚本仍有数学硬编码，不能直接拿去跑其他学科。后续改造目标是让所有 artifact 脚本读取 `configs/runtime/current_subject_request.json`，由 `run_subject_agent.py` 统一调度。
