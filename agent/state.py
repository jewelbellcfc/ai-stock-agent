# agent/state.py
# -------------------------------------------------------------
# PHASE 3 — Định nghĩa State (trạng thái) của Agent
#
# Kiến thức mới bạn học ở file này:
#   - TypedDict: dict có khai báo kiểu từng key
#   - Annotated: gắn metadata vào type hint
#   - operator.add: cách LangGraph merge messages
#   - Optional[]: giá trị có thể là None
# -------------------------------------------------------------

from typing import TypedDict, Annotated, Optional
from langgraph.graph.message import add_messages


# =============================================================
# STATE — "tờ giấy chung" của toàn bộ Agent
#
# Mỗi node nhận vào State hiện tại, xử lý,
# rồi trả về dict chứa các key muốn CẬP NHẬT.
# LangGraph tự động merge vào State.
# =============================================================

class AgentState(TypedDict):
    # ── Lịch sử hội thoại với LLM ──────────────────────────
    # Annotated + add_messages = tự động APPEND thay vì ghi đè
    # Mỗi lần node thêm message mới, LangGraph nối vào list cũ
    messages: Annotated[list, add_messages]

    # ── Dữ liệu thị trường ─────────────────────────────────
    # Kết quả từ tool analyze_sector_flow
    sector_data: Optional[dict]

    # ── Dữ liệu kỹ thuật ───────────────────────────────────
    # Kết quả từ tool scan_portfolio_signals
    technical_data: Optional[list]

    # ── Danh mục của user ──────────────────────────────────
    # Đọc từ portfolio/my_portfolio.json
    portfolio: Optional[list]

    # ── Báo cáo tổng hợp ───────────────────────────────────
    # Reporter node tạo ra chuỗi text này để gửi Telegram
    final_report: Optional[str]

    # ── Trạng thái luồng ───────────────────────────────────
    # "market"    → đang phân tích thị trường
    # "portfolio" → đang phân tích danh mục
    # "report"    → đang gửi báo cáo
    # "done"      → hoàn thành
    current_step: Optional[str]

    # Đã gửi Telegram thành công chưa
    report_sent: Optional[bool]


# =============================================================
# GIÁ TRỊ KHỞI TẠO — State ban đầu khi Agent bắt đầu chạy
# =============================================================
def get_initial_state() -> dict:
    """Trả về State mặc định để khởi động Agent."""
    return {
        "messages":      [],
        "sector_data":   None,
        "technical_data": None,
        "portfolio":     None,
        "final_report":  None,
        "current_step":  "market",
        "report_sent":   False,
    }


# =============================================================
# HELPER: In State ra console để debug
# =============================================================
def print_state_summary(state: AgentState):
    """In tóm tắt State hiện tại — dùng để debug."""
    print("\n── STATE SUMMARY ──────────────────────────")
    print(f"  current_step  : {state.get('current_step', 'N/A')}")
    print(f"  messages      : {len(state.get('messages', []))} tin nhắn")
    print(f"  sector_data   : {'✅ có dữ liệu' if state.get('sector_data') else '❌ trống'}")
    print(f"  technical_data: {'✅ có dữ liệu' if state.get('technical_data') else '❌ trống'}")
    print(f"  portfolio     : {'✅ có dữ liệu' if state.get('portfolio') else '❌ trống'}")
    print(f"  final_report  : {'✅ đã tạo' if state.get('final_report') else '❌ chưa tạo'}")
    print(f"  report_sent   : {state.get('report_sent', False)}")
    print("───────────────────────────────────────────\n")


if __name__ == "__main__":
    state = get_initial_state()
    print("State khởi tạo:")
    print_state_summary(state)
    print("Keys trong State:", list(state.keys()))
