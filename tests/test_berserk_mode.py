import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class BerserkModeTests(unittest.TestCase):
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
                VALUES (?, ?, ?, 1, 30, 999999, 2)
                """,
                ("berserk_tester", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("berserk_tester",),
            ).fetchone()["id"]

            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at, combat_mode)
                VALUES (?, ?, 'active', ?, ?, 'berserk')
                """,
                (self.user_id, "BerserkRunner", now, now),
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

            self.head_key = pick_key("HEAD")
            self.r_arm_key = pick_key("RIGHT_ARM")
            self.l_arm_key = pick_key("LEFT_ARM")
            self.legs_key = pick_key("LEGS")

            db.execute(
                """
                INSERT INTO robot_instance_parts (robot_instance_id, head_key, r_arm_key, l_arm_key, legs_key)
                VALUES (?, ?, ?, ?, ?)
                """,
                (self.robot_id, self.head_key, self.r_arm_key, self.l_arm_key, self.legs_key),
            )
            db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (self.robot_id, self.user_id))

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
                    "berserk_test_boss",
                    "背水試験ボス",
                    "assets/placeholder_enemy.png",
                    2,
                    "THUNDER",
                    20,
                    3,
                    2,
                    5,
                    8,
                    1,
                    "ventra",
                    "layer_2",
                ),
            )
            enemy_id = db.execute("SELECT id FROM enemies WHERE key = 'berserk_test_boss'").fetchone()["id"]
            db.execute(
                """
                UPDATE enemies
                SET is_active = 0
                WHERE COALESCE(is_boss, 0) = 1 AND boss_area_key = 'layer_2' AND key <> 'berserk_test_boss'
                """
            )
            db.execute(
                """
                INSERT INTO user_boss_progress
                (user_id, area_key, no_boss_streak, active_boss_enemy_id, boss_attempts_left, boss_alert_expires_at, updated_at)
                VALUES (?, 'layer_2', 0, ?, 1, ?, ?)
                ON CONFLICT(user_id, area_key) DO UPDATE SET
                    no_boss_streak = excluded.no_boss_streak,
                    active_boss_enemy_id = excluded.active_boss_enemy_id,
                    boss_attempts_left = excluded.boss_attempts_left,
                    boss_alert_expires_at = excluded.boss_alert_expires_at,
                    updated_at = excluded.updated_at
                """,
                (self.user_id, int(enemy_id), now + 3600, now),
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
    def _resolve_balanced(att_atk, att_acc, att_cri, def_def, def_acc, **kwargs):
        if int(att_atk) >= 5:
            return 2, False
        return 1, False

    @staticmethod
    def _mock_battle_render(template_name, **context):
        if template_name != "battle.html" or not context.get("explore_mode"):
            return ""
        logs = context.get("turn_logs") or []
        first = logs[0] if logs else {}
        has_berserk_line = any(bool(r.get("player_berserk_line")) for r in logs)
        return json.dumps(
            {
                "player_max": int(first.get("player_max", 0)) if first else 0,
                "build_profile_line": first.get("build_profile_line"),
                "has_berserk_line": bool(has_berserk_line),
            },
            ensure_ascii=False,
        )

    def _new_client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "berserk_tester"
        return client

    def _seed_build_inventory(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            for part_type, key in (
                ("HEAD", self.head_key),
                ("RIGHT_ARM", self.r_arm_key),
                ("LEFT_ARM", self.l_arm_key),
                ("LEGS", self.legs_key),
            ):
                db.execute(
                    """
                    INSERT INTO user_parts_inventory (user_id, part_type, part_key, obtained_at, source)
                    VALUES (?, ?, ?, ?, 'test')
                    """,
                    (self.user_id, part_type, key, now),
                )
            db.commit()

    def test_berserk_bonus_increases_and_caps(self):
        self.assertEqual(game_app._berserk_attack_bonus("BERSERK", 10, 10), 0.0)
        mid = game_app._berserk_attack_bonus("BERSERK", 5, 10)
        self.assertAlmostEqual(mid, 0.30, places=6)
        low = game_app._berserk_attack_bonus("BERSERK", 1, 10)
        self.assertAlmostEqual(low, 0.30, places=6)
        self.assertEqual(game_app._berserk_attack_bonus("STABLE", 1, 10), 0.0)

    def test_berserk_mode_reduces_hp_and_outputs_turn_log_line(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE robot_instances SET combat_mode = 'berserk' WHERE id = ?", (self.robot_id,))
            db.commit()
            base_hp = int(game_app._compute_robot_stats_for_instance(db, self.robot_id)["stats"]["hp"])

        client = self._new_client()
        with patch.object(game_app, "render_template", side_effect=self._mock_battle_render), patch.object(
            game_app, "_world_current_environment", return_value=self._stable_weekly_env()
        ), patch.object(game_app, "resolve_attack", side_effect=self._resolve_balanced):
            resp = client.post("/explore", data={"area_key": "layer_2", "boss_enter": "1"})
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.get_data(as_text=True))
        self.assertLess(payload["player_max"], base_hp)
        self.assertIn("背水型", payload.get("build_profile_line") or "")
        self.assertTrue(payload.get("has_berserk_line"))

    def test_build_confirm_rejects_berserk_without_alert(self):
        self._seed_build_inventory()
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                UPDATE user_boss_progress
                SET active_boss_enemy_id = NULL, boss_attempts_left = 0, boss_alert_expires_at = NULL, updated_at = ?
                WHERE user_id = ? AND area_key = 'layer_2'
                """,
                (int(time.time()), self.user_id),
            )
            db.commit()

        client = self._new_client()
        resp = client.post(
            "/build/confirm",
            data={
                "robot_name": "NoAlertBerserk",
                "head_key": self.head_key,
                "r_arm_key": self.r_arm_key,
                "l_arm_key": self.l_arm_key,
                "legs_key": self.legs_key,
                "combat_mode": "berserk",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ロボ編成", resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
