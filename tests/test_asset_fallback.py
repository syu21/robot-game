import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class AssetFallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        init_db.main()
        game_app.app.config["TESTING"] = True

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def test_enemy_image_rel_falls_back_and_warns_once_per_request(self):
        missing = f"enemies/not_found_{int(time.time()*1000)}.png"
        with game_app.app.test_request_context("/"):
            with self.assertLogs(game_app.app.logger.name, level="WARNING") as cap:
                rel1 = game_app._enemy_image_rel(missing)
                rel2 = game_app._enemy_image_rel(missing)
        self.assertEqual(rel1, "enemies/_placeholder.png")
        self.assertEqual(rel2, "enemies/_placeholder.png")
        self.assertEqual(len(cap.output), 1)
        self.assertIn("asset.missing", cap.output[0])

    def test_part_image_rel_falls_back_when_missing(self):
        part_like = {"key": "head_n_missing", "image_path": "parts/head/missing.png"}
        rel = game_app._part_image_rel(part_like)
        self.assertEqual(rel, "enemies/_placeholder.png")


if __name__ == "__main__":
    unittest.main()
