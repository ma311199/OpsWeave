from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from ..config.database import _get_conn


def _init_approvals() -> None:
    with _get_conn() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS tool_approvals (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            server_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            arguments TEXT NOT NULL,
            status TEXT NOT NULL,
            reviewer TEXT,
            created_at TEXT NOT NULL
        )""")


def create_approval(
    username: str, conversation_id: str, server_id: str, tool_name: str, arguments: dict
) -> str:
    _init_approvals()
    approval_id = str(uuid.uuid4())
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO tool_approvals (id, username, conversation_id, server_id, tool_name, arguments, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
            (
                approval_id,
                username,
                conversation_id,
                server_id,
                tool_name,
                json.dumps(arguments, ensure_ascii=False),
                datetime.now(UTC).isoformat(),
            ),
        )
    return approval_id


def list_approvals(username: str, is_admin: bool) -> list[dict]:
    _init_approvals()
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT id, username, conversation_id, server_id, tool_name, arguments, status, reviewer, created_at FROM tool_approvals WHERE status = 'pending' AND (? OR username = ?) ORDER BY created_at",
            (int(is_admin), username),
        ).fetchall()
    result = [dict(row) for row in rows]
    for item in result:
        item["arguments"] = json.loads(item["arguments"])
    return result


def resolve_approval(
    approval_id: str, username: str, is_admin: bool, approve: bool
) -> dict | None:
    _init_approvals()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM tool_approvals WHERE id = ?", (approval_id,)
        ).fetchone()
        if (
            not row
            or (row["username"] != username and not is_admin)
            or row["status"] != "pending"
        ):
            return None
        status = "approved" if approve else "rejected"
        updated = conn.execute(
            "UPDATE tool_approvals SET status = ?, reviewer = ? WHERE id = ? AND status = 'pending'",
            (status, username, approval_id),
        )
        if updated.rowcount != 1:
            return None
        result = dict(row)
        result["status"] = status
        result["arguments"] = json.loads(result["arguments"])
        if approve:
            conn.execute(
                "UPDATE tool_approvals SET status = 'executing' WHERE id = ? AND status = 'approved'",
                (approval_id,),
            )
        return result


def finish_approval(approval_id: str, status: str) -> None:
    _init_approvals()
    with _get_conn() as conn:
        conn.execute(
            "UPDATE tool_approvals SET status = ? WHERE id = ? AND status = 'executing'",
            (status, approval_id),
        )
