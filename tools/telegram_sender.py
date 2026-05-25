# tools/telegram_sender.py
# -------------------------------------------------------------
# PHASE 2 — MCP Tool: Gửi tin nhắn Telegram
#
# Kiến thức mới:
#   - requests (gọi HTTP API)
#   - async/await cơ bản (telegram bot dùng bất đồng bộ)
#   - String formatting nâng cao
#   - Markdown trong Telegram (bold, italic, code)
# -------------------------------------------------------------

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import requests
from langchain_core.tools import tool
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from datetime import datetime


# =============================================================
# HÀM NỘI BỘ: Gửi tin nhắn (dùng requests thay vì async)
# =============================================================

def _send_message(text: str, parse_mode: str = "HTML") -> bool:
    """
    Gửi tin nhắn qua Telegram Bot API.

    Telegram hỗ trợ 2 kiểu format:
    - HTML:     <b>đậm</b>, <i>nghiêng</i>, <code>code</code>
    - Markdown: *đậm*, _nghiêng_, `code`

    Trả về True nếu gửi thành công.
    """
    if not TELEGRAM_BOT_TOKEN:
        # Chưa cấu hình — in ra console thay thế
        print("\n" + "─" * 50)
        print("📱 [TELEGRAM MOCK — chưa cấu hình token]")
        print("─" * 50)
        print(text)
        print("─" * 50 + "\n")
        return True

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       text,
        "parse_mode": parse_mode,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print(f"[telegram] ✅ Gửi thành công")
            return True
        else:
            print(f"[telegram] ❌ Lỗi {response.status_code}: {response.text}")
            return False
    except requests.exceptions.Timeout:
        print("[telegram] ❌ Timeout — kiểm tra kết nối mạng")
        return False
    except Exception as e:
        print(f"[telegram] ❌ Lỗi: {e}")
        return False


def _format_market_report(sector_data: dict) -> str:
    """
    Format báo cáo thị trường thành tin nhắn HTML đẹp cho Telegram.
    """
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    lines = [
        f"📊 <b>BÁO CÁO THỊ TRƯỜNG</b>",
        f"🕐 {now}",
        f"",
        f"<b>Tổng quan:</b> {sector_data.get('market_sentiment', 'N/A')}",
        f"💰 Tổng GTGD: <b>{sector_data.get('total_market_bil', 0):,.0f} tỷ</b>",
        f"📈 Tỷ lệ ngành tăng: <b>{sector_data.get('positive_ratio', 0):.0f}%</b>",
        f"",
        f"<b>🟢 Top dòng tiền vào:</b>",
    ]

    for i, s in enumerate(sector_data.get("top_inflow", [])[:3], 1):
        change = s.get("avg_change_pct", 0)
        sign   = "+" if change >= 0 else ""
        lines.append(
            f"  {i}. {s['sector']} — "
            f"{s['total_value_bil']:,.0f} tỷ "
            f"({sign}{change:.1f}%)"
        )

    lines += ["", "<b>🔴 Top dòng tiền ra:</b>"]
    for i, s in enumerate(sector_data.get("top_outflow", [])[:3], 1):
        change = s.get("avg_change_pct", 0)
        sign   = "+" if change >= 0 else ""
        lines.append(
            f"  {i}. {s['sector']} — "
            f"{s['total_value_bil']:,.0f} tỷ "
            f"({sign}{change:.1f}%)"
        )

    lines += ["", f"<i>{sector_data.get('summary', '')}</i>"]
    return "\n".join(lines)


def _format_portfolio_report(portfolio_analysis: list) -> str:
    """
    Format phân tích danh mục thành tin nhắn Telegram.
    """
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    lines = [
        f"💼 <b>DANH MỤC CÁ NHÂN</b>",
        f"🕐 {now}",
        f"",
    ]

    for item in portfolio_analysis:
        ticker   = item.get("ticker", "?")
        pnl      = item.get("pnl_pct", 0)
        pnl_icon = "🟢" if pnl >= 0 else "🔴"
        price    = item.get("current_price", 0)
        rsi      = item.get("rsi", "N/A")
        signals  = item.get("signals", [])

        lines.append(
            f"{pnl_icon} <b>{ticker}</b> — "
            f"{price:,}đ | P&L: {pnl:+.1f}%"
        )
        if rsi:
            lines.append(f"   RSI: {rsi}")
        if signals:
            lines.append(f"   {signals[0]}")   # chỉ tín hiệu đầu tiên
        lines.append("")

    return "\n".join(lines)


# =============================================================
# TOOL 1: Gửi báo cáo thị trường
# =============================================================
@tool
def send_market_report(sector_analysis: dict) -> bool:
    """
    Format và gửi báo cáo tổng quan thị trường qua Telegram.

    Args:
        sector_analysis: dict từ tool analyze_sector_flow
    """
    message = _format_market_report(sector_analysis)
    return _send_message(message)


# =============================================================
# TOOL 2: Gửi phân tích danh mục
# =============================================================
@tool
def send_portfolio_report(portfolio_analysis: list) -> bool:
    """
    Format và gửi phân tích danh mục cá nhân qua Telegram.

    Args:
        portfolio_analysis: list từ tool scan_portfolio_signals
    """
    message = _format_portfolio_report(portfolio_analysis)
    return _send_message(message)


# =============================================================
# TOOL 3: Gửi cảnh báo tùy chỉnh
# =============================================================
@tool
def send_alert(message: str, level: str = "info") -> bool:
    """
    Gửi cảnh báo nhanh qua Telegram.

    Args:
        message: Nội dung cảnh báo
        level: "info" | "warning" | "danger"
    """
    icons = {"info": "ℹ️", "warning": "⚠️", "danger": "🚨"}
    icon  = icons.get(level, "ℹ️")
    now   = datetime.now().strftime("%H:%M")
    text  = f"{icon} <b>[{level.upper()}] {now}</b>\n{message}"
    return _send_message(text)


# =============================================================
# HƯỚNG DẪN TẠO BOT TELEGRAM
# =============================================================
SETUP_GUIDE = """
Cách lấy Telegram Bot Token:
1. Mở Telegram → tìm @BotFather
2. Gửi: /newbot
3. Đặt tên bot, đặt username (kết thúc bằng 'bot')
4. Copy token dán vào config.py → TELEGRAM_BOT_TOKEN

Cách lấy Chat ID:
1. Tìm @userinfobot trên Telegram
2. Gửi /start
3. Copy "Id:" dán vào config.py → TELEGRAM_CHAT_ID
"""


# =============================================================
# CHẠY THỬ
# =============================================================
if __name__ == "__main__":
    print(SETUP_GUIDE)
    print("=" * 55)
    print("TEST: Gửi báo cáo thị trường (mock)")
    print("=" * 55)

    # Dữ liệu mẫu
    mock_sector = {
        "market_sentiment": "🟢 Tích cực",
        "total_market_bil": 18500,
        "positive_ratio":   65.0,
        "summary":          "Dòng tiền tập trung vào Ngân hàng, thị trường tích cực.",
        "top_inflow": [
            {"sector": "Ngân hàng",     "total_value_bil": 4500, "avg_change_pct": 1.2},
            {"sector": "Chứng khoán",   "total_value_bil": 1800, "avg_change_pct": 2.1},
            {"sector": "Công nghệ",     "total_value_bil": 900,  "avg_change_pct": 0.8},
        ],
        "top_outflow": [
            {"sector": "Thép",          "total_value_bil": 950,  "avg_change_pct": -1.3},
            {"sector": "Bất động sản",  "total_value_bil": 2100, "avg_change_pct": -0.5},
            {"sector": "Dầu khí",       "total_value_bil": 600,  "avg_change_pct":  0.8},
        ],
    }

    send_market_report.invoke({"sector_analysis": mock_sector})

    print("TEST: Gửi cảnh báo")
    send_alert.invoke({
        "message": "HPG vừa vượt MA20 với khối lượng lớn!",
        "level": "warning"
    })
