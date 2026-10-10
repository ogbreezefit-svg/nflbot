"""Immutable prospective evidence, linked to existing selection outcomes."""
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.exc import IntegrityError
from db import Base, SessionLocal
from research_data import utc_time
from matchup_research import MatchupResearchSnapshot
from selection_tracker import selection_key
from moneyline_features import build_observation

log = logging.getLogger("ogbreeze.moneyline_observations")


class MoneylineResearchObservation(Base):
    __tablename__ = "moneyline_research_observations"

    observation_key = Column(String, primary_key=True)
    event_id = Column(String, nullable=False, index=True)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    kickoff_time = Column(DateTime(timezone=True), nullable=False)
    home_pick_key = Column(String, nullable=False, index=True)
    evidence_json = Column(Text, nullable=False)


def freeze_moneyline_observations(matchups):
    now = datetime.now(timezone.utc)
    counts = {"saved": 0, "existing": 0, "skipped": 0}

    with SessionLocal() as session:
        for matchup in matchups:
            event_id = matchup.get("event_id")
            snapshot = (
                session.get(MatchupResearchSnapshot, event_id)
                if event_id else None
            )

            try:
                report = (
                    json.loads(snapshot.report_json)
                    if snapshot is not None else None
                )
                evidence = build_observation(
                    matchup,
                    report,
                    utc_time(snapshot.fetched_at)
                    if snapshot is not None else None,
                    now,
                )
            except (TypeError, ValueError, AttributeError) as exc:
                counts["skipped"] += 1
                log.warning(
                    "Research observation skipped for %s: %s",
                    event_id, exc,
                )
                continue

            key = evidence["observation_key"]
            if session.get(MoneylineResearchObservation, key) is not None:
                counts["existing"] += 1
                continue

            try:
                with session.begin_nested():
                    session.add(MoneylineResearchObservation(
                        observation_key=key,
                        event_id=event_id,
                        captured_at=now,
                        kickoff_time=datetime.fromisoformat(
                            evidence["kickoff_time"]
                        ),
                        home_pick_key=selection_key(
                            event_id, "h2h", matchup["home"]
                        ),
                        evidence_json=json.dumps(
                            evidence, allow_nan=False
                        ),
                    ))
                    session.flush()
                counts["saved"] += 1

            except IntegrityError:
                if session.get(MoneylineResearchObservation, key) is None:
                    raise
                counts["existing"] += 1

        session.commit()

    log.warning("Pregame moneyline evidence: %s", counts)
    return counts
