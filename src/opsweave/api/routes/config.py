"""Configuration management endpoints."""

from __future__ import annotations

import json
import os
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from ...agents.retrieval_pipeline import clear_retrieval_index_cache
from ...config.database import get_all_configs, get_config, set_config, update_configs
from ...config.settings import get_settings
from ..auth import require_admin

router = APIRouter(dependencies=[Depends(require_admin)])


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
    embedding_max_tokens: int | None = Field(default=None, ge=1, le=1000000)
    milvus_uri: str | None = None
    milvus_user: str | None = None
    milvus_password: str | None = None
    milvus_database: str | None = None
    agent_max_iterations: int | None = None
    mcp_servers: list[dict] | None = None
    # Milvus collections (JSON list)
    milvus_collections: list[dict] | None = None


class MilvusField(BaseModel):
    name: str = Field(
        ..., min_length=1, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"
    )
    data_type: str = Field(..., description="Milvus scalar or vector data type")
    description: str = Field(default="", max_length=256)
    is_primary: bool = False
    auto_id: bool = False
    max_length: int | None = Field(default=None, ge=1, le=65535)
    dimension: int | None = Field(default=None, ge=1, le=32768)
    index_type: str = "AUTOINDEX"
    metric_type: str = "COSINE"
    index_params: dict[str, int | float | str] = Field(default_factory=dict)


class MilvusCollection(BaseModel):
    """A single Milvus collection configuration."""

    name: str = Field(..., description="Collection name")
    fields: list[MilvusField] = Field(..., min_length=2, max_length=64)
    description: str = Field(default="", description="Collection description")


class MilvusCollectionDescription(BaseModel):
    description: str = Field(default="", max_length=256)

    model_config = {"extra": "ignore"}


@router.get("/")
def get_configs() -> dict:
    """Get all configurations grouped by category."""
    db_configs = get_all_configs()
    settings = get_settings()

    result = {"llm": {}, "embedding": {}, "milvus": {}, "agent": {}}

    # LLM
    result["llm"]["base_url"] = db_configs.get("llm_base_url", settings.llm_base_url)
    result["llm"]["api_key"] = _mask_key(settings.llm_api_key)
    result["llm"]["model"] = db_configs.get("llm_model", settings.llm_model)
    result["llm"]["temperature"] = float(
        db_configs.get("llm_temperature", settings.llm_temperature)
    )

    # Embedding
    result["embedding"]["base_url"] = db_configs.get(
        "embedding_base_url", settings.embedding_base_url
    )
    result["embedding"]["api_key"] = _mask_key(settings.embedding_api_key)
    result["embedding"]["model"] = db_configs.get(
        "embedding_model", settings.embedding_model
    )
    result["embedding"]["dimension"] = int(
        db_configs.get("embedding_dimension", settings.embedding_dimension)
    )
    result["embedding"]["max_tokens"] = int(
        db_configs.get("embedding_max_tokens", 8192)
    )

    # Milvus
    result["milvus"]["uri"] = db_configs.get("milvus_uri", settings.milvus_uri)
    result["milvus"]["user"] = db_configs.get("milvus_user", settings.milvus_user)
    result["milvus"]["password"] = _mask_key(settings.milvus_password)
    result["milvus"]["database"] = db_configs.get(
        "milvus_database", settings.milvus_database
    )
    # Parse collections JSON
    collections_str = db_configs.get("milvus_collections", "[]")
    try:
        import json

        result["milvus"]["collections"] = json.loads(collections_str)
    except (json.JSONDecodeError, TypeError):
        result["milvus"]["collections"] = []

    # Agent
    result["agent"]["max_iterations"] = int(
        db_configs.get("agent_max_iterations", settings.agent_max_iterations)
    )
    try:
        result["mcp_servers"] = json.loads(db_configs.get("mcp_servers", "[]"))
    except (json.JSONDecodeError, TypeError):
        result["mcp_servers"] = []
    for server in result["mcp_servers"]:
        if server.get("token"):
            server["token"] = _mask_key(server["token"])

    return result


@router.put("/")
def update_configs_endpoint(req: ConfigUpdate) -> dict:
    """Update configurations and persist to SQLite."""
    updates = {}

    # LLM
    if req.llm_base_url is not None:
        updates["llm_base_url"] = req.llm_base_url
    if (
        req.llm_api_key is not None
        and req.llm_api_key != "..."
        and not req.llm_api_key.startswith("...")
    ):
        os.environ["LLM_API_KEY"] = req.llm_api_key
        get_settings.cache_clear()
    if req.llm_model is not None:
        updates["llm_model"] = req.llm_model
    if req.llm_temperature is not None:
        updates["llm_temperature"] = req.llm_temperature

    # Embedding
    if req.embedding_base_url is not None:
        updates["embedding_base_url"] = req.embedding_base_url
    if (
        req.embedding_api_key is not None
        and req.embedding_api_key != "..."
        and not req.embedding_api_key.startswith("...")
    ):
        os.environ["EMBEDDING_API_KEY"] = req.embedding_api_key
        get_settings.cache_clear()
    if req.embedding_model is not None:
        updates["embedding_model"] = req.embedding_model
    if req.embedding_dimension is not None:
        updates["embedding_dimension"] = req.embedding_dimension
    if req.embedding_max_tokens is not None:
        updates["embedding_max_tokens"] = req.embedding_max_tokens

    # Milvus
    if req.milvus_uri is not None:
        updates["milvus_uri"] = req.milvus_uri
    if req.milvus_user is not None:
        updates["milvus_user"] = req.milvus_user
    if (
        req.milvus_password is not None
        and req.milvus_password != "..."
        and not req.milvus_password.startswith("...")
    ):
        os.environ["MILVUS_PASSWORD"] = req.milvus_password
        get_settings.cache_clear()
    if req.milvus_database is not None:
        updates["milvus_database"] = req.milvus_database
    if req.milvus_collections is not None:
        import json

        updates["milvus_collections"] = json.dumps(
            req.milvus_collections, ensure_ascii=False
        )

    # Agent
    if req.agent_max_iterations is not None:
        updates["agent_max_iterations"] = req.agent_max_iterations
    if req.mcp_servers is not None:
        current_servers = json.loads(get_config("mcp_servers") or "[]")
        current_by_id = {server["id"]: server for server in current_servers}
        servers = [
            McpServerConfig.model_validate(server).model_dump()
            for server in req.mcp_servers
        ]
        if len({server["id"] for server in servers}) != len(servers):
            raise HTTPException(status_code=400, detail="MCP Server ID 不能重复")
        for server in servers:
            if server["token"].startswith("..."):
                server["token"] = current_by_id.get(server["id"], {}).get("token", "")
        updates["mcp_servers"] = json.dumps(servers, ensure_ascii=False)

    update_configs(updates)
    get_settings.cache_clear()
    # Milvus/Embedding 配置变化会使已缓存的直连检索索引失效，需清空重建
    if any(key.startswith(("milvus_", "embedding_")) for key in updates):
        clear_retrieval_index_cache()

    return {"status": "ok", "message": "配置已保存"}


class McpServerConfig(BaseModel):
    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=128)
    transport: str = Field(default="streamable-http", pattern=r"^streamable-http$")
    url: str = Field(..., min_length=1, max_length=2048)
    token: str = ""
    enabled: bool = True

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" and parsed.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError("MCP URL must use HTTPS unless connecting to localhost")
        return value

    model_config = {"extra": "forbid"}


@router.post("/mcp/test")
def test_mcp_server(req: McpServerConfig) -> dict:
    from ...tools.mcp_client import test_server

    server = req.model_dump()
    if server["token"].startswith("..."):
        current_servers = json.loads(get_config("mcp_servers") or "[]")
        current = next(
            (item for item in current_servers if item.get("id") == server["id"]), {}
        )
        server["token"] = current.get("token", "")

    try:
        tools = test_server(server)
        return {
            "status": "ok",
            "message": f"连接成功，发现 {len(tools)} 个工具",
            "tools": tools,
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)[:300]}


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
        return {
            "status": "error",
            "message": "无法连接到 LLM 服务，请检查网络或 Base URL",
        }
    except httpx.TimeoutException:
        return {"status": "error", "message": "LLM 服务响应超时"}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return {"status": "error", "message": "API Key 无效或未授权"}
        elif e.response.status_code == 404:
            return {
                "status": "error",
                "message": f"模型 '{settings.llm_model}' 不存在或接口路径错误",
            }
        else:
            return {
                "status": "error",
                "message": f"LLM 服务返回错误 (HTTP {e.response.status_code})",
            }
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
        return {
            "status": "error",
            "message": "无法连接到 Embedding 服务，请检查网络或 Base URL",
        }
    except httpx.TimeoutException:
        return {"status": "error", "message": "Embedding 服务响应超时"}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return {"status": "error", "message": "API Key 无效或未授权"}
        elif e.response.status_code == 404:
            return {
                "status": "error",
                "message": f"模型 '{settings.embedding_model}' 不存在或接口路径错误",
            }
        else:
            return {
                "status": "error",
                "message": f"Embedding 服务返回错误 (HTTP {e.response.status_code})",
            }
    except Exception as e:
        msg = str(e).lower()
        if "api key" in msg or "unauthorized" in msg:
            return {"status": "error", "message": "API Key 无效"}
        elif "model" in msg or "not found" in msg:
            return {
                "status": "error",
                "message": f"模型 '{settings.embedding_model}' 不存在",
            }
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
        host = (
            parsed.hostname
            or settings.milvus_uri.replace("http://", "")
            .replace("https://", "")
            .split(":")[0]
        )
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
        if (
            "connection" in msg
            or "connect" in msg
            or "refused" in msg
            or "timeout" in msg
        ):
            return {
                "status": "error",
                "message": "无法连接到 Milvus 服务，请检查网络或 URI",
            }
        elif "authentication" in msg or "unauthorized" in msg or "permission" in msg:
            return {"status": "error", "message": "用户名或密码不正确"}
        elif "type of 'host'" in msg or "host" in msg and "str" in msg:
            return {
                "status": "error",
                "message": f"Milvus URI 格式不正确: {settings.milvus_uri}，请使用 http://host:port 格式",
            }
        else:
            return {"status": "error", "message": f"Milvus 连接失败: {str(e)[:100]}"}


@router.post("/milvus/create-collection")
def create_milvus_collection(collection: MilvusCollection) -> dict:
    """Create a Milvus collection with the specified configuration."""
    settings = get_settings()
    try:
        from pymilvus import (
            Collection,
            CollectionSchema,
            DataType,
            FieldSchema,
            connections,
            utility,
        )

        # Connect
        parsed = urlparse(settings.milvus_uri)
        host = (
            parsed.hostname
            or settings.milvus_uri.replace("http://", "")
            .replace("https://", "")
            .split(":")[0]
        )
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

        # Build the requested schema from user-defined fields.
        supported_types = {
            "BOOL": DataType.BOOL,
            "INT8": DataType.INT8,
            "INT16": DataType.INT16,
            "INT32": DataType.INT32,
            "INT64": DataType.INT64,
            "FLOAT": DataType.FLOAT,
            "DOUBLE": DataType.DOUBLE,
            "VARCHAR": DataType.VARCHAR,
            "JSON": DataType.JSON,
            "FLOAT_VECTOR": DataType.FLOAT_VECTOR,
            "BINARY_VECTOR": DataType.BINARY_VECTOR,
        }
        names = [field.name for field in collection.fields]
        if len(names) != len(set(names)):
            raise ValueError("字段名称不能重复")
        primary_fields = [field for field in collection.fields if field.is_primary]
        vector_fields = [
            field
            for field in collection.fields
            if field.data_type in {"FLOAT_VECTOR", "BINARY_VECTOR"}
        ]
        if len(primary_fields) != 1 or len(vector_fields) < 1:
            raise ValueError("必须且只能设置一个主键，并至少设置一个向量字段")
        if primary_fields[0].auto_id and primary_fields[0].data_type != "INT64":
            raise ValueError("自动生成主键仅支持 INT64")
        if primary_fields[0].data_type not in {"INT64", "VARCHAR"}:
            raise ValueError("Milvus 主键仅支持 INT64 或 VARCHAR")
        fields = []
        for field in collection.fields:
            if field.data_type not in supported_types:
                raise ValueError(f"不支持的数据类型: {field.data_type}")
            kwargs = {
                "name": field.name,
                "dtype": supported_types[field.data_type],
                "description": field.description,
            }
            if field.data_type == "VARCHAR":
                if field.max_length is None:
                    raise ValueError(f"VARCHAR 字段 {field.name} 必须设置最大长度")
                kwargs["max_length"] = field.max_length
            if field.data_type in {"FLOAT_VECTOR", "BINARY_VECTOR"}:
                if field.dimension is None:
                    raise ValueError(f"向量字段 {field.name} 必须设置维度")
                if field.data_type == "BINARY_VECTOR" and field.dimension % 8 != 0:
                    raise ValueError(
                        f"二进制向量字段 {field.name} 的维度必须是 8 的倍数"
                    )
                kwargs["dim"] = field.dimension
            if field.is_primary:
                kwargs["is_primary"] = True
                kwargs["auto_id"] = field.auto_id
            fields.append(FieldSchema(**kwargs))

        schema = CollectionSchema(
            fields=fields,
            description=collection.description,
        )

        milvus_collection = Collection(name=collection.name, schema=schema)
        if collection.description:
            descriptions = get_config("milvus_collection_descriptions") or "{}"
            try:
                description_overrides = json.loads(descriptions)
            except ValueError:
                description_overrides = {}
            description_overrides[collection.name] = collection.description
            set_config(
                "milvus_collection_descriptions",
                json.dumps(description_overrides, ensure_ascii=False),
                "milvus",
            )

        # Create vector and scalar indexes using each field's configured type.
        for field in collection.fields:
            if field.data_type in {"FLOAT_VECTOR", "BINARY_VECTOR"}:
                metric = field.metric_type
                if field.data_type == "BINARY_VECTOR" and metric not in {
                    "HAMMING",
                    "JACCARD",
                }:
                    raise ValueError("二进制向量仅支持 HAMMING 或 JACCARD 度量")
                if field.data_type == "FLOAT_VECTOR" and metric not in {
                    "L2",
                    "IP",
                    "COSINE",
                }:
                    raise ValueError("浮点向量仅支持 L2、IP 或 COSINE 度量")
                milvus_collection.create_index(
                    field_name=field.name,
                    index_params={
                        "index_type": field.index_type,
                        "metric_type": metric,
                        "params": field.index_params,
                    },
                )
            elif field.data_type not in {"BOOL", "JSON"}:
                milvus_collection.create_index(
                    field_name=field.name,
                    index_params={
                        "index_type": field.index_type,
                        "params": field.index_params,
                    },
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
        host = (
            parsed.hostname
            or settings.milvus_uri.replace("http://", "")
            .replace("https://", "")
            .split(":")[0]
        )
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
        # 清除该 collection 的直连检索索引缓存，避免继续引用已删除的集合
        clear_retrieval_index_cache(name)
        descriptions = get_config("milvus_collection_descriptions") or "{}"
        try:
            description_overrides = json.loads(descriptions)
        except ValueError:
            description_overrides = {}
        if name in description_overrides:
            del description_overrides[name]
            set_config(
                "milvus_collection_descriptions",
                json.dumps(description_overrides, ensure_ascii=False),
                "milvus",
            )
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
    from urllib.parse import urlparse

    from pymilvus import connections

    parsed = urlparse(settings.milvus_uri)
    host = (
        parsed.hostname
        or settings.milvus_uri.replace("http://", "")
        .replace("https://", "")
        .split(":")[0]
    )
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
        from pymilvus import Collection, utility

        _connect_milvus()
        saved_descriptions = get_config("milvus_collection_descriptions") or "{}"
        try:
            description_overrides = json.loads(saved_descriptions)
        except ValueError:
            description_overrides = {}

        collections = utility.list_collections()
        result = []
        for name in collections:
            info = {"name": name, "description": description_overrides.get(name, "")}
            if utility.has_collection(name):
                try:
                    col = Collection(name)
                    info["description"] = (
                        description_overrides.get(name) or col.description or ""
                    )
                    try:
                        info["row_count"] = col.num_entities
                    except Exception:
                        info["row_count"] = 0
                    info["fields"] = [
                        {
                            "name": f.name,
                            "dtype": getattr(f.dtype, "name", str(f.dtype)),
                            "description": getattr(f, "description", "") or "",
                            "is_primary": f.is_primary,
                            "auto_id": f.auto_id,
                            "params": getattr(f, "params", {}) or {},
                        }
                        for f in col.schema.fields
                    ]
                    try:
                        info["index"] = [
                            {
                                "field": idx.field_name,
                                "index_type": idx.params.get(
                                    "index_type", idx.index_type
                                ),
                                "metric_type": idx.params.get(
                                    "metric_type", idx.params.get("metric", "")
                                ),
                            }
                            for idx in col.indexes
                        ]
                    except Exception:
                        info["index"] = []
                except Exception:
                    info["row_count"] = 0
                    info["fields"] = []
                    info["index"] = []
            result.append(info)

        return {"status": "ok", "collections": result}
    except Exception as e:
        msg = str(e).lower()
        if "connection" in msg or "connect" in msg:
            return {"status": "error", "message": "无法连接到 Milvus 服务"}
        elif "database" in msg or "db_name" in msg or "not found" in msg:
            return {
                "status": "error",
                "message": f"数据库 '{get_settings().milvus_database}' 不存在",
            }
        else:
            return {"status": "error", "message": f"获取集合列表失败: {str(e)[:100]}"}


@router.put("/milvus/collections/{name}")
def update_milvus_collection(name: str, payload: MilvusCollectionDescription) -> dict:
    """Update the collection description without changing its schema or data."""
    try:
        from pymilvus import utility

        _connect_milvus()

        if not utility.has_collection(name):
            return {"status": "error", "message": f"集合 '{name}' 不存在"}

        descriptions = get_config("milvus_collection_descriptions") or "{}"
        try:
            description_overrides = json.loads(descriptions)
        except ValueError:
            description_overrides = {}
        description_overrides[name] = payload.description
        set_config(
            "milvus_collection_descriptions",
            json.dumps(description_overrides, ensure_ascii=False),
            "milvus",
        )
        return {"status": "ok", "message": f"集合 '{name}' 描述已更新"}
    except Exception as e:
        msg = str(e).lower()
        if "connection" in msg or "connect" in msg:
            return {"status": "error", "message": "无法连接到 Milvus 服务"}
        elif "already exists" in msg:
            return {"status": "error", "message": f"集合 '{name}' 已存在，请先删除"}
        else:
            return {"status": "error", "message": f"更新集合失败: {str(e)[:100]}"}
