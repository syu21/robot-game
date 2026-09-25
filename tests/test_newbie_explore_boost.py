import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class NewbieExploreBoostTests(unittest.TestCase):
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
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins) VALUES (?, ?, ?, 0, 0)",
                ("newbie_boost_user", "x", now),
            )
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins) VALUES (?, ?, ?, 1, 0)",
                ("newbie_boost_admin", "x", now - 100 * 3600),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("newbie_boost_user",),
            ).fetchone()["id"]
            self.admin_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("newbie_boost_admin",),
            ).fetchone()["id"]
            db.commit()

        self._create_active_robot(self.user_id)
        self._create_active_robot(self.admin_id)

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    @staticmethod
    def _resolve_for_win(att_atk, att_acc, att_cri, def_def, def_acc, **kwargs):
        if int(att_atk) >= 5:
            return 999, False
        return 0, False

    def _create_active_robot(self, user_id):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (user_id, "BoostRunner", now, now),
            )
            robot_id = db.execute(
                "SELECT id FROM robot_instances WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (user_id,),
            ).fetchone()["id"]

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
            db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (robot_id, user_id))
            db.commit()

    def _set_last_action_at(self, user_id, last_action_at):
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT user_id FROM battle_state WHERE user_id = ?", (user_id,)).fetchone()
            if row is None:
                db.execute(
                    """
                    INSERT INTO battle_state (user_id, enemy_name, enemy_hp, last_action_at, active)
                    VALUES (?, 'CT_TEST_ENEMY', 5, ?, 1)
                    """,
                    (user_id, int(last_action_at)),
                )
            else:
                db.execute(
                    "UPDATE battle_state SET enemy_name = 'CT_TEST_ENEMY', enemy_hp = 5, active = 1, last_action_at = ? WHERE user_id = ?",
                    (int(last_action_at), user_id),
                )
            db.commit()

    def _mark_initial_sprint_complete(self, user_id):
        with game_app.app.app_context():
            db = game_app.get_db()
            for i in range(3):
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id, action_key)
                    VALUES (?, ?, ?, ?, 'explore')
                    """,
                    (
                        int(time.time()) - (30 - i),
                        game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                        '{"area_key":"layer_1","result":{"win":true}}',
                        int(user_id),
                    ),
                )
            db.commit()

    def _new_client(self, user_id, username):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = user_id
            session["username"] = username
        return client

    def test_newbie_boost_applies_20_seconds_cooldown(self):
        self._mark_initial_sprint_complete(self.user_id)
        now = int(time.time())
        self._set_last_action_at(self.user_id, now - 10)
        client = self._new_client(self.user_id, "newbie_boost_user")
        resp = client.post("/explore", data={"area_key": "layer_1"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertRegex(resp.get_data(as_text=True), r"あと ?(9|10)秒")

    def test_after_72_hours_cooldown_returns_to_40_seconds(self):
        now = int(time.time())
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                "UPDATE users SET created_at = ? WHERE id = ?",
                (now - (73 * 3600), self.user_id),
            )
            db.commit()
        self._mark_initial_sprint_complete(self.user_id)
        self._set_last_action_at(self.user_id, now - 10)
        client = self._new_client(self.user_id, "newbie_boost_user")
        resp = client.post("/explore", data={"area_key": "layer_1"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertRegex(html, r"あと ?(28|29|30)秒")

    def test_admin_ignores_cooldown_even_when_recently_actioned(self):
        self._set_last_action_at(self.admin_id, int(time.time()))
        client = self._new_client(self.admin_id, "newbie_boost_admin")
        with patch.object(game_app, "resolve_attack", side_effect=self._resolve_for_win), patch.object(
            game_app,
            "_has_area_boss_candidates",
            return_value=False,
        ):
            resp = client.post("/explore", data={"area_key": "layer_1"}, follow_redirects=False)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.content_type)

    def test_home_no_longer_shows_legacy_newbie_boost_card(self):
        client = self._new_client(self.user_id, "newbie_boost_user")
        active_html = client.get("/home").get_data(as_text=True)
        self.assertNotIn("新規ブースト中: 探索CT短縮", active_html)

        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                "UPDATE users SET created_at = ? WHERE id = ?",
                (int(time.time()) - (73 * 3600), self.user_id),
            )
            db.commit()
        expired_html = client.get("/home").get_data(as_text=True)
        self.assertNotIn("新規ブースト中: 探索CT短縮", expired_html)

    def test_explore_post_is_blocked_by_same_ct_even_when_state_inactive(self):
        self._mark_initial_sprint_complete(self.user_id)
        now = int(time.time())
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
                (self.user_id, now - 10),
            )
            db.commit()
        client = self._new_client(self.user_id, "newbie_boost_user")
        resp = client.post("/explore", data={"area_key": "layer_1"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertRegex(resp.get_data(as_text=True), r"あと ?(9|10)秒")

    def test_consecutive_explore_post_second_request_is_blocked(self):
        self._mark_initial_sprint_complete(self.user_id)
        client = self._new_client(self.user_id, "newbie_boost_user")
        with patch.object(game_app, "resolve_attack", side_effect=self._resolve_for_win), patch.object(
            game_app,
            "_has_area_boss_candidates",
            return_value=False,
        ):
            first = client.post("/explore", data={"area_key": "layer_1"}, follow_redirects=False)
        self.assertEqual(first.status_code, 200)

        second = client.post("/explore", data={"area_key": "layer_1"}, follow_redirects=True)
        self.assertEqual(second.status_code, 200)
        self.assertRegex(second.get_data(as_text=True), r"あと ?\d+秒")

        with game_app.app.app_context():
            db = game_app.get_db()
            start_count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
                    (self.user_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_START"]),
                ).fetchone()["c"]
                or 0
            )
        self.assertEqual(start_count, 1)

    def test_initial_sortie_sprint_ignores_cooldown_until_three_completions(self):
        now = int(time.time())
        self._set_last_action_at(self.user_id, now - 1)
        client = self._new_client(self.user_id, "newbie_boost_user")
        with patch.object(game_app, "resolve_attack", side_effect=self._resolve_for_win), patch.object(
            game_app,
            "_has_area_boss_candidates",
            return_value=False,
        ):
            first = client.post(
                "/explore",
                data={"area_key": "layer_1", "entry_source": "next_action_first_explore", "surface": "home"},
                follow_redirects=False,
            )
            second = client.post(
                "/explore",
                data={"area_key": "layer_1", "entry_source": "onboarding_sortie_sprint", "surface": "battle_result"},
                follow_redirects=False,
            )
            third = client.post(
                "/explore",
                data={"area_key": "layer_1", "entry_source": "onboarding_sortie_sprint", "surface": "battle_result"},
                follow_redirects=False,
            )
        self.assertEqual(first.status_code, 200)
        self.assertIn("第2試験へ出撃", first.get_data(as_text=True))
        self.assertEqual(second.status_code, 200)
        self.assertIn("最終試験へ出撃", second.get_data(as_text=True))
        self.assertEqual(third.status_code, 200)
        third_html = third.get_data(as_text=True)
        self.assertIn("起動試験 COMPLETE", third_html)
        self.assertIn("ここから自由に機体を育てられます。", third_html)

        with game_app.app.app_context():
            db = game_app.get_db()
            clicks = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ? ORDER BY id",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["ONBOARDING_SORTIE_CTA_CLICK"]),
            ).fetchall()
        self.assertEqual(len(clicks), 3)
        click_payloads = [json.loads(row["payload_json"]) for row in clicks]
        self.assertEqual([payload["sortie_index"] for payload in click_payloads], [1, 2, 3])
        self.assertEqual([payload["surface"] for payload in click_payloads], ["home", "battle_result", "battle_result"])
        self.assertEqual(click_payloads[0]["entry_source"], "next_action_first_explore")
        self.assertTrue(all(payload["entry_source"] == "onboarding_sortie_sprint" for payload in click_payloads[1:]))

        blocked = client.post("/explore", data={"area_key": "layer_1"}, follow_redirects=True)
        self.assertEqual(blocked.status_code, 200)
        self.assertRegex(blocked.get_data(as_text=True), r"あと ?\d+秒")

    def test_initial_sortie_home_progress_uses_historical_successful_completions(self):
        now = int(time.time())
        client = self._new_client(self.user_id, "newbie_boost_user")
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET created_at = ? WHERE id = ?", (now - 864000, self.user_id))
            db.commit()

        zero_html = client.get("/home").get_data(as_text=True)
        self.assertIn("起動試験", zero_html)
        self.assertIn("0 / 3", zero_html)

        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                "INSERT INTO world_events_log (created_at, event_type, payload_json, user_id, action_key) VALUES (?, ?, '{}', ?, 'explore')",
                (now - 3, game_app.AUDIT_EVENT_TYPES["EXPLORE_FAILED"], self.user_id),
            )
            db.commit()
            user = db.execute("SELECT * FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(game_app._initial_sortie_sprint_state(db, user)["completed"], 0)

            for completed in (1, 2):
                db.execute(
                    "INSERT INTO world_events_log (created_at, event_type, payload_json, user_id, action_key) VALUES (?, ?, ?, ?, 'explore')",
                    (now + completed, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], '{"area_key":"layer_1"}', self.user_id),
                )
                db.commit()
                html = client.get("/home").get_data(as_text=True)
                self.assertIn(f"{completed} / 3", html)
                user = db.execute("SELECT * FROM users WHERE id = ?", (self.user_id,)).fetchone()
                self.assertEqual(game_app._explore_ct_policy_for_user(user, db=db)["seconds"], 0)

            db.execute(
                "INSERT INTO world_events_log (created_at, event_type, payload_json, user_id, action_key) VALUES (?, ?, ?, ?, 'explore')",
                (now + 3, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], '{"area_key":"layer_1"}', self.user_id),
            )
            db.commit()

        complete_html = client.get("/home").get_data(as_text=True)
        self.assertNotIn('aria-label="起動試験', complete_html)
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT * FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(game_app._explore_ct_policy_for_user(user, db=db)["seconds"], 40)

    def test_paid_boost_resumes_after_initial_sortie_sprint(self):
        now = int(time.time())
        self._mark_initial_sprint_complete(self.user_id)
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                "UPDATE users SET created_at = ?, explore_boost_until = ? WHERE id = ?",
                (now - 864000, now + 3600, self.user_id),
            )
            db.commit()
            user = db.execute("SELECT * FROM users WHERE id = ?", (self.user_id,)).fetchone()
            policy = game_app._explore_ct_policy_for_user(user, now_ts=now, db=db)
        self.assertEqual(policy, {"seconds": 20, "reason": "paid_explore_boost"})

    def test_initial_sortie_sprint_guarantees_one_n_part_on_third_if_no_prior_drop(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            for i in range(2):
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id, action_key)
                    VALUES (?, ?, ?, ?, 'explore')
                    """,
                    (
                        int(time.time()) - (20 - i),
                        game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                        '{"area_key":"layer_1","result":{"win":true}}',
                        int(self.user_id),
                    ),
                )
            db.commit()

        client = self._new_client(self.user_id, "newbie_boost_user")
        with patch.object(game_app, "resolve_attack", side_effect=self._resolve_for_win), patch.object(
            game_app,
            "_has_area_boss_candidates",
            return_value=False,
        ), patch.object(game_app, "_market_part_drop_chance", return_value=0.0), patch.object(
            game_app,
            "_dinosaur_debut_campaign_active",
            return_value=False,
        ):
            resp = client.post(
                "/explore",
                data={"area_key": "layer_1", "entry_source": "onboarding_sortie_sprint_3"},
                follow_redirects=False,
            )
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("起動試験支給", html)
        self.assertIn("Nパーツを1個回収しました", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            guarantee = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM world_events_log
                WHERE user_id = ? AND event_type = ?
                """,
                (int(self.user_id), game_app.AUDIT_EVENT_TYPES["ONBOARDING_PART_GUARANTEE"]),
            ).fetchone()
            self.assertEqual(int(guarantee["c"] or 0), 1)
            event = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ? ORDER BY id DESC LIMIT 1",
                (int(self.user_id), game_app.AUDIT_EVENT_TYPES["ONBOARDING_PART_GUARANTEE"]),
            ).fetchone()
            payload = json.loads(event["payload_json"])
            self.assertEqual(payload["drop_source"], "onboarding_guarantee")
            self.assertEqual(payload["onboarding_sortie_index"], 3)
            user = db.execute("SELECT * FROM users WHERE id = ?", (int(self.user_id),)).fetchone()
            recommendation = game_app._first_upgrade_recommendation(db, user)
            self.assertIsNotNone(recommendation)
            self.assertTrue(recommendation["is_improvement"])


if __name__ == "__main__":
    unittest.main()
