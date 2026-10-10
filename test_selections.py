import unittest
from selection_tracker import grade_selection, selection_key, candidate_labels


class SelectionTests(unittest.TestCase):
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

    def test_spread_win_loss_push(self):
        for line, expected in [
            (-6.5, "WON"), (-7, "PUSH"), (-7.5, "LOST")
        ]:
            self.assertEqual(
                grade_selection(self.game(), "spreads", "Home", line)[0],
                expected,
            )

    def test_away_spread(self):
        self.assertEqual(
            grade_selection(self.game(), "spreads", "Away", 7.5)[0],
            "WON",
        )

    def test_over_under_push(self):
        for side, line, expected in [
            ("OVER", 40.5, "WON"),
            ("UNDER", 40.5, "LOST"),
            ("UNDER", 41.5, "WON"),
            ("OVER", 41, "PUSH"),
        ]:
            self.assertEqual(
                grade_selection(self.game(), "totals", side, line)[0],
                expected,
            )

    def test_moneyline_and_tie(self):
        self.assertEqual(
            grade_selection(self.game(), "h2h", "Away")[0], "LOST"
        )
        self.assertEqual(
            grade_selection(self.game(17, 17), "h2h", "Home")[0],
            "REVIEW_REQUIRED",
        )

    def test_live_game(self):
        self.assertIsNone(grade_selection(
            self.game(completed=False), "totals", "OVER", 40.5
        ))

    def test_missing_scores(self):
        game = self.game()
        game["scores"] = None
        self.assertIsNone(
            grade_selection(game, "spreads", "Home", -7)
        )

    def test_normalized_keys(self):
        self.assertEqual(
            selection_key("event", "spreads", "Home", -7),
            selection_key("event", "spreads", "Home", -7.0),
        )
        self.assertNotEqual(
            selection_key("event", "spreads", "Home", -7),
            selection_key("event", "spreads", "Home", -7.5),
        )
        self.assertEqual(
            selection_key("event", "h2h", "Home"),
            "oddsapi|event|h2h|Home",
        )

    def test_builder_label_mapping(self):
        matchup = {
            "home": "Home", "away": "Away",
            "home_ml": -150, "away_ml": 130,
            "home_spread": -3.5, "home_spread_odds": -110,
            "home_spread_odds_real": True,
            "total": 44.5, "total_odds": -110,
            "total_odds_real": True,
            "under_odds": -105, "under_odds_real": True,
        }
        labels = candidate_labels([matchup])
        for text in [
            "Home Moneyline (-150)",
            "Away Moneyline (+130) vs Home",
            "Home -3.5 (Bomb Anchor)",
            "Game Total: Away @ Home Over 44.5",
            "Fade: Away @ Home Under 44.5 (-105)",
            "Spread 2-Leg: Home -3.5",
            "Away vs Home Under 44.5",
        ]:
            self.assertEqual(len(labels[text]), 1)


if __name__ == "__main__":
    unittest.main()
