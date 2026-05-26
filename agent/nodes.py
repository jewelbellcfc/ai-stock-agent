# agent/nodes.py — Nodes cho LangGraph Agent (4 mức độ)

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
    """Slice n messages cuối, bỏ ToolMessage mồ côi ở đầu."""
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
# LEVEL 2 — NODE: memory_node
# Đọc lịch sử báo cáo từ DB để làm ngữ cảnh cho planner
# ─────────────────────────────────────────────────────────────

def memory_node(state: AgentState) -> dict:
    """Đọc báo cáo gần nhất từ DB, lưu vào state['memory']."""
    print("\n[memory_node] Đọc lịch sử báo cáo...")

    try:
        from data.db import get_recent_reports
        recent = get_recent_reports(days=3)
        memory = {
            "recent_reports": recent,
            "count":          len(recent),
            "summary":        f"{len(recent)} báo cáo trong 3 ngày qua" if recent
                              else "Chưa có báo cáo nào",
        }
        print(f"[memory_node] ✅ {memory['summary']}")
    except Exception as e:
        print(f"[memory_node] ⚠️ Lỗi DB: {e}")
        memory = {"recent_reports": [], "count": 0, "summary": "Không có lịch sử"}

    return {"memory": memory, "agent_iterations": 0}


# ─────────────────────────────────────────────────────────────
# LEVEL 3 — NODE: planner_node
# LLM lập kế hoạch phân tích dựa trên thị trường + memory
# ─────────────────────────────────────────────────────────────

def planner_node(state: AgentState) -> dict:
    """Tạo kế hoạch phân tích hôm nay; đồng thời fetch market_data để dùng chung."""
    print("\n[planner_node] Lập kế hoạch phân tích...")

    memory = state.get("memory") or {}
    recent = memory.get("recent_reports", [])

    from data.market_fetcher import get_full_market_data
    market_data = get_full_market_data()
    vn          = market_data["vnindex"]
    sectors     = sorted(market_data["sectors"], key=lambda x: x["total_value_bil"], reverse=True)[:3]
    sector_text = ", ".join(f"{s['sector']} ({s['avg_change_pct']:+.1f}%)" for s in sectors)

    if recent:
        history_lines = "\n".join(
            f"  {r['date']}: {r['content'][:150]}..."
            for r in recent[:2]
        )
    else:
        history_lines = "  (Chưa có lịch sử)"

    plan_prompt = (
        f"VN-Index: {vn['close']:,.2f} ({vn['change_pct']:+.2f}%) — {vn['trend_5d']}\n"
        f"Top ngành: {sector_text}\n"
        f"Sentiment: {market_data['sentiment']} ({market_data['market_score']}/100)\n\n"
        f"Lịch sử báo cáo gần đây:\n{history_lines}\n\n"
        'Tạo kế hoạch phân tích hôm nay dưới dạng JSON:\n'
        '{"analysis_mode": "comprehensive|market_focused|portfolio_focused",\n'
        ' "priorities": ["ưu tiên 1", "ưu tiên 2", "ưu tiên 3"],\n'
        ' "focus_stocks": ["mã đáng chú ý nếu có"],\n'
        ' "today_focus": "1 câu mô tả trọng tâm",\n'
        ' "risk_level": "low|medium|high"}\n'
        "Chỉ trả về JSON thuần, không giải thích thêm."
    )

    try:
        resp    = llm.invoke([
            SystemMessage(content="Bạn là AI planner phân tích chứng khoán. Chỉ trả về JSON hợp lệ."),
            HumanMessage(content=plan_prompt),
        ])
        content = resp.content.strip()
        start   = content.find("{")
        end     = content.rfind("}") + 1
        plan    = json.loads(content[start:end]) if start >= 0 else {}
        print(f"[planner_node] ✅ Focus: {plan.get('today_focus', 'N/A')}")
    except Exception as e:
        print(f"[planner_node] ⚠️ Fallback plan ({e})")
        plan = {
            "analysis_mode": "comprehensive",
            "priorities":    ["dòng tiền ngành", "P&L danh mục", "khuyến nghị"],
            "focus_stocks":  [],
            "today_focus":   "Phân tích toàn diện thị trường và danh mục",
            "risk_level":    "medium",
        }

    return {"plan": plan, "market_data": market_data}


# ─────────────────────────────────────────────────────────────
# NODE 1: analyst_node — thị trường + dòng tiền ngành
# ─────────────────────────────────────────────────────────────

def analyst_node(state: AgentState) -> dict:
    """Phân tích thị trường; dùng market_data từ planner nếu đã có."""
    print("\n[analyst_node] Phân tích thị trường...")

    # Tái sử dụng market_data đã fetch từ planner_node
    market_data = state.get("market_data")
    if not market_data:
        from data.market_fetcher import get_full_market_data
        market_data = get_full_market_data()

    plan    = state.get("plan") or {}
    vn      = market_data["vnindex"]
    hnx     = market_data["hnx"]
    foreign = market_data["foreign"]
    sectors = sorted(market_data["sectors"], key=lambda x: x["total_value_bil"], reverse=True)[:5]
    sector_text = "\n".join(
        f"  {s['sector']:20s} {s['total_value_bil']:>7,.0f} tỷ  {s['avg_change_pct']:>+5.1f}%"
        for s in sectors
    )

    today    = datetime.now().strftime("%d/%m/%Y %H:%M")
    focus    = plan.get("today_focus", "Phân tích toàn diện")
    risk_lvl = plan.get("risk_level", "medium")

    system_prompt = SystemMessage(content=(
        f"Bạn là chuyên gia phân tích chứng khoán Việt Nam. Hôm nay {today}.\n"
        f"Kế hoạch: {focus} (rủi ro: {risk_lvl})\n"
        "Nhiệm vụ: gọi tool analyze_sector_flow để phân tích chi tiết dòng tiền ngành."
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
        "current_step": "portfolio",
    }


# ─────────────────────────────────────────────────────────────
# NODE 2: portfolio_node — danh mục từ MBS + phân tích kỹ thuật
# ─────────────────────────────────────────────────────────────

def portfolio_node(state: AgentState) -> dict:
    """Lấy danh mục MBS, gọi scan_portfolio_signals để phân tích kỹ thuật."""
    print("\n[portfolio_node] Phân tích danh mục...")

    plan         = state.get("plan") or {}
    focus_stocks = plan.get("focus_stocks", [])

    holdings = []
    try:
        from data.mbs_client import MBSClient
        client = MBSClient()
        data   = client.to_standard_format()
        if "error" not in data and data.get("holdings"):
            holdings = data["holdings"]
            print(f"[portfolio_node] MBS: {len(holdings)} vị thế")
    except Exception as e:
        print(f"[portfolio_node] MBS không khả dụng: {e}")

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

    pnl_lines = []
    for h in holdings:
        pnl  = h.get("pnl_pct", 0)
        icon = "🟢" if pnl >= 0 else "🔴"
        star = " ⭐" if h["ticker"] in focus_stocks else ""
        pnl_lines.append(
            f"  {icon} {h['ticker']:6s}{star}  vốn: {h.get('avg_cost',0):>9,.0f}  "
            f"TT: {h.get('current_price',0):>9,.0f}  P&L: {pnl:>+6.1f}%  "
            f"({h.get('sector','?')})"
        )

    focus_note = f"\nChú ý đặc biệt: {', '.join(focus_stocks)}" if focus_stocks else ""

    system_prompt = SystemMessage(content=(
        "Bạn là chuyên gia tư vấn danh mục đầu tư chứng khoán Việt Nam.\n"
        "Dùng tool scan_portfolio_signals để phân tích kỹ thuật (RSI, MA) "
        "các mã trong danh mục, đưa ra khuyến nghị HOLD / MUA THÊM / CẮT LỖ / CHỐT LỜI."
    ))

    human_msg = HumanMessage(content=(
        f"Danh mục hiện tại ({len(holdings)} vị thế):\n"
        + "\n".join(pnl_lines)
        + f"\nDanh sách mã: {tickers}"
        + focus_note
        + "\nHãy gọi tool scan_portfolio_signals để phân tích kỹ thuật."
    ))

    response = llm_with_tools.invoke([system_prompt, human_msg])

    return {
        "messages":     [human_msg, response],
        "portfolio":    holdings,
        "current_step": "report",
    }


# ─────────────────────────────────────────────────────────────
# NODE 3: reporter_node — tổng hợp → draft_report
# KHÔNG gửi Telegram — evaluator_node quyết định
# ─────────────────────────────────────────────────────────────

def reporter_node(state: AgentState) -> dict:
    """Tổng hợp market_data + portfolio → draft_report. Tích hợp eval_feedback nếu revision."""
    print("\n[reporter_node] Tổng hợp báo cáo...")

    messages    = state.get("messages", [])
    market_data = state.get("market_data") or {}
    portfolio   = state.get("portfolio")   or []
    eval_fb     = state.get("eval_feedback")
    iterations  = state.get("agent_iterations", 0)

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

    revision_note = ""
    if eval_fb:
        revision_note = (
            f"\n\n⚠️ FEEDBACK CẦN CẢI THIỆN (lần revision {iterations}):\n{eval_fb}\n"
            "Hãy viết lại báo cáo, khắc phục đúng các điểm trên."
        )

    context_msg = HumanMessage(content=(
        f"=== TÓM TẮT DỮ LIỆU ({datetime.now().strftime('%d/%m/%Y %H:%M')}) ===\n\n"
        f"THỊ TRƯỜNG:\n"
        f"VN-Index : {vn.get('close', 0):,.2f} ({vn.get('change_pct', 0):+.2f}%) "
        f"{vn.get('trend_5d', '')}\n"
        f"HNX      : {market_data.get('hnx', {}).get('close', 0):,.2f}\n"
        f"Sentiment: {market_data.get('sentiment', 'N/A')} "
        f"({market_data.get('market_score', 0)}/100)\n"
        f"Khối ngoại: {foreign.get('net_label', 'N/A')}\n\n"
        f"NGÀNH DÒNG TIỀN:\n{sector_text}\n\n"
        f"DANH MỤC ({len(portfolio)} vị thế):\n{holding_text}\n\n"
        "(Tham khảo thêm phân tích chi tiết từ các tool ở lịch sử hội thoại.)\n"
        f"Hãy tổng hợp báo cáo đúng 3 phần như hướng dẫn.{revision_note}"
    ))

    response = llm.invoke(
        [SystemMessage(content=INTEGRATED_SYSTEM_PROMPT)]
        + _safe_message_slice(messages, 8)
        + [context_msg]
    )

    draft = response.content if hasattr(response, "content") else str(response)
    print(f"[reporter_node] Draft: {len(draft)} ký tự")

    # Gửi Telegram ngay (evaluator_node sẽ ghi đè nếu có trong graph)
    _do_send(draft, market_data, portfolio)

    return {
        "messages":     [context_msg, response],
        "draft_report": draft,
        "final_report": draft,
        "report_sent":  True,
        "current_step": "done",
    }


# ─────────────────────────────────────────────────────────────
# LEVEL 4 — NODE: evaluator_node
# Chấm điểm draft_report; gửi Telegram nếu đạt hoặc hết revision
# ─────────────────────────────────────────────────────────────

_EVALUATOR_SYSTEM = """Bạn là chuyên gia kiểm soát chất lượng báo cáo chứng khoán.

Đánh giá báo cáo theo thang 1-10:
1. Có đủ 3 phần: Thị trường / Danh mục / Khuyến nghị (3 điểm)
2. Số liệu cụ thể, không chung chung (2 điểm)
3. Mỗi mã có action rõ: HOLD / MUA THÊM / CẮT LỖ / CHỐT LỜI + lý do (2 điểm)
4. Format HTML Telegram đúng (<b>, <i>, emoji) (1 điểm)
5. Ngắn gọn, súc tích, dễ đọc trên mobile (2 điểm)

Trả về JSON:
{"score": <1-10>, "feedback": "<điểm cần cải thiện nếu score < 7, hoặc OK nếu đạt>"}
Chỉ trả về JSON thuần."""


def evaluator_node(state: AgentState) -> dict:
    """Chấm điểm draft_report; gửi nếu đạt hoặc đã hết lần revision."""
    print("\n[evaluator_node] Đánh giá chất lượng báo cáo...")

    draft       = state.get("draft_report", "")
    market_data = state.get("market_data") or {}
    portfolio   = state.get("portfolio")   or []
    iterations  = state.get("agent_iterations", 0)

    if not draft:
        print("[evaluator_node] ⚠️ Không có draft report")
        return {
            "eval_score":       0,
            "eval_feedback":    "Báo cáo trống",
            "agent_iterations": iterations + 1,
        }

    score    = 7
    feedback = "OK"
    try:
        eval_resp = llm.invoke([
            SystemMessage(content=_EVALUATOR_SYSTEM),
            HumanMessage(content=f"Báo cáo cần đánh giá:\n\n{draft[:3000]}"),
        ])
        content  = eval_resp.content.strip()
        start    = content.find("{")
        end      = content.rfind("}") + 1
        result   = json.loads(content[start:end]) if start >= 0 else {}
        score    = int(result.get("score", 7))
        feedback = result.get("feedback", "OK")
        print(f"[evaluator_node] Điểm: {score}/10 — {feedback[:100]}")
    except Exception as e:
        print(f"[evaluator_node] ⚠️ Lỗi chấm điểm ({e}), dùng mặc định {score}/10")

    new_iterations = iterations + 1
    should_send    = (score >= 7) or (new_iterations > 2)

    if should_send:
        reason = "đạt điểm" if score >= 7 else f"đã revision {new_iterations - 1} lần"
        print(f"[evaluator_node] ✅ Gửi Telegram ({reason})")
        _do_send(draft, market_data, portfolio)
        return {
            "eval_score":       score,
            "eval_feedback":    None,
            "agent_iterations": new_iterations,
            "final_report":     draft,
            "report_sent":      True,
            "current_step":     "done",
        }
    else:
        print(f"[evaluator_node] 🔄 Chưa đạt ({score}/10) → revision lần {new_iterations}")
        return {
            "eval_score":       score,
            "eval_feedback":    feedback,
            "agent_iterations": new_iterations,
            "report_sent":      False,
            "current_step":     "report",
        }


def _do_send(draft: str, market_data: dict, portfolio: list):
    """Format header/footer rồi gửi Telegram, log vào DB."""
    from tools.telegram_sender import _send_message
    from agent.report_pipeline import sanitize_for_telegram
    from agent.market_report_pipeline import _split_safe

    vn      = market_data.get("vnindex", {})
    now     = datetime.now().strftime("%d/%m/%Y %H:%M")
    vn_icon = "🟢" if vn.get("change_pct", 0) >= 0 else "🔴"

    header = (
        f"{'─'*35}\n"
        f"📊 <b>BÁO CÁO TÍCH HỢP</b> — {now}\n"
        f"{vn_icon} VN-Index: <b>{vn.get('close', 0):,.2f}</b> "
        f"({vn.get('change_pct', 0):+.2f}%)\n"
        f"{market_data.get('sentiment', '')}\n"
        f"{'─'*35}\n\n"
    )
    footer = f"\n\n{'─'*35}\n<i>🤖 VN Stock Agent</i>"
    full   = header + sanitize_for_telegram(draft) + footer

    parts  = _split_safe(full)
    for i, part in enumerate(parts, 1):
        prefix = f"<i>({i}/{len(parts)})</i>\n\n" if len(parts) > 1 else ""
        _send_message(prefix + part)

    try:
        from data.db import log_report
        log_report("integrated", draft, sent_ok=True)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# CONDITIONAL EDGES (kept for compatibility with graph.py)
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
