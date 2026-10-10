import os
from datetime import datetime, timezone
from ingestion import SportsDataAPI
from main import execute_shadow_mode

def run_strategy_pipeline():
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}] 🧠 Running Strategy Engine...")
    api = SportsDataAPI()
    
    # 1. Fetch upcoming games from The Odds API
    upcoming_games = api.get_upcoming_nfl_games()
    if not upcoming_games:
        print("No upcoming games found or schedule API failed.")
        return
        
    # 2. Fetch Season Stats from Tank01
    print("📊 Fetching live team stats from Tank01...")
    team_stats = api.get_tank01_stats("2026")
    
    print(f"🏈 Scanning {len(upcoming_games)} upcoming games for edge...")
    for game in upcoming_games:
        event_id = game.get("id")
        home_team = game.get("home_team", "Home")
        away_team = game.get("away_team", "Away")
        matchup_label = f"{away_team} @ {home_team}"
        kickoff = game.get("commence_time")
        
        if not kickoff:
            continue
            
        kickoff_dt = datetime.fromisoformat(kickoff.replace('Z', '+00:00'))
        if kickoff_dt <= datetime.now(timezone.utc):
            continue
            
        # 3. Pull stable odds lines for this specific game
        try:
            odds_data = api.get_game_odds(event_id)
        except Exception as e:
            print(f"⚠️ Could not fetch odds for game {event_id}: {e}")
            continue
        
        for bookmaker in odds_data.get("bookmakers", []):
            if bookmaker["key"] != "draftkings": # Standardize on DraftKings baseline
                continue
                
            for market in bookmaker.get("markets", []):
                market_name = market["key"] # 'h2h', 'spreads', or 'totals'
                
                for outcome in market.get("outcomes", []):
                    raw_desc = outcome.get("description") # Player/Team descriptor if applicable
                    side = outcome.get("name") # 'Over', 'Under', or Team Name
                    line = outcome.get("point") # Point spread or total line (None for h2h)
                    odds = outcome.get("price") # American price (e.g., -110, +310, -400)
                    
                    if odds is None:
                        continue
                        
                    # --- INTELLIGENT TEAM & MARKET FORMATTING ---
                    if market_name == "h2h":
                        target_name = f"{matchup_label} — Moneyline: {side}"
                        line_value = 0.0
                    elif market_name == "spreads":
                        target_name = f"{matchup_label} — Spread: {side} {line}"
                        line_value = line if line is not None else 0.0
                    elif market_name == "totals":
                        target_name = f"{matchup_label} — Game Total {side} {line}"
                        line_value = line if line is not None else 0.0
                    else:
                        readable_market = market_name.replace('_', ' ').title()
                        target_name = f"{matchup_label} — {readable_market} {side} {line if line is not None else ''}".strip()
                        line_value = line if line is not None else 0.0

                    # --- SIMULATED EDGE CHECK & DISPATCH ---
                    has_edge = True 
                        
                    if has_edge:
                        proposed_pick = {
                            "player_name": target_name,
                            "team_context": matchup_label,
                            "event_id": event_id,
                            "market": market_name,
                            "pick_side": side,
                            "line": line_value,
                            "odds": odds,
                            "kickoff_time": kickoff_dt,
                            "players": []
                        }
                        
                        # 4. Fire to the Gatekeeper via main.py
                        execute_shadow_mode(proposed_pick)
                        
    print("✅ Strategy scan complete.")

if __name__ == "__main__":
    run_strategy_pipeline()