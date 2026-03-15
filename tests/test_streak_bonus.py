import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class StreakBonusTests(unittest.TestCase):
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
                VALUES (?, ?, ?, 1, 20, 0, 2)
                """,
                ("streak_tester", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("streak_tester",),
            ).fetchone()["id"]
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (self.user_id, "StreakBot", now, now),
            )
            robot_id = db.execute(
                "SELECT id FROM robot_instances WHERE user_id = ?",
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
                    robot_id,
                    pick_key("HEAD"),
                    pick_key("RIGHT_ARM"),
                    pick_key("LEFT_ARM"),
                    pick_key("LEGS"),
                ),
            )
            db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (robot_id, self.user_id))
            db.execute(
                """
                UPDATE enemies
                SET is_active = 0
                WHERE COALESCE(is_boss, 0) = 1
                  AND boss_area_key = 'layer_1'
                """
            )
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _weak_enemy(self, tier=1):
        return {
            "id": 9001,
            "key": "test_weak_enemy",
            "name_ja": "弱い敵",
            "image_path": "assets/placeholder_enemy.png",
            "hp": 1,
            "atk": 1,
            "def": 0,
            "spd": 1,
            "acc": 1,
            "cri": 1,
            "tier": tier,
            "element": "NORMAL",
            "faction": "neutral",
        }

    def _strong_enemy(self, tier=1):
        return {
            "id": 9002,
            "key": "test_strong_enemy",
            "name_ja": "強い敵",
            "image_path": "assets/placeholder_enemy.png",
            "hp": 999,
            "atk": 99,
            "def": 0,
            "spd": 99,
            "acc": 99,
            "cri": 99,
            "tier": tier,
            "element": "NORMAL",
            "faction": "neutral",
        }

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
    def _resolve_for_win(att_atk, att_acc, att_cri, def_def, def_acc, **kwargs):
        if int(att_atk) >= 5:
            return 999, False
        return 0, False

    @staticmethod
    def _resolve_for_loss(att_atk, att_acc, att_cri, def_def, def_acc, **kwargs):
        if int(att_atk) >= 90:
            return 999, False
        return 0, False

    def _new_client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "streak_tester"
        return client

    def test_three_wins_same_area_grants_bonus_coin(self):
        client = self._new_client()
        with patch.object(game_app, "_pick_enemy_for_area", return_value=self._weak_enemy(tier=1)), patch.object(
            game_app, "_world_current_environment", return_value=self._stable_weekly_env()
        ), patch.object(game_app, "resolve_attack", side_effect=self._resolve_for_win):
            responses = [client.post("/explore", data={"area_key": "layer_1"}) for _ in range(3)]

        self.assertTrue(all(r.status_code == 200 for r in responses))
        third_html = responses[-1].get_data(as_text=True)
        self.assertIn("獲得コイン", third_html)
        self.assertIn("+3", third_html)

        with game_app.app.app_context():
            db = game_app.get_db()
            coins = db.execute("SELECT coins FROM users WHERE id = ?", (self.user_id,)).fetchone()["coins"]
            self.assertEqual(int(coins), 7)  # tier1 coin(2) * 3 + streak bonus(1)
            streak = db.execute(
                "SELECT win_streak FROM user_area_streaks WHERE user_id = ? AND area_key = 'layer_1'",
                (self.user_id,),
            ).fetchone()["win_streak"]
            self.assertEqual(int(streak), 3)
            bonus_logs = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = 'audit.streak.bonus'",
                (self.user_id,),
            ).fetchone()["c"]
            self.assertEqual(int(bonus_logs), 1)

    def test_switching_area_resets_other_area_streak(self):
        client = self._new_client()
        with patch.object(game_app, "_pick_enemy_for_area", return_value=self._weak_enemy(tier=1)), patch.object(
            game_app, "_world_current_environment", return_value=self._stable_weekly_env()
        ), patch.object(game_app, "resolve_attack", side_effect=self._resolve_for_win):
            client.post("/explore", data={"area_key": "layer_1"})
            client.post("/explore", data={"area_key": "layer_1"})
            client.post("/explore", data={"area_key": "layer_2"})

        with game_app.app.app_context():
            db = game_app.get_db()
            row1 = db.execute(
                "SELECT win_streak FROM user_area_streaks WHERE user_id = ? AND area_key = 'layer_1'",
                (self.user_id,),
            ).fetchone()
            row2 = db.execute(
                "SELECT win_streak FROM user_area_streaks WHERE user_id = ? AND area_key = 'layer_2'",
                (self.user_id,),
            ).fetchone()
            self.assertIsNotNone(row1)
            self.assertIsNotNone(row2)
            self.assertEqual(int(row1["win_streak"]), 0)
            self.assertEqual(int(row2["win_streak"]), 1)

    def test_losing_resets_streak_to_zero(self):
        client = self._new_client()

        with patch.object(game_app, "_pick_enemy_for_area", return_value=self._weak_enemy(tier=1)), patch.object(
            game_app, "_world_current_environment", return_value=self._stable_weekly_env()
        ), patch.object(game_app, "resolve_attack", side_effect=self._resolve_for_win):
            client.post("/explore", data={"area_key": "layer_1"})
            client.post("/explore", data={"area_key": "layer_1"})

        with patch.object(game_app, "_pick_enemy_for_area", return_value=self._strong_enemy(tier=1)), patch.object(
            game_app, "_world_current_environment", return_value=self._stable_weekly_env()
        ), patch.object(game_app, "resolve_attack", side_effect=self._resolve_for_loss):
            resp = client.post("/explore", data={"area_key": "layer_1"})

        self.assertEqual(resp.status_code, 200)
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT win_streak FROM user_area_streaks WHERE user_id = ? AND area_key = 'layer_1'",
                (self.user_id,),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(int(row["win_streak"]), 0)


if __name__ == "__main__":
    unittest.main()
