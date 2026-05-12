# Narrative Generation Prompt Template

你现在要为世界学科排名分析报告生成正文段落。请严格根据输入 JSON 中的 `tasks` 生成，不要改写任务结构，不要合并段落，不要新增未请求的段落。

## 目标

为每个 `logical_slot_id + segment_key` 生成一段可以直接写入 Word 模板正文的中文分析文字。

## 写作约束

1. 严格一段对应一个 `task`，不要合并多段。
2. 语气应接近正式分析报告，不要写成提示语、说明书或项目日志。
3. 段落长度以原模板对应段落为参考，通常为 1-3 句，优先控制在原模板长度的 0.8-1.4 倍内；除非原模板本身很短，否则不要明显长于原模板。
4. 必须优先使用输入中已有的数据结论、`generation_hint`、`artifact_narrative` 和 `data_preview`。
5. 如果某个指标或口径有明显边界，例如 THE 是领域口径、CWTS 是宽领域代理口径，应在表述中保持克制，不要写成超出数据边界的结论。
6. 不要发明未提供的具体数值、学校名称或位次。
7. 不要输出 Markdown，不要加标题，不要使用项目符号。
8. 输出必须是合法 JSON，字段名与输出模板完全一致。
9. 风格尽量贴近原模板：结论先行、句子偏短、少用解释性套话，避免“换句话说”“这说明”“从某种意义上”等扩写口吻。
10. 如果输入中包含 `template_mode=proxy_full` 或 `requires_disclosure=true`，必须在相关段落里自然保留代理口径边界，不要把代理学科写成精确一级学科数据。
11. 如果输入中包含 `template_mode=partial`，只能围绕已提供来源写结论；缺失来源要写成“未检索到/暂不纳入比较”，不要用相邻来源补成完整结论。
12. 如果输入中包含 `word_assembly_manifest` 的 `slot_decisions`，只为 `include_in_word=true` 的槽位生成正文；被排除槽位不要生成段落。

## 生成偏好

1. 先概括整体结论，再指出优势和短板。
2. 对历史趋势，优先写“提升/回落/波动”的方向性结论。
3. 对分项指标，优先写“哪些指标相对较强、哪些指标明显偏弱”。
4. 对论文指标，优先区分“数量表现”和“质量/占比表现”。
5. 同一段内避免重复解释同一个事实。
6. 能用一句话说清时，不要硬写成两三句。

## 输入

你将收到一个 JSON 文件，其中每个 task 至少包含：

- `logical_slot_id`
- `artifact_id`
- `segment_key`
- `reference_caption`
- `generation_hint`
- `template_text`
- `artifact_narrative`
- `data_preview`
- `source_files`
- `template_mode`
- `requires_disclosure`
- `disclosure_text`
- `word_assembly_manifest`

## 输出

按输出模板返回 JSON：

- `segment_texts` 中每一项必须对应一个输入 task
- `text` 字段只写最终正文，不要再包解释
