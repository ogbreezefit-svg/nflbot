"""Persist the latest blocking assessment. Never writes parlay tickets."""
import json
import logging
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Text
from db import Base, SessionLocal
from research_data import utc_time
from matchup_research import MatchupResearchSnapshot
from parlay_gate import assess_parlay_inputs

log = logging.getLogger("ogbreeze.parlay_research_gate")


class ParlayResearchDecision(Base):
    __tablename__ = "parlay_research_decisions"

    event_id = Column(String, primary_key=True)
    assessed_at = Column(DateTime(timezone=True), nullable=False)
    decision_json = Column(Text, nullable=False)


def record_parlay_research_gate(matchups):
    now = datetime.now(timezone.utc)
    counts = Counter()
    assessed = 0

    with SessionLocal() as session:
        for matchup in matchups:
            if not isinstance(matchup, dict) or not matchup.get("event_id"):
                counts["INVALID_MATCHUP_EVENT_ID"] += 1
                continue

            event_id = str(matchup["event_id"])
            snapshot = session.get(MatchupResearchSnapshot, event_id)
            report = None
            snapshot_time = None

            if snapshot is not None:
                snapshot_time = utc_time(snapshot.fetched_at)
                try:
                    report = json.loads(snapshot.report_json)
                except (TypeError, ValueError):
                    report = None

            decision = assess_parlay_inputs(
                matchup, report, snapshot_time, now
            )

            row = session.get(ParlayResearchDecision, event_id)
            if row is None:
                row = ParlayResearchDecision(event_id=event_id)
                session.add(row)

            row.assessed_at = now
            row.decision_json = json.dumps(decision, allow_nan=False)
            counts.update(decision["reasons"])
            assessed += 1

        session.commit()

    log.warning(
        "Strict parlay gate: %s events assessed; automatic creation PAUSED. "
        "Blockers: %s",
        assessed,
        dict(counts),
    )
    return {"status": "PAUSED", "assessed": assessed}
