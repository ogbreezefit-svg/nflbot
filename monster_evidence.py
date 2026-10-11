"""Frozen evidence to experimental diagnostics. No database writes."""
from datetime import timedelta

from frozen_player_features import (
    BASE_FIELDS,
    EXPANDED_FEATURE_FIELDS,
    extract_player_news_features,
)
from moneyline_features import implied_share
from monster_inference import predict_experimental_moneyline
from monster_policy import parse_time


def experimental_candidates(evidence, bundle, *, now):
    if not isinstance(evidence, dict):
        raise ValueError("Frozen evidence must be a dictionary.")
    if evidence.get("feature_version") != "moneyline-research-v1":
        raise ValueError("Unsupported frozen evidence version.")

    now = parse_time(now)
    captured = parse_time(evidence.get("captured_at"))
    observed = parse_time(evidence.get("odds_observed_at"))
    market_time = parse_time(evidence.get("market_last_update"))
    kickoff = parse_time(evidence.get("kickoff_time"))

    if any(value is None for value in (
        now, captured, observed, market_time, kickoff
    )):
        raise ValueError("Required timezone-aware timestamps are missing.")
    if not market_time <= observed <= captured <= now < kickoff:
        raise ValueError("Invalid pregame timestamp order.")
    if not timedelta(0) <= now - market_time < timedelta(minutes=15):
        raise ValueError("Provider quote is stale.")
    if not timedelta(hours=1) <= kickoff - captured <= timedelta(hours=24):
        raise ValueError("Evidence is outside the evaluated prediction window.")

    event_id = evidence.get("event_id")
    home = evidence.get("home")
    away = evidence.get("away")
    bookmaker = evidence.get("bookmaker_key")
    observation_key = evidence.get("observation_key")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (event_id, home, away, bookmaker, observation_key)
    ):
        raise ValueError("Evidence identity fields are missing.")
    if home == away:
        raise ValueError("Home and away teams must differ.")

    report = evidence.get("research_report")
    if not isinstance(report, dict) or report.get("event_id") != event_id:
        raise ValueError("Research event identity mismatch.")
    for side, name in (("home", home), ("away", away)):
        team = report.get(side)
        if not isinstance(team, dict) or team.get("team_name") != name:
            raise ValueError("Research team identity mismatch.")

    base = evidence.get("features")
    if not isinstance(base, dict) or not all(
        field in base for field in BASE_FIELDS
    ):
        raise ValueError("Base research feature fields are missing.")

    expanded = dict(base)
    expanded.update(extract_player_news_features(evidence))
    features = {
        field: expanded[field] for field in EXPANDED_FEATURE_FIELDS
    }

    for field in ("home_odds", "away_odds"):
        if isinstance(evidence.get(field), bool):
            raise ValueError("Moneyline price must not be boolean.")

    home_implied = implied_share(evidence.get("home_odds"))
    away_implied = implied_share(evidence.get("away_odds"))
    baseline = home_implied / (home_implied + away_implied)
    prediction = predict_experimental_moneyline(
        bundle, baseline, features
    )

    candidates = []
    for side, team, implied in (
        ("home", home, home_implied),
        ("away", away, away_implied),
    ):
        probability = prediction[f"{side}_probability"]
        decimal_odds = 1.0 / implied
        candidates.append({
            "event_id": event_id,
            "selection_key": f"{event_id}|h2h|{team}",
            "label": f"{team} moneyline",
            "market": "h2h",
            "side": side,
            "kickoff": kickoff.isoformat(),
            "quoted_at": market_time.isoformat(),
            "bookmaker_key": bookmaker,
            "observation_key": observation_key,
            "probability": probability,
            "decimal_odds": decimal_odds,
            "estimated_leg_ev": probability * decimal_odds - 1.0,
            "research_qualified": False,
            "prediction_approved": False,
            "publication_approved": False,
        })

    return {
        "status": "EXPERIMENTAL_DIAGNOSTICS_ONLY",
        "prediction": prediction,
        "candidates": candidates,
        "publication_approved": False,
    }
