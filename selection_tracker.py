"""Track actual selections without inventing standalone parlay stakes."""
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal

log = logging.getLogger("ogbreeze.selections")


def selection_key(event_id, market, side, line=None):
    if market == "h2h":
        return f"oddsapi|{event_id}|h2h|{side}"
    number = Decimal(str(line))
    if not number.is_finite():
        raise ValueError("Invalid selection line")
    # Normalize numerically equivalent lines, including negative zero.
    text = "0" if number == 0 else format(number.normalize(), "f")
    return f"oddsapi|{event_id}|{market}|{side}|{text}"


def grade_selection(game, market, side, line=None):
    """Grade a selection only; return no financial results."""
    if game.get("completed") is not True:
        return None

    try:
        home, away = game["home_team"], game["away_team"]
        items = game.get("scores")
        if home == away or not isinstance(items, list) or len(items) != 2:
            return None

        scores = {item["name"]: int(item["score"]) for item in items}
        if set(scores) != {home, away} or min(scores.values()) < 0:
            return None

        if market == "h2h":
            if side not in (home, away):
                return None
            if scores[home] == scores[away]:
                return ("REVIEW_REQUIRED", None, None)
            winner = home if scores[home] > scores[away] else away
            return ("WON" if side == winner else "LOST", None, None)

        number = Decimal(str(line))
        if not number.is_finite():
            return None

        if market == "spreads":
            if side not in (home, away):
                return None
            opponent = away if side == home else home
            difference = Decimal(scores[side] - scores[opponent]) + number

        elif market == "totals":
            if side not in ("OVER", "UNDER"):
                return None
            difference = Decimal(scores[home] + scores[away]) - number
            if side == "UNDER":
                difference = -difference

        else:
            return None

        status = "WON" if difference > 0 else (
            "LOST" if difference < 0 else "PUSH"
        )
        return (status, None, None)

    except (KeyError, TypeError, ValueError, ArithmeticError):
        return None


def candidate_labels(matchups):
    """Map the existing builders' exact labels to structured selections."""
    registry = {}

    def add(label, matchup, market, side, line=None, odds=None):
        candidate = {
            "matchup": matchup,
            "market": market,
            "side": side,
            "line": line,
            "odds": odds,
        }
        registry.setdefault(label, []).append(candidate)

    for m in matchups:
        home, away = m["home"], m["away"]

        for team, opponent, price in [
            (home, away, m.get("home_ml")),
            (away, home, m.get("away_ml")),
        ]:
            if not price:
                continue
            add(
                f"{team} Moneyline ({price})",
                m, "h2h", team, odds=price,
            )
            add(
                f"Micro 2-Leg: {team} Moneyline ({price})",
                m, "h2h", team, odds=price,
            )
            if price > 0:
                add(
                    f"{team} Moneyline (+{price}) vs {opponent}",
                    m, "h2h", team, odds=price,
                )
                add(
                    f"Underdog Micro: {team} Moneyline (+{price})",
                    m, "h2h", team, odds=price,
                )

        spread = m.get("home_spread")
        if m.get("home_spread_odds_real"):
            for suffix in [
                "Top Tier Matchup", "Secondary Edge", "Bomb Anchor"
            ]:
                add(
                    f"{home} {spread} ({suffix})",
                    m, "spreads", home, spread,
                    m.get("home_spread_odds"),
                )
            add(
                f"Spread 2-Leg: {home} {spread}",
                m, "spreads", home, spread,
                m.get("home_spread_odds"),
            )

        total = m.get("total")
        if total and m.get("total_odds_real"):
            for label in [
                f"Game Total: {away} @ {home} Over {total}",
                f"{away} @ {home} Over {total}",
            ]:
                add(
                    label, m, "totals", "OVER", total,
                    m.get("total_odds"),
                )

        if total and m.get("under_odds_real"):
            for label in [
                f"Fade: {away} @ {home} Under {total} ({m.get('under_odds')})",
                f"{away} @ {home} Under {total}",
                f"{home} vs {away} Under {total}",
                f"{away} vs {home} Under {total}",
            ]:
                add(
                    label, m, "totals", "UNDER", total,
                    m.get("under_odds"),
                )

    return registry


def track_ticket(session, slip, matchups):
    """Save ticket membership and ticket-specific prices atomically."""
    from db import PickLog, ParlayLeg
    from nfl_moneyline import as_utc, valid_odds
    from sqlalchemy.exc import IntegrityError

    labels = json.loads(slip.legs_json or "[]")
    if not isinstance(labels, list):
        raise ValueError("Ticket legs must be a list")

    registry = candidate_labels(matchups)
    now = datetime.now(timezone.utc)
    resolved = []
    seen = set()

    # Validate all selections before writing any ticket or leg.
    for label in labels:
        if not isinstance(label, str):
            raise ValueError("Unsupported non-text leg")
        if label.startswith(("Note:", "Game Script:")):
            continue

        candidates = registry.get(label, [])
        if len(candidates) != 1:
            raise ValueError(f"Unmatched or ambiguous leg: {label}")

        item = candidates[0]
        matchup = item["matchup"]
        event_id = matchup.get("event_id")
        if not event_id or not valid_odds(item["odds"]):
            raise ValueError(f"Missing event or valid price: {label}")

        kickoff = as_utc(matchup.get("commence_time"))
        if kickoff <= now:
            raise ValueError(f"Game already started: {label}")

        key = selection_key(
            event_id, item["market"], item["side"], item["line"]
        )
        if key in seen:
            raise ValueError(f"Duplicate selection in ticket: {label}")
        seen.add(key)
        resolved.append((label, item, kickoff, key))

    if len(resolved) < 2:
        raise ValueError("A parlay requires at least two actual selections")

    session.add(slip)
    session.flush()

    if session.query(ParlayLeg.id).filter(
        ParlayLeg.ticket_id == slip.id
    ).first():
        raise ValueError("Ticket already has linked legs")

    for position, (label, item, kickoff, key) in enumerate(resolved, 1):
        matchup = item["matchup"]
        pick = session.query(PickLog).filter(
            PickLog.pick_key == key
        ).first()

        if pick is None:
            try:
                with session.begin_nested():
                    pick = PickLog(
                        pick_key=key,
                        event_id=matchup["event_id"],
                        market_key=item["market"],
                        market_name=f"{matchup['away']} @ {matchup['home']}",
                        player_name=label,
                        pick_side=item["side"],
                        picked_line=item["line"],
                        picked_odds=float(item["odds"]),
                        kickoff_time=kickoff,
                        status="ACTIVE",
                        stake=0.0,
                        is_shadow=False,
                    )
                    session.add(pick)
                    session.flush()
            except IntegrityError:
                pick = session.query(PickLog).filter(
                    PickLog.pick_key == key
                ).first()
                if pick is None:
                    raise

        session.add(ParlayLeg(
            ticket_id=slip.id,
            pick_id=pick.id,
            position=position,
            quoted_odds=float(item["odds"]),
        ))

    session.flush()
    return slip

