import os
import requests
from datetime import datetime, timezone
from db import SessionLocal, PickLog

class Tank01SettlementEngine:
    def __init__(self):
        self.api_key = os.getenv("RAPIDAPI_KEY")
        self.host = "tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com"
        self.headers = {
            "x-rapidapi-host": self.host,
            "x-rapidapi-key": self.api_key
        }

    def get_game_boxscore(self, game_id: str) -> dict:
        """Fetches box score from Tank01 for a given game ID."""
        url = f"https://{self.host}/getNFLBoxScore"
        params = {"gameID": game_id, "playByPlay": "false", "fantasyPoints": "false"}
        try:
            res = requests.get(url, headers=self.headers, params=params, timeout=10)
            res.raise_for_status()
            return res.json().get("body", {})
        except Exception as e:
            print(f"Error fetching boxscore for game {game_id}: {e}")
            return {}

    def grade_player_prop(self, market: str, line: float, side: str, player_stats: dict) -> str:
        """Maps prop market key to actual box score stat and compares against line."""
        stat_map = {
            "player_pass_yds": ("Passing", "passYds"),
            "player_pass_tds": ("Passing", "passTD"),
            "player_rush_yds": ("Rushing", "rushYds"),
            "player_rec_yds": ("Receiving", "recYds")
        }

        if market not in stat_map:
            return "UNRESOLVED"

        category, stat_key = stat_map[market]
        category_stats = player_stats.get(category, {})
        
        try:
            actual_val = float(category_stats.get(stat_key, 0.0))
        except (ValueError, TypeError):
            actual_val = 0.0

        if side.upper() == "OVER":
            if actual_val > line:
                return "WON"
            elif actual_val < line:
                return "LOST"
            return "PUSH"
        elif side.upper() == "UNDER":
            if actual_val < line:
                return "WON"
            elif actual_val > line:
                return "LOST"
            return "PUSH"

        return "UNRESOLVED"

    def grade_total_or_spread(self, market: str, side: str, line: float, home_score: int, away_score: int, is_home: bool) -> str:
        """Grades Game Totals (Over/Under) and Point Spreads."""
        if market == "totals":
            total_points = home_score + away_score
            if side.upper() == "OVER":
                return "WON" if total_points > line else ("LOST" if total_points < line else "PUSH")
            elif side.upper() == "UNDER":
                return "WON" if total_points < line else ("LOST" if total_points > line else "PUSH")

        elif market == "spreads":
            team_score = home_score if is_home else away_score
            opp_score = away_score if is_home else home_score
            adjusted_score = team_score + line

            if adjusted_score > opp_score:
                return "WON"
            elif adjusted_score < opp_score:
                return "LOST"
            return "PUSH"

        return "UNRESOLVED"


def settle_completed_picks():
    session = SessionLocal()
    engine = Tank01SettlementEngine()
    now = datetime.now(timezone.utc)

    # Grab active picks whose kickoff was > 4 hours ago
    pending_picks = session.query(PickLog).filter(
        PickLog.status == "ACTIVE",
        PickLog.kickoff_time <= now
    ).all()

    if not pending_picks:
        print("⚡ Settlement Engine: No active bets currently pending settlement.")
        session.close()
        return

    print(f"🔍 Processing {len(pending_picks)} pending pick(s) for settlement...")

    for pick in pending_picks:
        boxscore = engine.get_game_boxscore(pick.event_id)
        if not boxscore:
            continue

        # Confirm the game has actually concluded
        game_status = boxscore.get("gameStatus", "")
        if "Final" not in game_status and game_status != "Completed":
            print(f"Game {pick.event_id} status is '{game_status}'. Skipping until finished.")
            continue

        home_score = int(boxscore.get("homeScore", 0))
        away_score = int(boxscore.get("awayScore", 0))
        outcome = "UNRESOLVED"

        # 1. Player Props Grading
        if pick.market_name.startswith("player_"):
            player_stats = {}
            all_player_stats = boxscore.get("playerStats", {})

            # Search home and away roster payloads for the target player
            for team_key in ["home", "away"]:
                for pid, pdata in all_player_stats.get(team_key, {}).items():
                    if pdata.get("longName", "").lower() == (pick.player_name or "").lower():
                        player_stats = pdata
                        break
                if player_stats:
                    break

            if player_stats:
                outcome = engine.grade_player_prop(
                    market=pick.market_name,
                    line=pick.picked_line,
                    side=pick.pick_side,
                    player_stats=player_stats
                )
        # 2. Spread & Total Lines Grading
        else:
            is_home = (pick.pick_side == boxscore.get("homeTeam", ""))
            outcome = engine.grade_total_or_spread(
                market=pick.market_name,
                side=pick.pick_side,
                line=pick.picked_line,
                home_score=home_score,
                away_score=away_score,
                is_home=is_home
            )

        if outcome in ["WON", "LOST", "PUSH"]:
            pick.status = outcome
            print(f"✅ Pick ID {pick.id} ({pick.player_name or pick.pick_side}) settled as: {outcome}")

    session.commit()
    session.close()

if __name__ == "__main__":
    settle_completed_picks()