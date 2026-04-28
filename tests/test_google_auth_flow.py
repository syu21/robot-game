import os
import tempfile
import time
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import app as game_app
import init_db


class GoogleAuthFlowTests(unittest.TestCase):
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

    def test_google_start_redirects_to_provider_and_stores_state(self):
        client = game_app.app.test_client()
        with patch.dict(
            os.environ,
            {
                "GOOGLE_OAUTH_CLIENT_ID": "cid",
                "GOOGLE_OAUTH_CLIENT_SECRET": "csecret",
            },
            clear=False,
        ):
            with patch.object(
                game_app,
                "_google_oauth_discovery_doc",
                return_value={"authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth"},
            ):
                resp = client.get("/auth/google/start?intent=register&ref=ALLY", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        redirect_url = resp.headers.get("Location", "")
        self.assertTrue(redirect_url.startswith("https://accounts.google.com/o/oauth2/v2/auth"))
        qs = parse_qs(urlparse(redirect_url).query)
        self.assertEqual(qs.get("client_id", [""])[0], "cid")
        self.assertEqual(qs.get("scope", [""])[0], "openid email")
        self.assertEqual(qs.get("response_type", [""])[0], "code")
        with client.session_transaction() as session:
            self.assertTrue(session.get("google_oauth_state"))
            self.assertEqual(session.get("google_oauth_ref_code"), "ALLY")

    def test_google_callback_registers_user_and_redirects_home(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["google_oauth_state"] = "state-123"
            session["google_oauth_nonce"] = "nonce-456"
            session["google_oauth_ref_code"] = ""
            session["google_oauth_next"] = ""

        with patch.dict(
            os.environ,
            {
                "GOOGLE_OAUTH_CLIENT_ID": "cid",
                "GOOGLE_OAUTH_CLIENT_SECRET": "csecret",
            },
            clear=False,
        ):
            with patch.object(game_app, "_google_oauth_exchange_code", return_value={"access_token": "token-abc"}):
                with patch.object(
                    game_app,
                    "_google_oauth_fetch_userinfo",
                    return_value={
                        "sub": "google-sub-1",
                        "email": "alchemist@example.com",
                        "email_verified": True,
                        "name": "あるけみすと",
                        "picture": "https://example.com/avatar.png",
                    },
                ):
                    resp = client.get("/auth/google/callback?state=state-123&code=oauth-code", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("最初のミッション", html)
        self.assertIn("第1層へ出撃", html)
        self.assertNotIn("あるけみすと", html)
        with client.session_transaction() as session:
            self.assertRegex(session.get("username") or "", r"^研究員\d{4}$")
            self.assertIsNone(session.get("needs_display_name_setup"))

        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute(
                "SELECT id, username, display_name, active_robot_id FROM users WHERE username LIKE ?",
                ("robo_%",),
            ).fetchone()
            self.assertIsNotNone(user)
            self.assertRegex(user["username"], r"^robo_\d{4}$")
            self.assertRegex(user["display_name"], r"^研究員\d{4}$")
            self.assertIsNotNone(user["active_robot_id"])
            identity = db.execute(
                "SELECT provider, provider_user_id, email, display_name, avatar_url FROM user_auth_identities WHERE user_id = ?",
                (int(user["id"]),),
            ).fetchone()
            self.assertIsNotNone(identity)
            self.assertEqual(identity["provider"], "google")
            self.assertEqual(identity["provider_user_id"], "google-sub-1")
            self.assertEqual(identity["email"], "alchemist@example.com")
            self.assertIsNone(identity["display_name"])
            self.assertIsNone(identity["avatar_url"])

    def test_google_identity_display_name_is_not_public_fallback(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            cur = db.execute(
                """
                INSERT INTO users (username, display_name, password_hash, created_at, last_seen_at)
                VALUES (?, NULL, ?, ?, ?)
                """,
                ("robo_7777", "x", now, now),
            )
            user_id = int(cur.lastrowid)
            db.execute(
                """
                INSERT INTO user_auth_identities
                (user_id, provider, provider_user_id, email, display_name, avatar_url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    "google",
                    "google-sub-real-name",
                    "real@example.com",
                    "本名 太郎",
                    None,
                    now,
                    now,
                ),
            )
            db.commit()
            row = db.execute("SELECT id, username, display_name, is_admin FROM users WHERE id = ?", (user_id,)).fetchone()
            self.assertEqual(game_app._display_username_for_user_row(db, row), "robo_7777")

    def test_google_registered_user_can_save_game_display_name(self):
        client = game_app.app.test_client()
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            cur = db.execute(
                """
                INSERT INTO users (username, display_name, password_hash, created_at, last_seen_at)
                VALUES (?, NULL, ?, ?, ?)
                """,
                ("alchemist_internal", "x", now, now),
            )
            user_id = int(cur.lastrowid)
            db.execute(
                """
                INSERT INTO user_auth_identities
                (user_id, provider, provider_user_id, email, display_name, avatar_url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    "google",
                    "google-sub-2",
                    "alchemist2@example.com",
                    "あるけみすと",
                    None,
                    now,
                    now,
                ),
            )
            db.commit()
        with client.session_transaction() as session:
            session["user_id"] = user_id
            session["username"] = "あるけみすと"
            session["needs_display_name_setup"] = 1
        resp = client.post(
            "/home/display-name",
            data={"display_name": "錬金見習い", "next": "/home"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("表示名を登録しました。", html)
        self.assertNotIn("表示名を決めよう", html)
        with client.session_transaction() as session:
            self.assertEqual(session.get("username"), "錬金見習い")
            self.assertIsNone(session.get("needs_display_name_setup"))
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT display_name FROM users WHERE id = ?", (user_id,)).fetchone()
            self.assertEqual(row["display_name"], "錬金見習い")


if __name__ == "__main__":
    unittest.main()
