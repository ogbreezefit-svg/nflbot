"""Pure Monster selection policy. No database writes or model approval."""
import math
from datetime import datetime, timedelta, timezone

MIN_LEGS = 10
MAX_LEGS = 30
MAX_PRICE_AGE = timedelta(minutes=15)


def parse_time(value):
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if result.tzinfo is None:
        return None
    return result.astimezone(timezone.utc)


def eligible_candidate(row, now, slate_start, slate_end):
    if not isinstance(row, dict):
        return None
    if row.get("research_qualified") is not True:
        return None
    if row.get("prediction_approved") is not True:
        return None
    if row.get("market") != "h2h":
        return None

    event = row.get("event_id")
    key = row.get("selection_key")
    label = row.get("label")
    if not all(isinstance(v, str) and v.strip() for v in (event, key, label)):
        return None

    kickoff = parse_time(row.get("kickoff"))
    quoted = parse_time(row.get("quoted_at"))
    if kickoff is None or quoted is None:
        return None
    if kickoff <= now or not slate_start <= kickoff < slate_end:
        return None
    if not timedelta(0) <= now - quoted < MAX_PRICE_AGE:
        return None

    try:
        probability = float(row["probability"])
        decimal_odds = float(row["decimal_odds"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None

    if not math.isfinite(probability) or not 0 < probability < 1:
        return None
    if not math.isfinite(decimal_odds) or decimal_odds <= 1:
        return None

    expected_gross = probability * decimal_odds
    if expected_gross <= 1:
        return None

    return {
        "event_id": event,
        "selection_key": key,
        "label": label,
        "kickoff": kickoff.isoformat(),
        "quoted_at": quoted.isoformat(),
        "probability": probability,
        "decimal_odds": decimal_odds,
        "estimated_leg_ev": expected_gross - 1,
    }


def select_monster(
    candidates, *, now, slate_start, slate_end,
    min_ticket_probability, stake=10.0
):
    now = parse_time(now)
    slate_start = parse_time(slate_start)
    slate_end = parse_time(slate_end)
    if None in (now, slate_start, slate_end) or slate_start >= slate_end:
        raise ValueError("Valid timezone-aware slate boundaries are required.")

    try:
        floor = float(min_ticket_probability)
        stake = float(stake)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Invalid ticket probability floor or stake.") from None
    if not math.isfinite(floor) or not 0 < floor <= 1:
        raise ValueError("Ticket probability floor must be in (0, 1].")
    if not math.isfinite(stake) or stake <= 0:
        raise ValueError("Stake must be positive and finite.")

    eligible = []
    for row in candidates:
        candidate = eligible_candidate(row, now, slate_start, slate_end)
        if candidate is not None:
            eligible.append(candidate)

    eligible.sort(key=lambda row: (
        -row["estimated_leg_ev"],
        -row["probability"],
        row["selection_key"],
    ))

    pool = []
    events = set()
    keys = set()
    for row in eligible:
        if row["event_id"] in events or row["selection_key"] in keys:
            continue
        pool.append(row)
        events.add(row["event_id"])
        keys.add(row["selection_key"])

    if len(pool) < MIN_LEGS:
        return {
            "status": "BLOCKED",
            "reason": "FEWER_THAN_TEN_QUALIFIED_EVENTS",
            "eligible_events": len(pool),
            "legs": [],
        }

    options = []
    for count in range(MIN_LEGS, min(MAX_LEGS, len(pool)) + 1):
        legs = pool[:count]
        log_probability = math.fsum(math.log(x["probability"]) for x in legs)
        if log_probability < math.log(floor):
            continue
        log_odds = math.fsum(math.log(x["decimal_odds"]) for x in legs)
        options.append((log_odds, log_probability, legs))

    if not options:
        return {
            "status": "BLOCKED",
            "reason": "TICKET_PROBABILITY_FLOOR_NOT_MET",
            "eligible_events": len(pool),
            "legs": [],
        }

    log_odds, log_probability, legs = max(options, key=lambda x: x[0])
    if log_odds > math.log(float.fromhex("0x1.fffffffffffffp+1023")):
        return {"status": "BLOCKED", "reason": "ODDS_OVERFLOW", "legs": []}

    decimal_odds = math.exp(log_odds)
    gross = stake * decimal_odds
    if not math.isfinite(gross):
        return {"status": "BLOCKED", "reason": "RETURN_OVERFLOW", "legs": []}

    return {
        "status": "CANDIDATE_ONLY",
        "category": "Weekly Monster",
        "legs": legs,
        "leg_count": len(legs),
        "decimal_odds": decimal_odds,
        "estimated_gross_return": round(gross, 2),
        "stake": stake,
        "estimated_probability": math.exp(log_probability),
        "probability_basis": "Assumes independence across selected events",
        "selection_method": "positive-EV-ranked-prefix-v1",
        "publication_approved": False,
    }
