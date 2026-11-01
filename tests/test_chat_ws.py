import json

from opsweave.api.routes import chat
from opsweave.auth.permissions import Role


def _create_session(monkeypatch, username="alice"):
    monkeypatch.setattr(chat, "websocket_role", lambda websocket: _viewer_role())
    monkeypatch.setattr(chat, "user_for_token", lambda token: (username, "viewer") if token == "test-session" else None)


async def _viewer_role():
    return Role.VIEWER


def test_chat_ws_emits_each_tool_call_then_answer(client, monkeypatch):
    _create_session(monkeypatch)
    monkeypatch.setattr(chat, "run_agent", lambda query, role, username: {
        "route": "answer",
        "answer": "服务正常。",
        "tool_calls": [
            {"server_id": "local", "name": "search_knowledge"},
            {"server_id": "remote-1", "name": "check_service"},
        ],
    })

    with client.websocket_connect("/api/chat/ws/chat", cookies={"opsweave_session": "test-session"}) as websocket:
        websocket.send_text(json.dumps({"query": "检查服务"}))
        messages = [websocket.receive_json() for _ in range(5)]

    assert [message["type"] for message in messages] == ["thinking", "tool", "tool", "answer", "done"]
    assert [message["tool"] for message in messages if message["type"] == "tool"] == ["search_knowledge", "check_service"]
    assert messages[-2]["content"] == "服务正常。"


def test_chat_ws_emits_clarification_without_tools(client, monkeypatch):
    _create_session(monkeypatch)
    monkeypatch.setattr(chat, "run_agent", lambda query, role, username: {
        "route": "clarify",
        "answer": "请问是哪项服务？",
        "tool_calls": [],
    })

    with client.websocket_connect("/api/chat/ws/chat", cookies={"opsweave_session": "test-session"}) as websocket:
        websocket.send_text(json.dumps({"query": "帮我检查一下"}))
        messages = [websocket.receive_json() for _ in range(3)]

    assert [message["type"] for message in messages] == ["thinking", "clarify", "done"]
    assert messages[1]["content"] == "请问是哪项服务？"


def test_chat_ws_rejects_missing_session(client, monkeypatch):
    async def unauthenticated(websocket):
        from fastapi import HTTPException
        raise HTTPException(status_code=401)

    monkeypatch.setattr(chat, "websocket_role", unauthenticated)

    from starlette.testclient import WebSocketDisconnect

    try:
        with client.websocket_connect("/api/chat/ws/chat"):
            pass
    except WebSocketDisconnect as exc:
        assert exc.code == 4401
    else:
        raise AssertionError("unauthenticated websocket should be rejected")
