# 模板对齐修正留档（2026-05-11）

## 本轮目标

根据 `data/同济大学XX学科的国际排名发展分析-2026年5月.docx` 的图表信息形态，继续修正 Word 填充前的 artifact 生成层，重点处理：

- peer 排名历史表的省份字段。
- US News/THE 权重图与模板树状/分支结构不一致的问题。
- THE 权重二级指标中异常 `100%` 对图形表达的污染。
- 本轮修改后的计算机科学与技术全量生成与审计。

## 修改内容

### 1. 学校-省份维表

新增脚本：

- `scripts/build_university_province_map.py`

该脚本从以下共性数据源抽取学校与省份映射，而不是只针对单一学科手工补值：

- `data/全国双一流学科明细表2022&2017.v2.xlsx`
- `data/全国高校第四轮&第三轮学科评估结果.xlsx`
- `data/副本第五轮评估结果（不完全）20260508(分析).xlsx`

输出：

- `processed/dim_university_province.csv`
- `processed/qa/university_province/university_province_summary.md`
- `processed/qa/university_province/university_province_conflicts.csv`

本次生成结果：

- 原始来源行数：8188
- 去重后学校数：472
- 省份冲突学校数：5

冲突主要来自多校区或同名办学主体，例如中国地质大学、中国石油大学、中国矿业大学、华北电力大学、延边大学。当前处理方式是采用来源中出现次数最多的省份，并在 QA 文件中保留冲突清单。

### 2. peer 历史表回填省份

修改：

- `scripts/subject_artifact_builders.py`

影响 artifact：

- `table_05_arwu_mainland_peer_ranking`
- `table_06_usnews_mainland_peer_ranking`
- `table_07_qs_mainland_peer_ranking`
- `table_08_the_mainland_peer_ranking`
- `table_09_peer_full_ranking_history_appendix`

生成逻辑会读取 `processed/dim_university_province.csv`，并对学校名带括号的情况做基础归一，如 `中国地质大学（武汉）` 可回退到 `中国地质大学` 查询。

### 3. US News/THE 权重图改为分支图

修改：

- `render_weight_tree`
- `build_weight_tree_data`
- `build_weight_artifact`

影响 artifact：

- `figure_05_usnews_indicator_weight`
- `figure_06_the_indicator_weight`

新增输出：

- `chart_tree_data.csv`

当前图形结构为：左侧根节点 `指标体系`，中间一级维度，右侧二级指标，线宽表示权重大小。这样比旧版环形图更接近参考 Word 中的 XMind/tree 风格。

### 4. THE 权重异常修正

在 `figure_06_the_indicator_weight/chart_tree_data.csv` 中保留：

- `weight_percent`：用于绘图的修正值。
- `weight_percent_original`：原始解析值。
- `weight_adjustment_note`：修正说明。

本轮发现 THE 计算机科学中 `授予博士学位数与授予学士学位数比` 被原始权重表解析成 `100.0`，超过所属一级指标 `教学 28.0`。生成树图时将其绘图值修正为一级指标剩余权重 `1.0`，同时保留原始值，避免静默覆盖数据问题。

## 验证结果

本轮重跑计算机科学与技术：

- run_dir: `outputs/subject_agent_runs/20260511_142142_0812_计算机科学与技术`
- attempted_count: 24
- generated_count: 24
- skipped_count: 0
- subject_artifact_audit: pass_count 24 / fail_count 0
- pre_word_audit: issue_count 0 / p1_count 0 / p2_count 0

重点人工查看：

- `figure_05_usnews_indicator_weight/chart.png`：已从环形图改为分支图，叶子标签不再互相重叠。
- `figure_06_the_indicator_weight/chart.png`：已从环形图改为分支图，异常 `100%` 不再污染图形线宽。
- `table_09_peer_full_ranking_history_appendix/table.png`：已填充省份，并保留四榜单多年份宽表结构。

## 仍需注意

- 论文类图 `figure_13-16` 当前仍使用 CWTS 宽领域代理数据，不是严格的 WOS/InCites 一级学科原始数据。
- 省份映射只覆盖当前评估/双一流数据中出现过的学校；少数国际排名中的特殊机构、分校名、医院名仍可能为空。
- 权重树图是模板信息形态对齐，后续如果要做到与参考 Word 完全一致，还可以继续按模板的 XMind 视觉样式微调节点位置、字体和线条。
