# OpsWeave API 文档

后端默认由 FastAPI 提供服务。REST 路径以 `/api` 开头；需要登录的接口使用 `opsweave_session` cookie，部分接口也接受 Bearer token。管理员接口要求 `admin` 角色。具体错误响应遵循 FastAPI 的 HTTP 错误格式。

## 1. 认证 `/api/auth`

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/register` | 公开 | 注册账号；用户名 3–64 字符，密码 8–256 字符 |
| POST | `/login` | 公开 | 登录，设置 HttpOnly session cookie；返回用户名与角色 |
| POST | `/logout` | 登录 | 注销 session 并清除 cookie |
| GET | `/me` | 登录 | 获取当前用户名与角色 |
| GET | `/users` | 管理员 | 列出用户 |

注册请求示例：

```json
{"username":"alice","password":"a-long-password"}
```

## 2. 健康检查

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health/ping` | 返回服务存活状态 |

## 3. 检索 `/api/retrieval`

### `POST /search`

需要登录及 `RETRIEVAL_INDEX` 权限。请求字段：`query`（字符串）、`top_k`（1–20，默认 5）。按当前用户身份执行检索过滤，返回 `query` 与 `results`；每项包含 `text`、`score`、`source`。

### `POST /build`

管理员专用。查询参数：`documents_path`（可选）、`collection_name`（默认 `opsweave`）。构建或连接索引，返回状态、collection 和 `ready`。

## 4. 聊天 WebSocket `/api/chat/ws/chat`

使用登录 session cookie；也支持通过 WebSocket subprotocol `bearer.<token>` 传入 token。客户端发送一条 JSON 文本消息：

```json
{"query":"如何排查数据库连接超时？"}
```

服务端依次发送 JSON 消息：`thinking`，每次 MCP 调用对应一个 `tool`（包含实际工具名），随后发送 `answer` 或 `clarify`，最后发送 `done`；异常时发送 `error`。Agent 将动态发现的 MCP 工具清单交给 LLM 决策，并可在收到工具结果后继续调用工具，直到回答、澄清或达到迭代上限。

## 5. 知识库 `/api/knowledge`

所有接口均要求登录。普通用户仅能查看和操作自己的文档；管理员可跨用户查看并审批。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/collections` | 列出当前 Milvus 数据库的 collections、描述与实体数 |
| GET | `/strategies` | 返回句子、Token 窗口、语义切分选项及当前 Embedding 最大 token 数 |
| POST | `/upload?collection_name={name}` | multipart 上传文件并绑定目标 collection |
| GET | `/documents` | 列出当前用户文档；管理员列出已申请或处理中的文档，不展示 `uploaded` 状态的未申请文档 |
| POST | `/documents/{document_id}/apply` | 提交索引申请，请求体含 `strategy`、`chunk_size`、`overlap` 等切分参数；普通用户提交后进入 `pending`，管理员提交后立即进入 `processing` 并后台构建 |
| POST | `/documents/{document_id}/cancel-application` | 申请人撤销 `pending` 状态申请，撤销后回到 `uploaded`；仅本人可撤销，管理员及非待审批状态返回错误 |
| GET | `/applications` | 列出当前用户待审批申请；管理员查看全部待审批申请 |
| POST | `/applications/{document_id}/review` | 管理员审批，请求体 `{"approve":true}` 或 `false`；批准后立即返回 `processing`，索引在后台运行 |
| GET | `/documents/{document_id}/chunks` | 查看文档切分结果 |
| DELETE | `/documents/{document_id}` | 删除文档及其索引数据；pending/processing 状态不能删除 |
| GET | `/status?collection_name={name}` | 检查 Milvus 连接、collection 必需字段和向量维度；返回 `ready`、`schema_valid`、`schema_errors`、实际/期望向量维度、collection 列表与文档数。未指定 collection 时遍历 collection 列表，任一符合要求的 collection 即视为就绪 |

支持的切分方式：

| ID | 实现 | 参数 |
|---|---|---|
| `sentence` | LlamaIndex `SentenceSplitter`，优先按句子边界切分 | `chunk_size`、`overlap`（Token） |
| `token` | LlamaIndex `TokenTextSplitter`，Token 滑动窗口 | `chunk_size`、`overlap`（Token） |
| `semantic` | LlamaIndex `SemanticSplitterNodeParser`，按语义变化分段 | `semantic_max_chunk_size` 为预切分安全上限；`chunk_size`、`overlap` 仍作为校验/保存参数 |

管理员在 `/api/config/` 中配置 `embedding.max_tokens`，默认 8192。该限制无法从 OpenAI 兼容 Embedding API 通用查询，需按实际模型服务文档设置。处理时使用 LlamaIndex tokenizer 统计每个最终 embedding 文本的 token 数；任一块超过上限即停止索引、将文档标记为 `failed` 并返回超限块信息，不会自动二次拆分。

普通用户申请后状态变为 `pending`，管理员批准后立即返回并异步处理，状态转为 `processing`；管理员本人直接开始构建也会进入 `processing`。前端在处理期间轮询文档状态，完成、拒绝或失败状态会显示在文档列表中。管理员文档列表默认不包含尚未申请的 `uploaded` 文档，并支持按用户、collection 和状态筛选。待审批申请可由申请人撤销，撤销后恢复 `uploaded`。

## 6. 配置 `/api/config`

此路由组要求管理员角色。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/config/` | 读取 LLM、Embedding、Milvus、Agent 配置；密钥会掩码显示 |
| PUT | `/api/config/` | 更新配置并保存到 SQLite；Embedding 配置含 `max_tokens` 上限 |
| POST | `/api/config/test/{service}` | 测试 `llm`、`embedding` 或 `milvus` 连接 |
| GET | `/api/config/milvus/collections` | 列出 Milvus collections 与 schema 信息 |
| POST | `/api/config/milvus/create-collection` | 创建 collection |
| PUT | `/api/config/milvus/collections/{name}` | 更新 collection 描述 |
| DELETE | `/api/config/milvus/collections/{name}` | 删除 collection |

配置读写涵盖 LLM、Embedding、Milvus、Agent 及 collection 定义。详细请求字段以 FastAPI OpenAPI schema 为准。

## 7. MCP 工具

FastMCP 服务端在 `opsweave.tools.mcp_server` 暴露 MCP 工具。Agent 通过 MCP Client 动态获取工具名称、描述和参数 schema，再由 LLM 选择具体工具并传递参数；每次调用附加已认证用户标识和 `MCP_TOKEN`。当前注册的知识搜索工具为 `search_knowledge`，参数 `query`、`top_k`（1–20）、`user_id`、`token`，结果包含 `source`、`score`、`text`。MCP 传输由 FastMCP 配置决定，不属于 `/api` REST 路由。

## 8. Python 模块接口

### 配置

```python
from opsweave.config.settings import get_settings
settings = get_settings()
```

`Settings` 包含 LLM、检索、Milvus、Embedding、Agent、认证 token 和 `data_dir` 配置。数据库配置覆盖项通过 `get_settings()` 加载并缓存；配置更新后 API 会清理缓存。

### 权限

```python
from opsweave.auth.permissions import PermissionChecker, ResourceType, Role
checker = PermissionChecker.default_rules()
checker.is_allowed(Role.OPS_ENGINEER, ResourceType.RETRIEVAL_INDEX)
checker.require(Role.VIEWER, ResourceType.MONITORING_API)
```

角色：`ADMIN`、`OPS_ENGINEER`、`VIEWER`。资源类型包括 `RETRIEVAL_INDEX`、`MONITORING_API`、`K8S_CLUSTER`、`SECRET_STORE`。

### 检索

```python
from opsweave.retrieval.retriever import Retriever
from opsweave.auth.permissions import Role

retriever = Retriever()
retriever.build_index(collection_name="opsweave")
results = retriever.retrieve(query="数据库连接超时", top_k=5, role=Role.ADMIN)
```

`retrieve()` 支持按 `user_id` 过滤结果；`RetrievalResult` 含 `text`、`score`、`source`。更多参数和配置参见实现及 `docs/architecture.md`。
