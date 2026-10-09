import os
import sqlite3
import requests
from datetime import datetime
from flask import Flask, render_template_string

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
    conn.commit()
    conn.close()

def fetch_live_odds_feed():
    """Pulls live odds, moneylines, and spreads directly from The-Odds-API."""
    url = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "h2h,spreads",
        "oddsFormat": "decimal",
        "bookmakers": "pinnacle,draftkings,fanduel,betmgm"
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    return []

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>THE VEGAS QUANT | Transparent Data Terminal</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-deep: #07090e;
            --bg-card: #111827;
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
        .odds { color: var(--gold-primary); font-weight: 700; }
        pre { background: #030712; padding: 15px; border-radius: 8px; color: #34d399; font-size: 12px; overflow-x: auto; max-height: 300px; border: 1px solid var(--border-color); }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">🎲 VEGAS QUANT <span>BACKEND MONITOR</span></div>
            <div style="color: var(--accent-green); font-size: 13px; font-weight: 700;">● LIVE API CONNECTED</div>
        </div>

        <div class="card">
            <h2>⚡ Live Odds, Spreads & Moneylines (Parsed from API)</h2>
            <table>
                <tr><th>Game Matchup</th><th>Bookmaker</th><th>Away ML</th><th>Home ML</th><th>Away Spread (Point / Odds)</th><th>Home Spread (Point / Odds)</th></tr>
                {% for game in raw_games %}
                    {% for book in game.bookmakers %}
                    <tr>
                        <td><strong>{{ game.away_team }} @ {{ game.home_team }}</strong></td>
                        <td style="color: #60a5fa;">{{ book.title }}</td>
                        {% set ns = namespace(away_ml='N/A', home_ml='N/A', away_spread='N/A', home_spread='N/A') %}
                        {% for market in book.markets %}
                            {% for out in market.outcomes %}
                                {% if market.key == 'h2h' %}
                                    {% if out.name == game.away_team %}{% set ns.away_ml = out.price %}{% endif %}
                                    {% if out.name == game.home_team %}{% set ns.home_ml = out.price %}{% endif %}
                                {% elif market.key == 'spreads' %}
                                    {% if out.name == game.away_team %}{% set ns.away_spread = out.point ~ ' (' ~ out.price ~ 'x)' %}{% endif %}
                                    {% if out.name == game.home_team %}{% set ns.home_spread = out.point ~ ' (' ~ out.price ~ 'x)' %}{% endif %}
                                {% endif %}
                            {% endfor %}
                        {% endfor %}
                        <td class="odds">{{ ns.away_ml }}</td>
                        <td class="odds">{{ ns.home_ml }}</td>
                        <td>{{ ns.away_spread }}</td>
                        <td>{{ ns.home_spread }}</td>
                    </tr>
                    {% endfor %}
                {% endfor %}
            </table>
        </div>

        <div class="card">
            <h2>🔍 Raw JSON Backend API Stream (Verifying Data Flow)</h2>
            <p style="font-size: 12px; color: var(--text-muted);">This is the exact live payload fetched from Vegas servers on every page refresh:</p>
            <pre>{{ raw_json_snippet }}</pre>
        </div>
    </div>
</body>
</html>
"""

@app.route("/")
def dashboard():
    raw_games = fetch_live_odds_feed()
    import json
    raw_json_snippet = json.dumps(raw_games[:2], indent=2) if raw_games else "No active games returned from API."
    return render_template_string(HTML_TEMPLATE, raw_games=raw_games, raw_json_snippet=raw_json_snippet)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)