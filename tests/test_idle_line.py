import unittest

from services.personality_logs import DEFAULT_IDLE_LINES, IDLE_LINES, get_idle_line


class IdleLineTests(unittest.TestCase):
    def test_current_personality_keys_have_specific_idle_lines(self):
        for key in ["silent", "cheerful", "analyst", "charger", "showoff", "veteran", "supportive", "cold"]:
            with self.subTest(key=key):
                line = get_idle_line(key, "テスト")
                self.assertTrue(line.startswith("テスト「"))
                self.assertTrue(line.endswith("」"))
                self.assertIn(line.removeprefix("テスト「").removesuffix("」"), IDLE_LINES[key])

    def test_legacy_personality_keys_remain_supported(self):
        for key in ["calm", "hotblood", "quiet"]:
            with self.subTest(key=key):
                line = get_idle_line(key, "テスト")
                self.assertIn(line.removeprefix("テスト「").removesuffix("」"), IDLE_LINES[key])

    def test_unknown_personality_falls_back(self):
        line = get_idle_line("unknown", "")
        self.assertTrue(line.startswith("ロボ「"))
        self.assertIn(line.removeprefix("ロボ「").removesuffix("」"), DEFAULT_IDLE_LINES)


if __name__ == "__main__":
    unittest.main()
