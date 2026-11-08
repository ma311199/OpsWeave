from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta

from ..config.database import _get_conn
from ..config.settings import get_settings


def _hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    salt = salt or secrets.token_bytes(16)
    return salt, hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)


def init_users() -> None:
    with _get_conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_salt BLOB NOT NULL, password_hash BLOB NOT NULL, role TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, expires_at TEXT NOT NULL)"
        )
    admin_password = (
        os.getenv("ADMIN_INITIAL_PASSWORD", "")
        or get_settings().admin_initial_password
        or os.getenv("ADMIN_TOKEN", "")
        or get_settings().admin_token
    )
    if admin_password:
        salt, digest = _hash_password(admin_password)
        with _get_conn() as conn:
            existing = conn.execute(
                "SELECT password_hash FROM users WHERE username = 'admin'"
            ).fetchone()
            if existing and len(existing["password_hash"]) != 32:
                conn.execute(
                    "UPDATE users SET password_salt = ?, password_hash = ?, role = 'admin' WHERE username = 'admin'",
                    (salt, digest),
                )
            else:
                conn.execute(
                    "INSERT OR IGNORE INTO users (username, password_salt, password_hash, role) VALUES ('admin', ?, ?, 'admin')",
                    (salt, digest),
                )


def register_user(username: str, password: str) -> None:
    init_users()
    if username == "admin":
        raise ValueError("该用户名不可注册")
    salt, digest = _hash_password(password)
    try:
        with _get_conn() as conn:
            conn.execute(
                "INSERT INTO users (username, password_salt, password_hash, role) VALUES (?, ?, ?, 'viewer')",
                (username, salt, digest),
            )
    except sqlite3.IntegrityError as exc:
        raise ValueError("用户名已存在") from exc


def authenticate_user(username: str, password: str) -> tuple[str, str] | None:
    init_users()
    with _get_conn() as conn:
        user = conn.execute(
            "SELECT password_salt, password_hash, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if not user or len(user["password_hash"]) != 32:
        return None
    _, digest = _hash_password(password, user["password_salt"])
    if not hmac.compare_digest(digest, user["password_hash"]):
        return None
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, username, expires_at) VALUES (?, ?, ?)",
            (token_hash, username, expires_at),
        )
    return token, user["role"]


def user_for_token(token: str | None) -> tuple[str, str] | None:
    if not token:
        return None
    init_users()
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT users.username, users.role, sessions.expires_at FROM sessions JOIN users USING (username) WHERE sessions.token_hash = ?",
            (token_hash,),
        ).fetchone()
    if not row or datetime.fromisoformat(row["expires_at"]) <= datetime.now(
        UTC
    ):
        return None
    return row["username"], row["role"]


def logout_token(token: str | None) -> None:
    if token:
        with _get_conn() as conn:
            conn.execute(
                "DELETE FROM sessions WHERE token_hash = ?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            )


def list_users() -> list[dict[str, str]]:
    init_users()
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT username, role FROM users ORDER BY username"
        ).fetchall()
    return [dict(row) for row in rows]
