import unittest

from services.personality_logs import get_idle_line


class IdleLineTests(unittest.TestCase):
    def test_idle_calm(self):
        line = get_idle_line("calm", "テスト")
        self.assertIn("悪くない", line)

    def test_idle_hotblood(self):
        line = get_idle_line("hotblood", "テスト")
        self.assertIn("行こう", line)

    def test_idle_quiet(self):
        line = get_idle_line("quiet", "テスト")
        self.assertIn("待機", line)


if __name__ == "__main__":
    unittest.main()
