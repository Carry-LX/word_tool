# Pre-Word Pipeline Quality Review

本文件记录进入 Word writer 之前，数据到图表流水线的质量复查结果。

## 本轮复查目标

本轮没有进入 Word 写入，而是反向检查：

1. 原始 Excel 到 `processed/` 的数据是否稳定。
2. 学科映射、THE 领域映射、指标组归并是否稳定。
3. subject agent 是否能从一个学科请求自动生成图表。
4. 图表数据是否和 peer scope、权重、分项指标口径一致。
5. 换学科时是否存在明显迁移断点。

## 已新增的 QA 工具

- `scripts/audit_pre_word_pipeline.py`
  - 默认审计最新一次 `outputs/subject_agent_runs/`。
  - 合并检查 processed 层、subject run 层、artifact 语义层。
  - 输出：
    - `configs/pre_word_pipeline_qa/pre_word_pipeline_qa.md`
    - `configs/pre_word_pipeline_qa/pre_word_pipeline_issues.csv`
    - `configs/pre_word_pipeline_qa/pre_word_pipeline_qa.json`

- `scripts/smoke_test_subject_migration.py`
  - 不生成图，只检查多个典型学科的数据覆盖。
  - 输出：
    - `configs/pre_word_pipeline_qa/subject_migration_smoke_test.md`
    - `configs/pre_word_pipeline_qa/subject_migration_smoke_test.csv`

## 已修复的问题

1. `figure_02` 指标共性图中，THE 的“研究质量”已归并到共性口径“科研/论文”。
   - source trace 仍保留原始指标组。
   - 图表聚合层使用 `configs/runtime/indicator_group_crosswalk.json`。

2. THE 学科领域到权重领域的映射已配置化。
   - 配置文件：`configs/runtime/the_weight_area_crosswalk.json`
   - 已补充 `工程 -> 工程学`，避免土木工程、生物医学工程等工科迁移时 THE 权重误判缺失。

3. 软科分项指标相对排名图已过滤“总得分/辅助总得分”。
   - 当前数学软科分项图保留 5 个有效分项指标。

4. subject-run 审计器现在自动生成视觉 contact sheet。
   - 不再需要手工拼图核验。

## 最新数学 run 状态

最新数学 run：

`outputs/subject_agent_runs/20260510_223602_0701_数学`

结果：

- readiness：24 个槽位级 artifact 中 16 个 ready，8 个 blocked/partial
- 自动生成：16 attempted / 16 generated / 0 skipped
- subject artifact audit：16 pass / 0 fail
- visual contact sheet：`outputs/subject_agent_runs/20260510_223602_0701_数学/audit/visual_contact_sheet.png`

Pre-Word QA：

- P1 operational defect：0
- P2 operational defect：0
- P3 migration note：1
- known blockers：3

## 当前 known blockers

这些不是执行器错误，而是数据边界：

1. US News 数学权重缺失。
   - `figure_05_usnews_indicator_weight` 必须 blocked。
   - 不能套用 US News 其他学科权重。

2. 软科同济分项指标历史只有 1 年。
   - `table_01_arwu_tongji_indicator_history` 若要多年历史，需补数据。
   - 可由用户确认后降级为最新年表。

3. US News 同济分项指标历史只有 1 年。
   - `table_02_usnews_tongji_indicator_history` 和 `figure_10_usnews_indicator_history_trend` 若要多年历史，需补数据。
   - 可由用户确认后降级为最新年表。

另外，论文类 4 张图仍是数据源缺失状态，已在 subject agent 的 `data_gap_report.csv` 中保留为 blocked/partial。

## 迁移 smoke test 结论

已抽测 5 个学科：

- 数学
- 物理学
- 化学
- 土木工程
- 生物医学工程

结论：

- 这些学科的排名和 peer scope 基本能被 subject agent 识别。
- 权重数据不是所有榜单都齐全，尤其 US News 权重覆盖有限。
- THE 权重领域通过 crosswalk 后，工科类学科不再误判 THE 权重缺失。

## 进入 Word 前的结论

对于当前已有数据能支撑的 16 个 artifact，数据到图表链路已经通过自动生成、文件审计、语义审计和视觉 contact sheet。

进入 Word writer 前仍需遵守：

1. Word writer 只读取某次 subject-run 目录下的 artifacts。
2. blocked/partial 槽位不能伪造数据。
3. US News 权重、软科/US News 多年分项历史、论文指标源，需要用户补数据或确认降级口径。
4. 换学科前先运行 `scripts/smoke_test_subject_migration.py` 或直接运行 `scripts/run_subject_agent.py` 看 readiness。

