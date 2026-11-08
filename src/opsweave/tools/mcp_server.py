from __future__ import annotations

import os
import secrets

from fastmcp import FastMCP

from ..auth.permissions import PermissionChecker, ResourceType, Role
from ..config.settings import get_settings

mcp = FastMCP("OpsWeave Operations Tools")
_checker = PermissionChecker.default_rules()


def _require_mcp_token(token: str | None) -> None:
    expected = get_settings().mcp_token or os.getenv("MCP_TOKEN", "")
    if not expected:
        raise PermissionError("MCP_TOKEN is not configured")
    if not token or not secrets.compare_digest(token, expected):
        raise PermissionError("Invalid MCP token")


@mcp.tool()
def search_knowledge(
    query: str, top_k: int = 5, user_id: str = "", token: str = ""
) -> list[dict[str, str | float]]:
    """Search the OpsWeave operational knowledge base."""
    _require_mcp_token(token)
    if not user_id:
        raise PermissionError("Authenticated user identity is required")
    user_role = Role.VIEWER
    _checker.require(user_role, ResourceType.RETRIEVAL_INDEX)
    if not query.strip():
        raise ValueError("query must not be empty")
    if not 1 <= top_k <= 20:
        raise ValueError("top_k must be between 1 and 20")

    from ..retrieval.retriever import Retriever

    retriever = Retriever()
    retriever.build_index(collection_name="opsweave")
    results = retriever.retrieve(
        query=query, top_k=top_k, role=user_role, user_id=user_id
    )
    return [
        {"source": item.source, "score": round(item.score, 4), "text": item.text}
        for item in results
    ]


if __name__ == "__main__":
    mcp.run()
