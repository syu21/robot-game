import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class TutorialLayer1FlowTests(unittest.TestCase):
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
                VALUES (?, ?, ?, 0, 0, 1000, 1)
                """,
                ("tutorial_l1", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("tutorial_l1",),
            ).fetchone()["id"]
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (self.user_id, "FirstRunner", now, now),
            )
            self.robot_id = db.execute(
                "SELECT id FROM robot_instances WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (self.user_id,),
            ).fetchone()["id"]

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
                (
                    self.robot_id,
                    pick_key("HEAD"),
                    pick_key("RIGHT_ARM"),
                    pick_key("LEFT_ARM"),
                    pick_key("LEGS"),
                ),
            )
            db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (self.robot_id, self.user_id))
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    @staticmethod
    def _stable_weekly_env():
        return {
            "element": "NORMAL",
            "mode": "安定",
            "enemy_spawn_bonus": 0.0,
            "drop_bonus": 0.0,
            "reason": "test",
        }

    @staticmethod
    def _resolve_player_win(att_atk, att_acc, att_cri, def_def, def_acc, **kwargs):
        if kwargs.get("attacker_archetype") is not None:
            return 999, False
        return 0, False

    @staticmethod
    def _resolve_player_loss(att_atk, att_acc, att_cri, def_def, def_acc, **kwargs):
        if kwargs.get("attacker_archetype") is not None:
            return 0, False
        return 999, False

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "tutorial_l1"
        return client

    def _explore(self, resolver):
        client = self._client()
        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "_enforce_explore_cooldown_or_wait", return_value=0
        ), patch.object(
            game_app,
            "_area_boss_spawn_check",
            return_value={"spawn": False, "probability": 0.05, "pity_forced": False, "streak_before": 0},
        ), patch.object(game_app, "resolve_attack", side_effect=resolver):
            return client.post("/explore", data={"area_key": "layer_1"})

    def _user_tutorial_row(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            return db.execute(
                """
                SELECT tutorial_layer1_state, tutorial_layer1_normal_win_count,
                       tutorial_layer1_boss_seen_at, tutorial_layer1_boss_fail_count,
                       tutorial_layer1_boss_help_ready, tutorial_layer1_forced_boss_ready,
                       tutorial_layer1_fuse_after_boss_fail_count,
                       max_unlocked_layer, coins, layer1_first_clear_reward_claimed,
                       layer1_first_clear_home_seen
                FROM users
                WHERE id = ?
                """,
                (self.user_id,),
            ).fetchone()

    def _insert_layer1_explore_end_events(self, count):
        with game_app.app.app_context():
            db = game_app.get_db()
            for i in range(int(count)):
                game_app.audit_log(
                    db,
                    game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                    user_id=self.user_id,
                    action_key="explore",
                    payload={"area_key": "layer_1", "idx": i},
                )
            db.commit()

    def _insert_layer1_boss_defeat(self, user_id=None):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.audit_log(
                db,
                game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                user_id=int(user_id or self.user_id),
                action_key="explore",
                payload={"area_key": "layer_1", "boss_kind": "fixed", "enemy_key": game_app.LAYER_BOSS_KEY_BY_LAYER[1]},
            )
            db.commit()

    class FixedRandom:
        def __init__(self, value):
            self.value = float(value)

        def random(self):
            return self.value

    def _insert_strengthen_materials(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            part = db.execute(
                """
                SELECT id, part_type
                FROM robot_parts
                WHERE part_type = 'HEAD' AND is_active = 1
                ORDER BY id ASC
                LIMIT 1
                """
            ).fetchone()
            self.assertIsNotNone(part)
            ids = []
            for _ in range(3):
                cur = db.execute(
                    """
                    INSERT INTO part_instances
                    (part_id, user_id, part_type, rarity, element, series, plus,
                     w_hp, w_atk, w_def, w_spd, w_acc, w_cri, status, created_at)
                    VALUES (?, ?, ?, 'N', 'NORMAL', 'starter', 0, 1, 1, 1, 1, 1, 1, 'inventory', ?)
                    """,
                    (int(part["id"]), self.user_id, part["part_type"], now),
                )
                ids.append(int(cur.lastrowid))
            db.commit()
            return ids

    def test_normal_win_forces_boss_then_failed_boss_guides_strengthen(self):
        first = self._explore(self._resolve_player_win)
        self.assertEqual(first.status_code, 200)
        row = self._user_tutorial_row()
        self.assertEqual(row["tutorial_layer1_state"], game_app.TUTORIAL_LAYER1_STATE_WON_NORMAL_ONCE)
        self.assertEqual(int(row["tutorial_layer1_normal_win_count"]), 1)
        self.assertEqual(int(row["tutorial_layer1_forced_boss_ready"]), 1)

        boss = self._explore(self._resolve_player_loss)
        self.assertEqual(boss.status_code, 200)
        html = boss.get_data(as_text=True)
        self.assertIn("あと少しで突破できそうです", html)
        self.assertIn("パーツを強化したり、もう一度出撃すると第1層ボスを倒しやすくなります。", html)
        self.assertIn("パーツ強化へ", html)
        self.assertIn("ロボ編成へ", html)
        self.assertIn("基地へ戻る", html)
        self.assertIn("もう一度出撃", html)
        self.assertIn("ボスの動きを記録しました。次は少し有利に戦えそうです。", html)
        row = self._user_tutorial_row()
        self.assertEqual(row["tutorial_layer1_state"], game_app.TUTORIAL_LAYER1_STATE_BOSS_FAILED_ONCE)
        self.assertGreater(int(row["tutorial_layer1_boss_seen_at"] or 0), 0)
        self.assertEqual(int(row["tutorial_layer1_boss_fail_count"]), 1)
        self.assertEqual(int(row["tutorial_layer1_boss_help_ready"]), 1)
        self.assertEqual(int(row["tutorial_layer1_forced_boss_ready"]), 0)
        with game_app.app.app_context():
            db = game_app.get_db()
            payload = json.loads(db.execute(
                """
                SELECT payload_json
                FROM world_events_log
                WHERE user_id = ? AND event_type = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (self.user_id, game_app.AUDIT_EVENT_TYPES["NEWBIE_PROTECTION_BATTLE_ASSIST"]),
            ).fetchone()["payload_json"])
            self.assertEqual(payload["hp_multiplier"], 0.8)
            self.assertEqual(payload["atk_multiplier"], 0.8)
            self.assertEqual(payload["def_multiplier"], 0.8)
            self.assertEqual(payload["acc_multiplier"], 0.9)
            self.assertIsNone(payload["player_hp_multiplier"])
            help_set = db.execute(
                "SELECT 1 FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["TUTORIAL_LAYER1_BOSS_HELP_SET"]),
            ).fetchone()
            self.assertIsNotNone(help_set)

        home = self._client().get("/home")
        self.assertEqual(home.status_code, 200)
        home_html = home.get_data(as_text=True)
        self.assertIn("第1層ボスに再挑戦しよう", home_html)
        self.assertIn("前回の戦闘記録により、次は少し有利に戦えます。", home_html)

    def test_fuse_after_boss_fail_guarantees_retry_and_clear(self):
        self._explore(self._resolve_player_win)
        self._explore(self._resolve_player_loss)
        ids = self._insert_strengthen_materials()

        client = self._client()
        fuse_resp = client.post(
            "/parts/strengthen",
            data={"mode": "select", "base_id": str(ids[0])},
            follow_redirects=False,
        )
        self.assertEqual(fuse_resp.status_code, 302)
        row = self._user_tutorial_row()
        self.assertEqual(row["tutorial_layer1_state"], game_app.TUTORIAL_LAYER1_STATE_BOSS_FAILED_ONCE)
        self.assertEqual(int(row["tutorial_layer1_forced_boss_ready"]), 1)
        self.assertEqual(int(row["tutorial_layer1_fuse_after_boss_fail_count"]), 1)

        retry = self._explore(self._resolve_player_win)
        self.assertEqual(retry.status_code, 200)
        html = retry.get_data(as_text=True)
        self.assertIn("第1層突破", html)
        row = self._user_tutorial_row()
        self.assertEqual(row["tutorial_layer1_state"], game_app.TUTORIAL_LAYER1_STATE_CLEARED)
        self.assertEqual(int(row["max_unlocked_layer"]), 2)
        self.assertEqual(int(row["tutorial_layer1_boss_help_ready"]), 0)
        self.assertEqual(int(row["layer1_first_clear_reward_claimed"]), 1)
        self.assertGreaterEqual(int(row["coins"]), 1100)
        with game_app.app.app_context():
            db = game_app.get_db()
            decor = db.execute(
                """
                SELECT 1
                FROM user_decor_inventory udi
                JOIN robot_decor_assets rda ON rda.id = udi.decor_asset_id
                WHERE udi.user_id = ? AND rda.key = ?
                """,
                (self.user_id, game_app.LAYER1_FIRST_CLEAR_DECOR_KEY),
            ).fetchone()
            self.assertIsNotNone(decor)
            duplicate = game_app._grant_layer1_first_clear_reward(db, self.user_id)
            self.assertFalse(duplicate["reward_granted"])
            self.assertEqual(duplicate["duplicate_skip_reason"], "already_claimed")
            consume = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ? ORDER BY id DESC LIMIT 1",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["TUTORIAL_LAYER1_BOSS_HELP_CONSUME"]),
            ).fetchone()
            self.assertIsNotNone(consume)
            self.assertEqual(json.loads(consume["payload_json"])["result"], "win")
            bonus = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ? ORDER BY id DESC LIMIT 1",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["TUTORIAL_LAYER1_BOSS_BONUS_GRANT"]),
            ).fetchone()
            self.assertIsNotNone(bonus)
            self.assertEqual(json.loads(bonus["payload_json"])["coins"], 100)
            db.commit()

        home = self._client().get("/home")
        self.assertEqual(home.status_code, 200)
        home_html = home.get_data(as_text=True)
        self.assertIn("第1層突破！", home_html)
        self.assertIn("研究員として最初の試験を突破しました", home_html)
        second_home = self._client().get("/home")
        self.assertNotIn("研究員として最初の試験を突破しました", second_home.get_data(as_text=True))

    def test_layer1_protection_subject_conditions(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT * FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertTrue(game_app.is_layer1_protection_active(db, user))

            db.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (self.user_id,))
            admin_user = db.execute("SELECT * FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertFalse(game_app.is_layer1_protection_active(db, admin_user))

            db.execute("UPDATE users SET is_admin = 0, max_unlocked_layer = 2 WHERE id = ?", (self.user_id,))
            layer2_user = db.execute("SELECT * FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertFalse(game_app.is_layer1_protection_active(db, layer2_user))

            db.execute("UPDATE users SET max_unlocked_layer = 1 WHERE id = ?", (self.user_id,))
            db.commit()
        self._insert_layer1_boss_defeat()
        with game_app.app.app_context():
            db = game_app.get_db()
            defeated_user = db.execute("SELECT * FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertFalse(game_app.is_layer1_protection_active(db, defeated_user))

    def test_layer1_uncleared_boss_spawn_rate_is_five_percent_only_for_layer1(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            roll = game_app._area_boss_spawn_check(
                db,
                self.user_id,
                "layer_1",
                rng=self.FixedRandom(0.049),
            )
            self.assertTrue(roll["spawn"])
            self.assertEqual(roll["probability"], 0.05)

            game_app.audit_log(
                db,
                game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                user_id=self.user_id,
                action_key="explore",
                payload={"area_key": "layer_1", "boss_kind": "fixed", "enemy_key": game_app.LAYER_BOSS_KEY_BY_LAYER[1]},
            )
            db.commit()
            cleared_roll = game_app._area_boss_spawn_check(
                db,
                self.user_id,
                "layer_1",
                rng=self.FixedRandom(0.01),
            )
            self.assertFalse(cleared_roll["spawn"])
            self.assertEqual(cleared_roll["probability"], game_app.AREA_BOSS_SPAWN_RATES["layer_1"])

            db.execute("UPDATE users SET max_unlocked_layer = 2 WHERE id = ?", (self.user_id,))
            db.commit()
            layer2_roll = game_app._area_boss_spawn_check(
                db,
                self.user_id,
                "layer_2",
                rng=self.FixedRandom(0.01),
            )
            self.assertFalse(layer2_roll["spawn"])
            self.assertEqual(layer2_roll["probability"], game_app.AREA_BOSS_SPAWN_RATES["layer_2"])

    def test_layer1_help_losing_retry_keeps_flag(self):
        self._explore(self._resolve_player_win)
        self._explore(self._resolve_player_loss)
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET tutorial_layer1_forced_boss_ready = 1 WHERE id = ?", (self.user_id,))
            db.commit()

        retry = self._explore(self._resolve_player_loss)
        self.assertEqual(retry.status_code, 200)
        row = self._user_tutorial_row()
        self.assertEqual(int(row["tutorial_layer1_boss_help_ready"]), 1)
        with game_app.app.app_context():
            db = game_app.get_db()
            consume = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ? ORDER BY id DESC LIMIT 1",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["TUTORIAL_LAYER1_BOSS_HELP_CONSUME"]),
            ).fetchone()
            self.assertIsNotNone(consume)
            self.assertEqual(json.loads(consume["payload_json"])["result"], "lose")

    def test_layer1_tenth_explore_guarantees_alert_not_immediate_battle(self):
        self._insert_layer1_explore_end_events(9)
        client = self._client()
        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "_enforce_explore_cooldown_or_wait", return_value=0
        ):
            resp = client.post("/explore", data={"area_key": "layer_1"}, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            progress = db.execute(
                """
                SELECT active_boss_enemy_id, boss_attempts_left, boss_alert_expires_at
                FROM user_boss_progress
                WHERE user_id = ? AND area_key = 'layer_1'
                """,
                (self.user_id,),
            ).fetchone()
            self.assertIsNotNone(progress)
            self.assertIsNotNone(progress["active_boss_enemy_id"])
            self.assertGreater(int(progress["boss_attempts_left"]), 0)
            guaranteed = db.execute(
                "SELECT 1 FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["NEWBIE_PROTECTION_BOSS_ALERT_GUARANTEED"]),
            ).fetchone()
            self.assertIsNotNone(guaranteed)
            explore_end_count = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"]),
            ).fetchone()["c"]
            self.assertEqual(int(explore_end_count), 9)

    def test_forced_boss_tutorial_priority_over_alert_guarantee(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET tutorial_layer1_forced_boss_ready = 1 WHERE id = ?", (self.user_id,))
            db.commit()
        self._insert_layer1_explore_end_events(9)
        resp = self._explore(self._resolve_player_loss)
        self.assertEqual(resp.status_code, 200)
        with game_app.app.app_context():
            db = game_app.get_db()
            guaranteed = db.execute(
                "SELECT 1 FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["NEWBIE_PROTECTION_BOSS_ALERT_GUARANTEED"]),
            ).fetchone()
            self.assertIsNone(guaranteed)
