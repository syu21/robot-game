import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactionWeeklyEventTests(unittest.TestCase):
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
            self.admin_id = self._create_user(db, "event_admin", now, "aurix", is_admin=1)
            self.aurix_user = self._create_user(db, "event_aurix", now, "aurix")
            self.week_key = game_app.get_current_week_key()
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _create_user(self, db, username, now, faction, *, is_admin=0):
        db.execute(
            """
            INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer, faction)
            VALUES (?, ?, ?, ?, 0, 1, ?)
            """,
            (username, "x", now, int(is_admin), faction),
        )
        user_id = int(db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"])
        game_app.initialize_new_user(db, user_id)
        return user_id

    def _client(self, user_id=None, username="event_aurix"):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user_id or self.aurix_user)
            session["username"] = username
        return client

    def test_tables_lifecycle_and_world_logs_are_idempotent(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            event_cols = {row["name"] for row in db.execute("PRAGMA table_info(faction_weekly_events)").fetchall()}
            log_cols = {row["name"] for row in db.execute("PRAGMA table_info(faction_weekly_event_logs)").fetchall()}
            self.assertIn("event_key", event_cols)
            self.assertIn("payload_json", log_cols)

            with self.assertRaises(ValueError):
                game_app.set_faction_weekly_event(db, self.week_key, "missing_event", admin_user_id=self.admin_id)

            draft = game_app.set_faction_weekly_event(db, self.week_key, "facility_focus", admin_user_id=self.admin_id)
            self.assertEqual(draft["status"], "draft")
            self.assertIsNone(game_app.get_current_faction_weekly_event(db, self.week_key))

            active = game_app.activate_faction_weekly_event(db, self.week_key, admin_user_id=self.admin_id)
            active_again = game_app.activate_faction_weekly_event(db, self.week_key, admin_user_id=self.admin_id)
            self.assertEqual(active["status"], "active")
            self.assertTrue(active["emitted_world_event"])
            self.assertFalse(active_again["emitted_world_event"])

            finalized = game_app.finalize_faction_weekly_event(db, self.week_key, admin_user_id=self.admin_id)
            finalized_again = game_app.finalize_faction_weekly_event(db, self.week_key, admin_user_id=self.admin_id)
            self.assertEqual(finalized["status"], "finalized")
            self.assertTrue(finalized["emitted_world_event"])
            self.assertFalse(finalized_again["emitted_world_event"])

            started_count = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ?",
                (game_app.FACTION_WEEKLY_EVENT_STARTED_EVENT_TYPE,),
            ).fetchone()["c"]
            finalized_count = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ?",
                (game_app.FACTION_WEEKLY_EVENT_FINALIZED_EVENT_TYPE,),
            ).fetchone()["c"]
            self.assertEqual(started_count, 1)
            self.assertEqual(finalized_count, 1)

            cancelled = game_app.cancel_faction_weekly_event(db, self.week_key, admin_user_id=self.admin_id)
            self.assertEqual(cancelled["status"], "cancelled")
            self.assertIsNone(game_app.get_current_faction_weekly_event(db, self.week_key))

    def test_facility_and_guardian_material_bonus(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.set_faction_weekly_event(db, self.week_key, "facility_focus", admin_user_id=self.admin_id)
            game_app.activate_faction_weekly_event(db, self.week_key, admin_user_id=self.admin_id)
            explore = game_app.grant_faction_facility_material(
                db,
                "aurix",
                self.aurix_user,
                game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                101,
                1,
                week_key=self.week_key,
            )
            boss = game_app.grant_faction_facility_material(
                db,
                "aurix",
                self.aurix_user,
                game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                102,
                20,
                week_key=self.week_key,
            )
            self.assertEqual(explore["material_amount"], 2)
            self.assertEqual(boss["material_amount"], 25)

            game_app.set_faction_weekly_event(db, self.week_key, "guardian_focus", admin_user_id=self.admin_id)
            game_app.activate_faction_weekly_event(db, self.week_key, admin_user_id=self.admin_id)
            guardian = game_app.grant_faction_facility_material(
                db,
                "aurix",
                self.aurix_user,
                "faction_guardian_attack",
                103,
                10,
                week_key=self.week_key,
            )
            manual = game_app.grant_faction_facility_material(db, "aurix", self.aurix_user, "manual", 104, 10, week_key=self.week_key)
            self.assertEqual(guardian["material_amount"], 12)
            self.assertEqual(manual["material_amount"], 10)

    def test_territory_focus_score_bonus_and_stats_are_safe(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            before_robot = db.execute("SELECT * FROM robot_instances WHERE user_id = ? ORDER BY id LIMIT 1", (self.aurix_user,)).fetchone()
            before_user = db.execute("SELECT coins FROM users WHERE id = ?", (self.aurix_user,)).fetchone()["coins"]
            game_app.set_faction_weekly_event(db, self.week_key, "territory_focus", admin_user_id=self.admin_id)
            game_app.activate_faction_weekly_event(db, self.week_key, admin_user_id=self.admin_id)
            game_app.grant_faction_facility_material(db, "aurix", self.aurix_user, "test.weekly.territory", 201, 100, week_key=self.week_key)

            result = game_app.calculate_faction_territory_scores(db, self.week_key)
            rows = {(row["area_key"], row["faction_key"]): row for row in result["scores"]}
            self.assertEqual(rows[("central_observation", "aurix")]["facility_score"], 110)

            after_robot = db.execute("SELECT * FROM robot_instances WHERE user_id = ? ORDER BY id LIMIT 1", (self.aurix_user,)).fetchone()
            after_user = db.execute("SELECT coins FROM users WHERE id = ?", (self.aurix_user,)).fetchone()["coins"]
            self.assertEqual(dict(before_robot), dict(after_robot))
            self.assertEqual(before_user, after_user)

    def test_pages_and_admin_routes_show_weekly_event(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.set_faction_weekly_event(db, self.week_key, "representative_focus", admin_user_id=self.admin_id)
            game_app.activate_faction_weekly_event(db, self.week_key, admin_user_id=self.admin_id)
            db.commit()

        client = self._client()
        self.assertIn("今週の陣営イベント", client.get("/faction").get_data(as_text=True))
        self.assertIn("代表応援週間", client.get("/world").get_data(as_text=True))
        self.assertIn("今週の陣営イベント", client.get("/comms/faction").get_data(as_text=True))
        self.assertEqual(client.get("/admin/factions/events").status_code, 403)

        admin = self._client(self.admin_id, "event_admin")
        self.assertEqual(admin.get("/admin/factions/events").status_code, 200)
        self.assertEqual(admin.post("/admin/factions/events/set", data={"week_key": self.week_key, "event_key": "guardian_author_focus"}).status_code, 302)
        self.assertEqual(admin.post("/admin/factions/events/activate", data={"week_key": self.week_key}).status_code, 302)
        self.assertEqual(admin.post("/admin/factions/events/finalize", data={"week_key": self.week_key}).status_code, 302)
        self.assertEqual(admin.post("/admin/factions/events/cancel", data={"week_key": self.week_key}).status_code, 302)


if __name__ == "__main__":
    unittest.main()
