import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class CompanionTests(unittest.TestCase):
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
                ("companion_user", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("companion_user",)).fetchone()["id"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "companion_user"
        return client

    def test_companion_initial_access_unlocks_defaults(self):
        html = self._client().get("/companion").get_data(as_text=True)
        self.assertIn("相棒ロボ研究所", html)
        self.assertIn("偵察ペットロボ", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertEqual(int(db.execute("SELECT COUNT(*) AS c FROM companion_robot_masters").fetchone()["c"]), 3)
            self.assertEqual(int(db.execute("SELECT COUNT(*) AS c FROM user_companion_robots WHERE user_id = ?", (self.user_id,)).fetchone()["c"]), 3)
            user = db.execute("SELECT active_companion_key FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(user["active_companion_key"], "collector_petbot")

    def test_companion_equip_and_upgrade_audit(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_companions(db, self.user_id)
            equip = game_app.equip_companion(db, self.user_id, "maintenance_petbot", request_id="companion-equip")
            self.assertTrue(equip["ok"])
            db.execute("UPDATE users SET factory_points = 300 WHERE id = ?", (self.user_id,))
            upgrade = game_app.upgrade_companion(db, self.user_id, "maintenance_petbot", request_id="companion-upgrade")
            self.assertTrue(upgrade["ok"])
            row = db.execute("SELECT level FROM user_companion_robots WHERE user_id = ? AND companion_key = ?", (self.user_id, "maintenance_petbot")).fetchone()
            self.assertEqual(int(row["level"]), 2)
            for event_type in (game_app.AUDIT_EVENT_TYPES["COMPANION_EQUIP"], game_app.AUDIT_EVENT_TYPES["COMPANION_UPGRADE"], game_app.AUDIT_EVENT_TYPES["FACTORY_POINTS_DELTA"]):
                event = db.execute(
                    "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ? ORDER BY id DESC LIMIT 1",
                    (self.user_id, event_type),
                ).fetchone()
                self.assertIsNotNone(event)
            payload = json.loads(event["payload_json"] or "{}")
            self.assertEqual(payload["companion_key"], "maintenance_petbot")

    def test_lab_submission_source_requires_approved(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_companions(db, self.user_id)
            now = int(time.time())
            db.execute(
                """
                INSERT INTO lab_robot_submissions
                (user_id, title, comment, image_path, thumb_path, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (self.user_id, "未承認ロボ", "", "x.png", "x.png", now, now),
            )
            pending_id = int(db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
            db.execute(
                """
                INSERT INTO companion_robot_masters
                (companion_key, name_ja, description, effect_type, base_effect_value, source_type, source_id, image_path, is_active, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, 0, 'lab_submission', ?, '', 1, 90, ?, ?)
                """,
                ("pending_submission_petbot", "未承認相棒", "", "scout_log", pending_id, now, now),
            )
            db.execute(
                "INSERT INTO user_companion_robots (user_id, companion_key, level, unlocked_at, updated_at) VALUES (?, ?, 1, ?, ?)",
                (self.user_id, "pending_submission_petbot", now, now),
            )
            self.assertFalse(game_app.equip_companion(db, self.user_id, "pending_submission_petbot")["ok"])

            db.execute("UPDATE lab_robot_submissions SET status = 'approved', approved_at = ? WHERE id = ?", (now, pending_id))
            approved = game_app.equip_companion(db, self.user_id, "pending_submission_petbot")
            self.assertTrue(approved["ok"])

    def test_factory_effects_do_not_touch_combat_or_coins(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_user_factory_facilities(db, self.user_id)
            game_app.ensure_companions(db, self.user_id)
            db.execute("UPDATE users SET factory_points = 0, coins = 777, active_companion_key = ? WHERE id = ?", ("collector_petbot", self.user_id))
            db.execute("UPDATE user_companion_robots SET level = 5 WHERE user_id = ? AND companion_key = ?", (self.user_id, "collector_petbot"))
            db.execute(
                "UPDATE user_factory_facilities SET last_claimed_at = ? WHERE user_id = ? AND facility_key = 'scrap_collector'",
                (int(time.time()) - 20 * 3600, self.user_id),
            )
            result = game_app.claim_factory_facility_points(db, self.user_id, "scrap_collector")
            self.assertTrue(result["ok"])
            user = db.execute("SELECT factory_points, coins FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(user["factory_points"]), 63)
            self.assertEqual(int(user["coins"]), 777)
            combat_stats = {"hp", "atk", "def", "spd", "acc", "cri"}
            self.assertTrue(all(item["effect_type"] not in combat_stats for item in game_app.COMPANION_DEFS))


if __name__ == "__main__":
    unittest.main()
