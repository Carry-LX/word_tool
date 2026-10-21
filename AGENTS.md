# 项目协作规则

- 跨 AI 接手先读 `AI_HANDOFF/START_HERE.md`、`AI_HANDOFF/HANDOFF.md` 和 `AI_HANDOFF/DECISIONS.md`。根目录旧接手说明包含历史阶段，当前状态以新交接说明、实际配置和用户后续决定核查。
- 每个稳定阶段更新上述人工交接说明，记录进度、决策、验证与下一步，再运行 `AI_HANDOFF/tools/refresh_handoff.py` 刷新聊天和证据。自动刷新不会代替人工更新进度。

- 向用户给出本机文件路径时，优先使用纯文本绝对路径或代码块，不要把 Windows 路径包装成 Markdown 链接；Markdown 会吞掉反斜杠，导致界面里的“打开”路径失效。
- 报告生成 Agent 的运行入口配置集中在 `configs/runtime/agent_runtime_profile.json` 和 `configs/runtime/current_subject_request.json`；换学校、换学科、换输出策略时优先改这两个文件，不要在多个脚本里散改硬编码。
- 脚本入口仍然保持“显式变量、无命令行参数”的习惯，但显式变量应默认从 runtime profile / subject request 加载，只有调试时才作为兜底。
- 每次做跨学科、数据治理、可维护性相关修改后，运行 `scripts/audit_agent_system_readiness.py` 生成系统体检结果，先看 P0/P1 问题再生成最终 Word。
