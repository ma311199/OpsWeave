"""Embedding client for OpenAI-compatible embedding APIs.

Provides a LlamaIndex BaseEmbedding adapter for DashScope qwen3-vl-embedding
and similar OpenAI-compatible /embeddings endpoints.
"""

from __future__ import annotations

import httpx
from llama_index.core.embeddings import BaseEmbedding
from pydantic import Field

from ..config.settings import get_settings


class OpenAICompatEmbedding(BaseEmbedding):
    """LlamaIndex BaseEmbedding backed by an OpenAI-compatible /embeddings API.

    Compatible with DashScope qwen3-vl-embedding and similar services.
    """

    base_url: str = Field(description="OpenAI-compatible embedding base URL")
    api_key: str = Field(description="API key for authentication")
    model: str = Field(description="Embedding model name")
    dimension: int = Field(default=2048, description="Vector dimension")
    timeout: float = Field(default=60.0, description="Request timeout in seconds")

    @classmethod
    def from_settings(cls) -> OpenAICompatEmbedding:
        """Create instance from environment settings."""
        s = get_settings()
        # Auto-append /embeddings if the base URL doesn't end with it
        base_url = s.embedding_base_url.rstrip("/")
        if not base_url.endswith("/embeddings"):
            base_url = f"{base_url}/embeddings"
        return cls(
            base_url=base_url,
            api_key=s.embedding_api_key,
            model=s.embedding_model,
            dimension=s.embedding_dimension,
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

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        # 向兼容端点发送批量输入，并统一校验返回条数和向量维度。
        response = httpx.post(
            self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "input": texts,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        embeddings = [item["embedding"] for item in data["data"]]
        self._validate_embeddings(embeddings, len(texts))
        return embeddings

    async def _aembed_batch(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": texts,
                },
            )
            response.raise_for_status()
            data = response.json()
        embeddings = [item["embedding"] for item in data["data"]]
        self._validate_embeddings(embeddings, len(texts))
        return embeddings

    def _validate_embeddings(self, embeddings: list[list[float]], expected_count: int) -> None:
        if len(embeddings) != expected_count:
            raise ValueError(f"Expected {expected_count} embeddings, received {len(embeddings)}")
        if any(len(embedding) != self.dimension for embedding in embeddings):
            raise ValueError(f"Embedding dimension does not match configured dimension {self.dimension}")
