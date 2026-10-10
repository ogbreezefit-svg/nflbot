"""Daily offensive-player snapshots for all teams in the team feed."""
import json
import logging
import os
from datetime import datetime, timezone, timedelta

from sqlalchemy import Column, String, DateTime, Text
from db import Base, SessionLocal
from research_data import ResearchSnapshot, utc_time
from player_stats import normalize_player, OFFENSIVE_POSITIONS

log = logging.getLogger("ogbreeze.player_research")


class PlayerResearchSnapshot(Base):
    __tablename__ = "player_research_snapshots"

    team_abv = Column(String, primary_key=True)
    fetched_at = Column(DateTime(timezone=True), nullable=False)
    payload_json = Column(Text, nullable=False)
    coverage_json = Column(Text, nullable=False)


def refresh_player_research():
    import requests

    key = os.getenv("RAPIDAPI_KEY")
    if not key:
        log.warning("Player collection skipped: RAPIDAPI_KEY missing.")
        return {"updated": 0, "cached": 0, "failed": 0}

    now = datetime.now(timezone.utc)

    with SessionLocal() as session:
        source = session.get(ResearchSnapshot, 1)
        if source is None:
            log.warning("Player collection requires a team snapshot.")
            return {"updated": 0, "cached": 0, "failed": 0}

        if now - utc_time(source.fetched_at) > timedelta(hours=24):
            log.warning("Team snapshot too old to drive player collection.")
            return {"updated": 0, "cached": 0, "failed": 0}

        teams = json.loads(source.payload_json).get("teams", [])

    abbreviations = sorted({
        team.get("teamAbv")
        for team in teams
        if isinstance(team, dict) and team.get("teamAbv")
    })
    if len(abbreviations) != 32:
        raise ValueError("Expected 32 team abbreviations")

    counts = {"updated": 0, "cached": 0, "failed": 0}
    host = "tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com"

    # A single coordinated ingestion process is assumed.
    with requests.Session() as client:
        client.headers.update({
            "x-rapidapi-host": host,
            "x-rapidapi-key": key,
        })

        for abbreviation in abbreviations:
            with SessionLocal() as session:
                existing = session.get(PlayerResearchSnapshot, abbreviation)
                if (
                    existing is not None
                    and now - utc_time(existing.fetched_at) < timedelta(hours=24)
                ):
                    counts["cached"] += 1
                    continue

            try:
                response = client.get(
                    f"https://{host}/getNFLTeamRoster",
                    params={
                        "teamAbv": abbreviation,
                        "getStats": "true",
                        "statsToGet": "true",
                    },
                    timeout=45,
                )

                if response.status_code == 429:
                    log.warning(
                        "Roster rate limit reached; stopping this batch."
                    )
                    counts["failed"] += 1
                    break

                if response.status_code != 200:
                    log.warning(
                        "Roster HTTP %s for %s; cached data retained.",
                        response.status_code, abbreviation,
                    )
                    counts["failed"] += 1
                    continue

                payload = response.json()
                if (
                    not isinstance(payload, dict)
                    or str(payload.get("statusCode")) != "200"
                    or payload.get("error")
                ):
                    raise ValueError("Provider response unsuccessful")

                body = payload.get("body")
                if not isinstance(body, dict):
                    raise ValueError("Missing roster body")

                roster = body.get("roster")
                if not isinstance(roster, list) or not roster:
                    raise ValueError("Missing roster list")

                if any(not isinstance(player, dict) for player in roster):
                    raise ValueError("Invalid roster entry")

                offensive = [
                    player for player in roster
                    if str(player.get("pos", "")).upper()
                    in OFFENSIVE_POSITIONS
                ]
                if not offensive:
                    raise ValueError("No offensive roster records")

                players = [normalize_player(player) for player in offensive]
                ids = [player["player_id"] for player in players]
                if len(ids) != len(set(ids)):
                    raise ValueError("Duplicate player IDs")

                coverage = {
                    "team": abbreviation,
                    "offensive_players": len(players),
                    "players_with_numeric_stats": sum(
                        player["has_numeric_season_stats"] for player in players
                    ),
                    "players_with_per_game_stats": sum(
                        player["per_game_ready"] for player in players
                    ),
                    "season_scope": "Tank01 current-season endpoint",
                    "provider_update_timestamp": None,
                    "recommendation_readiness": "INCOMPLETE",
                }

                with SessionLocal() as session:
                    snapshot = session.get(
                        PlayerResearchSnapshot, abbreviation
                    )
                    if snapshot is None:
                        snapshot = PlayerResearchSnapshot(
                            team_abv=abbreviation
                        )
                        session.add(snapshot)

                    snapshot.fetched_at = datetime.now(timezone.utc)
                    snapshot.payload_json = json.dumps({
                        "players": players,
                        "raw_offensive_roster": offensive,
                    }, allow_nan=False)
                    snapshot.coverage_json = json.dumps(coverage)
                    session.commit()

                counts["updated"] += 1

            except requests.RequestException:
                log.warning(
                    "Roster request failed for %s; cached data retained.",
                    abbreviation,
                )
                counts["failed"] += 1
            except (TypeError, ValueError):
                log.warning(
                    "Roster validation failed for %s; cached data retained.",
                    abbreviation,
                )
                counts["failed"] += 1

    log.info("Player research batch: %s", counts)
    return counts
