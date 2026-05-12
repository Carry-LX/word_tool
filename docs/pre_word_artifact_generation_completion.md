# Pre-Word Artifact Generation Completion

- generated_at: 2026-05-10T23:46:30
- latest_run: `E:\projects\water\word_tool\outputs\subject_agent_runs\20260510_234250_0701_数学`
- target_university: 同济大学
- target_subject: 数学
- target_subject_code: 0701
- stage: Word 写入前的数据、图、表生产层

## Current Status

本轮已经完成 Word 写入前的完整图表生产闭环：

- artifact attempted: 24
- artifact generated: 24
- artifact skipped: 0
- subject artifact audit: 24 pass / 0 fail
- pre-word QA: P1=0, P2=0, P3=1
- known_blocker_count: 0

P3 仅为全局学科映射提醒：仍有 82 个榜单原始学科名未映射，不阻塞当前数学报告。换学科时需要由 subject agent 先检查目标学科是否落入未映射集合。

## Important Caveat

`figure_05_usnews_indicator_weight` 已生成，但它是 `candidate_only`。

原因：当前仍未获得 US News 2026 数学官方权重专表；生成器使用的是 `external_data/processed/usnews_math_weight_candidate_indirect.csv`，该表基于“数学属于 soft sciences”的公开旁证与本地 soft sciences 权重结构。进入 Word 前必须决定是否接受这个候选口径。如果不接受，Word 中对应位置应保留缺口说明或删除该候选图。

## How To Reproduce

无需命令行传参。换学科时修改 `scripts/run_subject_agent.py` 顶部变量：

```python
TARGET_UNIVERSITY = "同济大学"
TARGET_SUBJECT = "数学"
TARGET_SUBJECT_CODE = "0701"
REPORT_YEAR = 2026
```

然后运行：

```powershell
& 'C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' 'E:\projects\water\word_tool\scripts\run_subject_agent.py'
& 'C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' 'E:\projects\water\word_tool\scripts\audit_pre_word_pipeline.py'
```

## Generated Artifact Coverage

| type | count | artifacts |
| --- | ---: | --- |
| figures | 16 | `figure_01`, `figure_02`, `figure_03`, `figure_04`, `figure_05`, `figure_06`, `figure_07`, `figure_09`, `figure_10`, `figure_11`, `figure_12`, `figure_13`, `figure_14`, `figure_15`, `figure_16` plus chart outputs under each directory |
| tables | 8 | `table_01`, `table_02`, `table_03`, `table_04`, `table_05`, `table_06`, `table_07`, `table_08`, `table_09` |

Note: The Word reference counted 14 embedded image objects and 8 table objects, but logical artifact mapping contains extra chart/caption needs such as `figure_10`; this run produces all 24 logical artifacts used by the pre-Word layer.

## Key Output Files

- Generation summary: `outputs/subject_agent_runs/20260510_234250_0701_数学/artifacts/artifact_generation_summary.json`
- Artifact audit: `outputs/subject_agent_runs/20260510_234250_0701_数学/audit/subject_artifact_audit.md`
- Visual contact sheet: `outputs/subject_agent_runs/20260510_234250_0701_数学/audit/visual_contact_sheet.png`
- Pre-Word QA: `configs/pre_word_pipeline_qa/pre_word_pipeline_qa.md`
- Data supplement report: `external_data/reports/external_gap_resolution_report.md`

## Data Source Rules For Word Stage

1. Every artifact directory contains primary data, source trace, spec, narrative, run log, and preview image/table.
2. Word writer should only consume artifact directories from the latest run unless the user pins another run.
3. For paper-strength figures, cite `CWTS Leiden Ranking Traditional Edition 2025` and state `Mathematics and computer science` wide-field口径.
4. Do not describe CWTS `MNCS` as InCites `CNCI`; it is a public replacement/proxy metric.
5. Do not silently turn `figure_05_usnews_indicator_weight` into a formal official US News weight chart; it is candidate-only.

## Next Step

The next engineering step is Word writing:

1. Copy the target template.
2. Match logical slots to template anchors/captions.
3. Insert `chart.png` or `table.png`/Word-native table from each artifact directory.
4. Fill narrative paragraphs from artifact `narrative.md` plus generated data summaries.
5. Render the completed DOCX to images/PDF and visually verify page layout.

