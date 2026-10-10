from datetime import datetime, timedelta, timezone

def validate_pick(pick: dict, sleeper_players: dict) -> tuple[bool, str]:
    """
    Evaluates a proposed pick/parlay against Injury, Time, and Math checks.
    Returns (True, "PASSED") or (False, "Reason for Quarantine").
    """
    now = datetime.now(timezone.utc)
    
    # 1. The Time Horizon Check
    kickoff = pick.get("kickoff_time")
    if not kickoff or not (now <= kickoff <= now + timedelta(days=7)):
        return False, f"Time Horizon Violation: Kickoff {kickoff} is outside the 7-day window."

    # 2. The Injury Check
    # The pick payload must pass multiple legs if it's a parlay. We iterate over all players involved.
    players_involved = pick.get("players", [pick.get("player_name")])
    for player_name in players_involved:
        if not player_name:
            continue
            
        # Match player name to Sleeper dict
        matched_player = next(
            (p for p in sleeper_players.values() 
             if f"{p.get('first_name', '')} {p.get('last_name', '')}".lower() == player_name.lower()), 
            None
        )
        
        if matched_player:
            status = matched_player.get("status", "Inactive")
            injury = matched_player.get("injury_status")
            
            if status != "Active" or injury in ["Out", "IR", "Questionable", "DNP"]:
                return False, f"Injury Check Failed: {player_name} is {status} / {injury}."
        else:
            return False, f"Gatekeeper Alert: Could not verify injury status for {player_name}."

    # 3. The Math Check (Game Scripting / Correlation)
    # Example: A parlay leg with an Under Total vs a Player Prop Over for TDs
    legs = pick.get("legs", [pick])
    has_heavy_under = any(l.get("market") == "totals" and l.get("pick_side") == "UNDER" and l.get("line", 50) < 42.5 for l in legs)
    has_high_qb_tds = any(l.get("market") == "player_pass_tds" and l.get("pick_side") == "OVER" and l.get("line", 0) >= 2.5 for l in legs)

    if has_heavy_under and has_high_qb_tds:
        return False, "Math Check Failed: Contradictory Game Script (Under 42.5 Total vs QB Over 2.5 TDs)."

    return True, "PASSED"