# tools/mbs_tools.py
# -------------------------------------------------------------
# MCP Tools — wrapper gọi MBSClient cho LangGraph Agent
# -------------------------------------------------------------

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from langchain_core.tools import tool
from data.mbs_client import MBSClient, save_token, load_token


def _get_client() -> MBSClient:
    return MBSClient()


# =============================================================
# TOOL 1: Lấy danh mục thật từ MBS
# =============================================================
@tool
def fetch_mbs_portfolio() -> dict:
    """
    Lấy danh mục cổ phiếu hiện tại trực tiếp từ tài khoản MBS.
    Trả về vị thế với giá vốn, giá thị trường, P&L thực tế.
    Gọi tool này đầu tiên để lấy dữ liệu danh mục thật.
    """
    client = _get_client()
    return client.to_standard_format()


# =============================================================
# TOOL 2: Sync danh mục → file JSON
# =============================================================
@tool
def sync_mbs_to_local() -> dict:
    """
    Đồng bộ danh mục từ MBS xuống portfolio/my_portfolio.json.
    Gọi mỗi buổi sáng trước khi chạy Agent để có dữ liệu mới nhất.
    """
    client  = _get_client()
    success = client.save_to_portfolio_file()
    if success:
        return {"success": True, "message": "✅ Đã sync danh mục từ MBS về local"}
    return {"success": False, "message": "❌ Sync thất bại — kiểm tra token"}


# =============================================================
# TOOL 3: Set token mới
# =============================================================
@tool
def set_mbs_token(token: str) -> dict:
    """
    Lưu Bearer token mới cho MBS API.
    Gọi tool này khi token hết hạn và bạn đã lấy token mới.

    Args:
        token: Bearer token từ app MBS, dạng "Bearer eyJhbGc..."
               hoặc chỉ cần phần token "eyJhbGc..." cũng được
    """
    save_token(token)
    # Test ngay sau khi set
    client = MBSClient(token=token)
    summary, positions = client.get_portfolio()
    if positions:
        return {
            "success": True,
            "message": f"✅ Token hợp lệ — {len(positions)} vị thế",
        }
    return {
        "success": False,
        "message": "⚠️  Token đã lưu nhưng API trả về rỗng — kiểm tra lại",
    }


if __name__ == "__main__":
    print("Test MBS Tools")
    result = fetch_mbs_portfolio.invoke({})
    if "error" in result:
        print(f"❌ {result['error']}")
        print("   Chạy: python data/mbs_client.py --token \"Bearer xxxx\"")
    else:
        holdings = result["holdings"]
        summary  = result["summary"]
        print(f"\n{'─'*55}")
        print(f"{'Mã':<8}{'SL':>7}{'Giá vốn':>12}{'Giá TT':>12}{'P&L%':>8}")
        print(f"{'─'*55}")
        for h in holdings:
            icon = "🟢" if h["pnl_pct"] >= 0 else "🔴"
            print(f"{icon}{h['ticker']:<7}{h['quantity']:>7,}"
                  f"{h['avg_cost']:>12,.0f}"
                  f"{h['current_price']:>12,.0f}"
                  f"{h['pnl_pct']:>+7.2f}%")
        print(f"{'─'*55}")
        print(f"{'TỔNG':>15}  "
              f"Thị trường: {summary['total_market']:>12,.0f}đ  "
              f"P&L: {summary['profit_ratio']:>+.2f}%")
