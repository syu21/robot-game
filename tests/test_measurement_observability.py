import json
import os
import tempfile
import time
import unittest

from werkzeug.security import generate_password_hash

import app as game_app
import init_db


class MeasurementObservabilityTests(unittest.TestCase):
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

    def _create_user(self, db, username, *, created_at=None, is_admin=0):
        now = int(created_at or time.time())
        db.execute(
            """
            INSERT INTO users (username, password_hash, created_at, last_seen_at, is_admin)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username, generate_password_hash("pw"), now, now, int(is_admin)),
        )
        return int(db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"])

    def _insert_event(self, db, user_id, event_type, *, created_at=None, payload=None, request_id=None):
        db.execute(
            """
            INSERT INTO world_events_log (created_at, event_type, payload_json, user_id, request_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                int(created_at or time.time()),
                str(event_type),
                json.dumps(payload or {}, ensure_ascii=False),
                int(user_id),
                request_id,
            ),
        )

    def _login(self, client, user_id, username):
        with client.session_transaction() as sess:
            sess["user_id"] = int(user_id)
            sess["username"] = username

    def test_common_onboarding_funnel_uses_same_second_third_counts(self):
        now = int(time.time())
        with game_app.app.app_context():
            db = game_app.get_db()
            user_id = self._create_user(db, "funnel_consistent", created_at=now)
            events = [
                (game_app.AUDIT_EVENT_TYPES["HOME_VIEW"], 1, {}),
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_START"], 2, {"area_key": "layer_1", "entry_source": "next_action_first_explore"}),
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], 3, {"area_key": "layer_1", "result": {"win": True}}),
                (game_app.AUDIT_EVENT_TYPES["BATTLE_RESULT_VIEW"], 4, {"area_key": "layer_1"}),
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_START"], 5, {"area_key": "layer_1", "entry_source": "battle_retry"}),
                (game_app.AUDIT_EVENT_TYPES["ONBOARDING_EXPLORE_SECOND_START"], 6, {"area_key": "layer_1"}),
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_START"], 7, {"area_key": "layer_1", "entry_source": "battle_retry"}),
                (game_app.AUDIT_EVENT_TYPES["ONBOARDING_EXPLORE_THIRD_START"], 8, {"area_key": "layer_1"}),
                (game_app.AUDIT_EVENT_TYPES["ONBOARDING_FIRST_THREE_COMPLETE"], 9, {"area_key": "layer_1"}),
            ]
            for event_type, offset, payload in events:
                self._insert_event(db, user_id, event_type, created_at=now + offset, payload=payload, request_id=f"req-{offset}")
            db.commit()

            snapshot = game_app.build_new_user_onboarding_funnel(db, window_days=7)

        by_key = {row["key"]: row for row in snapshot["rows"]}
        self.assertEqual(snapshot["second_start"]["numerator"], by_key["second_start"]["count"])
        self.assertEqual(snapshot["third_start"]["numerator"], by_key["third_start"]["count"])
        self.assertEqual(snapshot["first_three_complete"]["numerator"], by_key["first_three_complete"]["count"])

    def test_daily_metrics_audit_recalc_matches_explore_end(self):
        now = int(time.time())
        day_key = game_app.datetime.fromtimestamp(now, game_app.JST).strftime("%Y-%m-%d")
        with game_app.app.app_context():
            db = game_app.get_db()
            user_id = self._create_user(db, "daily_audit_match", created_at=now)
            self._insert_event(
                db,
                user_id,
                game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                created_at=now,
                payload={"area_key": "layer_1", "result": {"win": True}},
                request_id="req-end",
            )
            db.commit()
            daily = game_app._collect_daily_metrics(db, day_key)
            audit_count = game_app._audit_explore_count_for_day(db, day_key)

        self.assertEqual(daily["explore_count"], 1)
        self.assertEqual(audit_count, 1)

    def test_initial_home_records_ready_and_cta_view(self):
        with game_app.app.test_client() as client:
            response = client.post(
                "/register",
                data={"username": "home_ready_user", "password": "pass123"},
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT id FROM users WHERE username = ?", ("home_ready_user",)).fetchone()
            rows = db.execute(
                "SELECT event_type, payload_json FROM world_events_log WHERE user_id = ? ORDER BY id ASC",
                (int(user["id"]),),
            ).fetchall()
        event_types = [row["event_type"] for row in rows]
        self.assertIn(game_app.AUDIT_EVENT_TYPES["ONBOARDING_HOME_READY"], event_types)
        self.assertIn(game_app.AUDIT_EVENT_TYPES["ONBOARDING_FIRST_EXPLORE_CTA_VIEW"], event_types)

    def test_validation_failure_records_explore_failed_not_end(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            user_id = self._create_user(db, "failed_explore_user")
            db.commit()
        with game_app.app.test_client() as client:
            self._login(client, user_id, "failed_explore_user")
            response = client.post("/explore", data={"area_key": "missing_area"}, follow_redirects=False)
            self.assertEqual(response.status_code, 302)

        with game_app.app.app_context():
            db = game_app.get_db()
            failed = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (int(user_id), game_app.AUDIT_EVENT_TYPES["EXPLORE_FAILED"]),
            ).fetchone()
            end_count = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (int(user_id), game_app.AUDIT_EVENT_TYPES["EXPLORE_END"]),
            ).fetchone()["c"]
        self.assertIsNotNone(failed)
        self.assertEqual(int(end_count), 0)
        self.assertEqual(json.loads(failed["payload_json"])["reason"], "validation")


if __name__ == "__main__":
    unittest.main()
