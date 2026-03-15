import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactionWarTests(unittest.TestCase):
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
                "INSERT INTO users (username, password_hash, created_at, is_admin) VALUES (?, ?, ?, 0)",
                ("faction_user", "x", now),
            )
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin, faction) VALUES (?, ?, ?, 1, 'ignis')",
                ("faction_admin", "x", now),
            )
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin, faction) VALUES (?, ?, ?, 0, 'ignis')",
                ("f_ignis", "x", now),
            )
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin, faction) VALUES (?, ?, ?, 0, 'ventra')",
                ("f_ventra", "x", now),
            )
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin, faction) VALUES (?, ?, ?, 0, 'aurix')",
                ("f_aurix", "x", now),
            )
            self.user_id = db.execute("SELECT id FROM users WHERE username = 'faction_user'").fetchone()["id"]
            self.admin_id = db.execute("SELECT id FROM users WHERE username = 'faction_admin'").fetchone()["id"]
            self.ignis_id = db.execute("SELECT id FROM users WHERE username = 'f_ignis'").fetchone()["id"]
            self.ventra_id = db.execute("SELECT id FROM users WHERE username = 'f_ventra'").fetchone()["id"]
            self.aurix_id = db.execute("SELECT id FROM users WHERE username = 'f_aurix'").fetchone()["id"]
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _login(self, client, user_id, username):
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["username"] = username

    def _insert_event(self, user_id, event_type, payload=None, created_at=None):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (int(created_at or time.time()), event_type, json.dumps(payload or {}, ensure_ascii=False), int(user_id)),
            )
            db.commit()

    def test_faction_choose_blocked_until_requirements_met(self):
        with game_app.app.test_client() as client:
            self._login(client, self.user_id, "faction_user")
            resp = client.get("/faction/choose")
            self.assertEqual(resp.status_code, 403)

    def test_faction_choose_unlock_and_audit_logged(self):
        now = int(time.time())
        for _ in range(20):
            self._insert_event(self.user_id, "audit.explore.end", payload={"result": {"win": True}}, created_at=now)
        for _ in range(5):
            self._insert_event(self.user_id, "audit.build.confirm", created_at=now)
        for _ in range(3):
            self._insert_event(self.user_id, "audit.fuse", created_at=now)

        with game_app.app.test_client() as client:
            self._login(client, self.user_id, "faction_user")
            ok_page = client.get("/faction/choose")
            self.assertEqual(ok_page.status_code, 200)
            choose = client.post("/faction/choose", data={"faction": "ventra"}, follow_redirects=False)
            self.assertEqual(choose.status_code, 302)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT faction FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(row["faction"], "ventra")
            audit = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ? ORDER BY id DESC LIMIT 1",
                (self.user_id, "audit.faction.choose"),
            ).fetchone()
            self.assertIsNotNone(audit)

    def test_faction_war_recompute_aggregates_scores_and_winner(self):
        now = int(time.time())
        current_week = game_app._world_week_key(now)
        for _ in range(2):
            self._insert_event(self.ignis_id, "audit.explore.end", payload={"result": {"win": True}}, created_at=now)
        self._insert_event(self.ignis_id, "audit.boss.defeat", created_at=now)
        self._insert_event(self.ventra_id, "audit.build.confirm", created_at=now)
        self._insert_event(self.aurix_id, "audit.fuse", created_at=now)
        self._insert_event(self.aurix_id, "audit.fuse", created_at=now)

        with game_app.app.app_context():
            db = game_app.get_db()
            result = game_app._faction_war_recompute(db, current_week)
            db.commit()
            self.assertEqual(result["winner_faction"], "ignis")
            scores = db.execute(
                "SELECT faction, points FROM world_faction_weekly_scores WHERE week_key = ?",
                (current_week,),
            ).fetchall()
            by_faction = {row["faction"]: int(row["points"]) for row in scores}
            self.assertEqual(by_faction.get("ignis"), 12)
            self.assertEqual(by_faction.get("ventra"), 2)
            self.assertEqual(by_faction.get("aurix"), 2)
            winner = db.execute(
                "SELECT winner_faction FROM world_faction_weekly_result WHERE week_key = ?",
                (current_week,),
            ).fetchone()
            self.assertIsNotNone(winner)
            self.assertEqual(winner["winner_faction"], "ignis")

    def test_admin_recompute_route_writes_week_result(self):
        current_week = game_app._world_week_key()
        with game_app.app.test_client() as client:
            self._login(client, self.admin_id, "faction_admin")
            resp = client.get(f"/admin/world/faction-war/recompute?week_key={current_week}", follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT week_key, winner_faction FROM world_faction_weekly_result WHERE week_key = ?",
                (current_week,),
            ).fetchone()
            self.assertIsNotNone(row)

    def test_auto_close_creates_prev_week_result_once(self):
        now = int(time.time())
        current_week = game_app._world_week_key(now)
        prev_week = game_app._faction_prev_week_key(current_week)
        prev_start, _ = game_app._world_week_bounds(prev_week)
        prev_ts = int(prev_start.timestamp()) + 60
        self._insert_event(self.ignis_id, "audit.build.confirm", created_at=prev_ts)

        with game_app.app.test_client() as client:
            self._login(client, self.admin_id, "faction_admin")
            resp1 = client.get("/home")
            self.assertEqual(resp1.status_code, 200)
            resp2 = client.get("/home")
            self.assertEqual(resp2.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            result_row = db.execute(
                "SELECT week_key FROM world_faction_weekly_result WHERE week_key = ?",
                (prev_week,),
            ).fetchone()
            self.assertIsNotNone(result_row)
            event_count = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = 'FACTION_WAR_RESULT' AND CAST(json_extract(payload_json, '$.week_key') AS TEXT) = ?",
                (prev_week,),
            ).fetchone()["c"]
            self.assertEqual(int(event_count or 0), 1)


if __name__ == "__main__":
    unittest.main()
