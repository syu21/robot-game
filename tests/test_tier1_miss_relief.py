import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class Tier1MissReliefTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 1, 30, 2)
                """,
                ("tier1_relief_tester", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?", ("tier1_relief_tester",)
            ).fetchone()["id"]
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (self.user_id, "ReliefBot", now, now),
            )
            robot_id = db.execute(
                "SELECT id FROM robot_instances WHERE user_id = ?", (self.user_id,)
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
    def _mock_battle_render(template_name, **context):
        if template_name != "battle.html" or not context.get("explore_mode"):
            return ""
        return json.dumps(context.get("turn_logs") or [], ensure_ascii=False)

    @staticmethod
    def _resolve_forced_hit_after_two_miss(att_atk, att_acc, att_cri, def_def, def_acc, **kwargs):
        wants_detail = bool(kwargs.get("return_detail"))
        if kwargs.get("force_hit"):
            detail = {
                "miss": False,
                "hit_chance": 0.6,
                "att_acc": int(att_acc),
                "def_acc": int(def_acc),
                "hit_bonus": 0.0,
                "hit_forced": True,
            }
            return (1, False, detail) if wants_detail else (1, False)
        detail = {
            "miss": True,
            "hit_chance": 0.6,
            "att_acc": int(att_acc),
            "def_acc": int(def_acc),
            "hit_bonus": 0.0,
            "hit_forced": False,
        }
        return (0, False, detail) if wants_detail else (0, False)

    def test_tier1_relief_prevents_three_consecutive_player_miss(self):
        tier1_enemy = {
            "id": 999001,
            "key": "tier1_relief_enemy",
            "name_ja": "救済検証ターゲット",
            "image_path": "assets/placeholder_enemy.png",
            "tier": 1,
            "element": "NORMAL",
            "faction": "neutral",
            "hp": 999,
            "atk": 1,
            "def": 1,
            "spd": 1,
            "acc": 1,
            "cri": 1,
        }

        with patch.object(game_app, "render_template", side_effect=self._mock_battle_render), patch.object(
            game_app, "_pick_enemy_for_area", return_value=tier1_enemy
        ), patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "resolve_attack", side_effect=self._resolve_forced_hit_after_two_miss
        ):
            with game_app.app.test_client() as client:
                with client.session_transaction() as session:
                    session["user_id"] = self.user_id
                    session["username"] = "tier1_relief_tester"
                resp = client.post("/explore", data={"area_key": "layer_1"})

        self.assertEqual(resp.status_code, 200)
        turn_logs = json.loads(resp.get_data(as_text=True))
        self.assertTrue(turn_logs)

        miss_streak = 0
        relief_seen = False
        for row in turn_logs:
            note = row.get("player_attack_note") or ""
            if "MISS" in note:
                miss_streak += 1
            else:
                miss_streak = 0
            self.assertLessEqual(miss_streak, 2)
            if row.get("player_relief_line"):
                relief_seen = True

        self.assertTrue(relief_seen)

    def test_relief_never_triggers_against_tier2_enemy(self):
        tier2_enemy = {
            "id": 999002,
            "key": "tier2_relief_guard_enemy",
            "name_ja": "救済非対象ターゲット",
            "image_path": "assets/placeholder_enemy.png",
            "tier": 2,
            "element": "WIND",
            "faction": "neutral",
            "hp": 999,
            "atk": 1,
            "def": 1,
            "spd": 1,
            "acc": 1,
            "cri": 1,
        }
        player_force_flags = []

        def _resolve_capture(att_atk, att_acc, att_cri, def_def, def_acc, **kwargs):
            wants_detail = bool(kwargs.get("return_detail"))
            if kwargs.get("attacker_archetype") is not None:
                player_force_flags.append(bool(kwargs.get("force_hit")))
            detail = {
                "miss": True,
                "hit_chance": 0.6,
                "att_acc": int(att_acc),
                "def_acc": int(def_acc),
                "hit_bonus": 0.0,
                "hit_forced": bool(kwargs.get("force_hit")),
            }
            return (0, False, detail) if wants_detail else (0, False)

        with patch.object(game_app, "render_template", side_effect=self._mock_battle_render), patch.object(
            game_app, "_pick_enemy_for_area", return_value=tier2_enemy
        ), patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "resolve_attack", side_effect=_resolve_capture
        ):
            with game_app.app.app_context():
                db = game_app.get_db()
                db.execute(
                    """
                    INSERT INTO battle_state (user_id, enemy_name, enemy_hp, last_action_at, active)
                    VALUES (?, '', 0, 0, 0)
                    ON CONFLICT(user_id) DO UPDATE SET
                        last_action_at = 0,
                        active = 0
                    """,
                    (self.user_id,),
                )
                db.commit()
            with game_app.app.test_client() as client:
                with client.session_transaction() as session:
                    session["user_id"] = self.user_id
                    session["username"] = "tier1_relief_tester"
                resp = client.post("/explore", data={"area_key": "layer_2"})

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(player_force_flags)
        self.assertNotIn(True, player_force_flags)


if __name__ == "__main__":
    unittest.main()
