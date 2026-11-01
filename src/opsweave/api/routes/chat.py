"""Chat endpoints with WebSocket streaming for agent responses."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ...auth.permissions import Role
from ..agents import run_agent
from ..auth import websocket_role
from ..user_store import user_for_token

router = APIRouter()


@router.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket) -> None:
    """WebSocket endpoint for streaming agent chat responses.

    Protocol (JSON messages):
    Client → Server: {"role": "admin", "query": "问题内容"}
    Server → Client: {"type": "thinking", "content": "..."}
                     {"type": "tool", "tool": "knowledge_search", "content": "..."}
                     {"type": "clarify", "content": "..."} 或 {"type": "answer", "content": "..."}
                     {"type": "done"}
    """
    try:
        role = await websocket_role(websocket)
    except Exception:
        await websocket.close(code=4401)
        return
    if not isinstance(role, Role):
        await websocket.close(code=4401)
        return

    await websocket.accept()

    try:
        data = await websocket.receive_text()
        msg = json.loads(data)
        query = msg.get("query", "")


        await websocket.send_json({"type": "thinking", "content": "正在分析问题..."})
        token = websocket.cookies.get("opsweave_session")
        session_user = user_for_token(token)
        if not session_user:
            await websocket.close(code=4401)
            return
        state = await asyncio.to_thread(run_agent, query, role, session_user[0])
        for call in state.get("tool_calls", []):
            await websocket.send_json({
                "type": "tool",
                "server_id": call["server_id"],
                "tool": call["name"],
                "content": "工具调用完成",
            })
        if state.get("route") == "clarify":
            await websocket.send_json({"type": "clarify", "content": state["answer"]})
        else:
            await websocket.send_json({"type": "answer", "content": state["answer"]})
        await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "content": str(e)})
            await websocket.close()
        except Exception:
            pass
