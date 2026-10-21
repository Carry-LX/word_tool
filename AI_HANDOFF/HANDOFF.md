# word_tool 当前交接说明

最近人工核查日期：2026-10-21；本目录初始化于 2026-10-19。后续更新请同时记录日期和证据文件。

## 项目目标与当前阶段

项目位于 `E:\projects\water\word_tool`。利用国际排名、分项指标、学科映射、论文指标及核实后的 ESI 数据，按同济大学学科自动生成可审阅的 Word 分析报告，并用本地前端展示真实生成过程，供导师观看操作演示。

当前已存在完整 Word 链路、本地前端、连续录屏、30 秒演示及 GIF。根目录旧 `START_HERE_FOR_NEXT_AGENT.md` 混合保存了不同阶段说明，其中“还没有进入最终 Word 自动填充”等早期句子已被后续实现取代。当前操作入口优先参考 `docs/LOCAL_REPORT_DEMO.md`、运行配置和本目录历史。

## 原始输入 → 中间处理 → 最终任务

1. 原始输入：`data/` 中的排名 Excel、指标、学科映射及 Word 模板；ESI 来源和补充材料见相关 docs。原始文件保留。
2. 中间处理：构建数据治理与学科桥接，产出 `processed/ranking.sqlite`、CSV、来源选择和质量检查。`scripts/build_processed_core.py`、`build_ranking_indicators.py` 负责核心事实层。
3. 单学科任务：`scripts/run_subject_agent.py` 解析学科、选定榜单口径；`subject_artifact_builders.py` 产出图表、表格、来源记录与可用性结果。
4. Word：现有组装与 QA 链路生成 Word、更新域、渲染页面；批量入口包括 `run_batch_reports.py`，具体组装见 `build_word_replacement_trial.py`。
5. 演示：`demo_worker.py` 运行独立任务，`pipeline_observer.py` 发出真实阶段事件，`demo_stage_results.py` 提供阶段预览。前端每次从现有中间层开始，不重新执行全量 Excel 入库。

界面显示六个节点：数据检查、学科解析、来源决策、图表分析、Word 组装、渲染核查。一次运行一个报告任务。单次任务数据位于 `outputs/web_demo_runs/<job_id>/`，请求快照注入工作进程，不改全局学科请求。

## 现在怎么运行

双击根目录 `start_report_demo.cmd`，默认使用 `E:\conda_envs\graph-rag\python.exe`，本地地址为 `http://127.0.0.1:8766`。

- 全局配置：`configs/runtime/agent_runtime_profile.json`。
- 演示配置：`configs/runtime/web_demo_profile.json`，当前默认学科 `0830`，随机抽查默认 3 份。
- 目标学科配置：`configs/runtime/current_subject_request.json`。
- 报告编排与 ESI 展示关系：`configs/runtime/report_editorial_policy.json`。
- 软科原始文件选择：`configs/runtime/ranking_source_inputs.json`。

重要配置差异：web demo 的 `enable_narrative_api=false`；全局 runtime profile 的 narrative_llm.enabled 为 true，配置有 DeepSeek 提供方。不要把演示入口无需 API Key 的行为直接推定为所有批量入口的行为；运行前读实际调用链与配置覆盖。

## 最近完成的工作与可核查文件

- 最近项目聊天：`了解 word_tool 项目 (2)`，会话 ID `01a14a0d-e03a-7b02-b997-877581bcef13`。
- 导师希望看到直观操作演示，已建立选择学科、真实生成、节点回看、Word 预览下载和随机抽查流程。
- 30 秒视频：`outputs/web_demo_delivery_30s/operation-demo-30s.mp4`。
- 最新 GIF：`outputs/web_demo_delivery_30s/operation-demo-30s.gif`。本次检查文件存在，大小 11,007,607 字节；历史聊天报告为 30 秒、1280×800，具体检查见同目录 `gif_checks.json`。
- 原录制交付：`outputs/web_demo_delivery_v2/`；紧凑视频检查与帧映射见 30s 目录的 `video_checks.json`、`video_frame_mapping.npz`。
- 录制、导出逻辑与限制：`docs/LOCAL_REPORT_DEMO.md`、`scripts/build_demo_video_30s.py` 等。
- 软科 2026 数据接入：`docs/ARWU_2026_SOURCE_UPGRADE.md`；审计见 `outputs/arwu_source_upgrade_20260915/`。

上述视频/GIF文件存在已由本次读取确认；历史记录中“检查通过”的具体内容属于原任务证据。本次交接初始化没有重新跑报告、浏览器或视频完整解码验证。

## ESI 与学科映射的当前口径

演示继续使用已确认的六个报告关联：环境科学与工程、材料科学与工程、化学、计算机科学与技术、临床医学、药学。地球科学、社会科学总论由当前演示配置排除。ESI 宽领域、软科学科和教育部一级学科分别保留自身统计口径；图表展示关联不等于学科分类完全相同。

软科综合排名、同济历史指标和同行指标复用运行时选中的唯一口径。直接映射没有数据时，按映射置信度和披露策略决定处理，不自行用名称相近学科替换。

## 交接初始化时的 Git 状态（2026-10-19）

初始化前分支为 `codex/agent-overall-optimization`，最新提交 `2bec57d`，提交说明为“备份报告演示界面、ESI精简建议与连续录屏优化”。存在多项未提交业务修改和新增文件，本次全部保留。当前状态以 `state/git_state.json` 和实际 `git status` 为准。

`processed/`、`outputs/`、`external_data/`、`release/` 等在项目忽略规则中，Git 提交不能替代这些目录的文件备份。本交接目录的状态快照也不能代替数据和输出全量备份。

## 2026-10-21 GitHub 迁移阶段

用户明确授权将代码和运行数据迁移到另一台电脑，优先通过 GitHub，并要求传输完成后清理临时压缩包。已创建私有仓库 `https://github.com/Carry-LX/word_tool`，工作分支 `codex/github-migration`。原有业务修改全部保留并准备一并备份。

新增 `tools/migration/`、初始化入口、依赖清单和 `docs/MIGRATION.md`。运行数据计划包含 processed 64 文件（4,916,755,587 bytes）、external_data 213 文件（438,853,973 bytes）、当前演示及索引报告素材 20,896 文件（1,033,428,796 bytes）、Windows 工具 19,601 文件（1,683,187,934 bytes）。代码和原始 data 进 Git，运行数据在 `runtime-data-20261021` Release 分包。实际清单见本机 `outputs/github_migration/package_plan.json`。

运行入口优先项目 `.venv`；本机 Python 与 ASCII 临时目录覆盖记录到被忽略的 `configs/runtime/local_runtime.json`。历史索引旧绝对路径缺失时映射到当前项目，渲染优先项目标准脚本副本和 `.local/` 工具。不改写历史数据文件。

用户已确认本地备份提交，并授权继续上传、清理及提交校验和交接记录。代码和原有业务修改已在 `codex/github-migration` 本地备份，并推送远端 `main`。运行包 40,774 文件，未压缩 8,072,226,290 字节，六个分包共 1,933,116,219 字节；清单逐项保存 SHA-256。

已核查：Python 源码语法、中文内容及目录/文件名跨分包恢复、SHA-256 拦截、保护已有改动、目录穿越拒绝、临时分包清理、页面接口、46 学科选项和 46 历史报告索引。系统体检 P0/P1 为 0。Word 预检核对 COM 注册与 Python 导入。

远端 processed 分包已完整流式回读，64 文件逐文件 SHA-256 一致；Windows 工具已从附件完整恢复到独立中文目录，19,601 文件逐文件 SHA-256 一致，并使用恢复后的工具实际将中文报告转换为 PDF 和页面 PNG，中文输出目录可用。约 1.57 GiB 工具测试副本已删除。上传分包均在远端核验后删除本地副本，最终临时目录清理见本机 `outputs/github_migration/cleanup_receipt.json`。

发布入口为 `https://github.com/Carry-LX/word_tool/releases/tag/runtime-data-20261021`。Release 保留 `runtime-manifest.json` 和 `migration-checks.json`；本机详细证据在 `outputs/github_migration/`。`docs/MIGRATION_CHECKS.md` 保存人工核验结论，`docs/MIGRATION.md` 保存新电脑步骤。打包时提交与最终配套代码提交分别记录在 manifest 的 packaging_commit 和 code_commit。

## 下一位 AI 的第一步

当前用户授权的 GitHub 迁移工作已交付。先读取本目录、迁移文档和用户下一项要求；新电脑按初始化入口恢复运行环境与数据。若继续演示工作，先看本机已有 GIF/MP4 与检查结果；若修改跨学科、数据治理或可维护性逻辑，按项目规则运行 `scripts/audit_agent_system_readiness.py` 并检查 P0/P1，再生成 Word。

涉及界面或录屏时，按文档执行相应 dashboard、state I/O、recording、video 检查，避免重新运行真实任务造成重复。提交前先向用户总结文件和变更并取得确认；只做本地备份，不主动 push。
