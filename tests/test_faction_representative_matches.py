import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactionRepresentativeMatchTests(unittest.TestCase):
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
            self.admin_id = self._create_user(db, "rep_admin", now, "aurix", is_admin=1)
            self.aurix_top = self._create_user(db, "rep_aurix_top", now, "aurix")
            self.aurix_active = self._create_user(db, "rep_aurix_active", now, "aurix")
            self.ignis_user = self._create_user(db, "rep_ignis", now, "ignis")
            self.ventra_user = self._create_user(db, "rep_ventra", now, "ventra")
            self.week_key = game_app.get_current_week_key()
            self._force_robot_assets(db)
            self.guardian_ids = {}
            for faction_key in ("aurix", "ignis", "ventra"):
                cur = db.execute(
                    """
                    INSERT INTO faction_guardians
                    (week_key, faction_key, guardian_name, guardian_title, source_type, max_hp, current_hp, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'manual', 1000, 1000, ?, ?)
                    """,
                    (self.week_key, faction_key, f"{faction_key} guard", f"{faction_key} guard", game_app.now_str(), game_app.now_str()),
                )
                self.guardian_ids[faction_key] = int(cur.lastrowid)
            self._insert_guardian_attack(db, self.aurix_top, "aurix", 12)
            self._insert_guardian_attack(db, self.aurix_active, "aurix", 5)
            self._insert_guardian_attack(db, self.ignis_user, "ignis", 7)
            self._insert_guardian_attack(db, self.ventra_user, "ventra", 6)
            self._log_activity(db, self.aurix_active, count=3)
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

    def _force_robot_assets(self, db):
        rows = db.execute("SELECT id, active_robot_id FROM users").fetchall()
        for row in rows:
            if row["active_robot_id"]:
                db.execute(
                    "UPDATE robot_instances SET composed_image_path = ?, icon_32_path = ?, updated_at = ? WHERE id = ?",
                    (f"robot_composed/test_{row['id']}.png", f"robot_icons/test_{row['id']}.png", int(time.time()), int(row["active_robot_id"])),
                )

    def _insert_guardian_attack(self, db, user_id, faction_key, damage):
        db.execute(
            """
            INSERT INTO faction_guardian_attacks
            (week_key, attacker_faction_key, target_faction_key, guardian_id, attacker_user_id,
             source_event_type, source_event_id, request_id, damage, created_at)
            VALUES (?, ?, 'ignis', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.week_key,
                faction_key,
                self.guardian_ids["ignis"],
                int(user_id),
                game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                int(user_id) * 100,
                f"rep-{user_id}",
                int(damage),
                game_app.now_str(),
            ),
        )

    def _log_activity(self, db, user_id, count=1):
        for idx in range(count):
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id, request_id)
                VALUES (?, ?, '{}', ?, ?)
                """,
                (int(time.time()), game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], int(user_id), f"activity-{user_id}-{idx}"),
            )

    def _client(self, user_id=None, username="rep_aurix_top"):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user_id or self.aurix_top)
            session["username"] = username
        return client

    def test_auto_pick_uses_contribution_then_activity(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            rep_cols = {row["name"] for row in db.execute("PRAGMA table_info(faction_representatives)").fetchall()}
            match_cols = {row["name"] for row in db.execute("PRAGMA table_info(faction_representative_matches)").fetchall()}
            self.assertIn("selection_reason", rep_cols)
            self.assertIn("battle_log_json", match_cols)
            result = game_app.auto_pick_faction_representatives(db, self.week_key, faction_key="aurix")
            self.assertEqual(result["selected_count"], 1)
            rep = game_app.get_faction_representative_row(db, self.week_key, "aurix")
            self.assertEqual(rep["user_id"], self.aurix_top)
            self.assertEqual(rep["selection_reason"], "guardian_contribution_top")

            db.execute("DELETE FROM faction_guardian_attacks WHERE attacker_faction_key = 'aurix'")
            skipped = game_app.auto_pick_faction_representatives(db, self.week_key, faction_key="aurix")
            self.assertEqual(skipped["selected_count"], 0)
            rep = game_app.get_faction_representative_row(db, self.week_key, "aurix")
            self.assertEqual(rep["user_id"], self.aurix_top)
            game_app.auto_pick_faction_representatives(db, self.week_key, faction_key="aurix", overwrite=True)
            rep = game_app.get_faction_representative_row(db, self.week_key, "aurix")
            self.assertEqual(rep["user_id"], self.aurix_active)
            self.assertEqual(rep["selection_reason"], "activity_score_top")

    def test_manual_set_validates_faction_and_robot_owner(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            aurix_robot = db.execute("SELECT active_robot_id FROM users WHERE id = ?", (self.aurix_top,)).fetchone()["active_robot_id"]
            row = game_app.set_faction_representative(db, self.week_key, "aurix", self.aurix_top, aurix_robot)
            self.assertEqual(row["user_id"], self.aurix_top)
            with self.assertRaises(ValueError):
                game_app.set_faction_representative(db, self.week_key, "aurix", self.ignis_user, None)
            ignis_robot = db.execute("SELECT active_robot_id FROM users WHERE id = ?", (self.ignis_user,)).fetchone()["active_robot_id"]
            with self.assertRaises(ValueError):
                game_app.set_faction_representative(db, self.week_key, "aurix", self.aurix_top, ignis_robot)

    def test_generate_and_run_matches_are_idempotent(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.auto_pick_faction_representatives(db, self.week_key)
            first = game_app.generate_faction_representative_matches(db, self.week_key)
            second = game_app.generate_faction_representative_matches(db, self.week_key)
            self.assertEqual(first["created_count"], 3)
            self.assertEqual(second["created_count"], 0)
            run_first = game_app.run_faction_representative_matches(db, self.week_key)
            run_second = game_app.run_faction_representative_matches(db, self.week_key)
            self.assertEqual(run_first["run_count"], 3)
            self.assertEqual(run_second["run_count"], 0)
            rows = db.execute("SELECT * FROM faction_representative_matches WHERE week_key = ?", (self.week_key,)).fetchall()
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(row["result_status"] in ("completed", "skipped") for row in rows))
            self.assertTrue(any(row["winner_faction_key"] for row in rows))
            self.assertTrue(any(json.loads(row["battle_log_json"] or "[]") for row in rows))
            before_stats = db.execute("SELECT style_stats_json FROM robot_instances WHERE user_id = ?", (self.aurix_top,)).fetchone()["style_stats_json"]
            game_app.run_faction_representative_matches(db, self.week_key)
            after_stats = db.execute("SELECT style_stats_json FROM robot_instances WHERE user_id = ?", (self.aurix_top,)).fetchone()["style_stats_json"]
            self.assertEqual(before_stats, after_stats)
            event_count = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ?",
                (game_app.FACTION_REPRESENTATIVE_MATCH_RESULT_EVENT_TYPE,),
            ).fetchone()["c"]
            self.assertEqual(event_count, 1)

    def test_pages_and_admin_permissions(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.auto_pick_faction_representatives(db, self.week_key)
            game_app.run_faction_representative_matches(db, self.week_key)
            db.commit()
        client = self._client()
        self.assertIn("今週の陣営代表戦", client.get("/faction").get_data(as_text=True))
        self.assertIn("今週の陣営代表戦", client.get("/world").get_data(as_text=True))
        self.assertIn("今週の陣営代表戦", client.get("/comms/faction").get_data(as_text=True))
        self.assertEqual(client.get("/admin/factions/representatives").status_code, 403)
        admin = self._client(self.admin_id, "rep_admin")
        self.assertEqual(admin.get("/admin/factions/representatives").status_code, 200)
        self.assertEqual(admin.post("/admin/factions/representatives/auto-pick", data={"week_key": self.week_key}).status_code, 302)
        self.assertEqual(admin.post("/admin/factions/representatives/generate-matches", data={"week_key": self.week_key}).status_code, 302)
        self.assertEqual(admin.post("/admin/factions/representatives/run-matches", data={"week_key": self.week_key}).status_code, 302)


if __name__ == "__main__":
    unittest.main()
