import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactionMissionsTests(unittest.TestCase):
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
            self.admin_id = self._create_user(db, "mission_admin", now, "aurix", is_admin=1)
            self.aurix_user = self._create_user(db, "mission_aurix", now, "aurix")
            self.ignis_user = self._create_user(db, "mission_ignis", now, "ignis")
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

    def _client(self, user_id=None, username="mission_aurix"):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user_id or self.aurix_user)
            session["username"] = username
        return client

    def _log_event(self, db, user_id, event_type, *, count=1, payload=None):
        now = int(time.time())
        for offset in range(count):
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (now + offset, event_type, json.dumps(payload or {}, ensure_ascii=False), int(user_id)),
            )

    def test_default_missions_are_idempotent(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            first = game_app.create_default_faction_weekly_missions(db)
            second = game_app.create_default_faction_weekly_missions(db)
            count = db.execute("SELECT COUNT(*) AS c FROM faction_weekly_missions").fetchone()["c"]
            self.assertEqual(first["created_count"], 3)
            self.assertEqual(second["created_count"], 0)
            self.assertEqual(count, 3)

    def test_progress_counts_explore_boss_and_evolve(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._log_event(db, self.aurix_user, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=4)
            self._log_event(db, self.aurix_user, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], count=2)
            self._log_event(db, self.aurix_user, game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"], count=3, payload={"success": True})
            result = game_app.recalculate_faction_mission_progress(db)
            missions = {row["mission_type"]: row for row in game_app.get_faction_weekly_missions(db)}
            self.assertEqual(result["updated_progress_count"], 9)
            self.assertEqual(missions["explore_count"]["progress_by_faction"][0]["current_value"], 4)
            self.assertEqual(missions["boss_defeat_count"]["progress_by_faction"][0]["current_value"], 2)
            self.assertEqual(missions["evolve_count"]["progress_by_faction"][0]["current_value"], 3)

    def test_completion_sets_completed_at(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.create_default_faction_weekly_missions(db)
            db.execute("UPDATE faction_weekly_missions SET target_value = 2 WHERE mission_type = 'explore_count'")
            self._log_event(db, self.aurix_user, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=2)
            game_app.recalculate_faction_mission_progress(db)
            row = db.execute(
                """
                SELECT p.*
                FROM faction_weekly_mission_progress p
                JOIN faction_weekly_missions m ON m.id = p.mission_id
                WHERE m.mission_type = 'explore_count' AND p.faction_key = 'aurix'
                """
            ).fetchone()
            self.assertEqual(row["is_completed"], 1)
            self.assertTrue(row["completed_at"])

    def test_faction_and_world_pages_show_missions(self):
        faction_html = self._client().get("/faction").get_data(as_text=True)
        world_html = self._client().get("/world").get_data(as_text=True)
        self.assertIn("今週の陣営ミッション", faction_html)
        self.assertIn("今週の共同出撃", faction_html)
        self.assertIn("陣営ミッション進捗", world_html)

    def test_finalize_emits_world_event_once(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.create_default_faction_weekly_missions(db)
            db.execute("UPDATE faction_weekly_missions SET target_value = 1 WHERE mission_type = 'explore_count'")
            self._log_event(db, self.aurix_user, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=1)
            first = game_app.finalize_faction_weekly_missions(db)
            second = game_app.finalize_faction_weekly_missions(db)
            count = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ?",
                (game_app.FACTION_MISSION_RESULT_EVENT_TYPE,),
            ).fetchone()["c"]
            self.assertTrue(first["emitted_world_event"])
            self.assertFalse(second["emitted_world_event"])
            self.assertEqual(count, 1)

    def test_admin_mission_routes_write_audit(self):
        client = self._client(self.admin_id, "mission_admin")
        self.assertEqual(client.post("/admin/factions/missions/create-default").status_code, 302)
        self.assertEqual(client.post("/admin/factions/missions/recalculate").status_code, 302)
        self.assertEqual(client.post("/admin/factions/missions/finalize").status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            rows = db.execute(
                """
                SELECT event_type
                FROM world_events_log
                WHERE event_type IN (?, ?, ?)
                """,
                (
                    game_app.AUDIT_EVENT_TYPES["FACTION_MISSIONS_CREATE_DEFAULT"],
                    game_app.AUDIT_EVENT_TYPES["FACTION_MISSIONS_RECALCULATE"],
                    game_app.AUDIT_EVENT_TYPES["FACTION_MISSIONS_FINALIZE"],
                ),
            ).fetchall()
            self.assertEqual({row["event_type"] for row in rows}, {
                game_app.AUDIT_EVENT_TYPES["FACTION_MISSIONS_CREATE_DEFAULT"],
                game_app.AUDIT_EVENT_TYPES["FACTION_MISSIONS_RECALCULATE"],
                game_app.AUDIT_EVENT_TYPES["FACTION_MISSIONS_FINALIZE"],
            })


if __name__ == "__main__":
    unittest.main()
