# OpsWeave 代码规范

## 1. Python 版本与风格

- **Python 版本**：>= 3.11，使用类型注解语法（`list[str]` 而非 `List[str]`）
- **格式化**：使用 `ruff format`（由 `uv` 管理）
- **Lint**：使用 `ruff check`
- **代码风格**：遵循 PEP 8，行宽 100

### 运行检查

```bash
uv run ruff format --check .
uv run ruff check .
uv run ruff format .
uv run ruff check --fix .
```

## 2. 导入顺序

```python
from __future__ import annotations

# 标准库
import httpx
from typing import Any

# 第三方库
from llama_index.core import VectorStoreIndex
from pydantic import Field

# 本地模块
from ..config.settings import get_settings
```

## 3. 命名约定

| 类型 | 规则 | 示例 |
|---|---|---|
| 模块/文件 | `snake_case` | `vector_store.py` |
| 类 | `PascalCase` | `OpenAICompatEmbedding` |
| 函数/方法 | `snake_case` | `get_milvus_store()` |
| 常量 | `UPPER_SNAKE_CASE` | `EMBEDDING_DIMENSION` |
| 类型变量 | `PascalCase` | `T` |
| 私有成员 | `_leading_underscore` | `_embed_batch()` |

## 4. 类型注解

所有函数签名必须包含完整类型注解：

```python
def retrieve(
    self,
    query: str,
    top_k: int | None = None,
    role: Role = Role.ADMIN,
) -> list[RetrievalResult]:
```

使用 `from __future__ import annotations` 以获得更灵活的注解语法。

## 5. 文档字符串

所有公共类、函数、方法必须有 docstring：

```python
def retrieve(
    self,
    query: str,
    top_k: int | None = None,
    role: Role = Role.ADMIN,
) -> list[RetrievalResult]:
    """Retrieve relevant document chunks for a query.

    Args:
        query: Natural language query.
        top_k: Number of results to return. Defaults to settings value.
        role: Caller's role, checked against permission rules.

    Returns:
        List of RetrievalResult sorted by relevance.
    """
```

## 6. 配置管理

- 所有配置项通过 `pydantic-settings` 的 `Settings` 类管理
- 新增配置项需同步更新 `settings.py` 和 `.env`
- 敏感信息（API Key、密码）只存在于 `.env` 文件，不入库

## 7. 错误处理

- 检索和工具调用失败时抛出具体异常，不要静默吞掉错误
- 权限检查失败时抛出 `PermissionError`
- 外部 API 调用需要设置合理的 `timeout`

```python
if not self.is_ready:
    raise RuntimeError("Retriever index not built. Call build_index() first.")
```

## 8. 模块组织原则

- 每个模块只负责单一职责
- 模块间通过明确的接口交互，避免循环依赖
- `retrieval/` 不依赖 `api/` 或 Agent 编排层，API/Agent 可调用检索模块
- 需要授权的资源操作应在 API、Agent 或工具边界执行相应权限检查；公共服务连通性测试等不涉及用户资源授权的调用无需强行经过 `PermissionChecker`

## 9. 测试约定

- 测试文件放在 `tests/` 目录下
- 测试函数以 `test_` 开头
- 使用 `pytest` 框架
- 优先使用 mock 模拟外部依赖

## 10. Git 提交规范

建议使用 Conventional Commits：

```
<type>(<scope>): <description>

feat: 新增 Milvus 向量存储支持
fix: 修复 embedding URL 拼接问题
docs: 更新架构设计文档
refactor: 重构权限检查器
```

常用 type：
- `feat` — 新功能
- `fix` — Bug 修复
- `docs` — 文档变更
- `refactor` — 代码重构
- `test` — 测试相关
- `chore` — 构建/工具变更
