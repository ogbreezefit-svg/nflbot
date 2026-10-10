"""Cached fantasy-news collection and roster-linked matchup evidence."""
import json
import logging
import os
from datetime import datetime, timezone, timedelta

from sqlalchemy import Column, Integer, String, DateTime, Text
from db import Base, SessionLocal
from research_data import utc_time
from player_research import PlayerResearchSnapshot
from player_stats import normalize_player
from news_stats import normalize_news, link_news, NoNewsResults

log = logging.getLogger("ogbreeze.news_research")
NEWS_TTL = timedelta(hours=6)
ROSTER_TTL = timedelta(hours=24)


class NewsResearchSnapshot(Base):
    __tablename__ = "news_research_snapshots"

    id = Column(Integer, primary_key=True)
    last_attempt_at = Column(DateTime(timezone=True), nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False)
    payload_json = Column(Text, nullable=False)


def refresh_news_research():
    import requests

    key = os.getenv("RAPIDAPI_KEY")
    if not key:
        log.warning("News collection skipped: RAPIDAPI_KEY missing.")
        return {"status": "KEY_MISSING"}

    now = datetime.now(timezone.utc)

    with SessionLocal() as session:
        existing = session.get(NewsResearchSnapshot, 1)
        if existing is not None:
            age = now - utc_time(existing.last_attempt_at)
            if timedelta(0) <= age < NEWS_TTL:
                return {"status": "CACHED", "last_result": existing.status}

    host = "tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com"
    articles = None
    status = "FAILED"

    try:
        response = requests.get(
            f"https://{host}/getNFLNews",
            params={"fantasyNews": "true", "maxItems": "20"},
            headers={"x-rapidapi-host": host, "x-rapidapi-key": key},
            timeout=30,
        )

        if response.status_code == 200:
            articles = normalize_news(response.json())
            status = "OK"
        else:
            status = f"HTTP_{response.status_code}"

    except NoNewsResults:
        status = "NO_RESULTS"
    except requests.RequestException:
        status = "REQUEST_FAILED"
    except (TypeError, ValueError):
        status = "INVALID_RESPONSE"

    completed_at = datetime.now(timezone.utc)

    with SessionLocal() as session:
        snapshot = session.get(NewsResearchSnapshot, 1)
        if snapshot is None:
            snapshot = NewsResearchSnapshot(
                id=1,
                payload_json=json.dumps({"articles": []}),
            )
            session.add(snapshot)

        snapshot.last_attempt_at = completed_at
        snapshot.status = status

        # Failed attempts never overwrite the last successful feed.
        if articles is not None:
            snapshot.fetched_at = completed_at
            snapshot.payload_json = json.dumps(
                {"articles": articles}, allow_nan=False
            )

        session.commit()

    if status != "OK":
        log.warning("News refresh: %s; previous successful feed retained.", status)
    else:
        log.info("News refresh: %s articles stored.", len(articles))

    return {
        "status": status,
        "articles": len(articles) if articles is not None else None,
    }


def load_news_context(session, now, teams):
    context = {
        "status": "MISSING",
        "collected_at": None,
        "age_hours": None,
        "feed_item_count": 0,
        "unmatched_article_count": None,
        "by_team": {},
    }

    snapshot = session.get(NewsResearchSnapshot, 1)
    if snapshot is None:
        return context

    context["last_refresh_status"] = snapshot.status
    if snapshot.fetched_at is None:
        context["status"] = snapshot.status
        return context

    fetched_at = utc_time(snapshot.fetched_at)
    age = now - fetched_at
    context["collected_at"] = fetched_at.isoformat()
    context["age_hours"] = round(age.total_seconds() / 3600, 3)

    if age < timedelta(0):
        context["status"] = "INVALID_TIMESTAMP"
        return context
    if age >= NEWS_TTL:
        context["status"] = "STALE"
        return context
    if snapshot.status != "OK":
        context["status"] = snapshot.status
        return context

    try:
        payload = json.loads(snapshot.payload_json)
        articles = payload.get("articles")
        if not isinstance(articles, list) or not articles:
            raise ValueError("Stored news articles missing")

        expected = {
            team.get("teamAbv") for team in teams
            if isinstance(team, dict) and team.get("teamAbv")
        }
        if len(expected) != 32:
            raise ValueError("Expected 32 team abbreviations")

        roster = []
        for abbreviation in sorted(expected):
            player_snapshot = session.get(
                PlayerResearchSnapshot, abbreviation
            )
            if player_snapshot is None:
                context["status"] = "ROSTER_COVERAGE_INCOMPLETE"
                return context

            roster_age = now - utc_time(player_snapshot.fetched_at)
            if not timedelta(0) <= roster_age < ROSTER_TTL:
                context["status"] = "ROSTER_COVERAGE_INCOMPLETE"
                return context

            roster_payload = json.loads(player_snapshot.payload_json)
            raw = roster_payload.get("raw_offensive_roster")
            if not isinstance(raw, list) or not raw:
                raise ValueError("Raw offensive roster missing")

            normalized = [normalize_player(player) for player in raw]
            ids = [player["player_id"] for player in normalized]
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate roster player IDs")

            for source_player, player in zip(raw, normalized):
                source_team = source_player.get("teamAbv")
                if source_team and (
                    str(source_team).strip().upper()
                    != str(abbreviation).strip().upper()
                ):
                    raise ValueError("Roster team abbreviation mismatch")

                roster.append({
                    "player_id": player["player_id"],
                    "name": player["name"],
                    "team_abv": abbreviation,
                })

        by_team, unmatched = link_news(articles, roster)

    except (TypeError, ValueError, AttributeError, KeyError):
        context["status"] = "INVALID_LINKING_DATA"
        return context

    context.update({
        "status": "AVAILABLE",
        "feed_item_count": len(articles),
        "unmatched_article_count": unmatched,
        "by_team": by_team,
    })
    return context


def attach_news_to_matchup(report, context):
    report["news_evidence_status"] = context["status"]

    # Maintain the requested project scope.
    report["excluded_research_inputs"] = ["Venue", "Weather"]
    report["remaining_requirements"] = [
        item for item in report.get("remaining_requirements", [])
        if item != "Actual venue and kickoff weather"
    ]

    for side in ("home", "away"):
        team = report.get(side)
        if not isinstance(team, dict):
            continue

        team["news_evidence"] = {
            "status": context["status"],
            "collected_at": context["collected_at"],
            "age_hours": context["age_hours"],
            "feed_item_count": context["feed_item_count"],
            "unmatched_article_count": context["unmatched_article_count"],
            "articles": context["by_team"].get(team.get("team_abv"), []),
            "publication_times_verified": False,
            "availability_verified": False,
            "starting_roles_verified": False,
            "recommendation_readiness": "INCOMPLETE",
            "notes": [
                "Latest requested feed is limited to 20 items.",
                "No matched headline does not establish no relevant news.",
                "Unique name matching is not medical or lineup verification.",
            ],
        }
