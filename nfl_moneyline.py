"""Event-specific shadow moneylines. No real wagers are placed."""
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

log = logging.getLogger("ogbreeze.moneyline")
PREFIX = "oddsapi|"


def as_utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def valid_odds(value):
    try:
        number = float(value)
        return math.isfinite(number) and abs(number) >= 100
    except (TypeError, ValueError):
        return False


def grade_moneyline(game, team, odds, stake):
    """Return status, gross return, profit; None means not gradable."""
    if game.get("completed") is not True:
        return None

    try:
        home, away = game["home_team"], game["away_team"]
        items = game.get("scores")

        if home == away or team not in (home, away):
            return None
        if not isinstance(items, list) or len(items) != 2:
            return None

        scores = {item["name"]: int(item["score"]) for item in items}
        if set(scores) != {home, away} or min(scores.values()) < 0:
            return None
        if not valid_odds(odds):
            return None

        amount = Decimal(str(stake))
        if not amount.is_finite() or amount <= 0:
            return None

        if scores[home] == scores[away]:
            return ("REVIEW_REQUIRED", None, None)

        winner = home if scores[home] > scores[away] else away
        if team != winner:
            return ("LOST", 0.0, float(-amount))

        price = Decimal(str(odds))
        profit = amount * (
            price / Decimal("100")
            if price > 0 else Decimal("100") / abs(price)
        )
        profit = profit.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return ("WON", float(amount + profit), float(profit))

    except (KeyError, TypeError, ValueError, ArithmeticError):
        return None


def store_moneyline_picks(matchups):
    from db import SessionLocal, PickLog
    from sqlalchemy.exc import IntegrityError

    added = 0
    now = datetime.now(timezone.utc)

    with SessionLocal() as session:
        for matchup in matchups:
            event_id = matchup.get("event_id")
            team = matchup.get("home")
            odds = matchup.get("home_ml")
            kickoff_raw = matchup.get("commence_time")

            if not event_id or not team or not valid_odds(odds):
                continue

            try:
                kickoff = as_utc(kickoff_raw)
            except (TypeError, ValueError, AttributeError):
                log.warning("Skipping pick with invalid kickoff: %s", event_id)
                continue

            if kickoff <= now:
                continue

            key = f"{PREFIX}{event_id}|h2h|{team}"
            if session.query(PickLog.id).filter(
                PickLog.pick_key == key
            ).first():
                continue

            try:
                with session.begin_nested():
                    session.add(PickLog(
                        pick_key=key,
                        event_id=event_id,
                        market_key="h2h",
                        player_name=f"{team} (Moneyline)",
                        market_name=f"{matchup['away']} @ {team}",
                        pick_side=team,
                        kickoff_time=kickoff,
                        picked_odds=float(odds),
                        stake=50.0,
                        is_shadow=True,
                        status="ACTIVE",
                    ))
                    session.flush()
                added += 1

            except IntegrityError:
                # Another worker may have inserted this same selection.
                if not session.query(PickLog.id).filter(
                    PickLog.pick_key == key
                ).first():
                    raise

        session.commit()

    log.info("New event-specific shadow moneylines saved: %s", added)


def settle_moneyline_picks():
    from db import SessionLocal, PickLog
    import requests

    now = datetime.now(timezone.utc)

    with SessionLocal() as session:
        pending = session.query(PickLog.id).filter(
            PickLog.pick_key.startswith(PREFIX),
            PickLog.market_key.in_(["h2h", "spreads", "totals"]),
            PickLog.status.in_(["ACTIVE", "REVIEW_REQUIRED"]),
            PickLog.settled_at.is_(None),
            PickLog.kickoff_time <= now,
        ).first()

    if not pending:
        log.info("No started managed moneylines need settlement.")
        return

    key = os.getenv("ODDS_API_KEY")
    if not key:
        log.warning("Settlement skipped: ODDS_API_KEY is missing.")
        return

    try:
        response = requests.get(
            "https://api.the-odds-api.com/v4/sports/"
            "americanfootball_nfl/scores/",
            params={
                "apiKey": key,
                "daysFrom": 3,
                "dateFormat": "iso",
            },
            timeout=20,
        )

        log.info(
            "Scores API status: %s | credits remaining: %s",
            response.status_code,
            response.headers.get("x-requests-remaining"),
        )

        if response.status_code != 200:
            log.warning("Scores unavailable; outcomes unchanged.")
            return

        games = response.json()
        if not isinstance(games, list) or any(
            not isinstance(game, dict) for game in games
        ):
            raise ValueError("Invalid scores response")

    except (requests.RequestException, ValueError):
        # Do not log request URLs containing the API key.
        log.warning("Scores request failed; outcomes unchanged.")
        return

    by_id = {
        game["id"]: game
        for game in games
        if isinstance(game.get("id"), str)
    }

    settled = reviewed = 0

    with SessionLocal() as session:
        picks = session.query(PickLog).filter(
            PickLog.pick_key.startswith(PREFIX),
            PickLog.market_key.in_(["h2h", "spreads", "totals"]),
            PickLog.status.in_(["ACTIVE", "REVIEW_REQUIRED"]),
            PickLog.settled_at.is_(None),
            PickLog.kickoff_time <= now,
        ).all()

        for pick in picks:
            game = by_id.get(pick.event_id)

            if game is None:
                if as_utc(pick.kickoff_time) < now - timedelta(days=4):
                    pick.status = "REVIEW_REQUIRED"
                    pick.quarantine_reason = (
                        "Result missing from recent scores. "
                        "Check postponement or historical final result."
                    )
                    reviewed += 1
                continue

            # Keep revised kickoff times for postponed/rescheduled games.
            if game.get("commence_time"):
                try:
                    pick.kickoff_time = as_utc(game["commence_time"])
                except (TypeError, ValueError, AttributeError):
                    pass

            if game.get("completed") is not True:
                continue

            if (
                pick.market_key == "h2h"
                and pick.is_shadow
                and pick.stake is not None
                and pick.stake > 0
            ):
                result = grade_moneyline(
                    game, pick.pick_side, pick.picked_odds, pick.stake
                )
            else:
                from selection_tracker import grade_selection
                result = grade_selection(
                    game, pick.market_key, pick.pick_side, pick.picked_line
                )

            if result is None or result[0] == "REVIEW_REQUIRED":
                pick.status = "REVIEW_REQUIRED"
                pick.quarantine_reason = (
                    "Final score/pick invalid, or tied game. "
                    "Verify applicable grading rules."
                )
                reviewed += 1
                continue

            status, gross_return, profit = result

            # Settle once even if multiple workers attempt the update.
            changed = session.query(PickLog).filter(
                PickLog.id == pick.id,
                PickLog.status.in_(["ACTIVE", "REVIEW_REQUIRED"]),
                PickLog.settled_at.is_(None),
            ).update({
                "status": status,
                "realized_return": gross_return,
                "realized_profit": profit,
                "settled_at": now,
                "quarantine_reason": None,
            }, synchronize_session=False)

            settled += changed

        session.commit()

    log.info(
        "Moneyline settlement: %s settled; %s need review.",
        settled, reviewed,
    )
