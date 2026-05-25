# VN Stock Agent — Cấu trúc dự án

```
vn-stock-agent/
│
├── README.md
├── requirements.txt
├── config.py                  # Cấu hình: token, API key, danh sách mã
│
├── data/
│   ├── fetcher.py             # Phase 1: Lấy dữ liệu từ vnstock
│   ├── db.py                  # Phase 1: Lưu/đọc SQLite
│   └── stock_data.db          # Tự tạo khi chạy lần đầu
│
├── tools/
│   ├── sector_flow.py         # Phase 2: Tính dòng tiền ngành
│   ├── indicators.py          # Phase 2: RSI, MA đơn giản
│   ├── portfolio_analyzer.py  # Phase 4: Phân tích danh mục
│   └── telegram_sender.py     # Phase 2: Gửi Telegram
│
├── agent/
│   ├── state.py               # Phase 3: Định nghĩa State của LangGraph
│   ├── nodes.py               # Phase 3: Các node (analyst, portfolio, reporter)
│   └── graph.py               # Phase 3: Kết nối các node thành graph
│
├── portfolio/
│   └── my_portfolio.json      # Danh mục của bạn (tự cập nhật hàng ngày)
│
└── main.py                    # Điểm khởi động toàn bộ agent
```

## Thứ tự học
- Phase 1: `data/fetcher.py` → `data/db.py`
- Phase 2: `tools/` các file
- Phase 3: `agent/` các file
- Phase 4: `portfolio/` + `tools/portfolio_analyzer.py`
- Phase 5: `main.py` + schedule
