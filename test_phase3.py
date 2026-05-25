# test_phase3.py
# Chạy: python test_phase3.py
# -------------------------------------------------------------
# Test Phase 3 theo 3 cấp độ:
#   Level 1: State hoạt động đúng không?
#   Level 2: Từng node chạy độc lập được không?
#   Level 3: Toàn bộ graph chạy end-to-end không?
# -------------------------------------------------------------

import sys, os
sys.path.insert(0, os.path.dirname(__file__))


# =============================================================
# LEVEL 1: Test State
# =============================================================
def test_state():
    print("=" * 55)
    print("LEVEL 1: Test State")
    print("=" * 55)

    from agent.state import AgentState, get_initial_state, print_state_summary

    state = get_initial_state()
    print_state_summary(state)

    assert "messages"      in state
    assert "sector_data"   in state
    assert "current_step"  in state
    assert state["current_step"] == "market"

    print("✅ State khởi tạo đúng")
    return True


# =============================================================
# LEVEL 2: Test từng Node (không cần gọi LLM thật)
# =============================================================
def test_routing_functions():
    """
    Test các hàm định tuyến mà không gọi LLM.
    Tạo State giả để kiểm tra logic rẽ nhánh.
    """
    print("\n" + "=" * 55)
    print("LEVEL 2: Test Routing Logic")
    print("=" * 55)

    from agent.graph import (
        _route_after_analyst,
        _route_after_portfolio,
        _route_after_reporter,
    )
    from langchain_core.messages import AIMessage

    # Tạo message giả CÓ tool_calls
    msg_with_tools = AIMessage(
        content="",
        tool_calls=[{"name": "analyze_sector_flow", "args": {}, "id": "test_1"}]
    )

    # Tạo message giả KHÔNG có tool_calls
    msg_no_tools = AIMessage(content="Phân tích xong rồi.")

    # Test 1: Sau analyst có tool calls → phải đi "tools"
    state_with_tools = {"messages": [msg_with_tools], "portfolio": None}
    route = _route_after_analyst(state_with_tools)
    assert route == "tools", f"Expected 'tools', got '{route}'"
    print("✅ Analyst + tool_calls → route: tools")

    # Test 2: Sau analyst không có tool calls → phải đi "portfolio"
    state_no_tools = {"messages": [msg_no_tools], "portfolio": None}
    route = _route_after_analyst(state_no_tools)
    assert route == "portfolio", f"Expected 'portfolio', got '{route}'"
    print("✅ Analyst + no tool_calls → route: portfolio")

    # Test 3: Sau portfolio không có tool calls → phải đi "reporter"
    route = _route_after_portfolio({"messages": [msg_no_tools]})
    assert route == "reporter", f"Expected 'reporter', got '{route}'"
    print("✅ Portfolio + no tool_calls → route: reporter")

    # Test 4: Sau reporter không có tool calls → phải kết thúc
    route = _route_after_reporter({"messages": [msg_no_tools]})
    assert route == "end", f"Expected 'end', got '{route}'"
    print("✅ Reporter + no tool_calls → route: end")

    return True


# =============================================================
# LEVEL 3: Test Graph build (không chạy LLM)
# =============================================================
def test_graph_build():
    print("\n" + "=" * 55)
    print("LEVEL 3: Test Graph Build")
    print("=" * 55)

    from agent.graph import build_graph

    try:
        app = build_graph()
        print(f"✅ Graph build thành công")
        print(f"   Nodes: {list(app.get_graph().nodes.keys())}")
        return True
    except Exception as e:
        print(f"❌ Graph build thất bại: {e}")
        return False


# =============================================================
# LEVEL 4: Chạy LLM thật (cần ANTHROPIC_API_KEY)
# =============================================================
def test_full_agent():
    print("\n" + "=" * 55)
    print("LEVEL 4: Test Full Agent (cần API key)")
    print("=" * 55)

    from config import ANTHROPIC_API_KEY
    if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY == "":
        print("⚠️  Chưa có ANTHROPIC_API_KEY — bỏ qua test này")
        print("   Điền key vào .env để chạy full agent")
        return True   # không fail, chỉ skip

    try:
        from agent.graph import run_agent
        print("Đang chạy Agent (mất 10-30 giây)...")
        result = run_agent(verbose=True)
        print("✅ Full agent chạy thành công")
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
    results.append(("State",          test_state()))
    results.append(("Routing logic",  test_routing_functions()))
    results.append(("Graph build",    test_graph_build()))
    results.append(("Full agent",     test_full_agent()))

    print("\n" + "=" * 55)
    print("  KẾT QUẢ PHASE 3")
    print("=" * 55)
    all_pass = True
    for name, ok in results:
        print(f"  {'✅' if ok else '❌'} {name}")
        if not ok:
            all_pass = False

    if all_pass:
        print("\n🎉 Phase 3 hoàn thành! Agent đã có bộ não.")
        print("   Tiếp theo: Phase 4 — cá nhân hóa danh mục thật.")
    else:
        print("\n⚠️  Xem lỗi ở trên và sửa trước khi tiếp tục.")
