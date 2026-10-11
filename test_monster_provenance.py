from datetime import datetime, timedelta, timezone
import unittest

from monster_policy import eligible_candidate, select_monster


class MonsterProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
        self.start = self.now
        self.end = self.now + timedelta(days=1)

    def candidate(self, number=1, **changes):
        row = {
            "event_id": f"event-{number}",
            "selection_key": f"event-{number}|h2h|Team {number}",
            "label": f"Team {number} moneyline",
            "market": "h2h",
            "kickoff": (self.now + timedelta(hours=4)).isoformat(),
            "quoted_at": (self.now - timedelta(minutes=2)).isoformat(),
            "probability": 0.8,
            "decimal_odds": 1.5,
            "research_qualified": True,
            "prediction_approved": True,
            "bookmaker_key": "synthetic-test-book",
            "observation_key": f"synthetic-observation-{number}",
        }
        row.update(changes)
        return row

    def test_eligible_leg_preserves_source_identity(self):
        leg = eligible_candidate(
            self.candidate(), self.now, self.start, self.end
        )
        self.assertIsNotNone(leg)
        self.assertEqual(leg["bookmaker_key"], "synthetic-test-book")
        self.assertEqual(
            leg["observation_key"], "synthetic-observation-1"
        )

    def test_missing_identity_is_not_invented(self):
        row = self.candidate()
        del row["bookmaker_key"]
        del row["observation_key"]
        leg = eligible_candidate(row, self.now, self.start, self.end)
        self.assertIsNotNone(leg)
        self.assertIsNone(leg["bookmaker_key"])
        self.assertIsNone(leg["observation_key"])

    def test_selected_ticket_preserves_identity_without_approval(self):
        result = select_monster(
            [self.candidate(i) for i in range(10)],
            now=self.now,
            slate_start=self.start,
            slate_end=self.end,
            min_ticket_probability=0.01,
        )
        self.assertEqual(result["status"], "CANDIDATE_ONLY")
        self.assertEqual(result["leg_count"], 10)
        self.assertIs(result["publication_approved"], False)
        for leg in result["legs"]:
            self.assertEqual(
                leg["bookmaker_key"], "synthetic-test-book"
            )
            self.assertTrue(leg["observation_key"])

    def test_experimental_candidates_stay_blocked(self):
        result = select_monster(
            [
                self.candidate(
                    i,
                    research_qualified=False,
                    prediction_approved=False,
                )
                for i in range(10)
            ],
            now=self.now,
            slate_start=self.start,
            slate_end=self.end,
            min_ticket_probability=0.01,
        )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["legs"], [])


if __name__ == "__main__":
    unittest.main()
