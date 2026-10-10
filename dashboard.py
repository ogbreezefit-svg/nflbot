import os
from datetime import datetime, timezone
from flask import Flask, render_template_string
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Attempt to load database components safely
try:
    from db import SessionLocal, PickLog, engine, Base
    Base.metadata.create_all(bind=engine)
    DB_AVAILABLE = True
except Exception as e:
    print(f"Database initialization warning: {e}")
    DB_AVAILABLE = False

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

@app.route("/")
def dashboard_view():
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
        picks=picks[-15:] if picks else []
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)