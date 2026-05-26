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

# --- MBS API ---
MBS_CLIENT_ID     = os.getenv("MBS_CLIENT_ID", "")
MBS_CLIENT_SECRET = os.getenv("MBS_CLIENT_SECRET", "")
MBS_ACCOUNT_NO    = os.getenv("MBS_ACCOUNT_NO", "")
MBS_USERNAME      = os.getenv("MBS_USERNAME", "")

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

# --- MBS API ---
MBS_TOKEN          = os.getenv("MBS_TOKEN", "")
MBS_MASTER_ACCOUNT = os.getenv("MBS_MASTER_ACCOUNT", "777845")
MBS_ACCOUNT        = os.getenv("MBS_ACCOUNT", "7778458")

