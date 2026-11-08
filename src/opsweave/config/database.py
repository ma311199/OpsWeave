"""SQLite-based configuration persistence layer."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .settings import get_settings

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS configs (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general'
);
"""

# Non-sensitive config keys persisted in SQLite and used as settings overrides.
# Maps db_key -> (Settings field name, category)
CONFIG_MAP: dict[str, tuple[str, str]] = {
    # LLM
    "llm_base_url": ("llm_base_url", "llm"),
    "llm_model": ("llm_model", "llm"),
    "llm_temperature": ("llm_temperature", "llm"),
    # Embedding
    "embedding_base_url": ("embedding_base_url", "embedding"),
    "embedding_api_key": ("embedding_api_key", "embedding"),
    "embedding_model": ("embedding_model", "embedding"),
    "embedding_dimension": ("embedding_dimension", "embedding"),
    "embedding_max_tokens": ("embedding_max_tokens", "embedding"),
    # Milvus
    "milvus_uri": ("milvus_uri", "milvus"),
    "milvus_user": ("milvus_user", "milvus"),
    "milvus_database": ("milvus_database", "milvus"),
    "milvus_collections": ("milvus_collections", "milvus"),
    # Agent and MCP
    "agent_max_iterations": ("agent_max_iterations", "agent"),
    "mcp_servers": ("mcp_servers", "mcp"),
}


def _db_path() -> Path:
    settings = get_settings()
    return Path(settings.data_dir) / "opsweave.db"


def _get_conn() -> sqlite3.Connection:
    db_path = _db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create configs table if not exists."""
    with _get_conn() as conn:
        conn.execute(_TABLE_DDL)
        conn.execute(
            "DELETE FROM configs WHERE key IN (?, ?, ?)",
            ("llm_api_key", "embedding_api_key", "milvus_password"),
        )
        conn.commit()


def get_all_configs() -> dict[str, str]:
    """Return all persisted configs as a flat dict."""
    init_db()
    with _get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM configs").fetchall()
    return {row["key"]: row["value"] for row in rows}


def get_config(key: str) -> str | None:
    """Return a single config value or None."""
    init_db()
    with _get_conn() as conn:
        row = conn.execute("SELECT value FROM configs WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_config(key: str, value: str, category: str = "general") -> None:
    """Insert or update a config value."""
    init_db()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO configs (key, value, category) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "category = excluded.category",
            (key, value, category),
        )
        conn.commit()


def update_configs(configs: dict[str, Any]) -> dict[str, str]:
    """Bulk update configs. Returns the persisted key-value dict.

    Only keys present in CONFIG_MAP are persisted.
    """
    configs.pop("_category", None)
    for key, value in configs.items():
        if key not in CONFIG_MAP:
            continue
        db_key, cat = CONFIG_MAP[key]
        set_config(db_key, str(value), cat)
    get_settings.cache_clear()
    return get_all_configs()
