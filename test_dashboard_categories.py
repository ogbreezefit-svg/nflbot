import ast
import unittest
from pathlib import Path

from jinja2 import Environment
from dashboard_ui import build_dashboard_context


def dashboard_template():
    tree = ast.parse(Path("dashboard.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "HTML_TEMPLATE"
            for target in node.targets
        ):
            if isinstance(node.value, ast.Constant):
                return node.value.value
    raise AssertionError("Template not found")


class DashboardCategoryTests(unittest.TestCase):
    def ticket(self, number, category, trial=False):
        return {
            "id": number,
            "category": category,
            "is_trial": trial,
            "legs": [f"Selection {number}"],
            "odds": "+200",
            "stake": "$10.00",
            "payout": "$30.00",
            "display_status": "ACTIVE",
            "outcome": "PENDING" if trial else "UNTRACKED",
            "research_label": (
                "Trial · Not validated · Simulated"
                if trial else "Not research-qualified"
            ),
            "created": "Test time",
        }

    def render(self, tickets=()):
        context = build_dashboard_context([], [])
        context["active_tickets"] = list(tickets)
        context["micro_tickets"] = [
            self.ticket(104, "Micro Sandbox")
        ]
        context["straight_more"] = [{
            "game": "Additional tracked game",
            "pick": "Additional tracked selection",
            "odds": "+110",
            "kickoff": "Test time",
            "status": "ACTIVE",
        }]
        return Environment(autoescape=True).from_string(
            dashboard_template()
        ).render(available=True, **context)

    def test_all_requested_sections_are_visible(self):
        html = self.render([
            self.ticket(101, "Standard Cap"),
            self.ticket(102, "Booster Matrix"),
            self.ticket(103, "Bomb Target"),
            self.ticket(105, "Trial 2-Leg", trial=True),
        ])
        for title in (
            "Micro Parlays", "Standard Parlays", "Boosted Parlays",
            "Bomb Parlays", "Trial Parlays", "Tracked Picks",
        ):
            self.assertIn(title, html)
        for number in range(101, 106):
            self.assertIn(f"Ticket #{number}", html)
        self.assertIn("Additional tracked selection", html)
        self.assertNotIn("Show 1 more picks", html)

    def test_empty_categories_keep_their_headings(self):
        html = self.render()
        for title in ("Standard Parlays", "Boosted Parlays", "Bomb Parlays"):
            self.assertIn(title, html)
        self.assertIn("No active saved tickets in this category.", html)

    def test_other_saved_category_is_not_hidden(self):
        html = self.render([self.ticket(106, "Legacy Special")])
        self.assertIn("Other Saved Parlays", html)
        self.assertIn("Ticket #106", html)


if __name__ == "__main__":
    unittest.main()
