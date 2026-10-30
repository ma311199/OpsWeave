"""Configuration management endpoints."""

from __future__ import annotations

import httpx
from urllib.parse import urlparse
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...config.database import get_all_configs, update_configs, set_config, get_config
from ...config.settings import get_settings

router = APIRouter()

# Mask API keys in responses (show only last 4 chars)
def _mask_key(value: str) -> str:
    if not value or len(value) <= 4:
        return value
    return f"...{value[-4:]}"


def _unmask_key(value: str, current: str) -> str:
    """If value is masked (starts with ...), return the current value."""
    if value.startswith("..."):
        return current
    return value


class ConfigUpdate(BaseModel):
    """Request body for updating configs."""
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_temperature: float | None = None
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    milvus_uri: str | None = None
    milvus_user: str | None = None
    milvus_password: str | None = None
    milvus_database: str | None = None
    agent_max_iterations: int | None = None
    # Milvus collections (JSON list)
    milvus_collections: list[dict] | None = None


class MilvusCollection(BaseModel):
    """A single Milvus collection configuration."""
    name: str = Field(..., description="Collection name")
    dimension: int = Field(..., ge=1, le=4096, description="Vector dimension")
    metric_type: str = Field(default="L2", description="Metric type: L2, IP, or COSINE")
    index_type: str = Field(default="AUTOINDEX", description="Index type")
    description: str = Field(default="", description="Collection description")


@router.get("/")
def get_configs() -> dict:
    """Get all configurations grouped by category."""
    db_configs = get_all_configs()
    settings = get_settings()
    
    result = {"llm": {}, "embedding": {}, "milvus": {}, "agent": {}}
    
    # LLM
    result["llm"]["base_url"] = db_configs.get("llm_base_url", settings.llm_base_url)
    result["llm"]["api_key"] = _mask_key(db_configs.get("llm_api_key", settings.llm_api_key))
    result["llm"]["model"] = db_configs.get("llm_model", settings.llm_model)
    result["llm"]["temperature"] = float(db_configs.get("llm_temperature", settings.llm_temperature))
    
    # Embedding
    result["embedding"]["base_url"] = db_configs.get("embedding_base_url", settings.embedding_base_url)
    result["embedding"]["api_key"] = _mask_key(db_configs.get("embedding_api_key", settings.embedding_api_key))
    result["embedding"]["model"] = db_configs.get("embedding_model", settings.embedding_model)
    result["embedding"]["dimension"] = int(db_configs.get("embedding_dimension", settings.embedding_dimension))
    
    # Milvus
    result["milvus"]["uri"] = db_configs.get("milvus_uri", settings.milvus_uri)
    result["milvus"]["user"] = db_configs.get("milvus_user", settings.milvus_user)
    result["milvus"]["password"] = _mask_key(db_configs.get("milvus_password", settings.milvus_password))
    result["milvus"]["database"] = db_configs.get("milvus_database", settings.milvus_database)
    # Parse collections JSON
    collections_str = db_configs.get("milvus_collections", "[]")
    try:
        import json
        result["milvus"]["collections"] = json.loads(collections_str)
    except (json.JSONDecodeError, TypeError):
        result["milvus"]["collections"] = []
    
    # Agent
    result["agent"]["max_iterations"] = int(db_configs.get("agent_max_iterations", settings.agent_max_iterations))
    
    return result


@router.put("/")
def update_configs_endpoint(req: ConfigUpdate) -> dict:
    """Update configurations and persist to SQLite."""
    updates = {}
    settings = get_settings()
    
    # LLM
    if req.llm_base_url is not None:
        updates["llm_base_url"] = req.llm_base_url
    if req.llm_api_key is not None:
        current = get_config("llm_api_key") or settings.llm_api_key
        updates["llm_api_key"] = _unmask_key(req.llm_api_key, current)
    if req.llm_model is not None:
        updates["llm_model"] = req.llm_model
    if req.llm_temperature is not None:
        updates["llm_temperature"] = req.llm_temperature
    
    # Embedding
    if req.embedding_base_url is not None:
        updates["embedding_base_url"] = req.embedding_base_url
    if req.embedding_api_key is not None:
        current = get_config("embedding_api_key") or settings.embedding_api_key
        updates["embedding_api_key"] = _unmask_key(req.embedding_api_key, current)
    if req.embedding_model is not None:
        updates["embedding_model"] = req.embedding_model
    if req.embedding_dimension is not None:
        updates["embedding_dimension"] = req.embedding_dimension
    
    # Milvus
    if req.milvus_uri is not None:
        updates["milvus_uri"] = req.milvus_uri
    if req.milvus_user is not None:
        updates["milvus_user"] = req.milvus_user
    if req.milvus_password is not None:
        current = get_config("milvus_password") or settings.milvus_password
        updates["milvus_password"] = _unmask_key(req.milvus_password, current)
    if req.milvus_database is not None:
        updates["milvus_database"] = req.milvus_database
    if req.milvus_collections is not None:
        import json
        updates["milvus_collections"] = json.dumps(req.milvus_collections, ensure_ascii=False)
    
    # Agent
    if req.agent_max_iterations is not None:
        updates["agent_max_iterations"] = req.agent_max_iterations
    
    update_configs(updates)
    
    return {"status": "ok", "message": "配置已保存"}


@router.post("/test/{service}")
async def test_connection(service: str) -> dict:
    """Test connection to a service (llm, embedding, milvus)."""
    if service == "llm":
        return await _test_llm()
    elif service == "embedding":
        return await _test_embedding()
    elif service == "milvus":
        return await _test_milvus()
    else:
        raise HTTPException(status_code=400, detail=f"未知的服务类型: {service}")


async def _test_llm() -> dict:
    """Test LLM connection with a simple chat completion."""
    settings = get_settings()
    client = None
    try:
        client = httpx.AsyncClient(timeout=30.0)
        resp = await client.post(
            f"{settings.llm_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5,
            },
        )
        resp.raise_for_status()
        return {"status": "ok", "message": "LLM 连接正常"}
    except httpx.ConnectError:
        return {"status": "error", "message": "无法连接到 LLM 服务，请检查网络或 Base URL"}
    except httpx.TimeoutException:
        return {"status": "error", "message": "LLM 服务响应超时"}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return {"status": "error", "message": "API Key 无效或未授权"}
        elif e.response.status_code == 404:
            return {"status": "error", "message": f"模型 '{settings.llm_model}' 不存在或接口路径错误"}
        else:
            return {"status": "error", "message": f"LLM 服务返回错误 (HTTP {e.response.status_code})"}
    except Exception as e:
        msg = str(e).lower()
        if "api key" in msg or "unauthorized" in msg:
            return {"status": "error", "message": "API Key 无效"}
        elif "model" in msg or "not found" in msg:
            return {"status": "error", "message": f"模型 '{settings.llm_model}' 不存在"}
        else:
            return {"status": "error", "message": f"LLM 连接失败: {str(e)[:100]}"}
    finally:
        if client:
            await client.aclose()


async def _test_embedding() -> dict:
    """Test embedding connection with a simple embedding request."""
    settings = get_settings()
    client = None
    try:
        client = httpx.AsyncClient(timeout=30.0)
        resp = await client.post(
            f"{settings.embedding_base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {settings.embedding_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.embedding_model,
                "input": ["test"],
            },
        )
        resp.raise_for_status()
        return {"status": "ok", "message": "Embedding 连接正常"}
    except httpx.ConnectError:
        return {"status": "error", "message": "无法连接到 Embedding 服务，请检查网络或 Base URL"}
    except httpx.TimeoutException:
        return {"status": "error", "message": "Embedding 服务响应超时"}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return {"status": "error", "message": "API Key 无效或未授权"}
        elif e.response.status_code == 404:
            return {"status": "error", "message": f"模型 '{settings.embedding_model}' 不存在或接口路径错误"}
        else:
            return {"status": "error", "message": f"Embedding 服务返回错误 (HTTP {e.response.status_code})"}
    except Exception as e:
        msg = str(e).lower()
        if "api key" in msg or "unauthorized" in msg:
            return {"status": "error", "message": "API Key 无效"}
        elif "model" in msg or "not found" in msg:
            return {"status": "error", "message": f"模型 '{settings.embedding_model}' 不存在"}
        else:
            return {"status": "error", "message": f"Embedding 连接失败: {str(e)[:100]}"}
    finally:
        if client:
            await client.aclose()


async def _test_milvus() -> dict:
    """Test Milvus connection."""
    settings = get_settings()
    try:
        from pymilvus import connections, utility
        
        # Parse URI properly
        parsed = urlparse(settings.milvus_uri)
        host = parsed.hostname or settings.milvus_uri.replace("http://", "").replace("https://", "").split(":")[0]
        port = parsed.port or 19530
        
        connections.connect(
            alias="default",
            host=host,
            port=str(port),
            user=settings.milvus_user,
            password=settings.milvus_password,
            db_name=settings.milvus_database,
        )
        collections = utility.list_collections()
        return {
            "status": "ok",
            "message": f"Milvus 连接正常，共 {len(collections)} 个集合",
            "collections": collections,
        }
    except Exception as e:
        msg = str(e).lower()
        if "connection" in msg or "connect" in msg or "refused" in msg or "timeout" in msg:
            return {"status": "error", "message": "无法连接到 Milvus 服务，请检查网络或 URI"}
        elif "authentication" in msg or "unauthorized" in msg or "permission" in msg:
            return {"status": "error", "message": "用户名或密码不正确"}
        elif "type of 'host'" in msg or "host" in msg and "str" in msg:
            return {"status": "error", "message": f"Milvus URI 格式不正确: {settings.milvus_uri}，请使用 http://host:port 格式"}
        else:
            return {"status": "error", "message": f"Milvus 连接失败: {str(e)[:100]}"}


@router.post("/milvus/create-collection")
def create_milvus_collection(collection: MilvusCollection) -> dict:
    """Create a Milvus collection with the specified configuration."""
    settings = get_settings()
    try:
        from pymilvus import connections, Collection, FieldSchema, CollectionSchema, utility
        from pymilvus import DataType
        
        # Connect
        parsed = urlparse(settings.milvus_uri)
        host = parsed.hostname or settings.milvus_uri.replace("http://", "").replace("https://", "").split(":")[0]
        port = parsed.port or 19530
        connections.connect(
            alias="default",
            host=host,
            port=str(port),
            user=settings.milvus_user,
            password=settings.milvus_password,
            db_name=settings.milvus_database,
        )
        
        # Check if collection already exists
        if utility.has_collection(collection.name):
            return {"status": "exists", "message": f"集合 '{collection.name}' 已存在"}
        
        # Create collection
        id_field = FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True)
        vector_field = FieldSchema(
            name="vector", dtype=DataType.FLOAT_VECTOR, dim=collection.dimension
        )
        text_field = FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535)
        metadata_field = FieldSchema(name="metadata", dtype=DataType.JSON)
        
        schema = CollectionSchema(
            fields=[id_field, vector_field, text_field, metadata_field],
            description=collection.description or f"OpsWeave collection: {collection.name}",
        )
        
        milvus_collection = Collection(name=collection.name, schema=schema)
        
        # Create index
        milvus_collection.create_index(
            field_name="vector",
            index_type=collection.index_type,
            metric_type=collection.metric_type,
        )
        
        return {"status": "ok", "message": f"集合 '{collection.name}' 创建成功"}
    except Exception as e:
        msg = str(e).lower()
        if "connection" in msg or "connect" in msg:
            return {"status": "error", "message": "无法连接到 Milvus 服务"}
        elif "already exists" in msg:
            return {"status": "exists", "message": f"集合 '{collection.name}' 已存在"}
        else:
            return {"status": "error", "message": f"创建集合失败: {str(e)[:100]}"}


@router.delete("/milvus/collections/{name}")
def delete_milvus_collection(name: str) -> dict:
    """Delete a Milvus collection."""
    settings = get_settings()
    try:
        from pymilvus import connections, utility
        
        parsed = urlparse(settings.milvus_uri)
        host = parsed.hostname or settings.milvus_uri.replace("http://", "").replace("https://", "").split(":")[0]
        port = parsed.port or 19530
        connections.connect(
            alias="default",
            host=host,
            port=str(port),
            user=settings.milvus_user,
            password=settings.milvus_password,
            db_name=settings.milvus_database,
        )
        
        if not utility.has_collection(name):
            return {"status": "error", "message": f"集合 '{name}' 不存在"}
        
        utility.drop_collection(name)
        return {"status": "ok", "message": f"集合 '{name}' 已删除"}
    except Exception as e:
        msg = str(e).lower()
        if "connection" in msg or "connect" in msg:
            return {"status": "error", "message": "无法连接到 Milvus 服务"}
        else:
            return {"status": "error", "message": f"删除集合失败: {str(e)[:100]}"}


def _connect_milvus():
    """Helper: Connect to Milvus using current settings."""
    settings = get_settings()
    from pymilvus import connections
    from urllib.parse import urlparse

    parsed = urlparse(settings.milvus_uri)
    host = parsed.hostname or settings.milvus_uri.replace("http://", "").replace("https://", "").split(":")[0]
    port = parsed.port or 19530
    connections.connect(
        alias="default",
        host=host,
        port=str(port),
        user=settings.milvus_user,
        password=settings.milvus_password,
        db_name=settings.milvus_database,
    )


@router.get("/milvus/collections")
def list_milvus_collections() -> dict:
    """List all collections in the current database with details."""
    try:
        from pymilvus import utility, Collection

        _connect_milvus()

        collections = utility.list_collections()
        result = []
        for name in collections:
            info = {"name": name}
            if utility.has_collection(name):
                try:
                    col = Collection(name)
                    info["row_count"] = col.num_entities
                    info["description"] = col.description
                    info["fields"] = [
                        {
                            "name": f.name,
                            "dtype": str(f.dtype),
                            "is_primary": f.is_primary,
                            "auto_id": f.auto_id,
                        }
                        for f in col.fields
                    ]
                    try:
                        info["index"] = [
                            {
                                "field": idx.field_name,
                                "index_type": idx.index_type,
                                "metric_type": idx.metric_type,
                            }
                            for idx in col.indexes
                        ]
                    except Exception:
                        info["index"] = []
                except Exception:
                    info["row_count"] = 0
                    info["description"] = ""
                    info["fields"] = []
                    info["index"] = []
            result.append(info)

        return {"status": "ok", "collections": result}
    except Exception as e:
        msg = str(e).lower()
        if "connection" in msg or "connect" in msg:
            return {"status": "error", "message": "无法连接到 Milvus 服务"}
        elif "database" in msg or "db_name" in msg or "not found" in msg:
            return {"status": "error", "message": f"数据库 '{get_settings().milvus_database}' 不存在"}
        else:
            return {"status": "error", "message": f"获取集合列表失败: {str(e)[:100]}"}


@router.put("/milvus/collections/{name}")
def update_milvus_collection(name: str, collection: MilvusCollection) -> dict:
    """Update a collection by deleting and recreating it (data will be lost)."""
    try:
        from pymilvus import Collection, utility, FieldSchema, CollectionSchema, DataType

        _connect_milvus()

        if not utility.has_collection(name):
            return {"status": "error", "message": f"集合 '{name}' 不存在"}

        # Drop old collection
        utility.drop_collection(name)

        # Recreate with new configuration
        id_field = FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True)
        vector_field = FieldSchema(
            name="vector", dtype=DataType.FLOAT_VECTOR, dim=collection.dimension
        )
        text_field = FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535)
        metadata_field = FieldSchema(name="metadata", dtype=DataType.JSON)

        schema = CollectionSchema(
            fields=[id_field, vector_field, text_field, metadata_field],
            description=collection.description or f"OpsWeave collection: {collection.name}",
        )

        col = Collection(name=collection.name, schema=schema)
        col.create_index(
            field_name="vector",
            index_type=collection.index_type,
            metric_type=collection.metric_type,
        )

        return {"status": "ok", "message": f"集合 '{collection.name}' 已更新（数据已清空，请重新导入）"}
    except Exception as e:
        msg = str(e).lower()
        if "connection" in msg or "connect" in msg:
            return {"status": "error", "message": "无法连接到 Milvus 服务"}
        elif "already exists" in msg:
            return {"status": "error", "message": f"集合 '{name}' 已存在，请先删除"}
        else:
            return {"status": "error", "message": f"更新集合失败: {str(e)[:100]}"}
