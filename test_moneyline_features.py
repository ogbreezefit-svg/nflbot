import unittest
from datetime import datetime, timedelta, timezone
from moneyline_features import build_observation


class MoneylineFeatureTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.matchup = {
            "event_id": "synthetic-event",
            "home": "Test Home",
            "away": "Test Away",
            "home_ml": -150,
            "away_ml": 130,
            "bookmaker_key": "synthetic-book",
            "odds_observed_at": self.now.isoformat(),
            "commence_time": (
                self.now + timedelta(days=1)
            ).isoformat(),
            "h2h_market_last_update": (
                self.now - timedelta(minutes=1)
            ).isoformat(),
            "h2h_raw_outcomes": [
                {"name": "Test Home", "price": -150},
                {"name": "Test Away", "price": 130},
            ],
        }
        self.report = {
            "event_id": "synthetic-event",
            "team_source_fetched_at": self.now.isoformat(),
            "home": {
                "team_name": "Test Home",
                "rates": {"passing_yards_per_attempt": 8},
            },
            "away": {
                "team_name": "Test Away",
                "rates": {"passing_yards_per_attempt": 7},
            },
        }

    def build(self):
        return build_observation(
            self.matchup, self.report, self.now, self.now
        )

    def test_features_are_not_predictions(self):
        result = self.build()
        self.assertEqual(
            result["features"]["home_minus_away_passing_yards_per_attempt"],
            1,
        )
        self.assertIsNone(result["research_model_probability"])
        self.assertEqual(result["selection_decision"], "NOT_ASSESSED")
        self.assertFalse(
            result["market_baseline"]["is_research_model_prediction"]
        )

    def test_source_price_mismatch_rejected(self):
        self.matchup["home_ml"] = -200
        with self.assertRaises(ValueError):
            self.build()

    def test_started_game_rejected(self):
        self.matchup["commence_time"] = self.now.isoformat()
        with self.assertRaises(ValueError):
            self.build()

    def test_team_mismatch_rejected(self):
        self.report["home"]["team_name"] = "Other Team"
        with self.assertRaises(ValueError):
            self.build()

    def test_missing_market_timestamp_not_invented(self):
        self.matchup["h2h_market_last_update"] = None
        result = self.build()
        self.assertIsNone(result["market_last_update"])
        self.assertFalse(result["provider_market_timestamp_verified"])

    def test_frozen_report_detached_from_caller(self):
        result = self.build()
        self.report["home"]["rates"]["passing_yards_per_attempt"] = 99
        self.assertEqual(
            result["research_report"]["home"]["rates"]
            ["passing_yards_per_attempt"],
            8,
        )

    def test_stable_hourly_key(self):
        first = self.build()
        self.matchup["home_ml"] = -160
        self.matchup["h2h_raw_outcomes"][0]["price"] = -160
        second = self.build()
        self.assertEqual(
            first["observation_key"], second["observation_key"]
        )

    def test_market_baseline_sums_to_one(self):
        baseline = self.build()["market_baseline"]
        self.assertAlmostEqual(
            baseline["normalized_implied_home_share"]
            + baseline["normalized_implied_away_share"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
