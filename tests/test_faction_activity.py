import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactionActivityTests(unittest.TestCase):
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
            self.aurix_user_id = self._create_user(db, "aurix_user", now, "aurix")
            self.aurix_peer_id = self._create_user(db, "aurix_peer", now, "aurix")
            self.ignis_user_id = self._create_user(db, "ignis_user", now, "ignis")
            self.no_faction_user_id = self._create_user(db, "no_faction_user", now, None)
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _create_user(self, db, username, now, faction):
        db.execute(
            """
            INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer, faction)
            VALUES (?, ?, ?, 0, 0, 1, ?)
            """,
            (username, "x", now, faction),
        )
        user_id = int(db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"])
        game_app.initialize_new_user(db, user_id)
        return user_id

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.aurix_user_id
            session["username"] = "aurix_user"
        return client

    def _log_event(self, db, user_id, event_type, *, count=1, payload=None):
        now = int(time.time())
        for offset in range(count):
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    now + offset,
                    event_type,
                    json.dumps(payload or {}, ensure_ascii=False),
                    user_id,
                ),
            )

    def test_weekly_faction_activity_counts_events_and_excludes_unassigned(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._log_event(db, self.aurix_user_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=3)
            self._log_event(db, self.aurix_user_id, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], count=2)
            self._log_event(db, self.aurix_user_id, game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"], payload={"success": True})
            self._log_event(db, self.no_faction_user_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=5)
            db.commit()

            rows = {row["faction_key"]: row for row in game_app.get_weekly_faction_activity(db)}
            self.assertEqual(rows["aurix"]["explore_count"], 3)
            self.assertEqual(rows["aurix"]["boss_defeat_count"], 2)
            self.assertEqual(rows["aurix"]["evolve_count"], 1)
            self.assertEqual(rows["aurix"]["activity_score"], 53)
            self.assertEqual(rows["ignis"]["explore_count"], 0)
            self.assertEqual(rows["ventra"]["explore_count"], 0)

    def test_weekly_faction_activity_marks_minority(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            rows = {row["faction_key"]: row for row in game_app.get_weekly_faction_activity(db)}
            self.assertFalse(rows["aurix"]["is_minority"])
            self.assertFalse(rows["ignis"]["is_minority"])
            self.assertTrue(rows["ventra"]["is_minority"])

    def test_weekly_faction_members_spotlight_orders_by_activity_score(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._log_event(db, self.aurix_user_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=3)
            self._log_event(db, self.aurix_peer_id, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], count=1)
            self._log_event(db, self.aurix_peer_id, game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"], count=1)
            db.commit()

            rows = game_app.get_weekly_faction_members_spotlight(db, "aurix", limit=5)
            self.assertEqual(rows[0]["user_id"], self.aurix_peer_id)
            self.assertEqual(rows[0]["activity_score"], 30)
            self.assertIn(rows[0]["spotlight_label"], {"今週の突破役", "今週の研究主力"})
            self.assertEqual(rows[1]["user_id"], self.aurix_user_id)

    def test_faction_page_shows_activity_and_spotlight(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._log_event(db, self.aurix_user_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=2)
            self._log_event(db, self.aurix_user_id, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], count=1)
            db.commit()

        resp = self._client().get("/faction")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("今週の陣営活動", html)
        self.assertIn("所属人数", html)
        self.assertIn("活動スコア", html)
        self.assertIn("所属陣営の注目研究員", html)
        self.assertIn("今週の突破役", html)

    def test_world_page_shows_weekly_faction_report(self):
        resp = self._client().get("/world")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("今週の陣営レポート", html)
        self.assertIn("オリクス", html)
        self.assertIn("イグニス", html)
        self.assertIn("ヴェントラ", html)
        self.assertIn("活動スコア", html)
