from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RoboAnimationUiTests(unittest.TestCase):
    def _read(self, rel_path):
        return (ROOT / rel_path).read_text(encoding="utf-8")

    def test_css_has_reduced_motion_support(self):
        css = self._read("static/style.css")
        self.assertIn(".robo-anim", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertIn("animation: none !important", css)

    def test_home_has_robo_anim_without_new_card(self):
        html = self._read("templates/home.html")
        self.assertIn("main-robot-thumb robo-anim", html)
        self.assertIn("robo-anim-complete", html)
        self.assertIn("robo-anim-focus", html)
        self.assertNotIn("robo-animation-card", html)
        self.assertNotIn("アニメ設定", html)

    def test_user_chip_podium_robot_has_robo_anim(self):
        html = self._read("templates/_user_chip.html")
        self.assertIn("user-chip-robot{% if podium %} robo-anim robo-anim-focus{% endif %}", html)

    def test_ranking_top_robot_has_robo_anim(self):
        html = self._read("templates/ranking.html")
        self.assertIn("ranking-robot-thumb{% if loop.index <= 5 %} robo-anim robo-anim-idle{% endif %}", html)

    def test_world_mvp_has_robo_anim(self):
        html = self._read("templates/world.html")
        self.assertIn("world-mvp-thumb robo-anim robo-anim-focus", html)

    def test_records_highlight_robot_has_robo_anim(self):
        html = self._read("templates/records.html")
        self.assertIn("record-highlight-thumb robo-anim robo-anim-idle", html)

    def test_no_gif_or_js_dependency_added(self):
        changed_sources = "\n".join(
            [
                self._read("static/style.css"),
                self._read("templates/home.html"),
                self._read("templates/ranking.html"),
                self._read("templates/world.html"),
                self._read("templates/records.html"),
                self._read("templates/_user_chip.html"),
            ]
        )
        self.assertNotIn(".gif", changed_sources.lower())
        self.assertNotIn("requestAnimationFrame", changed_sources)
        self.assertNotIn("setInterval", changed_sources)


if __name__ == "__main__":
    unittest.main()
