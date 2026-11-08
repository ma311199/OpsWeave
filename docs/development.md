# OpsWeave 开发指南

## 1. 环境准备

需要 Python 3.11 或更高版本、`uv`，前端开发还需要 Node.js 与 npm。项目依赖由 `pyproject.toml` 和 `frontend/package.json` 管理。

```powershell
uv sync
Set-Location frontend
npm install
```

后端配置通过环境变量、根目录 `.env` 及部分 SQLite 配置覆盖项加载。首次启动前可配置 LLM、Embedding 和 Milvus 参数；敏感密钥不要提交到版本库。管理员初始密码及角色 token 等认证项请参照 `src/opsweave/config/settings.py`。

## 2. 项目结构

```text
OpsWeave/
├── src/opsweave/
│   ├── agents/              # LangGraph 编排（直连检索管道）
│   ├── api/                 # FastAPI、认证、Agent 与 API routes
│   ├── auth/                # 权限模型
│   ├── config/              # Settings、SQLite 配置
│   ├── llm/                 # LLM 客户端
│   ├── retrieval/           # Embedding、Milvus、Retriever
│   └── tools/               # MCP 客户端与服务端
├── frontend/                # Vue 3 + Vite 前端
├── tests/                   # API 测试
├── docs/                    # 项目文档
├── start.bat                # Windows 本地启动脚本
└── stop.bat                 # Windows 本地停止脚本
```

## 3. 本地启动

Windows 可在项目根目录运行：

```powershell
.\start.bat
```

脚本检查 `uv` 和前端依赖后启动后端 `127.0.0.1:8000`，等待健康检查通过再启动 Vite（默认 `127.0.0.1:5173`；端口占用时使用 5174）。停止服务可运行：

```powershell
.\stop.bat
```

也可分开启动：

```powershell
uv run python -m uvicorn opsweave.api.main:app --host 127.0.0.1 --port 8000
```

另开终端运行前端：

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

后端健康检查为 `http://127.0.0.1:8000/api/health/ping`。API 路由和 WebSocket 协议见 `docs/api.md`。

## 4. 代码检查与测试

```powershell
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/ -v
```

前端生产构建：

```powershell
Set-Location frontend
npm run build
```

测试使用 pytest 与 FastAPI TestClient；外部依赖按测试需要 mock。当前测试覆盖知识库 API 和检索 API，修改认证、权限、索引或文档状态流程时应同步补充测试。

## 5. 开发约定

- 新增 API 时放入 `src/opsweave/api/routes/`，并在 `api/main.py` 注册路由。
- 访问受保护资源时复用 `api/auth.py` 和 `auth/permissions.py` 的认证/授权机制。
- 用户文档与 chunk 元数据保存在 SQLite，向量写入 Milvus；需保持所有者过滤和 collection 关联行为。
- 配置项应同步维护 `config/settings.py`、配置 API 与相关前端表单。
- 修改接口行为时更新 `docs/api.md`；修改模块边界或数据流时更新 `docs/architecture.md`。

## 6. 当前主要功能

- 账号注册、登录、登出及管理员用户列表。
- 基于 LangGraph 的聊天路由：直接回答、内部检索或 MCP 知识库搜索。
- 基于 LangGraph 的直连检索管道（`/api/retrieval/search`）：连接索引、检索合并去重，预留问题分解/重排/混合检索扩展节点。
- Milvus 检索与管理员索引构建。
- 文档上传、切分策略选择、管理员审批、索引处理、chunk 查看和删除。
- 管理员 LLM、Embedding、Milvus、Agent 配置及服务连通性测试。
