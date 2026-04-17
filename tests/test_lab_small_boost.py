import os
import tempfile
import time
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlparse

import app as game_app
import init_db


class LabSmallBoostTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        self.old_testing = game_app.app.config.get("TESTING")
        self.old_bypass = game_app.app.config.get("BYPASS_RELEASE_GATES_IN_TESTS")
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        init_db.main()
        game_app.app.config["TESTING"] = True
        game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = True

        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 0, 0, 0, 1)
                """,
                ("research_boost_user", "x", now - (100 * 3600)),
            )
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 1, 1, 0, 1)
                """,
                ("research_boost_admin", "x", now - (100 * 3600)),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("research_boost_user",)).fetchone()["id"])
            self.admin_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("research_boost_admin",)).fetchone()["id"])
            db.commit()
        self.active_robot_id = self._create_active_robot(self.user_id)

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        if self.old_testing is None:
            game_app.app.config.pop("TESTING", None)
        else:
            game_app.app.config["TESTING"] = self.old_testing
        if self.old_bypass is None:
            game_app.app.config.pop("BYPASS_RELEASE_GATES_IN_TESTS", None)
        else:
            game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = self.old_bypass
        self.tmpdir.cleanup()

    def _client(self, *, admin=False):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.admin_id if admin else self.user_id
            session["username"] = "research_boost_admin" if admin else "research_boost_user"
        return client

    def _create_active_robot(self, user_id):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (int(user_id), "ResearchRunner", now, now),
            )
            robot_id = int(
                db.execute(
                    "SELECT id FROM robot_instances WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                    (int(user_id),),
                ).fetchone()["id"]
            )

            def pick_key(part_type):
                row = db.execute(
                    "SELECT key FROM robot_parts WHERE part_type = ? AND is_active = 1 ORDER BY id ASC LIMIT 1",
                    (part_type,),
                ).fetchone()
                self.assertIsNotNone(row)
                return row["key"]

            db.execute(
                """
                INSERT INTO robot_instance_parts (robot_instance_id, head_key, r_arm_key, l_arm_key, legs_key)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    robot_id,
                    pick_key("HEAD"),
                    pick_key("RIGHT_ARM"),
                    pick_key("LEFT_ARM"),
                    pick_key("LEGS"),
                ),
            )
            db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (robot_id, int(user_id)))
            db.commit()
            return robot_id

    def _set_last_action_at(self, user_id, last_action_at):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                INSERT INTO battle_state (user_id, enemy_name, enemy_hp, last_action_at, active)
                VALUES (?, 'CT_TEST_ENEMY', 5, ?, 0)
                ON CONFLICT(user_id) DO UPDATE SET
                    enemy_name = excluded.enemy_name,
                    enemy_hp = excluded.enemy_hp,
                    last_action_at = excluded.last_action_at,
                    active = excluded.active
                """,
                (int(user_id), int(last_action_at)),
            )
            db.commit()

    def test_home_grants_daily_login_stock_once_and_renders_controls(self):
        client = self._client()

        first = client.get("/home")
        self.assertEqual(first.status_code, 200)
        html = first.get_data(as_text=True)
        self.assertIn("研究ブースト 1 / 3", html)
        self.assertIn("次の1回はCTなしで出撃できます", html)
        self.assertIn("1回の出撃で1つ消費します", html)
        self.assertIn("自動使用: ON", html)
        self.assertIn("OFFにする", html)
        self.assertNotIn("10分使う", html)
        self.assertNotIn("10分間 出撃CT半減", html)
        self.assertIn("Xでシェアして研究ブースト +1回", html)
        self.assertIn("1日1回 / 現在機体画像つき", html)
        self.assertIn("研究ブーストを1回分獲得しました（1/3）", html)

        second = client.get("/home")
        self.assertEqual(second.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT research_boost_charges FROM users WHERE id = ?", (self.user_id,)).fetchone()
            event_count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
                    (self.user_id, game_app.AUDIT_EVENT_TYPES["RESEARCH_BOOST_GRANT"]),
                ).fetchone()["c"]
                or 0
            )
            self.assertEqual(int(user["research_boost_charges"]), 1)
            self.assertEqual(event_count, 1)

    def test_daily_login_does_not_exceed_stock_cap(self):
        client = self._client()
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET research_boost_charges = 3 WHERE id = ?", (self.user_id,))
            db.commit()

        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("研究ブーストは上限です（3/3）", html)
        self.assertIn("研究ブースト 3 / 3", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT research_boost_charges FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(user["research_boost_charges"]), 3)

    def test_research_boost_toggle_disables_auto_use_and_preserves_stock(self):
        client = self._client()
        client.get("/home")

        toggled = client.post("/home/research-boost/toggle", follow_redirects=True)
        self.assertEqual(toggled.status_code, 200)
        html = toggled.get_data(as_text=True)
        self.assertIn("研究ブースト自動使用をOFFにしました。", html)
        self.assertIn("自動使用: OFF", html)
        self.assertIn("ONにする", html)
        self.assertIn("OFF中です。ONにすると出撃時に使います", html)

        self._set_last_action_at(self.user_id, int(time.time()))
        with mock.patch.object(game_app, "_has_area_boss_candidates", return_value=False):
            blocked = client.post("/explore", data={"area_key": "layer_1"}, follow_redirects=False)
        self.assertEqual(blocked.status_code, 302)

        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute(
                "SELECT research_boost_charges, research_boost_auto_use_enabled FROM users WHERE id = ?",
                (self.user_id,),
            ).fetchone()
            consume_count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
                    (self.user_id, game_app.AUDIT_EVENT_TYPES["RESEARCH_BOOST_CONSUME"]),
                ).fetchone()["c"]
                or 0
            )
            toggle_count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
                    (self.user_id, game_app.AUDIT_EVENT_TYPES["RESEARCH_BOOST_TOGGLE"]),
                ).fetchone()["c"]
                or 0
            )
            self.assertEqual(int(user["research_boost_charges"]), 1)
            self.assertEqual(int(user["research_boost_auto_use_enabled"]), 0)
            self.assertEqual(consume_count, 0)
            self.assertEqual(toggle_count, 1)

        restored = client.post("/home/research-boost/toggle", follow_redirects=True)
        self.assertEqual(restored.status_code, 200)
        self.assertIn("研究ブースト自動使用をONにしました。", restored.get_data(as_text=True))
        self.assertIn("自動使用: ON", restored.get_data(as_text=True))

    def test_schema_compat_does_not_restore_consumed_charges_from_legacy_columns(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                UPDATE users
                SET lab_small_boost_count = 3,
                    lab_small_boost_until = ?,
                    research_boost_charges = 0
                WHERE id = ?
                """,
                (int(time.time()) + 600, self.user_id),
            )
            db.commit()

            game_app.ensure_schema(db)
            user = db.execute("SELECT research_boost_charges FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(user["research_boost_charges"]), 0)

    def test_lab_participation_grants_stock_once_per_day(self):
        client = self._client()

        first = client.get("/lab/showcase")
        self.assertEqual(first.status_code, 200)
        second = client.get("/lab/showcase")
        self.assertEqual(second.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT research_boost_charges FROM users WHERE id = ?", (self.user_id,)).fetchone()
            event_count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
                    (self.user_id, game_app.AUDIT_EVENT_TYPES["RESEARCH_BOOST_GRANT"]),
                ).fetchone()["c"]
                or 0
            )
            self.assertEqual(int(user["research_boost_charges"]), 1)
            self.assertEqual(event_count, 1)

    def test_x_share_grants_daily_stock_once_and_redirects_to_intent(self):
        client = self._client()

        first = client.post("/home/research-boost/x-share", follow_redirects=False)
        self.assertEqual(first.status_code, 302)
        location = first.headers.get("Location", "")
        self.assertTrue(location.startswith("https://x.com/intent/tweet?"))
        text = parse_qs(urlparse(location).query).get("text", [""])[0]
        self.assertIn("今日のロボらぼ", text)
        self.assertIn(f"/share/robot/{self.active_robot_id}", text)

        second = client.post("/home/research-boost/x-share", follow_redirects=False)
        self.assertEqual(second.status_code, 302)

        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT research_boost_charges FROM users WHERE id = ?", (self.user_id,)).fetchone()
            grant_count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
                    (self.user_id, game_app.AUDIT_EVENT_TYPES["RESEARCH_BOOST_GRANT"]),
                ).fetchone()["c"]
                or 0
            )
            share_count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
                    (self.user_id, game_app.AUDIT_EVENT_TYPES["SHARE_CLICK"]),
                ).fetchone()["c"]
                or 0
            )
            payload_row = db.execute(
                """
                SELECT payload_json
                FROM world_events_log
                WHERE user_id = ? AND event_type = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (self.user_id, game_app.AUDIT_EVENT_TYPES["SHARE_CLICK"]),
            ).fetchone()
            self.assertEqual(int(user["research_boost_charges"]), 1)
            self.assertEqual(grant_count, 1)
            self.assertEqual(share_count, 2)
            self.assertIn('"reason": "daily_x_share"', payload_row["payload_json"])
            self.assertIn('"boost_granted": true', payload_row["payload_json"])

    def test_share_robot_public_page_has_ogp_image(self):
        client = game_app.app.test_client()

        resp = client.get(f"/share/robot/{self.active_robot_id}")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("ResearchRunner | ロボらぼ", html)
        self.assertIn('property="og:image"', html)
        self.assertIn('property="og:url"', html)
        self.assertIn("ロボらぼで育てた機体を公開中", html)

    def test_explore_consumes_research_boost_charge_and_skips_ct(self):
        client = self._client()
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET research_boost_charges = 1 WHERE id = ?", (self.user_id,))
            db.commit()
        self._set_last_action_at(self.user_id, int(time.time()))

        with mock.patch.object(game_app, "_has_area_boss_candidates", return_value=False):
            resp = client.post("/explore", data={"area_key": "layer_1"})
        self.assertEqual(resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT research_boost_charges FROM users WHERE id = ?", (self.user_id,)).fetchone()
            state = db.execute("SELECT last_action_at FROM battle_state WHERE user_id = ?", (self.user_id,)).fetchone()
            consume_count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
                    (self.user_id, game_app.AUDIT_EVENT_TYPES["RESEARCH_BOOST_CONSUME"]),
                ).fetchone()["c"]
                or 0
            )
            self.assertEqual(int(user["research_boost_charges"]), 0)
            self.assertEqual(int(state["last_action_at"] or 0), 0)
            self.assertEqual(consume_count, 1)

        with mock.patch.object(game_app, "_has_area_boss_candidates", return_value=False):
            next_resp = client.post("/explore", data={"area_key": "layer_1"})
            blocked = client.post("/explore", data={"area_key": "layer_1"}, follow_redirects=False)
        self.assertEqual(next_resp.status_code, 200)
        self.assertEqual(blocked.status_code, 302)

    def test_research_boost_does_not_change_newbie_or_paid_ct_seconds(self):
        now = int(time.time())
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                UPDATE users
                SET created_at = ?, research_boost_charges = 2, explore_boost_until = 0
                WHERE id = ?
                """,
                (now, self.user_id),
            )
            user = db.execute("SELECT * FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(game_app._explore_ct_seconds_for_user(user, now_ts=now), 20)

            db.execute(
                "UPDATE users SET explore_boost_until = ? WHERE id = ?",
                (now + 86400, self.user_id),
            )
            paid_user = db.execute("SELECT * FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(game_app._explore_ct_seconds_for_user(paid_user, now_ts=now), 20)

    def test_paid_booster_still_consumes_research_boost_for_this_explore(self):
        client = self._client()
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                "UPDATE users SET research_boost_charges = 1, explore_boost_until = ? WHERE id = ?",
                (int(time.time()) + 86400, self.user_id),
            )
            db.commit()
        self._set_last_action_at(self.user_id, int(time.time()))

        with mock.patch.object(game_app, "_has_area_boss_candidates", return_value=False):
            resp = client.post("/explore", data={"area_key": "layer_1"})
        self.assertEqual(resp.status_code, 200)
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT research_boost_charges FROM users WHERE id = ?", (self.user_id,)).fetchone()
            state = db.execute("SELECT last_action_at FROM battle_state WHERE user_id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(user["research_boost_charges"]), 0)
            self.assertEqual(int(state["last_action_at"] or 0), 0)

    def test_admin_explore_does_not_consume_research_boost(self):
        self._create_active_robot(self.admin_id)
        client = self._client(admin=True)
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET research_boost_charges = 1 WHERE id = ?", (self.admin_id,))
            db.commit()
        self._set_last_action_at(self.admin_id, int(time.time()))

        with mock.patch.object(game_app, "_has_area_boss_candidates", return_value=False):
            resp = client.post("/explore", data={"area_key": "layer_1"})
        self.assertEqual(resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT research_boost_charges FROM users WHERE id = ?", (self.admin_id,)).fetchone()
            consume_count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
                    (self.admin_id, game_app.AUDIT_EVENT_TYPES["RESEARCH_BOOST_CONSUME"]),
                ).fetchone()["c"]
                or 0
            )
            self.assertEqual(int(user["research_boost_charges"]), 1)
            self.assertEqual(consume_count, 0)

    def test_feedback_post_does_not_grant_research_boost_stock(self):
        client = self._client()
        resp = client.post(
            "/comms/rooms?room=feedback_room",
            data={
                "room_key": "feedback_room",
                "message": "研究ブーストの確認投稿です",
                "next": "/comms/rooms?room=feedback_room",
            },
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT research_boost_charges FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(user["research_boost_charges"]), 0)

    def test_research_boost_release_control_only_lives_on_release_page(self):
        game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = False
        admin_client = self._client(admin=True)

        menu_resp = admin_client.get("/admin")
        self.assertEqual(menu_resp.status_code, 200)
        menu_html = menu_resp.get_data(as_text=True)
        self.assertNotIn("研究ブースト公開設定", menu_html)
        self.assertNotIn("研究ブーストを一般公開する", menu_html)

        release_resp = admin_client.get("/admin/release")
        self.assertEqual(release_resp.status_code, 200)
        release_html = release_resp.get_data(as_text=True)
        self.assertIn("研究ブースト", release_html)
        self.assertIn("一般公開する", release_html)

    def test_research_boost_release_flag_controls_public_home_surface(self):
        game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = False
        user_client = self._client()
        admin_client = self._client(admin=True)

        hidden = user_client.get("/home")
        self.assertEqual(hidden.status_code, 200)
        self.assertNotIn("研究ブースト", hidden.get_data(as_text=True))

        opened = admin_client.post(
            "/admin/release",
            data={"feature_key": game_app.LAB_SMALL_BOOST_FEATURE_KEY, "state": "public"},
            follow_redirects=True,
        )
        self.assertEqual(opened.status_code, 200)
        self.assertIn("研究ブースト を一般公開しました", opened.get_data(as_text=True))

        visible = user_client.get("/home")
        self.assertEqual(visible.status_code, 200)
        self.assertIn("研究ブースト 1 / 3", visible.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
