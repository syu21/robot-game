import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactoryTests(unittest.TestCase):
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
                ("factory_user", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("factory_user",)).fetchone()["id"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "factory_user"
        return client

    def test_initial_access_creates_three_facilities(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            result = game_app.ensure_user_factory_facilities(db, self.user_id, request_id="factory-ensure")
            db.commit()
            self.assertEqual(result["created_count"], 3)
            count = int(db.execute("SELECT COUNT(*) AS c FROM user_factory_facilities WHERE user_id = ?", (self.user_id,)).fetchone()["c"])
            self.assertEqual(count, 3)
            event = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["FACTORY_ENSURE_DEFAULTS"]),
            ).fetchone()
            self.assertIsNotNone(event)
        html = self._client().get("/factory").get_data(as_text=True)
        self.assertIn("ロボ工場", html)
        self.assertIn("スクラップ回収機", html)
        self.assertIn("エネルギー炉", html)
        self.assertIn("研究端末", html)

    def test_pending_points_and_twelve_hour_cap(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_user_factory_facilities(db, self.user_id)
            now = int(time.time())
            db.execute(
                "UPDATE user_factory_facilities SET last_claimed_at = ? WHERE user_id = ? AND facility_key = 'scrap_collector'",
                (now - 3 * 3600, self.user_id),
            )
            row = db.execute("SELECT * FROM user_factory_facilities WHERE user_id = ? AND facility_key = 'scrap_collector'", (self.user_id,)).fetchone()
            self.assertEqual(game_app._factory_pending_points(row, now), 15)
            db.execute(
                "UPDATE user_factory_facilities SET last_claimed_at = ? WHERE user_id = ? AND facility_key = 'scrap_collector'",
                (now - 20 * 3600, self.user_id),
            )
            row = db.execute("SELECT * FROM user_factory_facilities WHERE user_id = ? AND facility_key = 'scrap_collector'", (self.user_id,)).fetchone()
            self.assertEqual(game_app._factory_pending_points(row, now), 60)

    def test_claim_adds_factory_points_and_updates_timestamp_and_audit(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_user_factory_facilities(db, self.user_id)
            db.execute("UPDATE users SET factory_points = 10 WHERE id = ?", (self.user_id,))
            db.execute(
                "UPDATE user_factory_facilities SET last_claimed_at = ? WHERE user_id = ? AND facility_key = 'scrap_collector'",
                (int(time.time()) - 2 * 3600, self.user_id),
            )
            before = int(db.execute("SELECT last_claimed_at FROM user_factory_facilities WHERE user_id = ? AND facility_key = 'scrap_collector'", (self.user_id,)).fetchone()["last_claimed_at"])
            result = game_app.claim_factory_facility_points(db, self.user_id, "scrap_collector", request_id="factory-claim")
            self.assertTrue(result["ok"])
            user = db.execute("SELECT factory_points FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(user["factory_points"]), 20)
            after = int(db.execute("SELECT last_claimed_at FROM user_factory_facilities WHERE user_id = ? AND facility_key = 'scrap_collector'", (self.user_id,)).fetchone()["last_claimed_at"])
            self.assertGreaterEqual(after, before)
            event = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ? ORDER BY id DESC LIMIT 1",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["FACTORY_CLAIM"]),
            ).fetchone()
            self.assertIsNotNone(event)
            payload = json.loads(event["payload_json"] or "{}")
            self.assertEqual(payload["points_gained"], 10)
            self.assertEqual(payload["factory_points_before"], 10)
            self.assertEqual(payload["factory_points_after"], 20)
            second = game_app.claim_factory_facility_points(db, self.user_id, "scrap_collector", request_id="factory-claim-2")
            self.assertFalse(second["ok"])

    def test_upgrade_spends_coins_levels_up_and_audits(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_user_factory_facilities(db, self.user_id)
            db.execute("UPDATE users SET coins = 1000 WHERE id = ?", (self.user_id,))
            result = game_app.upgrade_factory_facility(db, self.user_id, "energy_reactor", request_id="factory-upgrade")
            self.assertTrue(result["ok"])
            row = db.execute("SELECT level FROM user_factory_facilities WHERE user_id = ? AND facility_key = 'energy_reactor'", (self.user_id,)).fetchone()
            user = db.execute("SELECT coins FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(row["level"]), 2)
            self.assertEqual(int(user["coins"]), 500)
            for event_type in (game_app.AUDIT_EVENT_TYPES["FACTORY_UPGRADE"], game_app.AUDIT_EVENT_TYPES["COIN_DELTA"]):
                self.assertIsNotNone(
                    db.execute(
                        "SELECT id FROM world_events_log WHERE user_id = ? AND event_type = ?",
                        (self.user_id, event_type),
                    ).fetchone()
                )

    def test_upgrade_rejects_insufficient_coins_and_max_level(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_user_factory_facilities(db, self.user_id)
            db.execute("UPDATE users SET coins = 499 WHERE id = ?", (self.user_id,))
            poor = game_app.upgrade_factory_facility(db, self.user_id, "research_terminal")
            self.assertFalse(poor["ok"])
            row = db.execute("SELECT level FROM user_factory_facilities WHERE user_id = ? AND facility_key = 'research_terminal'", (self.user_id,)).fetchone()
            self.assertEqual(int(row["level"]), 1)
            db.execute("UPDATE user_factory_facilities SET level = 5 WHERE user_id = ? AND facility_key = 'research_terminal'", (self.user_id,))
            maxed = game_app.upgrade_factory_facility(db, self.user_id, "research_terminal")
            self.assertFalse(maxed["ok"])
            self.assertIn("最大Lv", maxed["reason"])

    def test_home_links_factory(self):
        html = self._client().get("/home").get_data(as_text=True)
        self.assertIn("ロボ工場", html)
        self.assertIn("/factory", html)


if __name__ == "__main__":
    unittest.main()
