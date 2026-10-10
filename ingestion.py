import os
import requests
from dotenv import load_dotenv

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
        print(f"⚠️ Odds API Error (Games): {response.status_code} - {response.text}")
        return []

    def get_game_odds(self, event_id):
        # Queries core robust markets (h2h, spreads, totals) to avoid 422 unprocessable entity errors
        url = f"https://api.the-odds-api.com/v4/sports/americanfootball_nfl/events/{event_id}/odds?apiKey={self.odds_api_key}&regions=us&markets=h2h,spreads,totals&oddsFormat=american"
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        print(f"⚠️ Odds API Error (Odds for {event_id}): {response.status_code} - {response.text}")
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