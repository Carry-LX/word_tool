# 数据层 v2 整理方案（2026-05-11）

## 判断

当前项目已经从数学样例推进到了可迁移 agent 雏形，但数据层还没有真正“干净”。现在的状态更准确地说是：

- 计算机科学与技术已经能生成 24 个 Word 前 artifact。
- 数学、物理、化学、土木、生物医学工程做过 smoke test，数据查询层面基本可用。
- 全局 181 个学科中，85 个是 `agent_ready`，15 个是 `partial_with_indicators`，9 个是 `partial_ranking_only`，72 个有 alias 但没有实际排名记录。
- 但 readiness 只代表“数据可查/可生成”，不代表每个学科的所有图表都达到模板级语义、视觉和证据质量。

所以用户的担心是对的：继续补图表可以短期推进，但会让映射、补源、候选口径和绘图修正越来越散。

## 现有混乱点

### 1. 规范表不完整

已有一等表：

- `processed/dim_subject.csv`
- `processed/dim_subject_alias.csv`
- `processed/dim_indicator.csv`
- `processed/dim_university_province.csv`
- `processed/fact_ranking.csv`
- `processed/fact_ranking_indicator.csv`
- `processed/fact_indicator_weight.csv`

还没有一等表：

- `dim_university.csv`
- `fact_domestic_evaluation.csv`
- `fact_domestic_status.csv`
- `fact_paper_metric.csv`
- `fact_external_indicator_history.csv`
- `artifact_data_contract.csv`

现在很多图表能跑，是因为生成器直接读了外部补源 CSV 或临时映射，而不是全部通过稳定 fact/dim 表。

### 2. 映射规则太散

当前映射散在：

- `processed/dim_subject_alias.csv`
- `configs/runtime/manual_subject_aliases.json`
- `configs/runtime/the_weight_area_crosswalk.json`
- `configs/runtime/indicator_group_crosswalk.json`
- `external_data/processed/cwts_subject_field_crosswalk.csv`
- `scripts/subject_artifact_builders.py` 中的部分逻辑分支

这会导致后续 agent 难以判断：某个映射到底是精确学科、宽领域代理、候选口径，还是临时修正。

### 3. 外部补源证据等级不统一

`external_data/processed` 里同时有：

- 软科公开页补源。
- US News 同济分项历史补源。
- CWTS 宽领域论文代理。
- US News 数学权重 candidate indirect。

这些都不应该被同等对待。后续必须有 `evidence_level`：

- `official_raw`
- `official_public_page`
- `derived_from_local_workbook`
- `external_proxy`
- `candidate_indirect`
- `manual_override`

正式 Word 中，`candidate_indirect` 和 `external_proxy` 必须触发披露或降级。

### 4. artifact 生成器职责过重

`scripts/subject_artifact_builders.py` 现在同时做：

- 数据查询
- 数据补丁
- 学科映射筛选
- 图表数据构造
- PNG 渲染
- 表格渲染
- 少量数据异常修正

这在开发期可以接受，但后面会越来越难维护。

## v2 目标结构

### A. 数据规范层

只允许 Word 前 artifact 消费这些表：

- `dim_subject`
- `dim_subject_alias`
- `dim_university`
- `dim_indicator`
- `fact_ranking`
- `fact_ranking_indicator`
- `fact_indicator_weight`
- `fact_external_indicator_history`
- `fact_paper_metric`
- `fact_domestic_evaluation`
- `fact_domestic_status`
- `mapping_registry`
- `artifact_data_contract`

### B. 映射注册层

新增统一表：

- `processed/mapping_registry.csv`

建议字段：

- `mapping_id`
- `mapping_type`
- `source_system`
- `source_value`
- `target_type`
- `target_value`
- `subject_id`
- `ranking_source`
- `confidence`
- `scope_type`
- `evidence_level`
- `requires_disclosure`
- `source_file`
- `note`

这样 THE 领域、QS 多学科、US News broad subject、CWTS field、指标归并、学校别名都能进同一个治理入口。

### C. artifact contract 层

新增：

- `processed/artifact_data_contract.csv`

每个图表明确：

- 需要哪些 fact/dim 表。
- 是否允许 proxy。
- 是否允许 candidate。
- 缺数据时是 `blocked`、`partial` 还是 `degraded_available`。
- 正文必须披露什么。

这样 agent 不会因为脚本能生成 PNG 就误以为可以放入正式 Word。

### D. 执行层

`run_subject_agent.py` 后续不再在脚本顶部改 `TARGET_SUBJECT`，而是读：

- `configs/runtime/current_subject_request.json`

用户仍然不需要命令行参数。换学科时可以由 agent 写入这个 JSON，然后运行统一入口。

## 分阶段改造

### Phase 1：先止血

目标：让后续 agent 一眼知道哪些东西是补丁、哪些东西是一等数据。

任务：

- 建立 `data_layer_maintainability_audit`。
- 建立 `mapping_registry` 初版。
- 把外部补源文件登记进 `external_source_registry`。
- 标注所有 artifact 的 `allowed_evidence_level`。

当前已完成第一项：

- `configs/data_governance/data_layer_maintainability_audit.md`
- `configs/data_governance/data_layer_maintainability_issues.csv`
- `configs/data_governance/data_layer_script_risk_inventory.csv`

### Phase 2：把补源提升为规范表

目标：生成器不再直接读零散外部 CSV。

任务：

- `external_data/processed/usnews_tongji_subject_indicator_history_2022_2026_long.csv` → `fact_external_indicator_history`
- `external_data/processed/arwu_gras_public_tongji_history_2023_2025_long.csv` → `fact_external_indicator_history`
- `external_data/processed/cwts_traditional_2025_china_latest_all_fields.csv` → `fact_paper_metric`
- `processed/dim_university_province.csv` → `dim_university`

2026-05-11 首轮进度：已完成 v2 规范表落地，见 `docs/data_layer_v2_completion_20260511.md`。新增 `dim_university`、`fact_external_indicator_history`、`fact_paper_metric`、`fact_domestic_evaluation`、`fact_domestic_status`、`mapping_registry`、`external_source_registry`、`artifact_data_contract`，并写入 `processed/ranking.sqlite`。现有绘图逻辑已通过计算机科学与技术 24/24 artifact 回归验证。

### Phase 3：拆 artifact 生成器

目标：图表生成逻辑可复用、可测试、可维护。

建议拆分：

- `scripts/agent_data_access.py`
- `scripts/artifact_dataset_builders.py`
- `scripts/artifact_renderers.py`
- `scripts/artifact_validators.py`
- `scripts/run_subject_agent.py`

### Phase 4：再进入 Word

只有当某个学科的结果满足：

- artifact 生成 24/24 或缺口被明确标记。
- artifact_data_contract 无 P0/P1。
- proxy/candidate 都被披露。
- 图表视觉 QA 通过。

才进入 Word 插入。

## 对“其他学科能不能正常生成”的回答

不能简单回答“都能”。更准确的结论是：

- 数学、物理、化学、土木、计算机等主流理工学科，大概率可以正常跑出大部分或全部 artifact。
- 医学、经济、管理等有四榜单数据的学科，也可能能跑，但需要注意 US News/QS/THE 的宽领域映射。
- 72 个只有 alias、没有排名记录的学科，不应该承诺完整生成。
- 所有使用 CWTS 的论文类图，都应视为宽领域代理，不是一级学科精确论文统计。

因此下一步不应该继续盲目换学科跑，而应先完成数据层 v2 的 Phase 1 和 Phase 2。
