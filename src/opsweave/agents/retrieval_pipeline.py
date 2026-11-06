"""LangGraph-based direct retrieval pipeline.

`/api/retrieval/search` 不经过聊天 Agent，由本管道独立编排：
连接索引 →（可选）问题分解 → 向量检索与合并去重 →（可选）重排。
问题分解、重排与混合检索节点为后续扩展预留。
"""

from __future__ import annotations

import threading
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from ..auth.permissions import Role
from ..config.settings import get_settings
from ..retrieval.retriever import Retriever

DEFAULT_COLLECTION = "opsweave"

_index_cache: dict[str, Retriever] = {}
_index_lock = threading.Lock()
_pipeline = None


class RetrievalState(TypedDict, total=False):
    """直连检索管道状态。"""

    query: str
    role: Role
    user_id: str
    top_k: int
    collection_name: str
    options: dict[str, bool]
    sub_queries: list[str]
    raw_results: list[dict[str, str | float]]
    results: list[dict[str, str | float]]


def clear_retrieval_index_cache(collection_name: str | None = None) -> None:
    """清空直连检索索引缓存；Milvus/Embedding 配置或集合变更后调用。

    Args:
        collection_name: 仅清空指定 collection 的缓存；为空时清空全部。
    """
    with _index_lock:
        if collection_name:
            _index_cache.pop(collection_name, None)
        else:
            _index_cache.clear()


def _ensure_index(collection_name: str) -> Retriever:
    """获取指定 collection 已连接的索引，缺失时构建并缓存。"""
    with _index_lock:
        retriever = _index_cache.get(collection_name)
    if retriever is None:
        retriever = Retriever()
        retriever.build_index(collection_name=collection_name)
        with _index_lock:
            retriever = _index_cache.setdefault(collection_name, retriever)
    return retriever


def _options(state: RetrievalState) -> dict[str, bool]:
    return state.get("options") or {}


def _connect_index(state: RetrievalState) -> dict:
    """连接或构建目标 collection 的检索索引。"""
    collection_name = state.get("collection_name") or DEFAULT_COLLECTION
    _ensure_index(collection_name)
    return {"collection_name": collection_name}


def _decompose(state: RetrievalState) -> dict:
    """问题分解节点（预留）。当前直接透传原问题；后续接入 LLM 分解为多个子问题。"""
    return {"sub_queries": [state["query"]]}


def _search(state: RetrievalState) -> dict:
    """逐子问题执行向量检索，合并去重并按相似度排序。

    非管理员由 Retriever 按 user_id 过滤；混合检索（向量 + 关键词融合）
    预留在本节点内扩展。
    """
    top_k = state.get("top_k") or get_settings().retriever_top_k
    retriever = _ensure_index(state.get("collection_name") or DEFAULT_COLLECTION)
    best: dict[tuple[str, str], dict[str, str | float]] = {}
    for sub_query in state.get("sub_queries") or [state["query"]]:
        for item in retriever.retrieve(
            query=sub_query, top_k=top_k, role=state["role"], user_id=state["user_id"]
        ):
            key = (item.source, item.text)
            existing = best.get(key)
            if existing is None or item.score > existing["score"]:
                best[key] = {
                    "text": item.text,
                    "score": round(item.score, 4),
                    "source": item.source,
                }
    raw_results = sorted(best.values(), key=lambda item: item["score"], reverse=True)
    return {"raw_results": raw_results, "results": raw_results[:top_k]}


def _rerank(state: RetrievalState) -> dict:
    """重排节点（预留）。当前按相似度透传并截取 top_k；后续接入 LLM/交叉编码器重排。"""
    top_k = state.get("top_k") or get_settings().retriever_top_k
    results = sorted(
        state.get("raw_results", []), key=lambda item: item["score"], reverse=True
    )
    return {"results": results[:top_k]}


def _after_connect(state: RetrievalState) -> str:
    if _options(state).get("decompose"):
        return "decompose"
    return "search"


def _after_search(state: RetrievalState) -> str:
    if _options(state).get("rerank"):
        return "rerank"
    return "end"


def _build_graph():
    graph = StateGraph(RetrievalState)
    graph.add_node("connect_index", _connect_index)
    graph.add_node("decompose", _decompose)
    graph.add_node("search", _search)
    graph.add_node("rerank", _rerank)
    graph.add_edge(START, "connect_index")
    graph.add_conditional_edges(
        "connect_index", _after_connect, {"decompose": "decompose", "search": "search"}
    )
    graph.add_edge("decompose", "search")
    graph.add_conditional_edges(
        "search", _after_search, {"rerank": "rerank", "end": END}
    )
    graph.add_edge("rerank", END)
    return graph.compile()


def run_retrieval_pipeline(
    query: str,
    role: Role,
    user_id: str,
    top_k: int | None = None,
    collection_name: str = DEFAULT_COLLECTION,
    options: dict[str, bool] | None = None,
) -> RetrievalState:
    """执行直连检索管道并返回最终状态。

    Args:
        query: 用户的自然语言检索问题。
        role: 调用者角色，用于权限检查。
        user_id: 已认证用户名，非管理员按其过滤检索结果。
        top_k: 返回条数；缺省使用配置默认值。
        collection_name: Milvus collection 名称。
        options: 管道开关，当前支持 decompose、rerank（预留占位）。

    Returns:
        包含 results（按相关性排序的检索结果）的管道状态。
    """
    global _pipeline
    if _pipeline is None:
        _pipeline = _build_graph()
    return _pipeline.invoke(
        {
            "query": query,
            "role": role,
            "user_id": user_id,
            "top_k": top_k or get_settings().retriever_top_k,
            "collection_name": collection_name,
            "options": options or {},
        }
    )
