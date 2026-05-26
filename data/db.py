# data/db.py — SQLite: lưu và đọc dữ liệu thị trường + danh mục

import os
import sys
import sqlite3
import pandas as pd
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import DB_PATH



def init_db():
    """Tạo file database và các bảng nếu chưa có."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS price_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker      TEXT    NOT NULL,
                trade_date  TEXT    NOT NULL,
                open        REAL,
                high        REAL,
                low         REAL,
                close       REAL,
                volume      INTEGER,
                created_at  TEXT    DEFAULT (datetime('now', 'localtime')),
                UNIQUE(ticker, trade_date)
            );

            CREATE TABLE IF NOT EXISTS sector_flow (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date        TEXT NOT NULL,
                sector            TEXT NOT NULL,
                total_value_bil   REAL,
                avg_change_pct    REAL,
                advance_count     INTEGER,
                decline_count     INTEGER,
                money_flow_score  REAL,
                created_at        TEXT DEFAULT (datetime('now', 'localtime')),
                UNIQUE(trade_date, sector)
            );

            CREATE TABLE IF NOT EXISTS portfolio_snapshot (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT NOT NULL,
                ticker      TEXT NOT NULL,
                quantity    INTEGER,
                avg_cost    REAL,
                note        TEXT,
                created_at  TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS report_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date TEXT NOT NULL,
                report_type TEXT,
                content     TEXT,
                sent_ok     INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now', 'localtime'))
            );
        """)
        print(f"[db] Database khởi tạo xong: {DB_PATH}")



def save_price_history(df: pd.DataFrame):
    """
    Lưu DataFrame lịch sử giá vào bảng price_history.
    Bỏ qua các dòng đã tồn tại (UNIQUE constraint).
    """
    if df.empty:
        print("[db] DataFrame rỗng, không lưu gì cả")
        return

    # Chuẩn hóa tên cột
    df = df.rename(columns={"time": "trade_date"})
    cols = ["ticker", "trade_date", "open", "high", "low", "close", "volume"]
    df_save = df[[c for c in cols if c in df.columns]].copy()

    with sqlite3.connect(DB_PATH) as conn:
        col_names    = ", ".join(df_save.columns)
        placeholders = ", ".join(["?"] * len(df_save.columns))
        conn.executemany(
            f"INSERT OR IGNORE INTO price_history ({col_names}) VALUES ({placeholders})",
            df_save.itertuples(index=False, name=None)
        )
    print(f"[db] Đã lưu {len(df_save)} dòng vào price_history")


def save_sector_flow(df: pd.DataFrame, trade_date: str = None):
    """
    Lưu dòng tiền ngành vào bảng sector_flow.
    trade_date: YYYY-MM-DD, mặc định là hôm nay
    """
    if df.empty:
        return

    if trade_date is None:
        trade_date = datetime.today().strftime("%Y-%m-%d")

    df_save = df.copy()
    df_save["trade_date"] = trade_date

    with sqlite3.connect(DB_PATH) as conn:
        col_names    = ", ".join(df_save.columns)
        placeholders = ", ".join(["?"] * len(df_save.columns))
        conn.executemany(
            f"INSERT OR IGNORE INTO sector_flow ({col_names}) VALUES ({placeholders})",
            df_save.itertuples(index=False, name=None)
        )
    print(f"[db] Đã lưu sector_flow ngày {trade_date}")


def save_portfolio_snapshot(portfolio: list, snapshot_date: str = None):
    """
    Lưu snapshot danh mục.

    portfolio: list of dict, ví dụ:
        [
            {"ticker": "VCB",  "quantity": 1000, "avg_cost": 85000},
            {"ticker": "HPG",  "quantity": 2000, "avg_cost": 26000},
        ]
    """
    if not portfolio:
        return

    if snapshot_date is None:
        snapshot_date = datetime.today().strftime("%Y-%m-%d")

    df_save = pd.DataFrame(portfolio)
    df_save["snapshot_date"] = snapshot_date

    with sqlite3.connect(DB_PATH) as conn:
        df_save.to_sql("portfolio_snapshot", conn,
                       if_exists="append", index=False)
    print(f"[db] Đã lưu {len(portfolio)} vị thế vào portfolio_snapshot")



def get_latest_sector_flow() -> pd.DataFrame:
    """Lấy dòng tiền ngành của ngày gần nhất trong DB."""
    with sqlite3.connect(DB_PATH) as conn:
        query = """
            SELECT * FROM sector_flow
            WHERE trade_date = (SELECT MAX(trade_date) FROM sector_flow)
            ORDER BY money_flow_score DESC
        """
        return pd.read_sql(query, conn)


def get_price_history_from_db(ticker: str, days: int = 30) -> pd.DataFrame:
    """Đọc lịch sử giá của một mã từ DB."""
    with sqlite3.connect(DB_PATH) as conn:
        query = """
            SELECT * FROM price_history
            WHERE ticker = ?
            ORDER BY trade_date DESC
            LIMIT ?
        """
        return pd.read_sql(query, conn, params=(ticker, days))


def get_latest_portfolio() -> pd.DataFrame:
    """Lấy snapshot danh mục gần nhất."""
    with sqlite3.connect(DB_PATH) as conn:
        query = """
            SELECT * FROM portfolio_snapshot
            WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM portfolio_snapshot)
        """
        return pd.read_sql(query, conn)


def log_report(report_type: str, content: str, sent_ok: bool = False):
    """Ghi log báo cáo đã gửi."""
    today = datetime.today().strftime("%Y-%m-%d")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO report_log (report_date, report_type, content, sent_ok) VALUES (?,?,?,?)",
            (today, report_type, content, 1 if sent_ok else 0)
        )


def get_recent_reports(days: int = 3, report_type: str = None) -> list:
    """Đọc báo cáo gần nhất từ report_log để dùng làm memory cho Agent."""
    with sqlite3.connect(DB_PATH) as conn:
        if report_type:
            rows = conn.execute(
                """SELECT report_date, report_type, content, sent_ok
                   FROM report_log
                   WHERE report_type = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (report_type, days),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT report_date, report_type, content, sent_ok
                   FROM report_log
                   ORDER BY created_at DESC LIMIT ?""",
                (days,),
            ).fetchall()
    return [
        {
            "date":    r[0],
            "type":    r[1],
            "content": (r[2] or "")[:500],
            "sent_ok": bool(r[3]),
        }
        for r in rows
    ]
