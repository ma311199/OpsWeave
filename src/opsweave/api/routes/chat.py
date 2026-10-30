"""Chat endpoints with WebSocket streaming for agent responses."""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ...auth.permissions import PermissionChecker, ResourceType, Role

router = APIRouter()
_checker = PermissionChecker.default_rules()


@router.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket) -> None:
    """WebSocket endpoint for streaming agent chat responses.

    Protocol (JSON messages):
    Client → Server: {"role": "admin", "query": "问题内容"}
    Server → Client: {"type": "thinking", "content": "..."}
                     {"type": "tool", "tool": "retrieve", "content": "..."}
                     {"type": "answer", "content": "..."}
                     {"type": "done"}
    """
    await websocket.accept()

    try:
        # Receive initial message with role and query
        data = await websocket.receive_text()
        msg = json.loads(data)
        role_str = msg.get("role", "admin")
        query = msg.get("query", "")

        try:
            role = Role(role_str)
        except ValueError:
            await websocket.send_json({"type": "error", "content": f"Invalid role: {role_str}"})
            await websocket.close()
            return

        # Send thinking status
        await websocket.send_json({"type": "thinking", "content": "正在分析问题..."})

        # For now, delegate to LLM directly.
        # In production, this will be replaced by LangGraph agent.
        from ...llm.client import get_llm

        llm = get_llm()

        # Simple flow: LLM decides if retrieval needed
        decision_prompt = (
            f"你是一个运维助手。用户问题：{query}\n\n"
            f"请判断是否需要检索知识库。"
            f"如果问题涉及具体运维操作、故障排查、系统配置等，返回 JSON："
            f'{{"need_retrieval": true}}\n'
            f'如果是简单问候或常识问题，返回 JSON：{{"need_retrieval": false}}\n'
            f"只返回 JSON，不要其他内容。"
        )

        decision_msg = await llm.ainvoke(decision_prompt)
        decision_text = decision_msg.content.strip()

        try:
            decision = json.loads(decision_text)
        except json.JSONDecodeError:
            decision = {"need_retrieval": False}

        if decision.get("need_retrieval", False):
            _checker.require(role, ResourceType.RETRIEVAL_INDEX)
            await websocket.send_json({"type": "tool", "tool": "retrieve", "content": "正在检索知识库..."})

            from ...retrieval.retriever import Retriever

            retriever = Retriever()
            if retriever.is_ready:
                results = retriever.retrieve(query=query, role=role)
                context = "\n\n".join(r.text for r in results)
            else:
                context = ""

            final_prompt = (
                f"基于以下知识库信息回答用户问题：\n\n{context}\n\n"
                f"用户问题：{query}\n\n请提供准确、专业的回答。"
            )
            response = await llm.ainvoke(final_prompt)
        else:
            response = await llm.ainvoke(f"你是运维助手，请回答：{query}")

        await websocket.send_json({"type": "answer", "content": response.content})
        await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "content": str(e)})
            await websocket.close()
        except Exception:
            pass
