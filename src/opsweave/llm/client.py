"""LLM client factory (OpenAI-compatible)."""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from ..config.settings import get_settings


def get_llm() -> ChatOpenAI:
    """Return a ChatOpenAI client configured via env vars."""
    settings = get_settings()
    return ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
    )
