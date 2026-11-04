from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport

from ..auth.permissions import PermissionChecker, ResourceType, Role
from ..config.database import get_config
from ..config.settings import get_settings
_LOCAL_SERVER_ID = "local"
_LOCAL_SERVER = {"transport": "stdio", "command": sys.executable, "args": ["-m", "opsweave.tools.mcp_server"]}


def _remote_servers() -> list[dict[str, Any]]:
    raw = get_config("mcp_servers")
    if not raw:
        return []
    try:
        servers = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [server for server in servers if isinstance(server, dict) and server.get("enabled", True)]


def _transport_for(server: dict[str, Any]):
    if server["transport"] == "stdio":
        return StdioTransport(
            command=server["command"],
            args=server.get("args", []),
            env=server.get("env", {}),
        )
    headers = server.get("headers", {})
    token = server.get("token", "")
    if token:
        headers = {**headers, "Authorization": f"Bearer {token}"}
    return StreamableHttpTransport(url=server["url"], headers=headers)


async def _client_for(server: dict[str, Any], stack: AsyncExitStack):
    client = Client(_transport_for(server))
    return await stack.enter_async_context(client)


async def _list_tools() -> list[dict[str, Any]]:
    async with AsyncExitStack() as stack:
        clients: list[tuple[str, Any]] = []
        local_client = await _client_for(_LOCAL_SERVER, stack)
        clients.append((_LOCAL_SERVER_ID, local_client))
        for server in _remote_servers():
            clients.append((server["id"], await _client_for(server, stack)))
        tools = []
        for server_id, client in clients:
            for tool in await client.list_tools():
                tools.append({
                    "server_id": server_id,
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                    "annotations": getattr(tool, "annotations", None),
                })
        return tools


async def _call_tool(server_id: str, name: str, arguments: dict, role: Role, user_id: str):
    if name == "search_knowledge":
        PermissionChecker.default_rules().require(role, ResourceType.RETRIEVAL_INDEX)
    if server_id == _LOCAL_SERVER_ID:
        if name == "search_knowledge":
            token = get_settings().mcp_token or os.getenv("MCP_TOKEN", "")
            arguments = {**arguments, "user_id": user_id, "token": token}
            arguments.setdefault("top_k", get_settings().retriever_top_k)
        server = _LOCAL_SERVER
    else:
        server = next((item for item in _remote_servers() if item["id"] == server_id), None)
        if server is None:
            raise ValueError(f"Unknown MCP server: {server_id}")

    async with AsyncExitStack() as stack:
        client = await _client_for(server, stack)
        result = await client.call_tool(name, arguments)
    payload = getattr(result, "structured_content", None)
    if payload is None:
        text = "\n".join(item.text for item in result.content if hasattr(item, "text"))
        try:
            payload = json.loads(text) if text else ""
        except json.JSONDecodeError:
            payload = text
    return payload if payload is not None else ""


async def _test_server(server: dict[str, Any]) -> list[dict[str, Any]]:
    async with AsyncExitStack() as stack:
        client = await _client_for(server, stack)
        tools = await client.list_tools()
    return [{"name": tool.name, "description": tool.description, "input_schema": tool.inputSchema} for tool in tools]


def list_tools() -> list[dict[str, Any]]:
    return asyncio.run(_list_tools())


def call_tool(server_id: str, name: str, arguments: dict, role: Role, user_id: str):
    return asyncio.run(_call_tool(server_id, name, arguments, role, user_id))


def test_server(server: dict[str, Any]) -> list[dict[str, Any]]:
    return asyncio.run(_test_server(server))
