import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie

from werkzeug.security import generate_password_hash

import app as game_app
import init_db


class AuthSessionLifetimeTests(unittest.TestCase):
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

    def _create_user(self, username, *, is_admin=False, is_admin_protected=False):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, last_seen_at, is_admin, is_admin_protected)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    generate_password_hash("pw"),
                    now,
                    now,
                    int(is_admin),
                    int(is_admin_protected),
                ),
            )
            db.commit()

    def _session_cookie_from_response(self, response):
        cookie = SimpleCookie()
        for header in response.headers.getlist("Set-Cookie"):
            cookie.load(header)
        return cookie[game_app.app.config["SESSION_COOKIE_NAME"]]

    def test_login_sets_permanent_session_with_14_day_expiry(self):
        self._create_user("session_user")
        client = game_app.app.test_client()

        response = client.post(
            "/login",
            data={"username": "session_user", "password": "pw"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/home", response.headers.get("Location", ""))
        with client.session_transaction() as session:
            self.assertEqual(session.get("user_id"), 1)
            self.assertEqual(session.get("username"), "session_user")
            self.assertTrue(session.permanent)

        cookie = self._session_cookie_from_response(response)
        self.assertTrue(cookie.value)
        self.assertTrue(cookie["expires"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertTrue(cookie["httponly"])
        expires_at = parsedate_to_datetime(cookie["expires"])
        remaining = expires_at - datetime.now(timezone.utc)
        self.assertGreater(remaining, timedelta(days=13))
        self.assertLess(remaining, timedelta(days=15))

    def test_authenticated_request_refreshes_permanent_session_cookie(self):
        self._create_user("refresh_user")
        client = game_app.app.test_client()
        login_response = client.post(
            "/login",
            data={"username": "refresh_user", "password": "pw"},
            follow_redirects=False,
        )
        initial_cookie = self._session_cookie_from_response(login_response)
        initial_expires = parsedate_to_datetime(initial_cookie["expires"])

        time.sleep(1.1)
        refresh_response = client.get("/", follow_redirects=False)

        self.assertEqual(refresh_response.status_code, 302)
        self.assertIn("/home", refresh_response.headers.get("Location", ""))
        refreshed_cookie = self._session_cookie_from_response(refresh_response)
        refreshed_expires = parsedate_to_datetime(refreshed_cookie["expires"])
        self.assertGreater(refreshed_expires, initial_expires)

    def test_admin_login_also_sets_permanent_session(self):
        self._create_user("admin_only", is_admin=True, is_admin_protected=True)
        client = game_app.app.test_client()

        response = client.post(
            "/admin/login",
            data={"username": "admin_only", "password": "pw"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin", response.headers.get("Location", ""))
        with client.session_transaction() as session:
            self.assertEqual(session.get("username"), "admin_only")
            self.assertTrue(session.permanent)

    def test_logout_clears_permanent_session(self):
        self._create_user("logout_user")
        client = game_app.app.test_client()
        client.post(
            "/login",
            data={"username": "logout_user", "password": "pw"},
            follow_redirects=False,
        )

        response = client.get("/logout", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers.get("Location", ""))
        with client.session_transaction() as session:
            self.assertEqual(dict(session), {})

    def test_session_lifetime_config_defaults_to_14_days(self):
        self.assertEqual(game_app.app.config["PERMANENT_SESSION_LIFETIME"], timedelta(days=14))
        self.assertTrue(game_app.app.config["SESSION_REFRESH_EACH_REQUEST"])
        self.assertTrue(game_app.app.config["SESSION_COOKIE_HTTPONLY"])
        self.assertEqual(game_app.app.config["SESSION_COOKIE_SAMESITE"], "Lax")


if __name__ == "__main__":
    unittest.main()
