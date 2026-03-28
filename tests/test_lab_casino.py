import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class LabCasinoRouteTests(unittest.TestCase):
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
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 0, 0, 0, 1)
                """,
                ("casino_user", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("casino_user",)).fetchone()["id"])
            game_app.initialize_new_user(db, self.user_id)
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 1, 1, 0, 1)
                """,
                ("casino_admin", "x", now),
            )
            self.admin_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("casino_admin",)).fetchone()["id"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self, *, admin=False):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            if admin:
                session["user_id"] = self.admin_id
                session["username"] = "casino_admin"
            else:
                session["user_id"] = self.user_id
                session["username"] = "casino_user"
        return client

    def test_lab_race_daily_grant_applies_once_per_day(self):
        client = self._client()

        first = client.get("/lab/race")
        self.assertEqual(first.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT lab_coin, lab_coin_last_daily_at FROM users WHERE id = ?",
                (self.user_id,),
            ).fetchone()
            self.assertEqual(int(row["lab_coin"]), 1500)
            self.assertTrue(str(row["lab_coin_last_daily_at"] or "").strip())

        second = client.get("/lab/race")
        self.assertEqual(second.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT lab_coin FROM users WHERE id = ?",
                (self.user_id,),
            ).fetchone()
            self.assertEqual(int(row["lab_coin"]), 1500)

    def test_lab_race_page_uses_player_focused_copy(self):
        client = self._client()
        resp = client.get("/lab/race")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("6体の中から1体を選んで、レースの行方を見届けよう。", html)
        self.assertIn("いまのラボコイン", html)
        self.assertIn("賭けるコインを選んでスタート", html)
        self.assertIn("ロボの見かた", html)
        self.assertIn("素早さ", html)
        self.assertIn("安定", html)
        self.assertIn("器用さ", html)
        self.assertIn("ひらめき", html)
        self.assertIn("運", html)
        self.assertNotIn("敵6体の予想向けに、特殊区間だけを絞って配置するカジノコース。", html)
        self.assertNotIn("今日の補充は受け取り済み", html)
        self.assertNotIn("Race #", html)
        self.assertNotIn("10・50・100 の3択", html)

    def test_lab_race_bet_resolves_race_and_writes_audit(self):
        client = self._client()
        race_page = client.get("/lab/race")
        self.assertEqual(race_page.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            race = db.execute("SELECT * FROM lab_casino_races WHERE status = 'betting' ORDER BY id DESC LIMIT 1").fetchone()
            self.assertIsNotNone(race)
            entry = db.execute(
                "SELECT * FROM lab_casino_entries WHERE race_id = ? ORDER BY lane_index ASC LIMIT 1",
                (race["id"],),
            ).fetchone()
            self.assertIsNotNone(entry)

        resp = client.post(
            "/lab/race/bet",
            data={"race_id": int(race["id"]), "entry_id": int(entry["id"]), "amount": 50},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"/lab/race/watch/{int(race['id'])}", resp.headers["Location"])

        with game_app.app.app_context():
            db = game_app.get_db()
            race_row = db.execute("SELECT * FROM lab_casino_races WHERE id = ?", (int(race["id"]),)).fetchone()
            self.assertEqual(race_row["status"], "finished")
            frame_count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM lab_casino_frames WHERE race_id = ?",
                    (int(race["id"]),),
                ).fetchone()["c"]
                or 0
            )
            bet_row = db.execute(
                "SELECT * FROM lab_casino_bets WHERE race_id = ? AND user_id = ?",
                (int(race["id"]), self.user_id),
            ).fetchone()
            self.assertGreater(frame_count, 0)
            self.assertIsNotNone(bet_row)
            self.assertIsNotNone(bet_row["resolved_at"])
            event_types = {
                row["event_type"]
                for row in db.execute(
                    "SELECT event_type FROM world_events_log WHERE event_type LIKE 'audit.lab.casino.%'"
                ).fetchall()
            }
            self.assertIn(game_app.AUDIT_EVENT_TYPES["LAB_CASINO_BET_PLACE"], event_types)
            self.assertIn(game_app.AUDIT_EVENT_TYPES["LAB_CASINO_RACE_START"], event_types)
            self.assertIn(game_app.AUDIT_EVENT_TYPES["LAB_CASINO_RACE_FINISH"], event_types)
            self.assertIn(game_app.AUDIT_EVENT_TYPES["LAB_CASINO_BET_RESOLVE"], event_types)

    def test_lab_race_prize_claim_deducts_coin_and_records_audit(self):
        client = self._client()
        home = client.get("/lab/race")
        self.assertEqual(home.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            prize = db.execute(
                "SELECT * FROM lab_casino_prizes WHERE prize_key = 'lab_title_hot_streak' LIMIT 1"
            ).fetchone()
            self.assertIsNotNone(prize)

        resp = client.post(
            f"/lab/race/prizes/{int(prize['id'])}/claim",
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("交換しました", resp.get_data(as_text=True))

        with game_app.app.app_context():
            db = game_app.get_db()
            claim = db.execute(
                "SELECT * FROM lab_casino_prize_claims WHERE user_id = ? AND prize_id = ?",
                (self.user_id, int(prize["id"])),
            ).fetchone()
            self.assertIsNotNone(claim)
            wallet = db.execute("SELECT lab_coin FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(wallet["lab_coin"]), 1000)
            event_types = {
                row["event_type"]
                for row in db.execute(
                    "SELECT event_type FROM world_events_log WHERE event_type LIKE 'audit.lab.casino.%'"
                ).fetchall()
            }
            self.assertIn(game_app.AUDIT_EVENT_TYPES["LAB_CASINO_PRIZE_CLAIM"], event_types)

    def test_lab_race_history_page_shows_resolved_bet(self):
        client = self._client()
        client.get("/lab/race")
        with game_app.app.app_context():
            db = game_app.get_db()
            race = db.execute("SELECT * FROM lab_casino_races WHERE status = 'betting' ORDER BY id DESC LIMIT 1").fetchone()
            entry = db.execute(
                "SELECT * FROM lab_casino_entries WHERE race_id = ? ORDER BY lane_index ASC LIMIT 1",
                (int(race["id"]),),
            ).fetchone()
        client.post(
            "/lab/race/bet",
            data={"race_id": int(race["id"]), "entry_id": int(entry["id"]), "amount": 10},
            follow_redirects=False,
        )
        history = client.get("/lab/race/history")
        self.assertEqual(history.status_code, 200)
        html = history.get_data(as_text=True)
        self.assertIn(entry["display_name"], html)
        self.assertIn("/lab/race/watch/", html)

    def test_lab_home_shows_single_enemy_race_card(self):
        client = self._client()
        resp = client.get("/lab")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("エネミーレース", html)
        self.assertNotIn("ロボカジノ", html)
        self.assertNotIn('<div class="action-title">障害物レース</div>', html)

    def test_old_lab_casino_routes_redirect_to_enemy_race_routes(self):
        client = self._client()
        for old_path, new_path in (
            ("/lab/casino", "/lab/race"),
            ("/lab/casino/race", "/lab/race"),
            ("/lab/casino/history", "/lab/race/history"),
            ("/lab/casino/prizes", "/lab/race/prizes"),
        ):
            resp = client.get(old_path, follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn(new_path, resp.headers["Location"])

        client.get("/lab/race")
        with game_app.app.app_context():
            db = game_app.get_db()
            race = db.execute("SELECT * FROM lab_casino_races WHERE status = 'betting' ORDER BY id DESC LIMIT 1").fetchone()
            entry = db.execute(
                "SELECT * FROM lab_casino_entries WHERE race_id = ? ORDER BY lane_index ASC LIMIT 1",
                (int(race["id"]),),
            ).fetchone()
        client.post(
            "/lab/race/bet",
            data={"race_id": int(race["id"]), "entry_id": int(entry["id"]), "amount": 10},
            follow_redirects=False,
        )
        watch_redirect = client.get(f"/lab/casino/race/watch/{int(race['id'])}", follow_redirects=False)
        result_redirect = client.get(f"/lab/casino/race/result/{int(race['id'])}", follow_redirects=False)
        self.assertEqual(watch_redirect.status_code, 302)
        self.assertEqual(result_redirect.status_code, 302)
        self.assertIn(f"/lab/race/watch/{int(race['id'])}", watch_redirect.headers["Location"])
        self.assertIn(f"/lab/race/result/{int(race['id'])}", result_redirect.headers["Location"])


if __name__ == "__main__":
    unittest.main()
