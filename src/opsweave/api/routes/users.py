from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from ...auth.permissions import Role
from ..auth import require_admin
from ..user_store import (
    authenticate_user,
    list_users,
    logout_token,
    register_user,
    user_for_token,
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])
_bearer = HTTPBearer(auto_error=False)


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=256)


@router.post("/register", status_code=201)
def register(credentials: Credentials) -> dict:
    try:
        register_user(credentials.username, credentials.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "ok"}


@router.post("/login")
def login(credentials: Credentials, request: Request, response: Response) -> dict:
    result = authenticate_user(credentials.username, credentials.password)
    if not result:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token, role = result
    response.set_cookie(
        "opsweave_session",
        token,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        max_age=604800,
    )
    return {"username": credentials.username, "role": role}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    token = request.cookies.get("opsweave_session") or (
        credentials.credentials if credentials else None
    )
    logout_token(token)
    response.delete_cookie("opsweave_session")
    return {"status": "ok"}


@router.get("/me")
def me(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    token = request.cookies.get("opsweave_session") or (
        credentials.credentials if credentials else None
    )
    user = user_for_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return {"username": user[0], "role": user[1]}


@router.get("/users")
def users(_: Role = Depends(require_admin)) -> dict:
    return {"users": list_users()}
