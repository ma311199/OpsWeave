"""Knowledge base upload, approval, and document browsing endpoints."""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, model_validator

from ...auth.permissions import Role
from ...config.database import get_config
from ...config.settings import get_settings
from ..auth import current_user
from ..user_store import _get_conn

logger = logging.getLogger(__name__)
router = APIRouter()


class ApplicationRequest(BaseModel):
    strategy: str = Field(pattern="^(fixed|sentence|paragraph|recursive|sliding|structure|semantic|summary)$")
    chunk_size: int = Field(ge=1, le=100000)
    overlap: int = Field(ge=0, le=10000)
    semantic_max_chunk_size: int | None = Field(default=None, ge=1, le=100000)
    structure_format: str = Field(default="markdown", pattern="^(markdown|html|latex)$")
    semantic_threshold: int = Field(default=95, ge=50, le=99)
    collection_name: str | None = None

    @model_validator(mode="after")
    def validate_overlap(self):
        """确保滑动窗口重叠小于块大小，避免切分不前进。"""
        if self.overlap >= self.chunk_size:
            raise ValueError("overlap 必须小于 chunk_size")
        return self


def _init_knowledge() -> None:
    """创建知识库元数据表，并为既有 SQLite 数据库补齐新字段。"""
    with _get_conn() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS knowledge_documents (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, filename TEXT NOT NULL, path TEXT NOT NULL,
            size INTEGER NOT NULL, strategy TEXT NOT NULL DEFAULT 'token', status TEXT NOT NULL,
            reviewer TEXT, error TEXT, collection_name TEXT NOT NULL DEFAULT 'opsweave',
            chunk_size INTEGER NOT NULL DEFAULT 512, chunk_overlap INTEGER NOT NULL DEFAULT 64,
            semantic_max_chunk_size INTEGER NOT NULL DEFAULT 2048, structure_format TEXT NOT NULL DEFAULT 'markdown', semantic_threshold INTEGER NOT NULL DEFAULT 95, chunk_metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(knowledge_documents)")}
        if "collection_name" not in columns:
            conn.execute("ALTER TABLE knowledge_documents ADD COLUMN collection_name TEXT NOT NULL DEFAULT 'opsweave'")
        if "chunk_size" not in columns:
            conn.execute("ALTER TABLE knowledge_documents ADD COLUMN chunk_size INTEGER NOT NULL DEFAULT 512")
        if "chunk_overlap" not in columns:
            conn.execute("ALTER TABLE knowledge_documents ADD COLUMN chunk_overlap INTEGER NOT NULL DEFAULT 64")
        if "semantic_max_chunk_size" not in columns:
            conn.execute("ALTER TABLE knowledge_documents ADD COLUMN semantic_max_chunk_size INTEGER NOT NULL DEFAULT 2048")
        if "structure_format" not in columns:
            conn.execute("ALTER TABLE knowledge_documents ADD COLUMN structure_format TEXT NOT NULL DEFAULT 'markdown'")
        if "semantic_threshold" not in columns:
            conn.execute("ALTER TABLE knowledge_documents ADD COLUMN semantic_threshold INTEGER NOT NULL DEFAULT 95")
        if "chunk_metadata" not in columns:
            conn.execute("ALTER TABLE knowledge_documents ADD COLUMN chunk_metadata TEXT NOT NULL DEFAULT '{}'")
        conn.execute("""CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id TEXT PRIMARY KEY, document_id TEXT NOT NULL, owner TEXT NOT NULL,
            ordinal INTEGER NOT NULL, text TEXT NOT NULL, embedding_text TEXT NOT NULL,
            FOREIGN KEY(document_id) REFERENCES knowledge_documents(id)
        )""")


def _document_dir(owner: str) -> Path:
    path = Path(get_settings().data_dir) / "documents" / owner
    path.mkdir(parents=True, exist_ok=True)
    return path


def _document_row(document_id: str, owner: str, role: Role):
    """读取文档并统一执行所有者隔离；无权访问时按不存在处理。"""
    _init_knowledge()
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM knowledge_documents WHERE id = ?", (document_id,)).fetchone()
    if not row or (role is not Role.ADMIN and row["owner"] != owner):
        raise HTTPException(status_code=404, detail="文档不存在")
    return row


@router.get("/collections")
def list_knowledge_collections(_: tuple[str, Role] = Depends(current_user)) -> dict:
    from pymilvus import Collection, utility

    from .config import _connect_milvus

    _connect_milvus()
    descriptions = json.loads(get_config("milvus_collection_descriptions") or "{}")
    names = utility.list_collections()
    return {"collections": [{"name": name, "description": descriptions.get(name, ""), "row_count": Collection(name).num_entities} for name in names]}


@router.get("/strategies")
def strategies(_: tuple[str, Role] = Depends(current_user)) -> dict:
    return {"strategies": [
        {"id": "fixed", "name": "固定长度切分"},
        {"id": "sentence", "name": "句子级切分"},
        {"id": "paragraph", "name": "段落级切分"},
        {"id": "recursive", "name": "递归切分"},
        {"id": "sliding", "name": "滑动窗口切分"},
        {"id": "structure", "name": "结构化切分"},
        {"id": "semantic", "name": "语义切分"},
        {"id": "summary", "name": "摘要切分 (LLM)"},
    ], "embedding_max_tokens": int(get_config("embedding_max_tokens") or 8192)}


@router.post("/upload")
async def upload_document(collection_name: str, file: UploadFile = File(...), principal: tuple[str, Role] = Depends(current_user)) -> dict:
    owner, _ = principal
    from pymilvus import utility

    from .config import _connect_milvus
    _connect_milvus()
    if collection_name not in utility.list_collections():
        raise HTTPException(status_code=400, detail="所选知识库在管理员当前配置的知识库中不存在，请刷新知识库列表")
    filename = os.path.basename(file.filename or "document")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="不能上传空文件")
    document_id = str(uuid.uuid4())
    target = _document_dir(owner) / f"{document_id}_{filename}"
    target.write_bytes(content)
    _init_knowledge()
    with _get_conn() as conn:
        conn.execute("INSERT INTO knowledge_documents (id, owner, filename, path, size, strategy, status, collection_name) VALUES (?, ?, ?, ?, ?, 'token', 'uploaded', ?)",
                     (document_id, owner, filename, str(target), len(content), collection_name))
    return {"id": document_id, "filename": filename, "size": len(content), "status": "uploaded", "collection_name": collection_name}


@router.get("/documents")
def list_documents(principal: tuple[str, Role] = Depends(current_user)) -> dict:
    owner, role = principal
    _init_knowledge()
    with _get_conn() as conn:
        if role is Role.ADMIN:
            rows = conn.execute("SELECT id, owner, filename, size, strategy, status, reviewer, error, collection_name, chunk_size, chunk_overlap, semantic_max_chunk_size, structure_format, semantic_threshold, created_at FROM knowledge_documents WHERE status != 'uploaded' ORDER BY created_at DESC").fetchall()
        else:
            rows = conn.execute("SELECT id, owner, filename, size, strategy, status, reviewer, error, collection_name, chunk_size, chunk_overlap, semantic_max_chunk_size, created_at FROM knowledge_documents WHERE owner = ? ORDER BY created_at DESC", (owner,)).fetchall()
    return {"documents": [dict(row) for row in rows], "count": len(rows)}


@router.post("/documents/{document_id}/apply")
def apply_index(document_id: str, req: ApplicationRequest, background_tasks: BackgroundTasks, principal: tuple[str, Role] = Depends(current_user)) -> dict:
    """校验文档、collection 与 token 上限后，立即构建或送交管理员审批。"""
    owner, role = principal
    row = _document_row(document_id, owner, role)
    if row["status"] not in {"uploaded", "rejected", "failed"}:
        raise HTTPException(status_code=409, detail="该文档当前状态不能提交申请")
    collection_name = row["collection_name"] or req.collection_name
    if not collection_name:
        raise HTTPException(status_code=400, detail="该文档未绑定知识库，请刷新知识库列表后重新提交")
    from pymilvus import utility

    from .config import _connect_milvus
    _connect_milvus()
    if collection_name not in utility.list_collections():
        raise HTTPException(status_code=400, detail="所选知识库已不存在于管理员当前配置的 Milvus 数据库中，请刷新后重新上传")
    max_tokens = int(get_config("embedding_max_tokens") or 8192)
    requested_max = req.semantic_max_chunk_size if req.strategy == "semantic" else req.chunk_size
    if requested_max and requested_max > max_tokens:
        raise HTTPException(status_code=422, detail=f"切分块大小不能超过当前 Embedding 最大输入限制 {max_tokens} tokens")
    with _get_conn() as conn:
        conn.execute("UPDATE knowledge_documents SET collection_name = ?, chunk_size = ?, chunk_overlap = ?, semantic_max_chunk_size = ?, structure_format = ?, semantic_threshold = ? WHERE id = ?", (collection_name, req.chunk_size, req.overlap, req.semantic_max_chunk_size or req.chunk_size, req.structure_format, req.semantic_threshold, document_id))
    if role is Role.ADMIN:
        with _get_conn() as conn:
            conn.execute("UPDATE knowledge_documents SET strategy = ?, status = 'processing', reviewer = ?, error = NULL WHERE id = ?", (req.strategy, owner, document_id))
        background_tasks.add_task(_build_approved_document, document_id)
        return {"status": "processing", "document_id": document_id}
    with _get_conn() as conn:
        conn.execute("UPDATE knowledge_documents SET strategy = ?, status = 'pending', reviewer = NULL, error = NULL WHERE id = ?", (req.strategy, document_id))
    return {"status": "pending", "document_id": document_id}


def _process_document(document_id: str) -> None:
    """按所选策略切分文档，校验最终向量文本长度后写入 Milvus 和 SQLite。"""
    from llama_index.core import SimpleDirectoryReader
    from llama_index.core.node_parser import (
        SemanticSplitterNodeParser,
        SentenceSplitter,
        TokenTextSplitter,
    )
    from llama_index.core.schema import TextNode

    from ...retrieval.embeddings import OpenAICompatEmbedding
    from ...retrieval.vector_store import get_milvus_store

    with _get_conn() as conn:
        doc = conn.execute("SELECT * FROM knowledge_documents WHERE id = ?", (document_id,)).fetchone()
    loaded = SimpleDirectoryReader(input_files=[doc["path"]]).load_data()
    embedding = OpenAICompatEmbedding.from_settings()
    strategy = doc["strategy"] or "fixed"  # 

    if strategy in {"fixed", "sliding"}:  # 固定切分或滑动切分
        splitter = TokenTextSplitter(
            chunk_size=doc["chunk_size"],
            chunk_overlap=doc["chunk_overlap"] if strategy == "sliding" else 0,
        )
        source_nodes = splitter.get_nodes_from_documents(loaded)
    elif strategy == "sentence":  # 句子切分
        splitter = SentenceSplitter(chunk_size=doc["chunk_size"], chunk_overlap=doc["chunk_overlap"])
        source_nodes = splitter.get_nodes_from_documents(loaded)
    elif strategy in {"paragraph", "recursive", "structure"}:  # 段落切分、递归切分或结构化切分
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        structure_separators = {
            "markdown": [r"\n#{1,6}\s+", r"\n\n", r"\n"],
            "html": [r"</?(?:h[1-6]|p|div|section|article)[^>]*>", r"\n\n", r"\n"],
            "latex": [r"\\(?:chapter|section|subsection|paragraph)\*?\{", r"\n\n", r"\n"],
        }
        separators = {
            "paragraph": [r"\n\n", r"\n", ""],
            "recursive": [r"\n\n", r"\n", "。", "！", "？", r"\.\s+", "! ", "? ", ""],
            "structure": structure_separators[doc["structure_format"]] + ["。", "！", "？", ""],
        }[strategy]
        splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            chunk_size=doc["chunk_size"],
            chunk_overlap=doc["chunk_overlap"],
            separators=separators,
            is_separator_regex=True,
        )
        source_nodes = splitter.create_documents([item.text for item in loaded])
    elif strategy == "semantic":  # 语义切分    
        bounded_splitter = SentenceSplitter(chunk_size=doc["semantic_max_chunk_size"], chunk_overlap=0)
        bounded_nodes = bounded_splitter.get_nodes_from_documents(loaded)
        semantic_parser = SemanticSplitterNodeParser(
            buffer_size=1,
            breakpoint_percentile_threshold=doc["semantic_threshold"],
            embed_model=embedding,
        )
        source_nodes = [
            node
            for bounded_node in bounded_nodes
            for node in semantic_parser.get_nodes_from_documents([bounded_node])
        ]
    elif strategy == "summary":  # 摘要切分
        from ...llm.client import get_llm

        base_splitter = SentenceSplitter(chunk_size=doc["chunk_size"], chunk_overlap=doc["chunk_overlap"])
        source_nodes = base_splitter.get_nodes_from_documents(loaded)
        for source_node in source_nodes:
            prompt = (
                "为以下文本块生成简洁标题、摘要和关键词，只返回 JSON，字段为 title、summary、keywords。\n"
                f"文本：{source_node.get_content()}"
            )
            metadata = json.loads(get_llm().invoke(prompt).content)
            source_node.metadata.update(metadata)
    else:
        raise ValueError(f"不支持的切分策略: {strategy}")  # 不支持的切分策略

    logger.info(
        "Document chunking completed: document_id=%s strategy=%s source_documents=%d chunks=%d collection=%s",
        document_id, strategy, len(loaded), len(source_nodes), doc["collection_name"],
    )
    chunks: list[dict[str, str]] = []
    vector_nodes = []
    max_tokens = int(get_config("embedding_max_tokens") or 8192)  # 最大输入 token 数
    for ordinal, source in enumerate(source_nodes):  # 遍历所有文本块
        raw = source.get_content()
        if strategy == "summary":  # 摘要切分
            keywords = source.metadata.get("keywords", [])
            embed_text = (
                f"{source.metadata.get('title', '')}\n{source.metadata.get('summary', '')}\n"
                f"关键词：{', '.join(keywords) if isinstance(keywords, list) else keywords}\n{raw}"
            )
        else:
            embed_text = raw
        token_count = embedding.count_tokens(embed_text)
        if token_count > max_tokens:
            raise ValueError(f"第 {ordinal + 1} 个文本块超过 Embedding 模型最大输入限制：{token_count} > {max_tokens} tokens")
        chunk_id = str(uuid.uuid4())
        chunks.append({
            "id": chunk_id,
            "document_id": document_id,
            "owner": doc["owner"],
            "ordinal": ordinal,
            "text": raw,
            "embedding_text": embed_text,
        })
        node = TextNode(
            text=raw,
            id_=chunk_id,
            metadata={
                "user_id": doc["owner"],
                "filename": doc["filename"],
                "ref_doc_id": document_id,
            },
        )
        try:
            node.embedding = embedding.get_text_embedding(embed_text)
            vector_nodes.append(node)
            logger.debug(
                "Embedded chunk: document_id=%s ordinal=%d chunk_id=%s text_chars=%d embedding_tokens=%d embedding_dimensions=%d",
                document_id, ordinal, chunk_id, len(raw), token_count, len(node.embedding),
            )
        except Exception as exc:
            raise RuntimeError(f"Embedding 请求失败（{get_settings().embedding_base_url}）：{exc}") from exc

    if not vector_nodes:
        raise RuntimeError(f"切分完成但没有生成可写入的向量节点：策略={strategy}，source_documents={len(loaded)}，chunks={len(source_nodes)}")

    from pymilvus import MilvusClient

    settings = get_settings()
    token = f"{settings.milvus_user}:{settings.milvus_password}"
    try:
        client = MilvusClient(uri=settings.milvus_uri, token=token, db_name=settings.milvus_database)
        try:
            rows = [
                {
                    "id": node.node_id,
                    "document_id": document_id,
                    "text": node.text,
                    "vector": node.embedding,
                    "user_id": doc["owner"],
                    "filename": doc["filename"],
                }
                for node in vector_nodes
            ]
            insert_result = client.insert(doc["collection_name"], rows)
            returned_ids = insert_result.get("ids", [])
            logger.info(
                "Milvus insert returned: collection=%s expected=%d returned=%d",
                doc["collection_name"], len(vector_nodes), len(returned_ids),
            )
            client.flush(doc["collection_name"])
            inserted_ids = [node.node_id for node in vector_nodes]
            inserted_rows = client.get(doc["collection_name"], ids=inserted_ids, output_fields=["id"])
            verified_ids = {row["id"] for row in inserted_rows}
        finally:
            client.close()
    except Exception as exc:
        logger.exception("Milvus write or verification failed for collection %s", doc["collection_name"])
        raise RuntimeError(f"Milvus 写入或核验失败（{settings.milvus_uri}，数据库 {settings.milvus_database}，集合 {doc['collection_name']}）：{exc}") from exc
    if len(verified_ids) != len(vector_nodes):
        raise RuntimeError(
            f"Milvus 写入核验失败：集合 '{doc['collection_name']}'，切分策略={strategy}，"
            f"source_documents={len(loaded)}，chunks={len(source_nodes)}，"
            f"Embedding 节点={len(vector_nodes)}，insert 返回 ID={len(returned_ids)}，"
            f"按节点 ID 查询到={len(verified_ids)}，"
            f"未找到 IDs={sorted(set(inserted_ids) - verified_ids)}"
        )
    with _get_conn() as conn:  # 连接数据库
        conn.executemany(  # 批量插入文本块
            "INSERT INTO knowledge_chunks (id, document_id, owner, ordinal, text, embedding_text) "
            "VALUES (:id, :document_id, :owner, :ordinal, :text, :embedding_text)",
            chunks,
        )
        conn.execute("UPDATE knowledge_documents SET status = 'completed', error = NULL WHERE id = ?", (document_id,))  # 更新文档状态为已完成


@router.post("/documents/{document_id}/cancel-application")
def cancel_application(document_id: str, principal: tuple[str, Role] = Depends(current_user)) -> dict:
    owner, role = principal
    if role is Role.ADMIN:
        raise HTTPException(status_code=403, detail="仅申请人可以撤销构建申请")
    row = _document_row(document_id, owner, role)
    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail="只有待审批的构建申请可以撤销")
    with _get_conn() as conn:
        result = conn.execute(
            "UPDATE knowledge_documents SET status = 'uploaded', reviewer = NULL, error = NULL WHERE id = ? AND owner = ? AND status = 'pending'",
            (document_id, owner),
        )
    if result.rowcount != 1:
        raise HTTPException(status_code=409, detail="申请状态已变化，请刷新后重试")
    return {"status": "uploaded", "document_id": document_id}


@router.get("/applications")
def list_applications(principal: tuple[str, Role] = Depends(current_user)) -> dict:
    owner, role = principal
    _init_knowledge()
    with _get_conn() as conn:
        if role is Role.ADMIN:
            rows = conn.execute("SELECT * FROM knowledge_documents WHERE status = 'pending' ORDER BY created_at").fetchall()
        else:
            rows = conn.execute("SELECT * FROM knowledge_documents WHERE owner = ? AND status = 'pending' ORDER BY created_at", (owner,)).fetchall()
    return {"applications": [dict(row) for row in rows]}


class ReviewRequest(BaseModel):
    approve: bool


def _build_approved_document(document_id: str) -> None:
    try:
        _process_document(document_id)
    except Exception as exc:
        logger.exception("Approved document indexing failed: %s", document_id)
        with _get_conn() as conn:
            conn.execute("UPDATE knowledge_documents SET status = 'failed', error = ? WHERE id = ?", (str(exc), document_id))


@router.post("/applications/{document_id}/review")
def review_application(document_id: str, req: ReviewRequest, background_tasks: BackgroundTasks, principal: tuple[str, Role] = Depends(current_user)) -> dict:
    """管理员拒绝申请或批准后触发同一套文档索引处理流程。"""
    reviewer, role = principal
    if role is not Role.ADMIN:
        raise HTTPException(status_code=403, detail="仅管理员可审批")
    row = _document_row(document_id, reviewer, role)
    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail="申请已处理")
    if not req.approve:
        with _get_conn() as conn:
            conn.execute("UPDATE knowledge_documents SET status = 'rejected', reviewer = ? WHERE id = ?", (reviewer, document_id))
        return {"status": "rejected"}
    with _get_conn() as conn:
        conn.execute("UPDATE knowledge_documents SET status = 'processing', reviewer = ? WHERE id = ?", (reviewer, document_id))
    background_tasks.add_task(_build_approved_document, document_id)
    return {"status": "processing", "document_id": document_id}


@router.get("/documents/{document_id}/chunks")
def document_chunks(document_id: str, principal: tuple[str, Role] = Depends(current_user)) -> dict:
    owner, role = principal
    _document_row(document_id, owner, role)
    _init_knowledge()
    with _get_conn() as conn:
        rows = conn.execute("SELECT id, document_id, owner AS user_id, ordinal, text, embedding_text FROM knowledge_chunks WHERE document_id = ? ORDER BY ordinal", (document_id,)).fetchall()
    return {"chunks": [dict(row) for row in rows], "count": len(rows)}


@router.delete("/documents/{document_id}")
def delete_document(document_id: str, principal: tuple[str, Role] = Depends(current_user)) -> dict:
    owner, role = principal
    row = _document_row(document_id, owner, role)
    if row["status"] in {"pending", "processing"}:
        raise HTTPException(status_code=409, detail="待审批或处理中不能删除")
    Path(row["path"]).unlink(missing_ok=True)
    if row["status"] == "completed":
        from ...retrieval.vector_store import get_milvus_store
        get_milvus_store(row["collection_name"]).delete(document_id)
    with _get_conn() as conn:
        conn.execute("DELETE FROM knowledge_chunks WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM knowledge_documents WHERE id = ?", (document_id,))
    return {"status": "ok"}


@router.get("/status")
def get_status(
    collection_name: str | None = None,
    principal: tuple[str, Role] = Depends(current_user),
) -> dict[str, Any]:
    owner, role = principal
    _init_knowledge()
    with _get_conn() as conn:
        if role is Role.ADMIN:
            count = conn.execute("SELECT COUNT(*) AS n FROM knowledge_documents").fetchone()["n"]
        else:
            count = conn.execute("SELECT COUNT(*) AS n FROM knowledge_documents WHERE owner = ?", (owner,)).fetchone()["n"]

    try:
        from pymilvus import Collection, DataType, utility

        from .config import _connect_milvus

        _connect_milvus()
        collections = utility.list_collections()
        expected_dimension = int(get_config("embedding_dimension") or get_settings().embedding_dimension)
        expected_fields = {
            "id": DataType.VARCHAR,
            "document_id": DataType.VARCHAR,
            "text": DataType.VARCHAR,
            "vector": DataType.FLOAT_VECTOR,
            "user_id": DataType.VARCHAR,
            "filename": DataType.VARCHAR,
        }
        candidates = [collection_name] if collection_name else collections
        checked_collection = None
        schema_errors = []
        actual_dimension = None
        for candidate in candidates:
            if candidate not in collections:
                continue
            fields = {field.name: field for field in Collection(candidate).schema.fields}
            candidate_errors = []
            for name, expected_type in expected_fields.items():
                if name not in fields:
                    candidate_errors.append(f"缺少必需字段 {name}")
                elif fields[name].dtype != expected_type:
                    candidate_errors.append(f"字段 {name} 类型不匹配")
            if "id" in fields and not fields["id"].is_primary:
                candidate_errors.append("id 字段必须是主键")
            if "id" in fields and fields["id"].auto_id:
                candidate_errors.append("id 字段不能启用 auto_id")
            vector_field = fields.get("vector")
            candidate_dimension = None
            if vector_field is not None:
                candidate_dimension = (getattr(vector_field, "params", None) or {}).get("dim")
                if candidate_dimension != expected_dimension:
                    candidate_errors.append(
                        f"向量维度不匹配：collection={candidate_dimension}，配置={expected_dimension}"
                    )
            if not candidate_errors:
                checked_collection = candidate
                actual_dimension = candidate_dimension
                schema_errors = []
                break
            if not schema_errors:
                checked_collection = candidate
                actual_dimension = candidate_dimension
                schema_errors = candidate_errors
        collection_ready = bool(collection_name and collection_name in collections)
        schema_valid = checked_collection is not None and not schema_errors
        return {
            "ready": schema_valid,
            "milvus_connected": True,
            "collection": checked_collection,
            "collection_ready": collection_ready if collection_name else schema_valid,
            "schema_valid": schema_valid,
            "schema_errors": schema_errors,
            "vector_dimension": actual_dimension,
            "expected_vector_dimension": expected_dimension,
            "collections": collections,
            "document_count": count,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Knowledge base readiness check failed: %s", exc)
        return {
            "ready": False,
            "milvus_connected": False,
            "collection": collection_name,
            "collection_ready": False,
            "schema_valid": False,
            "schema_errors": [],
            "vector_dimension": None,
            "expected_vector_dimension": int(get_config("embedding_dimension") or get_settings().embedding_dimension),
            "collections": [],
            "document_count": count,
            "error": str(exc),
        }
