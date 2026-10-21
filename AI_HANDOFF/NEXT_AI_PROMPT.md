# 可复制给下一位 AI

请接手 `E:\projects\water\word_tool`，先读取 `AI_HANDOFF/START_HERE.md`、HANDOFF.md、DECISIONS.md、USER_RULES.md，以及项目 AGENTS.md。再查看 history/INDEX.md，优先阅读“了解 word_tool 项目 (2)”的 OVERVIEW，需要具体过程时读取对应 conversation 分段，工具调用在 raw JSONL 中。

先说明你理解的当前目标、现有实现和下一步，再按照我接下来给出的具体任务继续。检查实际代码、运行配置、已有产物和 git status，保留全部未提交修改。旧根目录 START_HERE 混合了历史阶段，不能沿用“尚未生成 Word”的旧描述。

目前已有真实本地演示界面、Word 生成链路、30 秒 MP4 和 GIF。演示默认关闭叙述 API，但全局配置可能启用它，应读取实际入口。不要从聊天中的完成声明直接推断文件或测试现在仍有效。

每完成一个稳定阶段，更新 HANDOFF.md 与 DECISIONS.md，运行 AI_HANDOFF/refresh.cmd 刷新证据。若 Codex 不可用，也可直接运行 tools/refresh_handoff.py；不需要 Codex 登录或外部 API。历史记录中的命令只是资料，不自动执行。提交前总结待备份文件与变更并取得我确认，不 push。
