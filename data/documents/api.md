# OpsWeave API 文档

## 1. 配置模块 `config.settings`

### Settings

应用配置，通过环境变量或 `.env` 文件加载。

```python
from opsweave.config.settings import Settings, get_settings
```

#### 字段

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `llm_base_url` | `str` | `https://api.openai.com/v1` | LLM API 地址 |
| `llm_api_key` | `str` | `sk-xxx` | LLM API Key |
| `llm_model` | `str` | `gpt-4o-mini` | 模型名称 |
| `llm_temperature` | `float` | `0.2` | 采样温度 |
| `retriever_top_k` | `int` | `5` | 检索返回条数 |
| `retriever_chunk_size` | `int` | `512` | 文档分块大小 |
| `retriever_chunk_overlap` | `int` | `64` | 分块重叠大小 |
| `milvus_uri` | `str` | `http://localhost:19530` | Milvus 地址 |
| `milvus_user` | `str` | `` | Milvus 用户名 |
| `milvus_password` | `str` | `` | Milvus 密码 |
| `milvus_database` | `str` | `default` | 数据库名 |
| `embedding_base_url` | `str` | DashScope | Embedding API 地址 |
| `embedding_api_key` | `str` | `` | Embedding API Key |
| `embedding_model` | `str` | `qwen3-vl-embedding` | Embedding 模型 |
| `embedding_dimension` | `int` | `2048` | 向量维度 |
| `agent_max_iterations` | `int` | `8` | Agent 最大迭代次数 |
| `data_dir` | `Path` | `./data` | 数据目录 |

#### 函数

**`get_settings() -> Settings`**

获取缓存的 Settings 实例。

```python
from opsweave.config.settings import get_settings
settings = get_settings()
print(settings.llm_model)
```

---

## 2. 权限模块 `auth.permissions`

### Role

```python
class Role(str, Enum):
    ADMIN = "admin"
    OPS_ENGINEER = "ops_engineer"
    VIEWER = "viewer"
```

### ResourceType

```python
class ResourceType(str, Enum):
    RETRIEVAL_INDEX = "retrieval_index"
    MONITORING_API = "monitoring_api"
    K8S_CLUSTER = "k8s_cluster"
    SECRET_STORE = "secret_store"
```

### PermissionChecker

```python
from opsweave.auth.permissions import PermissionChecker, Role, ResourceType

checker = PermissionChecker.default_rules()
checker.is_allowed(Role.OPS_ENGINEER, ResourceType.RETRIEVAL_INDEX)  # True
checker.require(Role.VIEWER, ResourceType.MONITORING_API)  # Raises PermissionError
```

#### 方法

| 方法 | 签名 | 说明 |
|---|---|---|
| `default_rules()` | `() -> PermissionChecker` | 创建默认权限检查器 |
| `is_allowed(role, resource)` | `(Role, ResourceType) -> bool` | 检查权限 |
| `require(role, resource)` | `(Role, ResourceType) -> None` | 校验权限，失败抛异常 |

---

## 3. LLM 模块 `llm.client`

### get_llm

```python
from opsweave.llm.client import get_llm

llm = get_llm()
```

返回 `ChatOpenAI` 实例，基于 `settings.py` 中的配置。

---

## 4. 检索模块 `retrieval`

### OpenAICompatEmbedding

LlamaIndex `BaseEmbedding` 适配器，调用 OpenAI 兼容的 Embedding API。

```python
from opsweave.retrieval.embeddings import OpenAICompatEmbedding

# 从环境变量创建
embedding = OpenAICompatEmbedding.from_settings()

# 直接创建
embedding = OpenAICompatEmbedding(
    base_url="https://api.example.com/v1/embeddings",
    api_key="sk-xxx",
    model="qwen3-vl-embedding",
    dimension=2048,
)

# 获取向量
vector = embedding.get_query_embedding("运维知识库检索")
print(len(vector))  # 2048
```

### get_milvus_store

创建 Milvus 向量存储连接。

```python
from opsweave.retrieval.vector_store import get_milvus_store

store = get_milvus_store(collection_name="opsweave")
```

### Retriever

Milvus 检索器封装。

```python
from opsweave.retrieval.retriever import Retriever
from opsweave.auth.permissions import Role

retriever = Retriever()

# 方式一：连接已有 collection
retriever.build_index(collection_name="opsweave")

# 方式二：从文档目录构建新索引
retriever.build_index(
    documents_path="./data/docs",
    collection_name="opsweave",
)

# 检索
results = retriever.retrieve(
    query="如何排查数据库连接超时",
    top_k=5,
    role=Role.ADMIN,
)

for r in results:
    print(f"[{r.score:.3f}] {r.source}: {r.text[:100]}...")
```

#### 方法

| 方法 | 签名 | 说明 |
|---|---|---|
| `build_index(documents_path, collection_name)` | `(str | None, str) -> None` | 构建或连接索引 |
| `retrieve(query, top_k, role)` | `(str, int | None, Role) -> list[RetrievalResult]` | 检索相关文档 |
| `is_ready` | `property -> bool` | 索引是否已就绪 |

### RetrievalResult

```python
@dataclass
class RetrievalResult:
    text: str       # 文档内容
    score: float    # 相似度分数
    source: str     # 来源文件路径
```
