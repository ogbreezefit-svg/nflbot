import unittest
from trial_parlays import evaluate_ticket


class TrialSettlementTests(unittest.TestCase):
    def test_two_wins(self):
        self.assertEqual(
            evaluate_ticket([("WON", 100), ("WON", -200)], 10),
            ("WON", 30.0, 20.0),
        )

    def test_loss_with_pending_leg(self):
        self.assertEqual(
            evaluate_ticket([("LOST", -110), ("ACTIVE", 150)], 10),
            ("LOST", 0.0, -10.0),
        )

    def test_pending(self):
        self.assertEqual(
            evaluate_ticket([("WON", 100), ("ACTIVE", -110)], 10),
            ("PENDING", None, None),
        )

    def test_push_removes_leg(self):
        self.assertEqual(
            evaluate_ticket([("WON", 100), ("PUSH", -110)], 10),
            ("WON", 20.0, 10.0),
        )

    def test_all_pushes(self):
        self.assertEqual(
            evaluate_ticket([("PUSH", -110), ("PUSH", 100)], 10),
            ("PUSH", 10.0, 0.0),
        )

    def test_review_blocks_final_settlement(self):
        self.assertEqual(
            evaluate_ticket(
                [("LOST", -110), ("REVIEW_REQUIRED", 100)], 10
            ),
            ("REVIEW_REQUIRED", None, None),
        )

    def test_invalid_odds(self):
        self.assertEqual(
            evaluate_ticket([("WON", 0), ("WON", 100)], 10),
            ("REVIEW_REQUIRED", None, None),
        )

    def test_missing_stake(self):
        self.assertEqual(
            evaluate_ticket([("WON", 100), ("WON", 100)], None),
            ("REVIEW_REQUIRED", None, None),
        )


if __name__ == "__main__":
    unittest.main()
