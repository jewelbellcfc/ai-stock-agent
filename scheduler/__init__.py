# scheduler/trading_schedule.py
# -------------------------------------------------------------
# PHASE 5 — Tự động hóa theo giờ giao dịch HOSE
#
# Lịch chạy:
#   08:30 — Báo cáo mở cửa (sync MBS + phân tích)
#   10:00 — Cảnh báo giữa phiên sáng
#   11:30 — Tổng kết phiên sáng
#   14:00 — Cảnh báo đầu phiên chiều
#   15:00 — Báo cáo đóng cửa (phân tích toàn ngày)
#
# Kiến thức mới:
#   - schedule library (lên lịch chạy task)
#   - threading (chạy nền không block)
#   - datetime.weekday() (bỏ qua thứ 7, CN)
#   - Snapshot so sánh (lưu giá đầu ngày để tính biến động)
# -------------------------------------------------------------

import sys, os, json, time, threading
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import schedule
from datetime import datetime, date
from data.mbs_client import MBSClient
from tools.telegram_sender import _send_message
from agent.report_pipeline import run_report_pipeline, fetch_data, sanitize_for_telegram

# File lưu snapshot đầu ngày để so sánh biến động
SNAPSHOT_FILE = "data/.daily_snapshot.json"


# =============================================================
# HELPER: Kiểm tra ngày giao dịch
# =============================================================

def is_trading_day() -> bool:
    """Thứ 2–6 mới là ngày giao dịch. Bỏ qua T7, CN."""
    return datetime.today().weekday() < 5   # 0=T2 ... 4=T6


def trading_day_only(func):
    """
    Decorator: tự động bỏ qua nếu không phải ngày giao dịch.
    Dùng: @trading_day_only trước def task():
    """
    def wrapper(*args, **kwargs):
        if not is_trading_day():
            day = datetime.today().strftime("%A")
            print(f"[scheduler] ⏭️  Bỏ qua ({day} — không phải ngày GD)")
            return
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


# =============================================================
# SNAPSHOT — lưu giá đầu ngày để tính biến động
# =============================================================

def save_daily_snapshot(holdings: list):
    """Lưu giá và P&L đầu ngày vào file."""
    today = date.today().isoformat()
    snapshot = {
        "date":     today,
        "holdings": {
            h["ticker"]: {
                "current_price": h.get("current_price", 0),
                "pnl_pct":       h.get("pnl_pct", 0),
                "market_value":  h.get("market_value", 0),
            }
            for h in holdings
        }
    }
    os.makedirs("data", exist_ok=True)
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(snapshot, f)
    print(f"[scheduler] 📸 Snapshot đầu ngày lưu: {len(holdings)} mã")


def load_daily_snapshot() -> dict:
    """Đọc snapshot đầu ngày. Trả về {} nếu không có hoặc khác ngày."""
    if not os.path.exists(SNAPSHOT_FILE):
        return {}
    try:
        with open(SNAPSHOT_FILE) as f:
            data = json.load(f)
        # Chỉ dùng snapshot của hôm nay
        if data.get("date") != date.today().isoformat():
            return {}
        return data.get("holdings", {})
    except Exception:
        return {}


# =============================================================
# CẢNH BÁO THÔNG MINH
# =============================================================

def check_alerts(current_holdings: list) -> list[str]:
    """
    So sánh danh mục hiện tại với snapshot đầu ngày.
    Trả về list cảnh báo cần gửi.

    Điều kiện cảnh báo:
    1. Mã lỗ tích lũy > 10% (từ giá vốn)
    2. Mã tăng/giảm đột biến > 5% trong ngày hôm nay
    """
    alerts    = []
    snapshot  = load_daily_snapshot()

    for h in current_holdings:
        ticker  = h["ticker"]
        pnl_pct = h.get("pnl_pct", 0)
        cur_px  = h.get("current_price", 0)

        # ── Cảnh báo 1: Lỗ tích lũy > 10% ─────────────────
        if pnl_pct <= -10:
            alerts.append(
                f"🚨 <b>{ticker}</b> đang lỗ <b>{pnl_pct:.1f}%</b> so với giá vốn\n"
                f"   Giá vốn: {h.get('avg_cost',0):,.0f} | "
                f"Giá TT: {cur_px:,.0f} | "
                f"Lỗ: {h.get('pnl_amount',0):,.0f}đ"
            )

        # ── Cảnh báo 2: Biến động > 5% trong ngày ──────────
        if snapshot and ticker in snapshot:
            open_px  = snapshot[ticker].get("current_price", 0)
            if open_px > 0 and cur_px > 0:
                day_change = (cur_px - open_px) / open_px * 100
                if abs(day_change) >= 5:
                    direction = "tăng 📈" if day_change > 0 else "giảm 📉"
                    alerts.append(
                        f"⚡ <b>{ticker}</b> {direction} <b>{day_change:+.1f}%</b> trong ngày\n"
                        f"   Đầu ngày: {open_px:,.0f} → Hiện tại: {cur_px:,.0f}"
                    )

    return alerts


def send_alerts_if_any(holdings: list):
    """Kiểm tra và gửi cảnh báo nếu có."""
    alerts = check_alerts(holdings)
    if not alerts:
        print("[scheduler] ✅ Không có cảnh báo")
        return

    now  = datetime.now().strftime("%H:%M")
    body = "\n\n".join(alerts)
    msg  = (
        f"⚠️ <b>CẢNH BÁO DANH MỤC</b> — {now}\n"
        f"{'─'*30}\n\n"
        f"{body}"
    )
    _send_message(sanitize_for_telegram(msg))
    print(f"[scheduler] 🚨 Đã gửi {len(alerts)} cảnh báo")


# =============================================================
# CÁC TASK THEO LỊCH
# =============================================================

@trading_day_only
def task_morning_open():
    """
    08:30 — Báo cáo mở cửa:
    Sync danh mục MBS → lưu snapshot → sinh báo cáo AI → gửi Telegram
    """
    print(f"\n[scheduler] ⏰ 08:30 — Báo cáo mở cửa")

    # Sync danh mục thật
    data = fetch_data()
    if not data or not data.get("holdings"):
        _send_message("⚠️ <b>Không lấy được danh mục MBS</b>\nKiểm tra token!")
        return

    # Lưu snapshot đầu ngày
    save_daily_snapshot(data["holdings"])

    # Chạy báo cáo AI
    run_report_pipeline()


@trading_day_only
def task_midmorning_alert():
    """10:00 — Kiểm tra cảnh báo giữa phiên sáng."""
    print(f"\n[scheduler] ⏰ 10:00 — Kiểm tra cảnh báo")
    data = fetch_data()
    if data and data.get("holdings"):
        send_alerts_if_any(data["holdings"])


@trading_day_only
def task_noon_summary():
    """
    11:30 — Tổng kết phiên sáng:
    Chỉ gửi tóm tắt nhanh P&L, không gọi LLM (tiết kiệm chi phí)
    """
    print(f"\n[scheduler] ⏰ 11:30 — Tổng kết phiên sáng")
    data = fetch_data()
    if not data or not data.get("holdings"):
        return

    holdings = data["holdings"]
    summary  = data["summary"]
    snapshot = load_daily_snapshot()
    now      = datetime.now().strftime("%H:%M")

    # Tính biến động so với đầu ngày
    changes = []
    for h in holdings:
        ticker = h["ticker"]
        cur_px = h.get("current_price", 0)
        if snapshot and ticker in snapshot:
            open_px = snapshot[ticker].get("current_price", 0)
            if open_px > 0:
                day_chg = (cur_px - open_px) / open_px * 100
                changes.append((ticker, day_chg, h.get("pnl_pct", 0)))

    # Format tin nhắn
    lines = [
        f"📊 <b>PHIÊN SÁNG — {now}</b>",
        f"{'─'*30}",
        f"💰 Tổng TT: <b>{summary['total_market']:,.0f}đ</b>",
        f"{'🟢' if summary['profit_ratio']>=0 else '🔴'} "
        f"P&amp;L: <b>{summary['profit_ratio']:+.2f}%</b>",
        "",
        "<b>Biến động trong ngày:</b>",
    ]

    if changes:
        changes.sort(key=lambda x: x[1], reverse=True)
        for ticker, day_chg, pnl in changes:
            icon = "🟢" if day_chg >= 0 else "🔴"
            lines.append(
                f"{icon} <code>{ticker:6s}</code> "
                f"hôm nay: <b>{day_chg:+.1f}%</b> | "
                f"tổng: {pnl:+.1f}%"
            )
    else:
        lines.append("  (Chưa có snapshot đầu ngày)")

    # Cảnh báo nếu có
    alerts = check_alerts(holdings)
    if alerts:
        lines += ["", f"⚠️ <b>{len(alerts)} cảnh báo:</b>"] + alerts

    _send_message(sanitize_for_telegram("\n".join(lines)))


@trading_day_only
def task_afternoon_alert():
    """14:00 — Kiểm tra cảnh báo đầu phiên chiều."""
    print(f"\n[scheduler] ⏰ 14:00 — Cảnh báo phiên chiều")
    data = fetch_data()
    if data and data.get("holdings"):
        send_alerts_if_any(data["holdings"])


@trading_day_only
def task_close():
    """
    15:00 — Báo cáo đóng cửa:
    Báo cáo AI đầy đủ + tổng kết cả ngày
    """
    print(f"\n[scheduler] ⏰ 15:00 — Báo cáo đóng cửa")
    run_report_pipeline()


# =============================================================
# KHỞI ĐỘNG SCHEDULER
# =============================================================

def setup_schedule():
    """Đăng ký tất cả task vào schedule."""
    schedule.clear()

    schedule.every().day.at("08:30").do(task_morning_open)
    schedule.every().day.at("10:00").do(task_midmorning_alert)
    schedule.every().day.at("11:30").do(task_noon_summary)
    schedule.every().day.at("14:00").do(task_afternoon_alert)
    schedule.every().day.at("15:00").do(task_close)

    print("\n[scheduler] 📅 Lịch đã đăng ký:")
    for job in schedule.get_jobs():
        print(f"   {job}")


def run_scheduler(blocking: bool = True):
    """
    Khởi động scheduler.

    blocking=True  → chạy vòng lặp vô tận (dùng cho production)
    blocking=False → chạy trên thread riêng (dùng khi test)
    """
    setup_schedule()

    # Gửi thông báo khởi động
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    _send_message(
        sanitize_for_telegram(
            f"🤖 <b>VN Stock Agent đã khởi động</b>\n"
            f"🕐 {now}\n"
            f"📅 Lịch: 08:30 | 10:00 | 11:30 | 14:00 | 15:00\n"
            f"<i>Chỉ chạy T2–T6 (ngày giao dịch)</i>"
        )
    )
    print(f"\n[scheduler] 🚀 Đang chạy... (Ctrl+C để dừng)")
    print(f"[scheduler] Giờ hiện tại: {datetime.now().strftime('%H:%M:%S')}")

    if blocking:
        _run_loop()
    else:
        t = threading.Thread(target=_run_loop, daemon=True)
        t.start()
        return t


def _run_loop():
    """Vòng lặp chính của scheduler."""
    while True:
        schedule.run_pending()
        time.sleep(30)   # check mỗi 30 giây


# =============================================================
# CHẠY NGAY LẬP TỨC (dùng để test)
# =============================================================

def run_task_now(task_name: str):
    """
    Chạy ngay một task cụ thể để test mà không cần đợi lịch.

    task_name: "open" | "alert" | "noon" | "close"
    """
    tasks = {
        "open":  task_morning_open,
        "alert": task_midmorning_alert,
        "noon":  task_noon_summary,
        "close": task_close,
    }
    task = tasks.get(task_name)
    if not task:
        print(f"[scheduler] ❌ Task không hợp lệ: {task_name}")
        print(f"   Có thể dùng: {list(tasks.keys())}")
        return

    print(f"[scheduler] ▶️  Chạy ngay task: {task_name}")
    # Bỏ decorator trading_day_only khi test thủ công
    task.__wrapped__() if hasattr(task, "__wrapped__") else task()


if __name__ == "__main__":
    # Khi chạy thẳng file này → khởi động scheduler
    run_scheduler(blocking=True)