import copy
import math
import unittest
from datetime import datetime, timedelta, timezone

from moneyline_evaluation import (
    select_observations,
    validate_selected,
    probability_metrics,
)


class MoneylineEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.captured = self.now - timedelta(hours=6)
        self.kickoff = self.now - timedelta(hours=4)
        self.record = {
            "observation_key": "synthetic-observation",
            "event_id": "synthetic-event",
            "captured_at": self.captured.isoformat(),
            "home_pick_key": "synthetic-pick",
            "pick_matches": 1,
            "pick": {
                "pick_key": "synthetic-pick",
                "event_id": "synthetic-event",
                "market_key": "h2h",
                "pick_side": "Test Home",
                "status": "WON",
                "kickoff_time": self.kickoff.isoformat(),
                "settled_at": (
                    self.now - timedelta(hours=1)
                ).isoformat(),
            },
        }
        self.evidence = {
            "observation_key": "synthetic-observation",
            "event_id": "synthetic-event",
            "captured_at": self.captured.isoformat(),
            "odds_observed_at": self.captured.isoformat(),
            "market_last_update": (
                self.captured - timedelta(minutes=1)
            ).isoformat(),
            "home": "Test Home",
            "away": "Test Away",
            "bookmaker_key": "synthetic-book",
            "home_odds": -150,
            "away_odds": 130,
            "features": {},
            "feature_version": "test",
        }

    def test_pending_not_used(self):
        self.record["pick"]["status"] = "ACTIVE"
        rows, _ = select_observations([self.record], self.now)
        self.assertEqual(rows, [])

    def test_ambiguous_selection_not_used(self):
        self.record["pick_matches"] = 2
        rows, _ = select_observations([self.record], self.now)
        self.assertEqual(rows, [])

    def test_one_latest_observation_per_game(self):
        older = copy.deepcopy(self.record)
        older["observation_key"] = "older"
        older["captured_at"] = (
            self.captured - timedelta(hours=1)
        ).isoformat()
        rows, _ = select_observations([older, self.record], self.now)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["observation_key"], "synthetic-observation"
        )

    def test_too_close_to_kickoff_not_used(self):
        self.record["captured_at"] = (
            self.kickoff - timedelta(minutes=30)
        ).isoformat()
        rows, _ = select_observations([self.record], self.now)
        self.assertEqual(rows, [])

    def test_missing_market_timestamp_rejected(self):
        self.evidence["market_last_update"] = None
        with self.assertRaises(ValueError):
            validate_selected(self.record, self.evidence)

    def test_stale_provider_quote_rejected(self):
        self.evidence["market_last_update"] = (
            self.captured - timedelta(hours=2)
        ).isoformat()
        with self.assertRaises(ValueError):
            validate_selected(self.record, self.evidence)

    def test_valid_row_has_outcome_not_simulated_profit(self):
        row = validate_selected(self.record, self.evidence)
        self.assertEqual(row["home_won"], 1)
        self.assertNotIn("realized_profit", row)

    def test_probability_metrics(self):
        result = probability_metrics([1], [0.75])
        self.assertAlmostEqual(result["brier_score"], 0.0625)
        self.assertAlmostEqual(result["log_loss"], -math.log(0.75))
        self.assertIsNone(probability_metrics([], []))


if __name__ == "__main__":
    unittest.main()
