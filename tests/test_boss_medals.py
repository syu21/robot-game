import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class BossMedalVisibilityTests(unittest.TestCase):
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
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 0, 1, 2)
                """,
                ("boss_medal_user", "x", now),
            )
            self.user_id = int(
                db.execute(
                    "SELECT id FROM users WHERE username = ?",
                    ("boss_medal_user",),
                ).fetchone()["id"]
            )
            game_app.initialize_new_user(db, self.user_id)
            decor = db.execute(
                "SELECT id FROM robot_decor_assets WHERE key = ?",
                ("boss_emblem_aurix",),
            ).fetchone()
            self.assertIsNotNone(decor)
            db.execute(
                """
                INSERT OR IGNORE INTO user_decor_inventory (user_id, decor_asset_id, acquired_at)
                VALUES (?, ?, ?)
                """,
                (self.user_id, int(decor["id"]), now - 60),
            )
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "boss_medal_user"
        return client

    def test_home_does_not_show_boss_medal_panel(self):
        resp = self._client().get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertNotIn("BOSS MEDALS", html)
        self.assertNotIn("機体整備の装飾でロボに付けられます", html)

    def test_records_show_earned_and_locked_boss_medals(self):
        resp = self._client().get("/records")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("ボス撃破の勲章", html)
        self.assertIn("オリクス紋章", html)
        self.assertIn("第一層ボス撃破の証", html)
        self.assertIn("ヴェントラ紋章", html)
        self.assertIn("未獲得", html)

    def test_decor_maintenance_labels_boss_medals_as_decor(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            robot_id = int(
                db.execute(
                    "SELECT active_robot_id FROM users WHERE id = ?",
                    (self.user_id,),
                ).fetchone()["active_robot_id"]
            )
        resp = self._client().get(f"/robots/{robot_id}/maintenance?slot=DECOR")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("ボス撃破の勲章や支援トロフィー", html)
        self.assertIn("オリクス紋章", html)


if __name__ == "__main__":
    unittest.main()
