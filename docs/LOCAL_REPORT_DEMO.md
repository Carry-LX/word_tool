# 本地报告操作演示

这套界面用于录制“选学科、运行流程、审阅 Word、随机抽查”的操作视频。前端连接项目现有生成链路，运行节点来自实际后台事件。

## 启动

双击项目根目录的 `start_report_demo.cmd`。它使用 `E:/conda_envs/graph-rag/python.exe` 启动本机服务，并打开 `http://127.0.0.1:8766`。关闭启动终端会结束服务；已经启动的独立报告任务会继续执行，其结果保存在任务目录中。再次启动服务可恢复显示。

主机、端口与子配置路径在 `configs/runtime/agent_runtime_profile.json` 的 `web_demo` 段设置。学科默认值、报告索引、抽查规则、Word 更新与运行输出在 `configs/runtime/web_demo_profile.json` 设置。脚本使用显式配置，无需命令行参数。

## 页面操作

1. 选择目标学科，点击“开始生成报告”。同一时间运行一个报告任务，防止图表、Word 与渲染争用资源。
2. 六个节点依次展示数据检查、学科解析、来源决策、图表分析、Word 组装与渲染核查。右侧结果区展示真实输入统计、匹配记录、榜单口径、逐项生成的图表或表格、Word 章节及检查后的页面。点击节点可回看该步结果，点击“跟随运行”继续自动切换。记录按钮可展开事件与下载日志。页面刷新后恢复最近任务。
3. 完成后在“本次生成”中打开 Word 页面，翻页查看，点击“末页建议”检查 ESI 与精简建议，或切换到“分析图表”。“放大阅读”与“查看整页”可切换预览尺寸。
4. 下载 Word。每次完成时自动随机抽查 3 份报告，也可以点击“换一组”重新抽取。

初次进入页面时会展示明确标注的历史报告示例。成功生成后才切换为本次结果。抽查候选必须为完整报告、至少覆盖 3 个榜单、超过 2 页且已有通过的渲染核查结果；按学科去重并优先使用本机新结果。换组时，在候选充足的情况下排除上一组。

## 处理链路与隔离

原始输入（排名 Excel、ESI 原始报告） → 已有处理层（SQLite、CSV、学科映射、已核实 ESI 序列） → 单学科任务（请求快照、来源决策、图表及数据） → Word 组装（现有模板、精简建议、适用的 ESI 章节） → 页面渲染与检查 → 浏览器审阅与下载。界面每次运行从已有处理层开始，不重复执行全量 Excel 入库。

`run_subject_agent.py` 通过 `pipeline_observer.py` 发出前四个阶段的事件，`subject_artifact_builders.py` 每完成一项素材就发出一次更新。普通脚本运行默认无观察者。`demo_worker.py` 在独立进程中接入观察者，`demo_stage_results.py` 从实际数据库、来源决策、完成的图表文件和 Word 读取预览；既有生成器、Word 组装器和 `audit_word_report.audit_docx` 继续负责生成及核查。检查未通过时任务显示错误并保留日志。Windows 状态文件读取允许共享删除，并对短暂占用做有界重试，保证高频刷新时仍原子替换完整 JSON。

每次任务位于 `outputs/web_demo_runs/<job_id>/`，包含请求快照、事件、图表、Word、QA 与运行日志。请求通过 `SUBJECT_REQUEST_PATH` 注入工作进程，不改写全局 `current_subject_request.json`。界面不接受任意脚本或文件路径，仅接受配置中已有学科代码。默认关闭外部叙述 API，读取项目数据和已有分析规则，无需新增 API Key。

## ESI 范围

继续使用 `report_editorial_policy.json` 中已确认的 6 个对应关系：环境科学与工程、材料科学与工程、化学、计算机科学与技术、临床医学、药学。地球科学与社会科学总论从本轮生成和界面列表中排除。保留原始核实数据与历史文件，后续批量入口默认不生成这两个专题。

## 验证与录制

`scripts/check_demo_dashboard.py` 检查接口校验、六个 ESI 对应关系、两类专题过滤、抽查排除、下载内容、实际页面预览、图表导航与手机宽度，结果在 `outputs/web_demo_validation/`。

服务启动后直接运行 `scripts/record_demo_operation.py`，会通过 Edge 浏览器真实点击按钮生成一份环境科学与工程报告，持续录制流程、页面预览、ESI 与建议、下载及随机抽查。显式配置在脚本顶部。录制使用 `E:/tools/playwright` 中的 FFmpeg；MP4 编码由已安装 OpenCV 完成。录制脚本会启动真实任务；意外退出后先查看任务状态，等待或继续观察当前任务，再决定下一次录制。

本轮交付产物在 `outputs/web_demo_delivery_v2/`，第一版保留在旧目录。`operation-demo.mp4` 按实际等待状态做连续变速，默认 15 倍速，可在 `web_demo_profile.json` 的 `video_idle_speed` 改为 30；鼠标移动、点击、翻页、节点结果查看均保留原速。指针有移动轨迹与点击扩散圆环，在报告弹窗中同样可见。录屏用帧内标记区分等待和操作，逐帧按原始顺序输出，不通过估算墙钟时间拼接片段；`video_frame_mapping.npz` 记录成片帧对应的原始帧。完整 MP4 与 WebM、六个节点结果截图、Word、操作时间线和验证清单同时保留。页面预览继续通过标准 Documents 链路生成。

录屏期间固定视口为1600×1000，截图只截取当前视口；整页长截图在另一个未录制的浏览器上下文中完成。录屏时使用整页截图会短暂改变浏览器视口，在视频中出现整体缩小及灰边，因此禁止混用。

`scripts/check_demo_recording.py` 验证弹窗中的鼠标显示与帧标记；`scripts/check_demo_state_io.py` 验证并发读写；`scripts/check_demo_video.py` 解码核对成片帧数，检查操作帧保留、帧顺序、六个节点回看、原始视频灰边和固定页眉的像素稳定性。`scripts/finalize_demo_delivery.py` 完成这些检查后再打包，包内包含 `video_continuity_check.json`，并校验 ZIP 内容可完整读取。

系统体检仍执行 `scripts/audit_agent_system_readiness.py`。本轮所有源文件保留本地未提交状态。

## 30 秒快速演示

`scripts/build_demo_video_30s.py` 从已通过连续性检查的完整录屏生成 30 秒版，配置集中在 `web_demo_profile.json` 的 `compact_video`。五段分别分配 3、8、5、10、4 秒，用于设置、生成、六个节点回看、Word 预览及下载、随机抽查。整个源时间轴连续变速，不删除中间片段；保留录制中的鼠标轨迹，并按真实点击事件的位置和时间加强圆环提示。输出在 `outputs/web_demo_delivery_30s/`，原版视频保留。脚本逐帧核对来源顺序、成片时长、尺寸及缩放灰边，验证记录与帧映射一起落盘。
