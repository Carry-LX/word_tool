# Template Slot Inventory

- reference_docx: `E:\projects\water\word_tool\data\同济大学XX学科的国际排名发展分析-2026年5月.docx`
- target_template_docx: `E:\projects\water\word_tool\data\【标黄】同济大学学科分析报告——理科（2026年）.docx`
- reference_blocks: 131
- reference_slots: 44
- reference_images: 14
- reference_tables: 8
- target_slots: 0
- covered_reference_slots_by_current_artifacts: 17
- uncovered_reference_slots: 27

## 判断

当前 10 个 artifact 覆盖的是核心分析链路，不等于覆盖了参考 Word 的全部图表槽位。下一步需要人工/规则结合地筛掉装饰性表格、拆分正文表格与图表，并形成最终 `slot -> artifact_id -> visual_style` 映射。

## 输出文件

- `reference_blocks.csv`：参考报告按文档顺序抽取的段落/表格/图片段落。
- `reference_slots.csv`：参考报告中候选图、表、标题槽位及初步 artifact 候选。
- `target_template_blocks.csv`：标黄模板按文档顺序抽取的段落/表格/图片段落。
- `target_template_slots.csv`：标黄模板候选槽位。
- `summary.json`：数量摘要。
