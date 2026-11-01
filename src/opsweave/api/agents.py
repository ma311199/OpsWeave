from __future__ import annotations

import json
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from ..auth.permissions import PermissionChecker, ResourceType, Role
from ..config.settings import get_settings
from ..llm.client import get_llm


class AgentState(TypedDict, total=False):
    query: str
    role: Role
    username: str
    route: str
    clarification: str
    answer: str
    tools: list[dict]
    tool_calls: list[dict]
    pending_server: str
    pending_tool: str
    pending_arguments: dict
    tool_result: str
    sources: list[dict[str, str | float]]
    iterations: int


_checker = PermissionChecker.default_rules()


def _decide(state: AgentState) -> dict:
    tools = state.get("tools", [])
    history = state.get("tool_calls", [])
    exposed_tools = [
        {"tool_id": str(index), "name": tool["name"], "description": tool["description"], "input_schema": tool["input_schema"]}
        for index, tool in enumerate(tools)
    ]
    prompt = (
        "你是运维 Agent。基于用户问题、可用工具及先前工具结果，决定下一步，只返回 JSON。\n"
        '直接回答时返回 {"action":"answer","answer":"..."}；\n'
        '信息不足需要用户补充时返回 {"action":"clarify","question":"..."}；\n'
        '需要工具时返回 {"action":"tool_call","tool_id":"工具清单中的 tool_id","arguments":{}}。\n'
        f"可用工具：{json.dumps(exposed_tools, ensure_ascii=False)}\n"
        f"已执行工具及结果：{json.dumps(history, ensure_ascii=False)}\n"
        f"用户问题：{state['query']}"
    )
    try:
        decision = json.loads(get_llm().invoke(prompt).content)
    except (json.JSONDecodeError, TypeError, AttributeError):
        decision = {"action": "answer", "answer": "抱歉，我暂时无法理解这个问题，请补充更多信息。"}

    action = decision.get("action")
    if action == "clarify" and decision.get("question"):
        return {"route": "clarify", "answer": decision["question"]}
    if action == "tool_call":
        tool_id = decision.get("tool_id")
        selected_tool = tools[int(tool_id)] if isinstance(tool_id, str) and tool_id.isdigit() and int(tool_id) < len(tools) else None
        arguments = decision.get("arguments")
        if selected_tool and isinstance(arguments, dict):
            return {
                "route": "tool_call",
                "pending_server": selected_tool["server_id"],
                "pending_tool": selected_tool["name"],
                "pending_arguments": arguments,
            }
    if action == "answer" and decision.get("answer"):
        return {"route": "answer", "answer": decision["answer"]}
    return {"route": "answer", "answer": "抱歉，我暂时无法完成这个请求，请补充更多信息。"}


def _call_tool(state: AgentState) -> dict:
    name = state["pending_tool"]
    if name == "search_knowledge":
        _checker.require(state["role"], ResourceType.RETRIEVAL_INDEX)
    from ..tools.mcp_client import call_tool

    server_id = state["pending_server"]
    result = call_tool(server_id, name, state.get("pending_arguments", {}), state["role"], state["username"])
    calls = [*state.get("tool_calls", []), {"name": name, "arguments": state.get("pending_arguments", {}), "result": result}]
    updates = {"tool_calls": calls, "iterations": state.get("iterations", 0) + 1}
    if name == "search_knowledge" and isinstance(result, list):
        updates["sources"] = result
    return updates


def _next_after_decision(state: AgentState) -> str:
    if state["route"] == "tool_call":
        if state.get("iterations", 0) >= get_settings().agent_max_iterations:
            return "limit"
        return "tool_call"
    return state["route"]


def _limit(state: AgentState) -> dict:
    return {"route": "answer", "answer": "已达到本次工具调用次数上限，请缩小问题范围后重试。"}


def _build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("decide", _decide)
    graph.add_node("tool_call", _call_tool)
    graph.add_node("answer", lambda state: {})
    graph.add_node("clarify", lambda state: {})
    graph.add_node("limit", _limit)
    graph.add_edge(START, "decide")
    graph.add_conditional_edges(
        "decide", _next_after_decision,
        {"tool_call": "tool_call", "answer": "answer", "clarify": "clarify", "limit": "limit"},
    )
    graph.add_edge("tool_call", "decide")
    graph.add_edge("answer", END)
    graph.add_edge("clarify", END)
    graph.add_edge("limit", END)
    return graph.compile()


_agent = None


def run_agent(query: str, role: Role, username: str) -> AgentState:
    global _agent
    if _agent is None:
        _agent = _build_graph()
    from ..tools.mcp_client import list_tools

    tools = list_tools()
    return _agent.invoke({
        "query": query,
        "role": role,
        "username": username,
        "tools": tools,
        "tool_calls": [],
        "iterations": 0,
    })
