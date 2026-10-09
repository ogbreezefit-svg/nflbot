import os
import requests
from journal_engine import log_bet, log_system_event
from notifier import send_discord_alert
from injury_scraper import evaluate_team_health

ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "82dc7af21b915e1ca03b2b52118f9f13")
SHARP_BOOK = "pinnacle"
RETAIL_BOOKS = ["draftkings", "fanduel", "betmgm"]
MINIMUM_EDGE = 0.035

def run_master_scan():
    log_system_event("Master Bot: Initiating scheduled odds sweep & edge calculation...")
    url = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "h2h,spreads",
        "oddsFormat": "decimal",
        "bookmakers": f"{SHARP_BOOK},draftkings,fanduel,betmgm"
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            games = response.json()
            log_system_event(f"Data Feed Connected: Evaluated {len(games)} live NFL matchups.")
            
            for game in games:
                home = game.get('home_team')
                away = game.get('away_team')
                
                # Apply Injury Veto Shield
                if evaluate_team_health(home) == "CRITICAL_QB_OUT" or evaluate_team_health(away) == "CRITICAL_QB_OUT":
                    log_system_event(f"Veto Triggered: Skipped {away} @ {home} due to critical injury.")
                    continue
                
                books = game.get('bookmakers', [])
                sharp_home, retail_best, best_book = 0.0, 0.0, ""
                
                for book in books:
                    b_key = book.get('key')
                    for market in book.get('markets', []):
                        if market.get('key') == 'h2h':
                            for outcome in market.get('outcomes', []):
                                if outcome.get('name') == home:
                                    price = outcome.get('price', 0.0)
                                    if b_key == SHARP_BOOK:
                                        sharp_home = price
                                    elif b_key in RETAIL_BOOKS and price > retail_best:
                                        retail_best = price
                                        best_book = book.get('title', 'Retail Book')

                if sharp_home > 0 and retail_best > 0:
                    true_prob = 1.0 / sharp_home
                    retail_prob = 1.0 / retail_best
                    edge = true_prob - retail_prob
                    
                    if edge >= MINIMUM_EDGE:
                        edge_pct = round(edge * 100, 1)
                        desc = f"Straight Bet: {home} ML @ {retail_best}x on {best_book} (+{edge_pct}% Edge)"
                        log_bet("Straight Edge Pick", desc, 50.0, round(50.0 * retail_best, 2))
                        send_discord_alert("Mathematical Edge Found!", desc, [
                            {"name": "Matchup", "value": f"{away} @ {home}", "inline": True},
                            {"name": "Edge Discrepancy", "value": f"+{edge_pct}%", "inline": True}
                        ])
        else:
            log_system_event(f"API Warning: Status code {response.status_code}")
    except Exception as e:
        log_system_event(f"Master Bot Error: {str(e)}")