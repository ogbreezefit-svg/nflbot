import unittest
from datetime import datetime, timezone

from test_research_dashboard import render
from research_dashboard import (
    make_research_status,
    unavailable_research_status,
)


class PublicDashboardPrivacyTests(unittest.TestCase):
    def assert_no_diagnostics(self, html):
        for text in (
            'id="research-status-panel"',
            'id="research-eligibility-panel"',
            "Research status",
            "Settled-event eligibility diagnostics",
            "Recorded blockers",
            "Experimental training status",
        ):
            self.assertNotIn(text, html)

    def test_public_dashboard_hides_available_diagnostics(self):
        status = make_research_status(
            90, 15, 0, [], datetime.now(timezone.utc)
        )
        status["recent_audit_events"] = 1
        status["blockers"] = [{
            "label": "PRIVATE_DIAGNOSTIC_SENTINEL",
            "count": 1,
        }]
        html = render(status)
        self.assert_no_diagnostics(html)
        self.assertNotIn("PRIVATE_DIAGNOSTIC_SENTINEL", html)
        self.assertIn('id="monster-title"', html)

    def test_public_dashboard_hides_unavailable_diagnostics(self):
        html = render(unavailable_research_status())
        self.assert_no_diagnostics(html)
        self.assertIn('id="monster-title"', html)

    def test_main_outage_does_not_expose_diagnostics(self):
        html = render(unavailable_research_status(), available=False)
        self.assert_no_diagnostics(html)


if __name__ == "__main__":
    unittest.main()
