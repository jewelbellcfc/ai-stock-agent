# agent/state.py — AgentState cho LangGraph

from typing import TypedDict, Annotated, Optional
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages:         Annotated[list, add_messages]  # tự động append, không ghi đè
    market_data:      Optional[dict]   # VN-Index, HNX, sectors, foreign
    sector_data:      Optional[dict]   # từ tool analyze_sector_flow
    technical_data:   Optional[list]   # từ tool scan_portfolio_signals
    portfolio:        Optional[list]   # danh mục MBS (holdings + P&L)
    final_report:     Optional[str]    # báo cáo đã được duyệt và gửi
    current_step:     Optional[str]    # "portfolio" | "report" | "done"
    report_sent:      Optional[bool]   # đã gửi Telegram thành công
    # Level 2 — Memory
    memory:           Optional[dict]   # lịch sử báo cáo gần nhất từ DB
    # Level 3 — Planning
    plan:             Optional[dict]   # kế hoạch: priorities, focus_stocks, mode
    draft_report:     Optional[str]    # bản nháp chờ evaluator duyệt
    # Level 4 — Self-evaluation
    eval_score:       Optional[int]    # điểm 1-10
    eval_feedback:    Optional[str]    # feedback để reporter revise
    agent_iterations: Optional[int]    # số lần revision (tránh vòng lặp vô tận)


def get_initial_state() -> dict:
    return {
        "messages":         [],
        "market_data":      None,
        "sector_data":      None,
        "technical_data":   None,
        "portfolio":        None,
        "final_report":     None,
        "current_step":     "market",
        "report_sent":      False,
        "memory":           None,
        "plan":             None,
        "draft_report":     None,
        "eval_score":       None,
        "eval_feedback":    None,
        "agent_iterations": 0,
    }
