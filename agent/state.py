# agent/state.py — AgentState cho LangGraph

from typing import TypedDict, Annotated, Optional
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages:       Annotated[list, add_messages]  # tự động append, không ghi đè
    market_data:    Optional[dict]   # VN-Index, HNX, sectors, foreign — từ market_fetcher
    sector_data:    Optional[dict]   # từ tool analyze_sector_flow
    technical_data: Optional[list]   # từ tool scan_portfolio_signals
    portfolio:      Optional[list]   # danh mục từ MBS (holdings + P&L)
    final_report:   Optional[str]    # báo cáo tổng hợp cuối
    current_step:   Optional[str]    # "market" → "portfolio" → "report" → "done"
    report_sent:    Optional[bool]   # đã gửi Telegram thành công chưa


def get_initial_state() -> dict:
    return {
        "messages":       [],
        "market_data":    None,
        "sector_data":    None,
        "technical_data": None,
        "portfolio":      None,
        "final_report":   None,
        "current_step":   "market",
        "report_sent":    False,
    }
