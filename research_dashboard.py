"""Read-only research status. No scheduler, model loading, or API requests."""
import json
import logging
from collections import Counter
from datetime import datetime, timezone, timedelta

log = logging.getLogger("ogbreeze.research_dashboard")
AUDIT_TTL = timedelta(hours=2)
LABELS = {
    "RECOMMENDATION_RESEARCH_NOT_READY": "Recommendation research not ready",
    "REQUIRED_RESEARCH_STILL_OUTSTANDING": "Required research remains outstanding",
    "RESEARCH_QUALIFIED_SELECTOR_NOT_IMPLEMENTED": "Research-qualified selector not implemented",
    "TEAM_EVIDENCE_INCOMPLETE": "Team evidence incomplete",
    "PLAYER_EVIDENCE_INCOMPLETE": "Player evidence incomplete",
    "NEWS_EVIDENCE_INCOMPLETE": "News evidence incomplete",
    "MATCHUP_RESEARCH_STALE": "Matchup research stale",
}

def unavailable_research_status():
    return {
        "available": False, "generation_status": "PAUSED",
        "model_approval": "NOT APPROVED",
        "experimental_training_status": "Not recorded in the dashboard database",
        "observation_count": None, "distinct_events": None,
        "eligible_settled_events": None, "recent_audit_events": None,
        "last_audit_utc": None, "blockers": [], "invalid_audit_rows": 0,
    }

def aware(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

def make_research_status(observation_count, distinct_events, eligible_settled_events,
                         audits, now=None):
    now = aware(now or datetime.now(timezone.utc))
    result = unavailable_research_status()
    result.update({"available": True, "observation_count": observation_count,
                   "distinct_events": distinct_events,
                   "eligible_settled_events": eligible_settled_events,
                   "recent_audit_events": 0})
    counts = Counter()
    recent_times = []
    for row in audits:
        try:
            assessed = aware(row.assessed_at)
            if not timedelta(0) <= now - assessed < AUDIT_TTL:
                continue
            decision = json.loads(row.decision_json)
            reasons = decision.get("reasons")
            if not isinstance(reasons, list) or any(not isinstance(x, str) for x in reasons):
                raise ValueError("Invalid audit reasons")
            counts.update(set(reasons))
            recent_times.append(assessed)
        except (ValueError, TypeError, AttributeError):
            result["invalid_audit_rows"] += 1
    result["recent_audit_events"] = len(recent_times)
    if recent_times:
        result["last_audit_utc"] = max(recent_times).strftime("%Y-%m-%d %H:%M:%S UTC")
    result["blockers"] = [
        {"code": code, "label": LABELS.get(code, code.replace("_", " ")),
         "count": count} for code, count in sorted(counts.items())
    ]
    return result

def load_research_status(session, now=None):
    now = aware(now or datetime.now(timezone.utc))
    try:
        from sqlalchemy import func, distinct
        from db import PickLog
        from moneyline_observations import MoneylineResearchObservation as Observation
        from parlay_research_gate import ParlayResearchDecision
        from moneyline_evaluation import select_observations, validate_selected

        metadata = session.query(
            Observation.observation_key, Observation.event_id,
            Observation.captured_at, Observation.home_pick_key,
        ).all()
        event_count = len({row.event_id for row in metadata})
        keys = sorted({row.home_pick_key for row in metadata})
        picks_by_key = {}
        for start in range(0, len(keys), 500):
            picks = session.query(PickLog).filter(
                PickLog.pick_key.in_(keys[start:start + 500])
            ).all()
            for pick in picks:
                picks_by_key.setdefault(pick.pick_key, []).append(pick)
        records = []
        for row in metadata:
            matches = picks_by_key.get(row.home_pick_key, [])
            pick = matches[0] if len(matches) == 1 else None
            records.append({
                "observation_key": row.observation_key,
                "event_id": row.event_id,
                "captured_at": aware(row.captured_at).isoformat(),
                "home_pick_key": row.home_pick_key,
                "pick_matches": len(matches),
                "pick": None if pick is None else {
                    "pick_key": pick.pick_key, "event_id": pick.event_id,
                    "market_key": pick.market_key, "pick_side": pick.pick_side,
                    "status": pick.status,
                    "kickoff_time": aware(pick.kickoff_time).isoformat()
                        if pick.kickoff_time is not None else None,
                    "settled_at": aware(pick.settled_at).isoformat()
                        if pick.settled_at is not None else None,
                },
            })
        selected, _ = select_observations(records, now, 1, 24)
        eligible = 0
        for record in selected:
            row = session.get(Observation, record["observation_key"])
            try:
                validate_selected(record, json.loads(row.evidence_json), 60)
                eligible += 1
            except (ValueError, TypeError, AttributeError, KeyError):
                continue
        audits = session.query(ParlayResearchDecision).filter(
            ParlayResearchDecision.assessed_at >= now - AUDIT_TTL
        ).all()
        return make_research_status(len(metadata), event_count, eligible, audits, now)
    except Exception as exc:
        log.warning("Research dashboard unavailable (%s); creation remains paused.",
                    type(exc).__name__)
        return unavailable_research_status()
