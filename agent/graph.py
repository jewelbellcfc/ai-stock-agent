# agent/graph.py — Kết nối các Node thành StateGraph hoàn chỉnh

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from agent.state import AgentState, get_initial_state
from agent.nodes import (
    analyst_node,
    portfolio_node,
    reporter_node,
    ALL_TOOLS,
)


def build_graph():
    """
    Lắp ráp StateGraph từ 3 node + tool node.

    Luồng:
      START → analyst ──(tool calls?)──→ tools ──┐
                                                  │ (quay lại analyst hoặc portfolio)
              analyst ──(không)──────→ portfolio ──(tool calls?)──→ tools ──┐
                                                                              │
              portfolio ──(không)──→ reporter → END
    """
    graph = StateGraph[AgentState, None, AgentState, AgentState](AgentState)

    graph.add_node("analyst",   analyst_node)
    graph.add_node("portfolio", portfolio_node)
    graph.add_node("reporter",  reporter_node)
    graph.add_node("tools",     ToolNode(tools=ALL_TOOLS))

    graph.set_entry_point("analyst")

    # analyst → tools | portfolio
    graph.add_conditional_edges(
        "analyst",
        _route_after_analyst,
        {"tools": "tools", "portfolio": "portfolio"},
    )

    # tools → quay về node đang xử lý dở
    graph.add_conditional_edges(
        "tools",
        _route_after_tools,
        {"analyst": "analyst", "portfolio": "portfolio", "reporter": "reporter"},
    )

    # portfolio → tools | reporter
    graph.add_conditional_edges(
        "portfolio",
        _route_after_portfolio,
        {"tools": "tools", "reporter": "reporter"},
    )

    # reporter → END (không gọi tool — tránh vòng lặp)
    graph.add_edge("reporter", END)

    return graph.compile()


def _route_after_analyst(state: AgentState) -> str:
    last = (state.get("messages") or [None])[-1]
    if last and hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "portfolio"


def _route_after_tools(state: AgentState) -> str:
    """Sau tools: dùng current_step để biết node nào đang chờ kết quả."""
    step = state.get("current_step", "portfolio")
    if step == "report":
        return "reporter"
    return "portfolio"   # step == "portfolio" → analyst vừa xong → sang portfolio


def _route_after_portfolio(state: AgentState) -> str:
    last = (state.get("messages") or [None])[-1]
    if last and hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "reporter"


def run_agent(verbose: bool = True) -> dict:
    """
    Chạy toàn bộ LangGraph Agent một lần.
    Trả về State cuối sau khi hoàn thành.
    """
    print("\n" + "═" * 55)
    print("  VN STOCK AGENT — LANGGRAPH")
    print("═" * 55)

    app           = build_graph()
    initial_state = get_initial_state()
    final_state   = {}

    for step_output in app.stream(initial_state, config={"recursion_limit": 25}):
        for node_name, node_state in step_output.items():
            if verbose:
                step = node_state.get("current_step", "")
                print(f"[graph] ✅ {node_name}" + (f" → {step}" if step else ""))
        final_state = step_output

    sent = False
    for v in final_state.values():
        if isinstance(v, dict) and v.get("report_sent"):
            sent = True
            break

    print("\n" + "═" * 55)
    print(f"  AGENT HOÀN THÀNH — {'✅ Đã gửi Telegram' if sent else '⚠️ Chưa gửi'}")
    print("═" * 55)

    return final_state
