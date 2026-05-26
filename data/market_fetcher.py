# data/market_fetcher.py — Dữ liệu thị trường tổng quan (vnstock API)

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from datetime import datetime, timedelta


# =============================================================
# CACHE — tránh gọi price_board 2 lần trong 1 phiên
# =============================================================

_CACHE = {"df": None, "ts": None}
_CACHE_TTL = 300  # giây


def _get_price_board() -> pd.DataFrame:
    """
    Fetch price_board cho toàn bộ VN100 + VN30, gộp với phân ngành.
    Kết quả được cache 5 phút để sector_flow và foreign_flow
    dùng chung mà không tốn thêm API call.
    """
    now = datetime.now()
    if _CACHE["df"] is not None and _CACHE["ts"]:
        if (now - _CACHE["ts"]).total_seconds() < _CACHE_TTL:
            return _CACHE["df"]

    try:
        from vnstock.api.listing import Listing
        from vnstock.api.trading import Trading

        l   = Listing()
        ind = l.symbols_by_industries()

        # VN100 + VN30 — đại diện tốt cho thị trường, không quá nặng API
        vn100    = l.symbols_by_group("VN100").tolist()
        vn30     = l.symbols_by_group("VN30").tolist()
        universe = list(set(vn100 + vn30))

        t  = Trading(symbol="VCB", source="VCI")
        df = t.price_board(symbols_list=universe)

        # Flatten MultiIndex columns
        df.columns = ["_".join(c) for c in df.columns]
        df = df.rename(columns={"listing_symbol": "symbol"})

        # Merge ngành
        df = df.merge(ind, on="symbol", how="left")

        # Dùng giá ATC → ATO → reference (theo thứ tự ưu tiên)
        df["price"] = (
            df["match_match_price_atc"].where(df["match_match_price_atc"] > 0,
            df["match_match_price_ato"].where(df["match_match_price_ato"] > 0,
            df["match_reference_price"]))
        )

        # Lọc dòng không có giá tham chiếu
        df = df[df["match_reference_price"] > 0].copy()

        # Tính toán các chỉ số
        df["change_pct"]      = (df["price"] - df["match_reference_price"]) / df["match_reference_price"] * 100
        df["value_bil"]       = df["match_accumulated_value"] / 1000          # triệu VND → tỷ VND
        df["foreign_buy_bil"] = df["match_foreign_buy_value"]  / 1e9
        df["foreign_sel_bil"] = df["match_foreign_sell_value"] / 1e9
        df["foreign_net_bil"] = df["foreign_buy_bil"] - df["foreign_sel_bil"]

        _CACHE["df"] = df
        _CACHE["ts"] = now
        return df

    except Exception as e:
        print(f"[market] price_board lỗi: {e}")
        return pd.DataFrame()


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

        if len(df) >= 5:
            t     = (float(df.iloc[-1]["close"]) / float(df.iloc[0]["close"]) - 1) * 100
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
# DÒNG TIỀN NGÀNH — thực từ price_board + phân ngành ICB
# =============================================================

def get_sector_flow_data() -> list[dict]:
    """
    Tính dòng tiền ngành thực từ VN100+VN30 price_board.
    Gộp theo ICB industry, tính: tổng GTGD, %thay đổi trung bình,
    mã dẫn đầu, dòng tiền ngoại.
    """
    df = _get_price_board()
    if df.empty:
        return _mock_sector_flow()

    try:
        # Bỏ dòng không có ngành hoặc không có giá trị GD
        df = df[df["industry_name"].notna() & (df["value_bil"] > 0)]

        # Gộp theo ngành
        grp = (
            df.groupby("industry_name")
            .agg(
                total_value_bil=("value_bil",       "sum"),
                avg_change_pct =("change_pct",      "mean"),
                foreign_net_bil=("foreign_net_bil", "sum"),
                count          =("symbol",          "count"),
            )
            .reset_index()
        )

        # Mã dẫn đầu theo GTGD trong mỗi ngành
        top_idx     = df.groupby("industry_name")["value_bil"].idxmax()
        top_tickers = df.loc[top_idx, ["industry_name", "symbol"]].rename(
            columns={"symbol": "top_ticker"}
        )
        grp = grp.merge(top_tickers, on="industry_name", how="left")

        # Score dòng tiền = giá trị × hướng thay đổi
        grp["money_flow_score"] = grp["total_value_bil"] * grp["avg_change_pct"].apply(
            lambda x: 1 if x >= 0 else -1
        ) * grp["avg_change_pct"].abs().clip(0, 5)

        records = grp.sort_values("total_value_bil", ascending=False).to_dict("records")
        # Thêm alias 'sector' để tương thích với code hiện tại
        for r in records:
            r["sector"] = r["industry_name"]
        print(f"[market] ✅ Sector flow thực: {len(records)} ngành từ {len(df)} mã")
        return records

    except Exception as e:
        print(f"[market] Sector flow lỗi: {e} → mock")
        return _mock_sector_flow()


# =============================================================
# KHỐI NGOẠI — thực từ price_board
# =============================================================

def get_foreign_flow() -> dict:
    """
    Tổng hợp dòng tiền ngoại từ VN100+VN30 price_board.
    Trả về: tổng mua, bán, ròng và top mã mua/bán nhiều nhất.
    """
    df = _get_price_board()
    if df.empty:
        return _mock_foreign_flow()

    try:
        total_buy  = df["foreign_buy_bil"].sum()
        total_sell = df["foreign_sel_bil"].sum()
        net        = total_buy - total_sell

        top_buy  = df.nlargest(1, "foreign_buy_bil")["symbol"].values[0]  if len(df) else "N/A"
        top_sell = df.nlargest(1, "foreign_sel_bil")["symbol"].values[0]  if len(df) else "N/A"

        direction = "Mua ròng" if net >= 0 else "Bán ròng"
        sign      = "+" if net >= 0 else ""
        label     = f"🌏 {direction} {sign}{net:.1f} tỷ"

        return {
            "buy_value_bil":  round(total_buy,  1),
            "sell_value_bil": round(total_sell, 1),
            "net_value_bil":  round(net,         1),
            "net_label":      label,
            "top_buy":        top_buy,
            "top_sell":       top_sell,
        }

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
    sectors = get_sector_flow_data()   # dùng price_board cache
    foreign = get_foreign_flow()       # dùng price_board cache (không gọi API lần nữa)
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


# =============================================================
# MOCK FALLBACK
# =============================================================

def _mock_vnindex() -> dict:
    return {
        "index": "VN-Index", "close": 1285.47,
        "change_pt": 8.32, "change_pct": 0.65,
        "volume": 520_000_000, "trend_5d": "📈 Tăng", "history": [],
    }


def _mock_sector_flow() -> list[dict]:
    return [
        {"sector": "Ngân hàng",    "industry_name": "Ngân hàng",    "total_value_bil": 2850, "avg_change_pct":  1.2, "top_ticker": "VCB", "foreign_net_bil":  50, "money_flow_score": 3420},
        {"sector": "Chứng khoán",  "industry_name": "Chứng khoán",  "total_value_bil":  980, "avg_change_pct":  2.8, "top_ticker": "SSI", "foreign_net_bil":  10, "money_flow_score": 2744},
        {"sector": "Bất động sản", "industry_name": "Bất động sản", "total_value_bil": 1250, "avg_change_pct": -0.3, "top_ticker": "VHM", "foreign_net_bil": -20, "money_flow_score": -375},
        {"sector": "Thép",         "industry_name": "Vật liệu xây dựng", "total_value_bil":  620, "avg_change_pct": -1.1, "top_ticker": "HPG", "foreign_net_bil": -30, "money_flow_score": -682},
        {"sector": "Công nghiệp",  "industry_name": "Xây dựng",     "total_value_bil":  480, "avg_change_pct":  1.8, "top_ticker": "GEX", "foreign_net_bil":   5, "money_flow_score":  864},
        {"sector": "Công nghệ",    "industry_name": "Công nghệ và thông tin", "total_value_bil":  390, "avg_change_pct":  0.9, "top_ticker": "FPT", "foreign_net_bil":  15, "money_flow_score":  351},
    ]


def _mock_foreign_flow() -> dict:
    return {
        "buy_value_bil": 420.5, "sell_value_bil": 380.2,
        "net_value_bil":  40.3, "net_label": "🌏 Mua ròng +40.3 tỷ",
        "top_buy": "VCB", "top_sell": "VHM",
    }
