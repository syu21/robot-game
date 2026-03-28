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

    def _new_client(self, user_id, username):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = user_id
            session["username"] = username
        return client

    def test_newbie_boost_applies_20_seconds_cooldown(self):
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


if __name__ == "__main__":
    unittest.main()
