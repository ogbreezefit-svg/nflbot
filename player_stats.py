"""Pure player-stat normalization. No API or database access."""
import math

OFFENSIVE_POSITIONS = {"QB", "RB", "FB", "WR", "TE"}
CATEGORIES = ("Passing", "Rushing", "Receiving")
NORMALIZATION_VERSION = 2

# Conservative allowlist. Unknown fields remain in season_totals.
# Do not divide percentages, ratings, averages, or longest plays.
ADDITIVE_FIELDS = {
    "Passing": {"passYds", "passAttempts", "passCompletions"},
    "Rushing": {"rushYds", "carries"},
    "Receiving": {"recYds", "receptions", "targets"},
}


def numeric(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def normalize_player(player):
    if not isinstance(player, dict):
        raise ValueError("Player must be an object")

    player_id = player.get("playerID")
    if player_id is None or not str(player_id).strip():
        raise ValueError("Missing player ID")

    stats = player.get("stats")
    if not isinstance(stats, dict):
        stats = {}

    games = numeric(stats.get("gamesPlayed"))
    games = int(games) if (
        games is not None and games > 0 and games.is_integer()
    ) else None

    totals = {}
    per_game = {}

    for category in CATEGORIES:
        values = stats.get(category)
        if not isinstance(values, dict):
            continue

        totals[category] = {
            field: numeric(value)
            for field, value in values.items()
        }
        per_game[category] = {
            field: value / games
            if games is not None and value is not None else None
            for field, value in totals[category].items()
            if field in ADDITIVE_FIELDS[category]
        }

    usable = any(
        value is not None
        for category in totals.values()
        for value in category.values()
    )

    per_game_usable = any(
        value is not None
        for category in per_game.values()
        for value in category.values()
    )

    injury = player.get("injury")
    injury = injury if isinstance(injury, dict) else {}

    return {
        "player_id": str(player_id),
        "name": (
            player.get("longName")
            or player.get("cbsLongName")
            or player.get("espnName")
            or str(player_id)
        ),
        "position": str(player.get("pos", "")).upper(),
        "roster_team": player.get("teamAbv") or player.get("team"),
        "roster_team_id": player.get("teamID"),
        "normalization_version": NORMALIZATION_VERSION,
        "stats_team": stats.get("teamAbv") or stats.get("team"),
        "games_played": games,
        "season_totals": totals,
        "per_game": per_game,
        "has_numeric_season_stats": usable,
        "per_game_ready": per_game_usable,
        "injury": {
            field: injury.get(field)
            for field in (
                "designation", "description", "injDate", "injReturnDate"
            )
        },
        "availability_evidence_status": (
            "REPORTED_DESIGNATION_NOT_VERIFIED"
            if str(injury.get("designation") or "").strip()
            else "UNKNOWN"
        ),
        "recent_usage_verified": False,
        "availability_verified": False,
        "starting_role_verified": False,
    }
