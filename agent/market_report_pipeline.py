# agent/market_report_pipeline.py — Pipeline tích hợp: thị trường + danh mục → Telegram

import sys, os, json
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime
from langchain_core.messages import HumanMessage, SystemMessage

from data.market_fetcher import get_full_market_data
from data.mbs_client import MBSClient
from tools.telegram_sender import _send_message
from agent.report_pipeline import sanitize_for_telegram
from agent.nodes import llm


# =============================================================
# SYSTEM PROMPT — Báo cáo tích hợp 3 phần
# =============================================================

INTEGRATED_SYSTEM_PROMPT = """Bạn là chuyên gia phân tích chứng khoán Việt Nam, \
kết hợp phân tích vĩ mô thị trường với tư vấn danh mục cá nhân.

Tạo báo cáo tích hợp gồm đúng 3 phần, dùng HTML cho Telegram:

━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHẦN 1 — THỊ TRƯỜNG TỔNG QUAN
━━━━━━━━━━━━━━━━━━━━━━━━━━━
• VN-Index: điểm số, % thay đổi, xu hướng ngắn hạn
• Tổng GTGD thị trường
• Top 3 ngành dòng tiền vào mạnh nhất
• Khối ngoại mua/bán ròng — ý nghĩa gì
• 1 câu nhận định tổng thể thị trường hôm nay

━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHẦN 2 — DANH MỤC vs THỊ TRƯỜNG
━━━━━━━━━━━━━━━━━━━━━━━━━━━
• So sánh P&L danh mục vs VN-Index hôm nay
• Mã nào đang "bơi cùng dòng" thị trường / "ngược dòng"
• Ngành nào trong danh mục đang được thị trường hỗ trợ
• Ngành nào đang bị thị trường bỏ lại

━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHẦN 3 — KHUYẾN NGHỊ HÔM NAY
━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Dựa trên dòng tiền thị trường, nên HOLD/MUA THÊM/CẮT LỖ mã nào
• Có ngành nào đang nóng mà danh mục chưa có không
• 1-2 điểm cần chú ý nhất trong phiên/ngày mai

Quy tắc format:
- Dùng <b>đậm</b> cho số liệu quan trọng
- Dùng <i>nghiêng</i> cho nhận định
- Dùng emoji phù hợp
- Ngắn gọn, súc tích — không giải thích lý thuyết
- Viết bằng tiếng Việt
"""


# =============================================================
# BUILD USER PROMPT từ data thật
# =============================================================

def _build_prompt(market_data: dict, portfolio_data: dict) -> str:
    """Ghép dữ liệu thị trường + danh mục thành prompt cho LLM."""

    vn      = market_data["vnindex"]
    hn      = market_data["hnx"]
    sectors = market_data["sectors"]
    foreign = market_data["foreign"]
    now     = market_data["updated_at"]

    # Format sectors ngắn gọn
    top_sectors = sorted(sectors, key=lambda x: x["total_value_bil"], reverse=True)[:5]
    sector_text = "\n".join(
        f"  {s['sector']:20s} {s['total_value_bil']:>7,.0f} tỷ  "
        f"{s['avg_change_pct']:>+5.1f}%  (top: {s.get('top_ticker','')})"
        for s in top_sectors
    )

    # Format holdings ngắn gọn
    holdings = portfolio_data.get("holdings", [])
    summary  = portfolio_data.get("summary", {})
    holding_text = "\n".join(
        f"  {h['ticker']:6s}  qty:{h['quantity']:>6,}  "
        f"vốn:{h['avg_cost']:>8,.0f}  "
        f"TT:{h['current_price']:>8,.0f}  "
        f"P&L:{h['pnl_pct']:>+6.1f}%  "
        f"ngành:{h.get('sector','?')}"
        for h in holdings
    )

    return f"""
=== DỮ LIỆU THỊ TRƯỜNG ({now}) ===

VN-Index : {vn['close']:,.2f} điểm  ({vn['change_pct']:+.2f}%)  {vn['trend_5d']}
HNX-Index: {hn['close']:,.2f} điểm  ({hn['change_pct']:+.2f}%)
Sentiment: {market_data['sentiment']}  (điểm {market_data['market_score']}/100)
Khối ngoại: {foreign['net_label']}  |  Mua nhiều: {foreign.get('top_buy','')}  Bán nhiều: {foreign.get('top_sell','')}

Top ngành theo GTGD:
{sector_text}

=== DANH MỤC MBS ===

Tổng thị trường : {summary.get('total_market', 0):>15,.0f} đ
P&L tổng        : {summary.get('total_profit', 0):>+15,.0f} đ  ({summary.get('profit_ratio', 0):+.2f}%)

Chi tiết vị thế:
{holding_text}

=== YÊU CẦU ===
Hãy tạo báo cáo tích hợp đúng 3 phần như đã hướng dẫn.
Đặc biệt chú ý phân tích mối liên hệ giữa dòng tiền thị trường và từng mã trong danh mục.
"""


# =============================================================
# PIPELINE TÍCH HỢP
# =============================================================

def run_integrated_pipeline() -> bool:
    """
    Pipeline Phase 6:
    1. Lấy dữ liệu thị trường (VN-Index, dòng tiền ngành, khối ngoại)
    2. Lấy danh mục từ MBS
    3. LLM sinh báo cáo tích hợp 3 phần
    4. Gửi Telegram
    """
    print("\n" + "═"*55)
    print("  VN STOCK AGENT — BÁO CÁO TÍCH HỢP (PHASE 6)")
    print("═"*55)

    # ── Bước 1: Thị trường ─────────────────────────────────
    print("\n[1/4] Lấy dữ liệu thị trường...")
    market_data = get_full_market_data()

    # ── Bước 2: Danh mục MBS ───────────────────────────────
    print("[2/4] Lấy danh mục MBS...")
    client         = MBSClient()
    portfolio_data = client.to_standard_format()

    if "error" in portfolio_data or not portfolio_data.get("holdings"):
        print("[pipeline] ⚠️  Không có danh mục MBS — chỉ báo cáo thị trường")
        portfolio_data = {
            "holdings": [],
            "summary": {"total_market": 0, "total_profit": 0, "profit_ratio": 0},
        }

    # ── Bước 3: Gọi LLM ────────────────────────────────────
    print("[3/4] LLM đang phân tích tích hợp...")
    user_prompt = _build_prompt(market_data, portfolio_data)

    response = llm.invoke([
        SystemMessage(content=INTEGRATED_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])
    report = response.content
    print(f"       ✅ Báo cáo: {len(report)} ký tự")

    # ── Bước 4: Gửi Telegram ───────────────────────────────
    print("[4/4] Gửi Telegram...")
    ok = _send_integrated_report(report, market_data, portfolio_data)

    print("═"*55)
    return ok


def _send_integrated_report(
    report: str,
    market_data: dict,
    portfolio_data: dict,
) -> bool:
    """Format header + report + footer rồi gửi Telegram."""

    vn      = market_data["vnindex"]
    summary = portfolio_data.get("summary", {})
    now     = datetime.now().strftime("%d/%m/%Y %H:%M")

    vn_icon  = "🟢" if vn["change_pct"] >= 0 else "🔴"
    pnl_icon = "🟢" if summary.get("profit_ratio", 0) >= 0 else "🔴"

    header = (
        f"{'─'*35}\n"
        f"📊 <b>BÁO CÁO TÍCH HỢP</b> — {now}\n"
        f"{vn_icon} VN-Index: <b>{vn['close']:,.2f}</b> "
        f"({vn['change_pct']:+.2f}%)\n"
        f"{pnl_icon} Danh mục: <b>{summary.get('profit_ratio', 0):+.2f}%</b>\n"
        f"{market_data['sentiment']}\n"
        f"{'─'*35}\n\n"
    )
    footer = (
        f"\n\n{'─'*35}\n"
        f"<i>🤖 VN Stock Agent</i>"
    )

    full = header + sanitize_for_telegram(report) + footer

    # Tách tin nhắn nếu quá dài
    parts  = _split_safe(full)
    all_ok = True
    for i, part in enumerate(parts, 1):
        prefix = f"<i>({i}/{len(parts)})</i>\n\n" if len(parts) > 1 else ""
        if not _send_message(prefix + part):
            all_ok = False

    return all_ok


def _split_safe(text: str, limit: int = 4000) -> list[str]:
    """Tách text thành nhiều phần ≤ limit ký tự, cắt tại dòng mới."""
    if len(text) <= limit:
        return [text]
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        parts.append(text)
    return parts

