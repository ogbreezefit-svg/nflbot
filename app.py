import os
import json
import logging
from datetime import datetime, timezone

from flask import Flask, render_template_string
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ogbreeze")

load_dotenv()
app = Flask(__name__)

# ---------- Database ----------
try:
    from db import SessionLocal, PickLog, ParlaySlip, engine, init_db
    init_db()
    DB_AVAILABLE = True
except Exception:
    log.exception("DATABASE INIT FAILED")
    DB_AVAILABLE = False

# ---------- Ingestion + scheduler ----------
try:
    import ingestion
except Exception:
    log.exception("COULD NOT IMPORT ingestion.py")
    ingestion = None


def run_ingestion():
    if ingestion is None:
        log.error("Ingestion module not loaded.")
        return
    try:
        ingestion.fetch_and_store_live_data()
    except Exception:
        log.exception("INGESTION FAILED")


try:
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=run_ingestion,
        trigger="interval",
        hours=6,                                # saves Odds API credits
        next_run_time=datetime.now(timezone.utc),  # also run once at startup
        max_instances=1,
    )
    scheduler.start()
    log.info("Background ingestion scheduler started.")
except Exception:
    log.exception("SCHEDULER FAILED TO START")

# ---------- Page template ----------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Ogbreeze Command Center</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="30">
    <style>
        body { background-color: #0d1117; color: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 20px; }
        h1 { color: #58a6ff; text-align: center; font-size: 24px; border-bottom: 1px solid #30363d; padding-bottom: 15px; }
        .grid { display: flex; justify-content: space-around; flex-wrap: wrap; gap: 10px; background: #161b22; padding: 15px; border-radius: 8px; border: 1px solid #30363d; margin-bottom: 20px; }
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
        .table-wrap { overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; background: #161b22; border-radius: 8px; overflow: hidden; border: 1px solid #30363d; }
        th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #30363d; font-size: 14px; }
        th { background: #21262d; color: #8b949e; }
        .badge-active { color: #3fb950; font-weight: bold; }
        .badge-archived { color: #8b949e; font-weight: bold; }
        .badge-blocked { color: #f85149; font-weight: bold; }
        .badge-won { color: #58a6ff; font-weight: bold; }
        .empty-state { text-align: center; color: #8b949e; padding: 20px; font-style: italic; }
        .warn { background: #3d1f1f; border: 1px solid #f85149; color: #f85149; padding: 10px; border-radius: 8px; text-align: center; margin-bottom: 15px; }
    </style>
</head>
<body>
    <h1>⚡ OGBREEZE TIERED PARLAY &amp; SHADOW COMMAND CENTER ⚡</h1>
    <p style="text-align: center; color: #8b949e; font-size: 12px;">UTC Timestamp: {{ timestamp }}</p>

    {% if not db_available %}
    <div class="warn">Database is not connected. Check your logs and visit /debug</div>
    {% endif %}

    <div class="grid">
        <div class="metric">Total Picks<span>{{ total_picks }}</span></div>
        <div class="metric">Active Shadow Bets<span>{{ active_count }}</span></div>
        <div class="metric">Quarantined<span>{{ quarantined_count }}</span></div>
        <div class="metric">Estimated ROI<span>{{ roi }}%</span></div>
    </div>

    <div class="section-title">🎯 Active Parlay Slips</div>
    <div class="parlay-grid">
        {% if active_parlays %}
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
        {% else %}
            <div class="empty-state" style="grid-column: 1 / -1;">No active parlays generated yet. Engine scanning upcoming matchups...</div>
        {% endif %}
    </div>

    <div class="section-title">🔥 High-Confidence Straight Bet Edge Archive</div>
    <div class="table-wrap">
    <table>
        <tr>
            <th>ID</th>
            <th>Target / Description</th>
            <th>Market</th>
            <th>Status</th>
            <th>Odds</th>
        </tr>
        {% if picks %}
            {% for p in picks %}
            <tr>
                <td>{{ p.id }}</td>
                <td>{{ p.player_name }}</td>
                <td>{{ p.market_name }}</td>
                <td>
                    {% if p.status == 'ACTIVE' %}<span class="badge-active">🟢 ACTIVE</span>
                    {% elif p.status == 'ARCHIVED' %}<span class="badge-archived">⚪ ARCHIVED</span>
                    {% elif p.status == 'QUARANTINED' %}<span class="badge-blocked">🚨 BLOCKED</span>
                    {% elif p.status == 'WON' %}<span class="badge-won">✅ WON</span>
                    {% else %}{{ p.status }}{% endif %}
                </td>
                <td>{{ p.odds }}</td>
            </tr>
            {% endfor %}
        {% else %}
            <tr><td colspan="5" class="empty-state">No micro bets logged in the archive yet.</td></tr>
        {% endif %}
    </table>
    </div>
</body>
</html>
"""


@app.route("/")
def dashboard_view():
    active_parlays = []
    picks = []
    total_picks = active_count = quarantined_count = 0

    if DB_AVAILABLE:
        session = SessionLocal()
        try:
            # Parlays: convert to plain dicts so the page never touches a closed session
            for p in session.query(ParlaySlip).filter(ParlaySlip.status == "ACTIVE").all():
                try:
                    legs = json.loads(p.legs_json) if p.legs_json else []
                except Exception:
                    legs = [p.legs_json] if p.legs_json else []
                active_parlays.append({
                    "category": p.category, "odds": p.odds, "stake": p.stake,
                    "payout": p.payout, "legs": legs,
                })

            for p in session.query(PickLog).order_by(PickLog.id.desc()).limit(25).all():
                odds = p.picked_odds
                if odds is not None and float(odds).is_integer():
                    odds = int(odds)
                picks.append({
                    "id": p.id, "player_name": p.player_name, "market_name": p.market_name,
                    "status": p.status, "odds": odds if odds is not None else "-",
                })

            total_picks = session.query(PickLog).count()
            active_count = session.query(PickLog).filter(PickLog.status == "ACTIVE").count()
            quarantined_count = session.query(PickLog).filter(PickLog.status == "QUARANTINED").count()
        except Exception:
            log.exception("DASHBOARD QUERY FAILED")
        finally:
            session.close()

    return render_template_string(
        HTML_TEMPLATE,
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        db_available=DB_AVAILABLE,
        total_picks=total_picks,
        active_count=active_count,
        quarantined_count=quarantined_count,
        roi="+0.00",
        active_parlays=active_parlays,
        picks=picks,
    )


@app.route("/debug")
def debug():
    info = {
        "DB_AVAILABLE": DB_AVAILABLE,
        "ODDS_API_KEY_set": bool(os.getenv("ODDS_API_KEY")),
        "DATABASE_URL_set": bool(os.getenv("DATABASE_URL")),
        "ingestion_loaded": ingestion is not None,
    }
    if DB_AVAILABLE:
        s = SessionLocal()
        try:
            info["database_type"] = engine.dialect.name
            info["pick_count"] = s.query(PickLog).count()
            info["parlay_count"] = s.query(ParlaySlip).count()
            info["parlay_statuses"] = [r[0] for r in s.query(ParlaySlip.status).distinct()]
            info["pick_statuses"] = [r[0] for r in s.query(PickLog.status).distinct()]
        except Exception as e:
            log.exception("DEBUG QUERY FAILED")
            info["error"] = str(e)
        finally:
            s.close()
    return info


@app.route("/run-now")
def run_now():
    """Visit this once to fetch data immediately without waiting."""
    run_ingestion()
    return "Ingestion triggered. Check your logs, then go back to the dashboard."


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
