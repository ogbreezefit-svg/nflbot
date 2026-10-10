import os
import json
import logging

import requests
from dotenv import load_dotenv

from db import SessionLocal, PickLog, ParlaySlip

load_dotenv()
log = logging.getLogger("ogbreeze.ingestion")


class SportsDataAPI:
    def __init__(self):
        self.odds_api_key = os.getenv("ODDS_API_KEY")

    def get_upcoming_nfl_games(self):
        if not self.odds_api_key:
            log.error("ODDS_API_KEY is NOT SET in this environment. Add it in your host's Variables tab.")
            return []

        url = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds/"
        params = {
            "apiKey": self.odds_api_key,
            "regions": "us",
            "markets": "h2h,spreads,totals",
            "oddsFormat": "american",
        }
        try:
            response = requests.get(url, params=params, timeout=20)
        except Exception:
            log.exception("Could not reach the Odds API")
            return []

        remaining = response.headers.get("x-requests-remaining")
        log.info("Odds API status: %s | credits remaining: %s", response.status_code, remaining)

        if response.status_code == 200:
            games = response.json()
            log.info("Games returned: %s", len(games))
            return games

        log.error("Odds API error %s: %s", response.status_code, response.text)
        return []


def american_to_decimal(odds):
    if odds is None or odds == 0:
        return None
    if odds > 0:
        return (odds / 100.0) + 1.0
    return (100.0 / abs(odds)) + 1.0


def calculate_parlay_odds(american_odds_list):
    """Combine several American odds into one parlay American price."""
    multiplier = 1.0
    used = 0
    for odds in american_odds_list:
        dec = american_to_decimal(odds)
        if dec is None:
            continue
        multiplier *= dec
        used += 1

    if used == 0 or multiplier <= 1.0:
        return 0
    if multiplier >= 2.0:
        return int(round((multiplier - 1.0) * 100.0))
    return int(round(-100.0 / (multiplier - 1.0)))


def parse_game(game):
    """Pull the numbers we need out of one game, using the first bookmaker."""
    bookmakers = game.get("bookmakers", [])
    if not bookmakers:
        return None

    home_team = game.get("home_team")
    away_team = game.get("away_team")
    data = {
        "home": home_team,
        "away": away_team,
        "home_ml": 0,
        "total": 0,
        "total_odds": -110,
        "home_spread": 0,
        "home_spread_odds": -110,
    }

    for market in bookmakers[0].get("markets", []):
        key = market.get("key")
        for outcome in market.get("outcomes", []):
            if key == "h2h" and outcome.get("name") == home_team:
                data["home_ml"] = outcome.get("price") or 0
            elif key == "totals" and outcome.get("name") == "Over":
                data["total"] = outcome.get("point") or 0
                data["total_odds"] = outcome.get("price", -110)
            elif key == "spreads" and outcome.get("name") == home_team:
                data["home_spread"] = outcome.get("point") or 0
                data["home_spread_odds"] = outcome.get("price", -110)
    return data


def store_straight_bets(matchups):
    db = SessionLocal()
    added = 0
    try:
        for m in matchups:
            if not m["home_ml"]:
                continue
            name = f"{m['home']} (Moneyline)"
            existing = db.query(PickLog).filter_by(player_name=name, status="ACTIVE").first()
            if existing:
                continue
            db.add(PickLog(
                player_name=name,
                market_name=f"{m['away']} @ {m['home']}",
                status="ACTIVE",
                picked_odds=m["home_ml"],
            ))
            added += 1
        db.commit()
        log.info("Straight bets saved. New picks added: %s", added)
    except Exception:
        db.rollback()
        log.exception("Error saving straight bets")
    finally:
        db.close()


def build_parlay(matchups):
    heavy_favorites = sorted(
        [m for m in matchups if m["home_spread"] and m["home_spread"] < 0 and m["home_ml"]],
        key=lambda x: x["home_spread"],
    )
    high_totals = sorted([m for m in matchups if m["total"]], key=lambda x: x["total"], reverse=True)

    if not heavy_favorites or not high_totals:
        log.info("Not enough data to build a parlay this round.")
        return

    fav = heavy_favorites[0]
    shootout = high_totals[0]

    odds = calculate_parlay_odds([fav["home_ml"], shootout["total_odds"]])
    if odds == 0:
        log.warning("Parlay odds came out as 0. Skipping parlay.")
        return

    multiplier = round((odds / 100.0) + 1.0 if odds > 0 else (100.0 / abs(odds)) + 1.0, 1)

    legs = [
        f"{fav['home']} Moneyline ({fav['home_ml']})",
        f"Game Total: {shootout['away']} @ {shootout['home']} Over {shootout['total']}",
        f"Game Script: {fav['away']} @ {fav['home']} - Expected High-Pace Dominance",
    ]

    db = SessionLocal()
    try:
        db.query(ParlaySlip).filter(ParlaySlip.status == "ACTIVE").update({"status": "ARCHIVED"})
        db.add(ParlaySlip(
            category="Standard Cap",
            odds=f"{multiplier}x (+{odds})" if odds > 0 else f"{multiplier}x ({odds})",
            stake="$50.00",
            payout=f"${50 * multiplier:.2f}",
            legs_json=json.dumps(legs),
            status="ACTIVE",
        ))
        db.commit()
        log.info("New parlay built and saved.")
    except Exception:
        db.rollback()
        log.exception("Error building parlay")
    finally:
        db.close()


def fetch_and_store_live_data():
    log.info("Starting data ingestion...")
    games = SportsDataAPI().get_upcoming_nfl_games()

    if not games:
        log.warning("No games fetched. Skipping update to keep existing data.")
        return

    matchups = [m for m in (parse_game(g) for g in games) if m]
    log.info("Games with bookmaker data: %s", len(matchups))

    store_straight_bets(matchups)
    build_parlay(matchups)
    log.info("Ingestion finished.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    fetch_and_store_live_data()