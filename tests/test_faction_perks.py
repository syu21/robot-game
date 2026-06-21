import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactionPerksTests(unittest.TestCase):
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
            self.user_id = self._create_user(db, "perk_user", now, "aurix", coins=100)
            self.no_faction_user_id = self._create_user(db, "perk_none", now, None, coins=100)
            self.admin_id = self._create_user(db, "perk_admin", now, "aurix", coins=100, is_admin=1)
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _create_user(self, db, username, now, faction, *, coins=0, is_admin=0):
        db.execute(
            """
            INSERT INTO users (username, password_hash, created_at, is_admin, wins, coins, max_unlocked_layer, faction)
            VALUES (?, ?, ?, ?, 0, ?, 1, ?)
            """,
            (username, "x", now, int(is_admin), int(coins), faction),
        )
        user_id = int(db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"])
        game_app.initialize_new_user(db, user_id)
        return user_id

    def _client(self, user_id=None, username="perk_user"):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user_id or self.user_id)
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

    def _coins(self, db, user_id):
        return int(db.execute("SELECT COALESCE(coins, 0) AS coins FROM users WHERE id = ?", (int(user_id),)).fetchone()["coins"] or 0)

    def test_activity_under_threshold_cannot_claim(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._log_event(db, self.user_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=9)
            db.commit()

        resp = self._client().post("/faction/weekly-bonus/claim", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertEqual(self._coins(db, self.user_id), 100)
            claims = db.execute("SELECT COUNT(*) AS c FROM faction_weekly_claims WHERE user_id = ?", (self.user_id,)).fetchone()["c"]
            self.assertEqual(int(claims), 0)

    def test_activity_threshold_claims_coin_and_badge_once(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._log_event(db, self.user_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=10)
            db.commit()

        resp = self._client().post("/faction/weekly-bonus/claim", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("今週の陣営特典を受け取りました。", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertEqual(self._coins(db, self.user_id), 150)
            claim = db.execute("SELECT * FROM faction_weekly_claims WHERE user_id = ?", (self.user_id,)).fetchone()
            self.assertIsNotNone(claim)
            self.assertEqual(int(claim["activity_score"]), 10)
            badge = db.execute("SELECT * FROM user_faction_badges WHERE user_id = ?", (self.user_id,)).fetchone()
            self.assertIsNotNone(badge)
            self.assertEqual(badge["badge_kind"], "weekly_participation")
            audit = db.execute(
                "SELECT payload_json FROM world_events_log WHERE event_type = ? AND user_id = ? ORDER BY id DESC LIMIT 1",
                (game_app.AUDIT_EVENT_TYPES["FACTION_WEEKLY_BONUS_CLAIM"], self.user_id),
            ).fetchone()
            self.assertIsNotNone(audit)
            payload = json.loads(audit["payload_json"])
            self.assertEqual(payload["coin_reward"], 50)

        second = self._client().post("/faction/weekly-bonus/claim", follow_redirects=True)
        self.assertEqual(second.status_code, 200)
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertEqual(self._coins(db, self.user_id), 150)
            claims = db.execute("SELECT COUNT(*) AS c FROM faction_weekly_claims WHERE user_id = ?", (self.user_id,)).fetchone()["c"]
            badges = db.execute("SELECT COUNT(*) AS c FROM user_faction_badges WHERE user_id = ?", (self.user_id,)).fetchone()["c"]
            self.assertEqual(int(claims), 1)
            self.assertEqual(int(badges), 1)

    def test_no_faction_user_cannot_claim(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._log_event(db, self.no_faction_user_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=20)
            db.commit()

        resp = self._client(self.no_faction_user_id, "perk_none").post("/faction/weekly-bonus/claim", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertEqual(self._coins(db, self.no_faction_user_id), 100)
            claims = db.execute("SELECT COUNT(*) AS c FROM faction_weekly_claims WHERE user_id = ?", (self.no_faction_user_id,)).fetchone()["c"]
            self.assertEqual(int(claims), 0)

    def test_faction_change_does_not_allow_second_claim_same_week(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._log_event(db, self.user_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=10)
            db.commit()

        self._client().post("/faction/weekly-bonus/claim", follow_redirects=True)
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET faction = 'ignis' WHERE id = ?", (self.user_id,))
            self._log_event(db, self.user_id, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], count=1)
            db.commit()

        self._client().post("/faction/weekly-bonus/claim", follow_redirects=True)
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertEqual(self._coins(db, self.user_id), 150)
            claims = db.execute("SELECT COUNT(*) AS c FROM faction_weekly_claims WHERE user_id = ?", (self.user_id,)).fetchone()["c"]
            self.assertEqual(int(claims), 1)

    def test_admin_grants_award_badges_idempotently(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._log_event(db, self.user_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=5)
            game_app.calculate_faction_weekly_awards(db)
            db.commit()

        client = self._client(self.admin_id, "perk_admin")
        first = client.post("/admin/factions/awards/grant-badges", follow_redirects=True)
        second = client.post("/admin/factions/awards/grant-badges", follow_redirects=True)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        with game_app.app.app_context():
            db = game_app.get_db()
            badges = db.execute(
                "SELECT COUNT(*) AS c FROM user_faction_badges WHERE user_id = ? AND badge_kind = 'weekly_award'",
                (self.user_id,),
            ).fetchone()["c"]
            self.assertEqual(int(badges), 2)
            audit = db.execute(
                "SELECT payload_json FROM world_events_log WHERE event_type = ? ORDER BY id DESC LIMIT 1",
                (game_app.AUDIT_EVENT_TYPES["FACTION_AWARDS_BADGES_GRANT"],),
            ).fetchone()
            self.assertIsNotNone(audit)

    def test_faction_page_shows_weekly_bonus_and_badges(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                INSERT INTO user_faction_badges
                (user_id, faction_key, badge_key, badge_label, badge_kind, week_key, source_type, granted_at, created_at)
                VALUES (?, 'aurix', 'test_badge', '今週の研究主力', 'weekly_award', ?, 'award', ?, ?)
                """,
                (self.user_id, game_app.get_current_week_key(), game_app.now_str(), game_app.now_str()),
            )
            db.commit()

        html = self._client().get("/faction").get_data(as_text=True)
        self.assertIn("今週の陣営特典", html)
        self.assertIn("コイン +50", html)
        self.assertIn("陣営参加バッジ", html)
        self.assertIn("獲得した陣営バッジ", html)
        self.assertIn("今週の研究主力", html)


if __name__ == "__main__":
    unittest.main()
