import os
import tempfile
import time
import unittest

import app as game_app
import init_db


INSECT_ENEMY_KEYS = (
    "enemy_insect_ant",
    "enemy_insect_batta",
    "enemy_insect_bee",
    "enemy_insect_kabuto",
    "enemy_insect_kuwagata",
    "enemy_insect_scorpion",
)


class InsectEnemyIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        init_db.main()
        game_app.app.config["TESTING"] = True

        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin) VALUES (?, ?, ?, 1)",
                ("insect_enemy_admin", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("insect_enemy_admin",),
            ).fetchone()["id"]
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _login(self, client):
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "insect_enemy_admin"

    def test_insect_enemy_master_rows_exist_with_expected_image_paths(self):
        expected_paths = {
            "enemy_insect_ant": "static/enemies/insect_ant.png",
            "enemy_insect_batta": "static/enemies/insect_batta.png",
            "enemy_insect_bee": "static/enemies/insect_bee.png",
            "enemy_insect_kabuto": "static/enemies/insect_kabuto.png",
            "enemy_insect_kuwagata": "static/enemies/insect_kuwagata.png",
            "enemy_insect_scorpion": "static/enemies/insect_scorpion.png",
        }
        with game_app.app.app_context():
            db = game_app.get_db()
            for key, image_path in expected_paths.items():
                with self.subTest(key=key):
                    row = db.execute(
                        "SELECT key, image_path, is_active, is_boss FROM enemies WHERE key = ?",
                        (key,),
                    ).fetchone()
                    self.assertIsNotNone(row)
                    self.assertEqual(row["image_path"], image_path)
                    self.assertEqual(int(row["is_active"]), 1)
                    self.assertEqual(int(row["is_boss"]), 0)
            butterfly = db.execute(
                "SELECT key FROM enemies WHERE key = ?",
                ("enemy_insect_butterfly",),
            ).fetchone()
            self.assertIsNone(butterfly)

    def test_enemy_image_rel_handles_static_prefixed_paths(self):
        self.assertEqual(
            game_app._enemy_image_rel("static/enemies/insect_ant.png"),
            "enemies/insect_ant.png",
        )

    def test_simulation_candidates_include_requested_insect_enemies(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            layer_1 = {row["key"] for row in game_app._load_simulation_enemies(db, "layer_1")}
            layer_2 = {row["key"] for row in game_app._load_simulation_enemies(db, "layer_2")}
            layer_3 = {row["key"] for row in game_app._load_simulation_enemies(db, "layer_3")}
            layer_4_forge = {row["key"] for row in game_app._load_simulation_enemies(db, "layer_4_forge")}
            layer_5_lab = {row["key"] for row in game_app._load_simulation_enemies(db, "layer_5_labyrinth")}

        self.assertIn("enemy_insect_ant", layer_1)
        self.assertIn("enemy_insect_batta", layer_1)
        self.assertIn("enemy_insect_bee", layer_2)
        self.assertIn("enemy_insect_bee", layer_3)
        self.assertIn("enemy_insect_kuwagata", layer_3)
        self.assertIn("enemy_insect_scorpion", layer_3)
        self.assertIn("enemy_insect_kabuto", layer_4_forge)
        self.assertTrue(layer_5_lab.isdisjoint(set(INSECT_ENEMY_KEYS)))

    def test_layer4_and_layer5_enemy_key_sets_match_insect_policy(self):
        self.assertIn("enemy_insect_kabuto", game_app.EXPLORE_AREA_ENEMY_KEYS["layer_4_forge"])
        self.assertIn("enemy_insect_bee", game_app.EXPLORE_AREA_ENEMY_KEYS["layer_4_haze"])
        self.assertIn("enemy_insect_scorpion", game_app.EXPLORE_AREA_ENEMY_KEYS["layer_4_burst"])
        for area_key in ("layer_5_labyrinth", "layer_5_pinnacle", "layer_5_final"):
            with self.subTest(area_key=area_key):
                self.assertTrue(set(game_app.EXPLORE_AREA_ENEMY_KEYS.get(area_key, ())).isdisjoint(set(INSECT_ENEMY_KEYS)))

    def test_admin_enemy_page_shows_insect_images_and_asset_checklist(self):
        with game_app.app.test_client() as client:
            self._login(client)
            resp = client.get("/admin/enemies")
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn("/static/enemies/insect_ant.png", html)
            self.assertIn("admin-enemy-image", html)
            self.assertIn("static/enemies/insect_butterfly.png", html)


if __name__ == "__main__":
    unittest.main()
