"""Pure player evidence summaries. No network or database access."""
import json
from datetime import datetime, timedelta
from player_stats import normalize_player, NORMALIZATION_VERSION

MAX_SNAPSHOT_AGE = timedelta(hours=24)


def summarize_player_snapshot(payload_json, fetched_at, now, team_abv):
    result = {
        "team_abv": team_abv,
        "status": "MISSING",
        "source_fetched_at": None,
        "age_hours": None,
        "normalization_version": NORMALIZATION_VERSION,
        "usable_for_current_research": False,
        "offensive_players": 0,
        "players_with_numeric_season_stats": 0,
        "players_with_per_game_stats": 0,
        "players_with_reported_designations": 0,
        "players": [],
        "issues": [],
        "availability_verified": False,
        "starting_roles_verified": False,
        "recent_game_usage_verified": False,
        "recommendation_readiness": "INCOMPLETE",
    }

    if payload_json is None or fetched_at is None:
        result["issues"].append("Player snapshot missing")
        return result

    if (
        not isinstance(fetched_at, datetime)
        or fetched_at.tzinfo is None
        or now.tzinfo is None
    ):
        result["status"] = "INVALID"
        result["issues"].append("Timezone-aware snapshot timestamps required")
        return result

    age = now - fetched_at
    result["source_fetched_at"] = fetched_at.isoformat()
    result["age_hours"] = round(age.total_seconds() / 3600, 3)

    if age.total_seconds() < 0:
        result["status"] = "INVALID"
        result["issues"].append("Snapshot timestamp is in the future")
        return result

    try:
        payload = json.loads(payload_json)
        if not isinstance(payload, dict):
            raise ValueError("Snapshot payload must be an object")

        raw_roster = payload.get("raw_offensive_roster")
        if not isinstance(raw_roster, list) or not raw_roster:
            raise ValueError("Stored raw offensive roster missing")

        players = [normalize_player(player) for player in raw_roster]
        ids = [player["player_id"] for player in players]

        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate player IDs")

    except (TypeError, ValueError) as exc:
        result["status"] = "INVALID"
        result["issues"].append(str(exc))
        return result

    result["players"] = players
    result["offensive_players"] = len(players)
    result["players_with_numeric_season_stats"] = sum(
        player["has_numeric_season_stats"] for player in players
    )
    result["players_with_per_game_stats"] = sum(
        player["per_game_ready"] for player in players
    )
    result["players_with_reported_designations"] = sum(
        bool(str(player["injury"].get("designation") or "").strip())
        for player in players
    )

    # Compare explicit abbreviations only. Do not guess display-name aliases.
    mismatches = [
        str(player.get("playerID"))
        for player in raw_roster
        if player.get("teamAbv")
        and str(player["teamAbv"]).strip().upper()
        != str(team_abv).strip().upper()
    ]

    if mismatches:
        result["status"] = "TEAM_MISMATCH"
        result["issues"].append(
            "Roster team abbreviations differ from snapshot team"
        )
        result["mismatched_player_ids"] = mismatches
        return result

    if age >= MAX_SNAPSHOT_AGE:
        result["status"] = "STALE"
        result["issues"].append("Player snapshot is at least 24 hours old")
        return result

    result["status"] = "FRESH"
    result["usable_for_current_research"] = True

    if result["players_with_numeric_season_stats"] == 0:
        result["issues"].append("No numeric offensive season statistics")
        result["usable_for_current_research"] = False

    result["issues"].extend([
        "Roster injuries do not verify game availability",
        "Season averages do not establish recent game-level usage",
        "Current starting roles are not verified",
    ])
    return result
