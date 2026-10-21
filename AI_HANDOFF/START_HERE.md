# word_tool：其他 AI 接手入口

初始化日期：2026-10-19（Asia/Shanghai）。本目录可以直接用普通文本编辑器或其他 AI 读取，不依赖 Codex 登录、应用或 API。

## 阅读顺序

1. `HANDOFF.md`：当前目标、实现链路、交付物与未完成事项。
2. `DECISIONS.md`：已经形成的关键约定，以及旧文档冲突的处理方式。
3. `USER_RULES.md`、`snapshots/user/GLOBAL_AGENTS.md`、`snapshots/project/AGENTS.md`：用户与项目协作要求。
4. `history/INDEX.md`：按标题找到相关讨论，先看各聊天的 `OVERVIEW.md`，有疑问再读分段对话和原始 JSONL。
5. `state/export_manifest.json`、`state/git_state.json`、`state/project_inventory.json`：自动采集时间、记录范围、Git 与文件索引。
6. 项目实际文件；`snapshots/project/` 是本次保存的文档和配置副本。

`NEXT_AI_PROMPT.md` 可以直接复制到新 AI。只想上传少量资料时，先上传本文件、HANDOFF、DECISIONS、USER_RULES，再按需补充某个聊天分段和相关代码。能访问本机的 AI 直接读取整个目录即可。

## 2026-10-21 迁移任务

用户已授权创建 GitHub 私有仓库、上传当前代码和运行数据，并要求完成传输后删除临时压缩包。仓库为 `Carry-LX/word_tool`；迁移实现与新电脑步骤见 `docs/MIGRATION.md`。GitHub 迁移分支为 `codex/github-migration`。聊天、快照和自动状态仍保留本机，已设为 Git 忽略；人工交接说明随代码迁移。

迁移交付：远端 `main` 保存代码及原始资料，`runtime-data-20261021` Release 保存六个运行分包和清单。核查记录见 `docs/MIGRATION_CHECKS.md`；本机细项回执见 `outputs/github_migration/`。新电脑先运行 `setup_new_computer.cmd`，初始化后运行 `start_report_demo.cmd`，无需安装 Codex。

## 后续怎样保持可用

双击 `refresh.cmd`，可在 Codex 无法打开时重新采集本地聊天、文档快照、文件目录和 Git 状态。Python 路径在 CMD 顶部显式设置；筛选设置在 `tools/refresh_handoff.py` 顶部。没有第三方依赖，不调用模型，不联网。

刷新只更新自动生成的 history、snapshots、state。它不会理解新进度，也不会改写 HANDOFF、DECISIONS 或用户规则。每个稳定阶段由当前协作 AI 更新这几份人工交接文档，再运行刷新。

若某个相关聊天在其他工作目录开始，在脚本 `ADDITIONAL_SESSION_IDS` 中补入会话 ID。已导出的旧文件保留，以当前 INDEX 和 manifest 为本轮索引。日志中的附件引用不等于附件文件已打包。

此目录保存交接背景和证据；完整运行仍需要项目的数据、代码、输出与本机环境。原始聊天可能包含历史敏感文本，外发前按实际需要选取。
