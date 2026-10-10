from db import SessionLocal, PickLog
from sqlalchemy import func

def print_shadow_metrics():
    session = SessionLocal()
    
    total_picks = session.query(PickLog).filter(PickLog.is_shadow == True).count()
    quarantined = session.query(PickLog).filter(PickLog.status == "QUARANTINED").count()
    won = session.query(PickLog).filter(PickLog.status == "WON").count()
    lost = session.query(PickLog).filter(PickLog.status == "LOST").count()
    
    # Calculate Average CLV Beat
    avg_clv = session.query(func.avg(PickLog.clv_edge)).filter(PickLog.status != "QUARANTINED").scalar() or 0.0
    
    # Calculate Shadow ROI ($50 per unit)
    total_staked = (won + lost) * 50.0
    # Assuming standard -110 odds (+45.45 profit per win)
    total_profit = (won * 45.45) - (lost * 50.0)
    roi = (total_profit / total_staked * 100) if total_staked > 0 else 0.0

    print("==========================================")
    print("      📊 SHADOW MODE PERFORMANCE REPORT   ")
    print("==========================================")
    print(f"Total Evaluated Picks: {total_picks}")
    print(f"Quarantined by Gatekeeper: {quarantined} ({quarantined/max(total_picks,1)*100:.1f}%)")
    print(f"Active Bets Record: {won}W - {lost}L")
    print(f"Estimated ROI: {roi:.2f}%")
    print(f"Avg CLV Edge: {avg_clv:+.2f} points vs Pinnacle Close")
    print("==========================================")
    
    if avg_clv > 0:
        print("🟢 Market Beat Status: BEATING THE CLOSING LINE (Valid Edge)")
    else:
        print("🔴 Market Beat Status: LAG BEHAVIOR (Refine Selection Model)")

if __name__ == "__main__":
    print_shadow_metrics()