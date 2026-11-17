"""Embedding client with automatic protocol detection.

Supports three embedding API styles without any manual selection:
- Standard OpenAI-compatible POST /embeddings with plain text inputs.
- Multimodal POST /embeddings with object inputs ({text}/{image}) plus a
  parameters block (dimension / enable_fusion), e.g. qwen3-vl-embedding.
- Plain-text embedding via POST /chat/completions.

The endpoint is probed once per (base_url, model, dimension), and the
result is cached in-process for reuse by ingestion and retrieval.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

import httpx
from llama_index.core.embeddings import BaseEmbedding
from pydantic import Field

from ..config.settings import get_settings

PROTOCOL_LABELS = {
    "openai": "/embeddings（标准 OpenAI 格式）",
    "multimodal": "/embeddings（多模态格式）",
    "chat": "/chat/completions",
}

# 探测时发送两条文本：根据返回向量条数校准服务的批量语义
_PROBE_TEXTS = ["连接探测文本一", "连接探测文本二"]


@dataclass
class EmbeddingEndpointInfo:
    """一次成功探测得到的端点协议信息。"""

    url: str  # 完整请求地址
    protocol: str  # openai | multimodal | chat
    supports_batch: bool  # 服务是否支持批量输入
    dimension: int = 0  # 探测实测的向量维度


class EmbeddingProbeError(RuntimeError):
    """端点探测失败，message 可直接展示给用户。"""


_endpoint_cache: dict[tuple[str, str, int], EmbeddingEndpointInfo] = {}
_cache_lock = threading.Lock()


def clear_embedding_endpoint_cache() -> None:
    """清空端点探测缓存（配置变更后由调用方触发）。"""
    with _cache_lock:
        _endpoint_cache.clear()


def _probe_candidates(model: str, dimension: int) -> list[tuple[str, str, dict]]:
    """按优先级返回 (protocol, url_suffix, payload) 探测候选列表。"""
    return [
        (
            "openai",
            "/embeddings",
            {"model": model, "input": list(_PROBE_TEXTS)},
        ),
        (
            "multimodal",
            "/embeddings",
            {
                "model": model,
                "input": [{"text": text} for text in _PROBE_TEXTS],
                "parameters": {"dimension": dimension, "enable_fusion": True},
            },
        ),
        (
            "chat",
            "/chat/completions",
            {"model": model, "input": list(_PROBE_TEXTS)},
        ),
    ]


def _parse_embeddings(data: object) -> list[list[float]]:
    """从多种常见响应格式中解析向量列表。"""
    if not isinstance(data, dict):
        return []
    items = data.get("data")
    if isinstance(items, list) and items:
        first = items[0]
        if isinstance(first, dict) and isinstance(first.get("embedding"), list):
            return [item["embedding"] for item in items]
        if isinstance(first, list):
            return items
    items = data.get("embeddings")
    if isinstance(items, list) and items and isinstance(items[0], list):
        return items
    return []


def _evaluate_response(
    resp: httpx.Response,
    protocol: str,
    url: str,
    expected_dimension: int,
    actual_dimensions: dict[str, int],
) -> EmbeddingEndpointInfo | None:
    """评估单次探测响应：返回端点信息，None 表示继续尝试下一候选。"""
    if resp.status_code == 404:
        return None
    if resp.status_code == 401:
        raise EmbeddingProbeError("API Key 无效或未授权")
    if resp.status_code != 200:
        return None
    try:
        embeddings = _parse_embeddings(resp.json())
    except ValueError:
        return None
    if not embeddings:
        return None
    actual_dimensions[protocol] = len(embeddings[0])
    if len(embeddings[0]) != expected_dimension:
        return None
    return EmbeddingEndpointInfo(
        url=url,
        protocol=protocol,
        supports_batch=len(embeddings) == len(_PROBE_TEXTS),
        dimension=len(embeddings[0]),
    )


def _probe_error_message(actual_dimensions: dict[str, int], dimension: int) -> str:
    if actual_dimensions:
        detail = "、".join(
            f"{PROTOCOL_LABELS.get(protocol, protocol)} 返回 {actual} 维"
            for protocol, actual in actual_dimensions.items()
        )
        return (
            f"接口可用但向量维度不匹配：{detail}，与配置的 {dimension} 维不符，"
            "请调整 Dimension 配置"
        )
    return (
        "无法识别 Embedding 接口：/embeddings 与 /chat/completions 均不可用，"
        "请检查 Base URL 与模型名称"
    )


def _cache_get(key: tuple[str, str, int]) -> EmbeddingEndpointInfo | None:
    with _cache_lock:
        return _endpoint_cache.get(key)


def _cache_put(key: tuple[str, str, int], info: EmbeddingEndpointInfo) -> None:
    with _cache_lock:
        _endpoint_cache[key] = info


def detect_embedding_endpoint(
    base_url: str,
    api_key: str,
    model: str,
    dimension: int,
    timeout: float = 30.0,
    force: bool = False,
) -> EmbeddingEndpointInfo:
    """同步探测可用的 embedding 端点协议，结果进程内缓存。"""
    root = base_url.rstrip("/")
    key = (root, model, dimension)
    if not force:
        cached = _cache_get(key)
        if cached:
            return cached

    actual_dimensions: dict[str, int] = {}
    with httpx.Client(timeout=timeout) as client:
        for protocol, suffix, payload in _probe_candidates(model, dimension):
            url = f"{root}{suffix}"
            resp = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            info = _evaluate_response(resp, protocol, url, dimension, actual_dimensions)
            if info:
                _cache_put(key, info)
                return info
    raise EmbeddingProbeError(_probe_error_message(actual_dimensions, dimension))


async def adetect_embedding_endpoint(
    base_url: str,
    api_key: str,
    model: str,
    dimension: int,
    timeout: float = 30.0,
    force: bool = False,
) -> EmbeddingEndpointInfo:
    """异步探测可用的 embedding 端点协议，结果进程内缓存。"""
    root = base_url.rstrip("/")
    key = (root, model, dimension)
    if not force:
        cached = _cache_get(key)
        if cached:
            return cached

    actual_dimensions: dict[str, int] = {}
    async with httpx.AsyncClient(timeout=timeout) as client:
        for protocol, suffix, payload in _probe_candidates(model, dimension):
            url = f"{root}{suffix}"
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            info = _evaluate_response(resp, protocol, url, dimension, actual_dimensions)
            if info:
                _cache_put(key, info)
                return info
    raise EmbeddingProbeError(_probe_error_message(actual_dimensions, dimension))


class OpenAICompatEmbedding(BaseEmbedding):
    """LlamaIndex BaseEmbedding backed by an auto-detected embedding API.

    The endpoint protocol (standard /embeddings, multimodal /embeddings,
    or /chat/completions) is probed automatically in from_settings() and
    reused for all subsequent requests.
    """

    base_url: str = Field(description="Embedding service base URL")
    api_key: str = Field(description="API key for authentication")
    model: str = Field(description="Embedding model name")
    dimension: int = Field(default=2048, description="Vector dimension")
    timeout: float = Field(default=60.0, description="Request timeout in seconds")
    # 自动探测结果；直接构造实例时保持旧行为（标准 /embeddings + 批量）
    endpoint_url: str | None = Field(
        default=None, description="Probed full request URL"
    )
    protocol: str = Field(
        default="openai", description="openai | multimodal | chat"
    )
    supports_batch: bool = Field(
        default=True, description="Whether the service accepts batch inputs"
    )

    @classmethod
    def from_settings(cls) -> OpenAICompatEmbedding:
        """Create instance from settings, probing the endpoint protocol."""
        s = get_settings()
        info = detect_embedding_endpoint(
            base_url=s.embedding_base_url,
            api_key=s.embedding_api_key,
            model=s.embedding_model,
            dimension=s.embedding_dimension,
        )
        return cls(
            base_url=s.embedding_base_url.rstrip("/"),
            api_key=s.embedding_api_key,
            model=s.embedding_model,
            dimension=s.embedding_dimension,
            endpoint_url=info.url,
            protocol=info.protocol,
            supports_batch=info.supports_batch,
        )

    def count_tokens(self, text: str) -> int:
        """使用 LlamaIndex 当前 tokenizer 估算文本 token 数，供入库前做长度校验。"""
        from llama_index.core.utils import get_tokenizer

        return len(get_tokenizer()(text))

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._embed_batch([query])[0]

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return (await self._aembed_batch([query]))[0]

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._embed_batch([text])[0]

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return self._embed_batch(texts)

    async def _aget_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return await self._aembed_batch(texts)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return (await self._aembed_batch([text]))[0]

    def _request_url(self) -> str:
        return self.endpoint_url or f"{self.base_url}/embeddings"

    def _request_payload(self, texts: list[str]) -> dict:
        if self.protocol == "multimodal":
            return {
                "model": self.model,
                "input": [{"text": text} for text in texts],
                "parameters": {
                    "dimension": self.dimension,
                    "enable_fusion": True,
                },
            }
        return {"model": self.model, "input": texts}

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        if self.supports_batch or len(texts) == 1:
            return self._embed_request(texts)
        # 服务不支持批量输入时自动降级为逐条嵌入
        return [self._embed_request([text])[0] for text in texts]

    async def _aembed_batch(self, texts: list[str]) -> list[list[float]]:
        if self.supports_batch or len(texts) == 1:
            return await self._aembed_request(texts)
        embeddings: list[list[float]] = []
        for text in texts:
            embeddings.append((await self._aembed_request([text]))[0])
        return embeddings

    def _embed_request(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(
            self._request_url(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=self._request_payload(texts),
            timeout=self.timeout,
        )
        response.raise_for_status()
        embeddings = _parse_embeddings(response.json())
        self._validate_embeddings(embeddings, len(texts))
        return embeddings

    async def _aembed_request(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self._request_url(),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=self._request_payload(texts),
            )
            response.raise_for_status()
            data = response.json()
        embeddings = _parse_embeddings(data)
        self._validate_embeddings(embeddings, len(texts))
        return embeddings

    def _validate_embeddings(
        self, embeddings: list[list[float]], expected_count: int
    ) -> None:
        if len(embeddings) != expected_count:
            raise ValueError(
                f"Expected {expected_count} embeddings, received {len(embeddings)}"
            )
        if any(len(embedding) != self.dimension for embedding in embeddings):
            raise ValueError(
                f"Embedding dimension does not match configured dimension {self.dimension}"
            )
