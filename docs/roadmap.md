# OpsWeave 项目进度与阶段规划

> 更新日期：2026-11-06
> 版本：0.1.0
> 本文档基于对 `docs/` 现有文档与代码库实际实现的交叉核对编写。功能状态以代码为准，文档与代码不一致处已在第 4 节列出。

## 1. 项目定位

OpsWeave 是面向运维场景的 Agentic RAG 系统：用户通过聊天向 LangGraph Agent 提问，Agent 基于动态发现的 MCP 工具自主决策，检索 Milvus 中的运维知识库，并对高风险工具调用执行人工审批。

技术栈：

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+、FastAPI、LangGraph、LangChain（OpenAI 兼容）、FastMCP 2、LlamaIndex、pymilvus、pydantic-settings |
| 前端 | Vue 3.5、Vite 6、Element Plus 2.9、vue-router 4、axios |
| 存储 | SQLite（用户/会话/配置/文档元数据/聊天记录/审批记录）、Milvus（向量）、本地文件（原始文档与长期记忆） |
| 质量 | ruff（format + lint）、pytest |

## 2. 总体阶段划分

| 阶段 | 主题 | 状态 |
|---|---|---|
| 阶段 0 | MVP：认证、知识库 RAG、Agent + MCP + 审批闭环 | 基本完成（遗留少量缺陷） |
| 阶段 1 | 稳定化：修复缺陷、补齐依赖与测试、对齐文档 | **下一阶段（推荐）** |
| 阶段 2 | Agent 与聊天体验：多会话、流式输出、审批续跑、MCP 连接复用 | 未开始 |
| 阶段 3 | 运维工具生态：只读监控/K8s 诊断工具、工具级权限与审计 | 未开始 |
| 阶段 4 | 生产化部署：容器化、CI、配置收敛、可观测性、数据备份 | 未开始 |
| 阶段 5 | RAG 增强：混合检索/重排、引用溯源、评测、更多文件格式 | 未开始 |

## 3. 阶段 0 已完成内容（MVP）

### 3.1 认证与权限

- 注册、登录、登出、`/me`、管理员用户列表（`src/opsweave/api/routes/users.py`）。
- PBKDF2-SHA256（31 万轮）密码哈希；session token 以 SHA-256 哈希入库，HttpOnly Cookie，7 天有效期；同时支持 Bearer token 与 WebSocket `bearer.<token>` 子协议。
- 三级角色 `admin / ops_engineer / viewer` × 四类资源（检索、监控 API、K8s、密钥库）的 `PermissionChecker`（`src/opsweave/auth/permissions.py`）。
- 管理员账号通过 `ADMIN_INITIAL_PASSWORD` 引导初始化。

### 3.2 系统配置

- 环境变量 + SQLite 覆盖项的两级配置，更新后清理 settings 缓存（`src/opsweave/config/`）。
- 管理员配置 API：LLM / Embedding / Milvus / Agent / 远程 MCP Server 的读写，密钥掩码返回。
- LLM、Embedding、Milvus 连通性测试；Milvus collection 的增删改查与字段 Schema 校验（前端约束 id/vector/text/user_id/document_id/filename 六个必需字段）。
- 前端「系统配置」页五个标签页（`frontend/src/views/ConfigView.vue`）。

### 3.3 知识库

- 文档上传并绑定 collection；按用户隔离文件与元数据，管理员可跨用户查看。
- 八种切分策略（`src/opsweave/api/routes/knowledge.py`）：
  - `fixed` / `sliding`：Token 固定/滑动窗口
  - `sentence`：句子边界切分
  - `paragraph` / `recursive` / `structure`（markdown/html/latex）：基于 langchain-text-splitters 的递归切分
  - `semantic`：LlamaIndex 语义切分（带预切分上限与阈值）
  - `summary`：LLM 生成标题/摘要/关键词后拼接入 embedding 文本
- 完整审批流：上传 → 申请（`pending`）/ 管理员直接构建（`processing`）→ 批准/拒绝/撤销 → 后台构建 → `completed` / `failed`。
- 入库前逐块校验 embedding token 上限（管理员可配置，默认 8192），超限即终止并标记 `failed`，不自动二次拆分。
- Milvus 写入后按 ID 回查核验；chunk 文本与元数据存 SQLite；删除文档时级联清理文件、SQLite、Milvus 向量。
- `/status` 就绪检查：Milvus 连接、必需字段、向量维度；前端轮询文档状态，支持按用户/collection/状态筛选。

### 3.4 检索

- LlamaIndex `VectorStoreIndex` + Milvus 向量库（`src/opsweave/retrieval/`）。
- 非管理员按 `user_id` 元数据过滤，仅能检索自己的文档；OpenAI 兼容 Embedding 适配器，返回向量数与维度强校验。

### 3.5 Agent、MCP 与工具审批

- LangGraph 状态机（`src/opsweave/api/agents.py`）：`decide → tool_call → decide` 循环，支持直接回答、澄清、工具调用、迭代上限。
- 工具清单按 `tool_id` 编号暴露给 LLM，不暴露 Server ID；注入短期对话历史与用户长期记忆。
- 本地 stdio FastMCP Server 提供 `search_knowledge` 工具（携带用户身份与 MCP_TOKEN）；支持管理员配置远程 Streamable HTTP MCP Server 并合并工具清单（`src/opsweave/tools/mcp_client.py`）。
- 仅当工具 `annotations.readOnlyHint === true` 时直接执行，其余一律写入 SQLite 待审批；发起人或管理员可在 `/api/approvals` 处理，批准后后端同步执行，审批状态持久化、禁止重复处理。
- WebSocket 聊天协议（`/api/chat/ws/chat`）：`thinking / tool / approval_required / clarify / answer / done / error`；前端聊天页内可直接批准/拒绝并展示执行结果。

### 3.6 记忆

- 短期记忆：SQLite `chat_messages`，按用户 + `conversation_id` 隔离，每会话保留最近 40 条。
- 长期记忆：`data/documents/{username}/memory.md`，聊天时可附 `remember` 字段显式追加。

### 3.7 前端与工程化

- 四个页面：Agent Chat、知识库检索、知识库管理（含审批、切分配置、chunk 查看）、系统配置；登录/注册卡片与顶栏导航。
- `start.bat` / `stop.bat` 一键启动后端（8000）与 Vite（5173/5174），含健康检查等待。
- 文档 5 篇（架构、API、部署、开发指南、代码规范）；pytest 测试 7 个文件。

## 4. 阶段 0 遗留问题（已在代码中核实）

| # | 问题 | 位置/证据 | 影响 |
|---|---|---|---|
| 1 | `langchain_text_splitters` 被直接 import，但未在 `pyproject.toml` 声明，干净环境中 `ModuleNotFoundError` | `src/opsweave/api/routes/knowledge.py:213` | paragraph/recursive/structure 三种切分策略运行即崩 |
| 2 | `/api/retrieval/search` 新建 `Retriever()` 后未调用 `build_index()`，`is_ready` 恒为 False，被 `RuntimeError` 捕获后固定返回 503 | `src/opsweave/api/routes/retrieval.py:32-36` | 知识库检索页与 MCP 之外的直连检索实际不可用；现有测试因 mock 了 Retriever 未暴露此问题 |
| 3 | `tests/test_memory_store.py` 失败：测试直接删 `chat_messages` 表，但未先触发建表（建表是惰性的） | 实测 `pytest`：26 passed, 1 failed | 测试红灯 |
| 4 | 端口文档不一致：文档写后端 8001，`start.bat`、Vite 代理、main.py 默认均为 8000 | `docs/deployment.md` vs `start.bat:24`、`frontend/vite.config.js:23` | 按文档手动启动会代理失败 |
| 5 | API 文档只记录 3 种切分策略，代码实际 8 种 | `docs/api.md:67-71` vs knowledge.py | 文档漂移 |
| 6 | 每次聊天都重新 `asyncio.run` 拉起本地 MCP Server 子进程并发现工具 | `src/opsweave/tools/mcp_client.py:104-105` | 每轮对话额外的进程启动开销与失败面 |
| 7 | 审批通过后经独立 REST 调用执行工具，原聊天轮次已结束，执行结果不会回到原对话上下文 | `src/opsweave/api/routes/approvals.py` + `routes/chat.py:61-65` | 审批后的工具结果不会驱动 Agent 继续作答 |
| 8 | 密钥策略冲突：代码规范要求密钥只在 `.env`，配置 API 实际把 LLM/Embedding/Milvus 密钥明文写入 SQLite | `docs/code_standards.md:89` vs `config/database.py` | 需明确取舍并补充加密或改为不回存 |
| 9 | `mcp_server.search_knowledge` 内角色硬编码为 VIEWER、collection 硬编码 `opsweave` | `src/opsweave/tools/mcp_server.py:29,39` | 多 collection 知识库无法经 Agent 检索 |
| 10 | 前端缺：多会话/历史浏览、审批中心页、用户管理页、路由守卫；`store/role.js` 基本空置 | `frontend/src/` | 体验与已有后端能力不匹配 |
| 11 | 工程化缺：README 为空、无 CI、无 Dockerfile/编排、CORS 为 `*` + credentials、LLM 非流式 | 仓库根目录、`api/main.py:21-27` | 仅限本地开发，不可公网使用 |

## 5. 阶段 1：稳定化计划（建议作为下一阶段）

目标：让 MVP 全链路真正可用、测试全绿、文档可信。预计为小工作量、高收益的收尾迭代。

### 5.1 缺陷修复（P0）

1. 补依赖：在 `pyproject.toml` 增加 `langchain-text-splitters`（与当前 LlamaIndex/LangChain 版本兼容的约束），`uv sync` 后验证三种递归类切分策略。
2. ~~修复直连检索~~ 已完成：`/api/retrieval/search` 改走 LangGraph 直连检索管道（连接索引 → 检索合并去重，预留问题分解/重排/混合检索节点），索引按 collection 缓存并在配置/集合变更时清理；已补回归测试。
3. 修复失败测试：让记忆存储在应用启动或测试 fixture 中显式初始化表，`pytest` 全绿。

### 5.2 一致性与安全（P1）

4. 统一后端端口为 8000（修改文档），或统一为 8001（修改脚本与代理）；二选一后全局对齐。
5. 更新 `docs/api.md`：补齐 8 种切分策略、审批 REST 路由、WebSocket `approval_required` 消息等实际协议。
6. 明确密钥落库策略：方案 A 为密钥仅存 `.env`/环境变量、SQLite 只存非敏感项；方案 B 为保留现状但用本机密钥加密。默认建议方案 A。
7. 收紧 CORS 配置为可配置的可信来源列表。

### 5.3 测试与工程（P1）

8. 补充测试：配置路由（含掩码/连通性测试 mock）、认证全流程、审批执行路径、知识库 8 种策略的切分参数校验。
9. 编写最小 README（定位、快速开始、文档索引）。
10. 增加 CI 工作流：`ruff format --check` + `ruff check` + `pytest` + 前端 `npm run build`。

验收标准：`pytest` 全绿、ruff 无告警、前端构建通过；上传→申请→批准→检索→Agent 问答主链路在真实 Milvus/LLM 环境手动走通一遍。

## 6. 后续阶段规划

### 阶段 2：Agent 与聊天体验

- 会话管理：会话列表/新建/重命名/删除的 API 与前端 UI，历史消息分页加载。
- LLM 输出与工具事件实时流式推送（当前为整轮结束后一次性返回）。
- 审批续跑：审批通过后工具结果回到 Agent 上下文继续推理，而不是结束轮次；待审批状态断线重连与提醒。
- MCP Client 连接复用与缓存（本地 Server 常驻、远程 Server 连接池、失败超时与降级）。
- `search_knowledge` 支持按用户可选 collection 检索。

### 阶段 3：运维工具生态

- 接入只读监控类 MCP 工具（日志/指标/告警查询），映射到 `MONITORING_API` 权限；K8s 只读诊断映射到 `K8S_CLUSTER`。
- 管理端按「工具 × 角色」配置自动放行/必须审批策略，替代单一 `readOnlyHint` 规则。
- 工具调用与审批的审计日志页面。

### 阶段 4：生产化部署

- Dockerfile 与 docker-compose（后端、前端静态资源/反代、Milvus）、`.env.example`。
- SQLite 备份指引与轻量 schema 迁移机制；健康检查细化（依赖项状态）。
- 结构化日志、基础指标、登录与调用限流；CORS/HTTPS/会话安全按部署文档收口。

### 阶段 5：RAG 能力增强

- 混合检索（向量 + 关键词）、重排、查询改写；回答引用溯源到具体 chunk/文档。
- 检索质量评测集与回归流程；扩展 PDF/DOCX 等格式的解析依赖校验与重建索引策略。

## 7. 下一阶段开发内容（阶段 1 任务清单）

按建议顺序执行：

1. `pyproject.toml` 补 `langchain-text-splitters` 并验证切分策略（修复问题 1）。
2. ~~修复 `/api/retrieval/search` 未建索引缺陷并加回归测试~~（问题 2，已完成：直连检索已改走 LangGraph 管道，见 5.1 第 2 条）。
3. 修复 `test_memory_store.py` 失败（问题 3）。
4. 统一端口文档/脚本配置（问题 4）。
5. 更新 `docs/api.md` 至与实现一致（问题 5、审批路由、WS 协议）。
6. 确定密钥存储策略并实施（问题 8），同步收紧 CORS（问题 11）。
7. 补齐配置/认证/审批测试，编写 README，添加 CI。
