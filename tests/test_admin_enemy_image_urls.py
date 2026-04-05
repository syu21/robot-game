import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class AdminEnemyImageUrlTests(unittest.TestCase):
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
                ("enemy_admin", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("enemy_admin",),
            ).fetchone()["id"]
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _login(self, client):
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "enemy_admin"

    def test_admin_enemy_list_uses_versioned_enemy_urls(self):
        with game_app.app.test_client() as client:
            self._login(client)
            resp = client.get("/admin/enemies")
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn("/static/enemies/", html)
            self.assertIn("?v=", html)

    def test_admin_enemy_edit_uses_versioned_enemy_url(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            enemy_key = db.execute("SELECT key FROM enemies ORDER BY id ASC LIMIT 1").fetchone()["key"]
        with game_app.app.test_client() as client:
            self._login(client)
            resp = client.get(f"/admin/enemies/{enemy_key}/edit")
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn("/static/enemies/", html)
            self.assertIn("?v=", html)


if __name__ == "__main__":
    unittest.main()
