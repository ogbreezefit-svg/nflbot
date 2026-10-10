import os
import requests
from dotenv import load_dotenv

# 1. Import your database components
from db import SessionLocal, PickLog

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

    def get_game_odds(self, event_id):
        url = f"https://api.the-odds-api.com/v4/sports/americanfootball_nfl/events/{event_id}/odds?apiKey={self.odds_api_key}&regions=us&markets=h2h,spreads,totals&oddsFormat=american"
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        print(f"⚠️ Odds API Error (Odds for {event_id}): {response.status_code}\n{response.text}")
        return {"bookmakers": []}

    def get_sleeper_players(self):
        url = "https://api.sleeper.app/v1/players/nfl"
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        return {}

    def get_tank01_stats(self, season="2026"):
        url = f"https://tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com/getNFLTeamStats?season={season}"
        headers = {
            "X-RapidAPI-Key": self.rapidapi_key,
            "X-RapidAPI-Host": "tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com"
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json().get("body", {})
        return {}


# 2. Create the pipeline function to save data to the database
def fetch_and_store_live_data():
    print("Starting data ingestion...")
    api = SportsDataAPI()
    
    # Fetch live games
    games = api.get_upcoming_nfl_games()
    
    if not games:
        print("No games fetched. Exiting ingestion.")
        return

    # Open a database session
    db = SessionLocal()
    
    try:
        # Example processing: Extracting Moneyline (h2h) odds and saving to PickLog
        # You can expand this logic to calculate your specific 'edges' and parlays
        for game in games:
            home_team = game.get('home_team')
            away_team = game.get('away_team')
            
            bookmakers = game.get('bookmakers', [])
            if not bookmakers:
                continue
                
            # Use the first bookmaker (usually DraftKings/FanDuel depending on your API region settings)
            first_book = bookmakers[0]
            
            for market in first_book.get('markets', []):
                if market.get('key') == 'h2h':
                    for outcome in market.get('outcomes', []):
                        team = outcome.get('name')
                        price = outcome.get('price')
                        
                        # Create a new PickLog entry
                        new_pick = PickLog(
                            player_name=f"{team} (Moneyline)", 
                            market_name=f"{away_team} @ {home_team}",
                            status="ACTIVE",
                            picked_odds=f"{price}"
                        )
                        db.add(new_pick)
        
        # Commit all new picks to the database at once
        db.commit()
        print("Successfully saved live odds to the database!")
        
    except Exception as e:
        db.rollback()
        print(f"Database error during ingestion: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    # 3. Allow the script to run standalone
    fetch_and_store_live_data()
    