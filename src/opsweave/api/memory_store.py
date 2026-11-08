from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from ..config.database import _get_conn
from ..config.settings import get_settings


def _init_memory() -> None:
    with _get_conn() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation ON chat_messages(username, conversation_id, id)"
        )


def get_history(
    username: str, conversation_id: str, limit: int = 20
) -> list[dict[str, str]]:
    _init_memory()
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM chat_messages WHERE username = ? AND conversation_id = ? ORDER BY id DESC LIMIT ?",
            (username, conversation_id, limit),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def append_turn(username: str, conversation_id: str, query: str, answer: str) -> None:
    _init_memory()
    with _get_conn() as conn:
        conn.executemany(
            "INSERT INTO chat_messages (username, conversation_id, role, content) VALUES (?, ?, ?, ?)",
            [
                (username, conversation_id, "user", query),
                (username, conversation_id, "assistant", answer),
            ],
        )
        conn.execute(
            "DELETE FROM chat_messages WHERE username = ? AND conversation_id = ? AND id NOT IN "
            "(SELECT id FROM chat_messages WHERE username = ? AND conversation_id = ? ORDER BY id DESC LIMIT 40)",
            (username, conversation_id, username, conversation_id),
        )


def _long_term_path(username: str) -> Path:
    safe_username = re.sub(r"[^A-Za-z0-9_.-]", "_", username)
    user_dir = Path(get_settings().data_dir) / "documents" / safe_username
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / "memory.md"


def get_long_term_memory(username: str) -> str:
    path = _long_term_path(username)
    return path.read_text(encoding="utf-8") if path.exists() else ""


def append_long_term_memory(username: str, note: str) -> None:
    note = note.strip()
    if not note:
        return
    path = _long_term_path(username)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    needs_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8") as memory_file:
        if needs_header:
            memory_file.write("# 长期记忆\n\n")
        memory_file.write(f"- {timestamp}: {note}\n")
