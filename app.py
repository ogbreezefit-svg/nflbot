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
MAX_PARLAY_STAKE = 50.0

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
    url = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/scores"
    params = {"apiKey": ODDS_API_KEY, "daysFrom": 3}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    return []

def run_bot_intelligence():
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
        return [], []
    
    odds_data = response.json()
    straight_picks = []
    parlay_legs = []

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
                edge_pct = round(edge * 100, 1)
                pick_data = {
                    "matchup": f"{away_team} @ {home_team}",
                    "pick": f"{home_team} Moneyline",
                    "odds": best_retail,
                    "book": best_book,
                    "edge": edge_pct
                }
                straight_picks.append(pick_data)
                parlay_legs.append(pick_data)
                log_bet("Straight Edge", f"{home_team} ML", 50.0, best_retail)

    # Build 10x Target Parlay if we have enough legs
    parlay_ticket = None
    if len(parlay_legs) >= 2:
        combined_mult = 1.0
        leg_descriptions = []
        for leg in parlay_legs[:3]: # Take top 3 legs
            combined_mult *= leg['odds']
            leg_descriptions.append(f"{leg['pick']} ({leg['odds']}x)")
        
        if combined_mult >= 8.0: # Targeting close to 10x
            parlay_ticket = {
                "legs": leg_descriptions,
                "multiplier": round(combined_mult, 2),
                "potential_payout": round(MAX_PARLAY_STAKE * combined_mult, 2)
            }
            log_bet("10x Parlay Target", " | ".join(leg_descriptions), MAX_PARLAY_STAKE, combined_mult)

    return straight_picks, parlay_ticket

# ==========================================
# VEGAS LUXURY WEB UI DASHBOARD
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>THE VEGAS QUANT | NFL Elite Betting Terminal</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-deep: #07090e;
            --bg-card: #111827;
            --bg-glass: rgba(17, 24, 39, 0.75);
            --gold-primary: #f59e0b;
            --gold-glow: rgba(245, 158, 11, 0.25);
            --accent-green: #10b981;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
            --border-color: rgba(255, 255, 255, 0.08);
        }
        body { font-family: 'Plus Jakarta Sans', sans-serif; background: var(--bg-deep); color: var(--text-main); margin: 0; padding: 25px; background-image: radial-gradient(circle at 50% 0%, #1e1b4b 0%, var(--bg-deep) 60%); min-height: 100vh; }
        .container { max-width: 1100px; margin: auto; }
        
        /* Header Banner */
        .header { display: flex; justify-content: space-between; align-items: center; background: var(--bg-glass); backdrop-filter: blur(12px); border: 1px solid var(--border-color); padding: 20px 30px; border-radius: 16px; margin-bottom: 25px; box-shadow: 0 15px 35px rgba(0,0,0,0.5); }
        .logo { font-size: 22px; font-weight: 800; letter-spacing: 1px; color: #fff; display: flex; align-items: center; gap: 10px; }
        .logo span { color: var(--gold-primary); text-shadow: 0 0 15px var(--gold-glow); }
        .live-badge { display: flex; align-items: center; gap: 8px; background: rgba(16, 185, 129, 0.15); color: var(--accent-green); padding: 6px 14px; border-radius: 30px; font-size: 12px; font-weight: 700; border: 1px solid rgba(16, 185, 129, 0.3); }
        .pulse { width: 8px; height: 8px; background: var(--accent-green); border-radius: 50%; box-shadow: 0 0 10px var(--accent-green); animation: pulse 2s infinite; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }

        /* Grid Layout */
        .grid-section { display: grid; grid-template-columns: 1fr 1fr; gap: 25px; margin-bottom: 25px; }
        @media (max-width: 850px) { .grid-section { grid-template-columns: 1fr; } }
        
        .card-box { background: var(--bg-glass); backdrop-filter: blur(12px); border: 1px solid var(--border-color); border-radius: 16px; padding: 25px; box-shadow: 0 10px 25px rgba(0,0,0,0.3); }
        h2 { font-size: 16px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: var(--gold-primary); margin-top: 0; margin-bottom: 20px; display: flex; align-items: center; gap: 8px; }

        /* Bets & Tickets */
        .pick-card { background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border-color); border-radius: 10px; padding: 15px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; transition: all 0.3s ease; }
        .pick-card:hover { border-color: var(--gold-primary); transform: translateY(-2px); }
        .pick-title { font-weight: 700; font-size: 15px; color: #fff; }
        .pick-meta { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
        .edge-tag { background: rgba(245, 158, 11, 0.15); color: var(--gold-primary); padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 12px; border: 1px solid rgba(245, 158, 11, 0.3); }

        /* Parlay Banner */
        .parlay-box { background: linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(17, 24, 39, 0.9) 100%); border: 1px solid rgba(245, 158, 11, 0.4); border-radius: 16px; padding: 25px; margin-bottom: 25px; }
        .parlay-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        .parlay-multiplier { font-size: 24px; font-weight: 800; color: var(--gold-primary); text-shadow: 0 0 20px var(--gold-glow); }

        /* Schedule & Scores Grid */
        .schedule-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 15px; }
        .game-card { background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); border-radius: 10px; padding: 15px; }
        .game-teams { font-weight: 700; font-size: 14px; margin-bottom: 6px; }
        .score-display { color: var(--gold-primary); font-weight: 700; font-size: 16px; margin-top: 8px; }

        /* Ledger Table */
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 14px; text-align: left; border-bottom: 1px solid var(--border-color); font-size: 13px; }
        th { color: var(--text-muted); font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; }
        td { color: #e5e7eb; }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <div class="logo">🎲 THE VEGAS <span>QUANT</span></div>
            <div class="live-badge"><div class="pulse"></div>SYSTEM ONLINE & SCANNING</div>
        </div>

        <!-- Top Row: Straight Edges & Parlay Generator -->
        <div class="grid-section">
            <div class="card-box">
                <h2>⚡ High-Edge Straight Bets (5%+)</h2>
                {% if straight_picks %}
                    {% for p in straight_picks %}
                        <div class="pick-card">
                            <div>
                                <div class="pick-title">{{ p.pick }}</div>
                                <div class="pick-meta">{{ p.matchup }} &bull; {{ p.book }} @ {{ p.odds }}x</div>
                            </div>
                            <div class="edge-tag">+{{ p.edge }}% Edge</div>
                        </div>
                    {% endfor %}
                {% else %}
                    <div style="color: var(--text-muted); font-size: 14px; padding: 10px 0;">Scanning market lines for optimal mathematical edge...</div>
                {% endif %}
            </div>

            <div class="card-box">
                <h2>🎯 Automated 10x Target Parlay</h2>
                {% if parlay_ticket %}
                    <div class="parlay-box" style="margin-bottom:0; padding:15px;">
                        <div class="parlay-header">
                            <span style="font-weight:700;">Multi-Leg Value Parlay</span>
                            <span class="parlay-multiplier">{{ parlay_ticket.multiplier }}x Payout</span>
                        </div>
                        <ul style="margin: 0; padding-left: 18px; font-size: 13px; color: var(--text-muted);">
                            {% for leg in parlay_ticket.legs %}
                                <li style="margin-bottom: 4px; color: #fff;">{{ leg }}</li>
                            {% endfor %}
                        </ul>
                        <div style="margin-top: 12px; font-size: 12px; color: var(--gold-primary); font-weight: 600;">
                            Target Stake: $50.00 &bull; Potential Return: ${{ parlay_ticket.potential_payout }}
                        </div>
                    </div>
                {% else %}
                    <div style="color: var(--text-muted); font-size: 14px; padding: 10px 0;">Awaiting multiple qualifying value legs to construct parlay ticket...</div>
                {% endif %}
            </div>
        </div>

        <!-- Schedule & Scores Section -->
        <div class="card-box" style="margin-bottom: 25px;">
            <h2>📅 Live Schedule & Scores</h2>
            <div class="schedule-grid">
                {% for game in schedule %}
                    <div class="game-card">
                        <div class="game-teams">{{ game.away_team }} @ {{ game.home_team }}</div>
                        <div style="font-size: 11px; color: var(--text-muted);">
                            {% if game.completed %}Status: Final{% else %}Status: Live / Upcoming{% endif %}
                        </div>
                        {% if game.scores %}
                            <div class="score-display">{{ game.scores[0].name }}: {{ game.scores[0].score }} | {{ game.scores[1].name }}: {{ game.scores[1].score }}</div>
                        {% else %}
                            <div style="font-size: 12px; color: #64748b; margin-top: 6px;">Commence: {{ game.commence_time[:16].replace('T', ' ') }} UTC</div>
                        {% endif %}
                    </div>
                {% endfor %}
            </div>
        </div>

        <!-- Bankroll Ledger -->
        <div class="card-box">
            <h2>📊 Bankroll Ledger History</h2>
            <table>
                <tr><th>Timestamp</th><th>Type</th><th>Description</th><th>Stake</th><th>Potential Payout</th><th>Status</th></tr>
                {% for row in history %}
                <tr>
                    <td>{{ row[1] }}</td>
                    <td><span style="color: var(--gold-primary); font-weight:600;">{{ row[2] }}</span></td>
                    <td>{{ row[3] }}</td>
                    <td>${{ row[4] }}</td>
                    <td>${{ row[5] }}</td>
                    <td><span style="color: var(--accent-green);">{{ row[6] }}</span></td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </div>
</body>
</html>
"""

@app.route("/")
def dashboard():
    init_db()
    straight_picks, parlay_ticket = run_bot_intelligence()
    schedule = fetch_live_scores_and_schedule()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bets ORDER BY id DESC LIMIT 12")
    history = cursor.fetchall()
    conn.close()
    
    return render_template_string(HTML_TEMPLATE, straight_picks=straight_picks, parlay_ticket=parlay_ticket, schedule=schedule, history=history)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)