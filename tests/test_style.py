import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db
from services import style as style_service


class StyleServiceTests(unittest.TestCase):
    def test_style_scores_are_deterministic_and_normalized(self):
        stats = {"hp": 120, "atk": 20, "def": 90, "spd": 25, "acc": 40, "cri": 10}
        raw = style_service.compute_style_scores(stats)
        normalized = style_service.normalize_style_scores(raw)

        self.assertEqual(style_service.resolve_current_style(raw), "stable")
        self.assertEqual(sum(normalized.values()), 100)
        self.assertTrue(all(value >= 0 for value in normalized.values()))

    def test_style_tie_break_and_next_style(self):
        scores = {"stable": 0.5, "burst": 0.5, "desperate": 0.5}
        self.assertEqual(style_service.resolve_current_style(scores), "stable")
        self.assertEqual(style_service.resolve_next_style(scores, "stable"), "burst")

    def test_style_rank_thresholds_and_award(self):
        state = style_service.empty_style_rank_state()
        result = style_service.award_style_xp_state(state, "burst", amount=10)
        self.assertTrue(result["rank_up"])
        self.assertEqual(result["old_rank"], 1)
        self.assertEqual(result["new_rank"], 2)
        self.assertEqual(style_service.get_style_rank_label(result["new_rank"]), "II")

        result = style_service.award_style_xp_state(result["state"], "burst", amount=200)
        self.assertEqual(result["new_rank"], 5)
        self.assertEqual(style_service.get_style_rank_label(result["new_rank"]), "MASTER")


class StyleRouteIntegrationTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, coins, max_unlocked_layer)
                VALUES (?, ?, ?, 0, 0, 0, 1)
                """,
                ("style_tester", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("style_tester",),
            ).fetchone()["id"]
            game_app.initialize_new_user(db, self.user_id)
            self.robot_id = db.execute(
                "SELECT active_robot_id FROM users WHERE id = ?",
                (self.user_id,),
            ).fetchone()["active_robot_id"]
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "style_tester"
        return client

    def test_home_shows_style_gauge_and_rank(self):
        client = self._client()
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("思想ゲージ", html)
        self.assertIn("思想ランク", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                """
                SELECT style_scores_json, style_rank_json, style_current_key, style_next_key
                FROM robot_instances
                WHERE id = ?
                """,
                (int(self.robot_id),),
            ).fetchone()
            self.assertTrue(row["style_scores_json"])
            self.assertTrue(row["style_rank_json"])
            self.assertIn(row["style_current_key"], style_service.STYLE_KEYS)
            self.assertIn(row["style_next_key"], style_service.STYLE_KEYS)

    def test_award_style_xp_persists_and_rank_up_logs(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            robot = db.execute(
                "SELECT * FROM robot_instances WHERE id = ?",
                (int(self.robot_id),),
            ).fetchone()
            game_app._ensure_style_snapshot(db, int(self.robot_id), force=True)
            result = game_app._award_robot_style_xp(db, int(self.robot_id), "burst", amount=10)
            game_app._record_style_rank_result(
                db,
                user_id=int(self.user_id),
                robot=robot,
                award_result=result,
                request_id="test-style-rank",
                ip="127.0.0.1",
            )
            db.commit()

            row = db.execute(
                "SELECT style_rank_json FROM robot_instances WHERE id = ?",
                (int(self.robot_id),),
            ).fetchone()
            rank_state = json.loads(row["style_rank_json"])
            self.assertEqual(rank_state["burst"]["rank"], 2)
            count = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ? AND user_id = ?",
                (game_app.AUDIT_EVENT_TYPES["STYLE_RANK_UP"], int(self.user_id)),
            ).fetchone()["c"]
            self.assertEqual(int(count), 1)


if __name__ == "__main__":
    unittest.main()
