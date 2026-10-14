# ESI千分之一学科趋势模块

本模块根据用户提供的ESI参考报告图3至图10，生成独立的八学科趋势Word验收样例。每个学科包含两三行黄色分析文字、一张蓝色折线图和图题，图号沿用原报告。图表范围为2024年11月至2026年9月的12个双月节点。

## 输入与运行

- `configs/esi_trend/source_config.json`：参考文件、项目内原始文件快照、输出目录、渲染工具和版式开关。
- `configs/esi_trend/verified_chart_data.json`：Agent逐图核对并转录的96条观测值、图表规格、正文和来源修正记录。
- `data/esi_reference/tongji_esi_reference_20261014.docx`：源报告原样备份，按SHA256校验。

直接运行 `scripts/build_esi_subject_trends.py` 生成Word、图表、数据和重绘包；再运行 `scripts/render_esi_subject_trends.py` 使用Documents标准渲染链路与Windows LibreOffice包装器检查版式。脚本无需命令行业务参数。优先使用 `E:/conda_envs/graph-rag/python.exe`。

## 处理流程

原始DOCX先提取为正文块、黄色高亮、7个物理表格和11个图片对象。原文没有可直接读取的图表XML或嵌入工作簿，图3至图10的数值由当前Codex Agent使用视觉能力逐图转录，随后作为UTF-8静态数据读取；正式运行无需模型API。

静态数据经校验后形成96条绘图观测值，并计算8科的期初、期末、下降量、相对下降比例、回升节点和首次观察到进入前1‰的节点。matplotlib生成PNG和SVG，python-docx将正文、图片及图题组装为独立Word。图表之间不借用教育部一级学科或四大榜单的别名关系。

源图2026年7月的8科千分位数值与源附表万分位逐科交叉核对，关系为千分位乘10等于万分位。当前样例的2026年9月数值来自趋势图，不以7月表格代替。数值越小，排名越靠前；前千分之一阈值为1‰，前万分之一阈值为0.1‰。

## 输出与重绘

正式产物位于 `outputs/esi_subject_trends/`：

- 独立Word与 `esi_trends_replot_bundle.zip`。
- `all_trend_data.csv`：96条可见标签转录数据。
- `trend_summary.csv`：8科学科变化分析结果。
- `reference_analysis.md`：完整参考报告结构、视觉解析记录、单位和图题修正。
- `artifacts/<subject_key>/`：每科的CSV、图表规格、PNG、SVG、原图、分析文字和来源追踪。
- `qa/`：结构审计、渲染页、版式审计及视觉验收记录。

让其他AI重绘单图时，发送该学科目录内的 `chart_data.csv`、`chart_spec.json`、`source_trace.csv`、`reference.png` 和 `replot_request.md`；全部重绘可以直接发送重绘ZIP。

## 参考报告修正

原图10的图题写成“地球科学”，图片标题与黄色分析段落对应“药理学与毒理学”。样例已修正图题，并保存原图题供追溯。原报告封面和部分表格标注2026年7月，趋势图实际延伸到2026年9月，样例直接标明实际观察期。

## 后续接入

`append_trend_section` 是可复用的Word组装函数。后续按用户选择接入现有学科报告时，先配置ESI学科与目标报告学科的对应关系，再调用该函数。当前交付范围是独立样例。
