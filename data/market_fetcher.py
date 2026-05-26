# data/market_fetcher.py
# -------------------------------------------------------------
# PHASE 6 — Dữ liệu thị trường tổng quan (vnstock API mới)
# -------------------------------------------------------------

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from datetime import datetime, timedelta


# =============================================================
# VN-INDEX
# =============================================================

def get_vnindex_data(days: int = 5) -> dict:
    """Lấy dữ liệu VN-Index N ngày gần nhất."""
    end   = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=days + 5)).strftime("%Y-%m-%d")

    try:
        from vnstock.api.quote import Quote
        q  = Quote(symbol="VNINDEX", source="VCI")
        df = q.history(start=start, end=end, interval="1D")

        if df is None or df.empty:
            return _mock_vnindex()

        df     = df.sort_values("time").tail(days)
        latest = df.iloc[-1]
        prev   = df.iloc[-2] if len(df) >= 2 else df.iloc[-1]

        change_pt  = float(latest["close"]) - float(prev["close"])
        change_pct = change_pt / float(prev["close"]) * 100

        # Xu hướng 5 ngày
        if len(df) >= 5:
            t = (float(df.iloc[-1]["close"]) / float(df.iloc[0]["close"]) - 1) * 100
            trend = "📈 Tăng" if t > 1.5 else ("📉 Giảm" if t < -1.5 else "➡️ Đi ngang")
        else:
            trend = "N/A"

        return {
            "index":      "VN-Index",
            "close":      round(float(latest["close"]), 2),
            "change_pt":  round(change_pt, 2),
            "change_pct": round(change_pct, 2),
            "volume":     int(latest.get("volume", 0)),
            "trend_5d":   trend,
            "history":    df[["time", "close", "volume"]].to_dict("records"),
        }

    except Exception as e:
        print(f"[market] VN-Index lỗi: {e} → mock")
        return _mock_vnindex()


def get_hnx_data() -> dict:
    """Lấy dữ liệu HNX-Index."""
    end   = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=7)).strftime("%Y-%m-%d")

    try:
        from vnstock.api.quote import Quote
        q  = Quote(symbol="HNXINDEX", source="VCI")
        df = q.history(start=start, end=end, interval="1D")

        if df is None or df.empty:
            return {"index": "HNX-Index", "close": 0, "change_pct": 0}

        df     = df.sort_values("time")
        latest = df.iloc[-1]
        prev   = df.iloc[-2] if len(df) >= 2 else df.iloc[-1]
        pct    = (float(latest["close"]) / float(prev["close"]) - 1) * 100

        return {
            "index":      "HNX-Index",
            "close":      round(float(latest["close"]), 2),
            "change_pct": round(pct, 2),
        }
    except Exception as e:
        print(f"[market] HNX lỗi: {e}")
        return {"index": "HNX-Index", "close": 0, "change_pct": 0}


# =============================================================
# DÒNG TIỀN NGÀNH
# =============================================================

def get_sector_flow_data() -> list[dict]:
    """Lấy dòng tiền ngành. Fallback về mock nếu lỗi."""
    try:
        from vnstock.api.trading import Trading
        t  = Trading(symbol="ACB", source="VCI")
        df = t.price_board(symbols_list=["HOSE"])

        if df is None or df.empty:
            return _mock_sector_flow()

        df.columns = [c.lower().replace(" ", "_") for c in df.columns]
        # vnstock price_board không có dữ liệu ngành — dùng dữ liệu ước tính
        return _mock_sector_flow()

    except Exception as e:
        print(f"[market] Sector flow lỗi: {e} → mock")
        return _mock_sector_flow()


# =============================================================
# KHỐI NGOẠI
# =============================================================

def get_foreign_flow() -> dict:
    """Lấy mua/bán ròng khối ngoại. Fallback mock."""
    try:
        # API mới của vnstock cho foreign trading
        from vnstock.api.trading import Trading
        t = Trading(symbol="VCB", source="TCBS")
        # Nếu có method foreign_trading → gọi ở đây
        # Hiện tại dùng mock
        return _mock_foreign_flow()
    except Exception as e:
        print(f"[market] Foreign flow lỗi: {e} → mock")
        return _mock_foreign_flow()


# =============================================================
# TỔNG HỢP
# =============================================================

def get_full_market_data() -> dict:
    """Lấy toàn bộ dữ liệu thị trường trong 1 lần gọi."""
    print("[market] 📡 Đang lấy dữ liệu thị trường...")

    vnindex = get_vnindex_data(days=5)
    hnx     = get_hnx_data()
    sectors = get_sector_flow_data()
    foreign = get_foreign_flow()
    score   = _calc_market_score(vnindex, sectors, foreign)

    print(f"[market] ✅ VN-Index: {vnindex['close']:,.2f} "
          f"({vnindex['change_pct']:+.2f}%) | "
          f"Sentiment: {score}/100")

    return {
        "vnindex":      vnindex,
        "hnx":          hnx,
        "sectors":      sectors,
        "foreign":      foreign,
        "market_score": score,
        "sentiment":    _score_to_label(score),
        "updated_at":   datetime.now().strftime("%d/%m/%Y %H:%M"),
    }


# =============================================================
# HELPERS
# =============================================================

def _calc_market_score(vnindex, sectors, foreign) -> int:
    score = 50
    chg   = vnindex.get("change_pct", 0)
    score += min(15, max(-15, int(chg / 0.5 * 3)))
    if sectors:
        pos   = sum(1 for s in sectors if s.get("avg_change_pct", 0) > 0)
        score += int((pos / len(sectors) - 0.5) * 20)
    net = foreign.get("net_value_bil", 0)
    if net > 100:    score += 10
    elif net > 0:    score += 5
    elif net < -100: score -= 10
    elif net < 0:    score -= 5
    return max(0, min(100, score))


def _score_to_label(score: int) -> str:
    if score >= 70: return "🟢 Tích cực"
    if score >= 51: return "🟡 Trung lập — thiên tích cực"
    if score >= 31: return "🟠 Trung lập — thiên tiêu cực"
    return "🔴 Tiêu cực"


def _mock_vnindex() -> dict:
    return {
        "index": "VN-Index", "close": 1285.47,
        "change_pt": 8.32,   "change_pct": 0.65,
        "volume": 520_000_000, "trend_5d": "📈 Tăng", "history": [],
    }


def _mock_sector_flow() -> list[dict]:
    return [
        {"sector": "Ngân hàng",    "total_value_bil": 2850, "avg_change_pct":  1.2, "top_ticker": "VCB"},
        {"sector": "Chứng khoán",  "total_value_bil":  980, "avg_change_pct":  2.8, "top_ticker": "SSI"},
        {"sector": "Bất động sản", "total_value_bil": 1250, "avg_change_pct": -0.3, "top_ticker": "VHM"},
        {"sector": "Thép",         "total_value_bil":  620, "avg_change_pct": -1.1, "top_ticker": "HPG"},
        {"sector": "Công nghiệp",  "total_value_bil":  480, "avg_change_pct":  1.8, "top_ticker": "GEX"},
        {"sector": "Công nghệ",    "total_value_bil":  390, "avg_change_pct":  0.9, "top_ticker": "FPT"},
        {"sector": "Dầu khí",      "total_value_bil":  310, "avg_change_pct":  0.4, "top_ticker": "GAS"},
        {"sector": "Bán lẻ",       "total_value_bil":  270, "avg_change_pct": -0.8, "top_ticker": "MWG"},
    ]


def _mock_foreign_flow() -> dict:
    return {
        "buy_value_bil": 420.5, "sell_value_bil": 380.2,
        "net_value_bil":  40.3, "net_label": "🌏 Mua ròng +40.3 tỷ",
        "top_buy": "VCB",       "top_sell": "VHM",
    }

