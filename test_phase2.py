# test_phase2.py
# Chạy: python test_phase2.py
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))


def test_sector_flow_tool():
    print("=" * 55)
    print("TEST 1: analyze_sector_flow")
    print("=" * 55)
    from tools.sector_flow import analyze_sector_flow

    result = analyze_sector_flow.invoke({"use_mock": True})

    assert "top_inflow"       in result, "Thiếu top_inflow"
    assert "market_sentiment" in result, "Thiếu market_sentiment"
    assert "summary"          in result, "Thiếu summary"

    print(f"\n✅ Sentiment: {result['market_sentiment']}")
    print(f"✅ Summary: {result['summary']}")
    print(f"\n Top dòng tiền vào:")
    for s in result["top_inflow"]:
        print(f"   {s['sector']:20s} {s['total_value_bil']:>6.0f} tỷ")
    return True


def test_indicators_tool():
    print("\n" + "=" * 55)
    print("TEST 2: analyze_stock_technical")
    print("=" * 55)
    from tools.indicators import analyze_stock_technical, scan_portfolio_signals

    result = analyze_stock_technical.invoke({"ticker": "VCB", "use_mock": True})

    assert "rsi"     in result, "Thiếu RSI"
    assert "signals" in result, "Thiếu signals"

    print(f"\n✅ VCB — RSI: {result['rsi']} | {result['rsi_signal']}")
    print(f"✅ MA20: {result['ma20']:,}đ")
    for sig in result["signals"]:
        print(f"   {sig}")

    scan = scan_portfolio_signals.invoke({
        "tickers": ["VCB", "HPG", "FPT"],
        "use_mock": True
    })
    print(f"\n✅ Scan 3 mã thành công, {len(scan)} kết quả")
    return True


def test_telegram_tool():
    print("\n" + "=" * 55)
    print("TEST 3: Telegram sender (mock mode)")
    print("=" * 55)
    from tools.telegram_sender import send_alert

    ok = send_alert.invoke({
        "message": "Test từ Phase 2 — hệ thống hoạt động!",
        "level": "info"
    })
    assert ok, "Gửi Telegram thất bại"
    print("✅ Telegram mock OK")
    return True


if __name__ == "__main__":
    results = []
    results.append(("sector_flow tool",    test_sector_flow_tool()))
    results.append(("indicators tool",     test_indicators_tool()))
    results.append(("telegram tool",       test_telegram_tool()))

    print("\n" + "=" * 55)
    print("  KẾT QUẢ PHASE 2")
    print("=" * 55)
    all_pass = True
    for name, ok in results:
        print(f"  {'✅' if ok else '❌'} {name}")
        if not ok: all_pass = False

    if all_pass:
        print("\n🎉 Phase 2 hoàn thành! Sẵn sàng sang Phase 3 — LangGraph Agent.")
