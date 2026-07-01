import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class CompanionDispatchTests(unittest.TestCase):
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
                ("dispatch_user", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("dispatch_user",)).fetchone()["id"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "dispatch_user"
        return client

    def test_initial_access_seeds_dispatch_courses_and_handles_no_active_companion(self):
        html = self._client().get("/companion/dispatch").get_data(as_text=True)
        self.assertIn("相棒ロボ派遣", html)
        self.assertIn("派遣できる相棒ロボがいません", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            count = int(db.execute("SELECT COUNT(*) AS c FROM companion_dispatch_masters").fetchone()["c"])
            self.assertEqual(count, 3)

    def test_start_dispatch_and_prevent_second_start(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_companions(db, self.user_id)
            result = game_app.start_companion_dispatch(db, self.user_id, "short_patrol", request_id="dispatch-start")
            self.assertTrue(result["ok"])
            row = db.execute("SELECT * FROM user_companion_dispatches WHERE user_id = ?", (self.user_id,)).fetchone()
            self.assertEqual(row["status"], "active")
            self.assertEqual(row["companion_key"], "collector_petbot")
            self.assertGreaterEqual(int(row["reward_factory_points"]), 20)
            self.assertLessEqual(int(row["reward_factory_points"]), 40)
            second = game_app.start_companion_dispatch(db, self.user_id, "scrap_search")
            self.assertFalse(second["ok"])
            event = db.execute(
                "SELECT id FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["COMPANION_DISPATCH_START"]),
            ).fetchone()
            self.assertIsNotNone(event)

    def test_claim_requires_completion_then_adds_factory_points_once(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_companions(db, self.user_id)
            start = game_app.start_companion_dispatch(db, self.user_id, "short_patrol")
            self.assertTrue(start["ok"])
            early = game_app.claim_companion_dispatch(db, self.user_id)
            self.assertFalse(early["ok"])
            self.assertIn("まだ派遣中", early["reason"])

            dispatch = db.execute("SELECT id, reward_factory_points FROM user_companion_dispatches WHERE user_id = ?", (self.user_id,)).fetchone()
            reward = int(dispatch["reward_factory_points"])
            db.execute(
                "UPDATE user_companion_dispatches SET completes_at = ? WHERE id = ?",
                (int(time.time()) - 1, int(dispatch["id"])),
            )
            claim = game_app.claim_companion_dispatch(db, self.user_id, request_id="dispatch-claim")
            self.assertTrue(claim["ok"])
            self.assertEqual(claim["reward_factory_points"], reward)
            user = db.execute("SELECT factory_points FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(user["factory_points"]), reward)
            row = db.execute("SELECT status FROM user_companion_dispatches WHERE id = ?", (int(dispatch["id"]),)).fetchone()
            self.assertEqual(row["status"], "claimed")
            second_claim = game_app.claim_companion_dispatch(db, self.user_id)
            self.assertFalse(second_claim["ok"])
            for event_type in (game_app.AUDIT_EVENT_TYPES["COMPANION_DISPATCH_CLAIM"], game_app.AUDIT_EVENT_TYPES["FACTORY_POINTS_DELTA"]):
                event = db.execute(
                    "SELECT id FROM world_events_log WHERE user_id = ? AND event_type = ?",
                    (self.user_id, event_type),
                ).fetchone()
                self.assertIsNotNone(event)

    def test_dispatch_blocks_equip_and_upgrade_for_dispatched_companion(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_companions(db, self.user_id)
            db.execute("UPDATE users SET factory_points = 1000 WHERE id = ?", (self.user_id,))
            start = game_app.start_companion_dispatch(db, self.user_id, "short_patrol")
            self.assertTrue(start["ok"])
            equip = game_app.equip_companion(db, self.user_id, "maintenance_petbot")
            self.assertFalse(equip["ok"])
            upgrade = game_app.upgrade_companion(db, self.user_id, "collector_petbot")
            self.assertFalse(upgrade["ok"])

    def test_dispatch_event_is_fixed_at_start_and_claim_updates_album_stats(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_companions(db, self.user_id)
            start = game_app.start_companion_dispatch(
                db,
                self.user_id,
                "short_patrol",
                event_type_override="great_success",
                journal_key_override="old_hangar",
            )
            self.assertTrue(start["ok"])
            dispatch = db.execute(
                "SELECT * FROM user_companion_dispatches WHERE id = ?",
                (int(start["dispatch_id"]),),
            ).fetchone()
            base_reward = int(dispatch["base_reward_factory_points"])
            self.assertEqual(dispatch["event_type"], "great_success")
            self.assertEqual(int(dispatch["event_bonus_points"]), base_reward)
            self.assertEqual(dispatch["journal_key"], "old_hangar")

            db.execute(
                "UPDATE user_companion_dispatches SET completes_at = ? WHERE id = ?",
                (int(time.time()) - 1, int(start["dispatch_id"])),
            )
            claim = game_app.claim_companion_dispatch(db, self.user_id, request_id="dispatch-event")
            self.assertTrue(claim["ok"])
            self.assertEqual(claim["event_type"], "great_success")
            self.assertEqual(claim["event_bonus_points"], base_reward)
            self.assertEqual(claim["reward_factory_points"], base_reward * 2)
            self.assertIn("古い格納庫", claim["journal_text"])

            user = db.execute("SELECT factory_points FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(user["factory_points"]), base_reward * 2)
            companion = db.execute(
                """
                SELECT experience, dispatch_count, factory_points_collected
                FROM user_companion_robots
                WHERE user_id = ? AND companion_key = 'collector_petbot'
                """,
                (self.user_id,),
            ).fetchone()
            self.assertEqual(int(companion["experience"]), 1)
            self.assertEqual(int(companion["dispatch_count"]), 1)
            self.assertEqual(int(companion["factory_points_collected"]), base_reward * 2)

            event = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["COMPANION_DISPATCH_EVENT"]),
            ).fetchone()
            self.assertIsNotNone(event)

    def test_dispatch_claim_page_shows_result_event_and_journal(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_companions(db, self.user_id)
            start = game_app.start_companion_dispatch(
                db,
                self.user_id,
                "short_patrol",
                event_type_override="scrap_found",
                journal_key_override="parts_yard",
            )
            db.execute(
                "UPDATE user_companion_dispatches SET completes_at = ? WHERE id = ?",
                (int(time.time()) - 1, int(start["dispatch_id"])),
            )
            db.commit()
        html = self._client().post("/companion/dispatch/claim", follow_redirects=True).get_data(as_text=True)
        self.assertIn("相棒ロボ帰還", html)
        self.assertIn("スクラップ発見", html)
        self.assertIn("部品置き場を巡回しました", html)


if __name__ == "__main__":
    unittest.main()
