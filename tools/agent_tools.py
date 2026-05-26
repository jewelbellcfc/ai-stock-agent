# tools/agent_tools.py — Tool điều khiển vòng lặp Agent

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from langchain_core.tools import tool


@tool
def finish_report(report: str) -> str:
    """
    Gọi tool này khi đã hoàn thành toàn bộ phân tích.
    Truyền vào báo cáo đầy đủ để chuyển sang bước kiểm tra chất lượng.

    Báo cáo phải đủ 3 phần:
    - PHẦN 1: Thị trường tổng quan (VN-Index, dòng tiền ngành, khối ngoại)
    - PHẦN 2: Danh mục vs Thị trường (P&L, so sánh, lý giải)
    - PHẦN 3: Khuyến nghị hành động (HOLD / MUA THÊM / CẮT LỖ / CHỐT LỜI)

    Dùng HTML Telegram: <b>đậm</b>, <i>nghiêng</i>, emoji phù hợp.

    Args:
        report: Nội dung báo cáo hoàn chỉnh
    """
    return f"✅ Báo cáo ({len(report)} ký tự) đã chuyển sang bước kiểm tra chất lượng."
