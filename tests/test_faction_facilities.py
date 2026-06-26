import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactionFacilityTests(unittest.TestCase):
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
            self.admin_id = self._create_user(db, "facility_admin", now, "aurix", is_admin=1)
            self.aurix_user = self._create_user(db, "facility_aurix", now, "aurix")
            self.ignis_user = self._create_user(db, "facility_ignis", now, "ignis")
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

    def _client(self, user_id=None, username="facility_aurix"):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user_id or self.aurix_user)
            session["username"] = username
        return client

    def _log_event(self, db, user_id, event_type, *, payload=None, created_at=None):
        cur = db.execute(
            """
            INSERT INTO world_events_log (created_at, event_type, payload_json, user_id, request_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                int(created_at or time.time()),
                event_type,
                json.dumps(payload or {}, ensure_ascii=False),
                int(user_id),
                f"facility-{user_id}-{event_type}-{time.time_ns()}",
            ),
        )
        return int(cur.lastrowid)

    def test_ensure_facilities_is_idempotent(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            cols = {row["name"] for row in db.execute("PRAGMA table_info(faction_facilities)").fetchall()}
            self.assertIn("visual_tier", cols)
            first = game_app.ensure_faction_facilities(db)
            second = game_app.ensure_faction_facilities(db)
            self.assertEqual(first["created_count"], 3)
            self.assertEqual(second["created_count"], 0)
            rows = game_app.get_faction_facilities_view(db, self.week_key)
            self.assertEqual(len(rows), 3)
            self.assertEqual({row["level"] for row in rows}, {1})

    def test_grant_material_levels_up_and_deduplicates_source(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            first = game_app.grant_faction_facility_material(
                db, "aurix", self.aurix_user, "test.facility", 101, 120, week_key=self.week_key
            )
            second = game_app.grant_faction_facility_material(
                db, "aurix", self.aurix_user, "test.facility", 101, 120, week_key=self.week_key
            )
            row = db.execute("SELECT * FROM faction_facilities WHERE faction_key = 'aurix'").fetchone()
            self.assertTrue(first["granted"])
            self.assertTrue(second["skipped_duplicate"])
            self.assertEqual(row["level"], 2)
            self.assertEqual(row["current_exp"], 20)
            logs = db.execute("SELECT COUNT(*) AS c FROM faction_facility_level_logs WHERE faction_key = 'aurix'").fetchone()["c"]
            self.assertEqual(logs, 1)
            world_logs = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ?",
                (game_app.FACTION_FACILITY_LEVEL_UP_EVENT_TYPE,),
            ).fetchone()["c"]
            self.assertEqual(world_logs, 1)

    def test_sync_materials_from_world_events_and_guardian_damage(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._log_event(db, self.aurix_user, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"])
            self._log_event(db, self.aurix_user, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"])
            self._log_event(db, self.aurix_user, game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"], payload={"success": True})
            self._log_event(db, self.aurix_user, game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"], payload={"success": False})
            db.execute(
                """
                INSERT INTO faction_guardian_attacks
                (week_key, attacker_faction_key, target_faction_key, guardian_id, attacker_user_id,
                 source_event_type, source_event_id, request_id, damage, created_at)
                VALUES (?, 'aurix', 'ignis', 1, ?, 'test.attack', 1, 'facility-attack', 50, ?)
                """,
                (self.week_key, self.aurix_user, game_app.now_str()),
            )
            result = game_app.sync_faction_facility_materials(db, self.week_key)
            self.assertEqual(result["material_total"], 41)
            self.assertEqual(game_app.sync_faction_facility_materials(db, self.week_key)["material_total"], 0)
            facility = db.execute("SELECT total_exp FROM faction_facilities WHERE faction_key = 'aurix'").fetchone()
            self.assertEqual(facility["total_exp"], 41)
            self.assertEqual(game_app.get_user_faction_facility_weekly_contribution(db, self.aurix_user, self.week_key), 41)

    def test_pages_and_admin_routes_show_facilities(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.grant_faction_facility_material(db, "aurix", self.aurix_user, "test.page", 201, 12, week_key=self.week_key)
            db.commit()
        client = self._client()
        self.assertIn("陣営施設", client.get("/faction").get_data(as_text=True))
        self.assertIn("陣営施設状況", client.get("/world").get_data(as_text=True))
        self.assertIn("陣営施設", client.get("/comms/faction").get_data(as_text=True))
        self.assertEqual(client.get("/admin/factions/facilities").status_code, 403)
        admin = self._client(self.admin_id, "facility_admin")
        self.assertEqual(admin.get("/admin/factions/facilities").status_code, 200)
        self.assertEqual(admin.post("/admin/factions/facilities/ensure", data={"week_key": self.week_key}).status_code, 302)
        self.assertEqual(admin.post("/admin/factions/facilities/recalculate", data={"week_key": self.week_key}).status_code, 302)
        self.assertEqual(
            admin.post(
                "/admin/factions/facilities/grant",
                data={"week_key": self.week_key, "faction_key": "aurix", "material_amount": "30"},
            ).status_code,
            302,
        )

    def test_facility_material_does_not_change_robot_stats(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            before = db.execute(
                "SELECT * FROM robot_instances WHERE user_id = ? ORDER BY id LIMIT 1",
                (self.aurix_user,),
            ).fetchone()
            game_app.grant_faction_facility_material(db, "aurix", self.aurix_user, "test.no_stats", 301, 300, week_key=self.week_key)
            after = db.execute(
                "SELECT * FROM robot_instances WHERE user_id = ? ORDER BY id LIMIT 1",
                (self.aurix_user,),
            ).fetchone()
            self.assertEqual(dict(before), dict(after))


if __name__ == "__main__":
    unittest.main()
