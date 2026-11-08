# OpsWeave 部署与运行

## 1. 运行依赖

| 组件 | 要求 | 用途 |
|---|---|---|
| Python | >= 3.11 | FastAPI 后端与 Agent |
| uv | 当前项目依赖管理工具 | 安装及运行 Python 项目 |
| Node.js / npm | 与 Vite 6 兼容 | 安装、构建和运行 Vue 前端 |
| Milvus | 可访问的 Milvus 服务 | 向量检索与知识库 collection |
| LLM API | OpenAI 兼容接口 | Agent 分类、回答及摘要策略 |
| Embedding API | OpenAI 兼容接口 | 文本向量生成 |

## 2. 安装

```powershell
uv sync
Set-Location frontend
npm install
```

在项目根目录配置 `.env` 或部署环境变量。配置字段及默认值以 `src/opsweave/config/settings.py` 为准，主要包含：

- `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`、`LLM_TEMPERATURE`
- `EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`、`EMBEDDING_MODEL`、`EMBEDDING_DIMENSION`
- `embedding_max_tokens` 在管理员配置页设置（默认 8192）；该值须按实际 embedding 模型文档手动填写
- `MILVUS_URI`、`MILVUS_USER`、`MILVUS_PASSWORD`、`MILVUS_DATABASE`
- `DATA_DIR`、`ADMIN_INITIAL_PASSWORD`、角色 token 与 `MCP_TOKEN`

非敏感应用设置可在管理员配置页面修改并保存到 `DATA_DIR/opsweave.db`；LLM、Embedding、Milvus 密钥只从环境变量或 `.env` 加载，不保存到 SQLite。密钥不得提交到版本库；请为生产环境使用独立凭据。

## 3. 本地启动

Windows 在项目根目录执行：

```powershell
.\start.bat
```

脚本启动后端于 `127.0.0.1:8000`，健康检查成功后启动前端 Vite，默认地址为 `127.0.0.1:5173`；若 5173 被非 Vite 程序占用则使用 5174。停止脚本：

```powershell
.\stop.bat
```

手动启动后端：

```powershell
uv run python -m uvicorn opsweave.api.main:app --host 127.0.0.1 --port 8000
```

手动启动前端：

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

健康检查端点：`GET /api/health/ping`。FastAPI OpenAPI 文档通常可在后端 `/docs` 查看。

## 4. 生产构建

构建前端静态资源：

```powershell
Set-Location frontend
npm run build
```

生产运行应由适合部署环境的进程管理器分别托管 ASGI 后端和前端静态资源/反向代理。当前仓库提供本地 Windows 启动脚本；没有提供已验证的 Dockerfile 或生产编排配置，不要直接依赖开发服务器作为公网生产服务。

生产环境建议：

- 将 Uvicorn 绑定到受控网络接口，并由反向代理提供 HTTPS。
- 通过 `CORS_ALLOW_ORIGINS` 设置逗号分隔的可信前端来源列表；默认仅允许本地 Vite 开发地址。
- 设置强认证凭据及 `MCP_TOKEN`，限制管理员与 MCP 服务访问。
- 将 `DATA_DIR` 指向持久化目录并做好 SQLite 备份；Milvus 按其自身策略备份。
- 确保后端能够访问 Milvus、LLM 与 Embedding 服务。

## 5. 知识库索引

通过前端上传和申请审批流程向 collection 写入文档。管理员也可通过受保护接口 `POST /api/retrieval/build` 连接或构建索引；参数包括可选 `documents_path` 和 `collection_name`。collection 的创建、字段及索引管理由管理员配置页面/API执行，collection schema 必须满足当前检索实现要求。

知识库文档文件和元数据位于 `DATA_DIR` 下；向量数据保存在 Milvus。删除或迁移数据前应同时考虑两处存储。

## 6. 故障排查

- **后端未启动**：确认 `uv sync` 已完成，并检查后端窗口的配置或依赖错误。
- **前端未启动**：确认已在 `frontend` 目录运行 `npm install`，且端口 5173/5174 可用。
- **Milvus 连接失败**：检查 URI、凭据、数据库名称及网络连通性。
- **Embedding 请求失败**：检查 API 地址、密钥、模型名称和向量维度。
- **LLM 请求失败**：检查兼容 API 地址、密钥和模型名称。
- **用户无法访问资源**：确认 session cookie 有效；访问管理员配置和索引构建需要管理员角色。
- **索引申请失败**：在知识库文档状态中检查 `error` 信息，并确认 collection 存在且字段与向量维度匹配。
