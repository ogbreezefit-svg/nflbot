"""Persist matchup evidence from the existing team snapshot."""
import json
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import Column, String, DateTime, Text
from db import Base, SessionLocal
from research_data import ResearchSnapshot, utc_time
from matchup_features import build_matchup_report
from player_research import PlayerResearchSnapshot
from player_matchup import summarize_player_snapshot

log = logging.getLogger("ogbreeze.matchup_research")


class MatchupResearchSnapshot(Base):
    __tablename__ = "matchup_research_snapshots"

    event_id = Column(String, primary_key=True)
    fetched_at = Column(DateTime(timezone=True), nullable=False)
    team_source_fetched_at = Column(DateTime(timezone=True), nullable=False)
    kickoff_time = Column(DateTime(timezone=True), nullable=False)
    report_json = Column(Text, nullable=False)


def save_matchup_research(matchups):
    now = datetime.now(timezone.utc)

    with SessionLocal() as session:
        source = session.get(ResearchSnapshot, 1)
        if source is None:
            log.warning("Matchup research unavailable: no team snapshot.")
            return 0

        source_time = utc_time(source.fetched_at)
        if now - source_time > timedelta(hours=2):
            log.warning("Matchup research unavailable: team snapshot stale.")
            return 0

        payload = json.loads(source.payload_json)
        teams = payload.get("teams")
        if not isinstance(teams, list) or len(teams) != 32:
            raise ValueError("Team snapshot does not contain 32 teams")

        saved = 0
        for matchup in matchups:
            event_id = matchup.get("event_id")
            kickoff_raw = matchup.get("commence_time")

            if not event_id or not isinstance(kickoff_raw, str):
                continue

            try:
                kickoff = datetime.fromisoformat(
                    kickoff_raw.replace("Z", "+00:00")
                )
                if kickoff.tzinfo is None:
                    raise ValueError("Kickoff timezone missing")
                kickoff = kickoff.astimezone(timezone.utc)
            except ValueError:
                log.warning("Invalid matchup kickoff: %s", event_id)
                continue

            if kickoff <= now:
                continue

            report = build_matchup_report(matchup, teams)

            # Weather and venue research are deliberately excluded.
            report["excluded_research_inputs"] = ["Venue", "Weather"]
            report["remaining_requirements"] = [
                item for item in report.get("remaining_requirements", [])
                if item != "Actual venue and kickoff weather"
            ]

            player_sides = []
            for side in ("home", "away"):
                team_report = report.get(side)
                if not isinstance(team_report, dict):
                    player_sides.append(False)
                    continue

                abbreviation = team_report.get("team_abv")
                player_snapshot = (
                    session.get(PlayerResearchSnapshot, abbreviation)
                    if abbreviation else None
                )

                evidence = summarize_player_snapshot(
                    player_snapshot.payload_json
                    if player_snapshot is not None else None,
                    utc_time(player_snapshot.fetched_at)
                    if player_snapshot is not None else None,
                    now,
                    abbreviation,
                )
                team_report["player_evidence"] = evidence
                player_sides.append(evidence["usable_for_current_research"])

            report["player_evidence_status"] = (
                "AVAILABLE"
                if len(player_sides) == 2 and all(player_sides)
                else "INCOMPLETE"
            )

            report["team_source_fetched_at"] = source_time.isoformat()
            report["assembled_at"] = now.isoformat()

            snapshot = session.get(MatchupResearchSnapshot, event_id)
            if snapshot is None:
                snapshot = MatchupResearchSnapshot(event_id=event_id)
                session.add(snapshot)

            snapshot.fetched_at = now
            snapshot.team_source_fetched_at = source_time
            snapshot.kickoff_time = kickoff
            snapshot.report_json = json.dumps(report, allow_nan=False)
            saved += 1

        session.commit()

    log.info("Matchup evidence snapshots saved: %s", saved)
    return saved
