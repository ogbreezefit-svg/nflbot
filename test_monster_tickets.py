import unittest
from jinja2 import Environment
from monster_ui import MONSTER_HERO_HTML


class MonsterTicketTests(unittest.TestCase):
    def render(self, tickets, available=True):
        return Environment(autoescape=True).from_string(
            MONSTER_HERO_HTML
        ).render(available=available, active_tickets=tickets)

    def ticket(self, number=1, outcome="PENDING", trial=True):
        return {
            "id": number, "is_trial": trial, "outcome": outcome,
            "legs": ["Home 1 moneyline", "Home 2 moneyline"],
            "stake": "$10.00", "payout": "$30.00",
            "created": "Test time",
        }

    def test_pending_ticket_shown(self):
        html = self.render([self.ticket()])
        self.assertIn("Ticket #1", html)
        self.assertIn("Home 1 moneyline", html)
        self.assertIn("$30.00", html)
        self.assertIn("Estimated simulated return", html)

    def test_newest_pending_ticket_selected(self):
        html = self.render([self.ticket(1), self.ticket(2)])
        self.assertIn("Ticket #2", html)
        self.assertNotIn("Ticket #1", html)

    def test_legacy_and_settled_tickets_excluded(self):
        html = self.render([
            self.ticket(1, trial=False),
            self.ticket(2, outcome="WON"),
        ])
        self.assertIn("Waiting for a weekly ticket.", html)
        self.assertNotIn("$30.00", html)

    def test_outage_hides_ticket(self):
        html = self.render([self.ticket()], available=False)
        self.assertNotIn("Ticket #1", html)
        self.assertNotIn("$30.00", html)

    def test_ticket_text_is_escaped(self):
        ticket = self.ticket()
        ticket["legs"] = ["<script>alert(1)</script>"]
        html = self.render([ticket])
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)


if __name__ == "__main__":
    unittest.main()
