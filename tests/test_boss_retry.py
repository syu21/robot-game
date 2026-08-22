import json
import os
import tempfile
import time
import unittest
from unittest import mock

import app as game_app
import init_db


class BossRetryTests(unittest.TestCase):
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
                VALUES ('boss_retry_user', 'x', ?, 0, 0, 0, 1)
                """,
                (now,),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = 'boss_retry_user'").fetchone()["id"])
            self._create_active_robot(db, self.user_id, now)
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
            sess["username"] = "boss_retry_user"
        return client

    def _create_active_robot(self, db, user_id, now):
        db.execute(
            """
            INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
            VALUES (?, 'RetryBot', 'active', ?, ?)
            """,
            (int(user_id), int(now), int(now)),
        )
        robot_id = int(db.execute("SELECT id FROM robot_instances WHERE user_id = ?", (int(user_id),)).fetchone()["id"])

        def pick_key(part_type):
            row = db.execute(
                "SELECT key FROM robot_parts WHERE part_type = ? AND is_active = 1 ORDER BY id ASC LIMIT 1",
                (part_type,),
            ).fetchone()
            self.assertIsNotNone(row)
            return row["key"]

        db.execute(
            """
            INSERT INTO robot_instance_parts (robot_instance_id, head_key, r_arm_key, l_arm_key, legs_key)
            VALUES (?, ?, ?, ?, ?)
            """,
            (robot_id, pick_key("HEAD"), pick_key("RIGHT_ARM"), pick_key("LEFT_ARM"), pick_key("LEGS")),
        )
        db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (robot_id, int(user_id)))
        return robot_id

    def _event(self, db, event_type, payload, created_at=None):
        db.execute(
            """
            INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
            VALUES (?, ?, ?, ?)
            """,
            (
                int(created_at or time.time()),
                event_type,
                json.dumps(payload, ensure_ascii=False),
                self.user_id,
            ),
        )

    def test_state_starts_on_layer1_boss_encounter_and_is_idempotent(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            boss_key = game_app.LAYER_BOSS_KEY_BY_LAYER[1]
            first = game_app._boss_retry_mark_encounter(db, self.user_id, boss_key=boss_key, now_ts=now)
            second = game_app._boss_retry_mark_encounter(db, self.user_id, boss_key=boss_key, now_ts=now + 10)
            row = db.execute(
                "SELECT retry_status, retry_first_encountered_at, retry_last_encountered_at, retry_attempt_count FROM user_boss_progress WHERE user_id = ? AND area_key = 'layer_1'",
                (self.user_id,),
            ).fetchone()
            self.assertTrue(first["available"])
            self.assertTrue(second["available"])
            self.assertEqual(row["retry_status"], "available")
            self.assertEqual(int(row["retry_first_encountered_at"]), now)
            self.assertEqual(int(row["retry_last_encountered_at"]), now + 10)
            self.assertEqual(int(row["retry_attempt_count"]), 1)

    def test_defeated_state_does_not_return_to_available(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            boss_key = game_app.LAYER_BOSS_KEY_BY_LAYER[1]
            game_app._boss_retry_mark_encounter(db, self.user_id, boss_key=boss_key, now_ts=100)
            game_app._boss_retry_mark_defeated(db, self.user_id, boss_key=boss_key, now_ts=200)
            state = game_app._boss_retry_mark_encounter(db, self.user_id, boss_key=boss_key, now_ts=300)
            self.assertFalse(state["available"])
            self.assertEqual(state["status"], "defeated")

    def test_attempt_count_is_idempotent_per_submission(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            boss_key = game_app.LAYER_BOSS_KEY_BY_LAYER[1]
            game_app._boss_retry_mark_encounter(db, self.user_id, boss_key=boss_key, now_ts=100)
            first = game_app._boss_retry_mark_attempt(db, self.user_id, submission_id="same", now_ts=110)
            second = game_app._boss_retry_mark_attempt(db, self.user_id, submission_id="same", now_ts=120)
            third = game_app._boss_retry_mark_attempt(db, self.user_id, submission_id="next", now_ts=130)
            self.assertEqual(first["attempt_count"], 2)
            self.assertEqual(second["attempt_count"], 2)
            self.assertEqual(third["attempt_count"], 3)

    def test_retry_route_rejects_unencountered_user(self):
        client = self._client()
        res = client.post(
            "/boss/retry/layer-1",
            data={"area_key": "layer_1", "entry_source": "boss_retry", "boss_enter": "1"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertIn("/home", res.headers["Location"])

    def test_retry_route_accepts_available_state_and_preserves_post(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app._boss_retry_mark_encounter(
                db,
                self.user_id,
                boss_key=game_app.LAYER_BOSS_KEY_BY_LAYER[1],
                now_ts=int(time.time()),
            )
            db.commit()
        client = self._client()
        with mock.patch.object(game_app, "_enforce_explore_cooldown_or_wait", return_value=0):
            res = client.post(
                "/boss/retry/layer-1",
                data={
                    "area_key": "layer_1",
                    "entry_source": "boss_retry",
                    "boss_enter": "1",
                    "explore_submission_id": "retry-1",
                },
            )
        self.assertEqual(res.status_code, 307)
        self.assertIn("/explore", res.headers["Location"])

    def test_home_next_action_prioritizes_boss_retry(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            self._event(db, game_app.AUDIT_EVENT_TYPES["EXPLORE_START"], {"area_key": "layer_1"}, created_at=now - 120)
            game_app._boss_retry_mark_encounter(
                db,
                self.user_id,
                boss_key=game_app.LAYER_BOSS_KEY_BY_LAYER[1],
                now_ts=now - 60,
            )
            db.commit()
        client = self._client()
        with mock.patch.object(game_app, "_enforce_explore_cooldown_or_wait", return_value=0):
            res = client.get("/home")
        body = res.get_data(as_text=True)
        self.assertIn("機体を調整して第1層ボスへ", body)
        self.assertIn("ボスへ再挑戦", body)
        self.assertIn("機体を調整する", body)

    def test_failure_reason_categories(self):
        accuracy = game_app._boss_retry_failure_reason(
            [{"actor": "player", "enemy_damage": 0, "note": "MISS"}, {"actor": "player", "enemy_damage": 0, "note": "MISS"}],
            player_hp=5,
            player_max_hp=10,
            timeout=False,
        )
        durability = game_app._boss_retry_failure_reason(
            [{"actor": "player", "enemy_damage": 3}],
            player_hp=0,
            player_max_hp=10,
            timeout=False,
        )
        damage = game_app._boss_retry_failure_reason(
            [{"actor": "player", "enemy_damage": 1}],
            player_hp=4,
            player_max_hp=10,
            timeout=True,
        )
        self.assertEqual(accuracy, "low_accuracy")
        self.assertEqual(durability, "low_durability")
        self.assertEqual(damage, "low_damage")

    def test_metrics_separate_initial_encounter_from_direct_retry(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time()) - 90000
            boss_key = game_app.LAYER_BOSS_KEY_BY_LAYER[1]
            self._event(
                db,
                game_app.AUDIT_EVENT_TYPES["BOSS_ENCOUNTER"],
                {"area_key": "layer_1", "boss_key": boss_key, "boss_source": "normal", "retry_available": True},
                created_at=now,
            )
            self._event(
                db,
                game_app.AUDIT_EVENT_TYPES["BOSS_ENCOUNTER"],
                {"area_key": "layer_1", "boss_key": boss_key, "boss_source": "guaranteed_retry"},
                created_at=now + 100,
            )
            self._event(
                db,
                game_app.AUDIT_EVENT_TYPES["BOSS_RETRY_CTA_VIEW"],
                {"area_key": "layer_1", "boss_key": boss_key},
                created_at=now + 110,
            )
            self._event(
                db,
                game_app.AUDIT_EVENT_TYPES["BOSS_RETRY_CTA_CLICK"],
                {"area_key": "layer_1", "boss_key": boss_key},
                created_at=now + 120,
            )
            self._event(
                db,
                game_app.AUDIT_EVENT_TYPES["EXPLORE_START"],
                {"area_key": "layer_1", "entry_source": "boss_retry"},
                created_at=now + 130,
            )
            self._event(
                db,
                game_app.AUDIT_EVENT_TYPES["BOSS_RETRY_RESULT"],
                {"area_key": "layer_1", "boss_key": boss_key, "defeated": True},
                created_at=now + 200,
            )
            self._event(
                db,
                game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                {"area_key": "layer_1", "boss_key": boss_key},
                created_at=now + 200,
            )
            db.commit()
            snapshot = game_app._admin_first_experience_snapshot(db, window_days=7)
        self.assertEqual(snapshot["layer1_boss"]["encounter_count"], 1)
        self.assertEqual(snapshot["layer1_boss_retry"]["available_users"], 1)
        self.assertEqual(snapshot["layer1_boss_retry"]["cta_click_users"], 1)
        self.assertEqual(snapshot["layer1_boss_retry"]["executed_users"], 1)
        self.assertEqual(snapshot["layer1_boss_retry"]["retry_defeat_users"], 1)
