import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactionWeeklyReportTests(unittest.TestCase):
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
            self.admin_id = self._create_user(db, "admin_report", now, "aurix", is_admin=1)
            self.aurix_user = self._create_user(db, "aurix_report", now, "aurix")
            self.aurix_peer = self._create_user(db, "aurix_peer_report", now, "aurix")
            self.ignis_user = self._create_user(db, "ignis_report", now, "ignis")
            self.ventra_user = self._create_user(db, "ventra_report", now, "ventra")
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

    def _client(self, user_id=None, username="aurix_report"):
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
                INSERT INTO world_events_log (created_at, event_type, user_id, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (now + offset, event_type, int(user_id), json.dumps(payload or {}, ensure_ascii=False)),
            )

    def _seed_activity(self, db):
        self._log_event(db, self.aurix_user, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=6)
        self._log_event(db, self.aurix_peer, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], count=1)
        self._log_event(db, self.ignis_user, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=5)
        self._log_event(db, self.ventra_user, game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"], count=1, payload={"success": True})

    def test_report_is_created_and_ranked_by_activity_score(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._seed_activity(db)
            result = game_app.calculate_faction_weekly_report(db)
            db.commit()

            self.assertEqual(result["updated_count"], 3)
            rows = game_app.get_faction_weekly_report(db)
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["faction_key"], "aurix")
            self.assertEqual(rows[0]["rank"], 1)
            self.assertEqual(rows[0]["report_label"], "research_leader")
            self.assertEqual(rows[0]["report_label_text"], "今週の研究優勢陣営")
            self.assertEqual(rows[1]["report_label"], "minority_elite")
            self.assertTrue(rows[1]["is_minority"])

    def test_finalize_marks_rows_and_emits_one_world_event(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._seed_activity(db)
            first = game_app.calculate_faction_weekly_report(db, finalize=True)
            second = game_app.calculate_faction_weekly_report(db, finalize=True)
            db.commit()

            self.assertTrue(first["emitted_world_event"])
            self.assertFalse(second["emitted_world_event"])
            rows = game_app.get_faction_weekly_report(db)
            self.assertTrue(all(row["is_finalized"] for row in rows))
            self.assertTrue(all(row["finalized_at"] for row in rows))
            event_count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ?",
                    (game_app.FACTION_WEEKLY_REPORT_EVENT_TYPE,),
                ).fetchone()["c"]
            )
            self.assertEqual(event_count, 1)

    def test_admin_recalculate_and_finalize_routes_write_audit_logs(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._seed_activity(db)
            db.commit()

        client = self._client(self.admin_id, "admin_report")
        self.assertEqual(client.post("/admin/factions/report/recalculate").status_code, 302)
        self.assertEqual(client.post("/admin/factions/report/finalize").status_code, 302)
        self.assertEqual(client.post("/admin/factions/report/finalize").status_code, 302)

        with game_app.app.app_context():
            db = game_app.get_db()
            recalc = db.execute(
                "SELECT payload_json FROM world_events_log WHERE event_type = ? ORDER BY id DESC LIMIT 1",
                (game_app.AUDIT_EVENT_TYPES["FACTION_REPORT_RECALCULATE"],),
            ).fetchone()
            finalize = db.execute(
                "SELECT payload_json FROM world_events_log WHERE event_type = ? ORDER BY id DESC LIMIT 1",
                (game_app.AUDIT_EVENT_TYPES["FACTION_REPORT_FINALIZE"],),
            ).fetchone()
            self.assertIsNotNone(recalc)
            self.assertIsNotNone(finalize)
            self.assertEqual(json.loads(recalc["payload_json"])["actor_admin_id"], self.admin_id)
            self.assertEqual(json.loads(finalize["payload_json"])["actor_admin_id"], self.admin_id)
            event_count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ?",
                    (game_app.FACTION_WEEKLY_REPORT_EVENT_TYPE,),
                ).fetchone()["c"]
            )
            self.assertEqual(event_count, 1)

    def test_world_and_faction_pages_show_weekly_report(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._seed_activity(db)
            game_app.calculate_faction_weekly_report(db)
            db.commit()

        client = self._client()
        world_html = client.get("/world").get_data(as_text=True)
        self.assertIn("今週の陣営順位", world_html)
        self.assertIn("今週の研究優勢陣営", world_html)
        self.assertIn("オリクス", world_html)
        self.assertIn("現在は勝敗報酬や戦闘補正はありません", world_html)

        faction_html = client.get("/faction").get_data(as_text=True)
        self.assertIn("今週の陣営比較", faction_html)
        self.assertIn("あなたの研究方針", faction_html)
        self.assertIn("オリクス", faction_html)
        self.assertIn("活動スコア", faction_html)


if __name__ == "__main__":
    unittest.main()
