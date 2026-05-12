# 图表视觉格式优化记录（2026-05-11）

## 目标

针对计算机科学与技术学科输出，修正 Word 前图表产物中不适合直接入报告的问题：

- 图表里出现 `完整数据见 chart_data.csv`、`完整数据见 CSV` 等调试说明。
- 表格图片行列宽度不够稳定，长标题存在截断风险。
- 表格数值列没有统一居中，名称列和指标列可读性不足。
- 个别历史遗留污染字符串进入表头。

## 修改内容

- `scripts/subject_artifact_builders.py`
  - 新增 `elide_text`、`wrap_text`、`draw_text_box`，统一处理单元格文本换行、截断和对齐。
  - 优化 `render_table`：
    - 自动估算列宽。
    - 数值列居中。
    - 学校/指标列左对齐。
    - 去掉“完整数据见 CSV”类调试说明。
    - 根据标题宽度自动放大画布，避免标题被裁掉。
  - 优化 `render_weight`：
    - 去掉 `chart_data.csv` 引导语。
    - 改为报告可接受的权重说明。
  - 修正软科公开页历史表第一列表头污染：`鎸囨爣` -> `指标`。
  - 长表标题改为报告式表达，例如“按排名前32项”，不再提示去看外部 CSV。

## 验证输出

计算机科学与技术已重新生成：

- `outputs/subject_agent_runs/20260511_104750_0812_计算机科学与技术`
- artifact audit：21 pass / 0 fail
- pre-word QA：`issue_count=0, p1_count=0, p2_count=0`

重点检查图片：

- `artifacts/table_01_arwu_tongji_indicator_history/table.png`
- `artifacts/table_05_arwu_mainland_peer_ranking/table.png`
- `audit/visual_contact_sheet.png`

当前观察：

- 旧版问号标题未复现。
- 调试型 CSV 提示已移除。
- 表格标题不再被裁切。
- 表头和数值对齐明显改善。

## 后续注意

这次优化主要处理公共渲染层，因此对后续学科迁移会自动生效。若进入 Word 自动填充阶段，建议继续区分：

- `table_matrix.csv`：用于生成真正 Word 表格。
- `table.png`：用于视觉预览或需要图片化插入的表格。

如果模板要求“表格对象”而不是“表格截图”，后续应优先把 `table_matrix.csv` 转成 Word 原生表格，而不是直接插入 `table.png`。
