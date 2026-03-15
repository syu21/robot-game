import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class BattleLogModeTests(unittest.TestCase):
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
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins) VALUES (?, ?, ?, 1, 20)",
                ("log_mode_tester", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("log_mode_tester",),
            ).fetchone()["id"]
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (self.user_id, "LogModeBot", now, now),
            )
            robot_id = db.execute(
                "SELECT id FROM robot_instances WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()["id"]

            def pick_key(part_type):
                row = db.execute(
                    "SELECT key FROM robot_parts WHERE part_type = ? AND is_active = 1 ORDER BY id ASC LIMIT 1",
                    (part_type,),
                ).fetchone()
                self.assertIsNotNone(row)
                return row["key"]

            db.execute(
                """
                INSERT INTO robot_instance_parts (robot_instance_id, head_key, r_arm_key, l_arm_key, legs_key)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    robot_id,
                    pick_key("HEAD"),
                    pick_key("RIGHT_ARM"),
                    pick_key("LEFT_ARM"),
                    pick_key("LEGS"),
                ),
            )
            db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (robot_id, self.user_id))
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "log_mode_tester"
        return client

    def test_mode_expanded_renders_details_open(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET battle_log_mode = 'expanded' WHERE id = ?", (self.user_id,))
            db.commit()

        client = self._client()
        resp = client.post("/explore", data={"area_key": "layer_1"})
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('<details class="battle-log-fold" open>', html)

    def test_mode_collapsed_renders_details_without_open(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET battle_log_mode = 'collapsed' WHERE id = ?", (self.user_id,))
            db.commit()

        client = self._client()
        resp = client.post("/explore", data={"area_key": "layer_1"})
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('<details class="battle-log-fold"', html)
        self.assertNotIn('<details class="battle-log-fold" open>', html)

    def test_settings_post_persists_mode(self):
        client = self._client()
        resp = client.post(
            "/settings/battle_log_mode",
            data={"mode": "expanded", "next": "/battle"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/battle", resp.headers.get("Location", ""))

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT battle_log_mode FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(row["battle_log_mode"], "expanded")


if __name__ == "__main__":
    unittest.main()
