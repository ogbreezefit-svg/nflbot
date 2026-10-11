import json
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from jinja2 import Environment
from dashboard_ui import ticket_display
from monster_ui import MONSTER_HERO_HTML


class MonsterDashboardMappingTests(unittest.TestCase):
    def slip(self, **changes):
        values = {
            "id": 900,
            "category": "Weekly Monster",
            "odds": "+900",
            "stake": "$10.00",
            "payout": "$100.00",
            "legs_json": json.dumps(
                [f"Test leg {i}" for i in range(10)]
            ),
            "status": "ACTIVE",
            "created_at": datetime(2026, 10, 10, tzinfo=timezone.utc),
            "publication_mode": "MONSTER",
            "outcome": "PENDING",
            "research_qualified": True,
            "prediction_approved": True,
            "publication_approved": True,
            "publication_approval_ref": "synthetic-test-approval",
        }
        values.update(changes)
        return SimpleNamespace(**values)

    def render(self, ticket):
        return Environment(autoescape=True).from_string(
            MONSTER_HERO_HTML
        ).render(available=True, active_tickets=[ticket])

    def test_approved_monster_is_featured(self):
        ticket = ticket_display(self.slip())
        self.assertTrue(ticket["is_monster"])
        self.assertTrue(ticket["publication_approved"])
        self.assertEqual(ticket["outcome"], "PENDING")
        self.assertIn("Monster · Pending", self.render(ticket))

    def test_each_approval_flag_must_be_exactly_true(self):
        for field in (
            "research_qualified",
            "prediction_approved",
            "publication_approved",
        ):
            for value in (False, None, "True", 1):
                with self.subTest(field=field, value=value):
                    ticket = ticket_display(
                        self.slip(**{field: value})
                    )
                    self.assertFalse(ticket["publication_approved"])
                    self.assertNotIn(
                        "Monster · Pending", self.render(ticket)
                    )

    def test_reference_must_be_nonblank_string(self):
        for value in (None, "", "   ", 123):
            with self.subTest(value=value):
                ticket = ticket_display(
                    self.slip(publication_approval_ref=value)
                )
                self.assertFalse(ticket["publication_approved"])

    def test_category_does_not_promote_legacy_ticket(self):
        slip = self.slip(publication_mode=None)
        for field in (
            "research_qualified",
            "prediction_approved",
            "publication_approved",
            "publication_approval_ref",
        ):
            delattr(slip, field)
        ticket = ticket_display(slip)
        self.assertFalse(ticket["is_monster"])
        self.assertFalse(ticket["publication_approved"])
        self.assertEqual(ticket["outcome"], "UNTRACKED")
        self.assertEqual(
            ticket["research_label"], "Not research-qualified"
        )

    def test_trial_behavior_is_preserved(self):
        ticket = ticket_display(self.slip(
            publication_mode="TRIAL",
            legs_json=json.dumps(["First leg", "Second leg"]),
        ))
        self.assertTrue(ticket["is_trial"])
        self.assertFalse(ticket["is_monster"])
        self.assertFalse(ticket["publication_approved"])
        self.assertEqual(ticket["outcome"], "PENDING")
        self.assertIn("Not validated", ticket["research_label"])
        self.assertIn("Ticket #900", self.render(ticket))
        self.assertNotIn("Monster · Pending", self.render(ticket))

    def test_settled_monster_is_not_featured(self):
        ticket = ticket_display(self.slip(outcome="WON"))
        self.assertEqual(ticket["outcome"], "WON")
        self.assertNotIn("Monster · Pending", self.render(ticket))

    def test_short_monster_is_not_featured(self):
        ticket = ticket_display(self.slip(
            legs_json=json.dumps(["First leg", "Second leg"]),
        ))
        self.assertNotIn("Monster · Pending", self.render(ticket))


if __name__ == "__main__":
    unittest.main()
