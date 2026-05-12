# 数据层可维护性审计

- 生成时间：2026-05-11T14:44:45
- 目的：把当前数据层从“能跑的补丁集合”整理成后续 agent 可维护的数据产品。

## 结论

当前系统已经能支撑计算机科学与技术等学科生成 24 个 Word 前 artifact，但数据层还不能算完全产品化。核心事实表、映射配置、外部补源和绘图修补逻辑边界不够硬，短期可继续使用，长期需要做一次数据层 v2 整理。

## 全学科覆盖现状

- 全局 readiness 可用：True
- smoke test 可用：True
- smoke test 学科数：5，ok：5
- 注意：readiness 表示数据可查询，不等价于所有 Word 图表都达到模板级质量。

### readiness 分布

- agent_ready: 85
- has_alias_no_ranking_records: 72
- partial_with_indicators: 15
- partial_ranking_only: 9

## 主要问题

- P0 / execution_contract：run_subject_agent.py 仍通过脚本顶部变量切换学科。 影响：适合当前开发，不适合作为真正 agent 的稳定接口。 建议：保留显式变量风格，但改为 subject_request.json/profile 驱动，脚本只读配置，不散落状态。
- P1 / mapping：manual_subject_aliases.json 体量大，且 mapping_class 混合 deterministic、broad、approximate。 影响：查询时如果不区分映射可信度，会把宽领域口径当成精确一级学科。 建议：拆成 subject_crosswalk_registry.csv，字段包含 confidence、scope_type、requires_disclosure。
- P1 / external_data：external_data/processed 中包含候选权重、CWTS 代理、公开网页补源等不同证据等级。 影响：后续 agent 可能误把候选/代理数据写成正式结论。 建议：统一沉淀 external_source_registry 和 evidence_level，在 artifact spec 中强制披露。
- P1 / artifact_layer：subject_artifact_builders.py 已承担查询、修补、绘图、表格渲染多重职责。 影响：新图表继续叠加会越来越难维护。 建议：拆成 data_access、artifact_dataset_builders、renderers、validators 四层。
- P2 / qa：已有 audit 能检查生成是否失败，但对映射可信度、代理口径、图表模板相似度的约束还不够硬。 影响：可能出现 audit 通过但报告语义仍不够正式。 建议：新增 data_contract_audit 和 artifact_semantic_contract，每个 artifact 明确 allowed_evidence_level。
- P2 / data_model：data_layer_v2 已补齐主要一等表，但 artifact 生成器尚未完全切换到新表。 影响：短期绘图逻辑不受影响；长期仍需要逐步迁移读取路径。 建议：下一阶段把 subject_artifact_builders 的数据访问改为消费 artifact_data_contract 和 v2 fact/dim 表。
- P1 / candidate_data：仍存在 candidate_or_indirect 外部补充数据。 影响：不能无条件进入正式 Word。 建议：生成器必须把 candidate_only 标记传到最终 slot 状态。
- P1 / hardcoded_logic：多个脚本存在硬编码请求变量、数学分支或旧样例逻辑。 影响：后续接手者难判断哪些脚本能跨学科运行。 建议：在 script registry 中标注 legacy/sample/production，并逐步迁移到统一入口。

## 分层建议

1. `processed` 只放一等规范表：dim/fact 表必须有 grain、主键、source_trace、证据等级。
2. `configs/runtime` 只放运行时请求和少量稳定 crosswalk，不放大体量人工知识库。
3. `configs/mapping_registry` 应承接 subject alias、THE area、CWTS field、指标归并、学校别名等所有映射。
4. `external_data/processed` 只做原始外部补源落盘，正式生成前必须进入规范 fact 表或以 candidate/proxy 状态显式披露。
5. artifact 生成层只消费规范表和 artifact contract，不直接判断某个外部文件该不该用。

## 下一步最小改造

先不继续进 Word。下一步建议先做 `data_layer_v2`：建立 `dim_university`、`fact_external_indicator_history`、`fact_paper_metric_proxy`、`mapping_registry`，然后让 `run_subject_agent.py` 只读这些规范表。这样换学科才像 agent，而不是靠脚本补丁记忆。

## 输出文件

- `data_layer_table_inventory.csv`
- `data_layer_external_inventory.csv`
- `data_layer_runtime_config_inventory.csv`
- `data_layer_script_risk_inventory.csv`
- `data_layer_maintainability_issues.csv`
- `data_layer_maintainability_audit.json`
