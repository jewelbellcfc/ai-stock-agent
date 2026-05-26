# tools/sector_flow.py — Phân tích dòng tiền ngành

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from langchain_core.tools import tool   # decorator @tool
import pandas as pd
from data.fetcher import _mock_sector_flow, get_sector_flow
from data.db import get_latest_sector_flow, save_sector_flow



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

    df_sorted = df.sort_values("money_flow_score", ascending=False)

    top_inflow  = df_sorted.head(3)[["sector", "money_flow_score",
                                     "total_value_bil", "avg_change_pct"]].to_dict("records")
    top_outflow = df_sorted.tail(3)[["sector", "money_flow_score",
                                     "total_value_bil", "avg_change_pct"]].to_dict("records")

    positive_sectors = len(df[df["avg_change_pct"] > 0])
    total_sectors    = len(df)
    ratio            = positive_sectors / total_sectors if total_sectors > 0 else 0

    if ratio >= 0.6:
        sentiment = "🟢 Tích cực"
    elif ratio >= 0.4:
        sentiment = "🟡 Trung lập"
    else:
        sentiment = "🔴 Tiêu cực"

    total_market_value = df["total_value_bil"].sum()

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



@tool
def compare_sector_flow_trend(sector_name: str) -> dict:
    """
    So sánh dòng tiền của một ngành cụ thể hôm nay vs hôm qua.
    Giúp phát hiện xu hướng tăng/giảm đột biến.

    Args:
        sector_name: Tên ngành, ví dụ "Ngân hàng", "Bất động sản"
    """
    import sqlite3
    from config import DB_PATH

    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("""
                SELECT trade_date, total_value_bil, avg_change_pct
                FROM sector_flow
                WHERE sector = ?
                ORDER BY trade_date DESC
                LIMIT 2
            """, (sector_name,)).fetchall()
    except Exception:
        rows = []

    if len(rows) < 2:
        return {
            "sector":       sector_name,
            "signal":       "⚠️ Chưa đủ dữ liệu lịch sử để so sánh",
            "today_bil":    0,
            "yesterday_bil": 0,
            "change_pct":   0,
        }

    today_bil = rows[0][1] or 0
    yest_bil  = rows[1][1] or 0
    value_pct = (today_bil - yest_bil) / yest_bil * 100 if yest_bil else 0

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
        "sector":         sector_name,
        "today_date":     rows[0][0],
        "yesterday_date": rows[1][0],
        "today_bil":      round(today_bil, 1),
        "yesterday_bil":  round(yest_bil, 1),
        "change_pct":     round(value_pct, 1),
        "signal":         signal,
    }
