from db import SessionLocal, PickLog
from ingestion import SportsDataAPI
from datetime import datetime, timezone

def log_closing_lines():
    session = SessionLocal()
    api = SportsDataAPI()
    now = datetime.now(timezone.utc)
    
    # Query picks that haven't kicked off yet, but are within 30 minutes of kickoff, and lack a closing line
    unclosed_picks = session.query(PickLog).filter(
        PickLog.status == "ACTIVE",
        PickLog.closing_line.is_(None),
        PickLog.kickoff_time <= now
    ).all()

    for pick in unclosed_picks:
        # Fetch current line from The Odds API using the stored event_id
        current_odds_data = api.get_player_props(pick.event_id)
        
        # Example parsing logic to find Pinnacle's closing line for this exact market
        closing_line = None
        for bookmaker in current_odds_data.get("bookmakers", []):
            if bookmaker["key"] == "pinnacle":
                for market in bookmaker.get("markets", []):
                    if market["key"] == pick.market_name:
                        for outcome in market.get("outcomes", []):
                            if outcome["name"] == pick.pick_side:
                                closing_line = outcome.get("point") # For spreads/totals/props
                                break
                                
        if closing_line is not None:
            pick.closing_line = closing_line
            # Calculate CLV Edge (Example: picked Over 42.5, closed at Over 45.5 -> +3 points of CLV)
            modifier = 1 if pick.pick_side == "OVER" else -1
            pick.clv_edge = (closing_line - pick.picked_line) * modifier
            
    session.commit()
    session.close()