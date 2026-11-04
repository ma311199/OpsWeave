# OpsWeave 架构设计文档

## 记忆

- 短期会话记忆存放在 SQLite `chat_messages` 表，按用户和 `conversation_id` 隔离。
- 长期记忆存放在 `data/documents/{username}/memory.md`，由用户在聊天中显式添加。

## MCP 与工具审批

- 本地内置 MCP Server 使用 stdio 子进程连接；管理员配置的远程 Server 使用 Streamable HTTP。
- MCP Client 合并各 Server 的工具清单，Agent 使用内部 `tool_id` 选择工具，不向 LLM 暴露 Server ID。
- MCP 工具元数据 `annotations.readOnlyHint` 仅在明确为 `true` 时作为只读工具直接执行；元数据缺失或其他值均视为高风险，先创建 SQLite 待审批记录。
- 发起人或管理员可查看并处理自己的/全部待审批项；批准后后端执行该工具，拒绝则不执行。审批项状态持久化，重复处理会被拒绝。
