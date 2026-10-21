# 阶段一盘点核验摘要

## 本阶段目标

把原始 Word/Excel 资产转换成后续分析 agent 可读取、可审查、可修改的配置基础。

## 已生成文件

- `data_catalog.json`：Excel 工作簿、sheet、字段、样例值与角色推断。
- `target_template_outline.json`：标黄理科模板的段落结构。
- `reference_report_outline.json`：数学参考报告的段落、表格、图片结构。
- `reference_report_structure.md`：参考报告中章节、图表、表格标题的人工可读摘录。
- `report_slots.yaml`：报告待生成位置与任务定义。
- `slot_data_mapping.yaml`：每个任务建议使用的数据源、联接键、风险。
- `entity_aliases.yaml`：学校、榜单、字段别名初稿。

## 核验结果

- Excel 文件数：37
- Excel sheet 数：59
- 目标模板非空段落数：25
- 目标模板标黄段落数：2
- 参考报告表格数：8
- 参考报告图片数：14
- 报告 slot 数：9
- 低置信度 slot：paper_strength_analysis, research_frontier_interdiscipline

## 数据角色统计

- subject_mapping: 4
- ranking_detail: 33
- indicator_weight: 12
- domestic_evaluation: 5
- tongji_subject_mapping: 5

## 需要人工确认的点

1. 对标高校范围：双一流高校、第五轮同档高校、还是各榜单前200内地高校？
2. 目标学科：当前参考报告是数学，后续生成其他学科时需要给出一级学科名称或学院名称。
3. “研究前沿及学科交叉”目前没有明显专门数据源，需要补教师方向/研究方向数据，或改为基于排名指标的弱分析。
4. 论文实力若要达到参考报告图10-图13的颗粒度，可能需要独立 WOS/Scopus 论文数据；当前可先使用排名明细中的论文代理指标。
