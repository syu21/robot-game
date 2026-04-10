import json
import os
import re
import tempfile
import time
import unittest
from datetime import datetime, timedelta
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
            db.execute(
                "INSERT INTO user_trophies (user_id, trophy_key, granted_at) VALUES (?, ?, ?)",
                (self.user_id, game_app.SUPPORTER_FOUNDER_TROPHY_KEY, now - 15),
            )
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

    def _jst_ts(self, day_offset=0, hour=12, minute=0):
        now_jst = datetime.fromtimestamp(int(time.time()), game_app.JST)
        base = datetime(now_jst.year, now_jst.month, now_jst.day, tzinfo=game_app.JST)
        return int((base + timedelta(days=day_offset, hours=hour, minutes=minute)).timestamp())

    def _login_log_text(self, ts):
        return datetime.fromtimestamp(int(ts), game_app.JST).strftime("%Y-%m-%d %H:%M:%S")

    def test_public_policy_pages_are_available(self):
        client = game_app.app.test_client()
        for path in ("/terms", "/privacy", "/commerce", "/contact", "/changelog", "/guide", "/support", "/shop"):
            resp = client.get(path)
            self.assertEqual(resp.status_code, 200)

    def test_public_root_redirects_to_register(self):
        client = game_app.app.test_client()
        resp = client.get("/", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers.get("Location", "").endswith("/register"))

    def test_public_root_redirects_to_register_and_preserves_ref(self):
        client = game_app.app.test_client()
        resp = client.get("/?ref=ab12", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/register?ref=AB12", resp.headers.get("Location", ""))

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
        self.assertIn("はじめる", html)
        self.assertIn("ログイン", html)
        self.assertIn('data-auth-mode-trigger="register"', html)
        self.assertIn('data-auth-mode-trigger="login"', html)
        self.assertIn("新規登録して出撃する", html)
        self.assertIn("ログインして基地へ戻る", html)
        self.assertIn("または", html)
        self.assertIn("Googleでかんたん登録", html)
        self.assertIn("Googleでログイン", html)
        self.assertIn("すでにアカウントがある場合は", html)
        self.assertIn("パスワード確認", html)
        self.assertIn("3ステップ", html)
        self.assertIn("出撃", html)
        self.assertIn("育成", html)
        self.assertIn("世界", html)
        self.assertIn("今この瞬間の世界", html)
        self.assertIn("/static/images/ui/register_hero_banner.png?v=", html)
        self.assertIn("/auth/google/start", html)
        self.assertIn('action="/register"', html)
        self.assertIn('action="/login"', html)
        self.assertNotIn("Googleで3秒ではじめる", html)
        self.assertNotIn("ロボらぼ β版公開中", html)

    def test_register_page_keeps_google_ui_visible_when_google_is_unconfigured(self):
        client = game_app.app.test_client()
        with patch.dict(
            os.environ,
            {
                "GOOGLE_OAUTH_CLIENT_ID": "",
                "GOOGLE_OAUTH_CLIENT_SECRET": "",
                "GOOGLE_OAUTH_REDIRECT_URI": "",
            },
            clear=False,
        ):
            resp = client.get("/register")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Googleでかんたん登録", html)
        self.assertIn("Google登録は準備中です。", html)
        self.assertIn("Googleでログイン", html)
        self.assertIn("Googleログインは準備中です。", html)
        self.assertIn("/auth/google/start", html)

    def test_register_login_mode_shows_shared_login_gateway(self):
        client = game_app.app.test_client()
        resp = client.get("/register?mode=login&next=%2Fhome")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('data-auth-pane="login"', html)
        self.assertIn("ログインして基地へ戻る", html)
        self.assertIn('name="next" value="/home"', html)
        self.assertIn('action="/login"', html)

    def test_login_get_redirects_to_register_login_mode(self):
        client = game_app.app.test_client()
        resp = client.get("/login?next=%2Fworld", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        location = resp.headers.get("Location", "")
        self.assertIn("/register?mode=login", location)
        self.assertIn("next=/world", location)

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
        self.assertIn("思想ごとの戦い方", html)
        self.assertIn("セットボーナス", html)
        self.assertIn("同属性パーツ 4部位で発動", html)

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

    def test_partial_maintenance_mode_blocks_explore_post_with_503_and_logs_mode(self):
        client = self._client_with_user(self.user_id, "ops_user")
        with patch.dict(os.environ, {"MAINTENANCE_MODE": "partial"}):
            resp = client.post("/explore", data={"area_key": "layer_1"})
        self.assertEqual(resp.status_code, 503)
        self.assertIn("アップデート中です", resp.get_data(as_text=True))
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                """
                SELECT payload_json
                FROM world_events_log
                WHERE event_type = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (game_app.AUDIT_EVENT_TYPES["SYSTEM_MAINTENANCE_BLOCK"],),
            ).fetchone()
            self.assertIsNotNone(row)
            payload = json.loads(row["payload_json"])
            self.assertEqual(payload["mode"], "partial")
            self.assertEqual(payload["path"], "/explore")
            self.assertEqual(payload["method"], "POST")
            self.assertEqual(payload["user_id"], self.user_id)

    def test_partial_maintenance_keeps_guide_readable_with_banner(self):
        client = game_app.app.test_client()
        with patch.dict(os.environ, {"MAINTENANCE_MODE": "partial"}):
            resp = client.get("/guide")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("現在アップデート中です。一部機能を停止しています。", html)
        self.assertIn("思想ごとの戦い方", html)

    def test_full_maintenance_blocks_non_admin_but_admin_can_still_use_protected_page(self):
        user_client = self._client_with_user(self.user_id, "ops_user")
        admin_client = self._client_with_user(self.admin_id, "ops_admin")
        with patch.dict(os.environ, {"MAINTENANCE_MODE": "full"}):
            blocked = user_client.get("/parts")
            allowed = admin_client.get("/parts")
        self.assertEqual(blocked.status_code, 503)
        self.assertIn("ただいまメンテナンス中です", blocked.get_data(as_text=True))
        self.assertEqual(allowed.status_code, 200)
        self.assertIn("所持パーツ", allowed.get_data(as_text=True))

    def test_admin_release_page_shows_maintenance_controls(self):
        client = self._client_with_user(self.admin_id, "ops_admin")
        with patch.dict(os.environ, {"MAINTENANCE_MODE": ""}, clear=False):
            resp = client.get("/admin/release")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("メンテナンスモード", html)
        self.assertIn("通常運用", html)
        self.assertIn("軽量メンテ", html)
        self.assertIn("全面メンテ", html)

    def test_admin_can_switch_maintenance_mode_from_admin_release_page(self):
        admin_client = self._client_with_user(self.admin_id, "ops_admin")
        user_client = self._client_with_user(self.user_id, "ops_user")
        with patch.dict(os.environ, {"MAINTENANCE_MODE": "", "MAINTENANCE_SCOPE": ""}, clear=False):
            resp = admin_client.post(
                "/admin/release",
                data={"action": "maintenance_mode", "maintenance_mode": "partial"},
                follow_redirects=False,
            )
            self.assertEqual(resp.status_code, 302)
            blocked = user_client.post("/explore")
        self.assertEqual(blocked.status_code, 503)
        self.assertIn("現在アップデート中です。一部機能を停止しています。", blocked.get_data(as_text=True))
        with game_app.app.app_context():
            db = game_app.get_db()
            state_row = db.execute(
                "SELECT mode, updated_by_user_id FROM maintenance_state WHERE id = 1"
            ).fetchone()
            self.assertIsNotNone(state_row)
            self.assertEqual(state_row["mode"], "partial")
            self.assertEqual(int(state_row["updated_by_user_id"]), int(self.admin_id))
            audit_row = db.execute(
                """
                SELECT payload_json
                FROM world_events_log
                WHERE event_type = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (game_app.AUDIT_EVENT_TYPES["ADMIN_MAINTENANCE_MODE_SET"],),
            ).fetchone()
            self.assertIsNotNone(audit_row)
            payload = json.loads(audit_row["payload_json"])
            self.assertEqual(payload["after_mode"], "partial")
            self.assertEqual(payload["effective_mode"], "partial")
            self.assertEqual(payload["effective_source"], "admin_release")

    def test_header_logo_links_to_home_for_logged_in_and_register_for_guest(self):
        user_client = self._client_with_user(self.user_id, "ops_user")
        logged_in_html = user_client.get("/parts").get_data(as_text=True)
        guest_html = game_app.app.test_client().get("/guide").get_data(as_text=True)
        self.assertIn('class="logo logo-link" href="/home"', logged_in_html)
        self.assertIn('class="logo logo-link" href="/register"', guest_html)

    def test_admin_metrics_is_admin_only(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            created_recent_ts = self._jst_ts(day_offset=-1, hour=10)
            created_returner_ts = self._jst_ts(day_offset=-4, hour=10)
            db.execute(
                "UPDATE users SET created_at = ? WHERE id = ?",
                (created_recent_ts, int(self.user_id)),
            )
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins) VALUES (?, ?, ?, 0, 0)",
                ("ops_returner", "x", created_returner_ts),
            )
            returner_id = int(
                db.execute("SELECT id FROM users WHERE username = ?", ("ops_returner",)).fetchone()["id"]
            )

            tracked_rows = [
                (int(self.user_id), self._login_log_text(self._jst_ts(day_offset=-1, hour=10)), None),
                (int(self.user_id), self._login_log_text(self._jst_ts(day_offset=0, hour=9)), None),
                (int(self.user_id), None, game_app.AUDIT_EVENT_TYPES["HOME_VIEW"]),
                (int(self.user_id), None, game_app.AUDIT_EVENT_TYPES["EXPLORE_START"]),
                (int(self.user_id), None, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"]),
                (int(self.user_id), None, game_app.AUDIT_EVENT_TYPES["FUSE"]),
                (int(self.user_id), None, game_app.AUDIT_EVENT_TYPES["BOSS_ENCOUNTER"]),
                (int(self.user_id), None, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"]),
                (returner_id, self._login_log_text(self._jst_ts(day_offset=-4, hour=10)), None),
                (returner_id, self._login_log_text(self._jst_ts(day_offset=-3, hour=11)), None),
                (returner_id, self._login_log_text(self._jst_ts(day_offset=-1, hour=12)), None),
                (returner_id, None, game_app.AUDIT_EVENT_TYPES["HOME_VIEW"]),
                (returner_id, None, game_app.AUDIT_EVENT_TYPES["BUILD_CONFIRM"]),
                (returner_id, None, game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"]),
            ]
            event_timestamps = {
                game_app.AUDIT_EVENT_TYPES["HOME_VIEW"]: self._jst_ts(day_offset=0, hour=9, minute=5),
                game_app.AUDIT_EVENT_TYPES["EXPLORE_START"]: self._jst_ts(day_offset=0, hour=9, minute=10),
                game_app.AUDIT_EVENT_TYPES["EXPLORE_END"]: self._jst_ts(day_offset=0, hour=9, minute=18),
                game_app.AUDIT_EVENT_TYPES["FUSE"]: self._jst_ts(day_offset=0, hour=9, minute=25),
                game_app.AUDIT_EVENT_TYPES["BOSS_ENCOUNTER"]: self._jst_ts(day_offset=0, hour=9, minute=32),
                game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"]: self._jst_ts(day_offset=0, hour=9, minute=40),
                game_app.AUDIT_EVENT_TYPES["BUILD_CONFIRM"]: self._jst_ts(day_offset=-1, hour=12, minute=5),
                game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"]: self._jst_ts(day_offset=-1, hour=12, minute=10),
            }
            for user_id, login_text, event_type in tracked_rows:
                if login_text:
                    db.execute(
                        "INSERT INTO login_logs (user_id, username, created_at) VALUES (?, ?, ?)",
                        (
                            int(user_id),
                            db.execute("SELECT username FROM users WHERE id = ?", (int(user_id),)).fetchone()["username"],
                            login_text,
                        ),
                    )
                    continue
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        int(event_timestamps[event_type]),
                        str(event_type),
                        json.dumps({}, ensure_ascii=False),
                        int(user_id),
                    ),
                )
            db.commit()

        admin_client = self._client_with_user(self.admin_id, "ops_admin")
        user_client = self._client_with_user(self.user_id, "ops_user")

        admin_resp = admin_client.get("/admin/metrics")
        self.assertEqual(admin_resp.status_code, 200)
        html = admin_resp.get_data(as_text=True)
        self.assertIn("運用メトリクス", html)
        self.assertIn("行動ファネル", html)
        self.assertIn("進行状況", html)
        self.assertIn("層ごとの到達人数", html)
        self.assertIn("停止層ファネル", html)
        self.assertIn("層ボス未撃破", html)
        self.assertIn("ユーザー進行一覧", html)
        self.assertIn("離脱ポイント", html)
        self.assertIn("平均探索数 / DAU", html)
        self.assertIn("登録日ユーザーの初回行動", html)
        self.assertIn("D1再訪率", html)
        self.assertIn("D3再訪率", html)
        self.assertIn("ログイン", html)
        self.assertIn("ホーム表示", html)
        self.assertIn("出撃開始", html)
        self.assertIn("探索完了", html)
        self.assertIn("パーツ強化", html)
        self.assertIn("進化", html)
        self.assertIn("編成完了", html)
        self.assertIn("翌日再訪", html)
        self.assertIn("第1層ボス未撃破", html)
        self.assertIn("ops_returner", html)

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
        self.assertIn("機体アイコン", html)
        self.assertIn("🏆", html)
        self.assertIn("user-trophy-badge", html)
        header_match = re.search(r"<header class=\"top topbar site-header\".*?</header>", html, re.DOTALL)
        self.assertIsNotNone(header_match)
        header_html = header_match.group(0)
        self.assertNotIn('href="/comms"', header_html)

    def test_home_header_shows_founder_badge_from_support_decor_fallback(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute("DELETE FROM user_trophies WHERE user_id = ?", (int(self.user_id),))
            decor = db.execute(
                "SELECT id FROM robot_decor_assets WHERE key = ?",
                (game_app.SUPPORT_PACK_DECOR_KEY,),
            ).fetchone()
            self.assertIsNotNone(decor)
            db.execute(
                """
                INSERT OR IGNORE INTO user_decor_inventory (user_id, decor_asset_id, acquired_at)
                VALUES (?, ?, ?)
                """,
                (int(self.user_id), int(decor["id"]), now),
            )
            db.commit()

        client = self._client_with_user(self.user_id, "ops_user")
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        header_match = re.search(r"<header class=\"top topbar site-header\".*?</header>", html, re.DOTALL)
        self.assertIsNotNone(header_match)
        header_html = header_match.group(0)
        self.assertIn("🏆", header_html)
        self.assertIn("user-trophy-badge", header_html)

    def test_changelog_shows_latest_2026_04_10_entry(self):
        client = game_app.app.test_client()
        resp = client.get("/changelog")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("v0.1.46 - 2026/04/10", html)
        self.assertIn("メンテモードと育成UIの分かりやすさを改善", html)
        self.assertIn("/admin/release", html)
        self.assertIn("MAINTENANCE_MODE=partial/full", html)
        self.assertIn("/parts", html)
        self.assertIn("セットボーナス", html)
        self.assertLess(html.index("v0.1.46 - 2026/04/10"), html.index("v0.1.45 - 2026/04/08"))

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
