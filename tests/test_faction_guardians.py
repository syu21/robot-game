import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactionGuardianTests(unittest.TestCase):
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
            self.admin_id = self._create_user(db, "guardian_admin", now, "aurix", is_admin=1)
            self.aurix_user = self._create_user(db, "guardian_aurix", now, "aurix")
            self.ignis_user = self._create_user(db, "guardian_ignis", now, "ignis")
            self.ventra_user = self._create_user(db, "guardian_ventra", now, "ventra")
            self.aurix_submission = self._create_submission(db, self.aurix_user, "Aurix Guard", now)
            self.ignis_submission = self._create_submission(db, self.ignis_user, "Ignis Guard", now)
            self.ventra_submission = self._create_submission(db, self.ventra_user, "Ventra Guard", now)
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

    def _create_submission(self, db, user_id, title, now):
        cur = db.execute(
            """
            INSERT INTO lab_robot_submissions
            (user_id, title, comment, image_path, thumb_path, status, created_at, updated_at, approved_at, approved_by_user_id)
            VALUES (?, ?, 'comment', 'lab/submission.png', 'lab/submission_thumb.png', 'approved', ?, ?, ?, ?)
            """,
            (int(user_id), title, now, now, now, self.admin_id),
        )
        return int(cur.lastrowid)

    def _client(self, user_id=None, username="guardian_aurix"):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user_id or self.aurix_user)
            session["username"] = username
        return client

    def _log_event(self, db, user_id, event_type, *, payload=None):
        db.execute(
            """
            INSERT INTO world_events_log (created_at, event_type, payload_json, user_id, request_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                int(time.time()),
                event_type,
                json.dumps(payload or {}, ensure_ascii=False),
                int(user_id),
                f"req-{user_id}-{event_type}-{time.time_ns()}",
            ),
        )

    def test_guardian_tables_are_idempotent(self):
        init_db.main()
        with game_app.app.app_context():
            db = game_app.get_db()
            cols = {row["name"] for row in db.execute("PRAGMA table_info(faction_guardians)").fetchall()}
            self.assertIn("faith_profile_json", cols)
            self.assertIn("current_hp", cols)

    def test_manual_set_uses_approved_submission(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            row = game_app.set_faction_guardian_from_submission(db, game_app.get_current_week_key(), "aurix", self.aurix_submission)
            self.assertEqual(row["faction_key"], "aurix")
            self.assertEqual(row["submission_id"], self.aurix_submission)
            self.assertEqual(row["current_hp"], game_app.FACTION_GUARDIAN_MAX_HP)

    def test_auto_pick_creates_unset_when_no_submission(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE lab_robot_submissions SET status = 'disabled'")
            result = game_app.auto_pick_faction_guardian(db, game_app.get_current_week_key(), "aurix")
            row = game_app.get_faction_guardian_row(db, result["week_key"], "aurix")
            self.assertFalse(result["selected"])
            self.assertEqual(row["source_type"], "unset")

    def test_recalculate_applies_damage_once_per_rebuild(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            week_key = game_app.get_current_week_key()
            game_app.set_faction_guardian_from_submission(db, week_key, "ventra", self.ventra_submission)
            self._log_event(db, self.ignis_user, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], payload={"win": True})
            self._log_event(db, self.ignis_user, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"])
            self._log_event(db, self.ignis_user, game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"], payload={"success": True})
            first = game_app.recalculate_faction_guardian_attacks(db, week_key)
            second = game_app.recalculate_faction_guardian_attacks(db, week_key)
            row = game_app.get_faction_guardian_row(db, week_key, "ventra")
            self.assertEqual(first["total_damage"], 46)
            self.assertEqual(second["total_damage"], 46)
            self.assertEqual(row["current_hp"], game_app.FACTION_GUARDIAN_MAX_HP - 46)

    def test_failed_events_and_admin_events_are_ignored(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            week_key = game_app.get_current_week_key()
            game_app.set_faction_guardian_from_submission(db, week_key, "ventra", self.ventra_submission)
            self._log_event(db, self.ignis_user, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], payload={"win": False})
            self._log_event(db, self.admin_id, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"])
            result = game_app.recalculate_faction_guardian_attacks(db, week_key)
            row = game_app.get_faction_guardian_row(db, week_key, "ventra")
            self.assertEqual(result["total_damage"], 0)
            self.assertEqual(row["current_hp"], game_app.FACTION_GUARDIAN_MAX_HP)

    def test_finalize_emits_world_event_once(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            week_key = game_app.get_current_week_key()
            game_app.set_faction_guardian_from_submission(db, week_key, "ventra", self.ventra_submission)
            first = game_app.finalize_faction_guardians(db, week_key)
            second = game_app.finalize_faction_guardians(db, week_key)
            count = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ?",
                (game_app.FACTION_GUARDIAN_RESULT_EVENT_TYPE,),
            ).fetchone()["c"]
            self.assertTrue(first["emitted_world_event"])
            self.assertFalse(second["emitted_world_event"])
            self.assertEqual(count, 1)

    def test_pages_show_guardian_sections(self):
        client = self._client()
        faction_html = client.get("/faction").get_data(as_text=True)
        world_html = client.get("/world").get_data(as_text=True)
        self.assertIn("今週の陣営守護戦", faction_html)
        self.assertIn("陣営守護戦", world_html)

    def test_admin_guardian_routes_write_audit(self):
        client = self._client(self.admin_id, "guardian_admin")
        week_key = game_app.get_current_week_key()
        self.assertEqual(
            client.post(
                "/admin/factions/guardians/set",
                data={"week_key": week_key, "faction_key": "aurix", "submission_id": self.aurix_submission},
            ).status_code,
            302,
        )
        self.assertEqual(client.post("/admin/factions/guardians/recalculate", data={"week_key": week_key}).status_code, 302)
        self.assertEqual(client.post("/admin/factions/guardians/finalize", data={"week_key": week_key}).status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            rows = db.execute(
                """
                SELECT event_type
                FROM world_events_log
                WHERE event_type IN (?, ?, ?)
                """,
                (
                    game_app.AUDIT_EVENT_TYPES["FACTION_GUARDIAN_SET"],
                    game_app.AUDIT_EVENT_TYPES["FACTION_GUARDIAN_RECALCULATE"],
                    game_app.AUDIT_EVENT_TYPES["FACTION_GUARDIAN_FINALIZE"],
                ),
            ).fetchall()
            self.assertEqual(
                {row["event_type"] for row in rows},
                {
                    game_app.AUDIT_EVENT_TYPES["FACTION_GUARDIAN_SET"],
                    game_app.AUDIT_EVENT_TYPES["FACTION_GUARDIAN_RECALCULATE"],
                    game_app.AUDIT_EVENT_TYPES["FACTION_GUARDIAN_FINALIZE"],
                },
            )


if __name__ == "__main__":
    unittest.main()
