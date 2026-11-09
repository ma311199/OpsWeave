from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth import current_user
from ..memory_store import (
    conversation_exists,
    create_conversation,
    delete_conversation,
    get_history,
    list_conversations,
    rename_conversation,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    title: str = Field(default="新会话", min_length=1, max_length=120)


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


@router.get("")
def get_conversations(
    principal: tuple[str, str] = Depends(current_user),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return {"items": list_conversations(principal[0], limit, offset)}


@router.post("")
def post_conversation(
    req: ConversationCreate, principal: tuple[str, str] = Depends(current_user)
) -> dict:
    conversation_id = str(uuid.uuid4())
    create_conversation(principal[0], conversation_id, req.title.strip())
    return {"conversation_id": conversation_id, "title": req.title.strip()}


@router.get("/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: str,
    principal: tuple[str, str] = Depends(current_user),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    items = get_history(principal[0], conversation_id, limit, offset)
    if not conversation_exists(principal[0], conversation_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"items": items, "limit": limit, "offset": offset}


@router.patch("/{conversation_id}")
def patch_conversation(
    conversation_id: str,
    req: ConversationRename,
    principal: tuple[str, str] = Depends(current_user),
) -> dict:
    title = req.title.strip()
    if not title or not rename_conversation(principal[0], conversation_id, title):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"conversation_id": conversation_id, "title": title}


@router.delete("/{conversation_id}")
def remove_conversation(
    conversation_id: str, principal: tuple[str, str] = Depends(current_user)
) -> dict:
    if not delete_conversation(principal[0], conversation_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"status": "deleted"}
