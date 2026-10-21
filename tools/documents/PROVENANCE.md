# DOCX 渲染脚本来源

`render_docx.py` 是本机 Codex Documents 插件 26.1015.12040 的标准渲染脚本快照（2026-10-21），按 UTF-8、LF 原样保存。

它调用 LibreOffice 转 PDF，再用 pdf2image 和 Poppler 生成页面 PNG。迁移运行包提供 Windows 工具，项目的 `audit_word_report.render_environment` 负责设置进程 PATH，因此新电脑无需安装 Codex 插件。

`tools/migration/soffice_wrapper.cs` 基于本机已验证的包装器，改为相对路径定位 LibreOffice，并在退出后清理复制的临时输入。
