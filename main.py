from db import SessionLocal, PickLog
from ingestion import SportsDataAPI
from validator import validate_pick

def execute_shadow_mode(proposed_pick: dict = None, **kwargs):
    """
    Accepts a proposed pick dictionary directly or via keyword arguments,
    runs it through the Gatekeeper validator, and logs it to the database.
    """
    # Fallback if arguments were passed as keyword args instead of a dict
    if not proposed_pick and kwargs:
        proposed_pick = kwargs

    if not proposed_pick or not isinstance(proposed_pick, dict):
        print("🚨 ERROR: execute_shadow_mode called with an invalid or undefined pick payload.")
        return

    session = SessionLocal()
    api = SportsDataAPI()
    
    # 1. Fetch live injury roster from Sleeper
    try:
        sleeper_roster = api.get_sleeper_players()
    except Exception as e:
        print(f"⚠️ Warning: Could not fetch Sleeper roster: {e}")
        sleeper_roster = {}
    
    # 2. Pass the pick through the Pre-Flight Gatekeeper
    is_valid, reason = validate_pick(proposed_pick, sleeper_roster)
    
    # 3. Determine a clean display name (handles single props or multi-leg parlays)
    display_name = proposed_pick.get("player_name")
    if not display_name and "legs" in proposed_pick:
        leg_summaries = [f"{leg.get('market', '')} {leg.get('pick_side', '')} {leg.get('line', '')}".strip() for leg in proposed_pick.get("legs", [])]
        display_name = " | ".join(leg_summaries) if leg_summaries else "Ogbreeze Tiered Parlay"
    elif not display_name:
        display_name = "System Pick / Game Total"

    # 4. Log the paper bet to the database
    new_pick = PickLog(
        player_name=display_name,
        event_id=proposed_pick.get("event_id", "unknown_event"),
        market_name=proposed_pick.get("market_name") or proposed_pick.get("market", "standard_prop"),
        pick_side=proposed_pick.get("pick_side", "OVER"),
        picked_line=proposed_pick.get("picked_line") or proposed_pick.get("line", 0.0),
        picked_odds=proposed_pick.get("picked_odds") or proposed_pick.get("odds", -110),
        kickoff_time=proposed_pick.get("kickoff_time"),
        status="ACTIVE" if is_valid else "QUARANTINED",
        quarantine_reason=reason if not is_valid else None,
        stake=proposed_pick.get("stake", 50.0),
        is_shadow=True
    )
    
    session.add(new_pick)
    session.commit()
    
    # Print status output
    if is_valid:
        print(f"Shadow Ticket Processed: ✅ ACCEPTED -> {display_name}")
    else:
        print(f"Shadow Ticket Processed: 🚨 QUARANTINED -> {display_name} | Reason: {reason}")
        
    session.close()

if __name__ == "__main__":
    # Test execution payload if running main.py directly
    from datetime import datetime, timezone
    sample_ticket = {
        "player_name": "Patrick Mahomes",
        "market": "player_pass_tds",
        "pick_side": "OVER",
        "line": 1.5,
        "odds": -110,
        "kickoff_time": datetime.now(timezone.utc),
        "players": ["Patrick Mahomes"]
    }
    execute_shadow_mode(sample_ticket)