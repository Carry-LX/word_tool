# 数据层 v2 首轮落地记录（2026-05-11）

## 本轮原则

本轮只新增规范数据层，不删除、不替换现有绘图逻辑。也就是说：

- 现有 `run_subject_agent.py` 和 `subject_artifact_builders.py` 仍能按原链路生成图表。
- 新增表先作为 v2 数据底座，后续再逐步迁移图表生成器读取路径。
- 所有 proxy、candidate、manual override 都要在表中显式标注，不再靠代码注释或记忆。

## 新增脚本

- `scripts/build_data_layer_v2.py`
- `scripts/audit_data_layer_maintainability.py` 已更新，能识别 v2 已补齐的一等表。

运行方式：

```powershell
& 'C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\build_data_layer_v2.py
& 'C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\audit_data_layer_maintainability.py
```

## 新增/补齐的一等表

输出位置均在 `processed/`，并已同步写入 `processed/ranking.sqlite`：

| 表 | 行数 | 作用 |
| --- | ---: | --- |
| `dim_university.csv` | 8639 | 汇总榜单、CWTS、省份表中的学校名称、英文名、国家地区、省份、同济标记 |
| `mapping_registry.csv` | 1337 | 统一登记 subject alias、人工规则、CWTS field、THE area、指标归并等映射 |
| `external_source_registry.csv` | 24 | 登记所有外部补源文件及证据等级 |
| `fact_external_indicator_history.csv` | 3270 | 软科公开页和 US News 本地明细抽取的同济分项历史 |
| `fact_paper_metric.csv` | 32040 | CWTS 2025 中国高校宽领域论文代理指标 |
| `fact_domestic_evaluation.csv` | 14308 | 第三、第四、第五轮国内学科评估结果 |
| `fact_domestic_status.csv` | 919 | 双一流、同济双一流、高峰高原等国内建设状态 |
| `artifact_data_contract.csv` | 24 | 24 个 Word 前 artifact 的数据依赖、允许证据等级、proxy/candidate 策略 |

QA 输出：

- `processed/qa/data_layer_v2/data_layer_v2_summary.md`
- `processed/qa/data_layer_v2/data_layer_v2_table_summary.csv`
- `processed/qa/data_layer_v2/data_layer_v2_known_limits.csv`

## 证据等级

本轮开始显式使用 `evidence_level`：

- `derived_from_local_workbook`
- `official_public_page`
- `external_proxy`
- `candidate_indirect`
- `manual_override`

重点约束：

- `fact_paper_metric` 全部是 `external_proxy`，来自 CWTS 宽领域代理，不能写成 WOS/InCites 一级学科精确统计。
- `external_source_registry` 中仍有 1 个 `candidate_indirect`，即 US News 数学权重候选数据，不能无确认进入正式 Word。
- `mapping_registry` 中 208 条映射 `requires_disclosure=yes`，主要是宽领域、代理或人工近似规则。

## 已知边界

- `fact_domestic_evaluation` 中有 515 行 `subject_id` 缺失。这些行来自国内评估学科名/代码和当前教育部目录不完全匹配，已保留为 QA 警告，不做强行匹配。
- `mapping_registry` 目前是初版统一注册表，后续应继续把学校别名、字段别名、artifact slot 映射也纳入。
- 当前 artifact 生成器还没有完全切换到 v2 表，因此数据层更干净了，但执行层还在兼容旧路径。

## 绘图逻辑验证

本轮新增 v2 表后，重跑计算机科学与技术：

- run_dir: `outputs/subject_agent_runs/20260511_144518_0812_计算机科学与技术`
- generated_count: 24
- subject_artifact_audit: 24 pass / 0 fail
- pre_word_audit: issue_count 0 / p1_count 0 / p2_count 0

说明现有画图、表格渲染、权重树、peer 历史表等逻辑没有丢失。

## 下一步

下一步不要继续零散补图。建议做：

1. 让 `run_subject_agent.py` 从 `configs/runtime/current_subject_request.json` 读取目标学科，而不是改脚本顶部变量。
2. 给 `subject_artifact_builders.py` 加一层 data access，优先读 v2 表，但保留旧路径 fallback。
3. 在 `audit_pre_word_pipeline.py` 中读取 `artifact_data_contract.csv`，检查 proxy/candidate 是否被正确标注。
