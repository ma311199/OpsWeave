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
    history: list[dict[str, str]]
    long_term_memory: str
    conversation_id: str
    approval_pending: dict


_checker = PermissionChecker.default_rules()


# 决定节点
def _decide(state: AgentState) -> dict:
    tools = state.get("tools", [])  # 获取可用工具
    history = state.get("tool_calls", [])  # 获取已执行工具及结果
    exposed_tools = [
        {
            "tool_id": str(index),
            "name": tool["name"],
            "description": tool["description"],
            "input_schema": tool["input_schema"],
        }
        for index, tool in enumerate(tools)
    ]
    prompt = (
        "你是运维 Agent。基于用户问题、可用工具及先前工具结果，决定下一步，只返回 JSON。\n"
        '直接回答时返回 {"action":"answer","answer":"..."}；\n'
        '信息不足需要用户补充时返回 {"action":"clarify","question":"..."}；\n'
        '需要工具时返回 {"action":"tool_call","tool_id":"工具清单中的 tool_id","arguments":{}}。\n'
        f"可用工具：{json.dumps(exposed_tools, ensure_ascii=False)}\n"
        f"本轮已执行工具及结果：{json.dumps(history, ensure_ascii=False)}\n"
        f"对话历史：{json.dumps(state.get('history', []), ensure_ascii=False)}\n"
        f"用户长期记忆：{state.get('long_term_memory', '')}\n"
        f"当前问题：{state['query']}"
    )
    try:
        decision = json.loads(get_llm().invoke(prompt).content)
    except (json.JSONDecodeError, TypeError, AttributeError):
        decision = {
            "action": "answer",
            "answer": "抱歉，我暂时无法理解这个问题，请补充更多信息。",
        }

    action = decision.get("action")
    if action == "clarify" and decision.get("question"):
        return {"route": "clarify", "answer": decision["question"]}
    if action == "tool_call":
        tool_id = decision.get("tool_id")
        selected_tool = (
            tools[int(tool_id)]
            if isinstance(tool_id, str)
            and tool_id.isdigit()
            and int(tool_id) < len(tools)
            else None
        )
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
    return {
        "route": "answer",
        "answer": "抱歉，我暂时无法完成这个请求，请补充更多信息。",
    }


# 调用工具节点
def _call_tool(state: AgentState) -> dict:
    name = state["pending_tool"]
    from ..api.approvals import create_approval
    from ..tools.mcp_client import call_tool

    server_id = state["pending_server"]
    selected_tool = next(
        (
            tool
            for tool in state.get("tools", [])
            if tool["server_id"] == server_id and tool["name"] == name
        ),
        {},
    )
    annotations = selected_tool.get("annotations") or {}
    if name == "search_knowledge":
        _checker.require(state["role"], ResourceType.RETRIEVAL_INDEX)
    if annotations.get("readOnlyHint") is not True:
        approval_id = create_approval(
            state["username"],
            state["conversation_id"],
            server_id,
            name,
            state.get("pending_arguments", {}),
        )
        return {
            "route": "approval_pending",
            "approval_pending": {
                "id": approval_id,
                "server_id": server_id,
                "tool": name,
                "arguments": state.get("pending_arguments", {}),
            },
        }
    result = call_tool(
        server_id,
        name,
        state.get("pending_arguments", {}),
        state["role"],
        state["username"],
    )
    calls = [
        *state.get("tool_calls", []),
        {
            "name": name,
            "arguments": state.get("pending_arguments", {}),
            "result": result,
        },
    ]
    updates = {
        "tool_calls": calls,
        "iterations": state.get("iterations", 0) + 1,
        "route": "tool_call",
    }
    if name == "search_knowledge" and isinstance(result, list):
        updates["sources"] = result
    return updates


# 决定节点后的下一步
def _next_after_decision(state: AgentState) -> str:
    if state.get("route") == "approval_pending":
        return "approval_pending"
    if state["route"] == "tool_call":
        if state.get("iterations", 0) >= get_settings().agent_max_iterations:
            return "limit"  # 如果超过最大迭代次数，返回限制节点
        return "tool_call"  # 否则返回调用工具节点
    return state["route"]  # 其他情况返回当前路由


# 限制节点
def _limit(state: AgentState) -> dict:
    return {
        "route": "answer",
        "answer": "已达到本次工具调用次数上限，请缩小问题范围后重试。",
    }


def _build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("decide", _decide)  # 决定节点
    graph.add_node("tool_call", _call_tool)  # 调用工具节点
    graph.add_node("answer", lambda state: {})  # 回答节点
    graph.add_node("clarify", lambda state: {})  # 澄清节点
    graph.add_node("limit", _limit)  # 限制节点
    graph.add_node("approval_pending", lambda state: {})
    graph.add_edge(START, "decide")  # 开始节点到决定节点
    graph.add_conditional_edges(  # add_conditional_edges 条件边，根据决定节点的路由选择下一步
        "decide",
        _next_after_decision,
        {
            "tool_call": "tool_call",
            "answer": "answer",
            "clarify": "clarify",
            "limit": "limit",
            "approval_pending": "approval_pending",
        },
    )  # 决定节点后的下一步
    graph.add_edge("tool_call", "decide")  # 调用工具节点到决定节点
    graph.add_edge("answer", END)  # 回答节点到结束节点
    graph.add_edge("clarify", END)  # 澄清节点到结束节点
    graph.add_edge("limit", END)  # 限制节点到结束节点
    graph.add_edge("approval_pending", END)
    return graph.compile()  # 编译状态图


_agent = None


def run_agent(
    query: str,
    role: Role,
    username: str,
    conversation_id: str = "",
    history: list[dict[str, str]] | None = None,
    long_term_memory: str = "",
) -> AgentState:
    global _agent
    if _agent is None:
        _agent = _build_graph()
    from ..tools.mcp_client import list_tools

    tools = list_tools()  # 获取可用工具
    return _agent.invoke(
        {
            "query": query,
            "role": role,
            "username": username,
            "conversation_id": conversation_id,
            "tools": tools,
            "tool_calls": [],
            "iterations": 0,
            "history": history or [],
            "long_term_memory": long_term_memory,
        }
    )
