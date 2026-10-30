"""Retrieval endpoints for querying the Milvus knowledge base."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...auth.permissions import PermissionChecker, ResourceType, Role
from ...retrieval.retriever import Retriever

router = APIRouter()
_checker = PermissionChecker.default_rules()


class RetrieveRequest(BaseModel):
    query: str = Field(..., description="Natural language query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results")
    role: str = Field(default="admin", description="User role for permission check")


class RetrieveResponse(BaseModel):
    query: str
    results: list[dict]


@router.post("/search", response_model=RetrieveResponse)
def search(req: RetrieveRequest) -> RetrieveResponse:
    """Search the knowledge base via Milvus vector retrieval."""
    try:
        role = Role(req.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}")

    _checker.require(role, ResourceType.RETRIEVAL_INDEX)

    retriever = Retriever()
    try:
        results = retriever.retrieve(query=req.query, top_k=req.top_k, role=role)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return RetrieveResponse(
        query=req.query,
        results=[
            {
                "text": r.text,
                "score": round(r.score, 4),
                "source": r.source,
            }
            for r in results
        ],
    )


@router.post("/build")
def build_index(
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
