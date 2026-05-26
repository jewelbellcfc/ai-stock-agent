# data/fetcher.py — Lấy dữ liệu thị trường từ vnstock

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from datetime import datetime, timedelta
from config import HISTORY_DAYS


# =============================================================
# HÀM 1: Lấy lịch sử giá của một mã
# =============================================================
def get_price_history(ticker: str, days: int = HISTORY_DAYS) -> pd.DataFrame:
    """
    Lấy lịch sử OHLCV của một mã cổ phiếu.
    Dùng vnstock.api.quote.Quote (API mới từ 31/08/2025).
    """
    end_date   = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        from vnstock.api.quote import Quote
        q  = Quote(symbol=ticker, source="VCI")
        df = q.history(start=start_date, end=end_date, interval="1D")
        if df is None or df.empty:
            return pd.DataFrame()
        df["ticker"] = ticker
        print(f"[fetcher] {ticker}: {len(df)} phiên ({start_date} → {end_date})")
        return df
    except Exception as e:
        print(f"[fetcher] Lỗi get_price_history({ticker}): {e}")
        return pd.DataFrame()


# =============================================================
# HÀM 2: Lấy bảng giá nhiều mã (price board)
# =============================================================
def get_price_board(symbols: list[str]) -> pd.DataFrame:
    """
    Lấy snapshot giá hiện tại của một danh sách mã.
    Dùng vnstock.api.trading.Trading (API mới).
    """
    try:
        from vnstock.api.trading import Trading
        t  = Trading(symbol=symbols[0], source="VCI")
        df = t.price_board(symbols_list=symbols)
        if df is None or df.empty:
            return pd.DataFrame()
        print(f"[fetcher] Price board: {len(df)} mã")
        return df
    except Exception as e:
        print(f"[fetcher] Lỗi get_price_board: {e}")
        return pd.DataFrame()


# =============================================================
# HÀM 3: Lấy danh sách cổ phiếu theo ngành
# =============================================================
def get_stocks_by_sector() -> pd.DataFrame:
    """Lấy danh sách niêm yết kèm ngành từ HOSE/HNX."""
    try:
        from vnstock.api.listing import Listing
        listing = Listing()
        df = listing.symbols_by_industries()
        if df is None or df.empty:
            return pd.DataFrame()
        print(f"[fetcher] Listing: {len(df)} cổ phiếu")
        return df
    except Exception as e:
        print(f"[fetcher] Lỗi get_stocks_by_sector: {e}")
        return pd.DataFrame()


# =============================================================
# HÀM 4: Dòng tiền ngành (fallback mock)
# =============================================================
def get_sector_flow() -> pd.DataFrame:
    """
    Tính dòng tiền ngành. Thử API thật trước,
    fallback về mock nếu lỗi.
    """
    try:
        # Thử lấy price board HOSE để tính dòng tiền
        from vnstock.api.trading import Trading
        t  = Trading(symbol="ACB", source="VCI")
        df = t.price_board(symbols_list=["HOSE"])
        if df is None or df.empty:
            return _mock_sector_flow()

        df.columns = [c.lower().replace(" ", "_") for c in df.columns]

        # Tính giá trị GD (tỷ đồng)
        for price_col in ["match_price", "price", "close"]:
            for vol_col in ["total_volume", "volume"]:
                if price_col in df.columns and vol_col in df.columns:
                    df["trade_value"] = df[price_col] * df[vol_col] / 1e9
                    break

        print(f"[fetcher] Sector flow: {len(df)} mã")
        return df

    except Exception as e:
        print(f"[fetcher] Sector flow fallback mock: {e}")
        return _mock_sector_flow()


# =============================================================
# MOCK DATA
# =============================================================
def _mock_sector_flow() -> pd.DataFrame:
    """Dữ liệu mẫu để test logic."""
    data = {
        "sector":          ["Ngân hàng", "BĐS", "Chứng khoán", "Thép", "Dầu khí"],
        "total_value_bil": [4500, 2100, 1800, 950, 600],
        "avg_change_pct":  [1.2, -0.5, 2.1, -1.3, 0.8],
        "advance_count":   [12, 5, 8, 3, 6],
        "decline_count":   [3, 9, 2, 10, 4],
    }
    df = pd.DataFrame(data)
    df["money_flow_score"] = df["total_value_bil"] * df["avg_change_pct"] / 100
    return df
