import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

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
        day_key = (game_app.datetime.now(game_app.JST).date() - game_app.timedelta(days=1)).strftime("%Y-%m-%d")
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

    def test_section_profiler_disabled_does_not_log(self):
        old_home_enabled = game_app.HOME_SECTION_LOG_ENABLED
        old_perf_diagnostics = game_app.PERF_DIAGNOSTICS
        game_app.HOME_SECTION_LOG_ENABLED = False
        game_app.PERF_DIAGNOSTICS = False
        try:
            with patch.dict(os.environ, {"HOME_SECTION_PROFILE": "", "SECTION_PROFILE": ""}, clear=False):
                with game_app.app.test_request_context("/home"):
                    with patch.object(game_app.app.logger, "info") as info_log:
                        elapsed = game_app._home_section_log("unit", time.perf_counter())
            self.assertGreaterEqual(elapsed, 0)
            info_log.assert_not_called()
        finally:
            game_app.HOME_SECTION_LOG_ENABLED = old_home_enabled
            game_app.PERF_DIAGNOSTICS = old_perf_diagnostics

    def test_section_profiler_enabled_logs_request_id_without_changing_result(self):
        old_home_enabled = game_app.HOME_SECTION_LOG_ENABLED
        old_perf_diagnostics = game_app.PERF_DIAGNOSTICS
        game_app.HOME_SECTION_LOG_ENABLED = False
        game_app.PERF_DIAGNOSTICS = False
        try:
            with patch.dict(os.environ, {"HOME_SECTION_PROFILE": "1"}, clear=False):
                with game_app.app.test_request_context("/home"):
                    game_app.g.request_id = "req-profiler-test"
                    game_app.session["user_id"] = 42
                    with patch.object(game_app.app.logger, "warning") as warning_log:
                        elapsed = game_app._home_section_log("unit", time.perf_counter())
            self.assertGreaterEqual(elapsed, 0)
            self.assertEqual(warning_log.call_count, 1)
            log_args = warning_log.call_args.args
            self.assertIn("perf.%s.section", log_args[0])
            self.assertIn("home", log_args)
            self.assertIn("unit", log_args)
            self.assertIn("req-profiler-test", log_args)
        finally:
            game_app.HOME_SECTION_LOG_ENABLED = old_home_enabled
            game_app.PERF_DIAGNOSTICS = old_perf_diagnostics

    def test_slow_sql_profiler_does_not_log_parameter_values(self):
        old_perf_diagnostics = game_app.PERF_DIAGNOSTICS
        old_sql_profile_enabled = game_app.SQL_SLOW_PROFILE_ENABLED
        old_sql_profile_ms = game_app.SQL_SLOW_PROFILE_MS
        game_app.PERF_DIAGNOSTICS = False
        game_app.SQL_SLOW_PROFILE_ENABLED = True
        game_app.SQL_SLOW_PROFILE_MS = 0
        try:
            with game_app.app.test_request_context("/home"):
                game_app.g.request_id = "req-sql-profiler-test"
                with patch.object(game_app.app.logger, "warning") as warning_log:
                    db = game_app.get_db()
                    db.execute("SELECT ? AS token", ("super-secret-token",)).fetchone()
            self.assertGreaterEqual(warning_log.call_count, 1)
            rendered_logs = [
                (call.args[0] % call.args[1:]) if len(call.args) > 1 else str(call.args[0])
                for call in warning_log.call_args_list
            ]
            slow_sql_logs = [
                line
                for line in rendered_logs
                if "perf.sql.slow" in line and "SELECT ? AS token" in line
            ]
            self.assertTrue(slow_sql_logs)
            self.assertIn("parameter_count=1", slow_sql_logs[0])
            self.assertIn("req-sql-profiler-test", slow_sql_logs[0])
            self.assertNotIn("super-secret-token", "\n".join(slow_sql_logs))
        finally:
            game_app.PERF_DIAGNOSTICS = old_perf_diagnostics
            game_app.SQL_SLOW_PROFILE_ENABLED = old_sql_profile_enabled
            game_app.SQL_SLOW_PROFILE_MS = old_sql_profile_ms

    def test_core_drop_observability_uses_days_window_for_sample(self):
        now = int(time.time())
        with game_app.app.app_context():
            db = game_app.get_db()
            user_id = self._create_user(db, "core_window_user", created_at=now - 30 * 86400)
            self._insert_event(
                db,
                user_id,
                game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                created_at=now - 60,
                payload={"result": {"win": True, "battle_count": 2}, "rewards": {"cores": 1}},
            )
            self._insert_event(
                db,
                user_id,
                game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                created_at=now - 120,
                payload={"result": {"win": False, "battle_count": 3}, "rewards": {"cores": 0}},
            )
            self._insert_event(
                db,
                user_id,
                game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                created_at=now - 30 * 86400,
                payload={"result": {"win": True, "battle_count": 7}, "rewards": {"cores": 9}},
            )
            db.commit()

            snapshot = game_app._core_drop_observability(db, sample_size=50, days=14, user_day_limit=20)

        self.assertEqual(snapshot["sample_size"], 50)
        self.assertEqual(snapshot["days"], 14)
        self.assertEqual(snapshot["explores"], 2)
        self.assertEqual(snapshot["wins"], 1)
        self.assertEqual(snapshot["battles_total"], 5)
        self.assertEqual(snapshot["core_total"], 1)

    def test_explore_battle_id_lookup_uses_result_cache(self):
        now = int(time.time())
        with game_app.app.app_context():
            db = game_app.get_db()
            user_id = self._create_user(db, "battle_cache_user", created_at=now)
            battle_id = "battle-cache-test"
            db.execute(
                """
                INSERT INTO battle_result_cache (id, user_id, area_key, area_label, summary_json, created_at)
                VALUES (?, ?, 'layer_1', '第1層', ?, ?)
                """,
                (battle_id, user_id, json.dumps({"battle_id": battle_id}, ensure_ascii=False), now),
            )
            db.commit()

            row = game_app._explore_end_row_for_battle_id(db, user_id, battle_id)

        self.assertIsNotNone(row)
        self.assertEqual(row["id"], battle_id)

    def test_robot_history_progress_request_lookup_has_composite_index(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            index_names = {
                row["name"]
                for row in db.execute("PRAGMA index_list('world_events_log')").fetchall()
            }
            plan_rows = db.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT 1
                FROM world_events_log
                WHERE event_type = 'audit.robot.history.progress'
                  AND user_id = ?
                  AND request_id = ?
                LIMIT 1
                """,
                (1, "battle-index-test"),
            ).fetchall()

        self.assertIn("idx_world_events_event_user_request", index_names)
        self.assertTrue(any("idx_world_events_event_user_request" in str(row[3]) for row in plan_rows))


if __name__ == "__main__":
    unittest.main()
