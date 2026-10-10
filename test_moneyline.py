import unittest
from nfl_moneyline import grade_moneyline, valid_odds


class MoneylineTests(unittest.TestCase):
    def game(self, home=24, away=17, completed=True):
        return {
            "completed": completed,
            "home_team": "Home",
            "away_team": "Away",
            "scores": [
                {"name": "Home", "score": str(home)},
                {"name": "Away", "score": str(away)},
            ],
        }

    def test_positive_odds_win(self):
        self.assertEqual(
            grade_moneyline(self.game(), "Home", 150, 50),
            ("WON", 125.0, 75.0),
        )

    def test_negative_odds_win(self):
        self.assertEqual(
            grade_moneyline(self.game(), "Home", -200, 50),
            ("WON", 75.0, 25.0),
        )

    def test_loss(self):
        self.assertEqual(
            grade_moneyline(self.game(), "Away", 150, 50),
            ("LOST", 0.0, -50.0),
        )

    def test_live_game_not_settled(self):
        self.assertIsNone(grade_moneyline(
            self.game(completed=False), "Home", 150, 50
        ))

    def test_tie_requires_review(self):
        self.assertEqual(
            grade_moneyline(self.game(17, 17), "Home", 150, 50),
            ("REVIEW_REQUIRED", None, None),
        )

    def test_invalid_or_missing_scores(self):
        game = self.game()
        game["scores"] = None
        self.assertIsNone(
            grade_moneyline(game, "Home", 150, 50)
        )
        game = self.game()
        game["scores"][0]["score"] = "invalid"
        self.assertIsNone(
            grade_moneyline(game, "Home", 150, 50)
        )

    def test_invalid_team(self):
        self.assertIsNone(
            grade_moneyline(self.game(), "Other", 150, 50)
        )

    def test_invalid_odds_and_stakes(self):
        for odds in [0, 99, None, float("nan"), float("inf")]:
            self.assertFalse(valid_odds(odds))
        for stake in [0, -50, None, float("nan")]:
            self.assertIsNone(
                grade_moneyline(self.game(), "Home", 150, stake)
            )

    def test_cent_rounding(self):
        self.assertEqual(
            grade_moneyline(self.game(), "Home", -110, 50),
            ("WON", 95.45, 45.45),
        )


if __name__ == "__main__":
    unittest.main()
