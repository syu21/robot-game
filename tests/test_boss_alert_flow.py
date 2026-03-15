import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class BossAlertFlowTests(unittest.TestCase):
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
                VALUES (?, ?, ?, 1, 30, 0, 2)
                """,
                ("boss_alert_tester", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("boss_alert_tester",),
            ).fetchone()["id"]
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (self.user_id, "AlertRunner", now, now),
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
                INSERT INTO enemies
                (key, name_ja, image_path, tier, element, hp, atk, def, spd, acc, cri, faction, is_boss, boss_area_key, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 1)
                ON CONFLICT(key) DO UPDATE SET
                    name_ja = excluded.name_ja,
                    image_path = excluded.image_path,
                    tier = excluded.tier,
                    element = excluded.element,
                    hp = excluded.hp,
                    atk = excluded.atk,
                    def = excluded.def,
                    spd = excluded.spd,
                    acc = excluded.acc,
                    cri = excluded.cri,
                    faction = excluded.faction,
                    is_boss = excluded.is_boss,
                    boss_area_key = excluded.boss_area_key,
                    is_active = excluded.is_active
                """,
                (
                    "test_alert_boss",
                    "警報試験ボス",
                    "assets/placeholder_enemy.png",
                    2,
                    "THUNDER",
                    1,
                    1,
                    1,
                    1,
                    1,
                    1,
                    "ventra",
                    "layer_2",
                ),
            )
            db.execute(
                """
                UPDATE enemies
                SET is_active = 0
                WHERE COALESCE(is_boss, 0) = 1
                  AND boss_area_key = 'layer_2'
                  AND key <> 'test_alert_boss'
                """
            )
            db.execute(
                """
                INSERT INTO user_boss_progress (user_id, area_key, no_boss_streak, updated_at)
                VALUES (?, 'layer_2', ?, ?)
                ON CONFLICT(user_id, area_key) DO UPDATE SET no_boss_streak = excluded.no_boss_streak, updated_at = excluded.updated_at
                """,
                (self.user_id, int(game_app.AREA_BOSS_PITY_MISSES["layer_2"]) - 1, now),
            )
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
    def _resolve_for_lose(att_atk, att_acc, att_cri, def_def, def_acc, **kwargs):
        if int(att_atk) >= 5:
            return 0, False
        return 999, False

    def _new_client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "boss_alert_tester"
        return client

    def _trigger_alert(self):
        client = self._new_client()
        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()):
            return client.post("/explore", data={"area_key": "layer_2"}, follow_redirects=True)

    def test_boss_alert_granted_then_three_attempts_end(self):
        alert_resp = self._trigger_alert()
        self.assertEqual(alert_resp.status_code, 200)
        self.assertIn("ボス警報", alert_resp.get_data(as_text=True))

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                """
                SELECT active_boss_enemy_id, boss_attempts_left, boss_alert_expires_at
                FROM user_boss_progress
                WHERE user_id = ? AND area_key = 'layer_2'
                """,
                (self.user_id,),
            ).fetchone()
            self.assertIsNotNone(row["active_boss_enemy_id"])
            self.assertEqual(int(row["boss_attempts_left"]), 3)
            self.assertGreater(int(row["boss_alert_expires_at"]), int(time.time()))
            encounter_count = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = 'audit.boss.encounter' AND user_id = ?",
                (self.user_id,),
            ).fetchone()["c"]
            self.assertGreaterEqual(int(encounter_count), 1)

        client = self._new_client()
        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "resolve_attack", side_effect=self._resolve_for_lose
        ):
            for _ in range(3):
                resp = client.post("/explore", data={"area_key": "layer_2", "boss_enter": "1"})
                self.assertEqual(resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                """
                SELECT active_boss_enemy_id, boss_attempts_left, boss_alert_expires_at
                FROM user_boss_progress
                WHERE user_id = ? AND area_key = 'layer_2'
                """,
                (self.user_id,),
            ).fetchone()
            self.assertIsNone(row["active_boss_enemy_id"])
            self.assertEqual(int(row["boss_attempts_left"]), 0)
            self.assertIsNone(row["boss_alert_expires_at"])
            attempt_count = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = 'audit.boss.attempt' AND user_id = ?",
                (self.user_id,),
            ).fetchone()["c"]
            self.assertEqual(int(attempt_count), 3)

    def test_alert_survives_build_roundtrip_and_can_reenter(self):
        alert_resp = self._trigger_alert()
        self.assertEqual(alert_resp.status_code, 200)
        self.assertIn("ボス警報", alert_resp.get_data(as_text=True))

        client = self._new_client()
        build_page = client.get("/build")
        self.assertEqual(build_page.status_code, 200)

        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "resolve_attack", side_effect=self._resolve_for_lose
        ):
            enter_resp = client.post("/explore", data={"area_key": "layer_2", "boss_enter": "1"})
        self.assertEqual(enter_resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT boss_attempts_left FROM user_boss_progress WHERE user_id = ? AND area_key = 'layer_2'",
                (self.user_id,),
            ).fetchone()
            self.assertEqual(int(row["boss_attempts_left"]), 2)

    def test_expired_alert_is_cleared_and_reentry_blocked(self):
        alert_resp = self._trigger_alert()
        self.assertEqual(alert_resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                UPDATE user_boss_progress
                SET boss_alert_expires_at = ?, updated_at = ?
                WHERE user_id = ? AND area_key = 'layer_2'
                """,
                (int(time.time()) - 1, int(time.time()), self.user_id),
            )
            db.commit()

        client = self._new_client()
        resp = client.post("/explore", data={"area_key": "layer_2", "boss_enter": "1"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("有効なボス警報がありません", resp.get_data(as_text=True))

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                """
                SELECT active_boss_enemy_id, boss_attempts_left, boss_alert_expires_at
                FROM user_boss_progress
                WHERE user_id = ? AND area_key = 'layer_2'
                """,
                (self.user_id,),
            ).fetchone()
            self.assertIsNone(row["active_boss_enemy_id"])
            self.assertEqual(int(row["boss_attempts_left"]), 0)
            self.assertIsNone(row["boss_alert_expires_at"])


if __name__ == "__main__":
    unittest.main()
