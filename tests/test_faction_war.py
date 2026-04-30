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
            self.assertEqual(by_faction.get("ignis"), 22)
            self.assertEqual(by_faction.get("ventra"), 2)
            self.assertEqual(by_faction.get("aurix"), 2)
            winner = db.execute(
                "SELECT winner_faction, summary_text, highlights_json, mvp_json FROM world_faction_weekly_result WHERE week_key = ?",
                (current_week,),
            ).fetchone()
            self.assertIsNotNone(winner)
            self.assertEqual(winner["winner_faction"], "ignis")
            self.assertTrue(winner["summary_text"])
            self.assertTrue(winner["highlights_json"])
            self.assertTrue(winner["mvp_json"])

    def test_add_faction_points_skips_unjoined_user(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            result = game_app.add_faction_points(
                db,
                self.user_id,
                "explore_win",
                1,
                counters={"explore_win_count": 1},
            )
            db.commit()
            self.assertFalse(result["ok"])
            count = db.execute("SELECT COUNT(*) AS c FROM world_faction_user_weekly_contributions").fetchone()["c"]
            self.assertEqual(int(count or 0), 0)

    def test_add_faction_points_updates_scores_contribution_and_log(self):
        week_key = game_app._world_week_key()
        with game_app.app.app_context():
            db = game_app.get_db()
            result = game_app.add_faction_points(
                db,
                self.ignis_id,
                "explore_win",
                1,
                counters={"explore_win_count": 1},
                payload={"area_key": "layer_1"},
                create_log=True,
                week_key=week_key,
            )
            db.commit()
            self.assertTrue(result["ok"])
            score = db.execute(
                "SELECT points FROM world_faction_weekly_scores WHERE week_key = ? AND faction = 'ignis'",
                (week_key,),
            ).fetchone()
            self.assertEqual(int(score["points"]), 1)
            contrib = db.execute(
                "SELECT points, explore_win_count FROM world_faction_user_weekly_contributions WHERE week_key = ? AND user_id = ?",
                (week_key, self.ignis_id),
            ).fetchone()
            self.assertEqual(int(contrib["points"]), 1)
            self.assertEqual(int(contrib["explore_win_count"]), 1)
            log = db.execute("SELECT event_type FROM world_faction_logs WHERE week_key = ? LIMIT 1", (week_key,)).fetchone()
            self.assertEqual(log["event_type"], "explore_win")

    def test_faction_points_new_event_values(self):
        week_key = game_app._world_week_key()
        cases = [
            ("evolve", 8, {"evolve_count": 1}),
            ("boss_defeat", 20, {"boss_defeat_count": 1}),
            ("champ_defeat", 15, {"champ_defeat_count": 1}),
            ("champ_upset", 30, {"champ_defeat_count": 1, "upset_count": 1}),
        ]
        with game_app.app.app_context():
            db = game_app.get_db()
            for event_type, points, counters in cases:
                game_app.add_faction_points(
                    db,
                    self.ventra_id,
                    event_type,
                    points,
                    counters=counters,
                    create_log=True,
                    week_key=week_key,
                )
            db.commit()
            contrib = db.execute(
                """
                SELECT points, evolve_count, boss_defeat_count, champ_defeat_count, upset_count
                FROM world_faction_user_weekly_contributions
                WHERE week_key = ? AND user_id = ?
                """,
                (week_key, self.ventra_id),
            ).fetchone()
            self.assertEqual(int(contrib["points"]), 73)
            self.assertEqual(int(contrib["evolve_count"]), 1)
            self.assertEqual(int(contrib["boss_defeat_count"]), 1)
            self.assertEqual(int(contrib["champ_defeat_count"]), 2)
            self.assertEqual(int(contrib["upset_count"]), 1)

    def test_comms_faction_changes_for_unjoined_and_joined(self):
        with game_app.app.test_client() as client:
            self._login(client, self.user_id, "faction_user")
            unjoined = client.get("/comms/faction")
            self.assertEqual(unjoined.status_code, 200)
            self.assertIn("まだ陣営に所属していません".encode("utf-8"), unjoined.data)

            self._login(client, self.ignis_id, "f_ignis")
            joined = client.get("/comms/faction")
            self.assertEqual(joined.status_code, 200)
            self.assertIn("イグニス通信".encode("utf-8"), joined.data)

    def test_recompute_is_not_double_counted_and_stores_mvp(self):
        now = int(time.time())
        week_key = game_app._world_week_key(now)
        self._insert_event(self.ignis_id, "audit.part.evolve", created_at=now)
        self._insert_event(self.ignis_id, "audit.champion.defeat", payload={"affinity_result": "advantage"}, created_at=now)
        self._insert_event(self.ventra_id, "CHAMP_DEFEAT_UPSET", payload={"affinity_result": "disadvantage"}, created_at=now)

        with game_app.app.app_context():
            db = game_app.get_db()
            first = game_app._faction_war_recompute(db, week_key)
            second = game_app._faction_war_recompute(db, week_key)
            db.commit()
            self.assertEqual(first["scores"], second["scores"])
            scores = db.execute(
                "SELECT faction, points FROM world_faction_weekly_scores WHERE week_key = ?",
                (week_key,),
            ).fetchall()
            by_faction = {row["faction"]: int(row["points"]) for row in scores}
            self.assertEqual(by_faction.get("ignis"), 23)
            self.assertEqual(by_faction.get("ventra"), 30)
            mvp = db.execute(
                "SELECT category, user_id FROM world_faction_weekly_mvp WHERE week_key = ? AND category = 'overall'",
                (week_key,),
            ).fetchone()
            self.assertIsNotNone(mvp)

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
