# data/mbs_client.py
# -------------------------------------------------------------
# MBS API Client — xác thực bằng Bearer token thủ công
#
# Cách dùng:
#   1. Lấy token từ app MBS / Postman
#   2. Chạy: python data/mbs_client.py --token "Bearer xxxx"
#      hoặc thêm MBS_TOKEN vào .env
#   3. Agent tự dùng token đó để gọi API
# -------------------------------------------------------------

import os, sys, json, argparse
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import requests
from dataclasses import dataclass, asdict
from typing import Optional
from config import MBS_TOKEN, MBS_MASTER_ACCOUNT, MBS_ACCOUNT

TOKEN_FILE = os.path.join(os.path.dirname(__file__), ".mbs_token.json")

# =============================================================
# DATA MODELS
# =============================================================

@dataclass
class StockPosition:
    ticker:        str
    quantity:      int      # sharesBalance = tổng CP đang nắm
    avg_cost:      float    # avgPrice
    current_price: float    # marketPrice
    market_value:  float    # marketValue
    gross_value:   float    # grossValue = giá vốn tổng
    pnl_amount:    float    # profit
    pnl_pct:       float    # profitRatio
    trade_type:    str      # "02" = thường, "07" = ký quỹ
    sector:        str = ""


@dataclass
class PortfolioSummary:
    shares_balance:    float   # tổng số CP
    available_balance: float   # CP khả dụng để bán
    gross_value:       float   # tổng giá vốn
    market_value:      float   # tổng giá trị thị trường
    profit:            float   # lãi/lỗ tổng
    profit_ratio:      float   # % lãi/lỗ


# =============================================================
# TOKEN MANAGER — lưu/đọc token từ file
# =============================================================

def save_token(token: str):
    """Lưu token xuống file để dùng lại."""
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump({"token": token}, f)
    print(f"[MBS] ✅ Token đã lưu vào {TOKEN_FILE}")


def load_token() -> str:
    """
    Đọc token theo thứ tự ưu tiên:
    1. File .mbs_token.json (set thủ công)
    2. Biến môi trường MBS_TOKEN trong .env
    """
    # Ưu tiên 1: file token
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE) as f:
                data = json.load(f)
            token = data.get("token", "")
            if token:
                return token
        except Exception:
            pass

    # Ưu tiên 2: .env
    if MBS_TOKEN:
        return MBS_TOKEN

    return ""


# =============================================================
# MBS CLIENT
# =============================================================

class MBSClient:
    BASE_URL       = "https://fot-api-web.mbs.com.vn"
    PORTFOLIO_PATH = "/v1/trade/info/s/portfolio/{master_account}"

    def __init__(self, token: str = ""):
        self.token          = token or load_token()
        self.master_account = MBS_MASTER_ACCOUNT
        self.account        = MBS_ACCOUNT
        self.session        = requests.Session()

        if not self.token:
            print("[MBS] ⚠️  Chưa có token! Chạy lệnh:")
            print("      python data/mbs_client.py --token \"Bearer xxxx\"")
        else:
            # Tự thêm "Bearer " nếu user quên
            if not self.token.startswith("Bearer "):
                self.token = f"Bearer {self.token}"
            self.session.headers.update({
                "Authorization": self.token,
                "Content-Type":  "application/json",
                "Accept":        "application/json",
            })
            print(f"[MBS] ✅ Token sẵn sàng ({self.token[:30]}...)")


    def get_portfolio(
        self,
        account: str = None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[PortfolioSummary | None, list[StockPosition]]:
        """
        Lấy danh mục từ MBS API.

        URL: /v1/trade/info/s/portfolio/{masterAccount}
             ?account=...&page=...&pageSize=...

        Trả về: (summary, [StockPosition, ...])
        """
        if not self.token:
            print("[MBS] ❌ Không có token")
            return None, []

        url = self.BASE_URL + self.PORTFOLIO_PATH.format(
            master_account=self.master_account
        )
        params = {
            "account":  account or self.account,
            "page":     page,
            "pageSize": page_size,
        }

        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            # ── Parse summary ────────────────────────────────
            raw_sum = data.get("summary", {})
            summary = PortfolioSummary(
                shares_balance    = raw_sum.get("sharesBalance", 0),
                available_balance = raw_sum.get("availableBalance", 0),
                gross_value       = raw_sum.get("grossValue", 0),
                market_value      = raw_sum.get("marketValue", 0),
                profit            = raw_sum.get("profit", 0),
                profit_ratio      = raw_sum.get("profitRatio", 0),
            )

            # ── Parse từng vị thế ────────────────────────────
            positions = []
            for item in data.get("items", []):
                pos = StockPosition(
                    ticker        = item.get("symbol", ""),
                    quantity      = int(item.get("sharesBalance", 0)),
                    avg_cost      = float(item.get("avgPrice", 0)),
                    current_price = float(item.get("marketPrice", 0)),
                    market_value  = float(item.get("marketValue", 0)),
                    gross_value   = float(item.get("grossValue", 0)),
                    pnl_amount    = float(item.get("profit", 0)),
                    pnl_pct       = float(item.get("profitRatio", 0)),
                    trade_type    = item.get("tradeType", "02"),
                    sector        = _guess_sector(item.get("symbol", "")),
                )
                if pos.ticker and pos.quantity > 0:
                    positions.append(pos)

            print(f"[MBS] ✅ {len(positions)} vị thế | "
                  f"Tổng TT: {summary.market_value:,.0f}đ | "
                  f"P&L: {summary.profit_ratio:+.2f}%")
            return summary, positions

        except requests.HTTPError as e:
            status = e.response.status_code
            if status == 401:
                print("[MBS] ❌ Token hết hạn hoặc không hợp lệ — cần set token mới")
            else:
                print(f"[MBS] ❌ HTTP {status}: {e.response.text[:200]}")
            return None, []
        except Exception as e:
            print(f"[MBS] ❌ Lỗi kết nối: {e}")
            return None, []


    def to_standard_format(self) -> dict:
        """
        Gọi API và chuyển sang format chuẩn của dự án.
        Dùng cho portfolio_analyzer và LangGraph Agent.
        """
        summary, positions = self.get_portfolio()

        if not positions:
            return {"error": "Không lấy được danh mục", "holdings": []}

        # Gộp các vị thế cùng ticker (tradeType 02 + 07)
        merged = {}
        for p in positions:
            if p.ticker not in merged:
                merged[p.ticker] = {
                    "ticker":         p.ticker,
                    "quantity":       0,
                    "avg_cost":       p.avg_cost,
                    "current_price":  p.current_price,
                    "market_value":   0.0,
                    "gross_value":    0.0,
                    "pnl_amount":     0.0,
                    "sector":         p.sector,
                    "trade_types":    [],
                }
            merged[p.ticker]["quantity"]     += p.quantity
            merged[p.ticker]["market_value"] += p.market_value
            merged[p.ticker]["gross_value"]  += p.gross_value
            merged[p.ticker]["pnl_amount"]   += p.pnl_amount
            merged[p.ticker]["trade_types"].append(p.trade_type)

        # Tính lại pnl_pct sau khi gộp
        holdings = []
        for h in merged.values():
            if h["gross_value"] > 0:
                h["pnl_pct"] = round(h["pnl_amount"] / h["gross_value"] * 100, 2)
            else:
                h["pnl_pct"] = 0.0
            holdings.append(h)

        # Sắp theo lãi nhiều nhất
        holdings.sort(key=lambda x: x["pnl_pct"], reverse=True)

        return {
            "holdings":    holdings,
            "summary": {
                "total_gross":    summary.gross_value    if summary else 0,
                "total_market":   summary.market_value   if summary else 0,
                "total_profit":   summary.profit         if summary else 0,
                "profit_ratio":   summary.profit_ratio   if summary else 0,
                "shares_balance": summary.shares_balance if summary else 0,
            },
            "updated_at":  __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source":      "MBS_API",
            "account":     self.account,
        }


    def save_to_portfolio_file(
        self,
        output_path: str = "portfolio/my_portfolio.json"
    ) -> bool:
        """Lấy danh mục thật → lưu vào file JSON chuẩn của dự án."""
        data = self.to_standard_format()
        if "error" in data:
            return False

        full_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), output_path
        )
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[MBS] ✅ Đã lưu {len(data['holdings'])} vị thế → {output_path}")
        return True


# =============================================================
# HELPER — đoán ngành từ ticker
# =============================================================

def _guess_sector(ticker: str) -> str:
    sector_map = {
        "VCB": "Ngân hàng",  "BID": "Ngân hàng",  "CTG": "Ngân hàng",
        "TCB": "Ngân hàng",  "MBB": "Ngân hàng",  "ACB": "Ngân hàng",
        "VPB": "Ngân hàng",  "HDB": "Ngân hàng",  "TPB": "Ngân hàng",
        "HPG": "Thép",       "HSG": "Thép",        "NKG": "Thép",
        "FPT": "Công nghệ",  "CMG": "Công nghệ",
        "VIC": "Bất động sản","VHM": "Bất động sản","NVL": "Bất động sản",
        "KDH": "Bất động sản","PDR": "Bất động sản","DXG": "Bất động sản",
        "SSI": "Chứng khoán","VND": "Chứng khoán", "HCM": "Chứng khoán",
        "MBS": "Chứng khoán","VCI": "Chứng khoán",
        "MWG": "Bán lẻ",     "FRT": "Bán lẻ",      "PNJ": "Bán lẻ",
        "GAS": "Dầu khí",    "PLX": "Dầu khí",     "BSR": "Dầu khí",
        "GEX": "Công nghiệp","CTD": "Xây dựng",
        "VNM": "Thực phẩm",  "SAB": "Thực phẩm",   "MSN": "Thực phẩm",
    }
    return sector_map.get(ticker.upper(), "Khác")


# =============================================================
# CLI — chạy thẳng để set token
# python data/mbs_client.py --token "Bearer eyJhbGc..."
# python data/mbs_client.py --test
# =============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MBS Client CLI")
    parser.add_argument("--token", type=str, help="Set Bearer token mới")
    parser.add_argument("--test",  action="store_true", help="Test kết nối API")
    parser.add_argument("--save",  action="store_true", help="Lưu danh mục vào portfolio JSON")
    args = parser.parse_args()

    # Lưu token mới
    if args.token:
        token = args.token
        if not token.startswith("Bearer "):
            token = f"Bearer {token}"
        save_token(token)
        print(f"[MBS] Token đã set. Chạy --test để kiểm tra.")

    # Test kết nối
    if args.test or args.save:
        client = MBSClient()
        summary, positions = client.get_portfolio()

        if positions:
            print(f"\n{'─'*60}")
            print(f"{'Mã':<8}{'Loại':<6}{'SL':>8}{'Giá vốn':>12}{'Giá TT':>12}{'P&L%':>8}")
            print(f"{'─'*60}")
            for p in positions:
                icon = "🟢" if p.pnl_pct >= 0 else "🔴"
                label = "Ký quỹ" if p.trade_type == "07" else "Thường"
                print(f"{icon}{p.ticker:<7}{label:<6}"
                      f"{p.quantity:>8,}"
                      f"{p.avg_cost:>12,.0f}"
                      f"{p.current_price:>12,.0f}"
                      f"{p.pnl_pct:>+7.2f}%")
            print(f"{'─'*60}")
            if summary:
                pnl_icon = "🟢" if summary.profit_ratio >= 0 else "🔴"
                print(f"{'TỔNG':>22}"
                      f"  Giá vốn: {summary.gross_value:>15,.0f}đ")
                print(f"{'':>22}"
                      f"  Thị trường: {summary.market_value:>12,.0f}đ")
                print(f"{'':>22}"
                      f"  {pnl_icon} P&L: {summary.profit:>+14,.0f}đ "
                      f"({summary.profit_ratio:+.2f}%)")

        if args.save and positions:
            client.save_to_portfolio_file()
