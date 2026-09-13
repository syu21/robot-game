import json
import os
import tempfile
import time
import unittest

from werkzeug.security import generate_password_hash

import app as game_app
import init_db


class DailyEventMetricsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        init_db.main()
        game_app.app.config["TESTING"] = True

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _create_user(self, db, username, *, created_at, is_admin=0, analytics_excluded=0):
        db.execute(
            """
            INSERT INTO users (username, password_hash, created_at, last_seen_at, is_admin, analytics_excluded)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (username, generate_password_hash("pw"), int(created_at), int(created_at), int(is_admin), int(analytics_excluded)),
        )
        return int(db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"])

    def _insert_event(self, db, user_id, event_type, *, created_at, payload=None):
        db.execute(
            """
            INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
            VALUES (?, ?, ?, ?)
            """,
            (int(created_at), str(event_type), json.dumps(payload or {}, ensure_ascii=False), int(user_id)),
        )

    def test_integer_created_at_cutoff_and_daily_aggregate_match_raw(self):
        day_key = "2026-09-12"
        start_ts, end_ts = game_app._jst_day_key_to_bounds(day_key)
        with game_app.app.app_context():
            db = game_app.get_db()
            user_id = self._create_user(db, "metric_user", created_at=start_ts)
            self._insert_event(db, user_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], created_at=start_ts - 1)
            self._insert_event(db, user_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], created_at=start_ts)
            self._insert_event(db, user_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], created_at=end_ts - 1)
            self._insert_event(db, user_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], created_at=end_ts)
            db.commit()

            daily = game_app._collect_daily_metrics(db, day_key)
            raw = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM world_events_log
                WHERE event_type = ?
                  AND created_at >= ?
                  AND created_at < ?
                """,
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], int(start_ts), int(end_ts)),
            ).fetchone()["c"]

        self.assertEqual(int(raw), 2)
        self.assertEqual(daily["explore_count"], 2)

    def test_daily_event_metrics_keep_analytics_exclusions(self):
        day_key = "2026-09-12"
        start_ts, _ = game_app._jst_day_key_to_bounds(day_key)
        with game_app.app.app_context():
            db = game_app.get_db()
            normal_id = self._create_user(db, "real_metric_user", created_at=start_ts)
            admin_id = self._create_user(db, "admin_metric_user", created_at=start_ts, is_admin=1)
            excluded_id = self._create_user(db, "excluded_metric_user", created_at=start_ts, analytics_excluded=1)
            test_id = self._create_user(db, "test_metric_user", created_at=start_ts)
            for uid in (normal_id, admin_id, excluded_id, test_id):
                self._insert_event(db, uid, game_app.AUDIT_EVENT_TYPES["EXPLORE_START"], created_at=start_ts + 10)
                self._insert_event(db, uid, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], created_at=start_ts + 20)
            db.commit()

            daily = game_app._collect_daily_metrics(db, day_key)
            start_count = game_app._daily_event_metric_count(db, day_key, game_app.AUDIT_EVENT_TYPES["EXPLORE_START"])

        self.assertEqual(daily["dau_count"], 1)
        self.assertEqual(daily["new_users"], 1)
        self.assertEqual(daily["explore_count"], 1)
        self.assertEqual(start_count, 1)

    def test_measurement_health_uses_historical_daily_event_metrics(self):
        day_key = "2026-09-12"
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                INSERT INTO daily_event_metrics (day_key, event_type, event_count, user_count, updated_at)
                VALUES (?, ?, 3, 2, ?)
                """,
                (day_key, game_app.AUDIT_EVENT_TYPES["EXPLORE_START"], int(time.time())),
            )
            db.execute(
                """
                INSERT INTO daily_event_metrics (day_key, event_type, event_count, user_count, updated_at)
                VALUES (?, ?, 2, 2, ?)
                """,
                (day_key, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], int(time.time())),
            )
            db.commit()
            snapshot = game_app._measurement_health_snapshot(db, rows=[{"day_key": day_key, "explore_count": 2}], window_days=3)

        self.assertGreaterEqual(snapshot["start_count"], 3)
        self.assertGreaterEqual(snapshot["end_count"], 2)

    def test_admin_behavior_events_can_read_daily_user_aggregate(self):
        day_key = "2026-09-13"
        start_ts, _ = game_app._jst_day_key_to_bounds(day_key)
        with game_app.app.app_context():
            db = game_app.get_db()
            user_id = self._create_user(db, "aggregate_funnel_user", created_at=start_ts)
            self._insert_event(db, user_id, game_app.AUDIT_EVENT_TYPES["HOME_VIEW"], created_at=start_ts + 1)
            self._insert_event(db, user_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_START"], created_at=start_ts + 2)
            self._insert_event(db, user_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], created_at=start_ts + 3)
            db.commit()
            game_app._collect_daily_metrics(db, day_key)
            db.execute("DELETE FROM world_events_log")
            db.commit()

            events = game_app._admin_behavior_events(db, start_ts)

        self.assertEqual(
            [event["step_key"] for event in events if event["user_id"] == user_id],
            ["home_view", "explore_start", "explore_end"],
        )


if __name__ == "__main__":
    unittest.main()
