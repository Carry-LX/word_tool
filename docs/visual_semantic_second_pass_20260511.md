# 图表语义与排版二轮核查记录（2026-05-11）

## 目标

本轮针对“计算机科学与技术（0812）”生成结果做 Word 填充前复核，重点检查：

- 图表中是否残留调试提示、CSV 路径、问号占位等不应进入报告的文字。
- peer 排名表是否仍有同一高校重复出现。
- 历史排名图是否因为多学科 alias 命中而出现同一榜单同一年多个点。
- 分项指标相对排名图是否与对应 peer 表使用同一批高校和同一学科口径。
- 画布尺寸、表格宽度、标题和右侧标注是否存在明显裁切。

## 发现并修复的问题

### 1. US News peer 表与分项相对排名图口径不一致

问题：`table_06_usnews_mainland_peer_ranking` 已经按高校去重到 92 行（含同济 1 行），但 `figure_11_usnews_peer_indicator_relative_rank` 早先重新从分项指标长表里按名称匹配，导致图中 peer scope 出现 94 或混合的 6/91。

原因：计算机学科在 US News 中同时命中“人工智能、计算机科学、工程学”等入口。peer 表已经按每所学校保留了最贴近目标学科的一条记录，但分项图没有完全复用这个选择结果。

修复：

- 新增 `peer_scope_from_file`，从 peer 表读取已确定的高校身份和学科入口。
- 分项相对排名图只允许进入对应 peer 表中已选定的高校和学科入口。
- 对同一指标、同一高校再次去重，避免同一高校因多入口重复参与计算。
- 对覆盖率过低的指标进行过滤。比如 US News 计算机学科中“全球学术声誉排名、地区学术声誉排名”只有 6 个 peer 同口径数据，不再混入 91 个 peer 的相对排名图。

### 2. 历史排名图同一年多点

问题：`figure_07_all_rankings_history` 中同一榜单同一年可能出现多个点，视觉上形成竖线。

原因：同济大学在同一 source/year 下可能通过多个 subject alias 命中，例如人工智能、计算机科学、工程学。

修复：

- 新增按 `ranking_source + release_year + ranking_year + university` 的去重逻辑。
- 优先保留更贴近目标学科的 alias，其次按排名更靠前、总分更高排序。

### 3. 图表文案和画布问题

修复：

- 删除图表内“完整数据见 CSV / chart_data.csv”等调试说明。
- 去掉论文图中硬编码的“37所对标高校”，改为通用“对标高校”。
- CWTS 注释改为使用当前学科映射到的宽领域名称。
- `figure_02` 脚注去掉“数学/目标学科”这类不适合迁移学科的措辞。
- 加宽 `figure_11` 画布，避免右侧小面板被裁切。

## 最新通过结果

最新计算机学科运行目录：

`outputs/subject_agent_runs/20260511_121451_0812_计算机科学与技术`

核查结果：

- subject artifact audit：21 pass / 0 fail
- pre-word pipeline QA：issue_count=0, p1_count=0, p2_count=0
- 图像数：21
- 小尺寸异常图像：0
- 图表/CSV 调试文字残留：0
- peer 表重复高校：
  - ARWU：66 行，重复 0
  - US News：92 行，重复 0
  - QS：19 行，重复 0
  - THE：23 行，重复 0
- `figure_11_usnews_peer_indicator_relative_rank`：10 个可比指标，peer_scope_size 全部为 91。

## 仍保留的数据缺口

这些不是绘图脚本未完成，而是当前共性数据源仍不足：

- `figure_05_usnews_indicator_weight`：US News 计算机/人工智能学科官方权重缺失，不能套用数学候选权重。
- `table_02_usnews_tongji_indicator_history`：US News 同济分项指标历史目前只有单年，不能生成多年历史表。
- `figure_10_usnews_indicator_history_trend`：同上，多年趋势图缺少可比历史数据。

## 对后续 agent 的要求

换学科时仍应从 `scripts/run_subject_agent.py` 入口生成整轮 artifact，不要手工改单个 CSV 或 PNG。生成后至少运行：

```powershell
& 'C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\audit_pre_word_pipeline.py
```

如果 peer 表通过，但分项相对排名图出现不同 `peer_scope_size`，优先检查该学科是否命中多个榜单入口，以及分项指标是否复用了 peer 表的最终学科入口选择。
