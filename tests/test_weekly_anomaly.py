import os
import tempfile
import time
import unittest

from werkzeug.security import generate_password_hash

import app as game_app
import init_db
from services.audit import audit_log
from services.daily_research import EVENT_ANOMALY_ATTEMPT, get_day_key, get_or_create_daily_research_missions
from services.weekly_anomaly import (
    ANOMALY_CLEAR_REWARD_COINS,
    build_cycle_config,
    class_for_layer,
    get_or_create_cycle,
    ranking_rows,
    summarize_battle_result,
)


class WeeklyAnomalyTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        self.old_bypass = game_app.app.config.get("BYPASS_RELEASE_GATES_IN_TESTS", True)
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        init_db.main()
        game_app.app.config["TESTING"] = True
        game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = False
        self.now = int(time.time())

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = self.old_bypass
        self.tmpdir.cleanup()

    def _login(self, client, user_id, username):
        with client.session_transaction() as sess:
            sess["user_id"] = int(user_id)
            sess["username"] = username

    def _create_user(self, db, username, *, is_admin=0, analytics_excluded=0, max_layer=1, coins=0):
        db.execute(
            """
            INSERT INTO users
            (username, password_hash, created_at, last_seen_at, is_admin, is_admin_protected, analytics_excluded, max_unlocked_layer, coins)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                generate_password_hash("pw"),
                self.now,
                self.now,
                int(is_admin),
                int(is_admin),
                int(analytics_excluded),
                int(max_layer),
                int(coins),
            ),
        )
        return int(db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"])

    def _create_robot(self, db, user_id, name="AnomalyBot", style="stable"):
        db.execute(
            """
            INSERT INTO robot_instances (user_id, name, status, style_key, style_current_key, created_at, updated_at)
            VALUES (?, ?, 'active', ?, ?, ?, ?)
            """,
            (int(user_id), name, style, style, self.now, self.now),
        )
        robot_id = int(db.execute("SELECT id FROM robot_instances WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()["id"])
        db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (robot_id, int(user_id)))
        return robot_id

    def _unlock_anomaly(self, db):
        db.execute("INSERT INTO release_flags (key, is_public, updated_at) VALUES ('anomaly', 1, ?) ON CONFLICT(key) DO UPDATE SET is_public = 1", (self.now,))

    def _insert_explores(self, db, user_id, count=3):
        for i in range(count):
            audit_log(
                db,
                game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                user_id=int(user_id),
                request_id=f"explore-{user_id}-{i}",
                payload={"area_key": "layer_1", "result": {"win": True}},
            )

    def test_same_week_cycle_is_stable_and_next_week_changes_config(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            first = get_or_create_cycle(db, "2026-W33")["cycle"]
            second = get_or_create_cycle(db, "2026-W33")["cycle"]
            self.assertEqual(first["template_key"], second["template_key"])
            self.assertEqual(first["config_json"], second["config_json"])
            self.assertNotEqual(build_cycle_config("2026-W33")["seed"], build_cycle_config("2026-W34")["seed"])

    def test_release_admin_only_and_participation_gate(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            user_id = self._create_user(db, "anomaly_new", max_layer=1)
            admin_id = self._create_user(db, "anomaly_admin", is_admin=1, max_layer=6)
            self._create_robot(db, user_id)
            self._create_robot(db, admin_id)
            db.commit()
        with game_app.app.test_client() as client:
            self._login(client, user_id, "anomaly_new")
            self.assertEqual(client.get("/anomaly").status_code, 302)
        with game_app.app.test_client() as client:
            self._login(client, admin_id, "anomaly_admin")
            self.assertEqual(client.get("/anomaly").status_code, 200)
        with game_app.app.app_context():
            db = game_app.get_db()
            self._unlock_anomaly(db)
            db.commit()
        with game_app.app.test_client() as client:
            self._login(client, user_id, "anomaly_new")
            response = client.get("/anomaly", follow_redirects=False)
            self.assertEqual(response.status_code, 302)

    def test_class_mapping_uses_progression_layers(self):
        self.assertEqual(class_for_layer(1), "observe")
        self.assertEqual(class_for_layer(2), "observe")
        self.assertEqual(class_for_layer(3), "field")
        self.assertEqual(class_for_layer(4), "field")
        self.assertEqual(class_for_layer(5), "deep")
        self.assertEqual(class_for_layer(7), "deep")

    def test_summary_treats_zero_enemy_hp_as_clear(self):
        summary = summarize_battle_result(
            {
                "enemy_max_hp": 500,
                "enemy_final_hp": 0,
                "player_max_hp": 700,
                "player_final_hp": 210,
                "turn_count": 6,
            }
        )
        self.assertEqual(summary["result"], "clear")
        self.assertEqual(summary["analysis_rate"], 100)
        self.assertEqual(summary["enemy_hp_remaining"], 0)

    def test_challenge_records_attempt_reward_and_idempotent_request(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            user_id = self._create_user(db, "anomaly_player", max_layer=6)
            self._create_robot(db, user_id, style="burst")
            self._unlock_anomaly(db)
            self._insert_explores(db, user_id, 3)
            db.commit()
        with game_app.app.test_client() as client:
            self._login(client, user_id, "anomaly_player")
            html = client.get("/anomaly").get_data(as_text=True)
            self.assertIn("週次異常個体", html)
            with client.session_transaction() as sess:
                submission_id = sess["anomaly_submission_id"]
            first = client.post("/anomaly/challenge", data={"submission_id": submission_id})
            second = client.post("/anomaly/challenge", data={"submission_id": submission_id})
            self.assertEqual(first.status_code, 302)
            self.assertEqual(second.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            attempts = db.execute("SELECT COUNT(*) AS c, MAX(turns) AS turns FROM anomaly_attempts WHERE user_id = ?", (user_id,)).fetchone()
            self.assertEqual(int(attempts["c"]), 1)
            self.assertLessEqual(int(attempts["turns"]), 8)
            row = db.execute("SELECT analysis_rate FROM anomaly_attempts WHERE user_id = ?", (user_id,)).fetchone()
            self.assertGreaterEqual(int(row["analysis_rate"]), 0)
            self.assertLessEqual(int(row["analysis_rate"]), 100)

    def test_ranking_separates_classes_and_excludes_admin(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_anomaly_schema(db)
            real_id = self._create_user(db, "anomaly_real", max_layer=6)
            admin_id = self._create_user(db, "anomaly_admin_rank", is_admin=1, max_layer=6)
            obs_id = self._create_user(db, "anomaly_observe", max_layer=1)
            real_robot = self._create_robot(db, real_id)
            admin_robot = self._create_robot(db, admin_id)
            obs_robot = self._create_robot(db, obs_id)
            for uid, robot_id, cls, rate, result in [
                (real_id, real_robot, "deep", 80, "incomplete"),
                (admin_id, admin_robot, "deep", 100, "clear"),
                (obs_id, obs_robot, "observe", 99, "incomplete"),
            ]:
                db.execute(
                    """
                    INSERT INTO anomaly_attempts
                    (week_key, user_id, robot_instance_id, challenge_class, template_key, result, turns,
                     player_hp_remaining, player_hp_max, enemy_hp_remaining, enemy_hp_max, damage_dealt,
                     analysis_rate, request_id, created_at)
                    VALUES ('2026-W33', ?, ?, ?, 'veil_runner', ?, 5, 50, 100, 10, 100, ?, ?, ?, ?)
                    """,
                    (uid, robot_id, cls, result, rate, rate, f"rank-{uid}", self.now + uid),
                )
            db.commit()
            deep = ranking_rows(db, week_key="2026-W33", challenge_class="deep", limit=5)
            observe = ranking_rows(db, week_key="2026-W33", challenge_class="observe", limit=5)
            self.assertEqual([row["user_id"] for row in deep], [real_id])
            self.assertEqual([row["user_id"] for row in observe], [obs_id])

    def test_daily_research_anomaly_candidate_only_when_eligible_and_attempt_progresses(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            user_id = self._create_user(db, "anomaly_daily", max_layer=3)
            self._unlock_anomaly(db)
            self._insert_explores(db, user_id, 3)
            day = get_day_key()
            missions = get_or_create_daily_research_missions(db, user_id, day)
            if not any(m["mission_key"] == "anomaly_observe_1" for m in missions):
                db.execute(
                    """
                    INSERT OR IGNORE INTO daily_research_progress
                    (user_id, day_key, mission_key, mission_type, title, description, condition_key, target, reward_coins, created_at, updated_at)
                    VALUES (?, ?, 'anomaly_observe_1', 'anomaly', '異常反応観測', '今週の異常個体へ1回挑戦', 'anomaly_attempt', 1, 25, ?, ?)
                    """,
                    (user_id, get_day_key(), self.now, self.now),
                )
            db.commit()
            audit_log(db, EVENT_ANOMALY_ATTEMPT, user_id=user_id, request_id="daily-anomaly-1", payload={"week_key": "2026-W33"})
            row = db.execute("SELECT progress, completed_at FROM daily_research_progress WHERE user_id = ? AND mission_key = 'anomaly_observe_1'", (user_id,)).fetchone()
            self.assertEqual(int(row["progress"]), 1)
            self.assertIsNotNone(row["completed_at"])


if __name__ == "__main__":
    unittest.main()
