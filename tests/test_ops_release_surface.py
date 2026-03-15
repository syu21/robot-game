import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class OpsReleaseSurfaceTests(unittest.TestCase):
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
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins) VALUES (?, ?, ?, 1, 0)",
                ("ops_admin", "x", now),
            )
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins) VALUES (?, ?, ?, 0, 0)",
                ("ops_user", "x", now),
            )
            self.admin_id = db.execute("SELECT id FROM users WHERE username = ?", ("ops_admin",)).fetchone()["id"]
            self.user_id = db.execute("SELECT id FROM users WHERE username = ?", ("ops_user",)).fetchone()["id"]
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client_with_user(self, user_id, username):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = user_id
            session["username"] = username
        return client

    def test_public_policy_pages_are_available(self):
        client = game_app.app.test_client()
        for path in ("/terms", "/privacy", "/contact", "/changelog"):
            resp = client.get(path)
            self.assertEqual(resp.status_code, 200)

    def test_maintenance_mode_blocks_explore_post_with_503(self):
        client = self._client_with_user(self.user_id, "ops_user")
        with patch.dict(os.environ, {"MAINTENANCE_MODE": "true"}):
            resp = client.post("/explore", data={"area_key": "layer_1"})
        self.assertEqual(resp.status_code, 503)
        self.assertIn("メンテナンス中", resp.get_data(as_text=True))

    def test_admin_metrics_is_admin_only(self):
        admin_client = self._client_with_user(self.admin_id, "ops_admin")
        user_client = self._client_with_user(self.user_id, "ops_user")

        admin_resp = admin_client.get("/admin/metrics")
        self.assertEqual(admin_resp.status_code, 200)
        self.assertIn("運用メトリクス", admin_resp.get_data(as_text=True))

        user_resp = user_client.get("/admin/metrics")
        self.assertEqual(user_resp.status_code, 403)

    def test_footer_shows_app_version(self):
        client = game_app.app.test_client()
        resp = client.get("/terms")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(f"v{game_app.APP_VERSION}", resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
