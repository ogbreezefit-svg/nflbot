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
        self.assertIn("Waiting for a weekly ticket.", MONSTER_HERO_HTML)
        self.assertIn("Available when a ticket is published", MONSTER_HERO_HTML)
        self.assertIn(
            '<span class="monster-reel-value">—</span>',
            MONSTER_HERO_HTML,
        )
        self.assertIn("Preview only.", MONSTER_HERO_HTML)

    def test_reduced_motion_is_supported(self):
        self.assertIn("prefers-reduced-motion: reduce", MONSTER_HERO_HTML)
        self.assertIn("animation: none", MONSTER_HERO_HTML)


if __name__ == "__main__":
    unittest.main()
