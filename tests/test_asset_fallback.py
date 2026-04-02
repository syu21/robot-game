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

    def test_part_image_rel_accepts_legacy_normal_alias(self):
        rel = game_app._part_image_rel(
            {"key": "head_1", "image_path": "parts/head/head_normal.png"}
        )
        self.assertEqual(rel, "robot_assets/parts/head/head_n_normal.png")

    def test_legacy_normal_compose_assets_exist(self):
        legacy_normals = (
            "parts/head/head_normal.png",
            "parts/left_arm/left_arm_normal.png",
            "parts/legs/legs_normal.png",
            "parts/right_arm/right_arm_normal.png",
        )
        for rel in legacy_normals:
            with self.subTest(rel=rel):
                self.assertTrue(os.path.exists(game_app._asset_abs(rel)))

    def test_feed_enemy_row_prefers_active_row_with_real_image(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                INSERT INTO enemies (key, name_ja, image_path, tier, element, hp, atk, def, spd, acc, cri, is_active)
                VALUES ('legacy_scout', 'スチールスカウト', 'enemies/steel_scout.png', 2, 'NORMAL', 30, 9, 8, 7, 8, 2, 0)
                """
            )
            db.execute(
                """
                INSERT INTO enemies (key, name_ja, image_path, tier, element, hp, atk, def, spd, acc, cri, is_active)
                VALUES ('active_scout', 'スチールスカウト', 'enemies/enemy14.png', 2, 'NORMAL', 30, 9, 8, 7, 8, 2, 1)
                """
            )
            db.commit()
            row = {"entity_type": "enemy", "entity_id": None}
            payload = {"enemy_key": "legacy_scout", "enemy_name": "スチールスカウト"}
            enemy = game_app._feed_enemy_row(db, row, payload)
        self.assertIsNotNone(enemy)
        self.assertNotEqual(enemy["key"], "legacy_scout")
        self.assertNotEqual(enemy["image_path"], "enemies/steel_scout.png")
        self.assertTrue(game_app._enemy_row_has_display_image(enemy))


if __name__ == "__main__":
    unittest.main()
