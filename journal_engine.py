import sqlite3
from datetime import datetime

DB_NAME = "bankroll_journal.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            bet_type TEXT,
            description TEXT,
            staked REAL,
            potential_payout REAL,
            status TEXT DEFAULT 'PENDING',
            profit_loss REAL DEFAULT 0.0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            message TEXT
        )
    ''')
    conn.commit()
    conn.close()

def log_bet(bet_type, description, staked, potential_payout):
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        INSERT INTO bets (date, bet_type, description, staked, potential_payout, status)
        VALUES (?, ?, ?, ?, ?, 'PENDING')
    ''', (date_str, bet_type, description, staked, potential_payout))
    conn.commit()
    conn.close()

def log_system_event(message):
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO bot_logs (timestamp, message) VALUES (?, ?)", (timestamp, message))
    conn.commit()
    conn.close()

def calculate_roi():
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(staked), SUM(profit_loss) FROM bets WHERE status != 'PENDING'")
    res = cursor.fetchone()
    conn.close()
    total_staked = res[0] or 0.0
    total_profit = res[1] or 0.0
    roi = (total_profit / total_staked * 100) if total_staked > 0 else 0.0
    return total_staked, total_profit, round(roi, 2)