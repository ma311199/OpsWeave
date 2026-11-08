"""Configuration management using pydantic-settings."""

from __future__ import annotations

import os
import sqlite3
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables + SQLite."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM (OpenAI-compatible)
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = "sk-xxx"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.2

    # Retrieval
    retriever_top_k: int = 5
    retriever_chunk_size: int = 512
    retriever_chunk_overlap: int = 64

    # Milvus
    milvus_uri: str = "http://localhost:19530"
    milvus_user: str = ""
    milvus_password: str = ""
    milvus_database: str = "default"

    # Embedding (OpenAI-compatible)
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_api_key: str = ""
    embedding_model: str = "qwen3-vl-embedding"
    embedding_dimension: int = 2048

    # Agent
    agent_max_iterations: int = 8

    # Role-based API tokens
    admin_initial_password: str = ""
    admin_token: str = ""
    ops_engineer_token: str = ""
    viewer_token: str = ""
    mcp_token: str = ""

    # Paths
    data_dir: Path = Path("./data")


def _load_sqlite_overrides() -> dict[str, str]:
    """Load config overrides from SQLite."""
    try:
        db_path = Path(os.getenv("DATA_DIR", str(Settings().data_dir))) / "opsweave.db"
        if not db_path.exists():
            return {}
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT key, value FROM configs").fetchall()
        return {row["key"]: row["value"] for row in rows}
    except Exception:
        return {}


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor with SQLite overrides."""
    settings = Settings()
    overrides = _load_sqlite_overrides()
    for key, value in overrides.items():
        if key in {"llm_api_key", "embedding_api_key", "milvus_password"}:
            continue
        if hasattr(settings, key):
            attr = getattr(settings, key)
            if isinstance(attr, float):
                setattr(settings, key, float(value))
            elif isinstance(attr, int):
                setattr(settings, key, int(value))
            else:
                setattr(settings, key, value)
    return settings
