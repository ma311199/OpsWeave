# OpsWeave 开发指南

## 1. 环境准备

### 安装 Python

需要 Python 3.11 或更高版本。使用 `uv` 管理 Python 版本：

```bash
uv python install 3.12
```

### 安装项目依赖

```bash
cd OpsWeave
uv sync
```

### 配置环境变量

复制 `.env.example` 为 `.env` 并填写实际配置：

```bash
cp .env.example .env
```

必须配置的项：

| 配置项 | 说明 |
|---|---|
| `LLM_BASE_URL` | LLM API 地址（OpenAI 兼容） |
| `LLM_API_KEY` | LLM API Key |
| `LLM_MODEL` | 模型名称 |
| `MILVUS_URI` | Milvus 服务地址 |
| `MILVUS_USER` | Milvus 用户名 |
| `MILVUS_PASSWORD` | Milvus 密码 |
| `EMBEDDING_BASE_URL` | Embedding API 地址 |
| `EMBEDDING_API_KEY` | Embedding API Key |
| `EMBEDDING_MODEL` | Embedding 模型名称 |

## 2. 项目结构

```
OpsWeave/
├── .env                  # 环境变量（不入库）
├── .env.example          # 环境变量模板
├── .python-version       # Python 版本
├── pyproject.toml        # 项目配置与依赖
├── main.py               # 入口文件
├── src/opsweave/         # 源代码
│   ├── __init__.py
│   ├── auth/             # 权限隔离
│   ├── config/           # 配置管理
│   ├── llm/              # LLM 客户端
│   ├── retrieval/        # 检索引擎
│   ├── tools/            # 外部工具
│   ├── agents/           # Agent 决策循环
│   └── ui/               # Gradio 界面
├── docs/                 # 技术文档
│   ├── architecture.md
│   ├── code_standards.md
│   ├── development.md
│   ├── api.md
│   └── deployment.md
└── tests/                # 测试代码（待创建）
```

## 3. 本地开发

### 启动开发服务器

```bash
uv run main.py
```

### 运行代码检查

```bash
uv run ruff format --check .
uv run ruff check .
```

### 自动修复代码风格

```bash
uv run ruff format .
uv run ruff check --fix .
```

## 4. 构建与打包

```bash
uv build
```

生成的包在 `dist/` 目录下。

## 5. 测试

### 编写测试

在 `tests/` 目录下创建测试文件，使用 `pytest`：

```python
import pytest
from opsweave.retrieval.retriever import Retriever

def test_retriever_initialization():
    retriever = Retriever()
    assert retriever.is_ready is False
```

### 运行测试

```bash
uv run pytest tests/ -v
```

## 6. 文档编写

- 架构设计：`docs/architecture.md`
- 代码规范：`docs/code_standards.md`
- API 文档：`docs/api.md`
- 开发指南：`docs/development.md`（本文件）
- 部署文档：`docs/deployment.md`

## 7. 常见开发任务

### 新增检索工具

1. 在 `retrieval/` 下创建新文件
2. 实现检索逻辑，返回 `RetrievalResult` 列表
3. 在 `__init__.py` 中导出
4. 更新 `docs/api.md`

### 新增外部工具

1. 在 `tools/` 下创建新文件
2. 实现工具调用逻辑
3. 在 `PermissionChecker` 中添加权限规则
4. 更新 `docs/architecture.md`

### 修改 Agent 决策逻辑

1. 在 `agents/` 下修改状态图
2. 调整节点间的数据流
3. 更新 `docs/architecture.md`

## 8. 调试技巧

### 查看日志

在 `main.py` 中配置日志级别：

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 连接 Milvus 调试

```bash
uv run python -c "
from opsweave.retrieval.vector_store import get_milvus_store
store = get_milvus_store()
print('Milvus connected:', store)
"
```

### 测试 Embedding API

```bash
uv run python -c "
from opsweave.retrieval.embeddings import OpenAICompatEmbedding
e = OpenAICompatEmbedding.from_settings()
vector = e.get_query_embedding('test query')
print('Vector dimension:', len(vector))
"
```

## 9. 版本管理

- 使用 `pyproject.toml` 中的 `version` 字段管理版本
- 遵循语义化版本（Semantic Versioning）：
  - `MAJOR.MINOR.PATCH`
  - `MAJOR`：不兼容的 API 变更
  - `MINOR`：向后兼容的功能新增
  - `PATCH`：向后兼容的问题修复
