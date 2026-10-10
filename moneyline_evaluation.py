"""One-game-one-row evaluation of frozen pregame observations."""
from frozen_player_features import EXPANDED_FEATURE_FIELDS, EXPORT_FEATURE_VERSION, extract_player_news_features
import math
from collections import Counter
from datetime import datetime, timedelta

from moneyline_features import implied_share

FEATURE_FIELDS = EXPANDED_FEATURE_FIELDS


def time_value(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIMESTAMP")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("INVALID_TIMESTAMP") from None
    if result.tzinfo is None:
        raise ValueError("TIMESTAMP_TIMEZONE_MISSING")
    return result


def select_observations(records, now, min_lead_hours=1, max_lead_hours=24):
    if not 0 < min_lead_hours < max_lead_hours:
        raise ValueError("Invalid evaluation lead-time window")

    selected = {}
    excluded = Counter()
    eligible_observations = 0

    for record in records:
        try:
            pick = record.get("pick")
            if record.get("pick_matches") != 1 or not isinstance(pick, dict):
                raise ValueError("MISSING_OR_AMBIGUOUS_SELECTION")

            if (
                pick.get("market_key") != "h2h"
                or pick.get("event_id") != record.get("event_id")
                or pick.get("pick_key") != record.get("home_pick_key")
            ):
                raise ValueError("SELECTION_IDENTITY_MISMATCH")

            if pick.get("status") not in {"WON", "LOST"}:
                raise ValueError("OUTCOME_NOT_SETTLED_WIN_OR_LOSS")

            kickoff = time_value(pick.get("kickoff_time"))
            settled = time_value(pick.get("settled_at"))
            captured = time_value(record.get("captured_at"))

            if not kickoff < settled <= now:
                raise ValueError("INVALID_SETTLEMENT_TIME")
            if captured > now:
                raise ValueError("CAPTURE_TIME_IN_FUTURE")

            lead = kickoff - captured
            if lead < timedelta(hours=min_lead_hours):
                raise ValueError("CAPTURE_TOO_CLOSE_TO_OR_AFTER_KICKOFF")
            if lead > timedelta(hours=max_lead_hours):
                raise ValueError("CAPTURE_TOO_EARLY_FOR_EVALUATION_WINDOW")

            key = record.get("observation_key")
            event_id = record.get("event_id")
            if not key or not event_id:
                raise ValueError("OBSERVATION_IDENTITY_MISSING")

        except (ValueError, TypeError, AttributeError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else "INVALID_METADATA"
            excluded[reason] += 1
            continue

        eligible_observations += 1
        previous = selected.get(event_id)

        if previous is None or (
            captured, str(key)
        ) > (
            time_value(previous["captured_at"]),
            str(previous["observation_key"]),
        ):
            selected[event_id] = record

    records_out = sorted(
        selected.values(),
        key=lambda item: (
            time_value(item["pick"]["kickoff_time"]),
            str(item["event_id"]),
        ),
    )
    return records_out, {
        "excluded_observations_by_reason": dict(excluded),
        "superseded_eligible_observations": (
            eligible_observations - len(records_out)
        ),
    }


def validate_selected(record, evidence, max_quote_age_minutes=60):
    if not isinstance(evidence, dict):
        raise ValueError("INVALID_EVIDENCE_JSON")

    pick = record["pick"]
    if (
        evidence.get("observation_key") != record["observation_key"]
        or evidence.get("event_id") != record["event_id"]
        or evidence.get("home") != pick.get("pick_side")
    ):
        raise ValueError("FROZEN_EVIDENCE_IDENTITY_MISMATCH")

    captured = time_value(record["captured_at"])
    if time_value(evidence.get("captured_at")) != captured:
        raise ValueError("CAPTURE_TIMESTAMP_MISMATCH")

    observed = time_value(evidence.get("odds_observed_at"))
    market_time = time_value(evidence.get("market_last_update"))
    kickoff = time_value(pick["kickoff_time"])

    if not market_time <= observed <= captured < kickoff:
        raise ValueError("INVALID_QUOTE_TIME_ORDER")

    if observed - market_time > timedelta(minutes=max_quote_age_minutes):
        raise ValueError("PROVIDER_QUOTE_TOO_OLD_AT_OBSERVATION")

    bookmaker = evidence.get("bookmaker_key")
    if not isinstance(bookmaker, str) or not bookmaker.strip():
        raise ValueError("BOOKMAKER_MISSING")

    home_odds = evidence.get("home_odds")
    away_odds = evidence.get("away_odds")
    home_implied = implied_share(home_odds)
    away_implied = implied_share(away_odds)
    baseline = home_implied / (home_implied + away_implied)

    features = evidence.get("features")
    if not isinstance(features, dict):
        raise ValueError("FEATURES_MISSING")
    features = dict(features)
    features.update(extract_player_news_features(evidence))

    row = {
        "event_id": record["event_id"],
        "observation_key": record["observation_key"],
        "home_pick_key": record["home_pick_key"],
        "captured_at": captured.isoformat(),
        "odds_observed_at": observed.isoformat(),
        "market_last_update": market_time.isoformat(),
        "kickoff_time": kickoff.isoformat(),
        "settled_at": pick["settled_at"],
        "actual_lead_hours": (kickoff - captured).total_seconds() / 3600,
        "home": evidence.get("home"),
        "away": evidence.get("away"),
        "bookmaker_key": bookmaker,
        "home_odds": float(home_odds),
        "away_odds": float(away_odds),
        "baseline_home_share": baseline,
        "home_won": int(pick["status"] == "WON"),
        "feature_version": EXPORT_FEATURE_VERSION,
    }

    for field in FEATURE_FIELDS:
        value = features.get(field)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError("INVALID_NUMERIC_FEATURE")
        row[field] = value

    return row


def probability_metrics(labels, probabilities):
    if len(labels) != len(probabilities):
        raise ValueError("Label/probability count mismatch")
    if not labels:
        return None
    if any(label not in (0, 1) for label in labels):
        raise ValueError("Invalid binary labels")
    if any(
        not isinstance(p, (int, float))
        or not math.isfinite(p)
        or not 0 < p < 1
        for p in probabilities
    ):
        raise ValueError("Invalid probability values")

    n = len(labels)
    return {
        "games": n,
        "brier_score": math.fsum(
            (p - y) ** 2 for y, p in zip(labels, probabilities)
        ) / n,
        "log_loss": -math.fsum(
            y * math.log(p) + (1 - y) * math.log1p(-p)
            for y, p in zip(labels, probabilities)
        ) / n,
        "observed_home_win_rate": sum(labels) / n,
        "mean_baseline_home_share": math.fsum(probabilities) / n,
    }
