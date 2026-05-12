# 计算机科学与技术、土木工程迁移试跑记录

## 试跑目的

验证当前学科 agent 是否能脱离数学样例，迁移到其他同济学科，并暴露数据层、外部补充源、图表生成和 QA 规则中的问题。

## 本次试跑学科

| 学科代码 | 学科名称 | run_dir |
| --- | --- | --- |
| 0812 | 计算机科学与技术 | `outputs/subject_agent_runs/20260511_093228_0812_subject` |
| 0814 | 土木工程 | `outputs/subject_agent_runs/20260511_093314_0814_subject` |

汇总文件：

```text
configs/pre_word_pipeline_qa/two_subject_trial_summary.json
```

## 发现并修复的问题

1. 数学专用外部补充源被错误套用到其他学科。
   - 现象：计算机和土木的 `table_01_arwu_tongji_indicator_history`、`table_02_usnews_tongji_indicator_history` 曾生成出数学分项历史数据。
   - 修复：`scripts/run_subject_agent.py` 和 `scripts/subject_artifact_builders.py` 增加学科适用范围判断。
   - 当前规则：数学专用 ARWU/US News 历史补充与 US News 候选权重只允许 `0701` 使用。

2. CWTS Mathematics and computer science 代理数据被错误用于土木工程。
   - 修复：CWTS 数学/计算机代理仅允许 `0701`、`0811`、`0812`、`0835`、`1405` 使用。
   - 土木工程现在会正确跳过论文类 4 个图，而不是借用数学/计算机口径。

3. pre-word QA 中残留数学固定 peer 数量检查。
   - 现象：非数学学科被错误要求 QS=16、US News=43 等数学样例数量。
   - 修复：数学固定同行数量检查只在 `0701` 时启用。

4. peer indicator 审计按原始行数比较，误判一对多 alias 记录。
   - 现象：US News/软科同一高校可能因多 alias 出现多行，审计把 raw rows 当作 peer scope。
   - 修复：审计改为按唯一高校数，并根据同济是否在 peer scope 中推导 expected peer scope。

## 最终试跑结果

| 学科 | ready/artifacts | generated | skipped | artifact audit | pre-word P1/P2/P3 |
| --- | ---: | ---: | ---: | --- | --- |
| 计算机科学与技术 | 20/24 | 20 | 4 | 20 pass / 0 fail | 0 / 0 / 0 |
| 土木工程 | 16/24 | 16 | 8 | 16 pass / 0 fail | 0 / 0 / 0 |

## 计算机科学与技术结果解释

计算机科学与技术四大排名、权重、同行排名、THE 多年分项、peer 指标图、论文代理图都可以生成。

跳过/阻塞项：

- `figure_05_usnews_indicator_weight`：缺 US News 人工智能官方权重，数学候选权重不再套用。
- `table_01_arwu_tongji_indicator_history`：软科同济分项指标只有最新年，缺多年历史。
- `table_02_usnews_tongji_indicator_history`：US News 同济分项指标只有最新年，缺多年历史。
- `figure_10_usnews_indicator_history_trend`：US News 趋势图需要多年分项指标。

## 土木工程结果解释

土木工程四大排名、权重、同行排名、THE 多年分项、peer 指标图都可以生成。

跳过/阻塞项：

- `figure_05_usnews_indicator_weight`：缺 US News 土木工程官方权重。
- `table_01_arwu_tongji_indicator_history`：软科同济分项指标只有最新年，缺多年历史。
- `table_02_usnews_tongji_indicator_history`：US News 同济分项指标只有最新年，缺多年历史。
- `figure_10_usnews_indicator_history_trend`：US News 趋势图需要多年分项指标。
- `figure_13` 至 `figure_16`：土木工程缺独立论文指标源，不能使用 CWTS 数学/计算机代理数据。

## 当前判断

这次试跑说明 agent 的主体迁移链路是可行的，但完整度会按学科变化：

- 计算机科学与技术属于高可用迁移学科，能生成 20/24 个 artifact。
- 土木工程也能生成主体排名和指标分析，但论文类图表缺真实独立数据源，因此生成 16/24 个 artifact。
- 关键原则已经修正：不能为了“全图表生成”而把数学补充数据套用到其他学科。
