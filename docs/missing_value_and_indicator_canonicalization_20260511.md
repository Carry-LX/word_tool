# 缺失值语义化与指标口径归并记录（2026-05-11）

## 背景

计算机科学与技术报告生成后，部分图表中可见空白单元格。核查后确认，底层数据并非整体缺失，而是宽表展示时把多年份、多榜单、多指标口径拼在一起，导致以下情况都显示为空：

- 榜单在该年份没有发布对应学科数据。
- 学校在该年份没有进入对应榜单。
- 不同年份指标名称发生变化。
- 原始公开页中存在空 indicator 行。

## 本次修改

修改文件：

- `scripts/subject_artifact_builders.py`

### 1. 历史排名附表缺失值语义化

影响 artifact：

- `table_09_peer_full_ranking_history_appendix`

处理规则：

- 如果某榜单在该年份没有任何对应学科记录，填充为 `未发布`。
- 如果某榜单该年份存在发布记录，但该学校没有对应排名，填充为 `未上榜`。
- 不再保留空白单元格。

### 2. 软科指标口径归并

影响 artifact：

- `table_01_arwu_tongji_indicator_history`

归并规则：

- `Q1`、`High Quality Research` -> `高质量研究`
- `CNCI`、`Research Impact` -> `研究影响`
- `IC`、`International Collaboration` -> `国际合作`
- `TOP`、`World-Class Output` -> `世界一流产出`
- `AWARD`、`World-Class Faculty` -> `世界一流师资`

这样可以避免 2023 年旧指标和 2024/2025 年新指标各自成行，造成大量“缺测”。

### 3. THE 指标口径归并

影响 artifact：

- `table_03_the_tongji_indicator_history`

归并规则：

- `篇均被引` -> `科研质量`
- `篇均被引排名` -> `科研质量排名`

这样可以兼容 THE 指标体系从早期引用类口径向后续科研质量口径的变化。

### 4. 空 indicator 行过滤

软科公开页中部分 indicator 行为空，已在生成表格前过滤，避免出现空指标行。

## 验证结果

最新运行：

`outputs/subject_agent_runs/20260511_134517_0812_计算机科学与技术`

结果：

- 24/24 个 artifact 生成成功。
- `audit_pre_word_pipeline.py`：`issue_count=0`，`p1_count=0`，`p2_count=0`。
- `table_01_arwu_tongji_indicator_history/table_matrix.csv`：年份列空白数为 0。
- `table_03_the_tongji_indicator_history/table_matrix.csv`：年份列空白数为 0。
- `table_09_peer_full_ranking_history_appendix/table_matrix.csv`：年份列空白数为 0。

## 注意

这里没有伪造排名或指标值。`未发布`、`未上榜`、`缺测` 都是展示层标签，用于替代原来的空白单元格，底层 `source_trace.csv` 仍保留原始来源与原始取数记录。
