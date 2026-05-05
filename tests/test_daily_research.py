import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone

import app as game_app
import init_db
from services.audit import audit_log
from services.daily_research import (
    EVENT_BUILD_CONFIRM,
    EVENT_BOSS_ENCOUNTER,
    EVENT_DROP,
    EVENT_EXPLORE_END,
    EVENT_FUSE,
    build_yesterday_report,
    claim_daily_task_reward,
    claim_pending_research_rewards,
    get_day_key,
    get_or_create_daily_task,
    mark_daily_research_modal_viewed,
    should_show_daily_research_modal,
)


class DailyResearchTests(unittest.TestCase):
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
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("daily_research_user",)).fetchone()["id"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def test_daily_task_is_created_once_and_progress_completes(self):
        today_key = get_day_key()
        with game_app.app.app_context():
            db = game_app.get_db()
            first = get_or_create_daily_task(db, self.user_id, today_key)
            second = get_or_create_daily_task(db, self.user_id, today_key)
            self.assertEqual(int(first["id"]), int(second["id"]))
            self.assertEqual(first["task_key"], "explore_3")

            for _ in range(3):
                audit_log(db, EVENT_EXPLORE_END, user_id=self.user_id, payload={"test": True})

            row = db.execute(
                "SELECT current_count, status FROM daily_research_tasks WHERE id = ?",
                (int(first["id"]),),
            ).fetchone()
            self.assertEqual(int(row["current_count"]), 3)
            self.assertEqual(row["status"], "completed")

            result = claim_daily_task_reward(db, self.user_id, int(first["id"]))
            self.assertTrue(result["ok"])
            after_claim = db.execute(
                "SELECT status FROM daily_research_tasks WHERE id = ?",
                (int(first["id"]),),
            ).fetchone()
            self.assertEqual(after_claim["status"], "claimed")
            coins = int(db.execute("SELECT coins FROM users WHERE id = ?", (self.user_id,)).fetchone()["coins"])
            self.assertEqual(coins, int(first["reward_coins"]))

            audit_log(db, EVENT_EXPLORE_END, user_id=self.user_id, payload={"test": True})
            claimed_row = db.execute(
                "SELECT current_count FROM daily_research_tasks WHERE id = ?",
                (int(first["id"]),),
            ).fetchone()
            self.assertEqual(int(claimed_row["current_count"]), 3)

    def test_tomorrow_reward_is_reserved_and_claimed_once(self):
        today_key = get_day_key()
        tomorrow_key = get_day_key(datetime.now() + timedelta(days=1))
        with game_app.app.app_context():
            db = game_app.get_db()
            for _ in range(5):
                audit_log(db, EVENT_EXPLORE_END, user_id=self.user_id, payload={"test": True})
            rewards = db.execute(
                "SELECT * FROM daily_research_rewards WHERE user_id = ? AND source_day_key = ?",
                (self.user_id, today_key),
            ).fetchall()
            self.assertEqual(len(rewards), 1)
            self.assertEqual(int(rewards[0]["reward_coins"]), 150)

            claimed = claim_pending_research_rewards(db, self.user_id, tomorrow_key)
            self.assertEqual(len(claimed), 1)
            self.assertEqual(int(claimed[0]["reward_coins"]), 150)
            claimed_again = claim_pending_research_rewards(db, self.user_id, tomorrow_key)
            self.assertEqual(claimed_again, [])
            coins = int(db.execute("SELECT coins FROM users WHERE id = ?", (self.user_id,)).fetchone()["coins"])
            self.assertEqual(coins, 150)

    def test_yesterday_report_and_modal_seen(self):
        today_key = get_day_key()
        yesterday = datetime.now() - timedelta(days=1)
        yesterday_key = get_day_key(yesterday)
        start = int(datetime.strptime(yesterday_key, "%Y-%m-%d").replace(tzinfo=timezone(timedelta(hours=9)), hour=12).timestamp())
        with game_app.app.app_context():
            db = game_app.get_db()
            for event_type in [EVENT_EXPLORE_END, EVENT_EXPLORE_END, EVENT_EXPLORE_END, EVENT_DROP, EVENT_FUSE, EVENT_BUILD_CONFIRM, EVENT_BOSS_ENCOUNTER]:
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                    VALUES (?, ?, '{}', ?)
                    """,
                    (start, event_type, self.user_id),
                )
            report = build_yesterday_report(db, self.user_id, today_key)
            self.assertIsNotNone(report)
            self.assertEqual(report["explore_count"], 3)
            self.assertEqual(report["drop_count"], 1)
            self.assertEqual(report["strengthen_count"], 1)
            self.assertEqual(report["build_count"], 1)
            self.assertEqual(report["boss_encounter_count"], 1)

            payload = {"claimed_rewards": [], "yesterday_report": report, "daily_task": None}
            self.assertTrue(should_show_daily_research_modal(db, self.user_id, today_key, payload))
            mark_daily_research_modal_viewed(db, self.user_id, today_key, payload)
            self.assertFalse(should_show_daily_research_modal(db, self.user_id, today_key, payload))


if __name__ == "__main__":
    unittest.main()
