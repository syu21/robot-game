import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class AdminAssetTogglePersistenceTests(unittest.TestCase):
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
                ("admin_asset_tester", "x", now),
            )
            db.commit()
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("admin_asset_tester",),
            ).fetchone()["id"]
            enemy_row = db.execute(
                """
                SELECT key
                FROM enemies
                WHERE COALESCE(is_boss, 0) = 0
                ORDER BY tier ASC, key ASC
                LIMIT 1
                """
            ).fetchone()
            self.assertIsNotNone(enemy_row)
            self.enemy_key = enemy_row["key"]

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "admin_asset_tester"
        return client

    def test_admin_enemy_toggle_persists_after_redirect_and_reopen(self):
        client = self._client()

        resp = client.post(f"/admin/enemies/{self.enemy_key}/toggle_active", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT is_active FROM enemies WHERE key = ?", (self.enemy_key,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(int(row["is_active"]), 0)

        resp = client.get("/admin/enemies?is_active=0")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.enemy_key, resp.get_data(as_text=True))

    def test_admin_decor_toggle_persists_after_redirect_and_reopen(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            decor_row = db.execute(
                "SELECT id FROM robot_decor_assets WHERE key = ?",
                ("boss_emblem_aurix",),
            ).fetchone()
            self.assertIsNotNone(decor_row)
            decor_id = int(decor_row["id"])

        client = self._client()
        resp = client.post(f"/admin/decor/{decor_id}/toggle_active", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT is_active FROM robot_decor_assets WHERE id = ?",
                (decor_id,),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(int(row["is_active"]), 0)


if __name__ == "__main__":
    unittest.main()
