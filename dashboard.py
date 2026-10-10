import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from db import SessionLocal, PickLog

load_dotenv()

def print_header():
    print("\n" + "═" * 75)
    print(" ⚡ OGBREEZE TIERED PARLAY & SHADOW COMMAND CENTER ⚡".center(75))
    print(f" Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}".center(75))
    print("═" * 75)

def render_dashboard():
    session = SessionLocal()
    picks = session.query(PickLog).all()
    session.close()

    total_picks = len(picks)
    if total_picks == 0:
        print_header()
        print("\n  [!] No active shadow picks or parlay tickets found in the database.")
        print("  [!] Run 'python3 strategy.py' to generate new automated edges.\n")
        print("═" * 75 + "\n")
        return

    quarantined = [p for p in picks if p.status == "QUARANTINED"]
    active = [p for p in picks if p.status == "ACTIVE"]
    settled = [p for p in picks if p.status in ["WON", "LOST", "PUSH"]]
    
    won = [p for p in settled if p.status == "WON"]
    lost = [p for p in settled if p.status == "LOST"]
    
    total_staked = len(settled) * 50.0
    profit = (len(won) * 45.45) - (len(lost) * 50.0)
    roi = (profit / total_staked * 100) if total_staked > 0 else 0.0
    
    clv_edges = [p.clv_edge for p in settled if p.clv_edge is not None]
    avg_clv = sum(clv_edges) / len(clv_edges) if clv_edges else 0.0

    print_header()
    
    print(f" 📊 PORTFOLIO HEALTH SUMMARY")
    print(f" ───────────────────────────────────────────────────────────────────────────")
    print(f" • Total Pipeline Scans : {total_picks:<5} | Quarantined Gatekeeper : {len(quarantined):<5}")
    print(f" • Active Shadow Bets   : {len(active):<5} | Settled Record         : {len(won)}W - {len(lost)}L")
    print(f" • Estimated ROI        : {roi:>+.2f}%       | Avg Closing Edge (CLV) : {avg_clv:>+.2f} pts")
    print(f" ───────────────────────────────────────────────────────────────────────────\n")

    print(f" 📋 RECENT PIPELINE TICKETS")
    print(f" {"ID":<4} | {"TARGET / PARLAY DESCRIPTION":<38} | {"STATUS":<12} | {"ODDS":<6}")
    print(f" " + "-" * 73)

    for p in picks[-12:]: 
        status_icon = "🟢 ACTIVE"
        if p.status == "QUARANTINED": status_icon = "🚨 BLOCKED"
        elif p.status == "WON":       status_icon = "✅ WON"
        elif p.status == "LOST":      status_icon = "❌ LOST"
        elif p.status == "PUSH":      status_icon = "➖ PUSH"

        target_label = (p.player_name or "Unknown Target")[:36]
        odds_label = str(p.picked_odds) if p.picked_odds else "N/A"

        print(f" {p.id:<4} | {target_label:<38} | {status_icon:<12} | {odds_label:<6}")

    print(" " + "═" * 75)
    if avg_clv >= 0:
        print(" 🟢 Market Beat Status: POSITIVE CLV ACCELERATION (Model Alpha Verified)")
    else:
        print(" 🟡 Market Beat Status: LAG BEHAVIOR (Tightening Execution Thresholds)")
    print("═" * 75 + "\n")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)