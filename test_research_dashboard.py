"""No import of dashboard: avoids initialization and background scheduling."""
import ast
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
try:
    from flask import Flask, render_template_string
except ImportError:
    Flask = None
    from jinja2 import Environment
from research_dashboard import make_research_status, unavailable_research_status

ROOT = Path(__file__).resolve().parent

def template_value():
    tree = ast.parse((ROOT / "dashboard.py").read_text())
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "HTML_TEMPLATE" for t in n.targets))
    return ast.literal_eval(node.value)

def render(status, available=True, ticket=None):
    context = {
        "research": status, "available": available,
        "week_label": "Synthetic test week", "timestamp": "Test time",
        "straight_count": 0, "pending_selections": 0, "record": "0–0–0",
        "win_rate": "—", "review_count": 0,
        "active_tickets": [ticket] if ticket else [], "micro_tickets": [],
        "straight_preview": [], "straight_more": [], "games": [],
        "weekly_summary": {"weeks": []},
        "ticket_history": [ticket] if ticket else [], "undated": 0,
    }
    if Flask is None:
        return Environment(autoescape=True).from_string(template_value()).render(**context)
    app = Flask("isolated-research-dashboard-test")
    with app.app_context():
        return render_template_string(template_value(), **context)

class ResearchDashboardTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
    def audit(self, reasons, age=1):
        return SimpleNamespace(assessed_at=self.now-timedelta(hours=age),
                               decision_json=json.dumps({"reasons": reasons}))
    def test_unavailable_is_unknown_not_zero(self):
        status = unavailable_research_status()
        self.assertIsNone(status["observation_count"])
        self.assertEqual(status["generation_status"], "PAUSED")
    def test_empty_database_displays_zero(self):
        status = make_research_status(0, 0, 0, [], self.now)
        self.assertTrue(status["available"])
        self.assertEqual(status["observation_count"], 0)
    def test_fifteen_observations_zero_eligible(self):
        status = make_research_status(15, 15, 0, [], self.now)
        self.assertEqual(status["eligible_settled_events"], 0)
        self.assertEqual(status["model_approval"], "NOT APPROVED")
    def test_reasons_count_once_per_event(self):
        status = make_research_status(15, 15, 0,
            [self.audit(["NEWS_EVIDENCE_INCOMPLETE"]*2)], self.now)
        self.assertEqual(status["blockers"][0]["count"], 1)
    def test_stale_audit_not_shown_as_current(self):
        status = make_research_status(15, 15, 0,
            [self.audit(["NEWS_EVIDENCE_INCOMPLETE"], 3)], self.now)
        self.assertEqual(status["recent_audit_events"], 0)
    def test_invalid_audit_counted(self):
        audit = SimpleNamespace(assessed_at=self.now, decision_json="not-json")
        status = make_research_status(15, 15, 0, [audit], self.now)
        self.assertEqual(status["invalid_audit_rows"], 1)
    def test_pause_panel_when_main_database_unavailable(self):
        html = render(unavailable_research_status(), available=False)
        self.assertIn("Results are temporarily unavailable", html)
        self.assertIn("Not validated", html)
        self.assertNotIn("Automatic parlays: PAUSED", html)
        self.assertNotIn('<section class="research-status"', html)
        self.assertNotIn("<h2>🎰 Trial Parlays</h2>", html)
    def test_existing_ticket_marked_not_qualified(self):
        ticket = {
            "id": 1, "category": "Standard Cap", "odds": "Test odds",
            "stake": "$50", "payout": "Estimate", "outcome": "UNTRACKED",
            "research_label": "Not research-qualified",
            "legs": ["Historical test leg"], "is_trial": False,
            "created": "Test time", "display_status": "ACTIVE",
        }
        html = render(
            make_research_status(15, 15, 0, [], self.now), ticket=ticket
        )
        self.assertIn("Not research-qualified", html)
        self.assertIn("Historical test leg", html)
        self.assertIn("UNTRACKED", html)
        trial_section = html.split("<h2>🎰 Trial Parlays</h2>", 1)[1]
        trial_section = trial_section.split("<details>", 1)[0]
        self.assertNotIn("Historical test leg", trial_section)
        self.assertIn("No trial tickets to show yet.", trial_section)
    def test_dynamic_values_are_escaped(self):
        payload = "<script>alert(1)</script>"
        ticket = {
            "id": 2, "category": "Trial 2-Leg", "odds": "Test odds",
            "stake": "$10", "payout": "$30", "outcome": "PENDING",
            "research_label": "Trial · Validation pending",
            "legs": [payload], "is_trial": True,
            "created": "Test time", "display_status": "ACTIVE",
            "paper_return": "—", "paper_profit": "—",
        }
        html = render(
            make_research_status(15, 15, 0, [], self.now), ticket=ticket
        )
        self.assertNotIn(payload, html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
    def test_ticket_display_preserves_labels_and_adds_qualification(self):
        tree = ast.parse((ROOT / "dashboard_ui.py").read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "ticket_display")
        namespace = {"json": json, "display_time": lambda value: "Unknown"}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "isolated_ticket", "exec"), namespace)
        slip = SimpleNamespace(id=1, category="Standard Cap", odds="Odds", stake="Stake",
            payout="Return", legs_json=json.dumps(["Actual leg", "Game Script: Annotation"]),
            status="ACTIVE", created_at=None)
        result = namespace["ticket_display"](slip)
        self.assertEqual(result["legs"], ["Actual leg"])
        self.assertEqual(result["research_label"], "Not research-qualified")
    def test_scheduler_has_explicit_preview_control(self):
        source = (ROOT / "dashboard.py").read_text()
        self.assertIn("INGESTION_SCHEDULER_ENABLED", source)
        self.assertIn("Background ingestion scheduler disabled for this process.", source)


    def test_trial_card_shows_paper_results(self):
        ticket = {
            "id": 3, "category": "Trial 2-Leg", "odds": "3x (+200)",
            "stake": "$10.00", "payout": "$30.00", "outcome": "WON",
            "research_label": "Trial · Validation pending",
            "legs": ["Visible trial leg"], "is_trial": True,
            "created": "Test time", "display_status": "ACTIVE",
            "paper_return": "$30.00", "paper_profit": "$20.00",
        }
        html = render(
            make_research_status(15, 15, 0, [], self.now), ticket=ticket
        )
        trial_section = html.split("<h2>🎰 Trial Parlays</h2>", 1)[1]
        trial_section = trial_section.split("<details>", 1)[0]
        self.assertIn("Visible trial leg", trial_section)
        self.assertIn("Outcome WON", trial_section)
        self.assertIn("Simulated stake $10.00", trial_section)
        self.assertIn("Simulated return $30.00", trial_section)
        self.assertIn("Simulated profit $20.00", trial_section)

if __name__ == "__main__":
    unittest.main()
