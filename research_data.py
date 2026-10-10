"""Scheduled research collection only; not a recommendation model."""
import json
import logging
import math
import os
from datetime import datetime, timezone, timedelta

from sqlalchemy import Column, Integer, DateTime, Text
from db import Base, SessionLocal

log = logging.getLogger("ogbreeze.research")


class ResearchSnapshot(Base):
    __tablename__ = "research_snapshots"

    id = Column(Integer, primary_key=True)
    fetched_at = Column(DateTime(timezone=True), nullable=False)
    source = Column(Text, nullable=False)
    payload_json = Column(Text, nullable=False)
    coverage_json = Column(Text, nullable=False)


def utc_time(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def numeric_value(value):
    """Unknown/missing statistics remain None, never invented zeroes."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def normalize_team_stats(stats):
    if not isinstance(stats, dict):
        return {}
    normalized = {}
    for category, values in stats.items():
        if isinstance(values, dict):
            normalized[category] = {
                name: numeric_value(value)
                for name, value in values.items()
            }
    return normalized


def validate_teams(teams):
    if not isinstance(teams, list) or len(teams) != 32:
        raise ValueError("Expected 32 NFL teams")

    seen = set()
    normalized = []

    for team in teams:
        if not isinstance(team, dict):
            raise ValueError("Invalid team record")

        abbreviation = team.get("teamAbv")
        if not abbreviation or abbreviation in seen:
            raise ValueError("Missing or duplicate team abbreviation")
        seen.add(abbreviation)

        stats = team.get("teamStats")
        roster = team.get("Roster")

        if not isinstance(stats, dict) or not stats:
            raise ValueError(f"Missing team statistics: {abbreviation}")
        if not isinstance(roster, dict) or not roster:
            raise ValueError(f"Missing roster: {abbreviation}")

        if any(not isinstance(player, dict) for player in roster.values()):
            raise ValueError(f"Invalid roster record: {abbreviation}")

        # Preserve raw values and IDs for later reconciliation.
        record = dict(team)
        record["normalizedTeamStats"] = normalize_team_stats(stats)
        normalized.append(record)

    return normalized


def coverage_summary(teams):
    players = injury_objects = numeric_stats = 0

    for team in teams:
        roster = team["Roster"]
        players += len(roster)
        injury_objects += sum(
            isinstance(player.get("injury"), dict)
            for player in roster.values()
        )
        numeric_stats += sum(
            value is not None
            for category in team["normalizedTeamStats"].values()
            for value in category.values()
        )

    return {
        "teams": len(teams),
        "roster_players": players,
        "players_with_injury_objects": injury_objects,
        "numeric_team_stats": numeric_stats,
        "season_scope": "Tank01 current-season endpoint",
        "provider_update_timestamp": None,
        "collection_status": "TEAM_ROSTER_SNAPSHOT_AVAILABLE",
        "recommendation_readiness": "INCOMPLETE",
        "notes": [
            "Fetched time is not the provider's publication time.",
            "An injury object does not establish current availability.",
            "Player season/game-level statistics are not yet normalized.",
            "News, weather, NFL.com inputs, and projections remain pending.",
        ],
    }


def refresh_team_research(force=False):
    import requests

    now = datetime.now(timezone.utc)

    with SessionLocal() as session:
        existing = session.get(ResearchSnapshot, 1)
        if (
            existing is not None
            and not force
            and now - utc_time(existing.fetched_at) < timedelta(minutes=60)
        ):
            log.info("Research snapshot is within the collection cache window.")
            return json.loads(existing.coverage_json)

    key = os.getenv("RAPIDAPI_KEY")
    if not key:
        log.warning("Research collection skipped: RAPIDAPI_KEY missing.")
        return None

    host = "tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com"

    try:
        response = requests.get(
            f"https://{host}/getNFLTeams",
            headers={
                "x-rapidapi-host": host,
                "x-rapidapi-key": key,
            },
            params={
                "teamStats": "true",
                "rosters": "true",
                "schedules": "true",
            },
            timeout=45,
        )

        if response.status_code != 200:
            log.warning(
                "Research HTTP %s; preserving the last snapshot.",
                response.status_code,
            )
            return None

        payload = response.json()
        if not isinstance(payload, dict) or payload.get("error"):
            raise ValueError("Invalid provider response")

        if str(payload.get("statusCode")) != "200":
            raise ValueError("Provider did not report success")

        teams = validate_teams(payload.get("body"))
        coverage = coverage_summary(teams)

    except requests.RequestException:
        log.warning("Research request failed; preserving the last snapshot.")
        return None
    except (ValueError, TypeError):
        log.warning("Research validation failed; preserving the last snapshot.")
        return None

    with SessionLocal() as session:
        snapshot = session.get(ResearchSnapshot, 1)
        if snapshot is None:
            snapshot = ResearchSnapshot(id=1)
            session.add(snapshot)

        snapshot.fetched_at = now
        snapshot.source = "Tank01 getNFLTeams"
        snapshot.payload_json = json.dumps(
            {"teams": teams}, allow_nan=False
        )
        snapshot.coverage_json = json.dumps(coverage)
        session.commit()

    log.info(
        "Research snapshot saved: %s teams, %s roster players.",
        coverage["teams"], coverage["roster_players"],
    )
    return coverage


if __name__ == "__main__":
    from dotenv import load_dotenv
    from pathlib import Path
    from db import init_db

    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    init_db()
    logging.basicConfig(level=logging.INFO)
    result = refresh_team_research()
    print(json.dumps(result, indent=2) if result else "Collection unavailable.")
