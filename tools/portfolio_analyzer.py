# tools/portfolio_analyzer.py
# -------------------------------------------------------------
# PHASE 4 — MCP Tool: Phân tích danh mục cá nhân
#
# Kiến thức mới bạn học ở file này:
#   - Tính P&L (Profit & Loss): lãi/lỗ thực tế
#   - Dict comprehension: {k: v for k, v in items}
#   - round(), abs(), sum() nâng cao
#   - Xử lý dữ liệu lồng nhau (nested dict/list)
# -------------------------------------------------------------

import sys, os, json
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from langchain_core.tools import tool
from data.fetcher import get_price_history, _mock_sector_flow
from data.db import get_price_history_from_db, save_portfolio_snapshot
from datetime import datetime


# =============================================================
# HÀM NỘI BỘ: Lấy giá hiện tại của một mã
# =============================================================
def _get_current_price(ticker: str, use_mock: bool = False) -> float:
    """
    Lấy giá đóng cửa gần nhất của một mã.
    Thử DB trước → vnstock API → mock nếu không có gì.
    """
    if use_mock:
        # Giá mock dựa trên seed cố định để test nhất quán
        mock_prices = {
            "VCB":  95600,
            "HPG":  23800,
            "FPT": 131000,
            "MWG":  62500,
            "VIC":  38200,
            "VHM":  28900,
            "TCB":  21400,
            "BID":  47800,
            "CTG":  33600,
            "VNM":  57000,
        }
        # Trả về giá mock nếu có, nếu không giả sử +5% so với giá vốn
        return mock_prices.get(ticker, 0)

    # Thử lấy từ DB
    df = get_price_history_from_db(ticker, days=1)
    if not df.empty and "close" in df.columns:
        return float(df["close"].iloc[-1])

    # Gọi API
    df = get_price_history(ticker, days=3)
    if not df.empty and "close" in df.columns:
        return float(df["close"].iloc[-1])

    return 0.0


# =============================================================
# TOOL 1: Tính P&L toàn bộ danh mục
# =============================================================
@tool
def calculate_portfolio_pnl(holdings: list, use_mock: bool = True) -> dict:
    """
    Tính lãi/lỗ (P&L) cho từng mã và toàn bộ danh mục.

    Công thức:
        P&L (đồng) = (giá hiện tại - giá vốn) × số lượng
        P&L (%)    = (giá hiện tại / giá vốn - 1) × 100

    Args:
        holdings: list dict, mỗi phần tử gồm:
                  {"ticker": "VCB", "quantity": 1000, "avg_cost": 85000}
        use_mock: True = dùng giá giả để test

    Returns:
        dict gồm từng mã và tổng danh mục
    """
    results      = []
    total_cost   = 0.0   # tổng vốn bỏ ra
    total_value  = 0.0   # tổng giá trị hiện tại

    for h in holdings:
        ticker    = h["ticker"]
        quantity  = h["quantity"]
        avg_cost  = h["avg_cost"]

        # Lấy giá hiện tại
        current_price = _get_current_price(ticker, use_mock=use_mock)

        # Nếu không lấy được giá → giả sử bằng giá vốn (P&L = 0)
        if current_price == 0:
            current_price = avg_cost
            print(f"[portfolio] ⚠️  Không có giá {ticker}, dùng giá vốn tạm thời")

        # Tính P&L
        cost_value    = avg_cost * quantity          # vốn bỏ ra
        market_value  = current_price * quantity     # giá trị hiện tại
        pnl_amount    = market_value - cost_value    # lãi/lỗ tuyệt đối (đồng)
        pnl_pct       = (current_price / avg_cost - 1) * 100  # lãi/lỗ %

        # Tích lũy tổng
        total_cost  += cost_value
        total_value += market_value

        # Tín hiệu đơn giản dựa trên P&L
        if pnl_pct >= 20:
            signal = "🏆 Lãi tốt — xem xét chốt một phần"
        elif pnl_pct >= 10:
            signal = "✅ Đang lãi — tiếp tục theo dõi"
        elif pnl_pct >= 0:
            signal = "➡️ Lãi nhẹ — HOLD"
        elif pnl_pct >= -10:
            signal = "⚠️ Lỗ nhẹ — theo dõi chặt"
        else:
            signal = "🚨 Lỗ nặng — xem xét cắt lỗ"

        results.append({
            "ticker":         ticker,
            "quantity":       quantity,
            "avg_cost":       avg_cost,
            "current_price":  current_price,
            "cost_value":     round(cost_value),
            "market_value":   round(market_value),
            "pnl_amount":     round(pnl_amount),
            "pnl_pct":        round(pnl_pct, 2),
            "signal":         signal,
            "sector":         h.get("sector", "Chưa phân loại"),
        })

    # Tổng danh mục
    total_pnl_amount = total_value - total_cost
    total_pnl_pct    = (total_value / total_cost - 1) * 100 if total_cost > 0 else 0

    # Sắp xếp: lãi nhiều nhất lên đầu
    results.sort(key=lambda x: x["pnl_pct"], reverse=True)

    return {
        "holdings":        results,
        "total_cost":      round(total_cost),
        "total_value":     round(total_value),
        "total_pnl":       round(total_pnl_amount),
        "total_pnl_pct":   round(total_pnl_pct, 2),
        "summary":         _build_pnl_summary(results, total_pnl_pct),
    }


# =============================================================
# TOOL 2: Phân tích phân bổ danh mục theo ngành
# =============================================================
@tool
def analyze_portfolio_allocation(holdings: list, use_mock: bool = True) -> dict:
    """
    Phân tích tỷ trọng danh mục theo từng mã và theo ngành.
    Phát hiện rủi ro tập trung (một mã/ngành chiếm quá lớn).

    Args:
        holdings: list dict với ticker, quantity, avg_cost, sector
        use_mock: True = dùng giá giả
    """
    # Tính giá trị từng mã
    items = []
    total_value = 0.0
    for h in holdings:
        price = _get_current_price(h["ticker"], use_mock=use_mock) or h["avg_cost"]
        value = price * h["quantity"]
        total_value += value
        items.append({**h, "market_value": value})

    if total_value == 0:
        return {"error": "Không tính được giá trị danh mục"}

    # Tỷ trọng từng mã
    for item in items:
        item["weight_pct"] = round(item["market_value"] / total_value * 100, 1)

    # Nhóm theo ngành
    sector_map = {}
    for item in items:
        sector = item.get("sector", "Khác")
        if sector not in sector_map:
            sector_map[sector] = {"value": 0, "tickers": []}
        sector_map[sector]["value"]   += item["market_value"]
        sector_map[sector]["tickers"].append(item["ticker"])

    sector_allocation = [
        {
            "sector":     s,
            "value":      round(d["value"]),
            "weight_pct": round(d["value"] / total_value * 100, 1),
            "tickers":    d["tickers"],
        }
        for s, d in sector_map.items()
    ]
    sector_allocation.sort(key=lambda x: x["weight_pct"], reverse=True)

    # ── Phát hiện rủi ro tập trung ──────────────────────────
    risks = []
    for item in items:
        if item["weight_pct"] > 30:
            risks.append(
                f"⚠️ {item['ticker']} chiếm {item['weight_pct']}% danh mục — quá tập trung"
            )
    for sec in sector_allocation:
        if sec["weight_pct"] > 50:
            risks.append(
                f"⚠️ Ngành {sec['sector']} chiếm {sec['weight_pct']}% — rủi ro tập trung ngành"
            )

    if not risks:
        risks.append("✅ Danh mục phân bổ hợp lý, không có rủi ro tập trung rõ ràng")

    return {
        "total_value":        round(total_value),
        "stock_allocation":   sorted(items, key=lambda x: x["weight_pct"], reverse=True),
        "sector_allocation":  sector_allocation,
        "concentration_risks": risks,
        "num_stocks":         len(items),
        "num_sectors":        len(sector_map),
    }


# =============================================================
# TOOL 3: Đọc file danh mục JSON
# =============================================================
@tool
def load_portfolio_from_file(file_path: str = "portfolio/my_portfolio.json") -> dict:
    """
    Đọc danh mục từ file JSON và lưu snapshot vào DB.
    Gọi tool này đầu tiên trước khi phân tích.

    Args:
        file_path: đường dẫn tới file JSON danh mục
    """
    # Thử nhiều đường dẫn
    paths_to_try = [
        file_path,
        os.path.join(os.path.dirname(os.path.dirname(__file__)), file_path),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "portfolio", "my_portfolio.json"),
    ]

    data = None
    for path in paths_to_try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"[portfolio] Đọc file: {path}")
            break

    if not data:
        return {"error": f"Không tìm thấy file danh mục: {file_path}"}

    holdings  = data.get("holdings", [])
    updated   = data.get("updated_at", "không rõ")

    # Lưu snapshot vào DB
    save_portfolio_snapshot(holdings)

    return {
        "holdings":    holdings,
        "updated_at":  updated,
        "num_stocks":  len(holdings),
        "tickers":     [h["ticker"] for h in holdings],
        "message":     f"Đọc được {len(holdings)} vị thế, cập nhật lúc {updated}",
    }


# =============================================================
# HÀM NỘI BỘ: Tạo summary text
# =============================================================
def _build_pnl_summary(results: list, total_pnl_pct: float) -> str:
    winning = [r for r in results if r["pnl_pct"] >= 0]
    losing  = [r for r in results if r["pnl_pct"] < 0]

    best  = results[0]  if results else None
    worst = results[-1] if results else None

    icon = "🟢" if total_pnl_pct >= 0 else "🔴"
    summary = f"{icon} Danh mục {total_pnl_pct:+.1f}% | "
    summary += f"{len(winning)} mã lãi, {len(losing)} mã lỗ"

    if best:
        summary += f" | Tốt nhất: {best['ticker']} ({best['pnl_pct']:+.1f}%)"
    if worst and worst['pnl_pct'] < 0:
        summary += f" | Kém nhất: {worst['ticker']} ({worst['pnl_pct']:+.1f}%)"

    return summary


# =============================================================
# CHẠY THỬ
# =============================================================
if __name__ == "__main__":
    # Danh mục mẫu
    sample_holdings = [
        {"ticker": "VCB",  "quantity": 1000, "avg_cost": 85000,  "sector": "Ngân hàng"},
        {"ticker": "HPG",  "quantity": 2000, "avg_cost": 26000,  "sector": "Thép"},
        {"ticker": "FPT",  "quantity": 500,  "avg_cost": 118000, "sector": "Công nghệ"},
        {"ticker": "MWG",  "quantity": 800,  "avg_cost": 70000,  "sector": "Bán lẻ"},
    ]

    print("=" * 55)
    print("TEST 1: Tính P&L danh mục")
    print("=" * 55)
    pnl = calculate_portfolio_pnl.invoke({
        "holdings": sample_holdings,
        "use_mock": True
    })
    print(f"\n📊 {pnl['summary']}")
    print(f"   Tổng vốn:    {pnl['total_cost']:>15,.0f} đ")
    print(f"   Giá trị HT:  {pnl['total_value']:>15,.0f} đ")
    print(f"   Lãi/lỗ:      {pnl['total_pnl']:>+15,.0f} đ\n")

    for h in pnl["holdings"]:
        print(f"   {h['ticker']:6s} | {h['current_price']:>8,}đ | "
              f"P&L {h['pnl_pct']:>+6.1f}% | {h['signal']}")

    print("\n" + "=" * 55)
    print("TEST 2: Phân bổ danh mục")
    print("=" * 55)
    alloc = analyze_portfolio_allocation.invoke({
        "holdings": sample_holdings,
        "use_mock": True
    })
    print(f"\n💼 {alloc['num_stocks']} mã / {alloc['num_sectors']} ngành")
    print(f"   Tổng giá trị: {alloc['total_value']:,.0f} đ\n")
    print("   Phân bổ ngành:")
    for s in alloc["sector_allocation"]:
        bar = "█" * int(s["weight_pct"] / 5)
        print(f"   {s['sector']:20s} {bar:10s} {s['weight_pct']:>5.1f}%")
    print("\n   Rủi ro:")
    for r in alloc["concentration_risks"]:
        print(f"   {r}")

    print("\n" + "=" * 55)
    print("TEST 3: Đọc file JSON")
    print("=" * 55)
    result = load_portfolio_from_file.invoke({})
    print(f"\n{result['message']}")
    print(f"   Mã: {result.get('tickers', [])}")
