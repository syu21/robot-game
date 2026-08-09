import os
import tempfile
import time
import unittest
from datetime import datetime, timezone

import app as game_app
import init_db
from services.audit import audit_log
from services.daily_research import (
    DAILY_RESEARCH_ALL_COMPLETE_COIN_REWARD,
    DAILY_RESEARCH_TASK_CLAIM,
    EVENT_BUILD_CONFIRM,
    EVENT_EXPLORE_END,
    EVENT_FUSE,
    daily_research_admin_summary,
    get_daily_research_missions,
    get_day_key,
    get_or_create_daily_research_missions,
)


class DailyResearchV1Tests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, coins, max_unlocked_layer)
                VALUES (?, ?, ?, 0, 1)
                """,
                ("daily_research_user", "x", now),
            )
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, coins, is_admin, max_unlocked_layer)
                VALUES (?, ?, ?, 0, 1, 3)
                """,
                ("daily_research_admin", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("daily_research_user",)).fetchone()["id"])
            self.admin_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("daily_research_admin",)).fetchone()["id"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def test_same_day_generates_same_three_common_missions(self):
        first = get_daily_research_missions("2026-08-09")
        second = get_daily_research_missions("2026-08-09")
        self.assertEqual([m["key"] for m in first], [m["key"] for m in second])
        self.assertEqual(len(first), 3)
        self.assertEqual(len({m["mission_type"] for m in first}), 3)

    def test_date_change_updates_missions(self):
        first = [m["key"] for m in get_daily_research_missions("2026-08-09")]
        changed = False
        for day in ["2026-08-10", "2026-08-11", "2026-08-12"]:
            if [m["key"] for m in get_daily_research_missions(day)] != first:
                changed = True
                break
        self.assertTrue(changed)

    def test_jst_day_boundary(self):
        before_midnight = datetime(2026, 8, 8, 14, 59, tzinfo=timezone.utc)
        after_midnight = datetime(2026, 8, 8, 15, 0, tzinfo=timezone.utc)
        self.assertEqual(get_day_key(before_midnight), "2026-08-08")
        self.assertEqual(get_day_key(after_midnight), "2026-08-09")

    def test_new_user_does_not_get_unlocked_area_target(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            missions = get_or_create_daily_research_missions(db, self.user_id, "2026-08-09")
            rows = db.execute(
                "SELECT mission_key, title, description FROM daily_research_progress WHERE user_id = ?",
                (self.user_id,),
            ).fetchall()
            self.assertEqual(len(missions), 3)
            text = "\n".join(f"{row['title']} {row['description']}" for row in rows)
            self.assertNotIn("第4層", text)

    def test_three_explores_complete_sortie_mission(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            get_or_create_daily_research_missions(db, self.user_id, get_day_key())
            db.execute(
                """
                UPDATE daily_research_progress
                SET mission_key = 'patrol_sortie_3', title = '巡回試験', condition_key = 'explore_complete', target = 3, progress = 0, completed_at = NULL, reward_claimed_at = NULL
                WHERE user_id = ? AND mission_type = 'sortie'
                """,
                (self.user_id,),
            )
            db.commit()
            for i in range(3):
                audit_log(db, EVENT_EXPLORE_END, user_id=self.user_id, request_id=f"explore-{i}", payload={"area_key": "layer_1", "result": {"win": True}})
            row = db.execute("SELECT progress, completed_at FROM daily_research_progress WHERE user_id = ? AND mission_key = 'patrol_sortie_3'", (self.user_id,)).fetchone()
            self.assertEqual(int(row["progress"]), 3)
            self.assertIsNotNone(row["completed_at"])

    def test_strengthen_once_completes_strengthen_mission(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            get_or_create_daily_research_missions(db, self.user_id, get_day_key())
            db.execute(
                """
                UPDATE daily_research_progress
                SET mission_key = 'strengthen_process_1', title = '強化試験', condition_key = 'strengthen', target = 1, progress = 0, completed_at = NULL, reward_claimed_at = NULL
                WHERE user_id = ? AND mission_type = 'training'
                """,
                (self.user_id,),
            )
            db.commit()
            audit_log(db, EVENT_FUSE, user_id=self.user_id, request_id="strengthen-1", payload={"success": True})
            row = db.execute("SELECT progress, completed_at FROM daily_research_progress WHERE user_id = ? AND mission_key = 'strengthen_process_1'", (self.user_id,)).fetchone()
            self.assertEqual(int(row["progress"]), 1)
            self.assertIsNotNone(row["completed_at"])

    def test_growth_tendency_progresses_only_matching_area(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            get_or_create_daily_research_missions(db, self.user_id, get_day_key())
            db.execute(
                """
                UPDATE daily_research_progress
                SET mission_key = 'aim_tendency_win_3', title = '照準試験', condition_key = 'tendency_win', target = 3, progress = 0, completed_at = NULL, reward_claimed_at = NULL
                WHERE user_id = ? AND mission_type = 'tendency'
                """,
                (self.user_id,),
            )
            db.commit()
            audit_log(db, EVENT_EXPLORE_END, user_id=self.user_id, request_id="wrong-area", payload={"area_key": "layer_2", "result": {"win": True}})
            audit_log(db, EVENT_EXPLORE_END, user_id=self.user_id, request_id="right-area", payload={"area_key": "layer_2_mist", "result": {"win": True}})
            row = db.execute("SELECT progress FROM daily_research_progress WHERE user_id = ? AND mission_key = 'aim_tendency_win_3'", (self.user_id,)).fetchone()
            self.assertEqual(int(row["progress"]), 1)

    def test_same_operation_does_not_double_count_or_double_reward(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            get_or_create_daily_research_missions(db, self.user_id, get_day_key())
            db.execute(
                """
                UPDATE daily_research_progress
                SET mission_key = 'strengthen_process_1', title = '強化試験', condition_key = 'strengthen', target = 1, progress = 0, completed_at = NULL, reward_claimed_at = NULL, reward_coins = 25
                WHERE user_id = ? AND mission_type = 'training'
                """,
                (self.user_id,),
            )
            db.commit()
            audit_log(db, EVENT_FUSE, user_id=self.user_id, request_id="same-request", payload={"success": True})
            audit_log(db, EVENT_FUSE, user_id=self.user_id, request_id="same-request", payload={"success": True})
            row = db.execute("SELECT progress FROM daily_research_progress WHERE user_id = ? AND mission_key = 'strengthen_process_1'", (self.user_id,)).fetchone()
            coins = int(db.execute("SELECT coins FROM users WHERE id = ?", (self.user_id,)).fetchone()["coins"])
            self.assertEqual(int(row["progress"]), 1)
            self.assertEqual(coins, 25)

    def test_all_complete_reward_is_once(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            get_or_create_daily_research_missions(db, self.user_id, get_day_key())
            db.execute(
                """
                UPDATE daily_research_progress
                SET target = 1, progress = 0, completed_at = NULL, reward_claimed_at = NULL, reward_coins = 0
                WHERE user_id = ?
                """,
                (self.user_id,),
            )
            db.execute("UPDATE daily_research_progress SET condition_key = 'explore_complete' WHERE user_id = ? AND mission_type = 'sortie'", (self.user_id,))
            db.execute("UPDATE daily_research_progress SET condition_key = 'strengthen' WHERE user_id = ? AND mission_type = 'training'", (self.user_id,))
            db.execute("UPDATE daily_research_progress SET mission_key = 'armor_tendency_win_3', condition_key = 'tendency_win' WHERE user_id = ? AND mission_type = 'tendency'", (self.user_id,))
            db.commit()
            audit_log(db, EVENT_EXPLORE_END, user_id=self.user_id, request_id="all-1", payload={"area_key": "layer_1", "result": {"win": True}})
            audit_log(db, EVENT_FUSE, user_id=self.user_id, request_id="all-2", payload={"success": True})
            audit_log(db, EVENT_EXPLORE_END, user_id=self.user_id, request_id="all-3", payload={"area_key": "layer_1", "result": {"win": True}})
            audit_log(db, EVENT_EXPLORE_END, user_id=self.user_id, request_id="all-3", payload={"area_key": "layer_1", "result": {"win": True}})
            coins = int(db.execute("SELECT coins FROM users WHERE id = ?", (self.user_id,)).fetchone()["coins"])
            self.assertEqual(coins, DAILY_RESEARCH_ALL_COMPLETE_COIN_REWARD)
            reward_events = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ? AND json_extract(payload_json, '$.mission_key') = 'daily_research_all_complete'",
                    (self.user_id, DAILY_RESEARCH_TASK_CLAIM),
                ).fetchone()["c"]
            )
            self.assertEqual(reward_events, 1)

    def test_admin_metrics_is_admin_only_and_summary_counts(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            get_or_create_daily_research_missions(db, self.user_id, get_day_key())
            summary = daily_research_admin_summary(db, get_day_key())
            self.assertEqual(summary["viewed_users"], 1)
            self.assertEqual(len(summary["missions"]), 3)

        client = game_app.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
            sess["username"] = "daily_research_user"
        self.assertEqual(client.get("/admin/metrics").status_code, 403)

        with client.session_transaction() as sess:
            sess["user_id"] = self.admin_id
            sess["username"] = "daily_research_admin"
        self.assertEqual(client.get("/admin/metrics").status_code, 200)

    def test_build_confirm_completes_build_mission(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            get_or_create_daily_research_missions(db, self.user_id, get_day_key())
            db.execute(
                """
                UPDATE daily_research_progress
                SET mission_key = 'build_update_1', title = '編成試験', condition_key = 'build_confirm', target = 1, progress = 0, completed_at = NULL, reward_claimed_at = NULL
                WHERE user_id = ? AND mission_type = 'training'
                """,
                (self.user_id,),
            )
            db.commit()
            audit_log(db, EVENT_BUILD_CONFIRM, user_id=self.user_id, request_id="build-1", payload={"robot_instance_id": 1})
            row = db.execute("SELECT progress, completed_at FROM daily_research_progress WHERE user_id = ? AND mission_key = 'build_update_1'", (self.user_id,)).fetchone()
            self.assertEqual(int(row["progress"]), 1)
            self.assertIsNotNone(row["completed_at"])


if __name__ == "__main__":
    unittest.main()
