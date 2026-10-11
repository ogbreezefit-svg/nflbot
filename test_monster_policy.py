import unittest
from datetime import datetime, timedelta, timezone

from monster_policy import select_monster


class MonsterPolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 10, 20, tzinfo=timezone.utc)

    def candidate(self, number, **changes):
        row = {
            "event_id": f"event-{number}",
            "selection_key": f"event-{number}|h2h|home",
            "label": f"Team {number} moneyline",
            "market": "h2h",
            "research_qualified": True,
            "prediction_approved": True,
            "kickoff": self.now + timedelta(days=1),
            "quoted_at": self.now,
            "probability": 0.7,
            "decimal_odds": 1.6,
        }
        row.update(changes)
        return row

    def select(self, rows, floor=0.001):
        return select_monster(
            rows, now=self.now,
            slate_start=self.now - timedelta(days=1),
            slate_end=self.now + timedelta(days=6),
            min_ticket_probability=floor,
        )

    def test_ten_qualified_legs_produce_candidate_not_publication(self):
        result = self.select([self.candidate(i) for i in range(10)])
        self.assertEqual(result["status"], "CANDIDATE_ONLY")
        self.assertEqual(result["leg_count"], 10)
        self.assertFalse(result["publication_approved"])

    def test_nine_legs_blocked(self):
        result = self.select([self.candidate(i) for i in range(9)])
        self.assertEqual(result["status"], "BLOCKED")

    def test_unapproved_prediction_excluded(self):
        rows = [self.candidate(i) for i in range(10)]
        rows[0]["prediction_approved"] = False
        self.assertEqual(self.select(rows)["status"], "BLOCKED")

    def test_incomplete_research_excluded(self):
        rows = [self.candidate(i) for i in range(10)]
        rows[0]["research_qualified"] = False
        self.assertEqual(self.select(rows)["status"], "BLOCKED")

    def test_same_event_not_counted_twice(self):
        rows = [self.candidate(i) for i in range(9)]
        rows.append(self.candidate(0, selection_key="alternate-side"))
        self.assertEqual(self.select(rows)["status"], "BLOCKED")

    def test_started_game_excluded(self):
        rows = [self.candidate(i) for i in range(10)]
        rows[0]["kickoff"] = self.now
        self.assertEqual(self.select(rows)["status"], "BLOCKED")

    def test_stale_price_excluded(self):
        rows = [self.candidate(i) for i in range(10)]
        rows[0]["quoted_at"] = self.now - timedelta(minutes=15)
        self.assertEqual(self.select(rows)["status"], "BLOCKED")

    def test_non_positive_value_excluded(self):
        rows = [self.candidate(i) for i in range(10)]
        rows[0]["decimal_odds"] = 1.2
        self.assertEqual(self.select(rows)["status"], "BLOCKED")

    def test_probability_floor_blocks_ticket(self):
        result = self.select(
            [self.candidate(i) for i in range(10)], floor=0.5
        )
        self.assertEqual(result["reason"], "TICKET_PROBABILITY_FLOOR_NOT_MET")

    def test_maximum_thirty_legs(self):
        result = self.select(
            [self.candidate(i) for i in range(40)], floor=0.000001
        )
        self.assertEqual(result["leg_count"], 30)

    def test_other_market_excluded(self):
        rows = [self.candidate(i) for i in range(10)]
        rows[0]["market"] = "player_props"
        self.assertEqual(self.select(rows)["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
