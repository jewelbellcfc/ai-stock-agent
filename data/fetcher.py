# data/fetcher.py
# -------------------------------------------------------------
# PHASE 1 — Lấy dữ liệu thị trường từ vnstock
#
# Kiến thức Python bạn sẽ học ở file này:
#   - import thư viện
#   - def function (hàm)
#   - try/except (bắt lỗi)
#   - pandas DataFrame (bảng dữ liệu)
#   - f-string (ghép chuỗi)
# -------------------------------------------------------------

import pandas as pd
from datetime import datetime, timedelta
from vnstock import Vnstock           # thư viện dữ liệu chứng khoán VN

# Import cấu hình từ file config.py cùng thư mục gốc
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import HISTORY_DAYS


# =============================================================
# HÀM 1: Lấy danh sách cổ phiếu theo ngành
# =============================================================
def get_stocks_by_sector() -> pd.DataFrame:
    """
    Trả về DataFrame gồm: ticker, organ_name, icb_name2 (tên ngành)
    Dữ liệu từ sàn HOSE + HNX.
    """
    try:
        stock = Vnstock().stock(symbol="VN30", source="VCI")
        # listing() trả về toàn bộ cổ phiếu đang niêm yết
        df = stock.listing.symbols_by_industries()
        print(f"[fetcher] Lấy được {len(df)} cổ phiếu từ sàn")
        return df
    except Exception as e:
        print(f"[fetcher] Lỗi get_stocks_by_sector: {e}")
        return pd.DataFrame()


# =============================================================
# HÀM 2: Lấy giá và khối lượng giao dịch hôm nay (intraday)
# =============================================================
def get_market_overview() -> pd.DataFrame:
    """
    Trả về snapshot thị trường: giá, % thay đổi, khối lượng,
    giá trị giao dịch của toàn bộ cổ phiếu.
    """
    try:
        stock = Vnstock().stock(symbol="VN30", source="VCI")
        df = stock.trading.price_board(
            symbols_list=["VN30"]   # lấy rổ VN30 làm mẫu nhanh
        )
        print(f"[fetcher] Market overview: {len(df)} mã")
        return df
    except Exception as e:
        print(f"[fetcher] Lỗi get_market_overview: {e}")
        return pd.DataFrame()


# =============================================================
# HÀM 3: Lấy lịch sử giá của một mã cụ thể
# =============================================================
def get_price_history(ticker: str, days: int = HISTORY_DAYS) -> pd.DataFrame:
    """
    Lấy lịch sử OHLCV (Open, High, Low, Close, Volume) của một mã.

    Ví dụ:
        df = get_price_history("VCB", days=30)
        print(df.tail())
    """
    end_date   = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        stock = Vnstock().stock(symbol=ticker, source="VCI")
        df = stock.quote.history(
            start=start_date,
            end=end_date,
            interval="1D"   # nến ngày
        )
        df["ticker"] = ticker   # thêm cột tên mã
        print(f"[fetcher] {ticker}: {len(df)} phiên từ {start_date} → {end_date}")
        return df
    except Exception as e:
        print(f"[fetcher] Lỗi get_price_history({ticker}): {e}")
        return pd.DataFrame()


# =============================================================
# HÀM 4: Lấy dòng tiền theo ngành (key function!)
# =============================================================
def get_sector_flow() -> pd.DataFrame:
    """
    Tính toán dòng tiền vào/ra theo từng ngành dựa trên:
      - Giá trị giao dịch (volume × price)
      - % thay đổi giá so với hôm qua

    Trả về DataFrame với các cột:
      sector | total_value | avg_change | money_flow_score
    """
    try:
        # Lấy toàn bộ cổ phiếu kèm ngành
        stock = Vnstock().stock(symbol="ACB", source="VCI")

        # Lấy dữ liệu bảng giá hôm nay
        df_price = stock.trading.price_board(symbols_list=["HOSE"])

        # ---- Xử lý dữ liệu ----
        # Đổi tên cột — xử lý cả MultiIndex (tuple) lẫn string
        df_price.columns = [
            "_".join(str(x) for x in c).lower().replace(" ", "_")
            if isinstance(c, tuple) else str(c).lower().replace(" ", "_")
            for c in df_price.columns
        ]

        # Tính giá trị giao dịch = giá × khối lượng (đơn vị: tỷ đồng)
        if "match_price" in df_price.columns and "total_volume" in df_price.columns:
            df_price["trade_value"] = (
                df_price["match_price"] * df_price["total_volume"] / 1e9
            )
        elif "price" in df_price.columns and "volume" in df_price.columns:
            df_price["trade_value"] = (
                df_price["price"] * df_price["volume"] / 1e9
            )

        print(f"[fetcher] Sector flow: lấy được {len(df_price)} mã")
        return df_price

    except Exception as e:
        print(f"[fetcher] Lỗi get_sector_flow: {e}")
        # Trả về dữ liệu giả để test khi chưa có mạng/API
        return _mock_sector_flow()


# =============================================================
# DỮ LIỆU GIẢ — dùng để test khi không có API
# =============================================================
def _mock_sector_flow() -> pd.DataFrame:
    """Dữ liệu mẫu để test logic mà không cần kết nối thật."""
    data = {
        "sector":            ["Ngân hàng", "BĐS", "Chứng khoán", "Thép", "Dầu khí"],
        "total_value_bil":   [4500, 2100, 1800, 950, 600],   # tỷ đồng
        "avg_change_pct":    [1.2, -0.5, 2.1, -1.3, 0.8],
        "advance_count":     [12, 5, 8, 3, 6],
        "decline_count":     [3, 9, 2, 10, 4],
    }
    df = pd.DataFrame(data)
    # Tính điểm dòng tiền đơn giản: giá trị × chiều giá
    df["money_flow_score"] = df["total_value_bil"] * df["avg_change_pct"] / 100
    return df


# =============================================================
# CHẠY THỬ TRỰC TIẾP (python data/fetcher.py)
# =============================================================
if __name__ == "__main__":
    print("=" * 50)
    print("TEST 1: Dòng tiền ngành (mock data)")
    print("=" * 50)
    df_flow = _mock_sector_flow()
    print(df_flow.to_string(index=False))

    print("\n" + "=" * 50)
    print("TEST 2: Lịch sử giá VCB (cần internet)")
    print("=" * 50)
    df_vcb = get_price_history("VCB", days=5)
    if not df_vcb.empty:
        print(df_vcb[["time", "open", "high", "low", "close", "volume"]].tail())
    else:
        print("Không lấy được dữ liệu — kiểm tra kết nối mạng")
