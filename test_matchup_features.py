import unittest
from matchup_features import (
    ratio, resolve_team, team_features, build_matchup_report
)


class MatchupFeatureTests(unittest.TestCase):
    def team(self):
        return {
            "teamID": "1", "teamAbv": "ARI",
            "teamCity": "Arizona", "teamName": "Cardinals",
            "wins": "2", "loss": "2", "tie": "0",
            "pf": "90", "pa": "85",
            "teamStats": {
                "Passing": {
                    "passYds": "800", "passAttempts": "100",
                    "passCompletions": "65",
                },
                "Rushing": {"rushYds": "400", "carries": "80"},
                "Defense": {"passingYardsAllowed": "700"},
            },
        }

    def test_rates(self):
        result = team_features(self.team())
        self.assertEqual(result["rates"]["passing_yards_per_attempt"], 8)
        self.assertEqual(result["rates"]["completion_percentage"], 65)
        self.assertEqual(result["rates"]["rushing_yards_per_carry"], 5)

    def test_missing_denominator(self):
        self.assertIsNone(ratio(800, None))
        self.assertIsNone(ratio(800, 0))

    def test_missing_is_not_zero(self):
        team = self.team()
        del team["teamStats"]["Passing"]["passAttempts"]
        self.assertIsNone(
            team_features(team)["rates"]["passing_yards_per_attempt"]
        )

    def test_exact_team_mapping(self):
        self.assertIsNotNone(
            resolve_team("Arizona Cardinals", [self.team()])
        )
        self.assertIsNone(resolve_team("Arizona", [self.team()]))

    def test_ambiguous_mapping_rejected(self):
        self.assertIsNone(
            resolve_team("Arizona Cardinals", [self.team(), self.team()])
        )

    def test_missing_opponent(self):
        report = build_matchup_report(
            {"event_id": "event", "home": "Arizona Cardinals", "away": "Unknown"},
            [self.team()],
        )
        self.assertEqual(report["team_evidence_status"], "INCOMPLETE")
        self.assertEqual(report["recommendation_readiness"], "INCOMPLETE")

    def test_no_unverified_per_game_rates(self):
        result = team_features(self.team())
        self.assertFalse(result["stats_standings_cutoff_verified"])
        self.assertNotIn("points_per_game", result["rates"])


if __name__ == "__main__":
    unittest.main()
