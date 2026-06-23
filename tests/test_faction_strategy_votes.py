import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactionStrategyVoteTests(unittest.TestCase):
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
            self.admin_id = self._create_user(db, "strategy_admin", now, "aurix", is_admin=1)
            self.aurix_user = self._create_user(db, "strategy_aurix", now, "aurix")
            self.aurix_user_b = self._create_user(db, "strategy_aurix_b", now, "aurix")
            self.ignis_user = self._create_user(db, "strategy_ignis", now, "ignis")
            self.week_key = game_app.get_current_week_key()
            self.guardian_ids = {}
            for faction_key, title in (("aurix", "Aurix Strategy Guard"), ("ignis", "Ignis Strategy Guard"), ("ventra", "Ventra Strategy Guard")):
                submission_id = self._create_submission(db, self.admin_id, title, now)
                row = game_app.set_faction_guardian_from_submission(db, self.week_key, faction_key, submission_id)
                self.guardian_ids[faction_key] = int(row["id"])
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

    def _client(self, user_id=None, username="strategy_aurix"):
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
                f"strategy-{user_id}-{event_type}-{time.time_ns()}",
            ),
        )

    def test_vote_insert_and_update_same_week(self):
        client = self._client()
        self.assertEqual(client.post("/faction/strategy/vote", data={"strategy_key": "steady_sortie"}).status_code, 302)
        self.assertEqual(client.post("/faction/strategy/vote", data={"strategy_key": "focus_analysis"}).status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            rows = db.execute("SELECT * FROM faction_strategy_votes WHERE user_id = ?", (self.aurix_user,)).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["strategy_key"], "focus_analysis")
            self.assertEqual(rows[0]["faction_key"], "aurix")

    def test_vote_cannot_move_after_faction_change(self):
        client = self._client()
        client.post("/faction/strategy/vote", data={"strategy_key": "steady_sortie"})
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET faction = 'ignis' WHERE id = ?", (self.aurix_user,))
            db.commit()
        html = client.post("/faction/strategy/vote", data={"strategy_key": "focus_analysis"}, follow_redirects=True).get_data(as_text=True)
        self.assertIn("同じ週に再投票はできません", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT * FROM faction_strategy_votes WHERE user_id = ?", (self.aurix_user,)).fetchone()
            self.assertEqual(row["faction_key"], "aurix")
            self.assertEqual(row["strategy_key"], "steady_sortie")

    def test_finalize_picks_top_and_defaults_empty_factions(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now_text = game_app.now_str()
            db.execute(
                "INSERT INTO faction_strategy_votes (week_key, faction_key, user_id, strategy_key, created_at) VALUES (?, 'aurix', ?, 'focus_analysis', ?)",
                (self.week_key, self.aurix_user, now_text),
            )
            db.execute(
                "INSERT INTO faction_strategy_votes (week_key, faction_key, user_id, strategy_key, created_at) VALUES (?, 'aurix', ?, 'steady_sortie', ?)",
                (self.week_key, self.aurix_user_b, now_text),
            )
            result = game_app.finalize_faction_strategies(db, self.week_key)
            db.commit()
            rows = {row["faction_key"]: row for row in db.execute("SELECT * FROM faction_weekly_strategies WHERE week_key = ?", (self.week_key,)).fetchall()}
            self.assertEqual(rows["aurix"]["strategy_key"], "steady_sortie")
            self.assertEqual(rows["ignis"]["strategy_key"], "steady_sortie")
            self.assertTrue(result["emitted_world_event"])
            second = game_app.finalize_faction_strategies(db, self.week_key)
            self.assertFalse(second["emitted_world_event"])

    def test_finalized_strategy_adjusts_guardian_recalculation_damage(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                INSERT INTO faction_weekly_strategies
                (week_key, faction_key, strategy_key, vote_count, is_finalized, finalized_at, created_at, updated_at)
                VALUES (?, 'aurix', 'steady_sortie', 1, 1, ?, ?, ?)
                """,
                (self.week_key, game_app.now_str(), game_app.now_str(), game_app.now_str()),
            )
            self._log_event(db, self.aurix_user, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], payload={"win": True})
            result = game_app.recalculate_faction_guardian_attacks(db, self.week_key)
            row = db.execute("SELECT damage FROM faction_guardian_attacks WHERE attacker_user_id = ?", (self.aurix_user,)).fetchone()
            self.assertEqual(result["total_damage"], 2)
            self.assertEqual(row["damage"], 2)

    def test_defense_strategy_reduces_incoming_damage(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = game_app.now_str()
            db.execute(
                """
                INSERT INTO faction_weekly_strategies
                (week_key, faction_key, strategy_key, vote_count, is_finalized, finalized_at, created_at, updated_at)
                VALUES (?, 'ignis', 'defense_test', 1, 1, ?, ?, ?)
                """,
                (self.week_key, now, now, now),
            )
            self._log_event(db, self.aurix_user, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"])
            result = game_app.recalculate_faction_guardian_attacks(db, self.week_key)
            row = db.execute("SELECT damage FROM faction_guardian_attacks WHERE attacker_user_id = ?", (self.aurix_user,)).fetchone()
            self.assertEqual(result["total_damage"], 27)
            self.assertEqual(row["damage"], 27)

    def test_pages_show_strategy_sections(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.finalize_faction_strategies(db, self.week_key)
            db.commit()
        client = self._client()
        self.assertIn("今週の陣営作戦", client.get("/faction").get_data(as_text=True))
        self.assertIn("今週の陣営作戦", client.get("/world").get_data(as_text=True))
        self.assertIn("今週の陣営作戦", client.get("/comms/faction").get_data(as_text=True))

    def test_admin_strategy_finalize_requires_admin(self):
        user_client = self._client(self.aurix_user, "strategy_aurix")
        self.assertEqual(user_client.get("/admin/factions/strategies").status_code, 403)
        self.assertEqual(user_client.post("/admin/factions/strategies/finalize", data={"week_key": self.week_key}).status_code, 403)
        admin_client = self._client(self.admin_id, "strategy_admin")
        self.assertEqual(admin_client.get("/admin/factions/strategies").status_code, 200)
        self.assertEqual(admin_client.post("/admin/factions/strategies/finalize", data={"week_key": self.week_key}).status_code, 302)


if __name__ == "__main__":
    unittest.main()
