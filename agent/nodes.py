# agent/nodes.py — Các Node của LangGraph Agent

import sys, os, json
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from agent.state import AgentState
from tools.sector_flow import analyze_sector_flow, compare_sector_flow_trend
from tools.indicators import analyze_stock_technical, scan_portfolio_signals
from tools.telegram_sender import send_market_report, send_portfolio_report, send_alert
from tools.mbs_tools import fetch_mbs_portfolio, sync_mbs_to_local
from config import ANTHROPIC_API_KEY, OPENAI_API_KEY
from datetime import datetime


def _build_llm():
    """
    Thử Anthropic trước (test nhanh 1 request nhỏ để check credit).
    Tự động fallback sang OpenAI nếu lỗi.
    """
    if ANTHROPIC_API_KEY:
        try:
            test_llm = ChatAnthropic(
                model="claude-sonnet-4-20250514",
                api_key=ANTHROPIC_API_KEY,
                temperature=0,
                max_tokens=16,
            )
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

    if OPENAI_API_KEY:
        print("[LLM] ✅ Dùng OpenAI (gpt-4o-mini)")
        return ChatOpenAI(model="gpt-4o-mini", api_key=OPENAI_API_KEY, temperature=0)

    raise ValueError(
        "❌ Không tìm thấy API key nào!\n"
        "   Thêm ANTHROPIC_API_KEY hoặc OPENAI_API_KEY vào file .env"
    )


def _safe_message_slice(messages: list, n: int) -> list:
    """Slice n messages cuối, bỏ ToolMessage mồ côi ở đầu (tránh lỗi OpenAI)."""
    sliced = messages[-n:] if len(messages) >= n else messages[:]
    while sliced and isinstance(sliced[0], ToolMessage):
        sliced = sliced[1:]
    return sliced


# Khởi tạo 1 lần khi import
llm = _build_llm()

ALL_TOOLS = [
    analyze_sector_flow,
    compare_sector_flow_trend,
    analyze_stock_technical,
    scan_portfolio_signals,
    fetch_mbs_portfolio,
    sync_mbs_to_local,
    send_market_report,
    send_portfolio_report,
    send_alert,
]
llm_with_tools = llm.bind_tools(ALL_TOOLS)


# ─────────────────────────────────────────────────────────────
# NODE 1: analyst_node — thị trường + dòng tiền ngành
# ─────────────────────────────────────────────────────────────

def analyst_node(state: AgentState) -> dict:
    """
    Fetch VN-Index, HNX, sector flow, foreign flow.
    Sau đó gọi LLM để phân tích dòng tiền ngành qua tool.
    """
    print("\n[analyst_node] Lấy dữ liệu thị trường...")

    from data.market_fetcher import get_full_market_data
    market_data = get_full_market_data()

    vn      = market_data["vnindex"]
    hnx     = market_data["hnx"]
    foreign = market_data["foreign"]
    sectors = sorted(market_data["sectors"], key=lambda x: x["total_value_bil"], reverse=True)[:5]
    sector_text = "\n".join(
        f"  {s['sector']:20s} {s['total_value_bil']:>7,.0f} tỷ  {s['avg_change_pct']:>+5.1f}%"
        for s in sectors
    )

    today = datetime.now().strftime("%d/%m/%Y %H:%M")

    system_prompt = SystemMessage(content=(
        f"Bạn là chuyên gia phân tích chứng khoán Việt Nam. Hôm nay {today}.\n"
        "Nhiệm vụ: phân tích chi tiết dòng tiền ngành bằng tool analyze_sector_flow, "
        "sau đó đưa ra nhận định ngắn gọn về cơ cấu dòng tiền hôm nay."
    ))

    human_msg = HumanMessage(content=(
        f"Dữ liệu thị trường ({today}):\n"
        f"VN-Index : {vn['close']:,.2f} ({vn['change_pct']:+.2f}%) {vn['trend_5d']}\n"
        f"HNX-Index: {hnx['close']:,.2f} ({hnx['change_pct']:+.2f}%)\n"
        f"Sentiment: {market_data['sentiment']} ({market_data['market_score']}/100)\n"
        f"Khối ngoại: {foreign['net_label']}\n\n"
        f"Top ngành GTGD:\n{sector_text}\n\n"
        "Hãy gọi tool analyze_sector_flow để phân tích chi tiết dòng tiền ngành."
    ))

    response = llm_with_tools.invoke([system_prompt, human_msg])

    return {
        "messages":     [human_msg, response],
        "market_data":  market_data,
        "current_step": "portfolio",  # sau analyst luôn chuyển sang portfolio
    }


# ─────────────────────────────────────────────────────────────
# NODE 2: portfolio_node — danh mục từ MBS + phân tích kỹ thuật
# ─────────────────────────────────────────────────────────────

def portfolio_node(state: AgentState) -> dict:
    """
    Lấy danh mục thật từ MBS (fallback: file JSON).
    Gọi LLM để scan tín hiệu kỹ thuật qua tool scan_portfolio_signals.
    """
    print("\n[portfolio_node] Lấy và phân tích danh mục...")

    # Ưu tiên MBS API
    holdings = []
    try:
        from data.mbs_client import MBSClient
        client = MBSClient()
        data = client.to_standard_format()
        if "error" not in data and data.get("holdings"):
            holdings = data["holdings"]
            print(f"[portfolio_node] MBS: {len(holdings)} vị thế")
    except Exception as e:
        print(f"[portfolio_node] MBS không khả dụng: {e}")

    # Fallback: file JSON
    if not holdings:
        portfolio_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "portfolio", "my_portfolio.json"
        )
        try:
            with open(portfolio_path, "r", encoding="utf-8") as f:
                portfolio_data = json.load(f)
            holdings = portfolio_data.get("holdings", [])
            print(f"[portfolio_node] File JSON: {len(holdings)} vị thế")
        except FileNotFoundError:
            print("[portfolio_node] Không tìm thấy danh mục")
            return {"messages": [], "portfolio": [], "current_step": "report"}

    tickers = [h["ticker"] for h in holdings]

    # Tóm tắt P&L để đưa vào context
    pnl_lines = []
    for h in holdings:
        pnl = h.get("pnl_pct", 0)
        icon = "🟢" if pnl >= 0 else "🔴"
        pnl_lines.append(
            f"  {icon} {h['ticker']:6s}  vốn: {h.get('avg_cost',0):>9,.0f}  "
            f"TT: {h.get('current_price',0):>9,.0f}  P&L: {pnl:>+6.1f}%  "
            f"({h.get('sector','?')})"
        )

    system_prompt = SystemMessage(content=(
        "Bạn là chuyên gia tư vấn danh mục đầu tư chứng khoán Việt Nam.\n"
        "Nhiệm vụ: dùng tool scan_portfolio_signals để phân tích kỹ thuật (RSI, MA) "
        "các mã trong danh mục, từ đó đưa ra khuyến nghị HOLD / MUA THÊM / CẮT LỖ / CHỐT LỜI."
    ))

    human_msg = HumanMessage(content=(
        f"Danh mục hiện tại ({len(holdings)} vị thế):\n"
        + "\n".join(pnl_lines)
        + f"\n\nDanh sách mã: {tickers}\n"
        "Hãy gọi tool scan_portfolio_signals để phân tích kỹ thuật từng mã."
    ))

    response = llm_with_tools.invoke([system_prompt, human_msg])

    return {
        "messages":     [human_msg, response],
        "portfolio":    holdings,
        "current_step": "report",   # sau portfolio luôn chuyển sang reporter
    }


# ─────────────────────────────────────────────────────────────
# NODE 3: reporter_node — tổng hợp báo cáo + gửi Telegram
# ─────────────────────────────────────────────────────────────

def reporter_node(state: AgentState) -> dict:
    """
    Tổng hợp market_data + portfolio + kết quả tool từ message history
    → LLM sinh báo cáo tích hợp 3 phần → gửi Telegram.
    Luôn trả về current_step='done' — không sinh vòng lặp.
    """
    print("\n[reporter_node] Tổng hợp báo cáo...")

    messages    = state.get("messages", [])
    market_data = state.get("market_data") or {}
    portfolio   = state.get("portfolio")   or []

    # Chuẩn bị dữ liệu tóm tắt cho LLM
    vn      = market_data.get("vnindex", {})
    foreign = market_data.get("foreign", {})
    sectors = sorted(
        market_data.get("sectors", []),
        key=lambda x: x.get("total_value_bil", 0), reverse=True
    )[:5]

    sector_text = "\n".join(
        f"  {s['sector']:20s} {s['total_value_bil']:>7,.0f} tỷ  {s['avg_change_pct']:>+5.1f}%"
        for s in sectors
    ) or "  (không có dữ liệu)"

    holding_text = "\n".join(
        f"  {h.get('ticker','?'):6s}  P&L: {h.get('pnl_pct', 0):>+6.1f}%  "
        f"ngành: {h.get('sector','?')}"
        for h in portfolio
    ) or "  (không có danh mục)"

    from agent.market_report_pipeline import INTEGRATED_SYSTEM_PROMPT

    context_msg = HumanMessage(content=(
        f"=== TÓM TẮT DỮ LIỆU ({datetime.now().strftime('%d/%m/%Y %H:%M')}) ===\n\n"
        f"THỊ TRƯỜNG:\n"
        f"VN-Index : {vn.get('close', 0):,.2f} ({vn.get('change_pct', 0):+.2f}%) "
        f"{vn.get('trend_5d', '')}\n"
        f"HNX      : {market_data.get('hnx', {}).get('close', 0):,.2f}\n"
        f"Sentiment: {market_data.get('sentiment', 'N/A')} "
        f"({market_data.get('market_score', 0)}/100)\n"
        f"Khối ngoại: {foreign.get('net_label', 'N/A')}\n\n"
        f"NGÀNH DÒng TIỀN:\n{sector_text}\n\n"
        f"DANH MỤC ({len(portfolio)} vị thế):\n{holding_text}\n\n"
        "(Tham khảo thêm phân tích chi tiết từ các tool ở lịch sử hội thoại bên trên.)\n"
        "Hãy tổng hợp báo cáo đúng 3 phần như hướng dẫn."
    ))

    # Dùng llm thuần (không bind tools) — tránh vòng lặp vô tận
    response = llm.invoke(
        [SystemMessage(content=INTEGRATED_SYSTEM_PROMPT)]
        + _safe_message_slice(messages, 8)
        + [context_msg]
    )

    final_report = response.content if hasattr(response, "content") else str(response)
    print(f"[reporter_node] Báo cáo: {len(final_report)} ký tự")

    # Gửi Telegram với header/footer
    from tools.telegram_sender import _send_message
    from agent.report_pipeline import sanitize_for_telegram
    from agent.market_report_pipeline import _split_safe

    now      = datetime.now().strftime("%d/%m/%Y %H:%M")
    vn_icon  = "🟢" if vn.get("change_pct", 0) >= 0 else "🔴"
    header = (
        f"{'─'*35}\n"
        f"📊 <b>BÁO CÁO TÍCH HỢP</b> — {now}\n"
        f"{vn_icon} VN-Index: <b>{vn.get('close', 0):,.2f}</b> "
        f"({vn.get('change_pct', 0):+.2f}%)\n"
        f"{market_data.get('sentiment', '')}\n"
        f"{'─'*35}\n\n"
    )
    footer = f"\n\n{'─'*35}\n<i>🤖 VN Stock Agent</i>"
    full   = header + sanitize_for_telegram(final_report) + footer

    parts  = _split_safe(full)
    all_ok = True
    for i, part in enumerate(parts, 1):
        prefix = f"<i>({i}/{len(parts)})</i>\n\n" if len(parts) > 1 else ""
        if not _send_message(prefix + part):
            all_ok = False

    return {
        "messages":     [context_msg, response],
        "final_report": final_report,
        "report_sent":  all_ok,
        "current_step": "done",
    }


# ─────────────────────────────────────────────────────────────
# CONDITIONAL EDGES
# ─────────────────────────────────────────────────────────────

def should_continue(state: AgentState) -> str:
    messages = state.get("messages", [])
    last     = messages[-1] if messages else None
    has_tool_calls = (
        hasattr(last, "tool_calls") and bool(last.tool_calls)
    ) if last else False

    if has_tool_calls:
        return "tools"

    current_step = state.get("current_step", "done")
    if current_step == "portfolio":
        return "portfolio"
    if current_step == "report":
        return "report"
    return "end"


def after_tools(state: AgentState) -> str:
    current_step = state.get("current_step", "done")
    if current_step == "tools":
        return "portfolio" if not state.get("portfolio") else "reporter"
    return "report"
