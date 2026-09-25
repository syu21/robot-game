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
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], 6, {"area_key": "layer_1", "result": {"win": True}}),
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_START"], 7, {"area_key": "layer_1", "entry_source": "battle_retry"}),
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], 8, {"area_key": "layer_1", "result": {"win": True}}),
            ]
            for event_type, offset, payload in events:
                self._insert_event(db, user_id, event_type, created_at=now + offset, payload=payload, request_id=f"req-{offset}")
            db.commit()

            snapshot = game_app.build_new_user_onboarding_funnel(db, window_days=7)

        by_key = {row["key"]: row for row in snapshot["rows"]}
        self.assertEqual(snapshot["second_start"]["numerator"], by_key["second_start"]["count"])
        self.assertEqual(snapshot["third_start"]["numerator"], by_key["third_start"]["count"])
        self.assertEqual(snapshot["first_three_complete"]["numerator"], by_key["first_three_complete"]["count"])

    def test_completed_sortie_index_ignores_failed_and_is_per_user(self):
        events_a = [
            {"id": 1, "event_type": game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], "created_at": 10},
            {"id": 2, "event_type": game_app.AUDIT_EVENT_TYPES["EXPLORE_FAILED"], "created_at": 20},
            {"id": 3, "event_type": game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], "created_at": 30},
            {"id": 4, "event_type": game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], "created_at": 40},
        ]
        events_b = [{"id": 5, "event_type": game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], "created_at": 25}]

        sorties_a = game_app._completed_sortie_events(events_a)
        sorties_b = game_app._completed_sortie_events(events_b)

        self.assertEqual([row["sortie_index"] for row in sorties_a], [1, 2, 3])
        self.assertEqual([row["onboarding_phase"] for row in sorties_a], ["first_3_sorties"] * 3)
        self.assertEqual([row["sortie_index"] for row in sorties_b], [1])

    def test_first_three_funnel_uses_completed_sorties_for_six_five_four_users(self):
        now = int(time.time())
        with game_app.app.app_context():
            db = game_app.get_db()
            for index in range(8):
                user_id = self._create_user(db, f"cohort_user_{index}", created_at=now - 60)
                self._insert_event(db, user_id, game_app.AUDIT_EVENT_TYPES["HOME_VIEW"], created_at=now - 50)
                completed = 3 if index < 4 else (2 if index < 5 else (1 if index < 6 else 0))
                for sortie_index in range(completed):
                    ts = now - 40 + sortie_index * 2
                    self._insert_event(
                        db,
                        user_id,
                        game_app.AUDIT_EVENT_TYPES["EXPLORE_START"],
                        created_at=ts,
                        payload={"area_key": "layer_1", "entry_source": "area_select"},
                        request_id=f"start-{index}-{sortie_index}",
                    )
                    self._insert_event(
                        db,
                        user_id,
                        game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                        created_at=ts + 1,
                        payload={"area_key": "layer_1", "result": {"win": True}},
                        request_id=f"start-{index}-{sortie_index}",
                    )
            db.commit()
            snapshot = game_app.build_new_user_onboarding_funnel(db, window_days=7)

        self.assertEqual(snapshot["registered_count"], 8)
        rows = {row["key"]: row for row in snapshot["rows"]}
        self.assertEqual(rows["layer1_first_complete"]["count"], 6)
        self.assertEqual(rows["second_start"]["count"], 5)
        self.assertEqual(rows["third_start"]["count"], 4)
        self.assertEqual(snapshot["first_three_complete"]["numerator"], 4)

    def test_first_adjustment_uses_player_build_confirm_and_post_adjustment_completion(self):
        now = int(time.time())
        with game_app.app.app_context():
            db = game_app.get_db()
            user_id = self._create_user(db, "adjustment_metric_user", created_at=now - 100)
            sequence = [
                (game_app.AUDIT_EVENT_TYPES["HOME_VIEW"], 1, {}),
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_START"], 2, {"area_key": "layer_1"}),
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], 3, {"area_key": "layer_1"}),
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], 4, {"area_key": "layer_1"}),
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], 5, {"area_key": "layer_1"}),
                (game_app.AUDIT_EVENT_TYPES["BUILD_CONFIRM"], 6, {"source": "player_build_confirm"}),
                (game_app.AUDIT_EVENT_TYPES["ONBOARDING_FIRST_UPGRADE_COMPLETE"], 7, {"source": "build_confirm"}),
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_START"], 8, {"area_key": "layer_1", "entry_source": "onboarding_post_adjustment"}),
            ]
            for event_type, offset, payload in sequence:
                self._insert_event(db, user_id, event_type, created_at=now - 100 + offset, payload=payload)
            db.commit()
            snapshot = game_app.build_new_user_onboarding_funnel(db, window_days=7)

        self.assertEqual(snapshot["first_upgrade"]["complete_users"], 1)
        self.assertEqual(snapshot["first_upgrade"]["after_explore_users"], 1)

    def test_revisit_denominators_exclude_users_before_judgment_day(self):
        now = int(time.time())
        old_created = now - 4 * 86400
        with game_app.app.app_context():
            db = game_app.get_db()
            old_user = self._create_user(db, "revisit_old_user", created_at=old_created)
            self._create_user(db, "revisit_new_user", created_at=now)
            self._insert_event(
                db,
                old_user,
                game_app.AUDIT_EVENT_TYPES["HOME_VIEW"],
                created_at=old_created + 3 * 86400,
            )
            db.commit()
            snapshot = game_app.build_new_user_onboarding_funnel(db, window_days=7)

        self.assertEqual(snapshot["d1"]["eligible"], 1)
        self.assertEqual(snapshot["d3"]["eligible"], 1)
        self.assertEqual(snapshot["d3"]["returned"], 1)

    def test_entry_source_allowlist_covers_normal_explore_routes(self):
        sources = {
            "next_action_first_explore",
            "battle_retry",
            "next_action",
            "previous_area",
            "layer1_primary_cta",
            "area_select",
            "boss_retry",
            "boss_recovery_normal",
            "layer2_unlock_result",
            "layer2_unlock_home",
            "first_robot_upgrade_result",
            "layer1_boss_signal",
            "layer1_boss_alert",
            "layer1_boss_guarantee",
        }
        self.assertEqual({game_app._normalize_entry_source(source) for source in sources}, sources)

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

    def test_measurement_health_classifies_request_lifecycle_and_sortie_indexes(self):
        now = int(time.time())
        with game_app.app.app_context():
            db = game_app.get_db()
            user_id = self._create_user(db, "health_lifecycle_user", created_at=now - 60)
            events = [
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_START"], "req-success", {}),
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], "req-success", {"sortie_index": 1}),
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_START"], "req-failed", {}),
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_FAILED"], "req-failed", {"reason": "exception"}),
                (game_app.AUDIT_EVENT_TYPES["EXPLORE_START"], "req-unmatched", {}),
            ]
            for offset, (event_type, request_id, payload) in enumerate(events, start=1):
                self._insert_event(
                    db,
                    user_id,
                    event_type,
                    created_at=now - 50 + offset,
                    payload=payload,
                    request_id=request_id,
                )
            db.commit()
            snapshot = game_app._measurement_health_snapshot(db, rows=[], window_days=7)

        self.assertEqual(snapshot["success_request_count"], 1)
        self.assertEqual(snapshot["failed_request_count"], 1)
        self.assertEqual(snapshot["unmatched_request_count"], 1)
        self.assertEqual(snapshot["sortie_index_missing_count"], 0)
        self.assertEqual(snapshot["sortie_index_duplicate_count"], 0)


if __name__ == "__main__":
    unittest.main()
