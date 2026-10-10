import os
import json
from datetime import datetime, timezone
from flask import Flask, render_template_string
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
import ingestion
from weekly_stats import shadow_roi, weekly_pick_summary

load_dotenv()
app = Flask(__name__)

# Initialize Database safely
try:
    from db import SessionLocal, PickLog, ParlaySlip, engine, Base, init_db
    init_db()
    DB_AVAILABLE = True
except Exception as e:
    print(f"Database initialization warning: {e}")
    DB_AVAILABLE = False

# Safe Background Scheduler Initialization
try:
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=ingestion.fetch_and_store_live_data, trigger="interval", minutes=60,
        next_run_time=datetime.now(timezone.utc), max_instances=1, coalesce=True,
    )
    scheduler.start()
    print("Background ingestion scheduler started.")
except Exception as e:
    print(f"Failed to start scheduler: {e}")

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
        .badge-archived { color: #8b949e; font-weight: bold; }
        .badge-blocked { color: #f85149; font-weight: bold; }
        .badge-won { color: #58a6ff; font-weight: bold; }
        .empty-state { text-align: center; color: #8b949e; padding: 20px; font-style: italic; }
    </style>
</head>
<body>
    <h1>⚡ OGBREEZE TIERED PARLAY & SHADOW COMMAND CENTER ⚡</h1>
    <p style="text-align: center; color: #8b949e; font-size: 12px;">UTC Timestamp: {{ timestamp }}</p>

    <div class="grid">
        <div class="metric">Logged Picks<span>{{ total_picks }}</span></div>
        <div class="metric">Active Shadow Bets<span>{{ active_count }}</span></div>
        <div class="metric">Quarantined / Review<span>{{ quarantined_count }}</span></div>
        <div class="metric">Settled Shadow ROI<span>{{ roi }}</span></div>
    </div>


    <!-- WEEKLY_PICK_TRACKER -->
    <div class="section-title">📊 Weekly Pick Record</div>
    <p style="color: #8b949e; font-size: 12px;">
        Monday–Sunday, Chicago time, grouped by game kickoff.
        Counts stored pick records—not parlay tickets or untracked legs.
        Win rate excludes pushes, pending picks, and review items.
    </p>

    {% if not weekly_available %}
    <p class="badge-blocked">
        Weekly results unavailable: the database could not be queried.
    </p>
    {% else %}
    <div style="overflow-x: auto;">
    <table>
        <tr>
            <th>Week</th>
            <th>Wins</th>
            <th>Losses</th>
            <th>Pushes</th>
            <th>Pending</th>
            <th>Review</th>
            <th>Other</th>
            <th>Total</th>
            <th>Win Rate</th>
        </tr>
        {% for week in weekly_summary.weeks %}
        <tr>
            <td>
                {{ week.label }}
                {% if week.current %}
                <span class="badge-active"> • Current</span>
                {% endif %}
            </td>
            <td class="badge-won">{{ week.wins }}</td>
            <td>{{ week.losses }}</td>
            <td>{{ week.pushes }}</td>
            <td>{{ week.pending }}</td>
            <td>{{ week.review }}</td>
            <td>{{ week.other }}</td>
            <td>{{ week.total }}</td>
            <td>{{ week.win_rate }}</td>
        </tr>
        {% endfor %}
    </table>
    </div>

    {% if weekly_summary.undated %}
    <p style="color: #d29922; font-size: 12px;">
        {{ weekly_summary.undated }} pick record(s) have no kickoff time.
        They are excluded from weekly totals—not assumed to belong
        to the current week.
    </p>
    {% endif %}
    {% endif %}

    <div class="section-title">🎯 Active Parlay Slips</div>
    <div class="parlay-grid">
        {% if active_parlays %}
            {% for parlay in active_parlays %}
            {% if parlay.category != 'Micro Sandbox' %}
            <div class="parlay-card">
                <div class="parlay-header">
                    <span class="parlay-title">{{ parlay.category }}</span>
                    <span class="parlay-odds">{{ parlay.odds }}</span>
                </div>
                <ul class="parlay-legs">
                    {% for leg in parlay.decoded_legs %}
                    <li>{{ leg }}</li>
                    {% endfor %}
                </ul>
                <div class="parlay-footer">
                    <span>Stake: {{ parlay.stake }}</span>
                    <span>Payout: {{ parlay.payout }}</span>
                </div>
            </div>
            {% endif %}
            {% endfor %}
        {% else %}
            <div class="empty-state" style="grid-column: 1 / -1;">No active parlays generated yet. Engine scanning upcoming matchups...</div>
        {% endif %}
    </div>

    <div class="section-title">📥 Sub-Threshold / Micro Sandbox</div>
    <p style="font-size: 12px; color: #8b949e;">Small micro bets, plus any Booster under 50x or Bomb under $1,000, are routed here automatically.</p>
    <table style="margin-bottom: 25px;">
        <tr>
            <th>Ticket</th>
            <th>Stake</th>
            <th>Odds</th>
            <th>Potential Return</th>
            <th>Status</th>
        </tr>
        {% if micro_parlays %}
            {% for m in micro_parlays %}
            <tr>
                <td>{{ m.decoded_legs | join(' + ') }}</td>
                <td>{{ m.stake }}</td>
                <td>{{ m.odds }}</td>
                <td class="badge-active">{{ m.payout }}</td>
                <td class="badge-archived">SET ASIDE</td>
            </tr>
            {% endfor %}
        {% else %}
            <tr><td colspan="5" class="empty-state">No micro sandbox tickets yet. Engine scanning upcoming matchups...</td></tr>
        {% endif %}
    </table>

    <div class="section-title">🔥 High-Confidence Straight Bet Edge Archive</div>
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
                <td>{{ p.picked_odds }}</td>
            </tr>
            {% endfor %}
        {% else %}
            <tr><td colspan="5" class="empty-state">No micro bets logged in the archive yet.</td></tr>
        {% endif %}
    </table>
</body>
</html>
"""

@app.route("/")
def dashboard_view():
    active_parlays = []
    micro_parlays = []
    picks = []
    total_picks = active_count = quarantined_count = 0
    roi = "N/A (no settled picks)"
    session = None
    weekly_summary = weekly_pick_summary([])
    weekly_available = False
    
    if DB_AVAILABLE:
        try:
            session = SessionLocal()
            weekly_summary = weekly_pick_summary(
                session.query(PickLog).all()
            )
            weekly_available = True
            total_picks = session.query(PickLog).count()
            active_count = session.query(PickLog).filter(
                PickLog.status == "ACTIVE", PickLog.is_shadow.is_(True)
            ).count()
            quarantined_count = session.query(PickLog).filter(
                PickLog.status.in_(["QUARANTINED", "REVIEW_REQUIRED"])
            ).count()
            roi = shadow_roi(session.query(PickLog).filter(
                PickLog.is_shadow.is_(True), PickLog.market_key == "h2h",
                PickLog.status.in_(["WON", "LOST", "PUSH"]),
                PickLog.realized_profit.isnot(None),
            ).all())
            
            # Fetch active parlays and decode their JSON legs safely in Python
            raw_parlays = session.query(ParlaySlip).filter(ParlaySlip.status == "ACTIVE").all()
            for p in raw_parlays:
                try:
                    p.decoded_legs = json.loads(p.legs_json) if p.legs_json else []
                except Exception:
                    p.decoded_legs = [p.legs_json] if p.legs_json else []
                active_parlays.append(p)

            # Show the tiers in order: Standard Cap, Booster Matrix, Bomb Target
            tier_order = {"Standard Cap": 0, "Booster Matrix": 1, "Bomb Target": 2}
            active_parlays.sort(key=lambda x: tier_order.get(x.category, 99))
            micro_parlays = [p for p in active_parlays if p.category == "Micro Sandbox"]
            
            # Fetch recent micro bets / straight bets for the archive ledger
            picks = session.query(PickLog).order_by(PickLog.id.desc()).limit(25).all()
        except Exception as e:
            print(f"Query error: {e}")
        finally:
            if session is not None:
                session.close()

    
    return render_template_string(
        HTML_TEMPLATE,
        timestamp=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
        total_picks=total_picks,
        active_count=active_count,
        quarantined_count=quarantined_count,
        roi=roi,
        weekly_summary=weekly_summary,
        weekly_available=weekly_available,
        active_parlays=active_parlays,
        micro_parlays=micro_parlays,
        picks=picks
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)