# 全局学科数据治理与可迁移性审计

## 本次目标

这次处理的目标不是继续优化数学单学科，而是从全学科 agent 的角度，把四大榜单原始学科名、教育部学科目录、同济学科映射之间的 alias 层补齐，并明确哪些数据可以直接支持换学科，哪些属于榜单本身没有对应口径或同济未上榜。

## 关键结论

- `processed/qa/subject_mapping_unmatched.csv` 已清零：当前所有原始榜单学科名都能进入 `dim_subject_alias` 映射层。
- `fact_ranking` 当前共 260235 行，排名解析异常为 0。
- `subject_id_missing_rows` 仍为 113021 行，但这不是未映射错误，而是多学科领域口径造成的预期结果，例如 THE 理学、US News engineering、QS 农业林业。
- 后续 agent 查询学科数据必须通过 `dim_subject_alias` join，不能只依赖 `fact_ranking.subject_id`。
- 181 个学科的全局 readiness：`agent_ready` 85 个，`partial_with_indicators` 15 个，`partial_ranking_only` 9 个，`has_alias_no_ranking_records` 72 个。
- 44 个同济相关学科的四大榜单解析：`ok` 122 行，`source_not_applicable` 36 行，`has_peer_records_no_tongji` 15 行，`confirmed_no_mapping` 3 行。

## 本次做了什么

1. 修复 alias 构建逻辑。
   - 原逻辑只拆少量分隔符，导致 `现代语言文学、英语语言文学、语言学` 这种已有映射无法拆出单个 alias。
   - 现在 `scripts/build_processed_core.py` 会保留原始 alias，同时拆分 `、`、`，`、`;`、`/` 等组合名，并对中文空格分隔组合做拆分。

2. 增加人工可审计 subject alias 规则层。
   - 脚本：`scripts/update_global_subject_alias_rules.py`
   - 配置：`configs/runtime/manual_subject_aliases.json`
   - 新增 `subject_alias_rules`，覆盖 QS、US News、软科的确定映射、多学科领域映射和少量近似映射。

3. 重建 processed core。
   - 脚本：`scripts/build_processed_core.py`
   - 输出：`processed/dim_subject.csv`、`processed/dim_subject_alias.csv`、`processed/fact_ranking.csv`、`processed/ranking.sqlite`
   - QA：`processed/qa/processed_core_summary.json`

4. 增加全局 readiness 审计。
   - 脚本：`scripts/audit_global_subject_data_readiness.py`
   - 输出：`processed/qa/global_subject_data_readiness.csv`
   - 报告：`processed/qa/global_subject_data_readiness.md`

5. 修正同济学科解析报告的状态语义。
   - 脚本：`scripts/build_subject_resolution_report.py`
   - `missing_alias` 不再用于表示“榜单本来没有该学科口径”；这类状态改为 `source_not_applicable`。
   - 真正需要报告说明的是 `has_peer_records_no_tongji`，即榜单有同行记录但同济未检索到记录。

## 映射规则分类

- `deterministic`：确定性映射，例如 QS 市场营销 -> 工商管理学，US News optics -> 光学工程。
- `broad_multi_subject`：榜单大领域口径，例如 US News engineering、QS 农业林业、THE 理学，不强行归入单一 subject_id。
- `approximate`：教育部目录无独立一级学科时的近似挂接，例如人类学 -> 社会学，神学/宗教研究 -> 哲学。报告生成时需要保留审慎表述。

## 复现顺序

```text
C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts/update_global_subject_alias_rules.py
C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts/build_processed_core.py
C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts/build_subject_resolution_report.py
C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts/smoke_test_subject_migration.py
C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts/audit_global_subject_data_readiness.py
```

## 重点输出文件

- `processed/qa/subject_mapping_unmatched.csv`：当前为空，表示原始榜单学科名无未映射残留。
- `processed/qa/global_subject_data_readiness.csv`：181 个学科逐项 readiness，后续换学科前先查这个文件。
- `processed/qa/global_subject_ambiguous_mapping_summary.csv`：一对多领域映射摘要，解释为什么 `subject_id_missing_rows` 仍存在。
- `processed/qa/global_subject_alias_mapping_classes.csv`：人工规则类别统计。
- `processed/qa/subject_resolution/subject_resolution_matrix.csv`：同济相关学科 x 四大榜单解析矩阵。
- `processed/qa/subject_resolution/subject_resolution_issues.csv`：同济未上榜或待确认说明清单。
- `configs/pre_word_pipeline_qa/subject_migration_smoke_test.csv`：代表学科 smoke test。

## 最终核验结果

- `scripts/build_processed_core.py`：通过，`subject_alias_no_match_rows=0`，`rank_parse_exception_rows=0`。
- `scripts/build_subject_resolution_report.py`：通过，同济相关学科-榜单组合 `ok=122`，`source_not_applicable=36`，`has_peer_records_no_tongji=15`，`confirmed_no_mapping=3`。
- `scripts/smoke_test_subject_migration.py`：通过，数学、物理学、化学、土木工程、生物医学工程 5 个代表学科均可查到多源数据。
- `scripts/audit_global_subject_data_readiness.py`：通过，181 个学科 readiness 已输出。
- `scripts/audit_pre_word_pipeline.py`：通过，当前数学 pre-word 图表产物 `issue_count=0`、`p1_count=0`、`p2_count=0`。
- 当前目录不是 git 仓库，本次未创建提交；如后续要把这些变更作为本地备份点，需要先初始化 git 或在已有仓库中提交。

## 后续 agent 使用规则

1. 输入学科后，先解析到 `subject_id`。
2. 用 `processed/qa/global_subject_data_readiness.csv` 判断该学科整体数据状态。
3. 用 `processed/qa/subject_resolution/subject_resolution_matrix.csv` 判断同济在各榜单是否有记录。
4. 查询排名事实时必须通过 `dim_subject_alias` join：
   - `fact_ranking.ranking_source = dim_subject_alias.ranking_source`
   - `fact_ranking.ranking_subject_norm = dim_subject_alias.ranking_subject_norm`
   - `dim_subject_alias.subject_id = 目标学科`
5. 遇到 `source_not_applicable` 时跳过该来源，不要报错。
6. 遇到 `has_peer_records_no_tongji` 时生成“同济未检索到记录/未上榜”的说明，不要造数。
7. 遇到 `approximate` 映射时，在分析文字里保留口径说明。
