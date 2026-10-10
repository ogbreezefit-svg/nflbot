import requests
import os

class SportsDataAPI:
    def __init__(self):
        self.sleeper_cache = {}
        self.tank_key = os.getenv("RAPIDAPI_KEY")
        self.odds_key = os.getenv("ODDS_API_KEY")
        
    def get_sleeper_players(self):
        """Fetches Sleeper NFL players dict. Keys are player_ids, values are player profiles."""
        if not self.sleeper_cache:
            url = "https://api.sleeper.app/v1/players/nfl"
            response = requests.get(url)
            response.raise_for_status()
            self.sleeper_cache = response.json()
        return self.sleeper_cache

    def get_tank01_stats(self, year="2026"):
        """Fetches live team stats and PPG from Tank01"""
        url = "https://tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com/getNFLTeams"
        headers = {
            "x-rapidapi-host": "tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com",
            "x-rapidapi-key": self.tank_key
        }
        params = {"teamStats": "true", "teamStatsSeason": year, "rosters": "false"}
        response = requests.get(url, headers=headers, params=params)
        return response.json().get("body", [])

    def get_player_props(self, event_id):
        """Pulls DraftKings & Pinnacle prop lines from The Odds API"""
        url = f"https://api.the-odds-api.com/v4/sports/americanfootball_nfl/events/{event_id}/odds"
        params = {
            "apiKey": self.odds_key,
            "regions": "us,eu",
            "markets": "player_pass_tds,player_pass_yds,player_rush_yds",
            "bookmakers": "draftkings,pinnacle"
        }
        response = requests.get(url, params=params)
        return response.json()
    def get_upcoming_nfl_games(self):
        """Fetches all upcoming NFL games and their event IDs from The Odds API."""
        url = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/events"
        params = {
            "apiKey": self.odds_key
        }
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Failed to fetch NFL schedule: {e}")
            return []