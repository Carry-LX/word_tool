# 在另一台 Windows 电脑运行项目

代码与原始 Excel、Word 模板在私有仓库 https://github.com/Carry-LX/word_tool 。已处理数据及渲染工具在同一仓库的 `runtime-data-20261021` Release。

## 新电脑操作

1. 安装 Git、GitHub CLI、64 位 Python 3.12 和 Microsoft Word。软件优先放到 E 盘；若已有 `E:\conda_envs\graph-rag\python.exe`，初始化器会直接用它创建项目环境。Microsoft Word 需能正常启动。
2. 在 GitHub CLI 登录有仓库权限的账号：`gh auth login`。然后执行 `gh auth setup-git`。
3. 将仓库克隆到希望保存的位置，例如 `E:\projects\water\word_tool`：`gh repo clone Carry-LX/word_tool`。
4. 双击根目录 `setup_new_computer.cmd`。它创建 `.venv`、安装依赖、恢复数据并检查 Word、数据库和历史报告。Python 包安装关闭 pip 缓存；压缩分包核验并读取后自动删除。
5. 初始化通过后，双击 `start_report_demo.cmd`，在浏览器访问 `http://127.0.0.1:8766`。

Python 未安装到约定路径时，初始化器使用 Windows 的 `py -3.12` 启动器。若启动器不可用，先用自己的 Python 3.12 创建 `.venv`，再双击初始化文件。可选录屏依赖位于 `requirements-recording.txt`，录屏还需按 `docs/LOCAL_REPORT_DEMO.md` 配置浏览器和 FFmpeg；普通报告生成不安装录屏依赖。

## 数据与空间

`data/` 是 Git 中的原始数据和模板；`processed/` 是 SQLite、维表、事实表和学科桥接；`external_data/` 是补充数据与溯源材料；运行包只挑选 `outputs/` 中当前演示依赖、被索引的报告和对应 source run，保留示例展示和随机抽查功能。旧视频、重复压缩包和历史失败任务不参与迁移。

Windows 渲染工具恢复到项目 `.local/`：LibreOffice、兼容包装器和 Poppler 不占用系统安装位置，也不要求另一台电脑安装 Codex。标准 `render_docx.py` 的项目副本位于 `tools/documents/`。工具快照约 1.6 GiB；数据与示例报告还需要若干 GiB，以 `outputs/github_migration/package_plan.json` 的核查记录为准。临时压缩包最多同时保留一份 512 MiB 分包；正在恢复的单个文件通过临时文件校验后原子替换。

上传端从原文件流式打包，不复制整份数据树。每一分包上传后校验 GitHub 返回的大小和 SHA-256；若服务未返回摘要，则流式回读远端计算摘要。确认一致才删除本地压缩包。失败时保留尚未确认的分包，避免丢失恢复依据。原始数据、数据库和已有报告不删除。

下载端先核对分包 SHA-256，再逐文件核对清单中的 SHA-256。重跑时保留已恢复且内容一致的文件；不同内容的已有文件默认报错，不覆盖。可在 `tools/migration/restore_runtime.py` 顶部调整显式变量。中断后的未完成分包保存在 `.local/downloads/`，重跑会检查并重新下载。

## 配置与路径

运行配置仍集中在 `configs/runtime/agent_runtime_profile.json` 和 `current_subject_request.json`。初始化程序只写被 Git 忽略的 `configs/runtime/local_runtime.json`，记录新电脑 Python 和 ASCII 临时目录路径。临时目录优先使用项目 `.local/tmp`；项目路径含中文时，按 E 盘、D 盘、公共用户目录的顺序选择可写的 ASCII 路径，并设置渲染进程 TEMP/TMP，避免中文 Windows 用户名影响转换。历史报告中的旧项目绝对路径在文件不存在时解析到当前 checkout，不改写原始证据文件。推荐保留项目目录名 `word_tool`。

演示默认关闭叙述 API，不需要 API Key。全局批量入口仍按 runtime profile 中的 DeepSeek 开关执行；需要使用时，在新电脑单独配置环境变量，或明确关闭该开关。

## 发布与核验入口

`tools/migration/publish_runtime.py` 默认只规划文件并编译包装器，`PUBLISH=False`。经确认完成本地提交和 push 后，由发布者将该显式变量设为 True 运行，或在交互式 Python 中设置模块变量再调用 main。它先建立草稿 Release，全部附件上传核验后再由发布者完成恢复验证并发布。

`tools/migration/check_portability.py` 只读检查当前机器的依赖、数据库、学科列表、示例报告索引和 Word COM。系统级检查继续运行 `scripts/audit_agent_system_readiness.py`。新电脑应生成至少一份报告，确认 Word、PDF 和页面 PNG 完整产生。

上传前只纳入代码、配置、原始数据、文档和人工交接说明。个人聊天导出、编辑器本机配置、环境目录、凭据和全部历史输出不进入 Git。
