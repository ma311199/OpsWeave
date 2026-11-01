from __future__ import annotations

import os
import secrets

from http.cookies import SimpleCookie

from fastapi import HTTPException, Request, Security, WebSocket
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..auth.permissions import Role
from ..config.settings import get_settings
from .user_store import user_for_token

_bearer = HTTPBearer(auto_error=False)


def _role_for_token(token: str | None) -> Role:
    if not token:
        raise HTTPException(status_code=401, detail="Bearer token required")

    user = user_for_token(token)
    if user:
        return Role(user[1])

    settings = get_settings()
    if token == settings.admin_initial_password and settings.admin_initial_password:
        return Role.ADMIN
    configured_tokens = {
        Role.ADMIN: settings.admin_token or os.getenv("ADMIN_TOKEN", ""),
        Role.OPS_ENGINEER: settings.ops_engineer_token or os.getenv("OPS_ENGINEER_TOKEN", ""),
        Role.VIEWER: settings.viewer_token or os.getenv("VIEWER_TOKEN", ""),
    }
    if not any(configured_tokens.values()):
        raise HTTPException(status_code=503, detail="API tokens are not configured")

    for role, configured in configured_tokens.items():
        if configured and secrets.compare_digest(token, configured):
            return role
    raise HTTPException(status_code=401, detail="Invalid bearer token")


def require_role(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> Role:
    token = credentials.credentials if credentials else request.cookies.get("opsweave_session")
    if token:
        user = user_for_token(token)
        if user:
            return Role(user[1])
    return _role_for_token(token)


def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> tuple[str, Role]:
    token = credentials.credentials if credentials else request.cookies.get("opsweave_session")
    user = user_for_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录账号后才能访问此资源")
    return user[0], Role(user[1])


def require_admin(role: Role = Security(require_role)) -> Role:
    if role is not Role.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required")
    return role


async def websocket_role(websocket: WebSocket) -> Role:
    protocols = websocket.scope.get("subprotocols", [])
    token = next(
        (protocol.removeprefix("bearer.") for protocol in protocols if protocol.startswith("bearer.")),
        None,
    )
    if not token:
        cookie = SimpleCookie()
        cookie.load(websocket.headers.get("cookie", ""))
        morsel = cookie.get("opsweave_session")
        token = morsel.value if morsel else None
    if token:
        user = user_for_token(token)
        if user:
            return Role(user[1])
    return _role_for_token(token)
