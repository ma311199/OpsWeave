# 知识库 RAG 全流程文档

> 最后更新：2026-11-20
> 适用范围：文档上传 → 解析 → 分词 → 切分 → 向量化 → 写入 Milvus → 检索 的完整链路。
> 维护约定：流程、参数或实现变更时，同步更新本文对应章节，并在文末「问题与变更记录」追加一条。

## 1. 总览

```
上传(原始文件)                     审批(策略+参数)
   │                                  │
   ▼                                  ▼
data/documents/{owner}/   ────►  _process_document(document_id)
                                      │
                     ┌────────────────┼─────────────────┐
                     ▼                ▼                 ▼
            ① 解析              ② 分词器          ③ 切分(策略)
        SimpleDirectoryReader   get_tokenizer()   LlamaIndex / langchain
                     │                │                 │
                     └────────────────┴────────┬────────┘
                                               ▼
                                    ④ token 上限校验
                                    embedding_max_tokens
                                               ▼
                                    ⑤ 向量化 get_text_embedding
                                    自动协议探测 /embeddings|/chat/completions
                                               ▼
                                    ⑥ 写 Milvus(幂等) + 核验 + SQLite 元数据
                                               ▼
检索：/api/retrieval/search 或 Agent 的 search_knowledge
      query → 同一 Embedding 客户端向量化 → Milvus top_k → 权限过滤 → 合并去重
```

核心代码位置：

| 阶段 | 代码 |
|---|---|
| 上传 / 审批 / 构建 | `src/opsweave/api/routes/knowledge.py` |
| 分词器 | `src/opsweave/retrieval/tokenization.py` |
| Embedding 客户端与协议探测 | `src/opsweave/retrieval/embeddings.py` |
| Milvus 向量存储 | `src/opsweave/retrieval/vector_store.py` |
| 检索器 | `src/opsweave/retrieval/retriever.py` |
| 直连检索管道 | `src/opsweave/agents/retrieval_pipeline.py` |
| 配置项 | `src/opsweave/config/settings.py`、`config/database.py` |

## 2. 阶段一：上传与解析

### 2.1 上传

- 接口：`POST /api/knowledge/upload?collection_name=...`。
- 先校验目标 collection 存在于 Milvus，再保存文件到 `data/documents/{owner}/{document_id}_{filename}`。
- SQLite `knowledge_documents` 初始状态 `uploaded`；用户提交 `strategy/chunk_size/...` 后进入 `pending`，管理员批准后后台构建。
- 前端上传框 `accept=".txt,.md,.pdf,.docx,.json,.yaml,.yml,.csv"`。

### 2.2 解析

构建时由 `_process_document()` 执行：

```python
loaded = SimpleDirectoryReader(input_files=[doc["path"]]).load_data()
```

- 产出 LlamaIndex `Document` 列表，每个文件至少 1 个 `Document`，正文在 `.text`。
- 纯文本类（`.txt/.md/.json/.yaml/.yml/.csv` 等）由默认文本读取器直接读取，无需额外依赖。
- `.pdf/.docx` 需要额外依赖（`llama-index-readers-file` / `pypdf` / `docx2txt`），**当前环境未安装**，上传后构建会在解析阶段失败。
  需要支持时安装对应依赖即可，切分逻辑无需修改。
- 解析阶段不做额外清洗（不剥离页眉页脚、不做 OCR）。

## 3. 阶段二：分词（token 口径）

切片长度、上限校验、后续展示都统一走 `tokenization.py`，保证「切片用的 token」和「Embedding 模型看到的 token」尽量一致。

### 3.1 优先级

| 优先级 | 来源 | 说明 |
|---|---|---|
| 1 | 本地 `tokenizer.json` | 由配置项 `embedding_tokenizer_path` 指定；填文件本身或其所在目录均可（目录下需有 `tokenizer.json`） |
| 2 | `tiktoken cl100k_base` | 未配置或加载失败时的回退；对中文是近似值 |

- 依赖：`tokenizers` 包（已在 `pyproject.toml` 声明）。
- 加载失败的典型日志：`加载分词器失败`、`未安装 tokenizers`，此时静默回退 cl100k，构建不会中断。
- 路径在保存配置时校验（`validate_tokenizer_path`），非法路径直接返回 400。

### 3.2 两个调用视图

LlamaIndex 切分器要求 `tokenizer(text)` 返回 **token 列表**（内部执行 `len(tokenizer(text))`），而 langchain 的 `length_function` 与上限校验需要 **int**，因此提供两个函数：

| 函数 | 返回 | 使用方 |
|---|---|---|
| `get_tokenizer()` | `list[str]` | LlamaIndex `TokenTextSplitter` / `SentenceSplitter` |
| `get_token_counter()` | `int` | langchain `RecursiveCharacterTextSplitter(length_function=...)`、`embedding.count_tokens()` |

两者共享同一份分词器实例（进程内缓存，配置保存后自动失效）。

### 3.3 口径差异实测

同一句「运维知识库系统需要对设备告警进行归因分析并生成处置建议。」：

| 分词器 | token 数 |
|---|---|
| bge-m3 本地 `tokenizer.json` | 20 |
| tiktoken `cl100k_base` | 28（偏多 40%） |

结论：使用非 OpenAI 系 Embedding 模型时，务必配置对应的 `tokenizer.json`，否则块大小和上限校验都会失真。

### 3.4 测试连接时的分词接口校准

Embedding「测试连接」在协议探测成功后，会额外探测服务端 `POST {base}/tokenize`：

- 依次尝试 vLLM（`{"model","prompt"}`）与 TEI（`{"inputs"}`）两种请求体；兼容 `count` / `tokens` / 裸列表三种响应。
- 服务端不提供（404/403/超时）：提示「服务端未提供分词接口（/tokenize）」，不影响 Embedding 测试成功。
- 提供：用固定中英混合样本比对服务端 token 数与当前分词器的 token 数：
  - 未配置本地分词器 → 提示偏差并建议配置；
  - 已配置且偏差 ≤5% → 提示「校验一致」；
  - 偏差 >5% → 提示双方 token 数，提醒确认分词器文件与模型是否匹配。
- 该校准**只在测试连接时执行**，运行期切片不会调用 `/tokenize`，无网络开销。

## 4. 阶段三：切分策略

八种策略，参数来自用户「配置切分策略」弹窗，写入 `knowledge_documents`：

| id | 名称 | 切分器 | 边界依据 | 块大小依据 | overlap |
|---|---|---|---|---|---|
| `fixed` | 固定长度 | `TokenTextSplitter` | 空格 → 换行 → 字符 | token | 固定 0 |
| `sliding` | 滑动窗口 | `TokenTextSplitter` | 同上 | token | 用户配置 |
| `sentence` | 句子级 | `SentenceSplitter` | 句子边界 | token | 用户配置 |
| `paragraph` | 段落级 | `RecursiveCharacterTextSplitter` | 正则 `\n\n` → `\n` → 空串 | token（`length_function`） | 用户配置 |
| `recursive` | 递归 | `RecursiveCharacterTextSplitter` | 段落/换行/中英文句末标点逐级回退 | token | 用户配置 |
| `structure` | 结构化 | `RecursiveCharacterTextSplitter` | markdown/html/latex 标题或块标签 → 句末标点 | token | 用户配置 |
| `semantic` | 语义 | `SentenceSplitter` 预切分 + `SemanticSplitterNodeParser` | 句子 + Embedding 断点（百分位阈值） | token | 预切分 0 |
| `summary` | 摘要（LLM） | `SentenceSplitter` + LLM | 句子边界 | token | 用户配置 |

补充说明：

- **段落/递归/结构化** 的切分**边界**是按字符/正则定位的，但**块大小上限**仍由 token 数控制（`length_function=get_token_counter()`），因此仍依赖分词器。
- **语义切分**：先用 `SentenceSplitter` 以 `semantic_max_chunk_size`（默认 2048，overlap=0）兜底切分，再用 `SemanticSplitterNodeParser`（`buffer_size=1`，`breakpoint_percentile_threshold=semantic_threshold`，默认 95）按 Embedding 相似度断句；会额外产生 Embedding 请求。
- **摘要切分**：对每个基础块调用 LLM 生成 `title/summary/keywords`（JSON），`embedding_text = 标题 + 摘要 + 关键词 + 原文`，写入 Milvus 的 `text` 字段仍是原文，`embedding_text` 存 SQLite 供查看。
- 参数约束：`overlap < chunk_size`（接口层 `validate_overlap`）；默认 `chunk_size=512`、`chunk_overlap=64`。
- 目前**没有**「纯字符计数、完全不使用分词器」的策略。若需要（例如按固定字符数切分以适配特殊模型），应新增策略或在切分器中改用 `length_function=len`，避免隐式改变现有策略口径。

## 5. 阶段四：向量化

实现：`OpenAICompatEmbedding`（`retrieval/embeddings.py`，继承 LlamaIndex `BaseEmbedding`）。

### 5.1 接口协议自动探测

按顺序尝试，首个成功者生效：

1. 标准 `POST /embeddings`（OpenAI 格式，`input` 为字符串数组）
2. 多模态 `POST /embeddings`（`input` 为 `{"text": ...}`，附带 `parameters.dimension / enable_fusion`）
3. `POST /chat/completions`（纯文本兼容接口）

- 探测结果按 `(base_url, model, dimension)` 进程内缓存；「测试连接」使用 `force=True` 重新探测；修改配置后清空缓存。
- 响应维度必须等于 `embedding_dimension`，否则报「接口可用但向量维度不匹配」。
- 单候选网络异常不会中断整体探测，最多重试 2 次并汇总异常信息。
- TLS：`verify=settings.verify_ssl`（配置页「网络与安全」开关，等同 `curl -k`；更安全做法是 `SSL_CERT_FILE` 信任企业 CA）。

### 5.2 构建时的调用方式

- 逐块调用 `embedding.get_text_embedding(embed_text)`，**构建阶段不做批量请求**（探测到的 `supports_batch` 仅影响探测判定）。
- `embed_text` = 原文（`summary` 策略为「标题+摘要+关键词+原文」）。
- 每块先做上限校验：

```python
token_count = embedding.count_tokens(embed_text)
if token_count > max_tokens:  # max_tokens = DB 配置 embedding_max_tokens，默认 8192
    raise ValueError("第 N 个文本块超过 Embedding 模型最大输入限制：x > y tokens")
```

超限直接失败，不会写入任何向量，便于定位问题块。

## 6. 阶段五：写入 Milvus 与元数据

写入字段：`id`（= LlamaIndex node ID = SQLite chunk id）、`document_id`、`text`、`vector`、`user_id`、`filename`。

幂等重建流程（防止失败重试产生重复数据）：

1. `MilvusClient.delete(collection, filter='document_id == "..."')` 删除该文档旧向量；
2. `insert`；
3. `flush`；
4. `load_collection`（新建集合默认未加载，查询前必须 load）；
5. `get(ids=...)` 回查核验数量；
6. 删除并重写 SQLite `knowledge_chunks`，状态置 `completed`。

维度约束：collection 的 `vector` 字段维度必须与 `embedding_dimension` 一致（例如 1024）。不一致会在写入时报 `the dim (x) of field data(vector) is not equal to schema dim (y)`。

SQLite 结构：

- `knowledge_documents`：状态机 `uploaded → pending → completed / failed`（可撤销 pending）。
- `knowledge_chunks`：`text`（写入 Milvus 的原文）与 `embedding_text`（实际向量化文本，摘要策略下二者不同）。

## 7. 阶段六：检索

### 7.1 直连检索

`POST /api/retrieval/search`（`query`, `top_k`）→ `run_retrieval_pipeline`：

```
connect_index（按 collection 缓存 Retriever）
   └─(可选) decompose（占位，当前透传原问题）
        └─ search：逐子查询 Milvus 向量检索 → 按 (source,text) 合并去重取最高分 → 截取 top_k
             └─(可选) rerank（占位，当前按相似度排序截取）
```

- 查询向量化复用同一个 `OpenAICompatEmbedding`（同一套协议探测与分词器配置）。
- 权限：管理员不过滤；其他角色按 `user_id` 元数据过滤，只能检索自己的文档。无 `RETRIEVAL_INDEX` 权限直接拒绝。
- `top_k` 默认 `retriever_top_k=5`（`1–20`）。
- `score` 为 Milvus 相似度（collection 使用 `COSINE`），越大越相关。
- Retriever 按 collection 进程内缓存；修改 Milvus/Embedding 配置、删除集合时清空缓存。

### 7.2 Agent 聊天中的检索

本地 MCP Server 的 `search_knowledge` 工具同样调用 `Retriever`（`src/opsweave/tools/mcp_server.py`），Agent 通过工具调用走相同的向量化与权限过滤流程。

### 7.3 重排（Reranker）

- 配置页已支持 Reranker 连接测试（`/rerank` 优先，`/chat/completions` 回退）。
- 直连检索管道的 `rerank` 节点目前是占位：只按相似度排序，**尚未真正调用 Reranker**。

## 8. 当前部署配置（2026-11-20 实测，不含密钥与内网地址）

| 配置项 | 当前值 | 说明 |
|---|---|---|
| `embedding_model` | `bge-m3-0.5B-changcheng:...` | 内网 bge-m3 服务 |
| `embedding_dimension` | 1024 | Milvus collection 必须为 1024 维 |
| `embedding_max_tokens` | 4000 | 单块上限，超限构建失败 |
| `embedding_tokenizer_path` | `D:\bge-m3-tokenizer` | 目录内含 `tokenizer.json` |
| `verify_ssl` | `false` | 内网自签名证书，等同 `curl -k` |
| `retriever_top_k` | 5（默认） | 检索返回条数 |
| `chunk_size / chunk_overlap` | 512 / 64（默认） | 构建时按文档单独配置 |
| `semantic_max_chunk_size` | 2048（默认） | 语义切分预切分上限 |
| `semantic_threshold` | 95（默认） | 语义断点百分位 |
| Reranker | 已配置、未启用 | 检索管道占位 |
| `tokenizers` | 0.23.3 | 已安装 |
| 可用解析格式 | 纯文本类 | `.pdf/.docx` 缺依赖，暂不可用 |

> Embedding / Milvus 的具体 URL、数据库名、密钥以管理员「系统配置」页为准；密钥不落库（仅进程环境变量），本文不记录。

## 9. 问题与变更记录

| 日期 | 问题 | 原因 | 处理 |
|---|---|---|---|
| 2026-11 | 切片 token 口径不一致 | `fixed/sentence/semantic/summary` 用 tiktoken，`paragraph/recursive/structure` 用 langchain 默认 gpt2 | 统一走 `tokenization.py`，所有策略传入同一分词器 |
| 2026-11 | 中文 token 数失真（cl100k 比 bge-m3 多 40%） | 用 OpenAI 分词器估算非 OpenAI 模型的 token | 支持本地 `tokenizer.json`，配置页 Embedding 区块可填路径 |
| 2026-11 | 测试连接结果与分词器口径脱节 | 只测了向量接口 | 测试连接增加 `/tokenize` 抽样校准（vLLM/TEI） |
| 2026-11 | 超长块导致 Embedding 400 | 未按模型上限校验 | 构建前逐块校验 `embedding_max_tokens`，超限明确报错 |
| 2026-11 | `Document object has no attribute 'get_content'` | langchain 切分器返回 langchain Document | 统一转换 `LIDocument(text=chunk.page_content)`，读取兼容 `.text` |
| 2026-11 | Milvus `dim (1024) != schema dim (2048)` | collection schema 与当前模型维度不符 | 按 `embedding_dimension` 重建 collection |
| 2026-11 | `collection not loaded` | 新建 collection 未加载 | `flush` 后 `load_collection` 再回查 |
| 2026-11 | 失败重试后数据重复 | 重试未清理旧向量/chunks | 插入前按 `document_id` 删除 Milvus 向量与 SQLite chunks |
| 2026-11 | 上传后文档从列表消失 | 管理员列表 SQL 过滤了 `uploaded` | 移除该过滤条件 |
| 2026-11 | 修改 SSL 开关后 LLM/Reranker 反而失败 | `verify` 参数取反 | 统一 `verify=settings.verify_ssl` |
| 2026-11 | 测试连接仍用旧 Key | 测试读后端已保存配置 | 测试前先静默保存表单 |
| 2026-11 | 部分网关 `/embeddings` 不可用 | 内网网关只挂了 `/v1/chat/completions` | 协议自动探测并回退 |

## 10. 待改进

- [ ] 纯字符切分策略（`length_function=len`），适配不按 token 计数的场景。
- [ ] 构建阶段批量 Embedding 请求（当前逐块请求，文档多时偏慢）。
- [ ] 直连检索的重排节点接入已配置的 Reranker。
- [ ] `.pdf/.docx` 解析依赖（`llama-index-readers-file`、`pypdf`、`docx2txt`）按需引入。
- [ ] 混合检索（向量 + 关键词）与问题分解节点落地。
