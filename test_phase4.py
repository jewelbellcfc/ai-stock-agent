# test_phase4.py
# Chạy: python test_phase4.py
import sys, os
sys.path.insert(0, os.path.dirname(__file__))


# =============================================================
# TEST 1: Portfolio P&L
# =============================================================
def test_pnl():
    print("=" * 55)
    print("TEST 1: Tính P&L danh mục")
    print("=" * 55)

    from tools.portfolio_analyzer import calculate_portfolio_pnl

    holdings = [
        {"ticker": "VCB",  "quantity": 1000, "avg_cost": 85000,  "sector": "Ngân hàng"},
        {"ticker": "HPG",  "quantity": 2000, "avg_cost": 26000,  "sector": "Thép"},
        {"ticker": "FPT",  "quantity": 500,  "avg_cost": 118000, "sector": "Công nghệ"},
        {"ticker": "MWG",  "quantity": 800,  "avg_cost": 70000,  "sector": "Bán lẻ"},
    ]

    result = calculate_portfolio_pnl.invoke({"holdings": holdings, "use_mock": True})

    assert "holdings"      in result
    assert "total_pnl_pct" in result
    assert "summary"       in result

    print(f"\n{result['summary']}")
    print(f"\n{'Mã':<8} {'Giá vốn':>10} {'Giá HT':>10} {'P&L%':>8}  Tín hiệu")
    print("-" * 65)
    for h in result["holdings"]:
        print(f"{h['ticker']:<8} {h['avg_cost']:>10,} {h['current_price']:>10,} "
              f"{h['pnl_pct']:>+7.1f}%  {h['signal']}")
    print("-" * 65)
    print(f"{'TỔNG':<8} {result['total_cost']:>10,.0f} {result['total_value']:>10,.0f} "
          f"{result['total_pnl_pct']:>+7.1f}%")

    print("\n✅ P&L calculation OK")
    return True


# =============================================================
# TEST 2: Portfolio Allocation
# =============================================================
def test_allocation():
    print("\n" + "=" * 55)
    print("TEST 2: Phân bổ danh mục")
    print("=" * 55)

    from tools.portfolio_analyzer import analyze_portfolio_allocation

    holdings = [
        {"ticker": "VCB",  "quantity": 1000, "avg_cost": 85000,  "sector": "Ngân hàng"},
        {"ticker": "HPG",  "quantity": 2000, "avg_cost": 26000,  "sector": "Thép"},
        {"ticker": "FPT",  "quantity": 500,  "avg_cost": 118000, "sector": "Công nghệ"},
        {"ticker": "MWG",  "quantity": 800,  "avg_cost": 70000,  "sector": "Bán lẻ"},
    ]

    result = analyze_portfolio_allocation.invoke({"holdings": holdings, "use_mock": True})

    assert "sector_allocation"    in result
    assert "concentration_risks"  in result

    print(f"\n💼 {result['num_stocks']} mã / {result['num_sectors']} ngành")
    print(f"   Tổng: {result['total_value']:,.0f} đ\n")

    print("   Phân bổ ngành:")
    for s in result["sector_allocation"]:
        bar = "█" * max(1, int(s["weight_pct"] / 4))
        print(f"   {s['sector']:22s} {bar:<15s} {s['weight_pct']:>5.1f}%  "
              f"({', '.join(s['tickers'])})")

    print("\n   Rủi ro tập trung:")
    for r in result["concentration_risks"]:
        print(f"   {r}")

    print("\n✅ Allocation analysis OK")
    return True


# =============================================================
# TEST 3: Load portfolio từ file JSON
# =============================================================
def test_load_portfolio():
    print("\n" + "=" * 55)
    print("TEST 3: Đọc file my_portfolio.json")
    print("=" * 55)

    from tools.portfolio_analyzer import load_portfolio_from_file

    result = load_portfolio_from_file.invoke({})

    if "error" in result:
        print(f"⚠️  {result['error']}")
        return True   # không fail, file có thể chưa có

    print(f"\n✅ {result['message']}")
    print(f"   Mã trong danh mục: {result['tickers']}")
    return True


# =============================================================
# TEST 4: Full portfolio_node (cần API key)
# =============================================================
def test_portfolio_node():
    print("\n" + "=" * 55)
    print("TEST 4: Portfolio Node (cần API key)")
    print("=" * 55)

    from config import ANTHROPIC_API_KEY, OPENAI_API_KEY
    if not ANTHROPIC_API_KEY and not OPENAI_API_KEY:
        print("⚠️  Chưa có API key — bỏ qua")
        return True

    try:
        from agent.nodes import portfolio_node
        from agent.state import get_initial_state

        state = get_initial_state()
        result = portfolio_node(state)

        assert "portfolio"    in result
        assert "messages"     in result
        assert "current_step" in result

        msgs = result["messages"]
        print(f"\n✅ Portfolio node OK")
        print(f"   Messages: {len(msgs)}")
        print(f"   Next step: {result['current_step']}")

        # In response của LLM nếu có
        for msg in msgs:
            if hasattr(msg, "content") and msg.content and not hasattr(msg, "tool_calls"):
                preview = str(msg.content)[:300]
                print(f"\n📋 LLM Response (preview):\n{preview}...")
                break

        return True
    except Exception as e:
        print(f"❌ Lỗi: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================================
# MAIN
# =============================================================
if __name__ == "__main__":
    results = []
    results.append(("P&L calculation",   test_pnl()))
    results.append(("Allocation",        test_allocation()))
    results.append(("Load JSON",         test_load_portfolio()))
    results.append(("Portfolio node",    test_portfolio_node()))

    print("\n" + "=" * 55)
    print("  KẾT QUẢ PHASE 4")
    print("=" * 55)
    all_pass = True
    for name, ok in results:
        print(f"  {'✅' if ok else '❌'} {name}")
        if not ok:
            all_pass = False

    if all_pass:
        print("\n🎉 Phase 4 hoàn thành!")
        print("   Tiếp theo: Phase 5 — tự động hóa + chạy hàng ngày.")
    else:
        print("\n⚠️  Xem lỗi ở trên.")
