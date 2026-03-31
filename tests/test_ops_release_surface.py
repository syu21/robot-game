import os
import re
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
        for path in ("/terms", "/privacy", "/commerce", "/contact", "/changelog", "/guide", "/support", "/shop"):
            resp = client.get(path)
            self.assertEqual(resp.status_code, 200)

    def test_public_landing_page_shows_beta_cta_and_legal_links(self):
        client = game_app.app.test_client()
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("ロボらぼ", html)
        self.assertIn("ロボらぼ β版公開中", html)
        self.assertIn("新規登録して始める", html)
        self.assertIn("ログイン", html)
        self.assertIn("今この瞬間の世界", html)
        self.assertIn("3ステップで始まる", html)
        self.assertIn("最新アップデート", html)
        self.assertIn("/terms", html)
        self.assertIn("/privacy", html)
        self.assertIn("/commerce", html)
        self.assertIn("/contact", html)
        self.assertIn("/support", html)

    def test_public_landing_shows_google_cta_when_configured(self):
        client = game_app.app.test_client()
        with patch.dict(
            os.environ,
            {
                "GOOGLE_OAUTH_CLIENT_ID": "google-client-id",
                "GOOGLE_OAUTH_CLIENT_SECRET": "google-client-secret",
            },
            clear=False,
        ):
            resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Googleで始める", html)
        self.assertIn("/auth/google/start", html)

    def test_register_page_has_hero_google_priority_and_world_reassurance(self):
        client = game_app.app.test_client()
        with patch.dict(
            os.environ,
            {
                "GOOGLE_OAUTH_CLIENT_ID": "google-client-id",
                "GOOGLE_OAUTH_CLIENT_SECRET": "google-client-secret",
            },
            clear=False,
        ):
            resp = client.get("/register")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("ロボを組んで出撃せよ", html)
        self.assertIn("Googleで3秒ではじめる", html)
        self.assertIn("今すぐロボを組んで始める", html)
        self.assertIn("新規登録して出撃する", html)
        self.assertIn("パスワード確認", html)
        self.assertIn("3ステップ", html)
        self.assertIn("出撃", html)
        self.assertIn("育成", html)
        self.assertIn("世界", html)
        self.assertIn("今この瞬間の世界", html)
        self.assertIn("/static/images/ui/register_hero_banner.png", html)

    def test_root_redirects_logged_in_user_to_home(self):
        client = self._client_with_user(self.user_id, "ops_user")
        resp = client.get("/", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/home", resp.headers.get("Location", ""))

    def test_guide_page_explains_core_terms(self):
        client = game_app.app.test_client()
        resp = client.get("/guide")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("用語", html)
        self.assertIn("性格", html)
        self.assertIn("背水", html)
        self.assertIn("進化コア", html)
        self.assertIn("世界ログ", html)

    def test_terms_privacy_and_commerce_are_separate_legal_pages(self):
        client = game_app.app.test_client()
        terms_resp = client.get("/terms")
        privacy_resp = client.get("/privacy")
        commerce_resp = client.get("/commerce")
        self.assertEqual(terms_resp.status_code, 200)
        self.assertEqual(privacy_resp.status_code, 200)
        self.assertEqual(commerce_resp.status_code, 200)
        terms_html = terms_resp.get_data(as_text=True)
        privacy_html = privacy_resp.get_data(as_text=True)
        commerce_html = commerce_resp.get_data(as_text=True)
        self.assertIn("利用規約", terms_html)
        self.assertIn("有償サービス", terms_html)
        self.assertIn("/privacy", terms_html)
        self.assertIn("/commerce", terms_html)
        self.assertIn("プライバシーポリシー", privacy_html)
        self.assertIn("Stripe", privacy_html)
        self.assertIn("/terms", privacy_html)
        self.assertIn("/commerce", privacy_html)
        self.assertIn("特定商取引法に基づく表記", commerce_html)
        self.assertIn("大谷周平", commerce_html)
        self.assertIn("KAS Development", commerce_html)
        self.assertIn("pochirobo021@gmail.com", commerce_html)

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
        html = resp.get_data(as_text=True)
        self.assertIn(f"v{game_app.APP_VERSION}", html)
        self.assertIn("/static/favicon.png", html)
        self.assertIn("/support", html)
        self.assertIn("/commerce", html)
        self.assertNotIn('href="/guide"', html)
        self.assertNotIn('href="/comms"', html)

    def test_healthz_is_public(self):
        client = game_app.app.test_client()
        resp = client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertTrue(payload["ok"])
        self.assertIn("portal_queue_pending", payload)

    def test_home_loads_header_scroll_script(self):
        client = self._client_with_user(self.user_id, "ops_user")
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("/static/header_scroll_v2.js", html)
        self.assertIn("/guide", html)
        self.assertIn("アイコン変更", html)
        header_match = re.search(r"<header class=\"top topbar site-header\".*?</header>", html, re.DOTALL)
        self.assertIsNotNone(header_match)
        header_html = header_match.group(0)
        self.assertNotIn('href="/comms"', header_html)

    def test_changelog_shows_latest_2026_03_26_entry(self):
        client = game_app.app.test_client()
        resp = client.get("/changelog")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("v0.1.14 - 2026/03/26", html)
        self.assertIn("探索場所ごとの育ち方の差を追加", html)
        self.assertIn("ロボの性格表示（安定 / 背水 / 爆発）を追加", html)
        self.assertLess(html.index("v0.1.14 - 2026/03/26"), html.index("v0.1.13 - 2026-03-21"))

    def test_sitemap_xml_is_public(self):
        client = game_app.app.test_client()
        old_public_game_url = game_app.PUBLIC_GAME_URL
        try:
            with patch.dict(os.environ, {"PUBLIC_GAME_URL": "https://robolabo.site"}, clear=False):
                game_app.PUBLIC_GAME_URL = "https://robolabo.site"
                resp = client.get("/sitemap.xml")
        finally:
            game_app.PUBLIC_GAME_URL = old_public_game_url
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/xml", resp.content_type)
        body = resp.get_data(as_text=True)
        self.assertIn("<loc>https://robolabo.site/</loc>", body)
        self.assertIn("<loc>https://robolabo.site/login</loc>", body)
        self.assertIn("<loc>https://robolabo.site/register</loc>", body)
        self.assertIn("<loc>https://robolabo.site/home</loc>", body)
        self.assertIn("<loc>https://robolabo.site/guide</loc>", body)
        self.assertIn("<loc>https://robolabo.site/terms</loc>", body)
        self.assertIn("<loc>https://robolabo.site/privacy</loc>", body)
        self.assertIn("<loc>https://robolabo.site/commerce</loc>", body)
        self.assertIn("<loc>https://robolabo.site/support</loc>", body)


if __name__ == "__main__":
    unittest.main()
