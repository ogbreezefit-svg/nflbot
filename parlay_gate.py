"""Research diagnostics. Legacy builders never qualify through this policy."""
from datetime import datetime, timedelta
from matchup_features import normalized_name

POLICY_VERSION = "strict-parlay-pause-v1"
MAX_RESEARCH_AGE = timedelta(hours=2)


def parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo is not None else None


def assess_parlay_inputs(matchup, report, snapshot_time, now):
    reasons = []
    valid_report = isinstance(report, dict)
    data = report if valid_report else {}

    if not valid_report:
        reasons.append("MATCHUP_RESEARCH_MISSING_OR_INVALID")

    if (
        not isinstance(snapshot_time, datetime)
        or snapshot_time.tzinfo is None
    ):
        reasons.append("RESEARCH_TIMESTAMP_MISSING_OR_INVALID")
    else:
        age = now - snapshot_time
        if age < timedelta(0):
            reasons.append("RESEARCH_TIMESTAMP_IN_FUTURE")
        elif age >= MAX_RESEARCH_AGE:
            reasons.append("MATCHUP_RESEARCH_STALE")

    kickoff = parse_time(matchup.get("commence_time"))
    if kickoff is None:
        reasons.append("KICKOFF_MISSING_OR_INVALID")
    elif kickoff <= now:
        reasons.append("GAME_ALREADY_STARTED")

    if valid_report:
        if data.get("event_id") != matchup.get("event_id"):
            reasons.append("RESEARCH_EVENT_ID_MISMATCH")

        for side in ("home", "away"):
            team = data.get(side)
            team = team if isinstance(team, dict) else {}
            expected = normalized_name(matchup.get(side))
            actual = normalized_name(team.get("team_name"))
            if not expected or not actual or expected != actual:
                reasons.append(f"{side.upper()}_TEAM_IDENTITY_UNVERIFIED")

        provider_time = parse_time(data.get("team_source_fetched_at"))
        if provider_time is None:
            reasons.append("TEAM_SOURCE_TIMESTAMP_UNVERIFIED")
        else:
            provider_age = now - provider_time
            if provider_age < timedelta(0):
                reasons.append("TEAM_SOURCE_TIMESTAMP_IN_FUTURE")
            elif provider_age >= MAX_RESEARCH_AGE:
                reasons.append("TEAM_SOURCE_STALE")

    for field, reason in (
        ("team_evidence_status", "TEAM_EVIDENCE_INCOMPLETE"),
        ("player_evidence_status", "PLAYER_EVIDENCE_INCOMPLETE"),
        ("news_evidence_status", "NEWS_EVIDENCE_INCOMPLETE"),
    ):
        if data.get(field) != "AVAILABLE":
            reasons.append(reason)

    if data.get("recommendation_readiness") != "READY":
        reasons.append("RECOMMENDATION_RESEARCH_NOT_READY")

    requirements = data.get("remaining_requirements")
    if not isinstance(requirements, list) or any(
        not isinstance(item, str) for item in requirements
    ):
        requirements = []
        reasons.append("REQUIREMENT_LIST_MISSING_OR_INVALID")
    elif requirements:
        reasons.append("REQUIRED_RESEARCH_STILL_OUTSTANDING")

    # READY labels alone must never activate the old odds-only builders.
    reasons.append("RESEARCH_QUALIFIED_SELECTOR_NOT_IMPLEMENTED")

    return {
        "policy_version": POLICY_VERSION,
        "event_id": matchup.get("event_id"),
        "assessed_at": now.isoformat(),
        "decision": "BLOCKED",
        "eligible": False,
        "legacy_builders_enabled": False,
        "blocked_builders": ["build_parlay", "build_tier_parlays"],
        "reasons": list(dict.fromkeys(reasons)),
        "remaining_requirements": requirements,
        "evidence_status": {
            field: data.get(field)
            for field in (
                "team_evidence_status",
                "player_evidence_status",
                "news_evidence_status",
                "recommendation_readiness",
            )
        },
        "excluded_research_inputs": ["Venue", "Weather"],
    }
