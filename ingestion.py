import os
import requests
from dotenv import load_dotenv

from db import SessionLocal, PickLog, ParlaySlip

load_dotenv()

class SportsDataAPI:
    def __init__(self):
        self.odds_api_key = os.getenv("ODDS_API_KEY")
        self.rapidapi_key = os.getenv("RAPIDAPI_KEY")
        
    def get_upcoming_nfl_games(self):
        url = f"https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds/?apiKey={self.odds_api_key}&regions=us&markets=h2h,spreads,totals&oddsFormat=american"
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        print(f"⚠️ Odds API Error (Games): {response.status_code}\n{response.text}")
        return []

# NEW MATH FUNCTION: American Odds -> Decimal -> Parlay Multiplier -> American Odds
def calculate_parlay_odds(american_odds_list):
    if not american_odds_list:
        return 0
        
    decimal_multiplier = 1.0
    for odds in american_odds_list:
        # Convert American odds to Decimal multiplier
        if odds > 0:
            decimal_odds = (odds / 100.0) + 1.0
        elif odds < 0:
            decimal_odds = (100.0 / abs(odds)) + 1.0
        else:
            continue
        decimal_multiplier *= decimal_odds
    
    # Convert final Decimal multiplier back to American Odds
    if decimal_multiplier >= 2.0:
        final_american = (decimal_multiplier - 1.0) * 100.0
    else:
        final_american = -100.0 / (decimal_multiplier - 1.0)
        
    return int(round(final_american))


def fetch_and_store_live_data():
    print("Starting data ingestion and multiplex parlay engine...")
    api = SportsDataAPI()
    
    games = api.get_upcoming_nfl_games()
    if not games:
        print("No games fetched. Exiting ingestion.")
        return

    matchups = []
    for game in games:
        away_team = game.get('away_team')
        home_team = game.get('home_team')
        bookmakers = game.get('bookmakers', [])
        
        if not bookmakers:
            continue
            
        first_book = bookmakers[0]
        home_ml = 0
        away_ml = 0
        total_over = 0
        total_odds = -110 # Standard juice
        home_spread = 0
        home_spread_odds = -110
        
        for market in first_book.get('markets', []):
            if market.get('key') == 'h2h':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == home_team:
                        home_ml = outcome.get('price')
                    else:
                        away_ml = outcome.get('price')
            elif market.get('key') == 'totals':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == 'Over':
                        total_over = outcome.get('point')
                        total_odds = outcome.get('price', -110)
            elif market.get('key') == 'spreads':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == home_team:
                        home_spread = outcome.get('point')
                        home_spread_odds = outcome.get('price', -110)

        matchups.append({
            "home": home_team,
            "away": away_team,
            "home_ml": home_ml,
            "away_ml": away_ml,
            "total": total_over,
            "total_odds": total_odds,
            "home_spread": home_spread,
            "home_spread_odds": home_spread_odds
        })

    # Sort games
    heavy_home_favorites = sorted([m for m in matchups if m['home_spread'] and m['home_spread'] < 0], key=lambda x: x['home_spread'])
    high_totals = sorted([m for m in matchups if m['total']], key=lambda x: x['total'], reverse=True)

    if not heavy_home_favorites or not high_totals:
        print("Not enough odds data to build parlays yet.")
        return

    db = SessionLocal()
    
    try:
        db.query(ParlaySlip).delete()

        # Engine 1: Standard Realistic
        fav_game = heavy_home_favorites[0]
        shootout_game = high_totals[0]
        
        s_odds = calculate_parlay_odds([fav_game['home_ml'], shootout_game['total_odds']])
        s_multiplier = round((s_odds / 100.0) + 1.0 if s_odds > 0 else (100.0 / abs(s_odds)) + 1.0, 1)
        
        standard_parlay = ParlaySlip(
            category="Standard Cap",
            odds=f"{s_multiplier}x (+{s_odds})" if s_odds > 0 else f"{s_multiplier}x ({s_odds})",
            stake="$50.00",
            payout=f"${(50 * s_multiplier):.2f}",
            legs=[
                f"{fav_game['home']} Moneyline ({fav_game['home_ml']})",
                f"Game Total: {shootout_game['away']} @ {shootout_game['home']} Over {shootout_game['total']}",
                f"Game Script: {fav_game['away']} @ {fav_game['home']} - Expected Domination"
            ]
        )
        db.add(standard_parlay)

        # Engine 2: Booster Matrix
        if len(heavy_home_favorites) > 1 and len(high_totals) > 1:
            fav2 = heavy_home_favorites[1]
            shoot2 = high_totals[1]
            
            # Using -110 as standard juice for the team total fade
            b_odds = calculate_parlay_odds([fav_game['home_spread_odds'], fav2['home_spread_odds'], shoot2['total_odds'], -110])
            b_multiplier = round((b_odds / 100.0) + 1.0 if b_odds > 0 else (100.0 / abs(b_odds)) + 1.0, 1)
            
            booster_parlay = ParlaySlip(
                category="Booster Matrix",
                odds=f"{b_multiplier}x (+{b_odds})" if b_odds > 0 else f"{b_multiplier}x ({b_odds})",
                stake="$25.00",
                payout=f"${(25 * b_multiplier):.2f}",
                legs=[
                    f"{fav_game['home']} {fav_game['home_spread']} (Top Tier Matchup)",
                    f"{fav2['home']} {fav2['home_spread']} (Secondary Edge)",
                    f"Game Total: {shoot2['away']} @ {shoot2['home']} Over {shoot2['total']}",
                    f"Fade: {fav_game['away']} Team Total Under"
                ]
            )
            db.add(booster_parlay)

        db.commit()
        print("Successfully built dynamic parlays with exact math and saved to database!")
        
    except Exception as e:
        db.rollback()
        print(f"Database error during ingestion: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    fetch_and_store_live_data()