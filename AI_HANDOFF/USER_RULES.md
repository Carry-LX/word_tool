# 用户长期协作要求（交接摘要）

根据用户在本次聊天提供的 AGENTS.md 整理，日期 2026-10-19。全局文件的原样内容另存于 snapshots/user/GLOBAL_AGENTS.md；项目根目录 AGENTS.md 补充项目规则。用户后续明确要求优先。

- 代码和新文本采用 UTF-8、LF。新版本独立创建并检查语法、乱码、引号与注释粘连，不整份复制历史污染。
- 默认 Python：E:\conda_envs\graph-rag\python.exe；项目有明确环境要求时按项目约束。Word COM 优先使用此环境。
- 参数写在代码顶部显式变量或项目配置中，不默认设计命令行参数入口。
- Windows 中中文、符号、路径、字段映射等通过明确 UTF-8 文件传递，避免 PowerShell here-string、内联脚本或控制台中转。跨边界验证关键文本。控制台编码出错时先排查编码，不直接认定业务数据错误。
- 修改前检查 Git 状态，保留现有未提交工作。大规模修改前检查仓库；无仓库提醒 git init。高风险改动使用 codex/任务名 分支。每个稳定阶段准备本地备份；git add / commit 前必须总结文件与变更并取得用户确认。没有明确指令绝不 push。
- 小中规模模型理解、提取、归纳等优先由当前 AI 阶段性完成并落盘 JSON/CSV/Markdown，不默认要求外部 API Key。大量反复调用或长期自动化先询问模型 API 与分批处理方案。
- 解释先说结论，再讲技术实现。复杂流程按“原始输入 → 中间处理单元 → 最终任务单元”解释，明确每层数字和一个具体例子，不混淆页、块、chunk 与任务数。
- 日志分析或图表交付同时提供分析后原数据、图表意图、复现/重绘源文件，以及要发给其他 AI 的文件清单。
- 全新网页项目前端先在同一个 HTML 网格提供六个布局、语气和信息密度不同的方案，标明取舍供用户选择。
- 软件与工具默认安装 E:\tools\工具名；安装包归档 E:\tools\installers。
- DOCX 优先标准 Documents render_docx.py 链路；LibreOffice 实体位于 E:\tools\LibreOffice\program\soffice.exe，但应优先命中包装器 E:\tools\codex-bin\soffice.exe。用实际文档的 PDF/PNG 渲染验证，不用 soffice --version 健康检查。
- Codex 商店版启动器修复不得直接裸跑 WindowsApps 下 Codex.exe；沿用带包身份 PowerShell 的两段式代理启动方案，入口 C:\Users\李鑫\.codex\launch_codex_with_proxy.cmd。
- 文字直接说明观点、依据、过程和证据，避免无信息增量的防御句、套话与弱化。保留事实强度与待定项。
- 交接维护：每个稳定阶段由当前 AI 更新 HANDOFF/DECISIONS 并刷新自动证据，写清验证了什么、哪些是历史声明、下一步需要什么。
