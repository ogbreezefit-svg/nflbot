import os
import sqlite3
import requests
import json
from datetime import datetime
from flask import Flask, render_template_string
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "82dc7af21b915e1ca03b2b52118f9f13")
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

def log_system_event(message):
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO bot_logs (timestamp, message) VALUES (?, ?)", (timestamp, message))
    conn.commit()
    conn.close()

def background_prediction_worker():
    """Runs automatically in the background 24/7 on a schedule."""
    print("[*] Background Worker: Fetching fresh Vegas odds and running predictions...")
    log_system_event("Scheduled background scan initiated.")
    
    url = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "h2h,spreads",
        "oddsFormat": "decimal",
        "bookmakers": "pinnacle,draftkings,fanduel"
    }
    
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            games = response.json()
            log_system_event(f"Successfully pulled fresh data for {len(games)} games.")
            
            # Example automated edge scan & mock logging
            init_db()
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            
            for game in games[:2]: # Log sample automated predictions for active games
                home = game['home_team']
                away = game['away_team']
                desc = f"Automated Scan: {home} vs {away}"
                
                # Check if already logged today
                cursor.execute("SELECT id FROM bets WHERE description = ? AND date LIKE ?", (desc, datetime.now().strftime("%Y-%m-%d") + "%"))
                if not cursor.fetchone():
                    cursor.execute('''
                        INSERT INTO bets (date, bet_type, description, staked, potential_payout, status)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Model Edge Scan", desc, 50.0, 95.0, "COMPLETED"))
                    conn.commit()
            conn.close()
        else:
            log_system_event(f"API Error during background scan: {response.status_code}")
    except Exception as e:
        log_system_event(f"Background worker exception: {str(e)}")

# Initialize and start the Background Scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=background_prediction_worker, trigger="interval", hours=1) # Runs every hour automatically
scheduler.start()

# HTML Template for UI
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>THE VEGAS QUANT | 24/7 Autonomous Backend</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-deep: #07090e;
            --gold-primary: #f59e0b;
            --accent-green: #10b981;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
            --border-color: rgba(255, 255, 255, 0.1);
        }
        body { font-family: 'Plus Jakarta Sans', sans-serif; background: var(--bg-deep); color: var(--text-main); margin: 0; padding: 25px; }
        .container { max-width: 1200px; margin: auto; }
        .header { background: #111827; border: 1px solid var(--border-color); padding: 20px 30px; border-radius: 12px; margin-bottom: 25px; display: flex; justify-content: space-between; align-items: center; }
        .logo { font-size: 20px; font-weight: 800; color: #fff; }
        .logo span { color: var(--gold-primary); }
        .card { background: #111827; border: 1px solid var(--border-color); border-radius: 12px; padding: 25px; margin-bottom: 25px; }
        h2 { color: var(--gold-primary); font-size: 16px; text-transform: uppercase; margin-top: 0; border-bottom: 1px solid var(--border-color); padding-bottom: 10px; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid var(--border-color); font-size: 13px; }
        th { color: var(--text-muted); text-transform: uppercase; font-size: 11px; }
        .log-box { background: #030712; padding: 15px; border-radius: 8px; color: #34d399; font-size: 12px; max-height: 250px; overflow-y: auto; border: 1px solid var(--border-color); }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">🎲 VEGAS QUANT <span>24/7 AUTONOMOUS WORKER</span></div>
            <div style="color: var(--accent-green); font-size: 13px; font-weight: 700;">● SCHEDULER ACTIVE (HOURLY RUNS)</div>
        </div>

        <div class="card">
            <h2>📊 Automated SQLite Bankroll & Model Ledger</h2>
            <table>
                <tr><th>Timestamp</th><th>Type</th><th>Description</th><th>Stake</th><th>Status</th></tr>
                {% for row in history %}
                <tr>
                    <td>{{ row[1] }}</td>
                    <td style="color: var(--gold-primary); font-weight:600;">{{ row[2] }}</td>
                    <td>{{ row[3] }}</td>
                    <td>${{ row[4] }}</td>
                    <td style="color: var(--accent-green);">{{ row[6] }}</td>
                </tr>
                {% endfor %}
            </table>
        </div>

        <div class="card">
            <h2>⚙️ Background Job Execution Logs</h2>
            <div class="log-box">
                {% for log in logs %}
                    <div>[{{ log[1] }}] {{ log[2] }}</div>
                {% endfor %}
            </div>
        </div>
    </div>
</body>
</html>
"""

@app.route("/")
def dashboard():
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bets ORDER BY id DESC LIMIT 10")
    history = cursor.fetchall()
    
    cursor.execute("SELECT * FROM bot_logs ORDER BY id DESC LIMIT 15")
    logs = cursor.fetchall()
    conn.close()
    
    return render_template_string(HTML_TEMPLATE, history=history, logs=logs)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)