import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactionAwardsTests(unittest.TestCase):
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
            self.admin_id = self._create_user(db, "admin_awards", now, "aurix", is_admin=1)
            self.user_a = self._create_user(db, "aurix_a", now, "aurix")
            self.user_b = self._create_user(db, "aurix_b", now, "aurix")
            self.user_c = self._create_user(db, "aurix_c", now, "aurix")
            self.user_d = self._create_user(db, "aurix_d", now, "aurix")
            self.ignis_user = self._create_user(db, "ignis_awards", now, "ignis")
            self.no_faction_user = self._create_user(db, "no_faction_awards", now, None)
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

    def _client(self, user_id=None, username="aurix_a"):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user_id or self.user_a)
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

    def _award_rows(self, db, award_key, faction_key="aurix"):
        return db.execute(
            """
            SELECT user_id, score
            FROM faction_weekly_awards
            WHERE week_key = ? AND faction_key = ? AND award_key = ?
            ORDER BY user_id ASC
            """,
            (game_app.get_current_week_key(), faction_key, award_key),
        ).fetchall()

    def test_schema_is_idempotent(self):
        init_db.main()
        with game_app.app.app_context():
            db = game_app.get_db()
            cols = {row["name"] for row in db.execute("PRAGMA table_info(faction_weekly_awards)").fetchall()}
            self.assertIn("reward_status", cols)
            self.assertIn("award_key", cols)

    def test_explore_top_becomes_award(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._log_event(db, self.user_a, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=2)
            self._log_event(db, self.user_b, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=5)
            result = game_app.calculate_faction_weekly_awards(db)
            db.commit()

            rows = self._award_rows(db, "explore")
            self.assertGreater(result["created_or_updated_count"], 0)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["user_id"], self.user_b)
            self.assertEqual(rows[0]["score"], 5)

    def test_boss_top_becomes_award(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._log_event(db, self.user_a, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], count=1)
            self._log_event(db, self.user_b, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], count=2)
            game_app.calculate_faction_weekly_awards(db)
            db.commit()

            rows = self._award_rows(db, "boss")
            self.assertEqual(rows[0]["user_id"], self.user_b)
            self.assertEqual(rows[0]["score"], 2)

    def test_evolve_success_top_becomes_award(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._log_event(db, self.user_a, game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"], count=3, payload={"success": True})
            self._log_event(db, self.user_b, game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"], count=5, payload={"success": False})
            game_app.calculate_faction_weekly_awards(db)
            db.commit()

            rows = self._award_rows(db, "evolve")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["user_id"], self.user_a)
            self.assertEqual(rows[0]["score"], 3)

    def test_activity_top_becomes_award(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._log_event(db, self.user_a, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=12)
            self._log_event(db, self.user_b, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], count=1)
            game_app.calculate_faction_weekly_awards(db)
            db.commit()

            rows = self._award_rows(db, "activity")
            self.assertEqual(rows[0]["user_id"], self.user_b)
            self.assertEqual(rows[0]["score"], 20)

    def test_score_zero_categories_are_not_saved(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            result = game_app.calculate_faction_weekly_awards(db)
            db.commit()
            count = db.execute("SELECT COUNT(*) AS c FROM faction_weekly_awards").fetchone()["c"]
            self.assertEqual(result["created_or_updated_count"], 0)
            self.assertEqual(count, 0)

    def test_tied_first_place_is_limited_to_three_users(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            for user_id in (self.user_a, self.user_b, self.user_c, self.user_d):
                self._log_event(db, user_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=4)
            game_app.calculate_faction_weekly_awards(db)
            db.commit()

            rows = self._award_rows(db, "explore")
            self.assertEqual(len(rows), 3)
            self.assertEqual({row["score"] for row in rows}, {4})

    def test_unassigned_users_are_excluded(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._log_event(db, self.no_faction_user, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=9)
            self._log_event(db, self.user_a, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=1)
            game_app.calculate_faction_weekly_awards(db)
            db.commit()

            rows = self._award_rows(db, "explore")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["user_id"], self.user_a)

    def test_faction_page_shows_weekly_awards(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._log_event(db, self.user_a, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=2)
            game_app.calculate_faction_weekly_awards(db)
            db.commit()

        resp = self._client().get("/faction")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("今週の陣営内表彰", html)
        self.assertIn("今週の周回担当", html)
        self.assertIn("今週の突破担当", html)
        self.assertIn("今週はまだ該当者なし", html)
        self.assertIn("戦闘ステータスへの補正はありません", html)

    def test_admin_recalculate_route_writes_audit_log(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._log_event(db, self.user_a, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], count=1)
            db.commit()

        resp = self._client(self.admin_id, "admin_awards").post("/admin/factions/awards/recalculate")
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            audit_row = db.execute(
                """
                SELECT payload_json
                FROM world_events_log
                WHERE event_type = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (game_app.AUDIT_EVENT_TYPES["FACTION_AWARDS_RECALCULATE"],),
            ).fetchone()
            self.assertIsNotNone(audit_row)
            payload = json.loads(audit_row["payload_json"])
            self.assertEqual(payload["actor_admin_id"], self.admin_id)
            self.assertGreater(payload["created_or_updated_count"], 0)
