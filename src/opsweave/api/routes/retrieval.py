"""Retrieval endpoints for querying the Milvus knowledge base."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...agents.retrieval_pipeline import DEFAULT_COLLECTION, run_retrieval_pipeline
from ...auth.permissions import PermissionChecker, ResourceType, Role
from ...retrieval.retriever import Retriever
from ..auth import current_user, require_admin

router = APIRouter()
_checker = PermissionChecker.default_rules()


class RetrieveOptions(BaseModel):
    """直连检索管道开关；分解与重排为预留占位，默认关闭。"""

    decompose: bool = Field(default=False, description="启用问题分解（预留）")
    rerank: bool = Field(default=False, description="启用重排（预留）")


class RetrieveRequest(BaseModel):
    query: str = Field(..., description="Natural language query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results")
    collection_name: str | None = Field(
        default=None, description="Milvus collection；缺省为 opsweave"
    )
    options: RetrieveOptions = Field(default_factory=RetrieveOptions)


class RetrieveResponse(BaseModel):
    query: str
    results: list[dict]


@router.post("/search", response_model=RetrieveResponse)
def search(
    req: RetrieveRequest, principal: tuple[str, Role] = Depends(current_user)
) -> RetrieveResponse:
    """Search the knowledge base via the LangGraph retrieval pipeline."""
    username, role = principal
    _checker.require(role, ResourceType.RETRIEVAL_INDEX)

    try:
        state = run_retrieval_pipeline(
            query=req.query,
            role=role,
            user_id=username,
            top_k=req.top_k,
            collection_name=req.collection_name or DEFAULT_COLLECTION,
            options=req.options.model_dump(),
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

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
    return {
        "status": "built",
        "collection": collection_name,
        "ready": retriever.is_ready,
    }
