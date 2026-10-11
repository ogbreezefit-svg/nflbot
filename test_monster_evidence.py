import unittest
from datetime import datetime, timedelta, timezone

from frozen_player_features import BASE_FIELDS
from monster_evidence import experimental_candidates
from test_monster_inference import MonsterInferenceTests


class MonsterEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 10, 20, tzinfo=timezone.utc)
        fixture = MonsterInferenceTests()
        fixture.setUp()
        self.bundle = fixture.bundle
        self.evidence = {
            "feature_version": "moneyline-research-v1",
            "event_id": "event-1",
            "observation_key": "observation-1",
            "captured_at": self.now.isoformat(),
            "odds_observed_at": self.now.isoformat(),
            "market_last_update": self.now.isoformat(),
            "kickoff_time": (self.now + timedelta(hours=12)).isoformat(),
            "home": "Home Team",
            "away": "Away Team",
            "bookmaker_key": "test-book",
            "home_odds": -110,
            "away_odds": 100,
            "features": {field: 1.0 for field in BASE_FIELDS},
            "research_report": {
                "event_id": "event-1",
                "home": {"team_name": "Home Team"},
                "away": {"team_name": "Away Team"},
            },
        }

    def run_adapter(self):
        return experimental_candidates(
            self.evidence, self.bundle, now=self.now
        )

    def test_both_sides_remain_unapproved(self):
        result = self.run_adapter()
        self.assertEqual(len(result["candidates"]), 2)
        for candidate in result["candidates"]:
            self.assertFalse(candidate["prediction_approved"])
            self.assertFalse(candidate["research_qualified"])
            self.assertFalse(candidate["publication_approved"])
        home, away = result["candidates"]
        self.assertAlmostEqual(home["probability"], 0.7)
        self.assertAlmostEqual(away["probability"], 0.3)
        self.assertAlmostEqual(home["decimal_odds"], 1 + 100 / 110)
        self.assertAlmostEqual(away["decimal_odds"], 2.0)

    def test_stale_provider_quote_rejected(self):
        self.evidence["market_last_update"] = (
            self.now - timedelta(minutes=15)
        ).isoformat()
        with self.assertRaises(ValueError):
            self.run_adapter()

    def test_missing_provider_time_rejected(self):
        self.evidence["market_last_update"] = None
        with self.assertRaises(ValueError):
            self.run_adapter()

    def test_long_horizon_rejected(self):
        self.evidence["kickoff_time"] = (
            self.now + timedelta(days=4)
        ).isoformat()
        with self.assertRaises(ValueError):
            self.run_adapter()

    def test_event_mismatch_rejected(self):
        self.evidence["research_report"]["event_id"] = "other-event"
        with self.assertRaises(ValueError):
            self.run_adapter()

    def test_future_capture_rejected(self):
        self.evidence["captured_at"] = (
            self.now + timedelta(minutes=1)
        ).isoformat()
        with self.assertRaises(ValueError):
            self.run_adapter()


if __name__ == "__main__":
    unittest.main()
