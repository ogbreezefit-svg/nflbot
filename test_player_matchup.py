import json
import unittest
from datetime import datetime, timedelta, timezone
from player_matchup import summarize_player_snapshot


class PlayerMatchupTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.player = {
            "playerID": "synthetic-player",
            "teamAbv": "TEST",
            "pos": "QB",
            "stats": {
                "gamesPlayed": "4",
                "Passing": {
                    "passYds": "800",
                    "passAttempts": "100",
                    "passerRating": "95",
                },
            },
            "injury": {},
        }

    def payload(self, players=None):
        return json.dumps({
            "raw_offensive_roster": (
                [self.player] if players is None else players
            )
        })

    def summary(self, payload=None, fetched_at=None):
        return summarize_player_snapshot(
            self.payload() if payload is None else payload,
            self.now - timedelta(hours=1)
            if fetched_at is None else fetched_at,
            self.now,
            "TEST",
        )

    def test_missing_snapshot(self):
        result = summarize_player_snapshot(None, None, self.now, "TEST")
        self.assertEqual(result["status"], "MISSING")
        self.assertFalse(result["usable_for_current_research"])

    def test_fresh_snapshot_uses_corrected_normalizer(self):
        result = self.summary()
        self.assertEqual(result["status"], "FRESH")
        self.assertTrue(result["usable_for_current_research"])
        player = result["players"][0]
        self.assertEqual(player["per_game"]["Passing"]["passYds"], 200)
        self.assertNotIn("passerRating", player["per_game"]["Passing"])
        self.assertEqual(result["recommendation_readiness"], "INCOMPLETE")

    def test_stale_snapshot_is_not_usable(self):
        result = self.summary(
            fetched_at=self.now - timedelta(hours=24)
        )
        self.assertEqual(result["status"], "STALE")
        self.assertFalse(result["usable_for_current_research"])

    def test_future_timestamp_rejected(self):
        result = self.summary(
            fetched_at=self.now + timedelta(minutes=1)
        )
        self.assertEqual(result["status"], "INVALID")

    def test_invalid_json(self):
        self.assertEqual(self.summary(payload="not-json")["status"], "INVALID")

    def test_wrong_team_rejected(self):
        self.player["teamAbv"] = "OTHER"
        result = self.summary()
        self.assertEqual(result["status"], "TEAM_MISMATCH")
        self.assertFalse(result["usable_for_current_research"])

    def test_injury_does_not_verify_availability(self):
        self.player["injury"] = {"designation": "Questionable"}
        result = self.summary()
        self.assertEqual(result["players_with_reported_designations"], 1)
        self.assertFalse(result["availability_verified"])
        self.assertFalse(result["players"][0]["availability_verified"])

    def test_duplicate_players_rejected(self):
        result = self.summary(
            payload=self.payload([self.player, self.player])
        )
        self.assertEqual(result["status"], "INVALID")


if __name__ == "__main__":
    unittest.main()
