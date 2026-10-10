import copy
import unittest
from datetime import datetime, timezone, timedelta
from frozen_player_features import extract_player_news_features, leader_rate

class FrozenPlayerFeatureTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.player = {"player_id": "test-qb", "position": "QB", "roster_team": "HOM",
                       "stats_team": "HOM", "injury": {"designation": "Questionable"},
                       "season_totals": {"Passing": {"passYds": 800, "passAttempts": 100}}}
        self.home = {"team_abv": "HOM", "player_evidence": {
            "status": "FRESH", "usable_for_current_research": True,
            "source_fetched_at": self.now.isoformat(), "players": [self.player]},
            "news_evidence": {"status": "AVAILABLE", "collected_at": self.now.isoformat(),
                "articles": [{"matched_player_id": "test-qb"}, {"matched_player_id": "test-qb"}]}}
        self.away = copy.deepcopy(self.home)
        self.away["team_abv"] = "AWY"
        p = self.away["player_evidence"]["players"][0]
        p["roster_team"] = p["stats_team"] = "AWY"
        p["season_totals"]["Passing"]["passYds"] = 700
        p["injury"] = {}
        self.away["news_evidence"]["articles"] = []
        self.evidence = {"captured_at": self.now.isoformat(),
                         "research_report": {"home": self.home, "away": self.away}}
    def test_player_efficiency_difference(self):
        result = extract_player_news_features(self.evidence)
        self.assertEqual(result["home_minus_away_passing_volume_leader_yards_per_attempt"], 1)
    def test_reported_designation_is_not_medical_verification(self):
        result = extract_player_news_features(self.evidence)
        self.assertEqual(result["home_minus_away_reported_designation_fraction"], 1)
        self.assertNotIn("availability_verified", result)
    def test_news_counts_unique_players_not_duplicate_articles(self):
        result = extract_player_news_features(self.evidence)
        self.assertEqual(result["home_minus_away_observed_news_player_count"], 1)
    def test_missing_news_is_missing_not_zero(self):
        self.away.pop("news_evidence")
        self.assertIsNone(extract_player_news_features(self.evidence)[
            "home_minus_away_observed_news_player_count"])
    def test_future_news_is_not_used(self):
        self.home["news_evidence"]["collected_at"] = (self.now+timedelta(seconds=1)).isoformat()
        self.assertIsNone(extract_player_news_features(self.evidence)[
            "home_minus_away_observed_news_player_count"])
    def test_future_player_snapshot_is_not_used(self):
        self.home["player_evidence"]["source_fetched_at"] = (self.now+timedelta(seconds=1)).isoformat()
        self.assertIsNone(extract_player_news_features(self.evidence)[
            "home_minus_away_passing_volume_leader_yards_per_attempt"])
    def test_unknown_stat_team_is_not_assumed_current_team(self):
        self.player["stats_team"] = None
        self.assertIsNone(extract_player_news_features(self.evidence)[
            "home_minus_away_passing_volume_leader_yards_per_attempt"])
    def test_tied_volume_leader_not_chosen_by_efficiency(self):
        second = copy.deepcopy(self.player)
        second["season_totals"]["Passing"]["passYds"] = 999
        self.assertIsNone(leader_rate([self.player, second], "HOM", "Passing",
                                     "passYds", "passAttempts", {"QB"}))
    def test_missing_rushing_not_converted_to_zero(self):
        self.assertIsNone(extract_player_news_features(self.evidence)[
            "home_minus_away_rushing_volume_leader_yards_per_carry"])
    def test_frozen_report_never_mutated(self):
        before = copy.deepcopy(self.evidence)
        extract_player_news_features(self.evidence)
        self.assertEqual(before, self.evidence)

if __name__ == "__main__":
    unittest.main()
