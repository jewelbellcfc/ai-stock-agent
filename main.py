# main.py
# -------------------------------------------------------------
# VN Stock Agent — Điểm khởi động duy nhất
#
# Lệnh hàng ngày:
#   python main.py                        → báo cáo tích hợp (thị trường + danh mục)
#   python main.py --market               → chỉ phân tích thị trường
#   python main.py --portfolio            → chỉ phân tích danh mục
#   python main.py --schedule             → chạy tự động theo giờ giao dịch
#   python main.py --set-token "Bearer …" → cập nhật MBS token
# -------------------------------------------------------------

import sys, os, argparse
sys.path.insert(0, os.path.dirname(__file__))

# Windows console UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from data.db import init_db


# =============================================================
# TASK 1: Phân tích thị trường tổng quan
# =============================================================
def run_market_analysis():
    """
    Lấy dữ liệu VN-Index, dòng tiền ngành, khối ngoại
    → LLM phân tích → gửi Telegram.
    """
    from data.market_fetcher import get_full_market_data
    from agent.nodes import llm
    from tools.telegram_sender import _send_message
    from agent.report_pipeline import sanitize_for_telegram
    from langchain_core.messages import HumanMessage, SystemMessage
    from datetime import datetime

    print("\n" + "═"*50)
    print("  PHÂN TÍCH THỊ TRƯỜNG")
    print("═"*50)

    # Bước 1: Lấy data
    print("[1/3] Lấy dữ liệu thị trường...")
    market = get_full_market_data()
    vn     = market["vnindex"]
    print(f"      VN-Index: {vn['close']:,.2f} ({vn['change_pct']:+.2f}%)")

    # Bước 2: LLM phân tích
    print("[2/3] LLM đang phân tích...")
    sectors     = market["sectors"]
    foreign     = market["foreign"]
    top_sectors = sorted(sectors, key=lambda x: x["total_value_bil"], reverse=True)[:5]
    sector_text = "\n".join(
        f"  {s['sector']:20s} {s['total_value_bil']:>7,.0f} tỷ  "
        f"{s['avg_change_pct']:>+5.1f}%  top: {s.get('top_ticker','')}"
        for s in top_sectors
    )

    prompt = f"""
Hôm nay {datetime.now().strftime('%d/%m/%Y %H:%M')}

VN-Index : {vn['close']:,.2f}  ({vn['change_pct']:+.2f}%)  {vn['trend_5d']}
HNX      : {market['hnx']['close']:,.2f}  ({market['hnx']['change_pct']:+.2f}%)
Sentiment: {market['sentiment']}  (điểm {market['market_score']}/100)
Khối ngoại: {foreign['net_label']}

Top ngành dòng tiền:
{sector_text}

Viết báo cáo thị trường ngắn gọn bằng tiếng Việt, dùng HTML Telegram (<b>, <i>):
1. Nhận định VN-Index hôm nay
2. Top 3 ngành dòng tiền mạnh — ý nghĩa gì
3. Khối ngoại — tác động thế nào
4. 1 câu tổng kết và lưu ý cho nhà đầu tư
"""
    resp   = llm.invoke([
        SystemMessage(content="Bạn là chuyên gia phân tích chứng khoán Việt Nam. Viết ngắn gọn, thực tế, dùng HTML Telegram."),
        HumanMessage(content=prompt),
    ])
    report = resp.content

    # Bước 3: Gửi Telegram
    print("[3/3] Gửi Telegram...")
    now      = datetime.now().strftime("%d/%m/%Y %H:%M")
    vn_icon  = "🟢" if vn["change_pct"] >= 0 else "🔴"
    message  = (
        f"{'─'*35}\n"
        f"📈 <b>THỊ TRƯỜNG — {now}</b>\n"
        f"{vn_icon} VN-Index: <b>{vn['close']:,.2f}</b> ({vn['change_pct']:+.2f}%)\n"
        f"{market['sentiment']}\n"
        f"{'─'*35}\n\n"
        f"{sanitize_for_telegram(report)}"
    )
    ok = _send_message(message)
    print(f"      {'✅ Đã gửi!' if ok else '❌ Gửi thất bại'}")
    return ok


# =============================================================
# TASK 2: Phân tích danh mục cá nhân
# =============================================================
def run_portfolio_analysis():
    """
    Lấy danh mục thật từ MBS
    → LLM phân tích P&L + khuyến nghị → gửi Telegram.
    """
    from data.mbs_client import MBSClient
    from agent.nodes import llm
    from tools.telegram_sender import _send_message
    from agent.report_pipeline import sanitize_for_telegram
    from langchain_core.messages import HumanMessage, SystemMessage
    from datetime import datetime
    import json

    print("\n" + "═"*50)
    print("  PHÂN TÍCH DANH MỤC")
    print("═"*50)

    # Bước 1: Lấy danh mục MBS
    print("[1/3] Lấy danh mục từ MBS...")
    client = MBSClient()
    data   = client.to_standard_format()

    if "error" in data or not data.get("holdings"):
        msg = "❌ Không lấy được danh mục MBS\nKiểm tra token: <code>python main.py --set-token \"Bearer …\"</code>"
        _send_message(msg)
        print("      ❌ Không có data MBS")
        return False

    holdings = data["holdings"]
    summary  = data["summary"]
    print(f"      {len(holdings)} vị thế | P&L: {summary['profit_ratio']:+.2f}%")

    # Bước 2: LLM phân tích
    print("[2/3] LLM đang phân tích danh mục...")
    holding_text = "\n".join(
        f"  {h['ticker']:6s}  SL:{h['quantity']:>6,}  "
        f"Vốn:{h['avg_cost']:>9,.0f}  "
        f"TT:{h['current_price']:>9,.0f}  "
        f"P&L:{h['pnl_pct']:>+6.1f}%  "
        f"({h.get('sector','?')})"
        for h in holdings
    )

    prompt = f"""
Hôm nay {datetime.now().strftime('%d/%m/%Y %H:%M')}
Tài khoản: {data.get('account', 'N/A')}

=== TỔNG DANH MỤC ===
Giá trị thị trường: {summary['total_market']:>15,.0f} đ
Lãi/lỗ tổng:        {summary['total_profit']:>+15,.0f} đ ({summary['profit_ratio']:+.2f}%)

=== CHI TIẾT VỊ THẾ ===
{holding_text}

Hãy viết báo cáo danh mục gồm 2 phần bằng tiếng Việt, dùng HTML Telegram:

PHẦN 1 — TỔNG QUAN
- Nhận xét tổng thể danh mục đang ở trạng thái nào
- Số mã lãi / lỗ, mã tốt nhất / kém nhất

PHẦN 2 — TỪNG MÃ
- Mỗi mã: P&L%, tình trạng, khuyến nghị (HOLD / CHỐT LỜI / MUA THÊM / CẮT LỖ)
- 1 câu lý do ngắn gọn
"""
    resp   = llm.invoke([
        SystemMessage(content="Bạn là chuyên gia tư vấn danh mục chứng khoán Việt Nam. Viết thực tế, ngắn gọn, có số liệu cụ thể, dùng HTML Telegram."),
        HumanMessage(content=prompt),
    ])
    report = resp.content

    # Bước 3: Gửi Telegram
    print("[3/3] Gửi Telegram...")
    now      = datetime.now().strftime("%d/%m/%Y %H:%M")
    pnl      = summary["profit_ratio"]
    pnl_icon = "🟢" if pnl >= 0 else "🔴"

    message  = (
        f"{'─'*35}\n"
        f"💼 <b>DANH MỤC — {now}</b>\n"
        f"{pnl_icon} P&amp;L tổng: <b>{pnl:+.2f}%</b>  "
        f"({summary['total_profit']:>+,.0f}đ)\n"
        f"{'─'*35}\n\n"
        f"{sanitize_for_telegram(report)}"
    )

    # Tách nếu quá 4096 ký tự
    ok = True
    if len(message) <= 4000:
        ok = _send_message(message)
    else:
        part1 = message[:3900] + "\n<i>(tiếp...)</i>"
        part2 = message[3900:]
        ok    = _send_message(part1) and _send_message(part2)

    print(f"      {'✅ Đã gửi!' if ok else '❌ Gửi thất bại'}")
    return ok


# =============================================================
# TASK 3: Báo cáo tích hợp (thị trường + danh mục)
# =============================================================
def run_full_report():
    """Chạy cả 2: phân tích thị trường rồi phân tích danh mục."""
    ok1 = run_market_analysis()
    ok2 = run_portfolio_analysis()
    return ok1 and ok2


# =============================================================
# MAIN
# =============================================================
def main():
    parser = argparse.ArgumentParser(
        description="VN Stock Agent",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--market",
        action="store_true",
        help="Chỉ phân tích thị trường (VN-Index, dòng tiền ngành)",
    )
    parser.add_argument(
        "--portfolio",
        action="store_true",
        help="Chỉ phân tích danh mục cá nhân từ MBS",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Khởi động scheduler tự động theo giờ giao dịch",
    )
    parser.add_argument(
        "--agent",
        action="store_true",
        help="Chạy LangGraph Agent (thị trường + danh mục + báo cáo tích hợp)",
    )
    parser.add_argument(
        "--set-token",
        metavar="TOKEN",
        help='Cập nhật MBS Bearer token\nVí dụ: --set-token "Bearer eyJhbGc..."',
    )
    args = parser.parse_args()

    # Khởi tạo DB
    init_db()

    # LangGraph Agent
    if args.agent:
        from agent.graph import run_agent
        result = run_agent(verbose=True)
        sys.exit(0)

    # Set MBS token
    if args.set_token:
        from data.mbs_client import save_token
        save_token(args.set_token)
        print("✅ Token đã lưu.")
        return

    # Scheduler
    if args.schedule:
        from scheduler.trading_schedule import run_scheduler
        run_scheduler(blocking=True)
        return

    # Chỉ thị trường
    if args.market:
        ok = run_market_analysis()
        sys.exit(0 if ok else 1)

    # Chỉ danh mục
    if args.portfolio:
        ok = run_portfolio_analysis()
        sys.exit(0 if ok else 1)

    # Mặc định: báo cáo tích hợp đầy đủ
    ok = run_full_report()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()