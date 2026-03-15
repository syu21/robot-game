import unittest

from services.personality_logs import get_streak_lines


class PersonalityStreakLinesTests(unittest.TestCase):
    def test_calm_second_win_hint(self):
        lines = get_streak_lines("calm", "ロボA", True, 2, 1)
        self.assertIn("流れは悪くない。", lines.get("streak_hint_line") or "")

    def test_calm_third_win_bonus(self):
        lines = get_streak_lines("calm", "ロボA", True, 3, 2)
        self.assertIn("3連勝か。", lines.get("bonus_line") or "")

    def test_calm_break_line_after_streak(self):
        lines = get_streak_lines("calm", "ロボA", False, 0, 2)
        self.assertIn("止まるか", lines.get("streak_break_line") or "")

    def test_hotblood_third_win_bonus(self):
        lines = get_streak_lines("hotblood", "ロボB", True, 3, 2)
        self.assertIn("まだ行ける", lines.get("bonus_line") or "")

    def test_quiet_third_win_bonus(self):
        lines = get_streak_lines("quiet", "ロボC", True, 3, 2)
        self.assertIn("……3連勝。", lines.get("bonus_line") or "")


if __name__ == "__main__":
    unittest.main()
