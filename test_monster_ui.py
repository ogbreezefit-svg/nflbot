import unittest
from monster_ui import MONSTER_HERO_HTML, add_monster_hero


class MonsterUITests(unittest.TestCase):
    def test_hero_precedes_existing_content(self):
        template = "<html><main><section>Existing dashboard</section></main></html>"
        result = add_monster_hero(template)
        self.assertLess(
            result.index('id="monster-title"'),
            result.index("Existing dashboard"),
        )

    def test_insertion_is_idempotent(self):
        once = add_monster_hero("<main>Dashboard</main>")
        self.assertEqual(add_monster_hero(once), once)

    def test_invalid_template_is_rejected(self):
        for template in ("No main", "<main></main><main></main>"):
            with self.assertRaises(ValueError):
                add_monster_hero(template)

    def test_waiting_state_has_no_fake_payout(self):
        from jinja2 import Environment
        html = Environment(autoescape=True).from_string(
            MONSTER_HERO_HTML
        ).render(available=True, active_tickets=[])
        self.assertIn("Waiting for a qualifying Monster.", html)
        self.assertIn("No qualifying Monster ticket is available.", html)
        self.assertIn("No pending two-leg side bet available.", html)
        self.assertIn('>—</span>', html)
        self.assertNotIn("Featured trial ticket", html)


    def test_reduced_motion_is_supported(self):
        self.assertIn("prefers-reduced-motion: reduce", MONSTER_HERO_HTML)
        self.assertIn("animation: none", MONSTER_HERO_HTML)


if __name__ == "__main__":
    unittest.main()
