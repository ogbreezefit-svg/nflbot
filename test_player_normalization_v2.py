import unittest
from player_stats import normalize_player


class PlayerNormalizationV2Tests(unittest.TestCase):
    def player(self, category, values, games="4", injury=None):
        return {
            "playerID": "synthetic-test-player",
            "teamAbv": "TEST",
            "teamID": "synthetic-team",
            "pos": "QB",
            "stats": {
                "gamesPlayed": games,
                category: values,
            },
            "injury": injury or {},
        }

    def test_additive_passing_fields(self):
        result = normalize_player(self.player("Passing", {
            "passYds": "800",
            "passAttempts": "100",
            "passCompletions": "60",
        }))
        self.assertEqual(result["per_game"]["Passing"]["passYds"], 200)
        self.assertEqual(result["per_game"]["Passing"]["passAttempts"], 25)
        self.assertTrue(result["per_game_ready"])

    def test_nonadditive_fields_not_divided(self):
        result = normalize_player(self.player("Passing", {
            "passYds": "800",
            "completionPercentage": "60",
            "passerRating": "95",
            "longestPass": "70",
        }))
        self.assertNotIn(
            "completionPercentage", result["per_game"]["Passing"]
        )
        self.assertNotIn("passerRating", result["per_game"]["Passing"])
        self.assertNotIn("longestPass", result["per_game"]["Passing"])
        self.assertEqual(
            result["season_totals"]["Passing"]["passerRating"], 95
        )

    def test_rates_only_not_per_game_ready(self):
        result = normalize_player(self.player("Passing", {
            "passerRating": "95",
        }))
        self.assertTrue(result["has_numeric_season_stats"])
        self.assertFalse(result["per_game_ready"])

    def test_roster_team_uses_abbreviation(self):
        player = self.player("Passing", {"passYds": "800"})
        player["team"] = "Other display label"
        result = normalize_player(player)
        self.assertEqual(result["roster_team"], "TEST")
        self.assertEqual(result["roster_team_id"], "synthetic-team")

    def test_no_injury_does_not_mean_cleared(self):
        result = normalize_player(
            self.player("Passing", {"passYds": "800"})
        )
        self.assertEqual(result["availability_evidence_status"], "UNKNOWN")
        self.assertFalse(result["availability_verified"])
        self.assertFalse(result["starting_role_verified"])
        self.assertFalse(result["recent_usage_verified"])

    def test_designation_is_evidence_not_verification(self):
        result = normalize_player(self.player(
            "Passing",
            {"passYds": "800"},
            injury={"designation": "Questionable"},
        ))
        self.assertEqual(
            result["availability_evidence_status"],
            "REPORTED_DESIGNATION_NOT_VERIFIED",
        )
        self.assertFalse(result["availability_verified"])

    def test_missing_games_preserves_totals(self):
        result = normalize_player(self.player(
            "Rushing", {"rushYds": "400", "carries": "80"}, games=None
        ))
        self.assertEqual(result["season_totals"]["Rushing"]["rushYds"], 400)
        self.assertIsNone(result["per_game"]["Rushing"]["rushYds"])
        self.assertFalse(result["per_game_ready"])


if __name__ == "__main__":
    unittest.main()
