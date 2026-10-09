import os
import sqlite3
import requests
import pandas as pd
import nfl_data_py as nfl
from datetime import datetime
from flask import Flask, render_template_string

app = Flask(__name__)

# ==========================================
# CONFIGURATION & ENVIRONMENT VARIABLES
# ==========================================
# Railway will automatically inject your API key securely from its dashboard
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "82dc7af21b915e1ca03b2b52118f9f13")
SEASON_YEAR = 2026
CURRENT_WEEK = 5
DB_NAME = "bankroll_journal.db"
SHARP_BOOK = "pinnacle"
RETAIL_BOOKS = "draftkings,fanduel,betmgm"
MINIMUM_EDGE_PERCENTAGE = 0.05

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
    conn.commit()
    conn.close()

def log_bet(bet_type, description, staked, payout_multiplier):
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    potential_payout = round(staked * payout_multiplier, 2)
    cursor.execute('''
        INSERT INTO bets (date, bet_type, description, staked, potential_payout)
        VALUES (?, ?, ?, ?, ?)
    ''', (date_str, bet_type, description, staked, potential_payout))
    conn.commit()
    conn.close()

def run_bot_logic():
    init_db()
    url = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "h2h",
        "oddsFormat": "decimal",
        "bookmakers": f"{SHARP_BOOK},{RETAIL_BOOKS}"
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return ["API Error or Invalid Key. Check Railway variables."]
    
    odds_data = response.json()
    value_picks = []

    for game in odds_data:
        home_team = game['home_team']
        away_team = game['away_team']
        books = game.get('bookmakers', [])
        
        sharp_home = 0
        for book in books:
            if book['key'] == SHARP_BOOK:
                for market in book.get('markets', []):
                    for outcome in market.get('outcomes', []):
                        if outcome['name'] == home_team:
                            sharp_home = outcome['price']
                            
        if sharp_home == 0: continue
        true_prob = 1 / sharp_home
        
        # Find best retail price
        best_retail, best_book = 0, None
        for book in books:
            if book['key'] == SHARP_BOOK: continue
            for market in book.get('markets', []):
                if market['key'] == 'h2h':
                    for outcome in market.get('outcomes', []):
                        if outcome['name'] == home_team and outcome['price'] > best_retail:
                            best_retail = outcome['price']
                            best_book = book['title']
                            
        if best_retail > 0:
            retail_prob = 1 / best_retail
            edge = true_prob - retail_prob
            if edge > MINIMUM_EDGE_PERCENTAGE:
                pick_str = f"{home_team} ML @ {best_retail}x on {best_book} (Edge: {round(edge*100, 1)}%)"
                value_picks.append(pick_str)
                log_bet("Straight", f"{home_team} ML", 50.0, best_retail)

    return value_picks if value_picks else ["Scanning markets: No bets currently meeting the 5% edge threshold."]

# ==========================================
# WEB UI DASHBOARD INTERFACE
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>NFL Value Betting Bot</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }
        .container { max-width: 800px; margin: auto; background: #1e293b; padding: 30px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.3); }
        h1 { color: #38bdf8; margin-top: 0; font-size: 24px; }
        .status-badge { display: inline-block; background: #22c55e; color: white; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: bold; margin-bottom: 20px; }
        .card { background: #334155; padding: 15px; border-radius: 8px; margin-bottom: 15px; border-left: 4px solid #38bdf8; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #475569; font-size: 14px; }
        th { color: #38bdf8; }
        .btn { display: inline-block; background: #0ea5e9; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: bold; margin-top: 15px; }
        .btn:hover { background: #0284c7; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🏈 NFL Analytics & Betting Bot</h1>
        <div class="status-badge">ONLINE & MONITORING</div>
        
        <h2>Live Value Bets Found (Week {{ week }})</h2>
        {% for pick in picks %}
            <div class="card"><strong>{{ pick }}</strong></div>
        {% endfor %}

        <h2>Bankroll Ledger History</h2>
        <table>
            <tr><th>Date</th><th>Type</th><th>Description</th><th>Stake</th><th>Payout</th></tr>
            {% for row in history %}
            <tr>
                <td>{{ row[1] }}</td>
                <td>{{ row[2] }}</td>
                <td>{{ row[3] }}</td>
                <td>${{ row[4] }}</td>
                <td>${{ row[5] }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>
</body>
</html>
"""

@app.route("/")
def dashboard():
    init_db()
    picks = run_bot_logic()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bets ORDER BY id DESC LIMIT 10")
    history = cursor.fetchall()
    conn.close()
    
    return render_template_string(HTML_TEMPLATE, picks=picks, history=history, week=CURRENT_WEEK)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)