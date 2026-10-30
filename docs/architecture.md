# OpsWeave 架构设计文档

## 1. 概述

OpsWeave 是一个面向运维场景的 Agentic RAG 系统，核心目标是让 Agent 能够自主决策：

- **直接回答** — 常识性问题无需检索
- **分解检索** — 复杂问题拆解后通过 LlamaIndex + Milvus 检索知识库
- **调用工具** — 调用监控 API 等外部系统获取实时数据

## 2. 技术栈

| 层 | 技术 | 用途 |
|---|---|---|
| Agent 决策循环 | LangGraph | 状态图驱动的多步决策 |
| 检索引擎 | LlamaIndex | 文档分块、向量索引、检索 |
| 向量数据库 | Milvus | 持久化向量存储 |
| Embedding | qwen3-vl-embedding | OpenAI 兼容接口，2048 维 |
| LLM | Spark X2.6 | OpenAI 兼容接口 |
| Web UI | Gradio | 原型演示与验证 |
| 配置管理 | pydantic-settings | 环境变量 + .env 文件 |

## 3. 模块结构

```
src/opsweave/
├── __init__.py
├── auth/           # 权限隔离
│   └── permissions.py
├── config/         # 配置管理
│   └── settings.py
├── llm/            # LLM 客户端
│   └── client.py
├── retrieval/      # 检索引擎
│   ├── embeddings.py
│   ├── vector_store.py
│   └── retriever.py
├── tools/          # 外部工具（待开发）
├── agents/         # LangGraph 决策循环（待开发）
└── ui/             # Gradio 界面（待开发）
```

## 4. 数据流

```
用户输入
  │
  ▼
┌─────────────┐
│  LangGraph  │  Agent 决策循环
│  StateGraph │
└───┬───┬─────┘
    │   │
    ▼   ▼
 ┌─────────────┐    ┌──────────────┐
 │ 直接回答    │    │ 分解检索      │
 │ (LLM)       │    │ (Retriever)   │
 └─────────────┘    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │    Milvus    │
                    │  (向量检索)   │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ 监控 API      │
                    │ (Tool Call)  │
                    └──────────────┘
                           │
                           ▼
                        用户
```

## 5. 权限模型

系统采用基于角色的访问控制（RBAC），三层角色：

| 角色 | 检索 | 监控 API | K8s 集群 | 密钥存储 |
|---|---|---|---|---|
| admin | ✅ | ✅ | ✅ | ✅ |
| ops_engineer | ✅ | ✅ | ❌ | ❌ |
| viewer | ✅ | ❌ | ❌ | ❌ |

所有检索和工具调用必须经过 `PermissionChecker.require()` 进行权限校验。

## 6. 检索流程

1. `Retriever.build_index()` 连接 Milvus collection
2. 如提供 `documents_path`，使用 `SimpleDirectoryReader` 加载文档
3. `SentenceSplitter` 按配置的 chunk_size / chunk_overlap 分块
4. 调用 Embedding API 生成向量并写入 Milvus
5. `retrieve()` 时将 query 编码为向量，在 Milvus 中做相似度搜索

## 7. 待开发模块

### 7.1 agents/ — LangGraph 决策循环

需要实现的状态图节点：

- **classify** — 判断问题类型（直接回答 / 需要检索 / 需要工具）
- **answer** — 直接由 LLM 生成回答
- **decompose** — 复杂问题拆解为子问题
- **retrieve** — 调用 Retriever 检索知识库
- **tool_call** — 调用外部工具（如监控 API）
- **synthesize** — 汇总检索结果和工具输出，生成最终回答

### 7.2 tools/ — 外部工具

- `monitoring.py` — 监控 API 客户端（Prometheus / Zabbix 等）
- `k8s.py` — Kubernetes API 封装（需 admin 权限）

### 7.3 ui/ — Gradio 界面

- 聊天界面，支持流式输出
- 角色选择（admin / ops_engineer / viewer）
- 检索结果可视化展示
