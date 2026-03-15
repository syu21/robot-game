import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class LayerUnlockProgressionTests(unittest.TestCase):
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
                VALUES (?, ?, ?, 1, 20, 0, 1)
                """,
                ("layer_unlock_tester", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("layer_unlock_tester",),
            ).fetchone()["id"]
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (self.user_id, "LayerRunner", now, now),
            )
            robot_id = db.execute(
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
                    robot_id,
                    pick_key("HEAD"),
                    pick_key("RIGHT_ARM"),
                    pick_key("LEFT_ARM"),
                    pick_key("LEGS"),
                ),
            )
            db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (robot_id, self.user_id))
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
    def _resolve_for_win(att_atk, att_acc, att_cri, def_def, def_acc, **kwargs):
        if kwargs.get("attacker_archetype") is not None:
            return 999, False
        return 0, False

    def _new_client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "layer_unlock_tester"
        return client

    def _activate_alert_for_area(self, area_key):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            layer = int(game_app.EXPLORE_AREA_LAYER_BY_KEY[area_key])
            boss_key = game_app.LAYER_BOSS_KEY_BY_LAYER[layer]
            boss_id = db.execute("SELECT id FROM enemies WHERE key = ?", (boss_key,)).fetchone()["id"]
            db.execute(
                "UPDATE enemies SET hp = 1, atk = 1, def = 1, spd = 1, acc = 1, cri = 1, is_active = 1 WHERE key = ?",
                (boss_key,),
            )
            db.execute(
                """
                INSERT INTO user_boss_progress
                (user_id, area_key, no_boss_streak, active_boss_enemy_id, boss_attempts_left, boss_alert_expires_at, updated_at)
                VALUES (?, ?, 0, ?, 3, ?, ?)
                ON CONFLICT(user_id, area_key) DO UPDATE SET
                    active_boss_enemy_id = excluded.active_boss_enemy_id,
                    boss_attempts_left = excluded.boss_attempts_left,
                    boss_alert_expires_at = excluded.boss_alert_expires_at,
                    updated_at = excluded.updated_at
                """,
                (self.user_id, area_key, int(boss_id), now + 3600, now),
            )
            db.commit()

    def test_layer1_boss_defeat_unlocks_layer2(self):
        self._activate_alert_for_area("layer_1")
        client = self._new_client()
        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "resolve_attack", side_effect=self._resolve_for_win
        ):
            resp = client.post("/explore", data={"area_key": "layer_1", "boss_enter": "1"})
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("⚙ 第2層 解放", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT max_unlocked_layer FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(row["max_unlocked_layer"]), 2)

    def test_layer2_boss_defeat_unlocks_layer3(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET max_unlocked_layer = 2 WHERE id = ?", (self.user_id,))
            now = int(time.time())
            required = int(game_app.LAYER3_UNLOCK_LAYER2_SORTIES_REQUIRED)
            for i in range(required):
                area_key = game_app.LAYER2_FAMILY_AREA_KEYS[i % len(game_app.LAYER2_FAMILY_AREA_KEYS)]
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        now - (required - i),
                        game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                        json.dumps({"area_key": area_key, "result": "win"}, ensure_ascii=False),
                        self.user_id,
                    ),
                )
            db.commit()
        self._activate_alert_for_area("layer_2")
        client = self._new_client()
        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "resolve_attack", side_effect=self._resolve_for_win
        ):
            resp = client.post("/explore", data={"area_key": "layer_2", "boss_enter": "1"})
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("⚙ 第3層 解放", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT max_unlocked_layer FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(row["max_unlocked_layer"]), 3)

    def test_layer3_boss_defeat_does_not_exceed_cap(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET max_unlocked_layer = 3 WHERE id = ?", (self.user_id,))
            db.commit()
        self._activate_alert_for_area("layer_3")
        client = self._new_client()
        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "resolve_attack", side_effect=self._resolve_for_win
        ):
            resp = client.post("/explore", data={"area_key": "layer_3", "boss_enter": "1"})
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertNotIn("第4層", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT max_unlocked_layer FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(row["max_unlocked_layer"]), 3)


if __name__ == "__main__":
    unittest.main()
