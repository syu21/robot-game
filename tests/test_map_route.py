import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class MapRouteTests(unittest.TestCase):
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
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins) VALUES (?, ?, ?, 0, 0)",
                ("map_tester", "x", now),
            )
            db.commit()
            self.user_id = db.execute("SELECT id FROM users WHERE username = ?", ("map_tester",)).fetchone()["id"]

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def test_map_requires_login(self):
        with game_app.app.test_client() as client:
            resp = client.get("/map")
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/login", resp.headers.get("Location", ""))

    def test_map_renders_and_hides_locked_layers_by_default(self):
        with game_app.app.test_client() as client:
            with client.session_transaction() as session:
                session["user_id"] = self.user_id
                session["username"] = "map_tester"

            resp = client.get("/map")
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn('id="map-node-layer_1"', html)
            self.assertNotIn('id="map-node-layer_3"', html)
            self.assertNotIn('id="map-node-layer_2_rush"', html)
            self.assertIn("第1層ボス：第1層を出撃していると低確率で警報", html)
            self.assertIn("第2層：第1層ボス撃破で解放", html)
            self.assertIn("ボス撃破で次の層や特別報酬につながります", html)
            self.assertIn("🔒 第2層（第1層ボス撃破で解放）", html)
            self.assertNotIn('name="area_key" value="layer_3"', html)
            self.assertNotIn('name="area_key" value="layer_2_rush"', html)

    def test_map_layer2_rush_visible_when_layer2_unlocked(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET max_unlocked_layer = 2 WHERE id = ?", (self.user_id,))
            db.commit()

        with game_app.app.test_client() as client:
            with client.session_transaction() as session:
                session["user_id"] = self.user_id
                session["username"] = "map_tester"

            resp = client.get("/map")
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn('id="map-node-layer_2_rush"', html)
            self.assertIn('name="area_key" value="layer_2_rush"', html)

    def test_map_shows_growth_tendency_without_internal_stat_keys(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET max_unlocked_layer = 4 WHERE id = ?", (self.user_id,))
            for key in game_app.LAYER4_SUBAREA_KEYS:
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        int(time.time()),
                        game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                        f'{{"area_key":"{key}","boss_kind":"fixed"}}',
                        self.user_id,
                    ),
                )
            db.commit()

        with game_app.app.test_client() as client:
            with client.session_transaction() as session:
                session["user_id"] = self.user_id
                session["username"] = "map_tester"

            resp = client.get("/map")
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn("育成傾向: 耐久・防御を伸ばしやすい高難度エリア", html)
            self.assertIn("育成傾向: 命中を伸ばしやすい高難度エリア", html)
            self.assertIn("育成傾向: 攻撃・会心を伸ばしやすい高難度エリア", html)
            for internal_key in ("w_hp", "w_atk", "w_def", "w_spd", "w_acc", "w_cri"):
                self.assertNotIn(internal_key, html)


if __name__ == "__main__":
    unittest.main()
