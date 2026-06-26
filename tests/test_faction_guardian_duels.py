import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactionGuardianDuelTests(unittest.TestCase):
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
            self.admin_id = self._create_user(db, "duel_admin", now, "aurix", is_admin=1)
            self.aurix_user = self._create_user(db, "duel_aurix", now, "aurix")
            self.ignis_user = self._create_user(db, "duel_ignis", now, "ignis")
            self.ventra_user = self._create_user(db, "duel_ventra", now, "ventra")
            self.week_key = game_app.get_current_week_key()
            self.submissions = {
                "aurix": self._create_submission(db, self.aurix_user, "Aurix Duel Guard", now),
                "ignis": self._create_submission(db, self.ignis_user, "Ignis Duel Guard", now),
                "ventra": self._create_submission(db, self.ventra_user, "Ventra Duel Guard", now),
            }
            for faction_key, submission_id in self.submissions.items():
                game_app.set_faction_guardian_from_submission(db, self.week_key, faction_key, submission_id)
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
            VALUES (?, ?, 'comment', ?, ?, 'approved', ?, ?, ?, ?)
            """,
            (int(user_id), title, f"lab/{title}.png", f"lab/{title}_thumb.png", now, now, now, self.admin_id),
        )
        return int(cur.lastrowid)

    def _client(self, user_id=None, username="duel_aurix"):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user_id or self.aurix_user)
            session["username"] = username
        return client

    def test_generate_guardian_duels_is_idempotent(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            cols = {row["name"] for row in db.execute("PRAGMA table_info(faction_guardian_duels)").fetchall()}
            self.assertIn("battle_log_json", cols)
            first = game_app.generate_faction_guardian_duels(db, self.week_key)
            second = game_app.generate_faction_guardian_duels(db, self.week_key)
            self.assertEqual(first["created_count"], 3)
            self.assertEqual(second["created_count"], 0)
            count = db.execute("SELECT COUNT(*) AS c FROM faction_guardian_duels WHERE week_key = ?", (self.week_key,)).fetchone()["c"]
            self.assertEqual(count, 3)

    def test_unset_guardian_is_skipped(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app._set_unset_faction_guardian(db, self.week_key, "ignis")
            game_app.generate_faction_guardian_duels(db, self.week_key)
            result = game_app.run_faction_guardian_duels(db, self.week_key)
            self.assertGreaterEqual(result["skipped_count"], 1)
            skipped = db.execute("SELECT COUNT(*) AS c FROM faction_guardian_duels WHERE result_status = 'skipped'").fetchone()["c"]
            self.assertGreaterEqual(skipped, 1)

    def test_stats_use_faith_and_strategy_bonus_only(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            guardian = game_app.get_faction_guardians_view(db, self.week_key)[0]
            base = game_app.build_guardian_duel_stats(db, guardian, self.week_key)
            self.assertGreaterEqual(base["hp"], 10)
            self.assertEqual(base["atk"], 50 + int(guardian["faith_profile"]["stats"]["atk"]) * 10)
            now = game_app.now_str()
            db.execute(
                """
                INSERT INTO faction_weekly_strategies
                (week_key, faction_key, strategy_key, vote_count, is_finalized, finalized_at, created_at, updated_at)
                VALUES (?, ?, 'focus_analysis', 1, 1, ?, ?, ?)
                """,
                (self.week_key, guardian["faction_key"], now, now, now),
            )
            boosted = game_app.build_guardian_duel_stats(db, guardian, self.week_key)
            self.assertEqual(boosted["atk"], int(base["atk"] * 1.03))

    def test_run_guardian_duels_is_idempotent_and_preserves_submission(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            before = db.execute("SELECT image_path, thumb_path FROM lab_robot_submissions WHERE id = ?", (self.submissions["aurix"],)).fetchone()
            game_app.generate_faction_guardian_duels(db, self.week_key)
            first = game_app.run_faction_guardian_duels(db, self.week_key)
            second = game_app.run_faction_guardian_duels(db, self.week_key)
            self.assertEqual(first["run_count"], 3)
            self.assertEqual(second["run_count"], 0)
            rows = db.execute("SELECT * FROM faction_guardian_duels WHERE week_key = ?", (self.week_key,)).fetchall()
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(row["result_status"] in ("completed", "skipped") for row in rows))
            self.assertTrue(any(row["winner_faction_key"] for row in rows))
            self.assertTrue(any(json.loads(row["battle_log_json"] or "[]") for row in rows))
            event_count = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ?",
                (game_app.FACTION_GUARDIAN_DUEL_RESULT_EVENT_TYPE,),
            ).fetchone()["c"]
            self.assertEqual(event_count, 1)
            after = db.execute("SELECT image_path, thumb_path FROM lab_robot_submissions WHERE id = ?", (self.submissions["aurix"],)).fetchone()
            self.assertEqual(dict(before), dict(after))

    def test_pages_and_admin_permissions(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.run_faction_guardian_duels(db, self.week_key)
            db.commit()
        client = self._client()
        self.assertIn("今週の守護機演習", client.get("/faction").get_data(as_text=True))
        self.assertIn("今週の守護機演習", client.get("/world").get_data(as_text=True))
        self.assertIn("今週の守護機演習", client.get("/comms/faction").get_data(as_text=True))
        self.assertEqual(client.get("/admin/factions/guardian-duels").status_code, 403)
        admin = self._client(self.admin_id, "duel_admin")
        self.assertEqual(admin.get("/admin/factions/guardian-duels").status_code, 200)
        self.assertEqual(admin.post("/admin/factions/guardian-duels/generate", data={"week_key": self.week_key}).status_code, 302)
        self.assertEqual(admin.post("/admin/factions/guardian-duels/run", data={"week_key": self.week_key}).status_code, 302)


if __name__ == "__main__":
    unittest.main()
