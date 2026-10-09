import os
import sqlite3
import requests
from datetime import datetime
from flask import Flask, render_template_string

app = Flask(__name__)

# ==========================================
# CONFIGURATION & ENVIRONMENT VARIABLES
# ==========================================
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "82dc7af21b915e1ca03b2b52118f9f13")
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
    
    # Prevent duplicate identical pending logs for the same bet description on the same day
    cursor.execute('''
        SELECT id FROM bets WHERE description = ? AND date LIKE ?
    ''', (description, datetime.now().strftime("%Y-%m-%d") + "%"))
    if not cursor.fetchone():
        cursor.execute('''
            INSERT INTO bets (date, bet_type, description, staked, potential_payout)
            VALUES (?, ?, ?, ?, ?)
        ''', (date_str, bet_type, description, staked, potential_payout))
        conn.commit()
    conn.close()

def fetch_live_scores_and_schedule():
    """Pulls current week NFL schedule, game statuses, and live scores."""
    url = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/scores"
    params = {"apiKey": ODDS_API_KEY, "daysFrom": 3}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    return []

def run_bot_intelligence():
    """Runs sharp vs retail odds comparison and logs high-edge bets."""
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
        return ["API Error: Unable to fetch live odds. Check API Key."]
    
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
            if edge >= MINIMUM_EDGE_PERCENTAGE:
                pick_str = f"{home_team} ML @ {best_retail}x on {best_book} (Edge: {round(edge*100, 1)}% vs Pinnacle)"
                value_picks.append(pick_str)
                log_bet("Straight Edge", f"{home_team} ML", 50.0, best_retail)

    return value_picks if value_picks else ["No games currently meeting the strict 5% mathematical edge threshold."]

# ==========================================
# WEB UI DASHBOARD INTERFACE
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>NFL Betting Analytics & Live Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }
        .container { max-width: 900px; margin: auto; background: #1e293b; padding: 30px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.4); }
        h1 { color: #38bdf8; margin-top: 0; font-size: 26px; display: flex; justify-content: space-between; align-items: center; }
        .status-badge { background: #22c55e; color: white; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; }
        h2 { color: #38bdf8; border-bottom: 2px solid #334155; padding-bottom: 8px; margin-top: 30px; font-size: 18px; }
        .card { background: #334155; padding: 15px; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid #38bdf8; font-size: 15px; }
        .game-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 15px; margin-top: 15px; }
        .game-card { background: #0f172a; padding: 15px; border-radius: 8px; border: 1px solid #475569; }
        .game-teams { font-weight: bold; margin-bottom: 8px; color: #cbd5e1; }
        .score { color: #38bdf8; font-size: 18px; font-weight: bold; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #475569; font-size: 14px; }
        th { color: #38bdf8; }
    </style>
</head>
<body>
    <div class="container">
        <h1>
            🏈 NFL Quant Bot
            <span class="status-badge">LIVE & MONITORING</span>
        </h1>
        
        <h2>🎯 High-Value Mathematical Edges (5%+ Target)</h2>
        {% for pick in picks %}
            <div class="card"><strong>{{ pick }}</strong></div>
        {% endfor %}

        <h2>📅 This Week's Schedule & Live Scores</h2>
        <div class="game-grid">
            {% for game in schedule %}
                <div class="game-card">
                    <div class="game-teams">{{ game.away_team }} @ {{ game.home_team }}</div>
                    <div style="font-size: 12px; color: #94a3b8; margin-bottom: 5px;">Status: {% if game.completed %}Final{% else %}Upcoming / Live{% endif %}</div>
                    {% if game.scores %}
                        <div class="score">{{ game.scores[0].name }}: {{ game.scores[0].score }} | {{ game.scores[1].name }}: {{ game.scores[1].score }}</div>
                    {% else %}
                        <div style="color: #64748b; font-size: 13px;">Commences: {{ game.commence_time[:16].replace('T', ' ') }} UTC</div>
                    {% endif %}
                </div>
            {% endfor %}
        </div>

        <h2>📊 Bankroll Ledger History</h2>
        <table>
            <tr><th>Timestamp</th><th>Type</th><th>Description</th><th>Stake</th><th>Potential Payout</th></tr>
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
    picks = run_bot_intelligence()
    schedule = fetch_live_scores_and_schedule()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bets ORDER BY id DESC LIMIT 15")
    history = cursor.fetchall()
    conn.close()
    
    return render_template_string(HTML_TEMPLATE, picks=picks, schedule=schedule, history=history)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)