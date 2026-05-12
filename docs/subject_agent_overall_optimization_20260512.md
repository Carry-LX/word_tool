# Subject Agent 整体优化记录

日期：2026-05-12

## 本轮目标

本轮在 `codex/agent-overall-optimization` 分支上做 agent 级工程化优化，目标是让换学科生成更稳定、更容易审计，并减少与其他分支或其他 agent 并行工作时的互相污染。

## 关键改动

1. 主入口路径去硬编码
   - `scripts/run_subject_agent.py`
   - `scripts/subject_artifact_builders.py`
   - `scripts/audit_subject_agent_run.py`
   - `scripts/build_ready_artifacts.py`

   这些脚本从固定 `E:\projects\water\word_tool` 改为 `Path(__file__).resolve().parent.parent`。

2. 运行请求改为 run 级产物
   - 默认不再改写 tracked 文件 `configs/runtime/current_subject_request.json`。
   - 每次运行在本次 run 目录写入 `current_subject_request.json`。
   - 如确实需要兼容旧脚本，可在 `scripts/run_subject_agent.py` 顶部把 `WRITE_GLOBAL_CURRENT_REQUEST` 改成 `True`。

3. README 不再被每次运行自动改写
   - 新增 `UPDATE_README_ON_RUN = False`。
   - README 作为交接文档，后续只在需要时人工更新。

4. 增加 run manifest
   - 每次运行生成 `run_manifest.json`。
   - 记录 Python 环境、输入文件检查、目标学科、ready/gap 计数和核心输出路径。

5. artifact 生成改为容错式调度
   - `scripts/subject_artifact_builders.py` 新增 `append_builder_result`。
   - 单个 artifact 抛异常时，写入 `status=error`、异常类型、原因和 traceback。
   - 不再因为一个图表失败而中断整轮 agent。
   - 汇总中新增 `error_count`，并在有错误时输出 `artifact_generation_errors.json`。

6. 明确 graph-rag 运行环境
   - `scripts/run_subject_agent.py` 中记录推荐环境 `E:\conda_envs\graph-rag\python.exe`。
   - `agent_run_summary.json` 和 `run_manifest.json` 会写入实际 Python 路径，并判断是否正在使用推荐环境。

7. 临时图表实验文件不再进入 Git
   - `.gitignore` 新增 `scripts/_test_charts.py` 和 `scripts/test_*.png`。

## 验证结果

使用环境：

```powershell
E:\conda_envs\graph-rag\python.exe
```

验证命令：

```powershell
& 'E:\conda_envs\graph-rag\python.exe' -m py_compile scripts\run_subject_agent.py scripts\subject_artifact_builders.py scripts\audit_subject_agent_run.py scripts\build_ready_artifacts.py
& 'E:\conda_envs\graph-rag\python.exe' scripts\run_subject_agent.py
```

端到端运行结果：

- 学科：计算机科学与技术
- run 目录：`outputs/subject_agent_runs/20260512_145658_0812_计算机科学与技术`
- artifact：24 generated / 0 skipped / 0 error
- 审计：24 pass / 0 fail
- 实际 Python：`E:\conda_envs\graph-rag\python.exe`

## 后续建议

1. 继续把旧 artifact 脚本中的硬编码路径逐步清理掉。
2. 把当前 `subject_artifact_builders.py` 中的大函数进一步拆成 ranking、weight、indicator、paper 四个模块。
3. 后续接 Word 生成时，也采用同样的 run 级 manifest 和容错式步骤记录。
