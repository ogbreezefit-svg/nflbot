import os
from datetime import datetime, timezone
from ingestion import SportsDataAPI
from main import execute_shadow_mode

def calculate_implied_probability(american_odds: int) -> float:
    """Converts American odds (e.g., -110, +150) to implied probability percentages."""
    if american_odds is None:
        return 50.0
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
        home_team = game.get("home_team", "Home")
        away_team = game.get("away_team", "Away")
        matchup_label = f"{away_team} @ {home_team}"
        kickoff = game.get("commence_time") # e.g., '2026-10-11T17:00:00Z'
        
        if not kickoff:
            continue
            
        # Skip if game has already started
        kickoff_dt = datetime.fromisoformat(kickoff.replace('Z', '+00:00'))
        if kickoff_dt <= datetime.now(timezone.utc):
            continue
            
        # 3. Pull Prop / Odds lines for this specific game
        try:
            props = api.get_player_props(event_id)
        except Exception as e:
            print(f"⚠️ Could not fetch props for game {event_id}: {e}")
            continue
        
        for bookmaker in props.get("bookmakers", []):
            if bookmaker["key"] != "draftkings": # Standardize on DraftKings baseline
                continue
                
            for market in bookmaker.get("markets", []):
                market_name = market["key"] # e.g., 'h2h', 'totals', 'h1_totals', 'player_pass_tds'
                
                for outcome in market.get("outcomes", []):
                    raw_desc = outcome.get("description") # Player name if prop, None if game/half total or moneyline
                    side = outcome.get("name") # 'Over', 'Under', or Team Name (e.g., 'Philadelphia Eagles')
                    line = outcome.get("point") # Float value (None for moneylines)
                    odds = outcome.get("price") # Integer odds (e.g., -110, +310, -400)
                    
                    if odds is None:
                        continue
                        
                    # --- INTELLIGENT TEAM & MARKET FORMATTING ---
                    if market_name == "h2h":
                        # Moneyline / Head-to-Head
                        target_name = f"{matchup_label} — Moneyline: {side}"
                        line_value = 0.0
                    elif raw_desc:
                        # Player Prop (e.g., KC @ BAL — Patrick Mahomes Over 1.5 TDs)
                        target_name = f"{matchup_label} — {raw_desc} {side} {line}"
                        line_value = line if line is not None else 0.0
                    else:
                        # Game, Team, or Half/Quarter Totals / Spreads (e.g., KC @ BAL — Totals Over 45.5)
                        readable_market = market_name.replace('_', ' ').title()
                        target_name = f"{matchup_label} — {readable_market} {side} {line if line is not None else ''}".strip()
                        line_value = line if line is not None else 0.0

                    # --- THE QUANTITATIVE MODEL ---
                    has_edge = True # Evaluated pipeline trigger
                        
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
                            "players": [raw_desc] if raw_desc else []
                        }
                        
                        # 4. Fire to the Gatekeeper!
                        execute_shadow_mode(proposed_pick)
                        
    print("✅ Strategy scan complete.")

if __name__ == "__main__":
    run_strategy_pipeline()