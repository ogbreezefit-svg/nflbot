from dashboard_ui import build_dashboard_context
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

HTML_TEMPLATE = '\n<!DOCTYPE html>\n<html>\n<head>\n    <title>Ogbreeze Command Center</title>\n    <meta name="viewport" content="width=device-width, initial-scale=1">\n    <meta http-equiv="refresh" content="60">\n    <style>\n        body {\n            margin: 0; padding: 20px;\n            background: #0d1117; color: #c9d1d9;\n            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;\n        }\n        main { max-width: 1250px; margin: auto; }\n        h1 { color: #58a6ff; font-size: 24px; margin-bottom: 6px; }\n        h2 { font-size: 18px; color: #58a6ff; margin-top: 28px; }\n        .muted { color: #8b949e; font-size: 12px; line-height: 1.6; }\n        .metrics, .cards {\n            display: grid; gap: 12px;\n            grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));\n        }\n        .metric, .card, details {\n            background: #161b22; border: 1px solid #30363d;\n            border-radius: 8px; padding: 15px;\n        }\n        .metric span { display: block; font-size: 23px; margin-top: 8px; color: #f0f6fc; }\n        .metric small { display: block; margin-top: 5px; color: #8b949e; }\n        .card-header { display: flex; justify-content: space-between; gap: 10px; }\n        .price, .won { color: #3fb950; }\n        .lost { color: #f85149; }\n        .review { color: #d29922; }\n        ul { padding-left: 20px; font-size: 13px; line-height: 1.8; }\n        .table-wrap { overflow-x: auto; }\n        table { width: 100%; border-collapse: collapse; font-size: 13px; }\n        th, td { padding: 11px; border-bottom: 1px solid #30363d; text-align: left; }\n        th { color: #8b949e; }\n        summary { cursor: pointer; color: #58a6ff; }\n        details { margin-top: 16px; }\n        .empty { color: #8b949e; padding: 12px 0; }\n        .error { border: 1px solid #f85149; padding: 15px; }\n    </style>\n</head>\n<body>\n<main>\n    <h1>⚡ OGBREEZE COMMAND CENTER</h1>\n    <p class="muted">{{ week_label }} · Chicago time · {{ timestamp }}</p>\n\n    {% if not available %}\n    <p class="error">Dashboard data unavailable. Check deployment logs.</p>\n    {% else %}\n\n    <div class="metrics">\n        <div class="metric">This Week’s Straight Picks\n            <span>{{ straight_count }}</span>\n            <small>Engine-logged standalone moneylines</small>\n        </div>\n        <div class="metric">Pending Selections\n            <span>{{ pending_selections }}</span>\n            <small>This week’s unique tracked selections</small>\n        </div>\n        <div class="metric">Pending Tickets\n            <span>—</span>\n            <small>Awaiting ticket-to-leg outcome links</small>\n        </div>\n        <div class="metric">Weekly Selection Record\n            <span>{{ record }}</span>\n            <small>Wins–losses–pushes · Win rate {{ win_rate }}</small>\n        </div>\n    </div>\n\n    {% if review_count %}\n    <p class="muted review">{{ review_count }} current-week selection(s) require review.</p>\n    {% endif %}\n\n    <h2>🎯 Parlay Tickets</h2>\n    <p class="muted">\n        Current engine-generated slips. Stakes and potential returns are engine estimates,\n        not confirmed sportsbook wagers or accepted quotes.\n    </p>\n    <div class="cards">\n        {% for ticket in active_tickets %}\n        <div class="card">\n            <div class="card-header">\n                <span>{{ ticket.category }}</span>\n                <span class="price">{{ ticket.odds }}</span>\n            </div>\n            <ul>{% for leg in ticket.legs %}<li>{{ leg }}</li>{% endfor %}</ul>\n            <div class="muted">\n                Stake {{ ticket.stake }} · Potential return {{ ticket.payout }}<br>\n                Ticket #{{ ticket.id }} · Outcome {{ ticket.outcome }}\n            </div>\n        </div>\n        {% else %}\n        <p class="empty">No current parlay slips.</p>\n        {% endfor %}\n    </div>\n\n    <details>\n        <summary>📥 Micro Sandbox · {{ micro_tickets | length }} current slips</summary>\n        <div class="table-wrap">\n        <table>\n            <tr><th>Selections</th><th>Stake</th><th>Odds</th><th>Potential Return</th></tr>\n            {% for ticket in micro_tickets %}\n            <tr>\n                <td>{{ ticket.legs | join(\' + \') }}</td>\n                <td>{{ ticket.stake }}</td>\n                <td>{{ ticket.odds }}</td>\n                <td>{{ ticket.payout }}</td>\n            </tr>\n            {% else %}\n            <tr><td colspan="4">No current Micro slips.</td></tr>\n            {% endfor %}\n        </table>\n        </div>\n    </details>\n\n    <h2>🏈 Straight Game Picks</h2>\n    <p class="muted">\n        This week’s standalone moneylines already logged by your engine.\n        Selection rules are unchanged; these are not newly filtered recommendations.\n    </p>\n\n    {% macro straight_table(rows) %}\n    <div class="table-wrap">\n    <table>\n        <tr><th>Game</th><th>Pick</th><th>Odds</th><th>Kickoff</th><th>Result</th></tr>\n        {% for pick in rows %}\n        <tr>\n            <td>{{ pick.game }}</td><td>{{ pick.pick }}</td>\n            <td>{{ pick.odds }}</td><td>{{ pick.kickoff }}</td>\n            <td class="{{ \'won\' if pick.status == \'WON\' else (\'lost\' if pick.status == \'LOST\' else \'\') }}">\n                {{ pick.status }}\n            </td>\n        </tr>\n        {% else %}\n        <tr><td colspan="5">No dated standalone picks recorded for this week.</td></tr>\n        {% endfor %}\n    </table>\n    </div>\n    {% endmacro %}\n\n    {{ straight_table(straight_preview) }}\n    {% if straight_more %}\n    <details>\n        <summary>Show {{ straight_more | length }} more straight picks</summary>\n        {{ straight_table(straight_more) }}\n    </details>\n    {% endif %}\n\n    <details>\n        <summary>🗓 This Week’s Games · {{ games | length }} recorded games</summary>\n        <p class="muted">\n            Games represented in stored engine selections—not a complete schedule feed.\n            Listing a game here does not designate it as a pick.\n        </p>\n        <div class="table-wrap">\n        <table>\n            <tr><th>Game</th><th>Kickoff</th></tr>\n            {% for game in games %}\n            <tr><td>{{ game.game }}</td><td>{{ game.kickoff }}</td></tr>\n            {% else %}\n            <tr><td colspan="2">No dated games recorded for this week.</td></tr>\n            {% endfor %}\n        </table>\n        </div>\n    </details>\n\n    <details>\n        <summary>📊 Weekly Selection History</summary>\n        <div class="table-wrap">\n        <table>\n            <tr>\n                <th>Week</th><th>Wins</th><th>Losses</th><th>Pushes</th>\n                <th>Pending</th><th>Review</th><th>Win Rate</th>\n            </tr>\n            {% for week in weekly_summary.weeks %}\n            <tr>\n                <td>{{ week.label }}</td><td>{{ week.wins }}</td>\n                <td>{{ week.losses }}</td><td>{{ week.pushes }}</td>\n                <td>{{ week.pending }}</td><td>{{ week.review }}</td>\n                <td>{{ week.win_rate }}</td>\n            </tr>\n            {% endfor %}\n        </table>\n        </div>\n    </details>\n\n    <details>\n        <summary>🧾 Ticket History · latest {{ ticket_history | length }} generated slips</summary>\n        <p class="muted">\n            Display status is separate from betting outcome.\n            ACTIVE and ARCHIVED do not mean pending, won, or lost.\n            Repeated engine-generated versions are not confirmed placed bets.\n            Ticket outcomes remain untracked until structured ticket links are added.\n        </p>\n        <div class="table-wrap">\n        <table>\n            <tr>\n                <th>Ticket</th><th>Created</th><th>Category</th>\n                <th>Display Status</th><th>Outcome</th><th>Legs</th>\n            </tr>\n            {% for ticket in ticket_history %}\n            <tr>\n                <td>#{{ ticket.id }}</td><td>{{ ticket.created }}</td>\n                <td>{{ ticket.category }}</td><td>{{ ticket.display_status }}</td>\n                <td>{{ ticket.outcome }}</td>\n                <td>\n                    <details>\n                        <summary>View</summary>\n                        <ul>{% for leg in ticket.legs %}<li>{{ leg }}</li>{% endfor %}</ul>\n                    </details>\n                </td>\n            </tr>\n            {% endfor %}\n        </table>\n        </div>\n    </details>\n\n    {% if undated %}\n    <p class="muted">\n        {{ undated }} stored selection(s) lack kickoff dates and are excluded from current-week totals.\n    </p>\n    {% endif %}\n\n    {% endif %}\n</main>\n</body>\n</html>\n'

@app.route("/")
def dashboard_view():
    data = build_dashboard_context([], [])
    available = False

    if DB_AVAILABLE:
        try:
            with SessionLocal() as session:
                picks = session.query(PickLog).all()
                slips = session.query(ParlaySlip).all()
                data = build_dashboard_context(picks, slips)
                available = True
        except Exception as error:
            print(f"Dashboard query error: {error}")

    return render_template_string(
        HTML_TEMPLATE, available=available, **data
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)