import unittest
from player_stats import normalize_player, numeric


class PlayerStatsTests(unittest.TestCase):
    def player(self):
        return {
            "playerID": "2578570",
            "longName": "Sample QB",
            "pos": "QB",
            "team": "ARI",
            "injury": {},
            "stats": {
                "gamesPlayed": "4",
                "teamAbv": "ARI",
                "Passing": {
                    "passYds": "818.0",
                    "passAttempts": "152.0",
                    "passTD": "6.0",
                },
            },
        }

    def test_per_game(self):
        result = normalize_player(self.player())
        self.assertEqual(result["games_played"], 4)
        self.assertEqual(result["per_game"]["Passing"]["passYds"], 204.5)
        self.assertEqual(result["per_game"]["Passing"]["passAttempts"], 38)
        self.assertTrue(result["per_game_ready"])

    def test_empty_stats_are_unknown(self):
        player = self.player()
        player["stats"] = {}
        result = normalize_player(player)
        self.assertFalse(result["has_numeric_season_stats"])
        self.assertIsNone(result["games_played"])

    def test_missing_denominator(self):
        player = self.player()
        del player["stats"]["gamesPlayed"]
        result = normalize_player(player)
        self.assertIsNone(result["per_game"]["Passing"]["passYds"])
        self.assertFalse(result["per_game_ready"])

    def test_zero_denominator(self):
        player = self.player()
        player["stats"]["gamesPlayed"] = "0"
        self.assertIsNone(normalize_player(player)["games_played"])

    def test_unknown_is_not_zero(self):
        self.assertIsNone(numeric(""))
        self.assertIsNone(numeric(None))
        self.assertIsNone(numeric("nan"))
        self.assertIsNone(numeric(True))
        self.assertEqual(numeric("0"), 0)

    def test_missing_id_rejected(self):
        player = self.player()
        del player["playerID"]
        with self.assertRaises(ValueError):
            normalize_player(player)

    def test_availability_not_invented(self):
        result = normalize_player(self.player())
        self.assertFalse(result["availability_verified"])
        self.assertFalse(result["starting_role_verified"])
        self.assertIsNone(result["injury"]["designation"])


if __name__ == "__main__":
    unittest.main()
