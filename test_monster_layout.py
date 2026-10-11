import unittest
from jinja2 import Environment
from monster_ui import MONSTER_HERO_HTML


class MonsterLayoutTests(unittest.TestCase):
    def ticket(self, number, monster=False):
        return {
            "id": number,
            "is_monster": monster,
            "publication_approved": monster,
            "is_trial": not monster,
            "outcome": "PENDING",
            "legs": [f"Leg {i}" for i in range(10 if monster else 2)],
            "stake": "$10.00",
            "payout": "$100.00",
            "odds": "+900",
            "research_label": "Synthetic test qualification",
            "created": "Test time",
        }

    def render(self, tickets, available=True):
        return Environment(autoescape=True).from_string(
            MONSTER_HERO_HTML
        ).render(active_tickets=tickets, available=available)

    def main(self, html):
        return html.split('id="monster-main-ticket"', 1)[1].split(
            '<aside', 1
        )[0]

    def test_trial_only_is_side_not_main(self):
        html = self.render([self.ticket(1)])
        self.assertIn("Ticket #1", html)
        self.assertIn("Featured Side Bet", html)
        self.assertNotIn("Ticket #1", self.main(html))
        self.assertIn("Waiting for a qualifying Monster.", self.main(html))
        self.assertIn("Not validated", html)

    def test_monster_and_side_are_separate(self):
        html = self.render([self.ticket(2, True), self.ticket(1)])
        self.assertIn("#2", self.main(html))
        self.assertNotIn("Ticket #1", self.main(html))
        self.assertIn("Ticket #1", html)

    def test_unapproved_monster_not_featured(self):
        ticket = self.ticket(2, True)
        ticket["publication_approved"] = False
        self.assertIn(
            "Waiting for a qualifying Monster.",
            self.main(self.render([ticket])),
        )

    def test_short_monster_not_featured(self):
        ticket = self.ticket(2, True)
        ticket["legs"] = ["One", "Two"]
        self.assertIn(
            "Waiting for a qualifying Monster.",
            self.main(self.render([ticket])),
        )

    def test_outage_hides_both_tickets(self):
        html = self.render(
            [self.ticket(2, True), self.ticket(1)], available=False
        )
        self.assertNotIn("Ticket #1", html)
        self.assertNotIn("has-ticket", self.main(html))

    def test_side_leg_text_is_escaped(self):
        ticket = self.ticket(1)
        ticket["legs"][0] = "<script>alert(1)</script>"
        html = self.render([ticket])
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)


if __name__ == "__main__":
    unittest.main()
