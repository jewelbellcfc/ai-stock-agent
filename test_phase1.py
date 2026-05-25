# test_phase1.py
# -------------------------------------------------------------
# Script kiểm tra Phase 1 hoạt động đúng
# Chạy: python test_phase1.py
# -------------------------------------------------------------

import gc
import os
import sys

# Đảm bảo Python tìm thấy các module trong dự án
sys.path.insert(0, os.path.dirname(__file__))


def test_imports():
    """Kiểm tra cài thư viện đúng chưa."""
    print("🔍 Kiểm tra thư viện...")
    errors = []

    try:
        import pandas as pd
        print(f"  ✅ pandas {pd.__version__}")
    except ImportError:
        print("  ❌ pandas — chạy: pip install pandas")
        errors.append("pandas")

    try:
        import vnstock
        print(f"  ✅ vnstock")
    except ImportError:
        print("  ❌ vnstock — chạy: pip install vnstock")
        errors.append("vnstock")

    try:
        import sqlite3
        print(f"  ✅ sqlite3 (có sẵn trong Python)")
    except ImportError:
        errors.append("sqlite3")

    return len(errors) == 0


def test_mock_data():
    """Kiểm tra dữ liệu mock hoạt động (không cần internet)."""
    print("\n📊 Kiểm tra dữ liệu mock...")
    from data.fetcher import _mock_sector_flow
    df = _mock_sector_flow()

    assert not df.empty, "DataFrame rỗng!"
    assert "sector" in df.columns, "Thiếu cột sector!"
    assert "money_flow_score" in df.columns, "Thiếu cột money_flow_score!"

    print(f"  ✅ Mock data: {len(df)} ngành")
    print(df[["sector", "total_value_bil", "avg_change_pct", "money_flow_score"]]
          .to_string(index=False))
    return True


def test_database():
    """Kiểm tra SQLite hoạt động."""
    print("\n💾 Kiểm tra database...")

    # Patch DB_PATH trực tiếp trên module data.db (không phải config)
    # vì data.db đã import DB_PATH thành biến local của nó rồi
    import data.db as db_module
    original_path = db_module.DB_PATH
    db_module.DB_PATH = "data/test_phase1.db"

    from data.db import init_db, save_sector_flow, get_latest_sector_flow
    from data.fetcher import _mock_sector_flow

    try:
        init_db()
        print("  ✅ Khởi tạo DB thành công")

        df_mock = _mock_sector_flow()
        save_sector_flow(df_mock, trade_date="2025-01-01")
        print("  ✅ Lưu dữ liệu thành công")

        df_read = get_latest_sector_flow()
        assert not df_read.empty, "Đọc từ DB rỗng!"
        print(f"  ✅ Đọc lại được {len(df_read)} dòng từ DB")
    finally:
        # Dọn dẹp luôn chạy dù test pass hay fail
        db_module.DB_PATH = original_path
        gc.collect()  # đóng các SQLite connection còn sót (cần thiết trên Windows)
        if os.path.exists("data/test_phase1.db"):
            os.remove("data/test_phase1.db")

    return True


def test_portfolio_json():
    """Kiểm tra đọc file danh mục."""
    print("\n📁 Kiểm tra portfolio JSON...")
    import json

    path = "portfolio/my_portfolio.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    holdings = data["holdings"]
    print(f"  ✅ Đọc được {len(holdings)} vị thế:")
    for h in holdings:
        value = h["quantity"] * h["avg_cost"] / 1_000_000
        print(f"     {h['ticker']:6s} | {h['quantity']:>6,} CP | "
              f"giá vốn {h['avg_cost']:>8,}đ | "
              f"tổng ~{value:.1f}tr")
    return True


# =============================================================
# MAIN
# =============================================================
if __name__ == "__main__":
    print("=" * 55)
    print("  PHASE 1 — KIỂM TRA HỆ THỐNG")
    print("=" * 55)

    results = []
    results.append(("Thư viện",      test_imports()))
    results.append(("Dữ liệu mock",  test_mock_data()))
    results.append(("Database",      test_database()))
    results.append(("Portfolio",     test_portfolio_json()))

    print("\n" + "=" * 55)
    print("  KẾT QUẢ")
    print("=" * 55)
    all_pass = True
    for name, ok in results:
        icon = "✅" if ok else "❌"
        print(f"  {icon} {name}")
        if not ok:
            all_pass = False

    if all_pass:
        print("\n🎉 Phase 1 hoàn thành! Sẵn sàng sang Phase 2.")
    else:
        print("\n⚠️  Một số bước chưa qua. Xem lỗi ở trên và sửa trước khi tiếp tục.")
