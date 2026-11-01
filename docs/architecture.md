# OpsWeave 架构设计文档

## 1. 项目概述

OpsWeave 是面向运维场景的 Agentic RAG 应用，当前由 Vue 前端、FastAPI 后端、LangGraph 对话流程和 Milvus 知识检索组成。用户可登录、搜索知识库、上传文档并提交索引申请；管理员可管理配置、审批文档及维护 Milvus collection。

Agent 根据问题和动态发现的 MCP 工具清单选择直接回答、向用户澄清或调用具体工具；工具结果会回传给 Agent，支持受配置上限约束的多轮工具调用。监控 API 与 Kubernetes 工具尚未注册，不应视为已交付能力。

## 2. 技术栈

| 层 | 技术 | 用途 |
|---|---|---|
| 前端 | Vue 3、Vite、Element Plus | 单页管理与聊天界面 |
| 后端 API | FastAPI、Uvicorn | REST API、WebSocket 聊天 |
| Agent | LangGraph、LangChain | 问题分类、检索路由和回答生成 |
| 检索 | LlamaIndex | 文档读取、切分、向量索引与检索 |
| 向量数据库 | Milvus | collection 管理及向量持久化 |
| Embedding | OpenAI 兼容接口 | 文本向量生成，默认配置为 qwen3-vl-embedding、2048 维 |
| LLM | OpenAI 兼容接口 | Agent 分类和回答生成 |
| MCP | FastMCP | 本地 stdio 与远程 Streamable HTTP 工具连接 |
| 本地数据 | SQLite | 用户、会话 token、应用配置、文档与文本 chunk 元数据 |

## 3. 主要模块

```text
src/opsweave/
├── api/
│   ├── main.py              # FastAPI 应用与路由注册
│   ├── auth.py              # API / WebSocket 身份与角色校验
│   ├── user_store.py        # SQLite 用户与会话
│   ├── agents.py            # LangGraph Agent
│   └── routes/              # health、users、chat、config、knowledge、retrieval
├── auth/permissions.py      # 角色与资源权限规则
├── config/                  # Settings 与 SQLite 配置存储
├── llm/                     # LLM 客户端
├── retrieval/               # Embedding、Milvus store、Retriever
└── tools/                   # MCP 客户端与服务端
frontend/                   # Vue 3 + Vite 前端
tests/                       # API 测试
```

## 4. 请求与数据流

### 聊天

1. 前端通过 WebSocket `/api/chat/ws/chat` 建立连接，使用登录 session cookie 认证。
2. Agent 动态发现 MCP 工具并将工具名、描述和参数 schema 提供给 LLM。
3. LLM 决定回答、澄清或调用工具清单中的 `tool_id`；Agent 将该 ID 映射回 MCP Client 内部保存的 Server 与工具，再执行并将结果回传，循环至回答/澄清或达到最大迭代次数。本地内置 Server 通过 stdio 子进程连接，管理员配置的远程 Server 通过 Streamable HTTP 连接。
4. WebSocket 发送 `thinking`、每次工具调用对应的 `tool`，随后发送 `answer` 或 `clarify`，最后发送 `done`。

### 知识库文档

1. 用户选择 Milvus collection 并上传文件；新上传文档进入 `uploaded` 状态，仅上传者可见，管理员列表不显示尚未申请的文档。
2. 用户选择切分策略提交索引申请后进入 `pending`，管理员可筛选用户、collection 和状态，并批准或拒绝；申请人在批准前可撤销申请。
3. 管理员批准申请或管理员本人直接开始构建后，文档立即进入 `processing`，索引任务在后台执行。页面轮询状态，完成后显示 `completed`，失败则显示 `failed` 及错误信息。
4. 后端读取文档、切分文本、生成 embedding 并将节点按 collection schema 的字段写入 Milvus；直接写入后按节点 ID 核验。摘要策略会先通过 LLM 生成用于 embedding 的摘要文本。
5. 文档状态、chunk 文本和所有者信息存入 SQLite；向量存储于 Milvus。申请撤销后回到 `uploaded`，拒绝、失败可重新提交。

## 5. 身份与权限

系统角色为 `admin`、`ops_engineer`、`viewer`。Web 登录通过 HttpOnly `opsweave_session` cookie 维护会话；部分 API 也支持配置的 Bearer token。普通用户只能查看和操作自己的文档；管理员可查看已申请或开始处理的文档并审批，未申请（`uploaded`）的文档不出现在管理员列表。普通用户可在待审批阶段撤销申请。配置管理和直接构建索引要求管理员角色。检索前还会检查 `RETRIEVAL_INDEX` 权限。

MCP 服务使用独立 `MCP_TOKEN` 验证调用，并要求提供已认证的用户标识。生产部署需限制 CORS 来源并妥善配置认证凭据。

## 6. 当前 API 路由

| 路径 | 用途 |
|---|---|
| `/api/health/ping` | 健康检查 |
| `/api/auth/*` | 注册、登录、登出、当前用户、管理员用户列表 |
| `/api/retrieval/search` | 知识库向量检索 |
| `/api/retrieval/build` | 管理员构建或连接索引 |
| `/api/chat/ws/chat` | WebSocket Agent 对话 |
| `/api/config/*` | 管理员配置、连通性测试、Milvus collection 管理 |
| `/api/knowledge/*` | collection/策略查询、上传、申请、审批、文档与 chunk 管理 |

## 7. 当前边界与后续工作

- 监控系统 API 和 Kubernetes 操作工具尚未实现。
- Agent 支持动态发现 MCP 工具、选择具体工具、将结果回传后继续决策；复杂任务拆解仍未实现。
- Embedding 最大输入 token 上限无法通过 OpenAI 兼容接口通用发现，由管理员在配置页按模型文档手动设置；索引前按 LlamaIndex tokenizer 校验每个切分块。语义切分也有预切分安全上限，避免单块超过嵌入上限。
- `GET /api/knowledge/status` 会实时检查 Milvus 连接、collection 必需字段及向量维度；可通过 `collection_name` 指定检查目标。
- 继续完善 API/前端测试，并根据实际生产部署方式补充部署编排、CORS 白名单和服务监控。
