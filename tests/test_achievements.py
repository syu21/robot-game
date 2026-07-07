import os
import tempfile
import time
import unittest

import app as game_app
import init_db
from services.achievements import (
    ensure_achievement_defaults,
    equip_profile_reward,
    grant_achievement,
)


class AchievementTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer, coins)
                VALUES (?, ?, ?, 0, 0, 1, 0)
                """,
                ("achievement_user", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("achievement_user",)).fetchone()["id"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "achievement_user"
        return client

    def test_default_achievements_are_seeded(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            ensure_achievement_defaults(db)
            count = int(db.execute("SELECT COUNT(*) AS c FROM achievements").fetchone()["c"])
            self.assertGreaterEqual(count, 8)
            self.assertIsNotNone(db.execute("SELECT 1 FROM achievements WHERE key = 'first_explore'").fetchone())

    def test_grant_is_idempotent_and_audited(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            first = grant_achievement(db, self.user_id, "first_explore", source_event_type="test")
            second = grant_achievement(db, self.user_id, "first_explore", source_event_type="test")
            db.commit()
            self.assertTrue(first["granted"])
            self.assertFalse(second["granted"])
            count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM user_achievements WHERE user_id = ? AND achievement_key = ?",
                    (self.user_id, "first_explore"),
                ).fetchone()["c"]
            )
            self.assertEqual(count, 1)
            event = db.execute(
                "SELECT id FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["ACHIEVEMENT_GRANT"]),
            ).fetchone()
            self.assertIsNotNone(event)

    def test_unowned_achievement_cannot_be_equipped(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            result = equip_profile_reward(db, self.user_id, "badge", "first_win")
            self.assertFalse(result["ok"])

    def test_owned_achievement_can_be_equipped(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            grant_achievement(db, self.user_id, "supporter", source_event_type="test")
            result = equip_profile_reward(db, self.user_id, "frame", "supporter")
            db.commit()
            self.assertTrue(result["ok"])
            row = db.execute(
                "SELECT equipped_frame_key FROM user_profile_rewards WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()
            self.assertEqual(row["equipped_frame_key"], "supporter")

    def test_achievements_page_requires_login_and_displays(self):
        anon = game_app.app.test_client()
        anon_response = anon.get("/achievements")
        self.assertEqual(anon_response.status_code, 302)
        response = self._client().get("/achievements")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("研究実績", html)
        self.assertIn("初出撃", html)


if __name__ == "__main__":
    unittest.main()
