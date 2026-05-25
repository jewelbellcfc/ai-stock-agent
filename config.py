# config.py
# -------------------------------------------------------------
# File cấu hình trung tâm — chỉnh sửa các giá trị này trước khi chạy
# -------------------------------------------------------------
import os
from dotenv import load_dotenv

# Tìm file .env đúng vị trí dù chạy từ đâu
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")   # đọc từ .env
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")     # đọc từ .env
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")    # đọc từ .env  # https://console.anthropic.com
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")       # đọc từ .env
# OPENAI_API_KEY  = "YOUR_OPENAI_KEY_HERE"       # nếu dùng GPT

# --- Dữ liệu ---
# Danh sách ngành muốn theo dõi (icb_code của HOSE)
SECTORS_TO_TRACK = [
    "Ngân hàng",
    "Bất động sản",
    "Chứng khoán",
    "Thép",
    "Dầu khí",
    "Công nghệ thông tin",
    "Bán lẻ",
    "Xây dựng",
]

# Top N mã mỗi ngành để lấy dữ liệu
TOP_STOCKS_PER_SECTOR = 5

# Số ngày lịch sử lấy khi khởi tạo DB lần đầu
HISTORY_DAYS = 30

# --- Database ---
DB_PATH = "data/stock_data.db"
