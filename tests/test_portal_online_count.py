import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class _DummyResp:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def getcode(self):
        return self.status


class PortalOnlineCountTests(unittest.TestCase):
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
                "INSERT INTO users (username, password_hash, created_at, last_seen_at, is_admin, wins) VALUES (?, ?, ?, ?, 0, 0)",
                ("portal_user_1", "x", now, now),
            )
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, last_seen_at, is_admin, wins) VALUES (?, ?, ?, ?, 0, 0)",
                ("portal_user_2", "x", now, now),
            )
            self.user1 = int(db.execute("SELECT id FROM users WHERE username = ?", ("portal_user_1",)).fetchone()["id"])
            self.user2 = int(db.execute("SELECT id FROM users WHERE username = ?", ("portal_user_2",)).fetchone()["id"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def test_count_online_users_window_minutes(self):
        now = int(time.time())
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET last_seen_at = ? WHERE id = ?", (now - 60, self.user1))
            db.execute("UPDATE users SET last_seen_at = ? WHERE id = ?", (now - 500, self.user2))
            db.commit()
            c = game_app.count_online_users(db, window_minutes=5, now_ts=now)
        self.assertEqual(c, 1)

    def test_home_request_touches_last_seen(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET last_seen_at = 0 WHERE id = ?", (self.user1,))
            db.commit()

        with game_app.app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user_id"] = self.user1
                sess["username"] = "portal_user_1"
            resp = client.get("/home")
            self.assertEqual(resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT last_seen_at FROM users WHERE id = ?", (self.user1,)).fetchone()
        self.assertGreater(int(row["last_seen_at"] or 0), 0)

    def test_send_portal_online_count_builds_query(self):
        now = int(time.time())
        captured = {}

        def _fake_open(req, timeout=0):
            captured["url"] = req.full_url
            captured["timeout"] = timeout
            return _DummyResp(status=204)

        with game_app.app.app_context(), patch.dict(
            os.environ,
            {
                "POCHI_PORTAL_ENDPOINT": "https://portal.example",
                "POCHI_PORTAL_GAME_KEY": "GAME-1",
                "POCHI_PORTAL_API_KEY": "API-1",
            },
            clear=False,
        ), patch("app.urlopen", side_effect=_fake_open):
            db = game_app.get_db()
            result = game_app.send_portal_online_count(db=db, now_ts=now, window_minutes=5)

        self.assertTrue(result["ok"])
        self.assertIn("/api/portal/online-count/", captured.get("url", ""))
        self.assertIn("game_key=GAME-1", captured.get("url", ""))
        self.assertIn("api_key=API-1", captured.get("url", ""))
        self.assertIn("online_count=", captured.get("url", ""))

    def test_send_portal_online_count_failure_is_non_fatal(self):
        with game_app.app.app_context(), patch.dict(
            os.environ,
            {
                "POCHI_PORTAL_ENDPOINT": "https://portal.example",
                "POCHI_PORTAL_GAME_KEY": "GAME-1",
                "POCHI_PORTAL_API_KEY": "API-1",
            },
            clear=False,
        ), patch("app.urlopen", side_effect=OSError("network down")):
            db = game_app.get_db()
            result = game_app.send_portal_online_count(db=db)

        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
