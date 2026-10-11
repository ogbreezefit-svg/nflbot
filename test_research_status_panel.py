import unittest
from datetime import datetime, timezone
from test_research_dashboard import render
from research_dashboard import make_research_status, unavailable_research_status


class ResearchStatusPanelTests(unittest.TestCase):
    def status(self):
        return make_research_status(
            15, 12, 3, [], datetime.now(timezone.utc)
        )

    def panel(self, html):
        return html.split('id="research-status-panel"', 1)[1].split(
            "</section>", 1
        )[0]

    def test_available_counts_and_no_approval(self):
        html = render(self.status())
        panel = self.panel(html)
        for value in ("15", "12", "3"):
            self.assertIn("<dd>" + value + "</dd>", panel)
        self.assertIn("Automatic parlays: PAUSED", panel)
        self.assertIn("Model approval: NOT APPROVED", panel)
        self.assertIn("not recorded in the dashboard database", panel)

    def test_zero_is_not_unavailable(self):
        status = make_research_status(
            0, 0, 0, [], datetime.now(timezone.utc)
        )
        panel = self.panel(render(status))
        self.assertIn("Total observations</dt>\n        <dd>0</dd>", panel)

    def test_research_outage_keeps_counts_unknown(self):
        panel = self.panel(render(unavailable_research_status()))
        self.assertIn("counts are unknown", panel)
        self.assertNotIn("<dd>0</dd>", panel)

    def test_main_outage_hides_panel(self):
        html = render(unavailable_research_status(), available=False)
        self.assertNotIn('id="research-status-panel"', html)

    def test_no_recent_audits_is_not_readiness(self):
        panel = self.panel(render(self.status()))
        self.assertIn("No recent audit data; generation remains paused.", panel)

    def test_blockers_are_escaped(self):
        status = self.status()
        status["recent_audit_events"] = 1
        status["blockers"] = [{
            "label": "<script>alert(1)</script>", "count": 1
        }]
        panel = self.panel(render(status))
        self.assertNotIn("<script>", panel)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", panel)

    def test_empty_blockers_do_not_establish_readiness(self):
        status = self.status()
        status["recent_audit_events"] = 1
        panel = self.panel(render(status))
        self.assertIn("this does not establish readiness", panel)

    def test_panel_follows_hero(self):
        html = render(self.status())
        hero_start = html.index('<section class="monster-hero"')
        hero_end = html.index("</section>", hero_start)
        self.assertGreater(html.index('id="research-status-panel"'), hero_end)


if __name__ == "__main__":
    unittest.main()
