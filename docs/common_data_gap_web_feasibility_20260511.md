# 共性数据缺口与网络补源可行性判断

> 2026-05-11 后续执行结果：本判断中的 P1 软科 GRAS 公开页采集和 P2 CWTS 五大宽领域代理已经完成首轮工程化接入。运行记录见 `docs/common_data_gap_supplement_run_20260511.md`。

## 背景

计算机科学与技术、土木工程试跑后，剩余缺口已经从“脚本没写完”收敛为几类共性数据源问题。这里判断这些缺口能否通过网络公开数据补齐，以及补齐后应如何接入 agent。

## 共性缺口分类

| 缺口 | 影响 artifact | 当前状态 | 网络补源可行性 |
| --- | --- | --- | --- |
| US News 学科权重 | `figure_05_usnews_indicator_weight` | 计算机、土木等缺官方目标学科权重 | 低到中。官方页面可说明总体方法，但具体学科权重公开获取不稳定，不应自动套用数学候选权重 |
| 软科同济多年分项指标历史 | `table_01_arwu_tongji_indicator_history` | 当前多数非数学学科只有本地最新年 | 中到高。软科历年网页公开展示总分和五大指标模块，可按学科和年份抓取 |
| US News 同济多年分项指标历史 | `table_02_usnews_tongji_indicator_history`、`figure_10_usnews_indicator_history_trend` | 当前多数非数学学科只有最新年 | 低。US News 官方站点抓取受限，历史分项指标公开稳定性弱 |
| 论文/被引/CNCI/高被引/国际合作 | `figure_13` 至 `figure_16` | 数学/计算机可用 CWTS 代理；土木不应套用数学/计算机 | 中。CWTS 可覆盖五大宽领域，可扩展到 Physical sciences and engineering 等宽领域，但不是教育部一级学科粒度 |

## 已核验的公开来源

1. 软科 GRAS 方法页说明 2025 年覆盖 57 个学科，候选大学基于 2020-2024 发表门槛，数据来自 Web of Science 和 InCites，并公开五类指标与权重表入口。
   - 来源：https://www.shanghairanking.com/methodology/gras/2025

2. 软科 2024 土木工程页面公开展示学校排名、总分及五大指标模块列。该页可作为恢复 2024 软科分项历史的网络来源。
   - 来源：https://www.shanghairanking.cn/rankings/gras/2024/RS0211

3. 软科 2024 计算机科学与工程页面同样公开展示历年入口、学校排名及指标模块列。
   - 来源：https://www.shanghairanking.cn/rankings/gras/2024/AS0210

4. 软科公开了 GRAS 与 Web of Science Category 的映射 PDF，可用于把学科归到 WoS 类别，辅助论文指标口径说明。
   - 来源：https://www.shanghairanking.cn/_pub/cn/gras/2024/%E8%BD%AF%E7%A7%91%E6%8E%92%E5%90%8D%E5%AD%A6%E7%A7%91%E4%B8%8EWeb%20of%20Science%20Category%E5%AF%B9%E5%BA%94%E5%85%B3%E7%B3%BB.pdf

5. CWTS Leiden Ranking Traditional 2025 明确提供五大主领域：Biomedical and health sciences、Life and earth sciences、Mathematics and computer science、Physical sciences and engineering、Social sciences and humanities，并说明基于 Web of Science。
   - 来源：https://traditional.leidenranking.com/information/fields

6. THE 学科排名方法页公开 11 个 subject areas 和指标权重表，THE 权重本项目已经有较完整结构化，不是当前主要缺口。
   - 来源：https://www.timeshighereducation.com/world-university-rankings/world-university-rankings-subject-2025-methodology

7. U.S. News 2025-2026 发布稿说明 Best Global Universities 覆盖 51 个 subject rankings，数据由 Web of Science Core Collection 与 InCites 提供，方法强调研究声誉与文献计量指标。但当前没有稳定公开的“各学科权重表 + 历年同济分项指标”批量入口。
   - 来源：https://www.prnewswire.com/news-releases/us-news-releases-2025-2026-best-global-universities-rankings-302482820.html

## 建议补源优先级

### P1：软科历年分项指标批量补齐

可做。建议先针对同济 `agent_ready` 学科批量抓取软科 2023、2024、2025 的同济行，恢复：

- 总分
- 世界一流教师
- 世界一流成果
- 高水平研究成果
- 科研影响力
- 国际合作

这样可以补齐 `table_01_arwu_tongji_indicator_history` 的共性缺口。

注意：软科页面的列名在浏览器文本中可能只有部分列显式出现，实际脚本需要解析页面嵌入数据或表格结构，不能只靠纯文本。

### P2：CWTS 五大宽领域扩展

可做，但要标注口径。当前已经下载 CWTS Traditional/Open 2025 原始文件，本地不是缺下载，而是只处理了数学/计算机宽领域。下一步可扩展：

- 土木、材料、机械、化工等：Physical sciences and engineering
- 医学类：Biomedical and health sciences
- 生命/生态/农学类：Life and earth sciences
- 社科/人文：Social sciences and humanities

这能让 `figure_13` 至 `figure_16` 对更多学科可用，但它仍是 CWTS 宽领域代理，不是严格一级学科。

### P3：US News 历史分项指标

谨慎。官方网页访问和历史分项稳定性都比较差。可以尝试：

- 从本地已有历年 US News 原始 Excel 中继续挖掘更多学科。
- 网络只作为辅助检索，不建议把第三方页面直接作为正式权威数据源。

### P4：US News 学科权重

谨慎。除非找到官方 PDF/页面明确列出目标学科权重，否则不要自动生成正式权重图。可以保留：

- `blocked`
- `candidate_requires_acceptance`
- 或仅展示指标覆盖数量，不展示权重

## 当前结论

可以通过网络补一部分，而且应该优先补“共性且可验证”的部分：

1. 软科历年分项指标：最值得补，能直接提高多数学科完整度。
2. CWTS 五大宽领域论文指标：值得补，但必须写明宽领域代理口径。
3. US News 历史分项和权重：不建议自动网络补齐，除非找到稳定官方源或本地原始表里能恢复。

因此，下一步最合理的工程任务不是泛泛搜索网页，而是新增两个补源脚本：

```text
scripts/acquire_arwu_gras_history_pages.py
scripts/process_cwts_all_field_subject_proxies.py
```

前者解决软科多年历史表，后者解决更多学科的论文类图表。
