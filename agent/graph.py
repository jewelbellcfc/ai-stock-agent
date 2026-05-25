# agent/graph.py
# -------------------------------------------------------------
# PHASE 3 — Kết nối các Node thành StateGraph hoàn chỉnh
#
# Kiến thức mới:
#   - StateGraph: khung chứa toàn bộ luồng
#   - add_node(): đăng ký node
#   - add_edge(): kết nối cứng A → B
#   - add_conditional_edges(): rẽ nhánh động
#   - ToolNode: node đặc biệt tự động thực thi tool calls
#   - compile(): "đông cứng" graph thành Runnable
# -------------------------------------------------------------

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from agent.state import AgentState, get_initial_state, print_state_summary
from agent.nodes import (
    analyst_node,
    portfolio_node,
    reporter_node,
    should_continue,
    ALL_TOOLS,
)


# =============================================================
# XÂY DỰNG GRAPH
# =============================================================
def build_graph():
    """
    Lắp ráp toàn bộ Agent từ các node và edge.

    Luồng:
      START
        ↓
      analyst_node  ←──────────────────┐
        ↓ (nếu có tool calls)          │
      tool_node ─────────────────────→─┘
        ↓ (nếu không có tool calls)
      portfolio_node ←─────────────────┐
        ↓ (nếu có tool calls)          │
      tool_node ─────────────────────→─┘
        ↓
      reporter_node ←──────────────────┐
        ↓ (nếu có tool calls)          │
      tool_node ─────────────────────→─┘
        ↓
      END
    """

    # ── Bước 1: Tạo graph với kiểu State ───────────────────
    graph = StateGraph[AgentState, None, AgentState, AgentState](AgentState)

    # ── Bước 2: Đăng ký các Node ───────────────────────────
    # add_node(tên, hàm_xử_lý)
    graph.add_node("analyst",   analyst_node)
    graph.add_node("portfolio", portfolio_node)
    graph.add_node("reporter",  reporter_node)

    # ToolNode đặc biệt: tự động nhận tool_calls từ LLM message,
    # thực thi từng tool, trả ToolMessage về State
    tool_node = ToolNode(tools=ALL_TOOLS)
    graph.add_node("tools", tool_node)

    # ── Bước 3: Điểm bắt đầu ───────────────────────────────
    graph.set_entry_point("analyst")

    # ── Bước 4: Kết nối các Node ───────────────────────────

    # Sau analyst: nếu LLM gọi tool → tools, ngược lại → portfolio
    graph.add_conditional_edges(
        "analyst",                  # node nguồn
        _route_after_analyst,       # hàm quyết định
        {
            "tools":     "tools",       # nếu trả về "tools" → đi tới tools node
            "portfolio": "portfolio",   # nếu trả về "portfolio" → đi tiếp
        }
    )

    # Sau tools: quay lại node phù hợp dựa trên current_step
    graph.add_conditional_edges(
        "tools",
        _route_after_tools,
        {
            "analyst":   "analyst",
            "portfolio": "portfolio",
            "reporter":  "reporter",
        }
    )

    # Sau portfolio: nếu LLM gọi tool → tools, ngược lại → reporter
    graph.add_conditional_edges(
        "portfolio",
        _route_after_portfolio,
        {
            "tools":    "tools",
            "reporter": "reporter",
        }
    )

    # Sau reporter: nếu LLM gọi tool (gửi Telegram) → tools, ngược lại → END
    graph.add_conditional_edges(
        "reporter",
        _route_after_reporter,
        {
            "tools": "tools",
            "end":   END,           # END là hằng số đặc biệt của LangGraph
        }
    )

    # ── Bước 5: Compile → tạo Runnable ─────────────────────
    return graph.compile()


# =============================================================
# CÁC HÀM ĐỊNH TUYẾN (routing functions)
# Mỗi hàm nhận State, trả về string tên node tiếp theo
# =============================================================

def _route_after_analyst(state: AgentState) -> str:
    """Sau analyst: có tool calls → gọi tools, không → sang portfolio."""
    messages = state.get("messages", [])
    last = messages[-1] if messages else None
    if last and hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "portfolio"


def _route_after_tools(state: AgentState) -> str:
    """Sau tools: quay về node đang xử lý dở."""
    current = state.get("current_step", "portfolio")
    if current == "reporter":
        return "reporter"
    if current == "portfolio":
        return "portfolio"
    if current in ("market", "tools", "report"):
        if not state.get("portfolio"):
            return "portfolio"
        return "reporter"
    return "reporter"


def _route_after_portfolio(state: AgentState) -> str:
    """Sau portfolio: có tool calls → tools, không → reporter."""
    messages = state.get("messages", [])
    last = messages[-1] if messages else None
    if last and hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "reporter"


def _route_after_reporter(state: AgentState) -> str:
    """Sau reporter: có tool calls (gửi Telegram) → tools, không → end."""
    messages = state.get("messages", [])
    last = messages[-1] if messages else None
    if last and hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "end"


# =============================================================
# CHẠY AGENT
# =============================================================
def run_agent(verbose: bool = True) -> dict:
    """
    Hàm chính để chạy toàn bộ Agent một lần.
    Trả về State cuối cùng sau khi Agent hoàn thành.
    """
    print("\n" + "=" * 55)
    print("  VN STOCK AGENT — BẮT ĐẦU PHÂN TÍCH")
    print("=" * 55)

    # Tạo graph
    app = build_graph()

    # Khởi tạo State ban đầu
    initial_state = get_initial_state()

    # Chạy graph — LangGraph sẽ tự điều hướng qua các node
    # stream() trả về từng bước để ta có thể theo dõi
    final_state = None
    for step_output in app.stream(initial_state, config={"recursion_limit": 20}):
        for node_name, node_state in step_output.items():
            if verbose:
                print(f"\n[graph] ✅ Hoàn thành node: {node_name}")
                if "current_step" in node_state:
                    print(f"        next step: {node_state['current_step']}")
        final_state = step_output

    print("\n" + "=" * 55)
    print("  AGENT HOÀN THÀNH")
    print("=" * 55)

    return final_state


if __name__ == "__main__":
    # Chạy thử Agent hoàn chỉnh
    result = run_agent(verbose=True)
    print("\nAgent chạy xong!")
