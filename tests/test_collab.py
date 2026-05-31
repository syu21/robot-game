import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class CollabRouteTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected, coins)
                VALUES (?, ?, ?, 0, 0, 100)
                """,
                ("collab_user", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("collab_user",)).fetchone()["id"])
            game_app.initialize_new_user(db, self.user_id)
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self, *, logged_in=False):
        client = game_app.app.test_client()
        if logged_in:
            with client.session_transaction() as session:
                session["user_id"] = self.user_id
                session["username"] = "collab_user"
        return client

    def _add_explore_ends(self, count):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            for i in range(count):
                db.execute(
                    "INSERT INTO world_events_log (created_at, event_type, payload_json, user_id) VALUES (?, ?, '{}', ?)",
                    (now - i, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], self.user_id),
                )
            db.commit()

    def test_collab_requires_login_and_hides_secret_from_guest(self):
        client = self._client()
        resp = client.get("/collab", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/register", resp.headers["Location"])
        self.assertIn("next=/collab", resp.headers["Location"])

        page = client.get("/collab", follow_redirects=True)
        html = page.get_data(as_text=True)
        self.assertNotIn("ロボらぼケルベロス", html)

    def test_collab_page_hides_secret_until_ten_explore_ends(self):
        client = self._client(logged_in=True)
        resp = client.get("/collab")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("コラボ", html)
        self.assertIn("チビクエBless", html)
        self.assertIn("あと", html)
        self.assertIn("出撃", html)
        self.assertIn("現在 0 / 10", html)
        self.assertNotIn("ロボらぼケルベロス", html)

    def test_collab_page_shows_chibique_bless_secret_after_ten_explore_ends(self):
        self._add_explore_ends(10)
        client = self._client(logged_in=True)
        resp = client.get("/collab")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("コラボ", html)
        self.assertIn("チビクエBless", html)
        self.assertIn("ロボらぼケルベロス", html)
        self.assertIn("絶対に他人と共有しないでください", html)
        self.assertIn("https://b.chibiquest.net/", html)
        self.assertIn('target="_blank"', html)
        self.assertIn('rel="noopener noreferrer"', html)

    def test_home_links_to_collab_with_locked_progress(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET home_beginner_mission_hidden = 1 WHERE id = ?", (self.user_id,))
            db.commit()
        self._add_explore_ends(3)

        client = self._client(logged_in=True)
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("コラボ", html)
        self.assertIn("あと7回出撃で合言葉", html)
        self.assertIn('href="/collab"', html)

    def test_home_links_to_collab_with_unlocked_label(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET home_beginner_mission_hidden = 1 WHERE id = ?", (self.user_id,))
            db.commit()
        self._add_explore_ends(10)

        client = self._client(logged_in=True)
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("コラボ", html)
        self.assertIn("合言葉を見る", html)
        self.assertIn('href="/collab"', html)

    def test_collab_view_does_not_change_user_state(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            before = dict(db.execute("SELECT username, coins, active_robot_id FROM users WHERE id = ?", (self.user_id,)).fetchone())

        client = self._client(logged_in=True)
        self.assertEqual(client.get("/collab").status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            after = dict(db.execute("SELECT username, coins, active_robot_id FROM users WHERE id = ?", (self.user_id,)).fetchone())
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
