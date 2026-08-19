import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FixedRng:
    def __init__(self, value=1.0):
        self.value = float(value)

    def random(self):
        return self.value


class Layer1OnboardingTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer, coins)
                VALUES (?, 'x', ?, 0, 0, 1, 0)
                """,
                ("onboarding_layer1", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("onboarding_layer1",)).fetchone()["id"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _db(self):
        return game_app.get_db()

    def _user(self):
        return self._db().execute("SELECT * FROM users WHERE id = ?", (self.user_id,)).fetchone()

    def _event(self, event_type, payload=None, user_id=None):
        db = self._db()
        db.execute(
            """
            INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
            VALUES (?, ?, ?, ?)
            """,
            (
                int(time.time()),
                event_type,
                json.dumps(payload or {}, ensure_ascii=False),
                int(user_id or self.user_id),
            ),
        )
        db.commit()

    def _enable_boss_retry(self):
        db = self._db()
        game_app.initialize_new_user(db, self.user_id)
        now = int(time.time())
        game_app._boss_retry_mark_encounter(
            db,
            self.user_id,
            boss_key=game_app._layer1_boss_retry_boss_key(),
            now_ts=now,
        )
        db.commit()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
            sess["username"] = "onboarding_layer1"
        return client

    def test_first_three_reward_is_idempotent(self):
        with game_app.app.app_context():
            for i in range(3):
                self._event(game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], {"area_key": "layer_1", "result": {"win": True, "i": i}})
            first = game_app._grant_onboarding_first_three_reward_if_ready(self._db(), self._user(), area_key="layer_1")
            second = game_app._grant_onboarding_first_three_reward_if_ready(self._db(), self._user(), area_key="layer_1")
            row = self._db().execute("SELECT coins, onboarding_first_three_reward_claimed FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertTrue(first["granted"])
            self.assertFalse(second["granted"])
            self.assertEqual(int(row["coins"]), 100)
            self.assertEqual(int(row["onboarding_first_three_reward_claimed"]), 1)

    def test_admin_and_analytics_excluded_are_not_targets(self):
        with game_app.app.app_context():
            db = self._db()
            db.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (self.user_id,))
            db.commit()
            self.assertIsNone(game_app._onboarding_first_three_progress_view(db, self._user()))
            self.assertIsNone(game_app._layer1_boss_alert_view(db, self._user()))
            db.execute("UPDATE users SET is_admin = 0, analytics_excluded = 1 WHERE id = ?", (self.user_id,))
            db.commit()
            self.assertIsNone(game_app._onboarding_first_three_progress_view(db, self._user()))
            self.assertIsNone(game_app._layer1_boss_alert_view(db, self._user()))

    def test_layer1_boss_alert_progress_and_ready(self):
        with game_app.app.app_context():
            db = self._db()
            for _ in range(9):
                game_app._advance_layer1_boss_alert_after_normal_win(
                    db,
                    self._user(),
                    area_key="layer_1",
                    is_boss=False,
                    final_outcome="win",
                )
            view = game_app._layer1_boss_alert_view(db, self._user())
            self.assertEqual(view["progress"], 9)
            self.assertFalse(view["ready"])
            game_app._advance_layer1_boss_alert_after_normal_win(
                db,
                self._user(),
                area_key="layer_1",
                is_boss=False,
                final_outcome="win",
            )
            view = game_app._layer1_boss_alert_view(db, self._user())
            self.assertTrue(view["ready"])
            self.assertIn("ボス警報発令", view["line"])

    def test_layer1_boss_alert_does_not_advance_on_loss_or_other_layer(self):
        with game_app.app.app_context():
            db = self._db()
            game_app._advance_layer1_boss_alert_after_normal_win(db, self._user(), area_key="layer_1", is_boss=False, final_outcome="lose")
            game_app._advance_layer1_boss_alert_after_normal_win(db, self._user(), area_key="layer_2", is_boss=False, final_outcome="win")
            view = game_app._layer1_boss_alert_view(db, self._user())
            self.assertEqual(view["progress"], 0)

    def test_ready_layer1_next_spawn_is_guaranteed_and_resets(self):
        with game_app.app.app_context():
            db = self._db()
            db.execute(
                """
                INSERT INTO user_boss_progress (user_id, area_key, no_boss_streak, updated_at)
                VALUES (?, 'layer_1', ?, ?)
                ON CONFLICT(user_id, area_key) DO UPDATE SET no_boss_streak = excluded.no_boss_streak
                """,
                (self.user_id, game_app.LAYER1_BOSS_ALERT_THRESHOLD, int(time.time())),
            )
            result = game_app._area_boss_spawn_check(db, self.user_id, "layer_1", rng=FixedRng(1.0))
            row = db.execute("SELECT no_boss_streak FROM user_boss_progress WHERE user_id = ? AND area_key = 'layer_1'", (self.user_id,)).fetchone()
            self.assertTrue(result["spawn"])
            self.assertEqual(result["encounter_source"], "alert_guarantee")
            self.assertEqual(int(row["no_boss_streak"]), 0)

    def test_boss_defeat_stops_layer1_alert(self):
        with game_app.app.app_context():
            self._event(game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], {"area_key": "layer_1", "boss_kind": "fixed"})
            db = self._db()
            result = game_app._advance_layer1_boss_alert_after_normal_win(
                db,
                self._user(),
                area_key="layer_1",
                is_boss=False,
                final_outcome="win",
            )
            self.assertIsNone(result)
            self.assertIsNone(game_app._layer1_boss_alert_view(db, self._user()))

    def test_first_win_result_template_has_ct_retry_cta(self):
        with game_app.app.test_request_context("/battle/result"):
            html = game_app.render_template(
                "battle.html",
                state={"active": 0, "enemy_name": "敵", "enemy_hp": 0},
                log=[],
                log_entries=[],
                message=None,
                new_robot=None,
                explore_mode=True,
                explore_area_key="layer_1",
                explore_area_label="第一層",
                active_robot={"name": "ロボ"},
                no_active_robot=False,
                turn_logs=[],
                summary={
                    "outcome": "勝利",
                    "outcome_is_win": True,
                    "layer1_first_win_result": True,
                    "next_action_primary_label": "もう一度、第1層へ出撃",
                    "explore_ct_remain": 12,
                    "explore_ct_ready_at": int(time.time()) + 12,
                    "explore_ct_is_admin": False,
                    "explore_ct_button_label": "もう一度出撃（あと12秒）",
                    "explore_ct_status_label": "CT中: あと12秒",
                    "reward_front": {"coin": 1},
                    "next_explore_submission_id": "x",
                },
                battle_log_mode="collapsed",
                battle_ritual_overlay_enabled=False,
                battle_short_replay_enabled=False,
            )
            self.assertIn("初勝利！", html)
            self.assertIn("もう一度、第1層へ出撃", html)
            self.assertIn("次の出撃まで あと 00:12", html)
            self.assertIn('entry_source" value="battle_retry"', html)

    def test_normal_second_win_template_does_not_show_first_win_copy(self):
        with game_app.app.test_request_context("/battle/result"):
            html = game_app.render_template(
                "battle.html",
                state={"active": 0, "enemy_name": "敵", "enemy_hp": 0},
                log=[],
                log_entries=[],
                message=None,
                new_robot=None,
                explore_mode=True,
                explore_area_key="layer_1",
                explore_area_label="第一層",
                active_robot={"name": "ロボ"},
                no_active_robot=False,
                turn_logs=[],
                summary={
                    "outcome": "勝利",
                    "outcome_is_win": True,
                    "layer1_first_win_result": False,
                    "explore_ct_remain": 0,
                    "explore_ct_ready_at": 0,
                    "explore_ct_is_admin": False,
                    "explore_ct_button_label": "もう一度出撃",
                    "explore_ct_status_label": "出撃可能",
                    "reward_front": {"coin": 1},
                },
                battle_log_mode="collapsed",
                battle_ritual_overlay_enabled=False,
                battle_short_replay_enabled=False,
            )
            self.assertNotIn("初勝利！", html)
            self.assertNotIn("ロボの調査が進みました。", html)

    def test_boss_retry_failure_diagnosis_categories(self):
        self.assertEqual(
            game_app._boss_retry_failure_reason(
                [{"actor": "player", "enemy_damage": 0, "text": "MISS"}, {"actor": "player", "enemy_damage": 0, "text": "MISS"}],
                player_hp=10,
                player_max_hp=30,
                timeout=False,
            ),
            "low_accuracy",
        )
        self.assertEqual(
            game_app._boss_retry_failure_reason([], player_hp=0, player_max_hp=30, timeout=False),
            "low_durability",
        )
        self.assertEqual(
            game_app._boss_retry_failure_reason(
                [{"actor": "player", "enemy_damage": 3}],
                player_hp=12,
                player_max_hp=30,
                timeout=True,
            ),
            "low_damage",
        )

    def test_boss_retry_result_template_prioritizes_adjust_cta(self):
        with game_app.app.test_request_context("/battle/result"):
            html = game_app.render_template(
                "battle.html",
                state={"active": 0, "enemy_name": "敵", "enemy_hp": 1},
                log=[],
                log_entries=[],
                message=None,
                new_robot=None,
                explore_mode=True,
                explore_area_key="layer_1",
                explore_area_label="第一層",
                active_robot={"name": "ロボ"},
                no_active_robot=False,
                turn_logs=[],
                summary={
                    "outcome": "敗北",
                    "outcome_is_win": False,
                    "explore_ct_remain": 0,
                    "explore_ct_ready_at": 0,
                    "explore_ct_is_admin": False,
                    "explore_ct_button_label": "もう一度出撃",
                    "explore_ct_status_label": "出撃可能",
                    "reward_front": {"coin": 0},
                    "next_explore_submission_id": "x",
                    "boss_retry": {
                        "title": "戦闘データを解析しました",
                        "desc": "機体を少し調整すれば、突破できる可能性があります。",
                        "cta_label": "このまま再挑戦",
                        "action_url": game_app.url_for("boss_retry_layer1"),
                        "build_action_url": game_app.url_for("boss_retry_layer1_build"),
                        "diagnosis_key": "accuracy",
                        "failure": game_app._boss_retry_failure_advice("low_accuracy"),
                    },
                },
                battle_log_mode="collapsed",
                battle_ritual_overlay_enabled=False,
                battle_short_replay_enabled=False,
            )
            self.assertIn("戦闘データを解析しました", html)
            self.assertIn("機体を調整する", html)
            self.assertIn("このまま再挑戦", html)
            self.assertIn('name="diagnosis_key" value="accuracy"', html)

    def test_boss_retry_build_route_logs_guide_click(self):
        with game_app.app.app_context():
            self._enable_boss_retry()
        resp = self._client().post(
            "/boss/retry/layer-1/build",
            data={"surface": "battle_result", "diagnosis_key": "accuracy"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/build?", resp.headers["Location"])
        with game_app.app.app_context():
            row = self._db().execute(
                """
                SELECT payload_json
                FROM world_events_log
                WHERE user_id = ? AND event_type = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (self.user_id, game_app.AUDIT_EVENT_TYPES["ONBOARDING_BOSS_RETRY_GUIDE_CLICK"]),
            ).fetchone()
            self.assertIsNotNone(row)
            payload = json.loads(row["payload_json"])
            self.assertEqual(payload["area_key"], "layer_1")
            self.assertEqual(payload["diagnosis_key"], "accuracy")


if __name__ == "__main__":
    unittest.main()
