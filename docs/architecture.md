# OpsWeave 架构设计文档

## 直连检索管道

- `/api/retrieval/search` 不经过聊天 Agent，由 `opsweave.agents.retrieval_pipeline` 的 LangGraph 管道独立处理：连接索引 →（可选，预留）问题分解 → 向量检索合并去重 →（可选，预留）重排。
- 检索索引按 collection 在进程内缓存；管理员修改 Milvus/Embedding 配置或删除 Milvus 集合时清空缓存。混合检索（向量 + 关键词融合）计划在检索节点内扩展。

## 记忆

- 短期会话记忆存放在 SQLite `chat_messages` 表，按用户和 `conversation_id` 隔离。
- 长期记忆存放在 `data/documents/{username}/memory.md`，由用户在聊天中显式添加。

## MCP 与工具审批

- 本地内置 MCP Server 使用 stdio 子进程连接；管理员配置的远程 Server 使用 Streamable HTTP。
- MCP Client 合并各 Server 的工具清单，Agent 使用内部 `tool_id` 选择工具，不向 LLM 暴露 Server ID。
- MCP 工具元数据 `annotations.readOnlyHint` 仅在明确为 `true` 时作为只读工具直接执行；元数据缺失或其他值均视为高风险，先创建 SQLite 待审批记录。
- 发起人或管理员可查看并处理自己的/全部待审批项；批准后后端执行该工具，拒绝则不执行。审批项状态持久化，重复处理会被拒绝。
