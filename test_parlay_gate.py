import ast
from pathlib import Path
import unittest
from unittest.mock import Mock
from datetime import datetime, timedelta, timezone

from parlay_gate import assess_parlay_inputs


class ParlayGateTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.matchup = {
            "event_id": "synthetic-event",
            "home": "Test Home",
            "away": "Test Away",
            "commence_time": (
                self.now + timedelta(days=1)
            ).isoformat(),
        }
        self.report = {
            "event_id": "synthetic-event",
            "home": {"team_name": "Test Home"},
            "away": {"team_name": "Test Away"},
            "team_source_fetched_at": self.now.isoformat(),
            "team_evidence_status": "AVAILABLE",
            "player_evidence_status": "AVAILABLE",
            "news_evidence_status": "AVAILABLE",
            "recommendation_readiness": "READY",
            "remaining_requirements": [],
        }

    def assess(self, report=None, timestamp=None):
        return assess_parlay_inputs(
            self.matchup,
            self.report if report is None else report,
            self.now if timestamp is None else timestamp,
            self.now,
        )

    def test_missing_report_is_blocked(self):
        result = assess_parlay_inputs(
            self.matchup, None, None, self.now
        )
        self.assertFalse(result["eligible"])
        self.assertIn(
            "MATCHUP_RESEARCH_MISSING_OR_INVALID", result["reasons"]
        )

    def test_stale_snapshot_is_blocked(self):
        result = self.assess(
            timestamp=self.now - timedelta(hours=2)
        )
        self.assertIn("MATCHUP_RESEARCH_STALE", result["reasons"])

    def test_stale_team_source_is_blocked(self):
        self.report["team_source_fetched_at"] = (
            self.now - timedelta(hours=3)
        ).isoformat()
        self.assertIn("TEAM_SOURCE_STALE", self.assess()["reasons"])

    def test_event_mismatch_is_blocked(self):
        self.report["event_id"] = "different-event"
        self.assertIn(
            "RESEARCH_EVENT_ID_MISMATCH", self.assess()["reasons"]
        )

    def test_incomplete_readiness_is_blocked(self):
        self.report["recommendation_readiness"] = "INCOMPLETE"
        self.assertIn(
            "RECOMMENDATION_RESEARCH_NOT_READY", self.assess()["reasons"]
        )

    def test_ready_labels_cannot_activate_legacy_builders(self):
        result = self.assess()
        self.assertFalse(result["eligible"])
        self.assertFalse(result["legacy_builders_enabled"])
        self.assertIn(
            "RESEARCH_QUALIFIED_SELECTOR_NOT_IMPLEMENTED",
            result["reasons"],
        )

    def test_started_game_is_blocked(self):
        self.matchup["commence_time"] = (
            self.now - timedelta(minutes=1)
        ).isoformat()
        self.assertIn("GAME_ALREADY_STARTED", self.assess()["reasons"])

    def isolated_builder(self, name, audit_failure=False):
        tree = ast.parse(Path("ingestion.py").read_text())
        node = next(
            item for item in tree.body
            if isinstance(item, ast.FunctionDef) and item.name == name
        )
        audit = Mock(
            side_effect=RuntimeError("synthetic audit failure")
            if audit_failure else None
        )
        db_access = Mock(
            side_effect=AssertionError("Legacy builder reached database")
        )
        namespace = {
            "record_parlay_research_gate": audit,
            "log": Mock(),
            "SessionLocal": db_access,
        }
        module = ast.Module(body=[node], type_ignores=[])
        exec(compile(module, "isolated_builder", "exec"), namespace)
        namespace[name]([self.matchup])
        audit.assert_called_once()
        db_access.assert_not_called()

    def test_both_builders_stop_before_legacy_logic(self):
        for name in ("build_parlay", "build_tier_parlays"):
            with self.subTest(builder=name):
                self.isolated_builder(name)

    def test_audit_failure_does_not_enable_builders(self):
        for name in ("build_parlay", "build_tier_parlays"):
            with self.subTest(builder=name):
                self.isolated_builder(name, audit_failure=True)


if __name__ == "__main__":
    unittest.main()
