# agent/nodes.py
# -------------------------------------------------------------
# PHASE 3 — Các Node của LangGraph Agent
#
# Kiến thức mới:
#   - ChatAnthropic (kết nối LLM)
#   - bind_tools() (gắn tool vào LLM)
#   - HumanMessage, AIMessage, ToolMessage
#   - Conditional edge (rẽ nhánh dựa trên State)
#   - json.load() (đọc file JSON)
# -------------------------------------------------------------

import sys, os, json
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from agent.state import AgentState
from tools.sector_flow import analyze_sector_flow, compare_sector_flow_trend
from tools.indicators import analyze_stock_technical, scan_portfolio_signals
from tools.telegram_sender import send_market_report, send_portfolio_report, send_alert
from config import ANTHROPIC_API_KEY, OPENAI_API_KEY
from datetime import datetime


# =============================================================
# KHỞI TẠO LLM — dùng chung cho tất cả nodes
# =============================================================
def _build_llm():
    """
    Thử khởi tạo Anthropic trước.
    Nếu không có key hoặc hết credit → tự động dùng OpenAI.
 
    Cách hoạt động:
    1. Có ANTHROPIC_API_KEY → thử gọi thử 1 request nhỏ
    2. Thành công → dùng Anthropic
    3. Lỗi credit / auth → in cảnh báo, switch sang OpenAI
    4. Không có cả 2 key → raise lỗi rõ ràng
    """
    # ── Thử Anthropic trước ─────────────────────────────────
    if ANTHROPIC_API_KEY:
        try:
            test_llm = ChatAnthropic(
                model="claude-sonnet-4-20250514",
                api_key=ANTHROPIC_API_KEY,
                temperature=0,
                max_tokens=16,   # nhỏ nhất có thể để test nhanh
            )
            # Gọi thử 1 message cực ngắn để kiểm tra credit
            test_llm.invoke([HumanMessage(content="hi")])
 
            print("[LLM] ✅ Dùng Anthropic Claude (claude-sonnet-4-20250514)")
            return ChatAnthropic(
                model="claude-sonnet-4-20250514",
                api_key=ANTHROPIC_API_KEY,
                temperature=0,
                max_tokens=2048,
            )
 
        except Exception as e:
            err = str(e).lower()
            # Phân loại lỗi để thông báo rõ ràng
            if "credit" in err or "billing" in err or "balance" in err:
                reason = "hết credit"
            elif "auth" in err or "api_key" in err or "unauthorized" in err:
                reason = "API key không hợp lệ"
            elif "overload" in err or "529" in err:
                reason = "server quá tải"
            else:
                reason = str(e)[:80]
 
            print(f"[LLM] ⚠️  Anthropic không khả dụng ({reason})")
            print(f"[LLM] 🔄 Tự động chuyển sang OpenAI...")
 
    # ── Fallback: OpenAI ────────────────────────────────────
    if OPENAI_API_KEY:
        print("[LLM] ✅ Dùng OpenAI (gpt-4o-mini)")
        return ChatOpenAI(
            model="gpt-4o-mini",
            api_key=OPENAI_API_KEY,
            temperature=0,
        )
 
    # ── Không có key nào ────────────────────────────────────
    raise ValueError(
        "❌ Không tìm thấy API key nào!\n"
        "   Thêm ANTHROPIC_API_KEY hoặc OPENAI_API_KEY vào file .env"
    )
 
 
def _safe_message_slice(messages: list, n: int) -> list:
    """Slice n messages cuối, bỏ ToolMessage mồ côi ở đầu để OpenAI không báo lỗi."""
    sliced = messages[-n:] if len(messages) >= n else messages[:]
    while sliced and isinstance(sliced[0], ToolMessage):
        sliced = sliced[1:]
    return sliced


# Khởi tạo LLM 1 lần khi import module
llm = _build_llm()

# Gắn tất cả tools vào LLM — LLM sẽ biết khi nào gọi tool nào
ALL_TOOLS = [
    analyze_sector_flow,
    compare_sector_flow_trend,
    analyze_stock_technical,
    scan_portfolio_signals,
    send_market_report,
    send_portfolio_report,
    send_alert,
]
llm_with_tools = llm.bind_tools(ALL_TOOLS)


# =============================================================
# NODE 1: analyst_node — phân tích thị trường
# =============================================================
def analyst_node(state: AgentState) -> dict:
    """
    Node phân tích thị trường và dòng tiền ngành.
    Gọi LLM với context ngày hôm nay,
    LLM tự quyết định gọi tool analyze_sector_flow.
    """
    print("\n[analyst_node] Bắt đầu phân tích thị trường...")

    today = datetime.now().strftime("%d/%m/%Y")

    system_prompt = SystemMessage(content=f"""
Bạn là chuyên gia phân tích chứng khoán Việt Nam.
Hôm nay là {today}.

Nhiệm vụ của bạn:
1. Phân tích dòng tiền luân chuyển giữa các ngành hôm nay
2. Xác định ngành nào đang được mua vào / bán ra mạnh
3. Đưa ra nhận định tổng quan thị trường

Hãy sử dụng tool analyze_sector_flow để lấy dữ liệu.
Trả lời bằng tiếng Việt, ngắn gọn và súc tích.
""")

    human_msg = HumanMessage(content=
        "Phân tích dòng tiền thị trường chứng khoán Việt Nam hôm nay. "
        "Sử dụng mock data (use_mock=true) để test."
    )

    # Gọi LLM — LLM sẽ tự gọi tool nếu cần
    response = llm_with_tools.invoke([system_prompt, human_msg])

    print(f"[analyst_node] LLM response type: {type(response).__name__}")
    print(f"[analyst_node] Tool calls: {len(response.tool_calls) if hasattr(response, 'tool_calls') else 0}")

    # Trả về dict để cập nhật State
    return {
        "messages":     [human_msg, response],
        "current_step": "tools" if response.tool_calls else "portfolio",
    }


# =============================================================
# NODE 2: portfolio_node — phân tích danh mục cá nhân
# =============================================================
def portfolio_node(state: AgentState) -> dict:
    """
    Node đọc danh mục từ file JSON,
    chạy phân tích kỹ thuật, và đưa ra tư vấn.
    """
    print("\n[portfolio_node] Đọc và phân tích danh mục...")

    # Đọc file danh mục
    portfolio_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "portfolio", "my_portfolio.json"
    )
    try:
        with open(portfolio_path, "r", encoding="utf-8") as f:
            portfolio_data = json.load(f)
        holdings = portfolio_data.get("holdings", [])
        print(f"[portfolio_node] Đọc được {len(holdings)} vị thế")
    except FileNotFoundError:
        print("[portfolio_node] Không tìm thấy file danh mục, dùng danh mục mẫu")
        holdings = [
            {"ticker": "VCB",  "quantity": 1000, "avg_cost": 85000,  "sector": "Ngân hàng"},
            {"ticker": "HPG",  "quantity": 2000, "avg_cost": 26000,  "sector": "Thép"},
            {"ticker": "FPT",  "quantity": 500,  "avg_cost": 118000, "sector": "Công nghệ"},
        ]

    # Lấy danh sách ticker
    tickers = [h["ticker"] for h in holdings]

    # Gọi LLM để phân tích danh mục
    system_prompt = SystemMessage(content="""
Bạn là chuyên gia tư vấn danh mục đầu tư chứng khoán Việt Nam.

Nhiệm vụ:
1. Phân tích kỹ thuật từng mã trong danh mục
2. Đánh giá rủi ro/cơ hội dựa trên RSI và xu hướng giá
3. Đưa ra khuyến nghị: HOLD / MUA THÊM / CẮT LỖ / CHỐT LỜI

Trả lời bằng tiếng Việt, rõ ràng và actionable.
""")

    human_msg = HumanMessage(content=
        f"Phân tích kỹ thuật các mã sau trong danh mục của tôi: {tickers}. "
        f"Dùng use_mock=true. "
        f"Danh mục chi tiết: {json.dumps(holdings, ensure_ascii=False)}"
    )

    response = llm_with_tools.invoke([system_prompt, human_msg])

    print(f"[portfolio_node] Tool calls: {len(response.tool_calls) if hasattr(response, 'tool_calls') else 0}")

    return {
        "messages":     [human_msg, response],
        "portfolio":    holdings,
        "current_step": "tools" if response.tool_calls else "report",
    }


# =============================================================
# NODE 3: reporter_node — tổng hợp và gửi Telegram
# =============================================================
def reporter_node(state: AgentState) -> dict:
    """
    Node cuối: tổng hợp toàn bộ kết quả phân tích,
    tạo báo cáo text rồi gửi Telegram trực tiếp (không qua tool_calls).
    Luôn trả về current_step='done' — không bao giờ sinh vòng lặp.
    """
    print("\n[reporter_node] Tổng hợp báo cáo...")

    messages = state.get("messages", [])

    system_prompt = SystemMessage(content=f"""
Bạn là trợ lý tổng hợp báo cáo chứng khoán.
Hôm nay: {datetime.now().strftime('%d/%m/%Y %H:%M')}

Dựa trên toàn bộ phân tích đã thực hiện, hãy tạo một báo cáo tổng hợp gồm:

1. 📊 TỔNG QUAN THỊ TRƯỜNG
   - Sentiment thị trường
   - Top ngành dòng tiền vào/ra

2. 💼 DANH MỤC CÁ NHÂN
   - Từng mã: RSI, tín hiệu, khuyến nghị

3. ⚠️ ĐIỂM CẦN CHÚ Ý HÔM NAY
   - Rủi ro, cơ hội đáng chú ý

Chỉ trả về text báo cáo, không gọi bất kỳ tool nào.
Viết ngắn gọn, dùng emoji để dễ đọc trên Telegram.
Viết bằng tiếng Việt.
""")

    summary_msg = HumanMessage(content=
        "Dựa trên tất cả phân tích trên, hãy tổng hợp báo cáo cuối ngày."
    )

    # Dùng llm thuần (không bind tools) — đảm bảo không sinh tool_calls
    response = llm.invoke(
        [system_prompt] + _safe_message_slice(messages, 6) + [summary_msg]
    )

    final_report = response.content if hasattr(response, "content") else str(response)
    print(f"[reporter_node] Báo cáo tạo xong ({len(final_report)} ký tự)")

    # Gửi Telegram trực tiếp trong Python — không qua tool_calls
    from tools.telegram_sender import _send_message
    sent = _send_message(final_report) if final_report else False

    return {
        "messages":     [summary_msg, response],
        "final_report": final_report,
        "report_sent":  sent,
        "current_step": "done",   # luôn done — không bao giờ quay lại tools
    }


# =============================================================
# CONDITIONAL EDGE — Rẽ nhánh: tiếp tục hay kết thúc?
# =============================================================
def should_continue(state: AgentState) -> str:
    """
    Hàm này quyết định bước tiếp theo trong graph.
    Trả về tên node tiếp theo (string).

    LangGraph gọi hàm này sau mỗi node để biết đi đâu.
    """
    current_step = state.get("current_step", "done")
    messages     = state.get("messages", [])

    # Kiểm tra message cuối có tool_calls không
    last_message = messages[-1] if messages else None
    has_tool_calls = (
        hasattr(last_message, "tool_calls") and
        bool(last_message.tool_calls)
    ) if last_message else False

    # Nếu LLM muốn gọi tool → đi tới tool_node
    if has_tool_calls:
        return "tools"

    # Nếu đang ở bước market → sang portfolio
    if current_step == "portfolio":
        return "portfolio"

    # Nếu đang ở bước report → sang reporter
    if current_step == "report":
        return "report"

    # Mặc định → kết thúc
    return "end"


def after_tools(state: AgentState) -> str:
    """
    Sau khi tools chạy xong, quay lại node nào?
    Dựa vào current_step trong State.
    """
    current_step = state.get("current_step", "done")

    if current_step == "tools":
        # Xem message trước tools là của node nào
        messages = state.get("messages", [])
        # Heuristic: nếu chưa có portfolio → về analyst
        if not state.get("portfolio"):
            return "analyst"
        return "portfolio"

    return "report"
