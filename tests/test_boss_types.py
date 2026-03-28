import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class BossTypeTests(unittest.TestCase):
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
                ("boss_type_tester", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("boss_type_tester",),
            ).fetchone()["id"]
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (self.user_id, "TypeRunner", now, now),
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
            # layer_2の既存ボスを固定ステータスにして倍率検証しやすくする。
            db.execute(
                """
                UPDATE enemies
                SET hp = 100, atk = 100, def = 100, spd = 1, acc = 100, cri = 5, is_active = 1
                WHERE key = 'boss_ventra_sentinel'
                """
            )
            enemy_row = db.execute("SELECT id FROM enemies WHERE key = 'boss_ventra_sentinel'").fetchone()
            self.assertIsNotNone(enemy_row)
            db.execute(
                """
                INSERT INTO user_boss_progress
                (user_id, area_key, no_boss_streak, active_boss_enemy_id, boss_attempts_left, boss_alert_expires_at, updated_at)
                VALUES (?, 'layer_2', 0, ?, 3, ?, ?)
                ON CONFLICT(user_id, area_key) DO UPDATE SET
                    active_boss_enemy_id = excluded.active_boss_enemy_id,
                    boss_attempts_left = excluded.boss_attempts_left,
                    boss_alert_expires_at = excluded.boss_alert_expires_at,
                    updated_at = excluded.updated_at
                """,
                (self.user_id, int(enemy_row["id"]), now + 3600, now),
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

    def _new_client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "boss_type_tester"
        return client

    @staticmethod
    def _mock_battle_render(template_name, **context):
        if template_name != "battle.html":
            return ""
        logs = context.get("turn_logs") or []
        first = logs[0] if logs else {}
        summary = context.get("summary") or {}
        return json.dumps(
            {
                "boss_type": summary.get("boss_type"),
                "boss_type_label": summary.get("boss_type_label"),
                "boss_type_recommend": summary.get("boss_type_recommend"),
                "enemy_tendency_tag": summary.get("enemy_tendency_tag"),
                "player_style_label": ((summary.get("player_style") or {}).get("style_label")),
                "enemy_max": int(first.get("enemy_max") or 0),
                "boss_type_line": first.get("boss_type_line"),
            },
            ensure_ascii=False,
        )

    def test_boss_type_mapping_for_bosses(self):
        self.assertEqual(game_app._boss_type_meta({"key": "boss_ignis_reaver"})["code"], "TANK")
        self.assertEqual(game_app._boss_type_meta({"key": "boss_ventra_sentinel"})["code"], "EVADE")
        self.assertEqual(game_app._boss_type_meta({"key": "boss_aurix_guardian"})["code"], "GLASS_CANNON")
        self.assertEqual(game_app._boss_type_meta({"key": "boss_4_forge_elguard"})["code"], "TANK")
        self.assertEqual(game_app._boss_type_meta({"key": "boss_4_haze_mirage"})["code"], "EVADE")
        self.assertEqual(game_app._boss_type_meta({"key": "boss_4_burst_volterio"})["code"], "GLASS_CANNON")
        self.assertEqual(game_app._boss_type_meta({"key": "boss_4_final_ark_zero"})["code"], "TACTICAL")
        self.assertEqual(game_app._boss_type_meta({"key": "boss_5_labyrinth_nyx_array"})["code"], "EVADE")
        self.assertEqual(game_app._boss_type_meta({"key": "boss_5_pinnacle_ignition_king"})["code"], "GLASS_CANNON")
        self.assertEqual(game_app._boss_type_meta({"key": "boss_5_final_omega_frame"})["code"], "TACTICAL")

    def test_boss_type_stat_modifiers(self):
        tank = game_app._apply_boss_type_modifiers(
            {"key": "boss_ignis_reaver", "hp": 100, "atk": 100, "def": 100, "acc": 100}
        )
        self.assertEqual(int(tank["hp"]), 125)
        self.assertEqual(int(tank["def"]), 125)
        self.assertEqual(int(tank["atk"]), 95)

        evade = game_app._apply_boss_type_modifiers(
            {"key": "boss_ventra_sentinel", "hp": 100, "atk": 100, "def": 100, "acc": 100}
        )
        self.assertEqual(int(evade["hp"]), 105)
        self.assertEqual(int(evade["acc"]), 125)

        glass = game_app._apply_boss_type_modifiers(
            {"key": "boss_aurix_guardian", "hp": 100, "atk": 100, "def": 100, "acc": 100}
        )
        self.assertEqual(int(glass["hp"]), 95)
        self.assertEqual(int(glass["def"]), 95)
        self.assertEqual(int(glass["atk"]), 125)

    def test_home_and_battle_show_boss_type_and_research_line(self):
        client = self._new_client()
        home_resp = client.get("/home")
        self.assertEqual(home_resp.status_code, 200)
        html = home_resp.get_data(as_text=True)
        self.assertNotIn("おすすめ：安定型（当てる）", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            base_enemy_hp = int(
                db.execute("SELECT hp FROM enemies WHERE key = 'boss_ventra_sentinel'").fetchone()["hp"]
            )
            base_enemy_acc = int(
                db.execute("SELECT acc FROM enemies WHERE key = 'boss_ventra_sentinel'").fetchone()["acc"]
            )

        captured_def_acc = []
        original_resolve = game_app.resolve_attack

        def _capture_resolve(*args, **kwargs):
            if len(args) >= 5:
                captured_def_acc.append(int(args[4]))
            return original_resolve(*args, **kwargs)

        with patch.object(game_app, "render_template", side_effect=self._mock_battle_render), patch.object(
            game_app, "_world_current_environment", return_value=self._stable_weekly_env()
        ), patch.object(game_app, "resolve_attack", side_effect=_capture_resolve):
            resp = client.post("/explore", data={"area_key": "layer_2", "boss_enter": "1"})
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.get_data(as_text=True))
        self.assertEqual(payload.get("boss_type"), "EVADE")
        self.assertEqual(payload.get("boss_type_label"), "回避")
        self.assertIn("ボス種別", payload.get("boss_type_line") or "")
        self.assertIn(payload.get("player_style_label"), ("安定", "背水", "爆発"))
        self.assertIsNone(payload.get("enemy_tendency_tag"))
        expected_hp = max(1, int(round(base_enemy_hp * 1.05)))
        expected_acc = max(1, int(round(base_enemy_acc * 1.25)))
        self.assertEqual(int(payload.get("enemy_max") or 0), expected_hp)
        self.assertIn(expected_acc, captured_def_acc)

    def test_recommendation_line_hidden_home_and_build(self):
        client = self._new_client()
        home_on = client.get("/home")
        build_on = client.get("/build")
        self.assertEqual(home_on.status_code, 200)
        self.assertEqual(build_on.status_code, 200)
        self.assertNotIn("おすすめ：安定型（当てる）", home_on.get_data(as_text=True))
        self.assertNotIn("今はボス警報中です：", build_on.get_data(as_text=True))

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

        home_off = client.get("/home")
        build_off = client.get("/build")
        self.assertEqual(home_off.status_code, 200)
        self.assertEqual(build_off.status_code, 200)
        self.assertNotIn("おすすめ：安定型（当てる）", home_off.get_data(as_text=True))
        self.assertNotIn("今はボス警報中です：", build_off.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
