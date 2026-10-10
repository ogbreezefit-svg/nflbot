# Inside execute_shadow_mode(proposed_pick):

# Determine a clean display name if it's a parlay or multi-leg ticket
display_name = proposed_press_name = proposed_pick.get("player_name")
if not display_name and "legs" in proposed_pick:
    # Auto-generate a readable summary for the parlay legs
    leg_summaries = [f"{leg.get('market')} {leg.get('pick_side')} {leg.get('line')}" for leg in proposed_pick.get("legs", [])]
    display_name = " | ".join(leg_summaries) if leg_summaries else "Tiered Parlay Ticket"

new_pick = PickLog(
    player_name=display_name, # <-- Uses the generated summary instead of leaving it blank
    event_id=proposed_pick.get("event_id"),
    market_name=proposed_pick.get("market", "tiered_parlay"),
    pick_side=proposed_pick.get("pick_side", "MULTI"),
    picked_line=proposed_pick.get("line", 0.0),
    picked_odds=proposed_pick.get("odds", 100),
    kickoff_time=proposed_pick.get("kickoff_time"),
    status="ACTIVE" if is_valid else "QUARANTINED",
    quarantine_reason=reason if not is_valid else None,
    stake=proposed_pick.get("stake", 50.0),
    is_shadow=True
)