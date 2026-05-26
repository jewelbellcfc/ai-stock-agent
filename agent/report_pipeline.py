# agent/report_pipeline.py
# -------------------------------------------------------------
# Pipeline chính: MBS data → LLM phân tích → Telegram
#
# Chạy thẳng: python agent/report_pipeline.py
# -------------------------------------------------------------

import sys, os, json
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime
from langchain_core.messages import HumanMessage, SystemMessage

import re

from data.mbs_client import MBSClient
from tools.telegram_sender import _send_message
from agent.nodes import llm   # dùng LLM đã có fallback Anthropic → OpenAI


# =============================================================
# HELPER: Lọc HTML cho Telegram
# =============================================================

_TELEGRAM_ALLOWED_TAGS = {
    "b", "strong", "i", "em", "u", "s", "strike", "del",
    "a", "code", "pre", "tg-spoiler",
}

def sanitize_for_telegram(text: str) -> str:
    """Xóa HTML tag không hợp lệ, giữ lại tag Telegram hỗ trợ."""
    # <br> → newline
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)

    def _keep_allowed(m: re.Match) -> str:
        tag = m.group(1).strip().lstrip("/").split()[0].lower()
        return m.group(0) if tag in _TELEGRAM_ALLOWED_TAGS else ""

    text = re.sub(r"<(/?[a-zA-Z][^>]*)>", _keep_allowed, text)
    return text


def _split_message(text: str, limit: int = 4000) -> list:
    """Tách text thành các phần ≤ limit ký tự, cắt tại dòng mới."""
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


# =============================================================
# BƯỚC 1: Lấy dữ liệu từ MBS
# =============================================================

def fetch_data() -> dict:
    """Lấy danh mục thật từ MBS và trả về dict chuẩn."""
    print("[pipeline] 📡 Đang lấy danh mục từ MBS...")
    client = MBSClient()
    data   = client.to_standard_format()

    if "error" in data or not data.get("holdings"):
        print("[pipeline] ❌ Không lấy được danh mục!")
        print("   Chạy: python data/mbs_client.py --token \"Bearer xxxx\"")
        return {}

    n = len(data["holdings"])
    r = data["summary"]["profit_ratio"]
    print(f"[pipeline] ✅ {n} vị thế | P&L tổng: {r:+.2f}%")
    return data


# =============================================================
# BƯỚC 2: LLM sinh báo cáo
# =============================================================

SYSTEM_PROMPT = """Bạn là chuyên gia phân tích danh mục đầu tư chứng khoán Việt Nam.

Nhiệm vụ: Dựa trên dữ liệu danh mục thực tế từ công ty chứng khoán MBS,
hãy tạo báo cáo hàng ngày gồm 2 phần rõ ràng:

─────────────────────────────────────
PHẦN 1 — TỔNG QUAN DANH MỤC
─────────────────────────────────────
- Tổng giá trị thị trường và P&L tổng thể
- Nhận định ngắn: danh mục đang ở trạng thái nào (tốt/trung bình/cần chú ý)
- Số mã đang lãi / đang lỗ
- Mã lãi nhất và mã lỗ nhất

─────────────────────────────────────
PHẦN 2 — CHI TIẾT TỪNG MÃ
─────────────────────────────────────
Với mỗi mã, phân tích:
- Trạng thái P&L (lãi/lỗ bao nhiêu %)
- Khuyến nghị hành động: HOLD / CHỐT LỜI / CẮT LỖ / MUA THÊM
- 1 câu lý do ngắn gọn

Lưu ý quan trọng:
- Dùng emoji phù hợp cho dễ đọc trên Telegram
- Viết bằng tiếng Việt, ngắn gọn, thực tế
- Không cần giải thích lý thuyết
- Format HTML cho Telegram: <b>đậm</b>, <i>nghiêng</i>, <code>code</code>
- KHÔNG dùng <br> — xuống dòng bằng newline thông thường
- Với mã đang lỗ > 10%: nhấn mạnh rủi ro
- Với mã đang lãi > 15%: gợi ý chốt một phần
"""


def generate_report(data: dict) -> str:
    """
    Gọi LLM sinh báo cáo từ data MBS.
    Trả về chuỗi HTML đã format sẵn cho Telegram.
    """
    if not data:
        return ""

    holdings = data["holdings"]
    summary  = data["summary"]
    now      = datetime.now().strftime("%d/%m/%Y %H:%M")

    # ── Chuẩn bị dữ liệu gửi cho LLM ──────────────────────
    # Chỉ gửi những field cần thiết, bỏ field thừa
    clean_holdings = []
    for h in holdings:
        clean_holdings.append({
            "ticker":        h["ticker"],
            "quantity":      h["quantity"],
            "avg_cost":      h["avg_cost"],
            "current_price": h["current_price"],
            "market_value":  h["market_value"],
            "pnl_amount":    h["pnl_amount"],
            "pnl_pct":       h["pnl_pct"],
            "sector":        h.get("sector", ""),
        })

    user_prompt = f"""
Hôm nay: {now}
Tài khoản: {data.get('account', 'N/A')}

=== TỔNG DANH MỤC ===
Tổng giá vốn:      {summary['total_gross']:>15,.0f} đ
Tổng thị trường:   {summary['total_market']:>15,.0f} đ
Lãi/lỗ tổng:       {summary['total_profit']:>+15,.0f} đ ({summary['profit_ratio']:+.2f}%)
Tổng số CP:        {summary['shares_balance']:>15,.0f}

=== CHI TIẾT TỪNG VỊ THẾ ===
{json.dumps(clean_holdings, ensure_ascii=False, indent=2)}

Hãy tạo báo cáo theo đúng format 2 phần đã yêu cầu.
"""

    print("[pipeline] 🤖 LLM đang phân tích...")
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])

    report = sanitize_for_telegram(response.content)
    print(f"[pipeline] ✅ Báo cáo tạo xong ({len(report)} ký tự)")
    return report


# =============================================================
# BƯỚC 3: Gửi Telegram
# =============================================================

def send_report(report: str, data: dict) -> bool:
    """Thêm header/footer rồi gửi qua Telegram."""
    if not report:
        return False

    now    = datetime.now().strftime("%d/%m/%Y %H:%M")
    pnl    = data["summary"]["profit_ratio"]
    icon   = "🟢" if pnl >= 0 else "🔴"

    header = (
        f"{'─'*35}\n"
        f"📊 <b>BÁO CÁO DANH MỤC MBS</b>\n"
        f"🕐 {now}\n"
        f"{icon} P&amp;L tổng: <b>{pnl:+.2f}%</b>\n"
        f"{'─'*35}\n\n"
    )
    footer = (
        f"\n\n{'─'*35}\n"
        f"<i>🤖 Phân tích bởi VN Stock Agent</i>"
    )

    full_message = header + report + footer

    # Telegram giới hạn 4096 ký tự / tin nhắn → tách nếu quá dài
    parts = _split_message(full_message)
    all_ok = True
    for i, part in enumerate(parts, 1):
        prefix = f"<i>({i}/{len(parts)})</i>\n\n" if len(parts) > 1 else ""
        if not _send_message(prefix + part):
            all_ok = False
    return all_ok


# =============================================================
# PIPELINE CHÍNH
# =============================================================

def run_report_pipeline() -> bool:
    """
    Chạy toàn bộ pipeline:
    MBS → LLM → Telegram

    Trả về True nếu thành công.
    """
    print("\n" + "═"*50)
    print("  VN STOCK AGENT — BÁO CÁO HÀNG NGÀY")
    print("═"*50)

    # Bước 1: Lấy data
    data = fetch_data()
    if not data:
        return False

    # Bước 2: Sinh báo cáo
    report = generate_report(data)
    if not report:
        return False

    # Bước 3: In preview ra console
    print("\n" + "─"*50)
    print("PREVIEW BÁO CÁO:")
    print("─"*50)
    print(report[:800] + "..." if len(report) > 800 else report)
    print("─"*50)

    # Bước 4: Gửi Telegram
    print("\n[pipeline] 📱 Đang gửi Telegram...")
    ok = send_report(report, data)

    if ok:
        print("[pipeline] ✅ Gửi thành công!")
    else:
        print("[pipeline] ❌ Gửi thất bại — kiểm tra Telegram token")

    print("\n" + "═"*50)
    return ok


# =============================================================
# CHẠY THẲNG
# =============================================================

if __name__ == "__main__":
    run_report_pipeline()
