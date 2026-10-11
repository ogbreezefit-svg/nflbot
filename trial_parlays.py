"""Trial ticket settlement. Paper tracking only; no wagers are placed."""
import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP


def evaluate_ticket(legs, stake):
    """Return outcome, paper gross return, paper profit.

    legs contains (selection_status, ticket_quoted_odds) pairs.
    Pushes remove a leg. All pushes return the paper stake.
    Unknown or review-required legs prevent final settlement.
    """
    if not legs:
        return ("REVIEW_REQUIRED", None, None)

    try:
        amount = Decimal(str(stake))
        if not amount.is_finite() or amount <= 0:
            return ("REVIEW_REQUIRED", None, None)

        statuses = []
        prices = []
        for status, odds in legs:
            price = Decimal(str(odds))
            if not price.is_finite() or abs(price) < 100:
                return ("REVIEW_REQUIRED", None, None)
            statuses.append(status)
            prices.append(price)

        allowed = {
            "ACTIVE", "PENDING", "WON", "LOST",
            "PUSH", "REVIEW_REQUIRED",
        }
        if any(status not in allowed for status in statuses):
            return ("REVIEW_REQUIRED", None, None)
        if "REVIEW_REQUIRED" in statuses:
            return ("REVIEW_REQUIRED", None, None)

        # A graded losing leg makes the paper ticket a loss.
        if "LOST" in statuses:
            return ("LOST", 0.0, float(-amount))

        if any(status in {"ACTIVE", "PENDING"} for status in statuses):
            return ("PENDING", None, None)

        multiplier = Decimal("1")
        wins = 0
        for status, price in zip(statuses, prices):
            if status == "PUSH":
                continue
            wins += 1
            multiplier *= (
                Decimal("1") + price / Decimal("100")
                if price > 0
                else Decimal("1") + Decimal("100") / abs(price)
            )

        gross = (amount * multiplier).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        profit = gross - amount
        if not all(math.isfinite(float(x)) for x in (gross, profit)):
            return ("REVIEW_REQUIRED", None, None)

        return (
            "WON" if wins else "PUSH",
            float(gross),
            float(profit),
        )
    except (TypeError, ValueError, ArithmeticError):
        return ("REVIEW_REQUIRED", None, None)


def settle_trial_tickets():
    """Use existing selection grades; never fetch or infer game results."""
    from db import SessionLocal, ParlaySlip, ParlayLeg, PickLog

    now = datetime.now(timezone.utc)
    counts = {"settled": 0, "pending": 0, "review": 0}

    with SessionLocal() as session:
        tickets = session.query(ParlaySlip).filter(
            ParlaySlip.publication_mode == "TRIAL",
            ParlaySlip.settled_at.is_(None),
        ).all()

        for ticket in tickets:
            links = session.query(ParlayLeg).filter(
                ParlayLeg.ticket_id == ticket.id
            ).order_by(ParlayLeg.position).all()

            legs = []
            event_ids = set()
            invalid = len(links) < 2

            for link in links:
                pick = session.get(PickLog, link.pick_id)
                if pick is None or not pick.event_id:
                    invalid = True
                    continue

                # This trial policy supports distinct-event tickets only.
                if pick.event_id in event_ids:
                    invalid = True
                event_ids.add(pick.event_id)

                status = pick.status
                if (
                    status in {"WON", "LOST", "PUSH"}
                    and pick.settled_at is None
                ):
                    status = "REVIEW_REQUIRED"
                legs.append((status, link.quoted_odds))

            result = (
                ("REVIEW_REQUIRED", None, None)
                if invalid
                else evaluate_ticket(legs, ticket.paper_stake)
            )
            outcome, gross, profit = result

            if outcome in {"PENDING", "REVIEW_REQUIRED"}:
                ticket.outcome = outcome
                counts["pending" if outcome == "PENDING" else "review"] += 1
                continue

            changed = session.query(ParlaySlip).filter(
                ParlaySlip.id == ticket.id,
                ParlaySlip.publication_mode == "TRIAL",
                ParlaySlip.settled_at.is_(None),
            ).update({
                "outcome": outcome,
                "paper_return": gross,
                "paper_profit": profit,
                "settled_at": now,
            }, synchronize_session=False)
            counts["settled"] += changed

        session.commit()

    return counts


TRIAL_METHOD = "home-moneyline-baseline-v1"


def build_trial_parlays(matchups):
    """Publish one two-event paper ticket; no trained-model claim."""
    import hashlib
    import json
    from datetime import timedelta
    from decimal import Decimal, ROUND_HALF_UP

    from db import SessionLocal, ParlaySlip
    from nfl_moneyline import as_utc, valid_odds
    from selection_tracker import track_ticket, selection_key
    from sqlalchemy.exc import IntegrityError

    now = datetime.now(timezone.utc)
    eligible = {}
    duplicate_ids = set()

    for matchup in matchups:
        if not isinstance(matchup, dict):
            continue

        event_id = matchup.get("event_id")
        home = matchup.get("home")
        away = matchup.get("away")
        price = matchup.get("home_ml")
        if (
            not isinstance(event_id, str) or not event_id
            or not isinstance(home, str) or not home
            or not isinstance(away, str) or not away
            or home == away or not valid_odds(price)
            or not matchup.get("bookmaker_key")
        ):
            continue

        try:
            kickoff = as_utc(matchup.get("commence_time"))
            observed = as_utc(matchup.get("odds_observed_at"))
            updated = as_utc(matchup.get("h2h_market_last_update"))
        except (TypeError, ValueError, AttributeError):
            continue

        if kickoff <= now:
            continue
        if not all(
            timedelta(0) <= now - timestamp < timedelta(minutes=60)
            for timestamp in (observed, updated)
        ):
            continue

        # Ambiguous duplicate event records are excluded.
        if event_id in eligible:
            duplicate_ids.add(event_id)
        eligible[event_id] = (kickoff, matchup)

    candidates = [
        item for event_id, item in eligible.items()
        if event_id not in duplicate_ids
    ]
    candidates.sort(key=lambda item: (
        item[0], item[1]["event_id"]
    ))

    if len(candidates) < 2:
        return {"status": "NO_ELIGIBLE_TICKET", "created": 0}

    chosen = [item[1] for item in candidates[:2]]
    keys = [
        selection_key(m["event_id"], "h2h", m["home"])
        for m in chosen
    ]
    identity = json.dumps(
        {"method": TRIAL_METHOD, "selections": sorted(keys)},
        sort_keys=True,
    )
    ticket_key = hashlib.sha256(identity.encode()).hexdigest()

    stake = Decimal("10")
    multiplier = Decimal("1")
    for matchup in chosen:
        price = Decimal(str(matchup["home_ml"]))
        multiplier *= (
            Decimal("1") + price / Decimal("100")
            if price > 0
            else Decimal("1") + Decimal("100") / abs(price)
        )
    gross = (stake * multiplier).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    american = (
        (multiplier - 1) * 100
        if multiplier >= 2
        else -100 / (multiplier - 1)
    )
    american = american.quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )

    slip = ParlaySlip(
        category="Trial 2-Leg",
        odds=f"{multiplier:.4f}x ({american:+.0f})",
        stake="$10.00",
        payout=f"${gross:.2f}",
        legs_json=json.dumps([
            f"{m['home']} Moneyline ({m['home_ml']})"
            for m in chosen
        ]),
        status="ACTIVE",
        publication_mode="TRIAL",
        selection_method=TRIAL_METHOD,
        ticket_key=ticket_key,
        outcome="PENDING",
        paper_stake=float(stake),
    )

    with SessionLocal() as session:
        if session.query(ParlaySlip.id).filter(
            ParlaySlip.ticket_key == ticket_key
        ).first():
            return {"status": "ALREADY_PUBLISHED", "created": 0}

        try:
            track_ticket(session, slip, chosen)
            session.commit()
        except IntegrityError:
            session.rollback()
            if session.query(ParlaySlip.id).filter(
                ParlaySlip.ticket_key == ticket_key
            ).first():
                return {"status": "ALREADY_PUBLISHED", "created": 0}
            raise

    return {"status": "TRIAL_PUBLISHED", "created": 1}
