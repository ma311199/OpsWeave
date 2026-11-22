"""Retrieval endpoints for querying the Milvus knowledge base."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymilvus.exceptions import MilvusException

from ...agents.retrieval_pipeline import (
    DEFAULT_COLLECTION,
    clear_retrieval_index_cache,
    run_retrieval_pipeline,
)
from ...auth.permissions import PermissionChecker, ResourceType, Role
from ...config.settings import get_settings
from ...retrieval.retriever import Retriever
from ..auth import current_user, require_admin

router = APIRouter()
_checker = PermissionChecker.default_rules()


class RetrieveRequest(BaseModel):
    query: str = Field(..., description="Natural language query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results")
    collection_name: str = Field(
        default=DEFAULT_COLLECTION, description="Milvus collection to search"
    )


class RetrieveResponse(BaseModel):
    query: str
    results: list[dict]


@router.post("/search", response_model=RetrieveResponse)
def search(
    req: RetrieveRequest, principal: tuple[str, Role] = Depends(current_user)
) -> RetrieveResponse:
    """Search the knowledge base via Milvus vector retrieval."""
    username, role = principal
    _checker.require(role, ResourceType.RETRIEVAL_INDEX)

    try:
        state = run_retrieval_pipeline(
            query=req.query,
            role=role,
            user_id=username,
            top_k=req.top_k,
            collection_name=req.collection_name,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except MilvusException as e:
        raise HTTPException(
            status_code=503,
            detail=(
                "向量库连接失败，请确认 Milvus 已启动且地址可访问："
                f"{get_settings().milvus_uri}"
            ),
        ) from e

    return RetrieveResponse(query=req.query, results=state.get("results", []))


@router.post("/build")
def build_index(
    role: Role = Depends(require_admin),
    documents_path: str | None = None,
    collection_name: str = "opsweave",
) -> dict:
    """Build or connect to a Milvus index."""
    retriever = Retriever()
    try:
        retriever.build_index(
            documents_path=documents_path,
            collection_name=collection_name,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Build failed: {e}")
    # 重建后丢弃旧的缓存索引，避免直连检索继续用过期集合句柄。
    clear_retrieval_index_cache(collection_name)
    return {
        "status": "built",
        "collection": collection_name,
        "ready": retriever.is_ready,
    }
