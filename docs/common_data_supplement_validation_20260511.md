# 通用数据补充与验证记录（2026-05-11）

## 本次目标

这次不是只补某一个学科，而是补齐会影响多学科迁移的共性数据缺口，并验证这些补充已经进入 subject agent 的正式生成流程。

## 已补充内容

### 1. US News 指标权重表扩展

原问题：US News 权重工作簿里很多学科行的权重列为空，实际含义是沿用上一行同组权重。旧脚本只抽到了少数学科，导致切换学科时经常误报 US News 权重缺失。

处理方式：

- 修改 `scripts/build_indicator_weights.py`。
- `parse_usnews()` 按 US News 分组继承上一条非空权重模板。
- 对空权重但有学科名的行进行展开，形成可直接查找的学科权重记录。

验证结果：

- `processed/fact_indicator_weight.csv` 总行数：1481。
- US News 权重记录：431 行。
- US News 可覆盖学科/领域：41 个。
- 权重总和异常：0。

### 2. US News 同济学科指标历史补充

原问题：US News 同济多年份指标历史不是所有学科都能从主事实表直接取到，导致 `table_02_usnews_tongji_indicator_history` 和 `figure_10_usnews_indicator_history_trend` 对其他学科迁移不稳定。

处理方式：

- 新增 `scripts/supplement_usnews_tongji_indicator_history.py`。
- 从本地 US News 明细 Excel 抽取同济大学的学科指标历史，形成通用长表和宽表。
- 2021 文件只有总分/学科分数，不含可比的指标明细，因此不纳入本次指标历史补充。

输出文件：

- `external_data/processed/usnews_tongji_subject_indicator_history_2022_2026_long.csv`
- `external_data/processed/usnews_tongji_subject_indicator_history_2022_2026_wide.csv`
- `external_data/reports/usnews_tongji_indicator_history_supplement_summary.json`
- `external_data/reports/usnews_tongji_indicator_history_supplement_summary.md`

验证结果：

- 长表：1605 行。
- 宽表：855 行。
- 覆盖学科标签：74 个。
- 覆盖排名年：2022、2023、2025、2026。
- 本地明细源中没有独立的 2024 ranking year，因此不是脚本遗漏。

### 3. subject agent 接入方式

修改 `scripts/subject_artifact_builders.py`：

- US News 历史图表不再只限制数学学科。
- `build_external_indicator_history_table()` 和 `build_usnews_indicator_history_trend()` 会按当前目标学科筛选外部补充数据。
- 优先使用学科注册表中的显式 `usnews_subject_name`，再扩展同义英文/中文标签，避免把宽泛 alias（如 Engineering、Computer Science）混入目标学科趋势图。

修改 `scripts/run_subject_agent.py`：

- 数据可用性检查读取 US News 外部补充长表。
- 权重可用性检查支持复合学科名拆分，例如：
  - `物理学 凝聚态物理学` 可命中 `物理学` 或 `凝聚态物理学`。
  - `物理化学 化学工程 化学` 可命中 `物理化学`、`化学工程` 或 `化学`。
  - `化学，化学工程` 可命中 `化学` 或 `化学工程`。

修改 `scripts/smoke_test_subject_migration.py`：

- 同步使用复合学科候选拆分逻辑，避免 QA 脚本和正式 agent 判断口径不一致。

## 当前验证结果

### 计算机科学与技术（0812）

最新验证运行：

`outputs/subject_agent_runs/20260511_125157_0812_计算机科学与技术`

结果：

- 图表对象：24/24 生成成功。
- 阻塞或部分可用图表：0。
- `data_gap_report.csv`：无缺口。
- `audit_pre_word_pipeline.py`：issue_count=0，p1_count=0，p2_count=0。
- US News 历史表/图使用的学科标签：
  - 2023：`artificial intelligence`
  - 2025：`人工智能`
  - 2026：`人工智能`

### 多学科迁移烟测

输出：

- `configs/pre_word_pipeline_qa/subject_migration_smoke_test.csv`
- `configs/pre_word_pipeline_qa/subject_migration_smoke_test.md`

本次测试学科：

- 数学：四大排名权重均可用。
- 物理学：四大排名权重均可用。
- 化学：四大排名权重均可用。
- 土木工程：四大排名权重均可用。
- 生物医学工程：软科、THE 可用；QS 原始映射为 `无`，US News 权重源没有独立 `生物医学工程` 口径，仍保留真实缺口。

## 仍需保留的边界

1. 不能把没有源依据的学科强行映射到相近口径。比如生物医学工程是否应使用 US News 的 `工程学`、`生物学与生物化学` 或其他代理，需要明确业务规则后再写入配置。
2. US News 2024 ranking year 当前没有来自本地明细文件的指标历史，不应伪造。
3. 外部补充数据现在解决的是“本地已有明细源可抽取”的共性缺口；如果后续要求覆盖所有一级学科，还需要继续补充缺失排名源或新增明确映射规则。

## 复现命令

```powershell
& 'C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\build_indicator_weights.py
& 'C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\supplement_usnews_tongji_indicator_history.py
& 'C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\smoke_test_subject_migration.py
& 'C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\run_subject_agent.py
& 'C:\Users\李鑫\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\audit_pre_word_pipeline.py outputs\subject_agent_runs\20260511_125157_0812_计算机科学与技术
```
