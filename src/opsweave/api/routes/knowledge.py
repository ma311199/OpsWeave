"""Knowledge base management endpoints."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from ...config.settings import get_settings

router = APIRouter()

# Track build status in memory (simple approach for prototype)
_build_status: dict[str, Any] = {"status": "idle", "progress": 0, "message": ""}


class BuildRequest(BaseModel):
    collection_name: str = "opsweave"
    documents_path: str | None = None


class StatusResponse(BaseModel):
    ready: bool
    collection: str
    document_count: int = 0
    build_status: str = "idle"
    build_progress: int = 0
    build_message: str = ""


def _get_docs_dir() -> Path:
    settings = get_settings()
    docs_dir = Path(settings.data_dir) / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    return docs_dir


def _count_documents() -> int:
    docs_dir = _get_docs_dir()
    count = 0
    for ext in (".txt", ".md", ".pdf", ".docx", ".json", ".yaml", ".yml", ".csv"):
        count += len(list(docs_dir.glob(f"*{ext}")))
    return count


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)) -> dict:
    """Upload a document to the knowledge base."""
    docs_dir = _get_docs_dir()
    
    # Sanitize filename
    safe_name = os.path.basename(file.filename or "document")
    target = docs_dir / safe_name
    
    # Avoid overwriting
    if target.exists():
        name, ext = os.path.splitext(safe_name)
        target = docs_dir / f"{name}_{int(target.stat().st_mtime)}{ext}"
    
    with open(target, "wb") as f:
        content = await file.read()
        f.write(content)
    
    return {
        "status": "ok",
        "filename": target.name,
        "size": len(content),
        "message": f"文档 {target.name} 已上传",
    }


@router.post("/build")
def build_index(req: BuildRequest) -> dict:
    """Build or connect to a Milvus index from uploaded documents."""
    docs_path = req.documents_path or str(_get_docs_dir())
    
    try:
        from ...retrieval.retriever import Retriever
        
        retriever = Retriever()
        retriever.build_index(
            documents_path=docs_path,
            collection_name=req.collection_name,
        )
        
        return {
            "status": "built",
            "collection": req.collection_name,
            "ready": retriever.is_ready,
            "message": "索引构建完成",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"构建失败: {e}")


@router.get("/status")
def get_status() -> StatusResponse:
    """Get knowledge base status."""
    docs_count = _count_documents()
    
    # Check if index is ready by trying to connect
    ready = False
    try:
        from ...retrieval.retriever import Retriever
        retriever = Retriever()
        ready = retriever.is_ready
    except Exception:
        pass
    
    return StatusResponse(
        ready=ready,
        collection="opsweave",
        document_count=docs_count,
        build_status=_build_status["status"],
        build_progress=_build_status["progress"],
        build_message=_build_status["message"],
    )


@router.get("/documents")
def list_documents() -> dict:
    """List uploaded documents."""
    docs_dir = _get_docs_dir()
    documents = []
    
    for f in sorted(docs_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.is_file():
            documents.append({
                "name": f.name,
                "size": f.stat().st_size,
                "modified": f.stat().st_mtime,
            })
    
    return {"documents": documents, "count": len(documents)}


@router.delete("/documents/{filename}")
def delete_document(filename: str) -> dict:
    """Delete an uploaded document."""
    docs_dir = _get_docs_dir()
    target = docs_dir / os.path.basename(filename)
    
    if not target.exists():
        raise HTTPException(status_code=404, detail="文档不存在")
    
    target.unlink()
    return {"status": "ok", "message": f"文档 {filename} 已删除"}
