from news_research import refresh_news_research
from matchup_research import save_matchup_research
from player_research import refresh_player_research
from research_data import refresh_team_research
from selection_tracker import track_ticket
from nfl_moneyline import store_moneyline_picks, settle_moneyline_picks
import os
import json
import logging
from datetime import datetime, timedelta, timezone

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
        "event_id": game.get("id"),
        "commence_time": game.get("commence_time"),
        "home": home_team,
        "away": away_team,
        "home_ml": 0,
        "total": 0,
        "total_odds": -110,
        "home_spread": 0,
        "home_spread_odds": -110,
        "away_ml": 0,
        "under_odds": -110,
        # ADDED: True only when the sportsbook actually sent that price (not the -110 backup)
        "total_odds_real": False,
        "home_spread_odds_real": False,
        "under_odds_real": False,
    }

    for market in bookmakers[0].get("markets", []):
        key = market.get("key")
        for outcome in market.get("outcomes", []):
            if key == "h2h" and outcome.get("name") == home_team:
                data["home_ml"] = outcome.get("price") or 0
            elif key == "totals" and outcome.get("name") == "Over":
                data["total"] = outcome.get("point") or 0
                data["total_odds"] = outcome.get("price", -110)
                data["total_odds_real"] = outcome.get("price") is not None
            elif key == "spreads" and outcome.get("name") == home_team:
                data["home_spread"] = outcome.get("point") or 0
                data["home_spread_odds"] = outcome.get("price", -110)
                data["home_spread_odds_real"] = outcome.get("price") is not None
            elif key == "h2h" and outcome.get("name") == away_team:
                data["away_ml"] = outcome.get("price") or 0
            elif key == "totals" and outcome.get("name") == "Under":
                data["under_odds"] = outcome.get("price", -110)
                data["under_odds_real"] = outcome.get("price") is not None
    return data


def store_straight_bets(matchups):
    store_moneyline_picks(matchups)


def build_parlay(matchups):
    heavy_favorites = sorted(
        [m for m in matchups if m["home_spread"] and m["home_spread"] < 0 and m["home_ml"]],
        key=lambda x: x["home_spread"],
    )
    high_totals = sorted([m for m in matchups if m["total"]], key=lambda x: x["total"], reverse=True)
    high_totals = [m for m in high_totals if m.get("total_odds_real")]  # ADDED: skip totals with no real price

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
        db.add(track_ticket(db, ParlaySlip(
            category="Standard Cap",
            odds=f"{multiplier}x (+{odds})" if odds > 0 else f"{multiplier}x ({odds})",
            stake="$50.00",
            payout=f"${50 * multiplier:.2f}",
            legs_json=json.dumps(legs),
            status="ACTIVE",
        ), matchups))
        db.commit()
        log.info("New parlay built and saved.")
    except Exception:
        db.rollback()
        log.exception("Error building parlay")
    finally:
        db.close()


# ==========================================
# ADDED: Booster Matrix, Bomb Target, Micro Sandbox
# (restored from commits 8ade376, 258a676, 7ef626b, 0ca6cf5)
# ==========================================
BOOSTER_STAKE = 25.0
BOOSTER_MIN_MULTIPLIER = 50.0            # $25 Booster must be 50x+
BOMB_STAKE_OPTIONS = [15.0, 20.0, 25.0]  # Bomb stake must be $15-$25
BOMB_MIN_PAYOUT = 1000.0                 # Bomb must return $1,000+
BOMB_TARGET_MULTIPLIER = BOMB_MIN_PAYOUT / max(BOMB_STAKE_OPTIONS)  # 40x clears $1,000 on $25
MAX_PARLAY_LEGS = 7
TIER_CATEGORIES = ["Booster Matrix", "Bomb Target", "Micro Sandbox"]


def odds_to_multiplier(american):
    dec = american_to_decimal(american)
    return round(dec, 1) if dec else 1.0


def format_parlay_odds(multiplier, american):
    return f"{multiplier}x (+{american})" if american > 0 else f"{multiplier}x ({american})"


def find_underdogs(matchups):
    """Plus-money moneylines, shortest price first."""
    dogs = []
    for m in matchups:
        for team, opp, ml in ((m["home"], m["away"], m.get("home_ml")), (m["away"], m["home"], m.get("away_ml"))):
            if ml and ml > 0:
                dogs.append({"team": team, "opponent": opp, "ml": ml,
                             "total": m["total"], "under_odds": m.get("under_odds", -110),
                             "under_odds_real": m.get("under_odds_real", False)})
    return sorted(dogs, key=lambda d: d["ml"])


def stack_underdogs(legs, odds_list, used_teams, underdogs, target_mult):
    """Add underdog moneylines until the parlay reaches target_mult (or MAX_PARLAY_LEGS)."""
    odds = calculate_parlay_odds(odds_list)
    mult = odds_to_multiplier(odds)
    for dog in underdogs:
        if mult >= target_mult or len(legs) >= MAX_PARLAY_LEGS:
            break
        if dog["team"] in used_teams:
            continue
        legs.append(f"{dog['team']} Moneyline (+{dog['ml']}) vs {dog['opponent']}")
        odds_list.append(dog["ml"])
        used_teams.update({dog["team"], dog["opponent"]})
        odds = calculate_parlay_odds(odds_list)
        mult = odds_to_multiplier(odds)
    return odds, mult


def micro_slip(legs, odds_list, stake, note):
    odds = calculate_parlay_odds(odds_list)
    if odds == 0:
        return None
    mult = odds_to_multiplier(odds)
    return ParlaySlip(
        category="Micro Sandbox",
        odds=format_parlay_odds(mult, odds),
        stake=f"${stake:.2f}",
        payout=f"${stake * mult:,.2f}",
        legs_json=json.dumps(legs + [f"Note: {note}"]),
        status="ACTIVE",
    )


def build_tier_parlays(matchups):
    heavy_favorites = sorted(
        [m for m in matchups if m["home_spread"] and m["home_spread"] < 0 and m["home_ml"]],
        key=lambda x: x["home_spread"],
    )
    high_totals = sorted([m for m in matchups if m["total"]], key=lambda x: x["total"], reverse=True)
    # Only use legs the sportsbook actually priced (no -110 backups)
    heavy_favorites = [m for m in heavy_favorites if m.get("home_spread_odds_real")]
    high_totals = [m for m in high_totals if m.get("total_odds_real")]
    underdogs = find_underdogs(matchups)

    if not heavy_favorites or not high_totals:
        log.info("Not enough data to build Booster / Bomb / Micro this round.")
        return

    fav = heavy_favorites[0]
    shootout = high_totals[0]
    slips = []

    # Booster Matrix: $25 stake, 50x+ (original 4 legs from 8ade376, topped up with underdogs)
    if len(heavy_favorites) > 1 and len(high_totals) > 1:
        fav2 = heavy_favorites[1]
        shoot2 = high_totals[1]
        b_legs = [
            f"{fav['home']} {fav['home_spread']} (Top Tier Matchup)",
            f"{fav2['home']} {fav2['home_spread']} (Secondary Edge)",
            f"Game Total: {shoot2['away']} @ {shoot2['home']} Over {shoot2['total']}",
        ]
        b_list = [fav["home_spread_odds"], fav2["home_spread_odds"], shoot2["total_odds"]]
        # Fade leg now uses the real live Under price for the favorite's game (skipped if not priced)
        if fav.get("under_odds_real") and fav["total"] and fav is not shoot2:
            b_legs.append(f"Fade: {fav['away']} @ {fav['home']} Under {fav['total']} ({fav['under_odds']})")
            b_list.append(fav["under_odds"])
        b_used = {fav["home"], fav["away"], fav2["home"], fav2["away"]}
        b_odds, b_mult = stack_underdogs(b_legs, b_list, b_used, underdogs, BOOSTER_MIN_MULTIPLIER)
        if b_mult >= BOOSTER_MIN_MULTIPLIER:
            slips.append(ParlaySlip(
                category="Booster Matrix",
                odds=format_parlay_odds(b_mult, b_odds),
                stake=f"${BOOSTER_STAKE:.2f}",
                payout=f"${BOOSTER_STAKE * b_mult:,.2f}",
                legs_json=json.dumps(b_legs),
                status="ACTIVE",
            ))
        else:
            slips.append(micro_slip(b_legs, b_list, BOOSTER_STAKE,
                                    f"Booster only reached {b_mult}x (needs {BOOSTER_MIN_MULTIPLIER:.0f}x+)"))

    # Bomb Target: $15-$25 stake, $1,000+ payout (rules from 258a676)
    bomb_legs = [
        f"{fav['home']} {fav['home_spread']} (Bomb Anchor)",
        f"Game Total: {shootout['away']} @ {shootout['home']} Over {shootout['total']}",
    ]
    bomb_list = [fav["home_spread_odds"], shootout["total_odds"]]
    bomb_used = {fav["home"], fav["away"], shootout["home"], shootout["away"]}
    bomb_odds, bomb_mult = stack_underdogs(bomb_legs, bomb_list, bomb_used, underdogs, BOMB_TARGET_MULTIPLIER)
    bomb_stake = next((s for s in BOMB_STAKE_OPTIONS if s * bomb_mult >= BOMB_MIN_PAYOUT), None)
    if bomb_stake:
        slips.append(ParlaySlip(
            category="Bomb Target",
            odds=format_parlay_odds(bomb_mult, bomb_odds),
            stake=f"${bomb_stake:.2f}",
            payout=f"${bomb_stake * bomb_mult:,.2f}",
            legs_json=json.dumps(bomb_legs),
            status="ACTIVE",
        ))
    else:
        slips.append(micro_slip(bomb_legs, bomb_list, BOMB_STAKE_OPTIONS[-1],
                                f"Bomb only reached {bomb_mult}x (needs ${BOMB_MIN_PAYOUT:,.0f}+ on $25)"))

    # Micro Sandbox: small 2-leg tickets, $10-$15 stakes (sub-threshold logic from 7ef626b / 0ca6cf5)
    if fav.get("total_odds_real") and fav["total"]:
        slips.append(micro_slip(
            [f"Micro 2-Leg: {fav['home']} Moneyline ({fav['home_ml']})",
             f"{fav['away']} @ {fav['home']} Over {fav['total']}"],
            [fav["home_ml"], fav["total_odds"]], 15.0, "Micro favorite + Over"))
    if len(heavy_favorites) > 1 and heavy_favorites[1].get("under_odds_real"):
        fav2 = heavy_favorites[1]
        slips.append(micro_slip(
            [f"Spread 2-Leg: {fav2['home']} {fav2['home_spread']}",
             f"{fav2['away']} @ {fav2['home']} Under {fav2['total']}"],
            [fav2["home_spread_odds"], fav2.get("under_odds", -110)], 10.0, "Micro spread + Under"))
    real_under_dogs = [d for d in underdogs if d["under_odds_real"]]
    if real_under_dogs:
        dog = real_under_dogs[0]
        slips.append(micro_slip(
            [f"Underdog Micro: {dog['team']} Moneyline (+{dog['ml']})",
             f"{dog['team']} vs {dog['opponent']} Under {dog['total']}"],
            [dog["ml"], dog["under_odds"]], 10.0, "Micro underdog + Under"))

    db = SessionLocal()
    try:
        # Only archive the old Booster / Bomb / Micro rows. Standard Cap is handled by build_parlay().
        db.query(ParlaySlip).filter(
            ParlaySlip.status == "ACTIVE", ParlaySlip.category.in_(TIER_CATEGORIES)
        ).update({"status": "ARCHIVED"}, synchronize_session=False)
        for slip in slips:
            if slip is not None:
                db.add(track_ticket(db, slip, matchups))
        db.commit()
        log.info("Booster / Bomb / Micro slips built and saved: %s", sum(1 for x in slips if x))
    except Exception:
        db.rollback()
        log.exception("Error building Booster / Bomb / Micro slips")
    finally:
        db.close()


def filter_upcoming_games(games, now=None):
    """Keep games starting strictly after now and within seven days."""
    now = now or datetime.now(timezone.utc)
    cutoff = now + timedelta(days=7)
    upcoming = []
    for game in games:
        try:
            kickoff = datetime.fromisoformat(game["commence_time"].replace("Z", "+00:00"))
            if kickoff.tzinfo is None:
                raise ValueError("Kickoff timestamp has no timezone")
        except (KeyError, TypeError, ValueError, AttributeError):
            log.warning("Skipping game with invalid kickoff: %s", game.get("id"))
            continue
        if now < kickoff <= cutoff:
            upcoming.append(game)
    return upcoming


def fetch_and_store_live_data():
    from db import init_db
    init_db()
    log.info("Starting data ingestion...")
    try:
        settle_moneyline_picks()
    except Exception:
        log.exception("Moneyline settlement failed; continuing ingestion")
    try:
        refresh_team_research()
        refresh_player_research()
    except Exception:
        log.exception("Research collection failed; existing engine unchanged")

    try:
        refresh_news_research()
    except Exception:
        log.exception("News collection failed; existing engine unchanged")

    games = SportsDataAPI().get_upcoming_nfl_games()

    if not games:
        log.warning("No games fetched. Skipping update to keep existing data.")
        return

    games = filter_upcoming_games(games)
    if not games:
        log.info("No games starting within the next seven days. Keeping existing data.")
        return

    matchups = [m for m in (parse_game(g) for g in games) if m]
    log.info("Games with bookmaker data: %s", len(matchups))

    try:
        save_matchup_research(matchups)
    except Exception:
        log.exception("Matchup research failed; existing engine unchanged")

    store_straight_bets(matchups)
    build_parlay(matchups)
    build_tier_parlays(matchups)
    log.info("Ingestion finished.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    fetch_and_store_live_data()