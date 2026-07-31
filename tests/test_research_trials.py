import os
import tempfile
import time
import unittest
from unittest import mock

import app as game_app
import init_db


class ResearchTrialTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 0, 0, 3)
                """,
                ("trial_user", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("trial_user",)).fetchone()["id"])
            game_app.initialize_new_user(db, self.user_id)
            self.robot_id = int(db.execute("SELECT active_robot_id FROM users WHERE id = ?", (self.user_id,)).fetchone()["active_robot_id"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "trial_user"
        return client

    def test_research_trial_tables_exist(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            tables = {
                row["name"]
                for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }
            self.assertIn("research_trial_attempts", tables)
            self.assertIn("user_research_trial_progress", tables)

    def test_trial_list_renders_twelve_trials_and_links(self):
        html = self._client().get("/research/trials").get_data(as_text=True)
        self.assertIn("研究試験場", html)
        self.assertIn("合格 0 / 12", html)
        self.assertIn("高速決着試験", html)
        self.assertIn("速攻型三連戦試験", html)
        self.assertIn("第2層ボス再現試験", html)

        factory_html = self._client().get("/factory").get_data(as_text=True)
        self.assertIn("研究試験場へ", factory_html)
        research_html = self._client().get("/research").get_data(as_text=True)
        self.assertIn("研究試験場", research_html)

    def test_trial_run_records_progress_and_exp_delta_once(self):
        battle = {
            "win": True,
            "turns": 4,
            "timeout": False,
            "player_hp_max": 20,
            "player_final_hp": 16,
            "player_hp_percent": 80,
            "enemy_final_hp": 0,
            "defeated_count": 1,
            "enemy_count": 1,
            "player_damage_total": 40,
            "enemy_damage_total": 4,
            "player_miss_count": 0,
            "enemy_miss_count": 0,
            "turn_logs": [
                {"turn": 1, "actor": "player", "enemy_name": "標準試験機", "damage": 20, "miss": False},
            ],
        }
        client = self._client()
        with mock.patch.object(game_app, "_simulate_research_trial", return_value=battle):
            html = client.post("/research/trials/perf_fast_win", follow_redirects=True).get_data(as_text=True)
            self.assertIn("完全解析", html)
            self.assertIn("研究EXP +55", html)
            html = client.post("/research/trials/perf_fast_win", follow_redirects=True).get_data(as_text=True)
            self.assertIn("ベスト更新なし", html)
            self.assertIn("研究EXP +0", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            attempts = int(db.execute("SELECT COUNT(*) AS c FROM research_trial_attempts WHERE user_id = ?", (self.user_id,)).fetchone()["c"])
            progress = db.execute(
                "SELECT best_grade, best_grade_rank, attempts_count FROM user_research_trial_progress WHERE user_id = ? AND trial_key = ?",
                (self.user_id, "perf_fast_win"),
            ).fetchone()
            user = db.execute("SELECT lab_total_exp FROM users WHERE id = ?", (self.user_id,)).fetchone()
            title = db.execute(
                "SELECT 1 FROM robot_title_grants WHERE robot_id = ? AND title_key = ?",
                (self.robot_id, "research_trial_analyst"),
            ).fetchone()
            self.assertEqual(attempts, 2)
            self.assertEqual(progress["best_grade"], "complete")
            self.assertEqual(int(progress["best_grade_rank"]), 3)
            self.assertEqual(int(progress["attempts_count"]), 2)
            self.assertEqual(int(user["lab_total_exp"]), 55)
            self.assertIsNotNone(title)


if __name__ == "__main__":
    unittest.main()
