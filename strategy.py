import os
from datetime import datetime, timezone
from ingestion import SportsDataAPI
from main import execute_shadow_mode

def calculate_implied_probability(american_odds: int) -> float:
    """Converts American odds (e.g., -110, +150) to implied probability percentages."""
    if american_odds < 0:
        return (abs(american_odds) / (abs(american_odds) + 100)) * 100
    else:
        return (100 / (american_odds + 100)) * 100

def run_strategy_pipeline():
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}] 🧠 Running Strategy Engine...")
    api = SportsDataAPI()
    
    # 1. Fetch upcoming games from The Odds API
    try:
        upcoming_games = api.get_upcoming_nfl_games()
    except AttributeError:
        print("🚨 ERROR: get_upcoming_nfl_games() is missing from ingestion.py!")
        print("Make sure you added the schedule fetching function to ingestion.py.")
        return
        
    if not upcoming_games:
        print("No upcoming games found or schedule API failed.")
        return
        
    # 2. Fetch Season Stats from Tank01
    print("📊 Fetching live team stats from Tank01...")
    team_stats = api.get_tank01_stats("2026")
    
    print(f"🏈 Scanning {len(upcoming_games)} upcoming games for edge...")
    for game in upcoming_games:
        event_id = game.get("id")
        kickoff = game.get("commence_time") # e.g., '2026-10-11T17:00:00Z'
        
        # Skip if game has already started
        kickoff_dt = datetime.fromisoformat(kickoff.replace('Z', '+00:00'))
        if kickoff_dt <= datetime.now(timezone.utc):
            continue
            
        # 3. Pull Prop lines for this specific game
        try:
            props = api.get_player_props(event_id)
        except Exception as e:
            print(f"⚠️ Could not fetch props for game {event_id}: {e}")
            continue
        
        for bookmaker in props.get("bookmakers", []):
            if bookmaker["key"] != "draftkings": # Standardize on one book for baseline
                continue
                
            for market in bookmaker.get("markets", []):
                market_name = market["key"] # e.g., 'player_pass_tds'
                
                for outcome in market.get("outcomes", []):
                    player_name = outcome.get("description") # e.g., 'Patrick Mahomes'
                    side = outcome.get("name") # 'Over' or 'Under'
                    line = outcome.get("point") # e.g., 1.5
                    odds = outcome.get("price") # e.g., -110
                    
                    if not line or not player_name or not odds:
                        continue
                        
                    # --- THE QUANTITATIVE MODEL ---
                    # In production, this replaces your hardcoded stats mapping.
                    # For this shadow test run, we simulate a projected baseline.
                    projected_stat = line * 1.2 
                    
                    implied_prob = calculate_implied_probability(odds)
                    
                    # Calculate if we have an edge
                    has_edge = False
                    if side.upper() == "OVER" and projected_stat > (line * 1.15): # 15% buffer
                        has_edge = True
                    elif side.upper() == "UNDER" and projected_stat < (line * 0.85):
                        has_edge = True
                        
                    if has_edge:
                        proposed_pick = {
                            "player_name": player_name,
                            "event_id": event_id,
                            "market": market_name,
                            "pick_side": side.upper(),
                            "line": line,
                            "odds": odds,
                            "kickoff_time": kickoff_dt,
                            "players": [player_name] # Used by gatekeeper for injury check
                        }
                        
                        # 4. Fire to the Gatekeeper!
                        execute_shadow_mode(proposed_pick)
                        
    print("✅ Strategy scan complete.")

if __name__ == "__main__":
    run_strategy_pipeline()