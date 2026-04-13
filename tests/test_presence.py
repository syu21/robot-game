import os
import tempfile
import unittest
from datetime import datetime, timedelta

import app as game_app
import init_db
from services.presence import (
    JST,
    get_presence_count,
    get_recent_presence,
    serialize_presence_entry,
    touch_presence,
)


class PresenceTests(unittest.TestCase):
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
            now = int(datetime.now(JST).timestamp())
            db.execute(
                """
                INSERT INTO users (username, display_name, password_hash, created_at, last_seen_at, is_admin, is_banned, wins, max_unlocked_layer)
                VALUES (?, ?, 'x', ?, ?, 0, 0, 1, 1)
                """,
                ("presence_user", "ぷれ研究員", now, now),
            )
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, last_seen_at, is_admin, is_banned, wins, max_unlocked_layer)
                VALUES (?, 'x', ?, ?, 0, 1, 1, 1)
                """,
                ("presence_banned", now, now),
            )
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, last_seen_at, is_admin, is_banned, wins, max_unlocked_layer)
                VALUES (?, 'x', ?, ?, 1, 0, 1, 1)
                """,
                ("presence_admin", now, now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("presence_user",)).fetchone()["id"])
            self.banned_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("presence_banned",)).fetchone()["id"])
            self.admin_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("presence_admin",)).fetchone()["id"])
            db.commit()
        self.robot_id = self._create_active_robot(self.user_id)

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

    def _create_active_robot(self, user_id):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(datetime.now(JST).timestamp())
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, 'PresenceRunner', 'active', ?, ?)
                """,
                (int(user_id), now, now),
            )
            robot_id = int(db.execute("SELECT id FROM robot_instances WHERE user_id = ?", (int(user_id),)).fetchone()["id"])

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

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "presence_user"
        return client

    def test_touch_presence_upserts_one_row_per_user(self):
        now = datetime(2026, 4, 13, 12, 0, tzinfo=JST)
        with game_app.app.app_context():
            db = game_app.get_db()
            touch_presence(db, self.user_id, "home", "home.view", path="/home", now=now)
            touch_presence(db, self.user_id, "lab", "lab.view", path="/lab", now=now + timedelta(minutes=1))
            rows = db.execute("SELECT * FROM user_presence WHERE user_id = ?", (self.user_id,)).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["last_surface"], "lab")
            self.assertEqual(rows[0]["last_path"], "/lab")

            entries = get_recent_presence(db, limit=10, within_minutes=20, include_admin=True, now=now + timedelta(minutes=2))
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["state_label"], "実験室参加中")

    def test_recent_presence_filters_window_ban_and_admin(self):
        now = datetime(2026, 4, 13, 12, 0, tzinfo=JST)
        with game_app.app.app_context():
            db = game_app.get_db()
            touch_presence(db, self.user_id, "home", "home.view", now=now)
            touch_presence(db, self.banned_id, "home", "home.view", now=now)
            touch_presence(db, self.admin_id, "home", "home.view", now=now)
            old_user_id = self.user_id
            touch_presence(db, old_user_id, "world", "world.view", now=now - timedelta(minutes=30))
            touch_presence(db, self.admin_id, "home", "home.view", now=now)

            self.assertEqual(get_presence_count(db, within_minutes=20, include_admin=False, now=now), 0)
            self.assertEqual(get_presence_count(db, within_minutes=20, include_admin=True, now=now), 1)

            touch_presence(db, self.user_id, "home", "home.view", now=now)
            self.assertEqual(get_presence_count(db, within_minutes=20, include_admin=False, now=now), 1)
            self.assertEqual(get_presence_count(db, within_minutes=20, include_admin=True, now=now), 2)

    def test_state_labels_tone_and_minutes_are_stable(self):
        now = datetime(2026, 4, 13, 12, 0, tzinfo=JST)
        recent = serialize_presence_entry(
            {
                "user_id": self.user_id,
                "username": "presence_user",
                "last_active_at": (now - timedelta(minutes=4)).isoformat(timespec="seconds"),
                "last_surface": "explore",
                "last_action_key": "explore.start",
            },
            now=now,
        )
        idle = serialize_presence_entry(
            {
                "user_id": self.user_id,
                "username": "presence_user",
                "last_active_at": (now - timedelta(minutes=12)).isoformat(timespec="seconds"),
                "last_surface": "home",
                "last_action_key": "home.view",
            },
            now=now,
        )
        self.assertEqual(recent["state_label"], "出撃中")
        self.assertEqual(recent["tone"], "active")
        self.assertEqual(recent["minutes_ago"], 4)
        self.assertEqual(idle["state_label"], "さっきまで参加")
        self.assertEqual(idle["tone"], "idle")
        self.assertGreaterEqual(idle["minutes_ago"], 0)

    def test_home_renders_presence_bar_and_api_requires_login(self):
        anonymous = game_app.app.test_client()
        self.assertEqual(anonymous.get("/api/presence/recent").status_code, 302)

        client = self._client()
        with game_app.app.app_context():
            db = game_app.get_db()
            touch_presence(db, self.admin_id, "home", "home.view")
            db.commit()

        home = client.get("/home")
        self.assertEqual(home.status_code, 200)
        html = home.get_data(as_text=True)
        self.assertIn("研究員 1名 参加中", html)
        self.assertIn("現在の参加研究員", html)

        api = client.get("/api/presence/recent?limit=24")
        self.assertEqual(api.status_code, 200)
        data = api.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["entries"][0]["display_name"], "ぷれ研究員")
        self.assertIn("robot_icon_32_url", data["entries"][0])
        self.assertIn("avatar_url", data["entries"][0])
        self.assertIn("state_label", data["entries"][0])
        self.assertIn("minutes_ago", data["entries"][0])


if __name__ == "__main__":
    unittest.main()
