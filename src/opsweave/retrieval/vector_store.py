"""Milvus vector store configuration.

Connects to Milvus via pymilvus with password authentication.
"""

from __future__ import annotations

from llama_index.vector_stores.milvus import MilvusVectorStore

from ..config.settings import get_settings


def get_milvus_store(collection_name: str = "opsweave") -> MilvusVectorStore:
    """Create a MilvusVectorStore instance from settings.

    Args:
        collection_name: Name of the Milvus collection to use.

    Returns:
        MilvusVectorStore configured with auth credentials.
    """
    settings = get_settings()
    # Milvus token format: "username:password"
    token = f"{settings.milvus_user}:{settings.milvus_password}"
    return MilvusVectorStore(
        uri=settings.milvus_uri,
        token=token,
        collection_name=collection_name,
        overwrite=False,
        dim=settings.embedding_dimension,
        enable_dense=True,
    )
