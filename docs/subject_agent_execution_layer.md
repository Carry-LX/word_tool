# Subject Agent Execution Layer

本文件记录本轮把“换学科流程”从人工多步骤推进为 agent 单入口执行的改造结果。

## 当前入口

换学科时优先使用：

```powershell
$py='C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py scripts\run_subject_agent.py
```

脚本不使用命令行参数。换学科时只改 `scripts/run_subject_agent.py` 顶部显式变量：

```python
TARGET_UNIVERSITY = "同济大学"
TARGET_SUBJECT = "数学"
TARGET_SUBJECT_CODE = "0701"
REPORT_YEAR = 2026
```

## Agent 当前自动完成的事情

`scripts/run_subject_agent.py` 现在会自动完成：

1. 解析目标学科到 `subject_id`。
2. 汇总四大榜单别名映射。
3. 检查四大榜单中同济最新排名是否存在。
4. 检查各榜单前 200 内地高校 peer 样本。
5. 检查软科、QS、US News、THE 权重数据。
6. 检查分项指标数据和年份覆盖。
7. 检查论文指标源是否存在。
8. 生成 24 个槽位级 artifact readiness 判断。
9. 自动生成当前已参数化的 ready artifacts。
10. 自动审计本次 run 生成的 artifact 文件。

## 当前已参数化自动生成的 artifact

本轮已接入 subject-run 专属输出目录：

`outputs/subject_agent_runs/<run_id>/artifacts/`

当前自动生成 16 个 artifact：

- `figure_01_tongji_subject_ranking_overview`
- `figure_02_ranking_indicator_commonality`
- `figure_03_arwu_indicator_weight`
- `figure_04_qs_indicator_weight`
- `figure_06_the_indicator_weight`
- `figure_07_all_rankings_history`
- `table_04_mainland_rank_band_distribution`
- `table_05_arwu_mainland_peer_ranking`
- `table_06_usnews_mainland_peer_ranking`
- `table_07_qs_mainland_peer_ranking`
- `table_08_the_mainland_peer_ranking`
- `table_03_the_tongji_indicator_history`
- `table_09_peer_full_ranking_history_appendix`
- `figure_09_arwu_peer_indicator_relative_rank`
- `figure_11_usnews_peer_indicator_relative_rank`
- `figure_12_the_peer_indicator_relative_rank`

每个 artifact 目录包含数据、图片、spec、source trace、narrative 和 run log。

## 最新数学自检

最新一次数学 run：

`outputs/subject_agent_runs/20260510_222443_0701_数学`

结果：

- readiness：24 个槽位级 artifact 中 16 个 ready，8 个 blocked/partial
- 参数化自动生成：16 attempted / 16 generated / 0 skipped
- subject artifact audit：16 pass / 0 fail
- 视觉核验 contact sheet：`outputs/subject_agent_runs/20260510_222443_0701_数学/audit/visual_contact_sheet.png`

## 当前仍未自动生成的部分

当前 24 个槽位级 artifact 中，剩余 8 个不是执行器漏做，而是数据 blocked/partial：

- `figure_05_usnews_indicator_weight`
- `table_01_arwu_tongji_indicator_history`
- `table_02_usnews_tongji_indicator_history`
- `figure_10_usnews_indicator_history_trend`
- `figure_13_paper_output_citation_relative_rank`
- `figure_14_paper_cnci_cpp_relative_rank`
- `figure_15_paper_highly_cited_relative_rank`
- `figure_16_paper_international_collab_relative_rank`

## 当前数据阻塞项

数学学科下仍有 8 个 blocked/partial：

- US News 数学权重缺失
- 软科同济分项指标历史只有单年
- US News 同济分项指标历史只有单年
- US News 分项指标历史趋势图缺多年数据
- 论文及被引总量缺独立论文指标源
- CNCI/篇均被引缺独立论文指标源
- 高被引 TOP 论文缺独立论文指标源
- 国际合著论文占比缺独立论文指标源

这些不能由排名表臆造。

## 下一步

下一步应进入 Word writer：

1. Word writer 读取某次 `outputs/subject_agent_runs/<run_id>/artifacts/`。
2. 按 `configs/template_slot_inventory/logical_slot_artifact_mapping.csv` 定位槽位。
3. 对 ready artifact 插图/插表。
4. 对 blocked/partial artifact 写入待补数据说明或保留模板占位。
5. 渲染 Word/PDF 做视觉核验。
