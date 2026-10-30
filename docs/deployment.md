# OpsWeave 部署文档

## 1. 前置条件

| 组件 | 版本要求 | 说明 |
|---|---|---|
| Python | >= 3.11 | 推荐 3.12 |
| Milvus | >= 2.4 | 向量数据库 |
| Embedding API | OpenAI 兼容 | 如 DashScope qwen3-vl-embedding |
| LLM API | OpenAI 兼容 | 如 Spark X2.6 |

## 2. 安装

### 2.1 克隆仓库

```bash
git clone https://github.com/your-org/OpsWeave.git
cd OpsWeave
```

### 2.2 安装 Python

```bash
uv python install 3.12
```

### 2.3 安装项目依赖

```bash
uv sync
```

### 2.4 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件填写实际配置：

```env
# LLM
LLM_BASE_URL=https://maas-api.cn-huabei-1.xf-yun.com/v2
LLM_API_KEY=your-api-key
LLM_MODEL=spark-x2.6
LLM_TEMPERATURE=0.7

# Milvus
MILVUS_URI=http://your-milvus-host:19530
MILVUS_USER=mm
MILVUS_PASSWORD=your-password
MILVUS_DATABASE=opsweave

# Embedding
EMBEDDING_BASE_URL=https://your-embedding-api/v1
EMBEDDING_API_KEY=your-embedding-key
EMBEDDING_MODEL=qwen3-vl-embedding
EMBEDDING_DIMENSION=2048

# Agent
AGENT_MAX_ITERATIONS=8

# Data
DATA_DIR=./data
```

## 3. 构建知识库索引

### 3.1 准备文档

将运维相关文档放入 `./data/docs/` 目录，支持的格式：

- `.txt` / `.md` — 纯文本
- `.pdf` — PDF 文档
- `.docx` — Word 文档
- `.html` — 网页快照

### 3.2 创建索引

```bash
uv run python -c "
from opsweave.retrieval.retriever import Retriever
retriever = Retriever()
retriever.build_index(
    documents_path='./data/docs',
    collection_name='opsweave',
)
print('Index built successfully')
"
```

### 3.3 验证索引

```bash
uv run python -c "
from opsweave.retrieval.retriever import Retriever
retriever = Retriever()
retriever.build_index(collection_name='opsweave')
results = retriever.retrieve('数据库连接超时排查')
print(f'Retrieved {len(results)} results')
"
```

## 4. 运行

### 4.1 开发模式

```bash
uv run main.py
```

Gradio 服务默认运行在 `http://localhost:7860`。

### 4.2 生产部署

#### 方式一：Docker

创建 `Dockerfile`：

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . .
RUN pip install uv && uv sync --frozen

EXPOSE 7860
CMD ["uv", "run", "main.py"]
```

构建并运行：

```bash
docker build -t opsweave .
docker run -d -p 7860:7860 \
  -e LLM_API_KEY=xxx \
  -e MILVUS_URI=http://host.docker.internal:19530 \
  opsweave
```

#### 方式二：直接运行

```bash
uv sync
uv run main.py --host 0.0.0.0 --port 7860
```

## 5. 生产环境注意事项

### 5.1 安全

- `.env` 文件不要入库，使用 CI/CD 注入环境变量
- 限制 API Key 的访问范围
- Milvus 启用 TLS 加密
- 使用反向代理（Nginx）保护 Gradio 端口

### 5.2 性能

- `retriever_top_k` 根据实际需求调整（3-10 之间）
- `retriever_chunk_size` 影响检索精度，建议 256-1024
- Milvus 集群部署时启用分段索引加速检索

### 5.3 监控

- 记录 Agent 决策路径（使用 LangGraph 的 callback）
- 监控 Embedding API 调用延迟和错误率
- 监控 Milvus 连接状态和查询延迟
- 设置 API Key 使用量告警

## 6. 常见问题

### Milvus 连接失败

```
Connection refused → 检查 MILVUS_URI 是否可达
Authentication failed → 检查 MILVUS_USER / MILVUS_PASSWORD
Collection not found → 先运行 build_index() 创建
```

### Embedding API 报错

```
401 Unauthorized → 检查 EMBEDDING_API_KEY
404 Not Found → 检查 EMBEDDING_BASE_URL 是否正确
Dimension mismatch → 检查 EMBEDDING_DIMENSION 与模型实际维度一致
```

### 检索结果质量差

- 增大 `retriever_top_k`
- 调整 `retriever_chunk_size`（更小的块提高精度）
- 检查文档质量（确保分块后的文本有完整语义）

## 7. 升级

```bash
git pull
uv sync
uv run python -c "
from opsweave.retrieval.retriever import Retriever
retriever = Retriever()
retriever.build_index(collection_name='opsweave')
"
uv run main.py
```
