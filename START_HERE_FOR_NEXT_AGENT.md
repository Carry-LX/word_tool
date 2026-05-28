# 接手入口：表格数据分析 Agent

## 2026-05-28 Word 自动生成链路交接

本轮工作重点已经从“Word 前图表产物”推进到“按学科生成完整 Word 报告”，并围绕 `1401 集成电路科学与工程` 做了多轮问题收敛。后续接手时请先按本节理解当前状态。

### 最新可核查样例

- 最新学科运行目录：`outputs/subject_agent_runs/20260528_155621_1401_集成电路科学与工程`
- 最新 Word 输出：`outputs/full_word_reports/20260528_155621_1401_集成电路科学与工程/同济大学集成电路科学与工程_学科国际排名发展分析.docx`
- 最新 Word QA：`outputs/full_word_reports/20260528_155621_1401_集成电路科学与工程/qa/word_qa_report.json`
- 最新系统体检：`outputs/agent_system_audit/latest/agent_system_readiness.json`

最新 1401 渲染结果：`render_status=ok`，15 页，无空白页、无 sparse page。剩余 `wide_tables_need_visual_review` 是宽表人工视觉复核提示，不是页面变宽、图文错位或数据缺失错误。

### 本轮已修正的关键问题

- 排名口径统一：严格使用当前学科在预处理映射表和运行期决策里选定的榜单口径；没有同济最新综合排名的来源不再进入主图或强行补齐。
- QS/软科无直接口径时不再用近邻口径替代：以 1401 为例，QS 不再混用“数据科学与人工智能”和“电子与电气工程”；软科外部候选口径 `Electrical & Electronic Engineering` 不再进入正文的软科分项历史表。
- 图文对应关系修正：无可核验图表的来源小节会从对标高校整体分析、分指标分析、排名历史分析中移除，避免“只有标题/图题没有图”或图跑到下一节。
- 图表位置修正：U.S.News、THE 分指标图会重新锚定到对应图题前，避免插入到论文章节或错误小节。
- 论文数据来源修正：论文章只使用 37 校 Web of Science 一级学科论文数据。若该一级学科没有记录，只写缺失说明，不使用学校整体论文数据或宽口径代理数据。
- 排名显示清洗：正文和表格中的 `#9`、`=30` 等来源标记会清洗为普通数字。
- `U.S.News` 显示修正：Word 正文中将 `U.S.News` 拆成单独西文字体 run，避免中文排版把它显示成 `U. S. News`。
- 页面版式修正：生成后统一 section 页面几何，所有 section 恢复竖向 A4 和一致页边距，避免目录和正文继承横向宽版面。

### 当前主要脚本入口

- 批量或单学科 Word 生成入口：`scripts/run_batch_reports.py`
- 学科事实、口径、artifact readiness 决策：`scripts/run_subject_agent.py`
- 图表/表格产物构建：`scripts/subject_artifact_builders.py`
- Word 模板替换、后处理、页面几何修正：`scripts/build_word_replacement_trial.py`
- 系统体检：`scripts/audit_agent_system_readiness.py`

当前单学科验证命令示例：

```powershell
E:\conda_envs\graph-rag\python.exe -c "import sys; from pathlib import Path; sys.path.insert(0, str(Path('scripts').resolve())); import run_batch_reports as r; r.ONLY_CODES=['1401']; r.UPDATE_WORD_FIELDS_WITH_COM=False; r.NORMALIZE_DOCX_FOR_WORD_OPEN=False; r.main()"
E:\conda_envs\graph-rag\python.exe scripts/audit_agent_system_readiness.py
```

### 接手时优先检查

1. 先看 `outputs/subject_agent_runs/20260528_155621_1401_集成电路科学与工程/artifact_readiness.csv`，确认哪些 artifact 是 ready，哪些是 disclosed missing。
2. 再看 `outputs/subject_agent_runs/20260528_155621_1401_集成电路科学与工程/source_decision_matrix.csv`，确认各榜单是否有同济最新综合位次。
3. 对 Word 版式问题，优先检查 `scripts/build_word_replacement_trial.py` 中的这些后处理函数：
   - `normalize_evidence_backed_source_sections`
   - `repair_peer_indicator_figure_anchors`
   - `normalize_missing_paper_section`
   - `normalize_section_page_geometry`
4. 若继续做全学科批量生成，不要直接一次全量生成交付；先抽样跑若干典型学科，检查 `word_qa_report.json`、渲染页 PNG、`agent_system_readiness.json`。

### 仍需注意的边界

- `soft/QS/THE/US News` 的“学科口径”必须以运行期决策和预处理映射结果为准，不能在不同章节各自找近邻口径。
- 外部补源只能在同济有可核验综合排名或人工确认的情况下进入正文；否则只能作为候选或缺口说明。
- 37 校 WoS 论文数据按教育部一级学科代码匹配。没有匹配记录时必须说明缺失，不要回退到学校整体论文数据。
- 当前 Git 分支为 `codex/agent-overall-optimization`。本项目 Git 主要用于本地备份，不要主动 push。

## 2026-05-11 共性补源更新

本项目已经新增两类可迁移补源，不再只围绕数学样例：

- 软科 GRAS 2023-2025 公开网页数据：见 `scripts/acquire_arwu_gras_public_pages.py` 和 `external_data/processed/arwu_gras_public_*`。
- CWTS Leiden 2025 五大宽领域论文指标代理：见 `scripts/process_external_cwts_sources.py`、`external_data/processed/cwts_subject_field_crosswalk.csv` 和 `external_data/processed/cwts_traditional_2025_china_latest_all_fields.csv`。

土木工程已重新验证：`outputs/subject_agent_runs/20260511_102908_0814_土木工程` 生成 21 个 artifact，21 pass / 0 fail。软科历史表和论文类 `figure_13` 至 `figure_16` 已由共性补源生成；剩余共性缺口主要是 US News 权重和 US News 多年分项指标。完整记录见 `docs/common_data_gap_supplement_run_20260511.md`。

这份文档给后续接手的 AI 或开发者使用。先读这里，再进入具体脚本和报告。

## 当前项目目标

项目目标是：根据 `data/` 中的四大国际排名、指标权重、分项指标、同济学科映射等 Excel 数据，自动为某个同济学科生成 Word 报告前所需的所有图表、表格和分析素材。

当前阶段还没有进入最终 Word 自动填充，而是已经完成了 Word 前的数据层和图表产物层建设。

## 当前最重要的结论

- 原始榜单学科名的未映射问题已经处理完：`processed/qa/subject_mapping_unmatched.csv` 为空。
- 数学样例的 Word 前图表产物 QA 已通过：`audit_pre_word_pipeline.py` 结果为 `issue_count=0`、`p1_count=0`、`p2_count=0`。
- 全局 181 个学科已经做 readiness 审计：
  - `agent_ready`：85 个
  - `partial_with_indicators`：15 个
  - `partial_ranking_only`：9 个
  - `has_alias_no_ranking_records`：72 个
- 后续换学科时，不需要重新清洗所有原始 Excel；先查 readiness，再决定哪些图表可以生成、哪些图表要降级说明。

## 另一个 AI 接手时先读哪些文件

建议按这个顺序读：

1. `START_HERE_FOR_NEXT_AGENT.md`
2. `docs/global_subject_data_readiness_20260511.md`
3. `processed/qa/global_subject_data_readiness.csv`
4. `processed/qa/subject_resolution/subject_resolution_matrix.csv`
5. `docs/pre_word_artifact_generation_completion.md`
6. `docs/two_subject_migration_trial_20260511.md`
7. `outputs/subject_agent_runs/20260510_234250_0701_数学/manifest.json`
8. `outputs/subject_agent_runs/20260510_234250_0701_数学/audit/visual_contact_sheet.png`

## 目录和文件是什么意思

### `data/`

原始数据和 Word 模板目录。不要覆盖或改写这里的原始文件。

关键文件：
- `【标黄】同济大学学科分析报告——理科（2026年）.docx`：目标 Word 模板骨架。
- `同济大学XX学科的国际排名发展分析-2026年5月.docx`：图表和表格样式参考报告。
- 各类排名 Excel：软科、QS、US News、THE 等原始表格。

### `processed/`

结构化后的核心数据层。后续 agent 应主要读这里，而不是直接读原始 Excel。

关键文件：
- `dim_subject.csv`：教育部一级学科、同济学科、榜单学科口径的主维表。
- `dim_subject_alias.csv`：榜单原始学科名到 `subject_id` 的 alias 映射表。
- `fact_ranking.csv`：四大榜单排名事实表。
- `fact_indicator_weight.csv`：四大榜单指标权重表。
- `fact_ranking_indicator.csv`：四大榜单分项指标长表。
- `ranking.sqlite`：同样数据的 SQLite 版本，便于 join 查询。

### `processed/qa/`

数据层 QA 和接手报告。

关键文件：
- `processed_core_summary.json`：核心数据层构建摘要。
- `subject_mapping_unmatched.csv`：未映射原始榜单学科名。当前应为空。
- `global_subject_data_readiness.csv`：181 个学科的换学科可用性审计。
- `global_subject_ambiguous_mapping_summary.csv`：一对多领域映射摘要。
- `global_subject_alias_mapping_classes.csv`：人工 alias 规则类别统计。

### `processed/qa/subject_resolution/`

同济相关学科 x 四大榜单的解析结果。

关键文件：
- `subject_resolution_matrix.csv`：每个同济学科在每个榜单中的状态。
- `subject_resolution_issues.csv`：真正需要报告中说明的“同行有记录但同济未上榜/未检索到”项。
- `subject_latest_tongji_rankings.csv`：同济各学科最新可查排名记录。

### `configs/runtime/`

运行时配置和规则。

关键文件：
- `manual_subject_aliases.json`：人工 alias 配置。现在包含 `subject_alias_rules`，用于补充 QS、US News、软科等原始学科名。
- `current_subject_request.json`：当前学科请求配置。
- `subject_request_schema.yaml`：后续 agent 输入格式。
- `query_contract.md`：查询约定，尤其强调必须通过 `dim_subject_alias` join。

### `configs/template_slot_inventory/`

Word 参考报告中的图、表、图题、表题槽位盘点。

关键文件：
- `logical_slot_artifact_mapping.csv`：Word 逻辑槽位到 artifact 的映射。
- `full_slot_artifact_mapping.md`：槽位覆盖说明。

### `configs/pre_word_pipeline_qa/`

Word 前图表产物 QA。

关键文件：
- `pre_word_pipeline_qa.json`：当前数学样例图表产物质量审计。
- `pre_word_pipeline_issues.csv`：当前应为空或无 P1/P2。
- `subject_migration_smoke_test.csv`：代表学科换学科 smoke test。

### `outputs/subject_agent_runs/`

每次学科 agent 运行的正式输出。

当前最完整样例：
- `outputs/subject_agent_runs/20260510_234250_0701_数学/`

里面通常包含：
- `manifest.json`：本次生成了哪些图表/表格。
- `run_summary.md`：本次运行摘要。
- `artifacts/`：图表、表格、原始数据和说明文本。
- `audit/visual_contact_sheet.png`：图表总览图，方便快速看样式是否正常。

## 核心流程是怎么形成的

```text
原始 Excel / Word 模板
  ↓
阶段 1：原始资产盘点
  scripts/build_stage1_inventory.py
  ↓
阶段 2：数据治理与数据模型设计
  scripts/build_data_governance.py
  ↓
阶段 3：核心数据层构建
  scripts/update_global_subject_alias_rules.py
  scripts/build_processed_core.py
  ↓
阶段 4：指标权重与分项指标结构化
  scripts/build_indicator_weights.py
  scripts/build_ranking_indicators.py
  ↓
阶段 5：外部补充数据处理
  scripts/acquire_external_public_sources.py
  scripts/process_external_cwts_sources.py
  scripts/build_indicator_history_supplements.py
  ↓
阶段 6：Word 槽位和 artifact recipe 对齐
  scripts/build_template_slot_inventory.py
  scripts/build_full_slot_artifact_mapping.py
  ↓
阶段 7：运行某个学科 agent
  scripts/run_subject_agent.py
  ↓
阶段 8：Word 前图表产物 QA
  scripts/audit_subject_agent_run.py
  scripts/audit_pre_word_pipeline.py
```

## 换学科应该怎么做

1. 先查 `processed/qa/global_subject_data_readiness.csv`。
   - `agent_ready`：大概率顺利。
   - `partial_with_indicators`：可生成部分图表。
   - `partial_ranking_only`：只能生成基础排名相关图表。
   - `has_alias_no_ranking_records`：榜单本身缺记录，不适合完整生成。

2. 再查 `processed/qa/subject_resolution/subject_resolution_matrix.csv`。
   - `ok`：该榜单可以用于同济分析。
   - `source_not_applicable`：该榜单没有对应口径，跳过。
   - `has_peer_records_no_tongji`：同行有数据但同济没有记录，报告里说明未上榜/未检索到。
   - `confirmed_no_mapping`：确认无映射，不要强行生成。

3. 修改 `scripts/run_subject_agent.py` 顶部显式变量：

```python
TARGET_UNIVERSITY = "同济大学"
TARGET_SUBJECT = "数学"
TARGET_SUBJECT_CODE = "0701"
REPORT_YEAR = 2026
```

4. 运行：

```text
C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts/run_subject_agent.py
C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts/audit_subject_agent_run.py
C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts/audit_pre_word_pipeline.py
```

## 查询数据时的硬规则

不要只按 `fact_ranking.subject_id` 查数据。很多榜单是领域口径，一条原始榜单记录会通过 alias 对应多个学科。

正确方式是通过 `dim_subject_alias` join：

```text
fact_ranking.ranking_source = dim_subject_alias.ranking_source
fact_ranking.ranking_subject_norm = dim_subject_alias.ranking_subject_norm
dim_subject_alias.subject_id = 目标学科
```

## 容易误解的点

- `subject_id_missing_rows` 不等于数据错误。它主要表示原始记录属于多学科领域口径，不能唯一落到一个 subject_id。
- `source_not_applicable` 不等于失败。它表示该榜单没有这个一级学科口径，报告里跳过即可。
- `has_peer_records_no_tongji` 是业务事实：其他学校有记录，但同济没有，需要在报告里说明未上榜/未检索到。
- `approximate` alias 需要审慎表述，例如人类学暂挂社会学，神学/宗教研究暂挂哲学。
- 原始 `data/` 不要改，所有处理产物都在 `processed/`、`configs/`、`outputs/`、`docs/`。

## 当前可认为稳定的核验结果

- `processed/qa/subject_mapping_unmatched.csv`：0 行。
- `processed/qa/processed_core_summary.json`：`subject_alias_no_match_rows=0`。
- `processed/qa/global_subject_data_readiness.csv`：181 个学科已审计。
- `processed/qa/subject_resolution/subject_resolution_summary.json`：同济相关学科问题行已从语义上收敛到 15 个 `has_peer_records_no_tongji`。
- `configs/pre_word_pipeline_qa/pre_word_pipeline_qa.json`：数学样例 Word 前产物 P1/P2 问题为 0。
- `docs/two_subject_migration_trial_20260511.md`：计算机科学与技术、土木工程迁移试跑记录；已确认数学专用外部补充源不会再套用到其他学科。

## 版本备份状态

当前目录不是 git 仓库。本轮没有创建提交。若后续需要用 git 做本地备份，请先初始化仓库或在用户确认后提交当前稳定状态。
