import unittest
from datetime import datetime, timezone
from jinja2 import Environment
from monster_ui import (
    MONSTER_HERO_HTML,
    RESEARCH_STATUS_HTML,
    RESEARCH_ELIGIBILITY_HTML,
)


def render(status, available=True):
    # Test internal templates independently of the public dashboard.
    env = Environment(autoescape=True)
    template = env.from_string(
        MONSTER_HERO_HTML
        + RESEARCH_STATUS_HTML
        + RESEARCH_ELIGIBILITY_HTML
    )
    return template.render(
        available=available,
        research=status,
        active_tickets=[],
    )

from research_dashboard import make_research_status, unavailable_research_status


class ResearchEligibilityPanelTests(unittest.TestCase):
    def status(self):
        result = make_research_status(
            90, 15, 0, [], datetime.now(timezone.utc)
        )
        result.update({
            "events_selected_before_integrity_checks": 2,
            "superseded_eligible_observations": 4,
            "excluded_observations_by_reason": {
                "OUTCOME_NOT_SETTLED_WIN_OR_LOSS": 80
            },
            "excluded_selected_events_by_reason": {
                "INVALID_QUOTE_TIME_ORDER": 2
            },
        })
        return result

    def panel(self, status, available=True):
        html = render(status, available=available)
        return html.split('id="research-eligibility-panel"', 1)[1].split(
            "</section>", 1
        )[0]

    def test_counts_have_distinct_units(self):
        panel = self.panel(self.status())
        self.assertIn("80 observation(s)", panel)
        self.assertIn("2 event(s)", panel)
        self.assertIn("<dd>2</dd>", panel)
        self.assertIn("<dd>4</dd>", panel)

    def test_zero_is_preserved(self):
        status = self.status()
        status["events_selected_before_integrity_checks"] = 0
        status["superseded_eligible_observations"] = 0
        panel = self.panel(status)
        self.assertEqual(panel.count("<dd>0</dd>"), 2)

    def test_empty_reasons_are_not_approval(self):
        status = self.status()
        status["excluded_observations_by_reason"] = {}
        status["excluded_selected_events_by_reason"] = {}
        panel = self.panel(status)
        self.assertEqual(
            panel.count("No exclusions recorded at this stage."), 2
        )
        self.assertIn("Automatic generation remains paused.", panel)

    def test_unavailable_is_unknown(self):
        status = unavailable_research_status()
        self.assertIsNone(status["excluded_observations_by_reason"])
        self.assertIsNone(status["excluded_selected_events_by_reason"])
        panel = self.panel(status)
        self.assertIn("counts are unknown", panel)
        self.assertNotIn("<dd>0</dd>", panel)

    def test_missing_diagnostic_fields_are_unavailable(self):
        status = make_research_status(
            0, 0, 0, [], datetime.now(timezone.utc)
        )
        panel = self.panel(status)
        self.assertEqual(panel.count("Diagnostics unavailable."), 2)

    def test_main_outage_hides_diagnostics(self):
        html = render(unavailable_research_status(), available=False)
        self.assertNotIn('id="research-eligibility-panel"', html)

    def test_reasons_are_escaped(self):
        status = self.status()
        status["excluded_selected_events_by_reason"] = {
            "<script>alert(1)</script>": 1
        }
        panel = self.panel(status)
        self.assertNotIn("<script>", panel)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", panel)

    def test_diagnostics_follow_status_panel(self):
        html = render(self.status())
        self.assertLess(
            html.index('id="research-status-panel"'),
            html.index('id="research-eligibility-panel"'),
        )


if __name__ == "__main__":
    unittest.main()
