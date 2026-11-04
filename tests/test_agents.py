from types import SimpleNamespace

import pytest

from opsweave.api import agents
from opsweave.auth.permissions import Role


class FakeLLM:
    def __init__(self, decisions):
        self.decisions = iter(decisions)
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        import json
        return SimpleNamespace(content=json.dumps(next(self.decisions), ensure_ascii=False))


@pytest.fixture(autouse=True)
def reset_agent():
    agents._agent = None
    yield
    agents._agent = None


def setup_tools(monkeypatch, names=("search_knowledge",)):
    monkeypatch.setattr("opsweave.tools.mcp_client.list_tools", lambda: [{"server_id": "remote-1" if name == "check_service" else "local", "name": name, "description": f"Tool {name}", "input_schema": {"type": "object"}, "annotations": {"readOnlyHint": True}}
        for name in names
    ])


def test_run_agent_direct_answer(monkeypatch):
    llm = FakeLLM([{"action": "answer", "answer": "你好！"}])
    monkeypatch.setattr(agents, "get_llm", lambda: llm)
    setup_tools(monkeypatch)

    result = agents.run_agent("你好", Role.VIEWER, "alice")

    assert result["answer"] == "你好！"
    assert result.get("tool_calls", []) == []
    assert "search_knowledge" in llm.prompts[0]


def test_run_agent_selects_and_calls_mcp_tool(monkeypatch):
    llm = FakeLLM([
        {"action": "tool_call", "tool_id": "0", "arguments": {"query": "检查服务状态"}},
        {"action": "answer", "answer": "请检查健康状态接口。"},
    ])
    monkeypatch.setattr(agents, "get_llm", lambda: llm)
    setup_tools(monkeypatch)
    captured = {}

    def fake_call(server_id, name, arguments, role, user_id):
        captured.update(server_id=server_id, name=name, arguments=arguments, role=role, user_id=user_id)
        return [{"source": "mcp://runbook", "score": 0.91, "text": "检查服务健康状态"}]

    monkeypatch.setattr("opsweave.tools.mcp_client.call_tool", fake_call)
    result = agents.run_agent("检查服务状态", Role.OPS_ENGINEER, "bob")

    assert result["route"] == "answer"
    assert result["answer"] == "请检查健康状态接口。"
    assert result["sources"] == [{"source": "mcp://runbook", "score": 0.91, "text": "检查服务健康状态"}]
    assert captured == {
        "server_id": "local",
        "name": "search_knowledge",
        "arguments": {"query": "检查服务状态"},
        "role": Role.OPS_ENGINEER,
        "user_id": "bob",
    }
    assert "检查服务健康状态" in llm.prompts[-1]


def test_run_agent_can_call_multiple_tools(monkeypatch):
    llm = FakeLLM([
        {"action": "tool_call", "tool_id": "0", "arguments": {"query": "服务状态"}},
        {"action": "tool_call", "tool_id": "1", "arguments": {"service": "api"}},
        {"action": "answer", "answer": "服务正常。"},
    ])
    monkeypatch.setattr(agents, "get_llm", lambda: llm)
    setup_tools(monkeypatch, ("search_knowledge", "check_service"))
    called = []
    monkeypatch.setattr("opsweave.tools.mcp_client.call_tool", lambda server_id, name, args, role, user: called.append(name) or {"status": "ok"})

    result = agents.run_agent("检查 api 服务", Role.OPS_ENGINEER, "bob")

    assert called == ["search_knowledge", "check_service"]
    assert len(result["tool_calls"]) == 2
    assert result["answer"] == "服务正常。"


def test_run_agent_clarifies_incomplete_query(monkeypatch):
    llm = FakeLLM([{"action": "clarify", "question": "你想查询哪项服务？"}])
    monkeypatch.setattr(agents, "get_llm", lambda: llm)
    setup_tools(monkeypatch)
    monkeypatch.setattr("opsweave.tools.mcp_client.call_tool", lambda *args: pytest.fail("tool must not run"))

    result = agents.run_agent("帮我查一下", Role.VIEWER, "alice")

    assert result["route"] == "clarify"
    assert result["answer"] == "你想查询哪项服务？"
    assert result.get("tool_calls", []) == []


def test_tool_call_enforces_permissions_before_mcp_call(monkeypatch):
    llm = FakeLLM([{"action": "tool_call", "tool_id": "0", "arguments": {"query": "查知识库"}}])
    monkeypatch.setattr(agents, "get_llm", lambda: llm)
    setup_tools(monkeypatch)

    class DenyRetrieval:
        def require(self, role, resource):
            raise PermissionError("retrieval denied")

    monkeypatch.setattr(agents, "_checker", DenyRetrieval())
    monkeypatch.setattr("opsweave.tools.mcp_client.call_tool", lambda *args: pytest.fail("MCP tool must not run"))
    with pytest.raises(PermissionError, match="retrieval denied"):
        agents.run_agent("查知识库", Role.VIEWER, "alice")
