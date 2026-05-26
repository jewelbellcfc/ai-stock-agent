# tools/indicators.py — Chỉ báo kỹ thuật (RSI, MA, tín hiệu)

import os
import sys
import random
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from langchain_core.tools import tool
from data.db import get_price_history_from_db
from data.fetcher import get_price_history



def _calc_ma(prices: list, period: int) -> list:
    ma = []
    for i in range(len(prices)):
        if i < period - 1:
            ma.append(None)
        else:
            window = prices[i - period + 1 : i + 1]
            ma.append(sum(window) / period)
    return ma


def _calc_rsi(prices: list, period: int = 14) -> float:
    if len(prices) < period + 1:
        return None

    # Tính thay đổi giá mỗi phiên
    changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]

    # Tách gains (tăng) và losses (giảm)
    gains  = [c if c > 0 else 0 for c in changes]
    losses = [abs(c) if c < 0 else 0 for c in changes]

    # Lấy `period` phiên gần nhất
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0   # tăng liên tục, RSI = 100

    rs  = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 1)


def _interpret_rsi(rsi: float) -> str:
    """Diễn giải giá trị RSI thành tín hiệu."""
    if rsi is None:
        return "Không đủ dữ liệu"
    if rsi >= 70:
        return "⚠️ Mua quá mức (overbought) — thận trọng"
    if rsi >= 60:
        return "📈 Đà tăng mạnh"
    if rsi >= 40:
        return "➡️ Trung tính"
    if rsi >= 30:
        return "📉 Đà giảm"
    return "🚨 Bán quá mức (oversold) — có thể hồi phục"



@tool
def analyze_stock_technical(ticker: str, use_mock: bool = False) -> dict:
    """
    Phân tích kỹ thuật cơ bản một mã cổ phiếu:
    RSI, MA20, MA50, tín hiệu mua/bán.

    Args:
        ticker: Mã cổ phiếu, ví dụ "VCB", "HPG", "FPT"
        use_mock: True = dùng dữ liệu giả để test
    """
    if use_mock:
        random.seed(42)
        base = 85000
        prices = [base]
        for _ in range(59):
            change = random.uniform(-0.02, 0.025)
            prices.append(round(prices[-1] * (1 + change)))
    else:
        df = get_price_history_from_db(ticker, days=60)
        if df.empty:
            df = get_price_history(ticker, days=60)
        if df.empty:
            return {"error": f"Không có dữ liệu cho {ticker}"}
        prices = df["close"].tolist()

    if len(prices) < 20:
        return {"error": f"Cần ít nhất 20 phiên, chỉ có {len(prices)}"}

    current_price = prices[-1]
    prev_price    = prices[-2]
    price_change  = (current_price - prev_price) / prev_price * 100

    ma20_list = _calc_ma(prices, 20)
    ma50_list = _calc_ma(prices, 50)
    ma20 = next((v for v in reversed(ma20_list) if v is not None), None)
    ma50 = next((v for v in reversed(ma50_list) if v is not None), None)
    rsi  = _calc_rsi(prices)

    signals = []

    if ma20 and ma50:
        if current_price > ma20 > ma50:
            signals.append("✅ Giá trên MA20 và MA50 — xu hướng tăng")
        elif current_price < ma20 < ma50:
            signals.append("❌ Giá dưới MA20 và MA50 — xu hướng giảm")
        elif current_price > ma20:
            signals.append("🔶 Giá trên MA20, dưới MA50 — tín hiệu hỗn hợp")

    if rsi:
        signals.append(_interpret_rsi(rsi))

    # Giá so với đỉnh/đáy 20 phiên
    high_20 = max(prices[-20:])
    low_20  = min(prices[-20:])
    pct_from_high = (current_price - high_20) / high_20 * 100
    pct_from_low  = (current_price - low_20) / low_20 * 100

    if pct_from_high > -3:
        signals.append("🔔 Gần đỉnh 20 phiên")
    if pct_from_low < 5:
        signals.append("💡 Gần đáy 20 phiên — vùng hỗ trợ")

    return {
        "ticker":         ticker,
        "current_price":  current_price,
        "price_change":   round(price_change, 2),
        "rsi":            rsi,
        "rsi_signal":     _interpret_rsi(rsi),
        "ma20":           round(ma20) if ma20 else None,
        "ma50":           round(ma50) if ma50 else None,
        "high_20d":       high_20,
        "low_20d":        low_20,
        "signals":        signals,
    }



@tool
def scan_portfolio_signals(tickers: list, use_mock: bool = False) -> list:
    """
    Quét tín hiệu kỹ thuật nhanh cho danh sách mã cổ phiếu.
    Trả về danh sách xếp theo mức độ cần chú ý.

    Args:
        tickers: Danh sách mã, ví dụ ["VCB", "HPG", "FPT"]
        use_mock: True = dùng dữ liệu giả
    """
    results = []
    for ticker in tickers:
        analysis = analyze_stock_technical.invoke({
            "ticker": ticker,
            "use_mock": use_mock
        })
        if "error" not in analysis:
            # Tính điểm ưu tiên để sắp xếp
            priority = 0
            rsi = analysis.get("rsi", 50) or 50
            if rsi > 70 or rsi < 30:
                priority += 2    # RSI cực đoan → ưu tiên cao
            if abs(analysis.get("price_change", 0)) > 2:
                priority += 1    # biến động mạnh

            results.append({**analysis, "priority": priority})

    # Sắp xếp: mã cần chú ý nhất lên đầu
    results.sort(key=lambda x: x["priority"], reverse=True)
    return results

