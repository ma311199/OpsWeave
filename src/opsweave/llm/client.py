"""LLM client factory (OpenAI-compatible)."""

from __future__ import annotations

import httpx
from langchain_openai import ChatOpenAI

from ..config.settings import get_settings


def get_llm() -> ChatOpenAI:
    """Return a ChatOpenAI client configured via env vars."""
    settings = get_settings()
    kwargs: dict = {}
    if not settings.verify_ssl:
        # 内网自签名证书场景（等同 curl -k），同步/异步客户端都需跳过验证
        kwargs["http_client"] = httpx.Client(verify=False)
        kwargs["http_async_client"] = httpx.AsyncClient(verify=False)
    return ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        **kwargs,
    )
