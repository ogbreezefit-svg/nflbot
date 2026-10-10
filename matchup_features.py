"""Pure matchup features. No invented probabilities or missing-data zeroes."""
import math
import re


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def ratio(numerator, denominator, multiplier=1):
    numerator, denominator = number(numerator), number(denominator)
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator * multiplier


def normalized_name(value):
    value = re.sub(r"\s+", " ", str(value or "").strip()).casefold()
    # Explicit city abbreviations only; no fuzzy team matching.
    if value.startswith("la "):
        value = "los angeles " + value[3:]
    elif value.startswith("ny "):
        value = "new york " + value[3:]
    return value


def resolve_team(name, teams):
    wanted = normalized_name(name)
    matches = []

    for team in teams:
        aliases = {
            normalized_name(team.get("teamAbv")),
            normalized_name(
                f"{team.get('teamCity', '')} {team.get('teamName', '')}"
            ),
        }
        if wanted and wanted in aliases:
            matches.append(team)

    return matches[0] if len(matches) == 1 else None


def team_features(team):
    raw = team.get("teamStats")
    raw = raw if isinstance(raw, dict) else {}

    totals = {
        category: {
            field: number(value)
            for field, value in values.items()
        }
        for category, values in raw.items()
        if isinstance(values, dict)
    }

    passing = totals.get("Passing", {})
    rushing = totals.get("Rushing", {})

    record_values = [
        number(team.get(field)) for field in ("wins", "loss", "tie")
    ]
    standings_games = (
        int(sum(record_values))
        if all(
            value is not None and value >= 0 and value.is_integer()
            for value in record_values
        )
        else None
    )

    return {
        "team_id": team.get("teamID"),
        "team_abv": team.get("teamAbv"),
        "team_name": (
            f"{team.get('teamCity', '')} {team.get('teamName', '')}"
        ).strip(),
        "standings_games": standings_games,
        "points_for": number(team.get("pf")),
        "points_against": number(team.get("pa")),
        "season_totals": totals,
        "rates": {
            "passing_yards_per_attempt": ratio(
                passing.get("passYds"), passing.get("passAttempts")
            ),
            "completion_percentage": ratio(
                passing.get("passCompletions"),
                passing.get("passAttempts"),
                100,
            ),
            "rushing_yards_per_carry": ratio(
                rushing.get("rushYds"), rushing.get("carries")
            ),
        },
        "stats_standings_cutoff_verified": False,
    }


def build_matchup_report(matchup, teams):
    home = resolve_team(matchup.get("home"), teams)
    away = resolve_team(matchup.get("away"), teams)
    missing = []

    if home is None:
        missing.append("Home team identity not resolved uniquely")
    if away is None:
        missing.append("Away team identity not resolved uniquely")

    home_features = team_features(home) if home else None
    away_features = team_features(away) if away else None

    for side, data in (
        ("home", home_features), ("away", away_features)
    ):
        if data is None:
            continue
        for category in ("Passing", "Rushing", "Defense"):
            values = data["season_totals"].get(category, {})
            if not any(value is not None for value in values.values()):
                missing.append(f"{side}: missing numeric {category} statistics")

    return {
        "event_id": matchup.get("event_id"),
        "home": home_features,
        "away": away_features,
        "team_evidence_status": (
            "AVAILABLE" if not missing else "INCOMPLETE"
        ),
        "missing_team_evidence": missing,
        "recommendation_readiness": "INCOMPLETE",
        "excluded_research_inputs": ["Venue", "Weather"],
        "remaining_requirements": [
            "Verified player availability and current role",
            "Recent game-level usage",
            "Timestamped player news",
            "Required authorized NFL.com inputs",
            "Evaluated projection and selection model",
        ],
        "notes": [
            "Team totals and standings may have different update cutoffs.",
            "Within-category rates are descriptive, not next-game predictions.",
            "No win probability or confidence score is generated.",
        ],
    }
