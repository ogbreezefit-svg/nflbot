import os
from datetime import datetime, timezone
from flask import Flask, render_template_string
from dotenv import load_dotenv

# 1. Import scheduler and ingestion
from apscheduler.schedulers.background import BackgroundScheduler
import ingestion

# 2. Initialize Flask App
load_dotenv()
app = Flask(__name__)

# 3. Initialize Database safely
try:
    from db import SessionLocal, PickLog, engine, Base
    Base.metadata.create_all(bind=engine)
    DB_AVAILABLE = True
except Exception as e:
    print(f"Database initialization warning: {e}")
    DB_AVAILABLE = False

# 4. Start Background Scheduler
try:
    scheduler = BackgroundScheduler()
    ingestion.fetch_and_store_live_data()
    scheduler.add_job(func=ingestion.fetch_and_store_live_data, trigger="interval", minutes=60)
    scheduler.start()
    print("Background ingestion scheduler started.")
except Exception as e:
    print(f"Failed to start scheduler: {e}")

# 5. HTML Template (Now entirely dynamic for parlays)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Ogbreeze Command Center</title>
    <meta http-equiv="refresh" content="30">
    <style>
        body { background-color: #0d1117; color: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 20px; }
        h1 { color: #58a6ff; text-align: center; font-size: 24px; border-bottom: 1px solid #30363d; padding-bottom: 15px; }
        .grid { display: flex; justify-content: space-around; background: #161b22; padding: 15px; border-radius: 8px; border: 1px solid #30363d; margin-bottom: 20px; }
        .metric { text-align: center; }
        .metric span { display: block; font-size: 20px; font-weight: bold; color: #f0f6fc; margin-top: 5px; }
        .section-title { color: #58a6ff; font-size: 18px; margin-top: 30px; margin-bottom: 15px; border-bottom: 1px solid #30363d; padding-bottom: 5px; }
        .parlay-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px; margin-bottom: 25px; }
        .parlay-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 15px; }
        .parlay-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #30363d; padding-bottom: 8px; margin-bottom: 10px; }
        .parlay-title { font-weight: bold; color: #f0f6fc; }
        .parlay-odds { color: #3fb950; font-weight: bold; }
        .parlay-legs { list-style-type: disc; padding-left: 20px; margin: 10px 0; font-size: 13px; color: #8b949e; }
        .parlay-footer { font-size: 12px; color: #8b949e; display: flex; justify-content: space-between; margin-top: 10px; border-top: 1px solid #30363d; padding-top: 8px; }
        table { width: 100%; border-collapse: collapse; background: #161b22; border-radius: 8px; overflow: hidden; border: 1px solid #30363d; }
        th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #30363d; font-size: 14px; }
        th { background: #21262d; color: #8b949e; }
        .badge-active { color: #3fb950; font-weight: bold; }
        .badge-blocked { color: #f85149; font-weight: bold; }
        .badge-won { color: #58a6ff; font-weight: bold; }
    </style>
</head>
<body>
    <h1>⚡ OGBREEZE TIERED PARLAY & SHADOW COMMAND CENTER ⚡</h1>
    <p style="text-align: center; color: #8b949e; font-size: 12px;">UTC Timestamp: {{ timestamp }}</p>

    <div class="grid">
        <div class="metric">Pipeline Scans<span>{{ total_picks }}</span></div>
        <div class="metric">Active Shadow Bets<span>{{ active_count }}</span></div>
        <div class="metric">Quarantined Gatekeeper<span>{{ quarantined_count }}</span></div>
        <div class="metric">Estimated ROI<span>{{ roi }}%</span></div>
    </div>

    <div class="section-title">🎯 Active Parlay Slips</div>
    <div class="parlay-grid">
        {% for parlay in active_parlays %}
        <div class="parlay-card">
            <div class="parlay-header">
                <span class="parlay-title">{{ parlay.category }}</span>
                <span class="parlay-odds">{{ parlay.odds }}</span>
            </div>
            <ul class="parlay-legs">
                {% for leg in parlay.legs %}
                <li>{{ leg }}</li>
                {% endfor %}
            </ul>
            <div class="parlay-footer">
                <span>Stake: {{ parlay.stake }}</span>
                <span>Payout: {{ parlay.payout }}</span>
            </div>
        </div>
        {% endfor %}
    </div>

    <div class="section-title">🔥 High-Confidence Straight Bet Edge Archive</div>
    <table>
        <tr>
            <th>ID</th>
            <th>Target / Description</th>
            <th>Market</th>
            <th>Status</th>
            <th>Odds</th>
        </tr>
        {% for p in picks %}
        <tr>
            <td>{{ p.id }}</td>
            <td>{{ p.player_name }}</td>
            <td>{{ p.market_name }}</td>
            <td>
                {% if p.status == 'ACTIVE' %}<span class="badge-active">🟢 ACTIVE</span>
                {% elif p.status == 'QUARANTINED' %}<span class="badge-blocked">🚨 BLOCKED</span>
                {% elif p.status == 'WON' %}<span class="badge-won">✅ WON</span>
                {% else %}{{ p.status }}{% endif %}
            </td>
            <td>{{ p.picked_odds }}</td>
        </tr>
        {% endfor %}
    </table>
</body>
</html>
"""

# 6. Routes and Logic
@app.route("/")
def dashboard_view():
    # Dynamic Parlay Data Structure (No Bye Week Players)
    active_parlays = [
        {
            "category": "Standard Cap",
            "odds": "10.2x (+920)",
            "stake": "$50.00",
            "payout": "$510.00",
            "legs": [
                "Baltimore Ravens Team Total Over (Offensive PPG: 29.5)",
                "Lamar Jackson Over 225.5 Passing Yards",
                "Game Script: Baltimore Ravens vs Washington Commanders - High Pace & Efficiency Matchup"
            ]
        },
        {
            "category": "Booster Matrix",
            "odds": "53.5x (+5250)",
            "stake": "$25.00",
            "payout": "$1,337.50",
            "legs": [
                "San Francisco 49ers -6.5 (Top Offense vs Defense)",
                "Brock Purdy 2+ Passing Touchdowns",
                "Deebo Samuel 50+ Receiving Yards",
                "Game Total: San Francisco 49ers vs Arizona Cardinals Over 45.5"
            ]
        },
        {
            "category": "Bomb Target",
            "odds": "55.5x (+5450)",
            "stake": "$15.00",
            "payout": "$1,000.00+",
            "legs": [
                "Buffalo Bills -4.5 (No. 1 Scoring Offense)",
                "James Cook 75+ Rushing Yards & Anytime TD",
                "Josh Allen 3+ Pass TDs",
                "1st Half Total: Buffalo Bills vs New York Jets Over 21.5"
            ]
        }
    ]

    picks = []
    if DB_AVAILABLE:
        try:
            session = SessionLocal()
            picks = session.query(PickLog.id, PickLog.player_name, PickLog.market_name, PickLog.status, PickLog.picked_odds).all()
            session.close()
        except Exception as e:
            print(f"Query error: {e}")

    total_picks = len(picks) if picks else 0
    active_count = sum(1 for p in picks if p.status == "ACTIVE") if picks else 0
    quarantined_count = sum(1 for p in picks if p.status == "QUARANTINED") if picks else 0
    
    return render_template_string(
        HTML_TEMPLATE,
        timestamp=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
        total_picks=total_picks,
        active_count=active_count,
        quarantined_count=quarantined_count,
        roi="+0.00",
        active_parlays=active_parlays,
        picks=picks[-15:] if picks else []
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)