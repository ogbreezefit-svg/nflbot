from datetime import datetime, timezone

def validate_pick(proposed_pick: dict, sleeper_roster: dict) -> tuple[bool, str]:
    """
    Gatekeeper validation pipeline.
    Checks:
      1. Time Horizon Window (Kickoff sanity & automatic string-to-datetime parsing)
      2. Injury Status (Sleeper API check for inactive/IR/out players)
      3. Mathematical Logic & Parlay Contradictions
    Returns:
      (True, "PASSED") if valid, else (False, "Quarantine Reason")
    """
    if not isinstance(proposed_pick, dict):
        return False, "Gatekeeper Error: Invalid pick payload format (expected dictionary)."

    # ------------------------------------------------------------------
    # 1. Time Horizon & Kickoff Sanity Check
    # ------------------------------------------------------------------
    kickoff = proposed_pick.get("kickoff_time")
    if not kickoff:
        return False, "Time Horizon Violation: Missing kickoff timestamp."
    
    # If kickoff was passed as an ISO string instead of datetime, parse it
    if isinstance(kickoff, str):
        try:
            kickoff = datetime.fromisoformat(kickoff.replace('Z', '+00:00'))
        except ValueError:
            return False, "Time Horizon Violation: Invalid kickoff timestamp format."

    now = datetime.now(timezone.utc)
    
    # Ensure timezone awareness
    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)
        
    time_to_kick = kickoff - now
    
    # Reject if game has already started or is more than 7 days out
    if time_to_kick.total_seconds() <= 0:
        return False, "Time Horizon Violation: Game has already started or kickoff has passed."
    if time_to_kick.days > 7:
        return False, "Time Horizon Violation: Kickoff is further than the 7-day window."

    # ------------------------------------------------------------------
    # 2. Player Injury Check (Sleeper Roster Gate)
    # ------------------------------------------------------------------
    players_to_check = proposed_pick.get("players", [])
    if not players_to_check and proposed_pick.get("player_name"):
        players_to_check = [proposed_pick.get("player_name")]

    # Normalize sleeper_roster to handle list or dict formats safely
    if isinstance(sleeper_roster, list):
        # Convert list format to dict keyed by player name or ID if needed
        roster_iterable = {str(p.get('player_id', i)): p for i, p in enumerate(sleeper_roster)}
    elif isinstance(sleeper_roster, dict):
        roster_iterable = sleeper_roster
    else:
        roster_iterable = {}

    for player_name in players_to_check:
        if not player_name or not isinstance(player_name, str):
            continue
            
        matched_player = None
        for pid, data in roster_iterable.items():
            if not isinstance(data, dict):
                continue
            first = data.get('first_name', '') or ''
            last = data.get('last_name', '') or ''
            full_name = f"{first} {last}".strip()
            
            # Match by full name or if the player name is contained in the string
            if full_name.lower() == player_name.lower() or player_name.lower() in full_name.lower():
                matched_player = data
                break
        
        if matched_player:
            injury_status = matched_player.get("injury_status")
            active_status = matched_player.get("status")
            
            # Quarantine if injured or inactive
            if injury_status in ["Out", "IR", "Doubtful", "PUP", "Sus"]:
                return False, f"Injury Check Failed: {player_name} is marked as '{injury_status}'."
            if active_status and str(active_status).lower() in ["inactive", "ir"]:
                return False, f"Injury Check Failed: {player_name} roster status is '{active_status}'."

    # ------------------------------------------------------------------
    # 3. Mathematical Logic & Parlay Contradiction Check
    # ------------------------------------------------------------------
    legs = proposed_pick.get("legs", [])
    if isinstance(legs, list) and legs:
        totals_sides = [leg.get("pick_side") for leg in legs if leg.get("market") == "totals"]
        if len(set(totals_sides)) > 1:
            return False, "Math Check Failed: Contradictory total lines found within parlay legs."

    return True, "PASSED"