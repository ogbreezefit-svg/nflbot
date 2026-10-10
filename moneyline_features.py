"""Freeze pregame research and prices. No prediction or selection model."""
import hashlib
import json
from datetime import datetime, timedelta
from player_stats import numeric
from matchup_features import normalized_name

FEATURE_VERSION = "moneyline-research-v1"


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo is not None else None


def implied_share(price):
    price = numeric(price)
    if price is None or abs(price) < 100:
        raise ValueError("Invalid American moneyline")
    return (
        100 / (price + 100)
        if price > 0 else abs(price) / (abs(price) + 100)
    )


def build_observation(matchup, report, report_time, now):
    if not isinstance(report, dict):
        raise ValueError("Research report missing")

    kickoff = timestamp(matchup.get("commence_time"))
    observed = timestamp(matchup.get("odds_observed_at"))

    if kickoff is None or observed is None:
        raise ValueError("Kickoff/observation timestamp missing")
    if not observed <= now < kickoff:
        raise ValueError("Observation is not pregame")

    if (
        not isinstance(report_time, datetime)
        or report_time.tzinfo is None
        or not timedelta(0) <= now - report_time < timedelta(hours=2)
    ):
        raise ValueError("Research snapshot missing, future, or stale")

    source_time = timestamp(report.get("team_source_fetched_at"))
    if source_time is None or not (
        timedelta(0) <= now - source_time < timedelta(hours=2)
    ):
        raise ValueError("Team source timestamp missing, future, or stale")

    event_id = matchup.get("event_id")
    if not event_id or report.get("event_id") != event_id:
        raise ValueError("Event identity mismatch")

    bookmaker = matchup.get("bookmaker_key")
    if not isinstance(bookmaker, str) or not bookmaker.strip():
        raise ValueError("Bookmaker identity missing")

    home, away = matchup.get("home"), matchup.get("away")
    if not home or not away or home == away:
        raise ValueError("Invalid matchup teams")

    for side in ("home", "away"):
        team = report.get(side)
        if not isinstance(team, dict) or (
            normalized_name(team.get("team_name"))
            != normalized_name(matchup.get(side))
        ):
            raise ValueError("Research team identity mismatch")

    outcomes = matchup.get("h2h_raw_outcomes")
    if not isinstance(outcomes, list) or len(outcomes) != 2:
        raise ValueError("Expected exactly two moneyline outcomes")

    prices = {}
    for item in outcomes:
        if not isinstance(item, dict):
            raise ValueError("Invalid moneyline outcome")
        name = item.get("name")
        if name in prices:
            raise ValueError("Duplicate moneyline outcome")
        price = numeric(item.get("price"))
        implied_share(price)
        prices[name] = price

    if set(prices) != {home, away}:
        raise ValueError("Moneyline outcome identities mismatch")

    if (
        prices[home] != numeric(matchup.get("home_ml"))
        or prices[away] != numeric(matchup.get("away_ml"))
    ):
        raise ValueError("Parsed prices differ from source outcomes")

    market_time_raw = matchup.get("h2h_market_last_update")
    market_time = timestamp(market_time_raw)
    if market_time_raw is not None and market_time is None:
        raise ValueError("Invalid provider market timestamp")
    if market_time is not None and market_time > observed:
        raise ValueError("Provider market timestamp is after observation")

    features = {}
    for field in (
        "passing_yards_per_attempt",
        "completion_percentage",
        "rushing_yards_per_carry",
    ):
        values = []
        for side in ("home", "away"):
            rates = report[side].get("rates")
            rates = rates if isinstance(rates, dict) else {}
            values.append(numeric(rates.get(field)))

        features[f"home_minus_away_{field}"] = (
            values[0] - values[1]
            if all(value is not None for value in values) else None
        )

    if not any(value is not None for value in features.values()):
        raise ValueError("No comparable numeric research features")

    home_implied = implied_share(prices[home])
    away_implied = implied_share(prices[away])
    bucket = now.replace(minute=0, second=0, microsecond=0).isoformat()
    key = hashlib.sha256(json.dumps(
        [event_id, bookmaker, bucket],
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()

    result = {
        "observation_key": key,
        "feature_version": FEATURE_VERSION,
        "event_id": event_id,
        "captured_at": now.isoformat(),
        "odds_observed_at": observed.isoformat(),
        "kickoff_time": kickoff.isoformat(),
        "home": home,
        "away": away,
        "bookmaker_key": bookmaker,
        "home_odds": prices[home],
        "away_odds": prices[away],
        "market_last_update": (
            market_time.isoformat() if market_time else None
        ),
        "provider_market_timestamp_verified": market_time is not None,
        "research_snapshot_time": report_time.isoformat(),
        "features": features,
        "market_baseline": {
            "normalized_implied_home_share": (
                home_implied / (home_implied + away_implied)
            ),
            "normalized_implied_away_share": (
                away_implied / (home_implied + away_implied)
            ),
            "is_research_model_prediction": False,
        },
        "research_model_probability": None,
        "selection_decision": "NOT_ASSESSED",
        "research_report": report,
    }

    # Detach the frozen representation from mutable caller dictionaries.
    return json.loads(json.dumps(result, allow_nan=False))
