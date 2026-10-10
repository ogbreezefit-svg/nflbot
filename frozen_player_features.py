"""Player/news proxies derived only from immutable pregame reports."""
import math
from datetime import datetime, timedelta

BASE_FIELDS = (
    "home_minus_away_passing_yards_per_attempt",
    "home_minus_away_completion_percentage",
    "home_minus_away_rushing_yards_per_carry",
)
SIDE_FIELDS = (
    "passing_volume_leader_yards_per_attempt",
    "rushing_volume_leader_yards_per_carry",
    "receiving_target_leader_yards_per_target",
    "reported_designation_fraction",
    "observed_news_player_count",
)
EXPANDED_FEATURE_FIELDS = BASE_FIELDS + tuple("home_minus_away_" + x for x in SIDE_FIELDS)
EXPORT_FEATURE_VERSION = "moneyline-expanded-v2"

def numeric(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None

def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo is not None else None

def fresh(source_time, captured, hours):
    source = timestamp(source_time)
    return source is not None and timedelta(0) <= captured-source < timedelta(hours=hours)

def leader_rate(players, abbreviation, category, numerator, denominator, positions):
    candidates = []
    for player in players:
        if player.get("position") not in positions:
            continue
        # Do not assign old-team or unidentified-team season statistics to this team.
        if str(player.get("stats_team") or "").strip().upper() != abbreviation:
            continue
        totals = player.get("season_totals")
        values = totals.get(category) if isinstance(totals, dict) else None
        if not isinstance(values, dict):
            continue
        volume, yards = numeric(values.get(denominator)), numeric(values.get(numerator))
        if volume is None or yards is None or volume <= 0 or yards < 0:
            continue
        candidates.append((volume, yards / volume))
    if not candidates:
        return None
    maximum = max(volume for volume, rate in candidates)
    leaders = [rate for volume, rate in candidates if volume == maximum]
    # A tied volume leader is not resolved by choosing the better efficiency.
    return leaders[0] if len(leaders) == 1 else None

def side_features(team, captured):
    result = {name: None for name in SIDE_FIELDS}
    if not isinstance(team, dict):
        return result
    abbreviation = str(team.get("team_abv") or "").strip().upper()
    if not abbreviation:
        return result
    evidence = team.get("player_evidence")
    if isinstance(evidence, dict) and (
        evidence.get("status") == "FRESH"
        and evidence.get("usable_for_current_research") is True
        and fresh(evidence.get("source_fetched_at"), captured, 24)
    ):
        players = evidence.get("players")
        if isinstance(players, list) and players and all(
            isinstance(p, dict)
            and str(p.get("roster_team") or "").strip().upper() == abbreviation
            for p in players
        ):
            reported = sum(
                bool(str(p.get("injury", {}).get("designation") or "").strip())
                for p in players if isinstance(p.get("injury"), dict)
            )
            result["reported_designation_fraction"] = reported / len(players)
            result["passing_volume_leader_yards_per_attempt"] = leader_rate(
                players, abbreviation, "Passing", "passYds", "passAttempts", {"QB"})
            result["rushing_volume_leader_yards_per_carry"] = leader_rate(
                players, abbreviation, "Rushing", "rushYds", "carries", {"QB", "RB", "FB"})
            result["receiving_target_leader_yards_per_target"] = leader_rate(
                players, abbreviation, "Receiving", "recYds", "targets", {"WR", "TE", "RB", "FB"})

    news = team.get("news_evidence")
    if isinstance(news, dict) and news.get("status") == "AVAILABLE" and fresh(
        news.get("collected_at"), captured, 6
    ):
        articles = news.get("articles")
        if isinstance(articles, list) and all(isinstance(a, dict) for a in articles):
            # Zero means no uniquely identified players in this observed limited feed.
            # It never means no injuries or no relevant news exists.
            ids = {str(a["matched_player_id"]) for a in articles if a.get("matched_player_id")}
            result["observed_news_player_count"] = len(ids)
    return result

def extract_player_news_features(evidence):
    captured = timestamp(evidence.get("captured_at")) if isinstance(evidence, dict) else None
    if captured is None:
        raise ValueError("Captured timestamp missing for expanded features")
    report = evidence.get("research_report")
    report = report if isinstance(report, dict) else {}
    home, away = (side_features(report.get(side), captured) for side in ("home", "away"))
    return {
        "home_minus_away_" + field: (
            home[field]-away[field] if home[field] is not None and away[field] is not None else None
        ) for field in SIDE_FIELDS
    }
