import os
import sqlite3
import requests
from datetime import datetime
from flask import Flask, render_template_string
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# ==========================================
# CONFIGURATION & ENVIRONMENT VARIABLES
# ==========================================
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "82dc7af21b915e1ca03b2b52118f9f13")
DB_NAME = "bankroll_journal.db"
SHARP_BOOK = "pinnacle"
RETAIL_BOOKS = "draftkings,fanduel,betmgm"
MINIMUM_EDGE_PERCENTAGE = 0.04

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
    """Autonomous 24/7 background worker scanning odds and logging automated model edges."""
    log_system_event("Autonomous background scanner initiated.")
    url = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "h2h,spreads",
        "oddsFormat": "decimal",
        "bookmakers": f"{SHARP_BOOK},{RETAIL_BOOKS}"
    }
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            games = response.json()
            log_system_event(f"Successfully fetched {len(games)} live games from Vegas API.")
            
            # Autonomous Mock Bet & Edge Evaluation Engine
            init_db()
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            
            for game in games[:3]:
                home = game.get('home_team', 'Home')
                away = game.get('away_team', 'Away')
                books = game.get('bookmakers', [])
                
                # Look for Pinnacle sharp price vs retail
                sharp_price = 0.0
                retail_price = 0.0
                best_book_name = "DraftKings"
                
                for book in books:
                    if book.get('key') == SHARP_BOOK:
                        for market in book.get('markets', []):
                            if market.get('key') == 'h2h':
                                for outcome in market.get('outcomes', []):
                                    if outcome.get('name') == home:
                                        sharp_price = outcome.get('price', 0.0)
                    elif book.get('key') in ['draftkings', 'fanduel']:
                        for market in book.get('markets', []):
                            if market.get('key') == 'h2h':
                                for outcome in market.get('outcomes', []):
                                    if outcome.get('name') == home and outcome.get('price', 0.0) > retail_price:
                                        retail_price = outcome.get('price', 0.0)
                                        best_book_name = book.get('title', 'Retail Book')

                if sharp_price > 0 and retail_price > 0:
                    true_prob = 1 / sharp_price
                    retail_prob = 1 / retail_price
                    edge = true_prob - retail_prob
                    
                    if edge >= MINIMUM_EDGE_PERCENTAGE:
                        desc = f"Model Edge: {home} ML @ {retail_price}x on {best_book_name} (Edge: {round(edge*100, 1)}%)"
                        cursor.execute("SELECT id FROM bets WHERE description = ? AND date LIKE ?", (desc, datetime.now().strftime("%Y-%m-%d") + "%"))
                        if not cursor.fetchone():
                            cursor.execute('''
                                INSERT INTO bets (date, bet_type, description, staked, potential_payout, status)
                                VALUES (?, ?, ?, ?, ?, ?)
                            ''', (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Quant Edge Pick", desc, 50.0, round(50.0 * retail_price, 2), "PENDING"))
                            conn.commit()
                            log_system_event(f"Logged automated value bet: {desc}")
            conn.close()
        else:
            log_system_event(f"API Error during background sync: Status {response.status_code}")
    except Exception as e:
        log_system_event(f"Background worker exception: {str(e)}")

# Initialize and start background cron scheduler (Runs every hour automatically)
scheduler = BackgroundScheduler()
scheduler.add_job(func=background_prediction_worker, trigger="interval", hours=1)
scheduler.start()

def fetch_structured_games():
    """Fetches live odds and market data for rendering unified UI cards."""
    url = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "h2h,spreads",
        "oddsFormat": "decimal",
        "bookmakers": "pinnacle,draftkings,fanduel,betmgm"
    }
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return []

# ==========================================
# FULL VEGAS LUXURY UI TEMPLATE (HTML/CSS)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>THE VEGAS QUANT | Autonomous NFL Betting Terminal</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-deep: #07090e;
            --bg-card: #111827;
            --bg-glass: rgba(17, 24, 39, 0.85);
            --gold-primary: #f59e0b;
            --gold-glow: rgba(245, 158, 11, 0.2);
            --accent-green: #10b981;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
            --border-color: rgba(255, 255, 255, 0.08);
        }
        body { font-family: 'Plus Jakarta Sans', sans-serif; background: var(--bg-deep); color: var(--text-main); margin: 0; padding: 25px; background-image: radial-gradient(circle at 50% 0%, #1e1b4b 0%, var(--bg-deep) 70%); min-height: 100vh; }
        .container { max-width: 1200px; margin: auto; }
        
        .header { display: flex; justify-content: space-between; align-items: center; background: var(--bg-glass); backdrop-filter: blur(12px); border: 1px solid var(--border-color); padding: 20px 30px; border-radius: 16px; margin-bottom: 25px; box-shadow: 0 15px 35px rgba(0,0,0,0.5); }
        .logo { font-size: 22px; font-weight: 800; letter-spacing: 1px; color: #fff; display: flex; align-items: center; gap: 10px; }
        .logo span { color: var(--gold-primary); text-shadow: 0 0 15px var(--gold-glow); }
        .live-badge { display: flex; align-items: center; gap: 8px; background: rgba(16, 185, 129, 0.15); color: var(--accent-green); padding: 6px 14px; border-radius: 30px; font-size: 12px; font-weight: 700; border: 1px solid rgba(16, 185, 129, 0.3); }
        .pulse { width: 8px; height: 8px; background: var(--accent-green); border-radius: 50%; box-shadow: 0 0 10px var(--accent-green); animation: pulse 2s infinite; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }

        h2 { font-size: 16px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: var(--gold-primary); margin-top: 0; margin-bottom: 20px; display: flex; align-items: center; gap: 8px; }

        .games-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .game-card { background: var(--bg-glass); backdrop-filter: blur(12px); border: 1px solid var(--border-color); border-radius: 16px; padding: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.3); position: relative; overflow: hidden; }
        .game-card::before { content: ''; position: absolute; top: 0; left: 0; width: 4px; height: 100%; background: var(--gold-primary); }
        
        .game-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; border-bottom: 1px solid var(--border-color); padding-bottom: 10px; }
        .matchup-title { font-size: 15px; font-weight: 800; color: #fff; }
        .kickoff { font-size: 11px; color: var(--text-muted); }

        .market-section { margin-bottom: 10px; background: rgba(0,0,0,0.25); border-radius: 10px; padding: 10px 12px; border: 1px solid rgba(255,255,255,0.04); }
        .book-title { font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--gold-primary); margin-bottom: 6px; letter-spacing: 0.5px; }
        .odds-row { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 4px; }
        .odds-val { color: #38bdf8; font-weight: 700; }
        
        .card-box { background: var(--bg-glass); backdrop-filter: blur(12px); border: 1px solid var(--border-color); border-radius: 16px; padding: 25px; margin-bottom: 25px; box-shadow: 0 10px 25px rgba(0,0,0,0.3); }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid var(--border-color); font-size: 13px; }
        th { color: var(--text-muted); font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; }
        td { color: #e5e7eb; }
        .log-box { background: #030712; padding: 15px; border-radius: 8px; color: #34d399; font-size: 12px; max-height: 200px; overflow-y: auto; border: 1px solid var(--border-color); }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header Banner -->
        <div class="header">
            <div class="logo">🎲 THE VEGAS <span>QUANT TERMINAL</span></div>
            <div class="live-badge"><div class="pulse"></div>24/7 AUTONOMOUS WORKER ACTIVE</div>
        </div>

        <!-- Unified Matchup Cards Grid -->
        <h2>🏈 Live Matchup Odds & Casino Markets</h2>
        <div class="games-grid">
            {% if games %}
                {% for game in games %}
                <div class="game-card">
                    <div class="game-header">
                        <div class="matchup-title">{{ game.away_team }} @ {{ game.home_team }}</div>
                        <div class="kickoff">{{ game.commence_time[:16].replace('T', ' ') }} UTC</div>
                    </div>

                    {% if game.bookmakers %}
                        {% for book in game.bookmakers %}
                        <div class="market-section">
                            <div class="book-title">{{ book.title }}</div>
                            
                            {% set away_ml = namespace(val='N/A') %}
                            {% set home_ml = namespace(val='N/A') %}
                            {% set away_spread = namespace(val='N/A') %}
                            {% set home_spread = namespace(val='N/A') %}

                            {% if book.markets %}
                                {% for m in book.markets %}
                                    {% if m.outcomes %}
                                        {% for o in m.outcomes %}
                                            {% if m.key == 'h2h' %}
                                                {% if o.name == game.away_team %}{% set away_ml.val = o.price|string + 'x' %}{% endif %}
                                                {% if o.name == game.home_team %}{% set home_ml.val = o.price|string + 'x' %}{% endif %}
                                            {% elif m.key == 'spreads' %}
                                                {% if o.name == game.away_team %}{% set away_spread.val = (o.point|string) + ' (' + (o.price|string) + 'x)' %}{% endif %}
                                                {% if o.name == game.home_team %}{% set home_spread.val = (o.point|string) + ' (' + (o.price|string) + 'x)' %}{% endif %}
                                            {% endif %}
                                        {% endfor %}
                                    {% endif %}
                                {% endfor %}
                            {% endif %}

                            <div class="odds-row">
                                <span>{{ game.away_team }}</span>
                                <div>ML: <span class="odds-val">{{ away_ml.val }}</span> | Spread: <span class="odds-val">{{ away_spread.val }}</span></div>
                            </div>
                            <div class="odds-row">
                                <span>{{ game.home_team }}</span>
                                <div>ML: <span class="odds-val">{{ home_ml.val }}</span> | Spread: <span class="odds-val">{{ home_spread.val }}</span></div>
                            </div>
                        </div>
                        {% endfor %}
                    {% else %}
                        <div style="color: var(--text-muted); font-size: 13px;">No bookmaker odds available currently.</div>
                    {% endif %}
                </div>
                {% endfor %}
            {% else %}
                <div class="card-box" style="grid-column: 1 / -1; text-align: center; color: var(--text-muted);">
                    Awaiting live game feed from API... Check API key or active game schedules.
                </div>
            {% endif %}
        </div>

        <!-- Bankroll Ledger Section -->
        <div class="card-box">
            <h2>📊 Autonomous Quant Model Ledger & Bankroll Journal</h2>
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

        <!-- Background Execution Logs Section -->
        <div class="card-box">
            <h2>⚙️ 24/7 Background Scheduler & Worker Logs</h2>
            <div class="log-box">
                {% for log in logs %}
                    <div>[{{ log[1] ]] {{ log[2] }}</div>
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
    games = fetch_structured_games()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bets ORDER BY id DESC LIMIT 15")
    history = cursor.fetchall()
    
    cursor.execute("SELECT * FROM bot_logs ORDER BY id DESC LIMIT 15")
    logs = cursor.fetchall()
    conn.close()
    
    return render_template_string(HTML_TEMPLATE, games=games, history=history, logs=logs)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)