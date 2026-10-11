import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from jinja2 import Environment
from dashboard_ui import build_dashboard_context, ticket_display
from monster_ui import MONSTER_HERO_HTML


class TrialDashboardMappingTests(unittest.TestCase):
    def slip(self, **changes):
        fields = {
            "id": 101,
            "category": "Trial 2-Leg",
            "odds": "3.0000x (+200)",
            "stake": "$10.00",
            "payout": "$30.00",
            "legs_json": json.dumps([
                "Home 1 Moneyline (-110)",
                "Home 2 Moneyline (+120)",
            ]),
            "status": "ACTIVE",
            "created_at": datetime.now(timezone.utc),
            "publication_mode": "TRIAL",
            "outcome": "PENDING",
            "paper_return": None,
            "paper_profit": None,
        }
        fields.update(changes)
        return SimpleNamespace(**fields)

    def test_trial_metadata_is_preserved(self):
        ticket = ticket_display(self.slip())
        self.assertTrue(ticket["is_trial"])
        self.assertEqual(ticket["outcome"], "PENDING")
        self.assertEqual(len(ticket["legs"]), 2)
        self.assertIn("Simulated", ticket["research_label"])

    def test_saved_trial_reaches_monster(self):
        context = build_dashboard_context([], [self.slip()])
        self.assertEqual(len(context["active_tickets"]), 1)
        html = Environment(autoescape=True).from_string(
            MONSTER_HERO_HTML
        ).render(available=True, **context)
        self.assertIn("Ticket #101", html)
        self.assertIn("Home 1 Moneyline", html)
        self.assertIn("Home 2 Moneyline", html)
        self.assertIn("$30.00", html)
        self.assertNotIn("Waiting for a weekly ticket.", html)

    def test_legacy_ticket_is_not_reclassified(self):
        ticket = ticket_display(self.slip(
            publication_mode=None, outcome="PENDING"
        ))
        self.assertFalse(ticket["is_trial"])
        self.assertEqual(ticket["outcome"], "UNTRACKED")
        self.assertEqual(
            ticket["research_label"], "Not research-qualified"
        )

    def test_missing_and_zero_returns_are_distinct(self):
        pending = ticket_display(self.slip())
        self.assertEqual(pending["paper_return"], "—")
        self.assertEqual(pending["paper_profit"], "—")

        lost = ticket_display(self.slip(
            outcome="LOST", paper_return=0.0, paper_profit=-10.0
        ))
        self.assertEqual(lost["outcome"], "LOST")
        self.assertEqual(lost["paper_return"], "$0.00")
        self.assertEqual(lost["paper_profit"], "$-10.00")


if __name__ == "__main__":
    unittest.main()
