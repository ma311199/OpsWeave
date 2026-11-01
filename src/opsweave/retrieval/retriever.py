"""LlamaIndex-based retrieval tool for Milvus.

Builds a VectorStoreIndex on top of Milvus and exposes a simple
retrieve() interface for the agent to use.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.schema import NodeRelationship, TextNode
from llama_index.core.vector_stores import MetadataFilter, MetadataFilters

from ..auth.permissions import PermissionChecker, ResourceType, Role
from ..config.settings import get_settings
from .embeddings import OpenAICompatEmbedding
from .vector_store import get_milvus_store


@dataclass
class RetrievalResult:
    """A single retrieved document chunk."""

    text: str
    score: float
    source: str = ""


@dataclass
class Retriever:
    """Milvus-backed vector retriever using LlamaIndex."""

    index: VectorStoreIndex | None = None
    permission_checker: PermissionChecker = field(default_factory=PermissionChecker.default_rules)

    def __post_init__(self) -> None:
        """初始化检索配置与 embedding 客户端，供建索引和查询共用。"""
        self._settings = get_settings()
        self._embedding = OpenAICompatEmbedding.from_settings()

    @property
    def is_ready(self) -> bool:
        return self.index is not None

    def build_index(
        self,
        documents_path: str | None = None,
        collection_name: str = "opsweave",
    ) -> None:
        """Build or connect to a Milvus collection.

        Args:
            documents_path: Path to a directory of documents (txt, md, pdf, etc.).
                            If None, assumes the collection already exists in Milvus.
            collection_name: Milvus collection name.
        """
        # 有本地文档目录时读入并切分后写入；否则只连接现有 collection。
        vector_store = get_milvus_store(collection_name=collection_name)

        if documents_path:
            reader = SimpleDirectoryReader(documents_path)
            nodes = reader.load_data(
                transforms=[],  # skip default transformations
            )
            # Re-split nodes with configured chunk size
            from llama_index.core.node_parser import SentenceSplitter

            splitter = SentenceSplitter(
                chunk_size=self._settings.retriever_chunk_size,
                chunk_overlap=self._settings.retriever_chunk_overlap,
            )
            nodes = splitter.get_nodes_from_documents(
                [self._to_document(node) for node in nodes]
            )
            # Add relationship metadata
            for node in nodes:
                node.relationships[NodeRelationship.SOURCE] = (
                    node.metadata.get("file_path", "unknown")
                )
            self.index = VectorStoreIndex.from_documents(
                nodes,
                embedding=self._embedding,
                vector_store=vector_store,
            )
        else:
            self.index = VectorStoreIndex.from_vector_store(
                vector_store,
                embedding=self._embedding,
            )

    @staticmethod
    def _to_document(node: TextNode) -> TextNode:
        return node

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        role: Role = Role.ADMIN,
        user_id: str | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve relevant document chunks for a query.

        Args:
            query: Natural language query.
            top_k: Number of results to return. Defaults to settings value.
            role: Caller's role, checked against permission rules.

        Returns:
            List of RetrievalResult sorted by relevance.
        """
        if not self.is_ready:
            raise RuntimeError("Retriever index not built. Call build_index() first.")

        self.permission_checker.require(role, ResourceType.RETRIEVAL_INDEX)

        # 普通用户只能检索带有自身 user_id 元数据的向量。
        top_k = top_k or self._settings.retriever_top_k
        filters = None
        if role is not Role.ADMIN:
            if not user_id:
                raise PermissionError("Authenticated user identity is required for retrieval")
            filters = MetadataFilters(filters=[MetadataFilter(key="user_id", value=user_id)])
        retriever = self.index.as_retriever(similarity_top_k=top_k, filters=filters)
        nodes = retriever.retrieve(query)

        return [
            RetrievalResult(
                text=node.metadata.get("text", node.get_content()),
                score=float(node.score or 0.0),
                source=node.metadata.get("filename", node.metadata.get("file_path", "unknown")), 
            )
            for node in nodes
        ]
