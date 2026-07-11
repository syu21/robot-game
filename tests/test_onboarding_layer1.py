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


if __name__ == "__main__":
    unittest.main()
