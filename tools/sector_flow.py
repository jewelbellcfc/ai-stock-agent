# tools/sector_flow.py
# -------------------------------------------------------------
# PHASE 2 — MCP Tool: Phân tích dòng tiền ngành
#
# Kiến thức mới bạn học ở file này:
#   - @tool decorator (biến hàm thường → LangGraph tool)
#   - Type hints: def foo(x: str) -> dict  (khai báo kiểu)
#   - Docstring (mô tả hàm — Agent đọc cái này để hiểu tool!)
#   - dict (từ điển key-value)
#   - sorted(), max(), min() với lambda
# -------------------------------------------------------------

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from langchain_core.tools import tool   # decorator @tool
import pandas as pd
from data.fetcher import _mock_sector_flow, get_sector_flow
from data.db import get_latest_sector_flow, save_sector_flow


# =============================================================
# TOOL 1: Lấy tổng quan dòng tiền ngành hôm nay
# =============================================================
@tool
def analyze_sector_flow(use_mock: bool = False) -> dict:
    """
    Phân tích dòng tiền luân chuyển giữa các ngành trên thị trường
    chứng khoán Việt Nam hôm nay.

    Trả về:
    - top_inflow: 3 ngành được mua vào mạnh nhất
    - top_outflow: 3 ngành bị bán ra mạnh nhất
    - market_sentiment: nhận định chung (tích cực/trung lập/tiêu cực)
    - summary: đoạn tóm tắt ngắn gọn

    Args:
        use_mock: True = dùng dữ liệu giả để test
    """
    # Lấy dữ liệu (mock hoặc thật)
    if use_mock:
        df = _mock_sector_flow()
    else:
        # Thử lấy từ DB trước (nhanh hơn)
        df = get_latest_sector_flow()
        if df.empty:
            df = get_sector_flow()          # gọi API nếu DB trống
            if df.empty:
                df = _mock_sector_flow()    # fallback cuối cùng

    # ── Xử lý dữ liệu ──────────────────────────────────────
    # sort_values: sắp xếp theo cột money_flow_score
    df_sorted = df.sort_values("money_flow_score", ascending=False)

    top_inflow  = df_sorted.head(3)[["sector", "money_flow_score",
                                     "total_value_bil", "avg_change_pct"]].to_dict("records")
    top_outflow = df_sorted.tail(3)[["sector", "money_flow_score",
                                     "total_value_bil", "avg_change_pct"]].to_dict("records")

    # Tính sentiment: nếu >50% ngành tăng → tích cực
    positive_sectors = len(df[df["avg_change_pct"] > 0])
    total_sectors    = len(df)
    ratio            = positive_sectors / total_sectors if total_sectors > 0 else 0

    if ratio >= 0.6:
        sentiment = "🟢 Tích cực"
    elif ratio >= 0.4:
        sentiment = "🟡 Trung lập"
    else:
        sentiment = "🔴 Tiêu cực"

    # Tổng giá trị giao dịch toàn thị trường
    total_market_value = df["total_value_bil"].sum()

    # ── Tạo summary text ────────────────────────────────────
    top_sector = top_inflow[0]["sector"] if top_inflow else "N/A"
    top_value  = top_inflow[0]["total_value_bil"] if top_inflow else 0

    summary = (
        f"Thị trường hôm nay {sentiment}. "
        f"Tổng giá trị giao dịch {total_market_value:.0f} tỷ đồng. "
        f"Dòng tiền tập trung mạnh nhất vào ngành {top_sector} "
        f"với {top_value:.0f} tỷ đồng. "
        f"{positive_sectors}/{total_sectors} ngành tăng điểm."
    )

    return {
        "top_inflow":       top_inflow,
        "top_outflow":      top_outflow,
        "market_sentiment": sentiment,
        "total_market_bil": round(total_market_value, 1),
        "positive_ratio":   round(ratio * 100, 1),
        "summary":          summary,
    }


# =============================================================
# TOOL 2: So sánh dòng tiền ngành hôm nay vs hôm qua
# =============================================================
@tool
def compare_sector_flow_trend(sector_name: str) -> dict:
    """
    So sánh dòng tiền của một ngành cụ thể hôm nay vs hôm qua.
    Giúp phát hiện xu hướng tăng/giảm đột biến.

    Args:
        sector_name: Tên ngành, ví dụ "Ngân hàng", "Bất động sản"
    """
    # Trong Phase 2 dùng mock data, Phase 4 sẽ nối DB thật
    mock_today     = {"total_value_bil": 4500, "avg_change_pct": 1.2}
    mock_yesterday = {"total_value_bil": 3800, "avg_change_pct": 0.3}

    value_change = mock_today["total_value_bil"] - mock_yesterday["total_value_bil"]
    value_pct    = value_change / mock_yesterday["total_value_bil"] * 100

    if value_pct > 20:
        signal = "⚡ Dòng tiền tăng đột biến — chú ý!"
    elif value_pct > 5:
        signal = "📈 Dòng tiền tăng nhẹ"
    elif value_pct < -20:
        signal = "🚨 Dòng tiền rút mạnh — cảnh báo!"
    elif value_pct < -5:
        signal = "📉 Dòng tiền giảm nhẹ"
    else:
        signal = "➡️ Dòng tiền ổn định"

    return {
        "sector":       sector_name,
        "today_bil":    mock_today["total_value_bil"],
        "yesterday_bil":mock_yesterday["total_value_bil"],
        "change_pct":   round(value_pct, 1),
        "signal":       signal,
    }


# =============================================================
# CHẠY THỬ
# =============================================================
if __name__ == "__main__":
    print("=" * 55)
    print("TEST: analyze_sector_flow")
    print("=" * 55)

    # Gọi tool bình thường như một hàm Python
    result = analyze_sector_flow.invoke({"use_mock": True})

    print(f"\n📊 {result['summary']}")
    print(f"\n🟢 Top dòng tiền vào:")
    for s in result["top_inflow"]:
        print(f"   {s['sector']:20s} | {s['total_value_bil']:>7.0f} tỷ | {s['avg_change_pct']:+.1f}%")

    print(f"\n🔴 Top dòng tiền ra:")
    for s in result["top_outflow"]:
        print(f"   {s['sector']:20s} | {s['total_value_bil']:>7.0f} tỷ | {s['avg_change_pct']:+.1f}%")

    print("\n" + "=" * 55)
    print("TEST: compare_sector_flow_trend")
    print("=" * 55)
    trend = compare_sector_flow_trend.invoke({"sector_name": "Ngân hàng"})
    print(f"\n{trend['signal']}")
    print(f"Hôm nay: {trend['today_bil']} tỷ | Hôm qua: {trend['yesterday_bil']} tỷ | "
          f"Thay đổi: {trend['change_pct']:+.1f}%")
