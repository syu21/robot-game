import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class StageModifiersTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        self.old_stage_mod_flag = game_app.STAGE_MODIFIERS_ENABLED
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
                VALUES (?, ?, ?, 0, 0, 2)
                """,
                ("stage_mod_tester", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("stage_mod_tester",),
            ).fetchone()["id"]
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (self.user_id, "ModRunner", now, now),
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
        game_app.STAGE_MODIFIERS_ENABLED = self.old_stage_mod_flag
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _new_client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "stage_mod_tester"
        return client

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
    def _resolve_for_quick_win(att_atk, att_acc, att_cri, def_def, def_acc, **kwargs):
        if kwargs.get("attacker_archetype") is not None:
            return 999, False
        return 0, False

    @staticmethod
    def _mock_battle_render(template_name, **context):
        if template_name != "battle.html":
            return ""
        summary = context.get("summary") or {}
        logs = context.get("turn_logs") or []
        first = logs[0] if logs else {}
        return json.dumps(
            {
                "stage_modifier": summary.get("stage_modifier"),
                "stage_modifier_line": summary.get("stage_modifier_line"),
                "turn_stage_modifier_line": first.get("stage_modifier_line"),
            },
            ensure_ascii=False,
        )

    def test_effective_stats_and_log_line_when_enabled(self):
        game_app.STAGE_MODIFIERS_ENABLED = True
        pm = game_app.STAGE_MODIFIERS_BY_AREA["layer_2_rush"]["player_mult"]

        client = self._new_client()
        with patch.object(game_app, "render_template", side_effect=self._mock_battle_render), patch.object(
            game_app, "_world_current_environment", return_value=self._stable_weekly_env()
        ), patch.object(game_app, "resolve_attack", side_effect=self._resolve_for_quick_win):
            resp = client.post("/explore", data={"area_key": "layer_2_rush"})
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.get_data(as_text=True))
        stage = payload.get("stage_modifier") or {}
        base = stage.get("player_base") or {}
        player_effective = stage.get("player_effective") or {}
        expected_atk = max(1, int(round(int(base.get("atk") or 0) * float(pm["atk"]))))
        expected_def = max(1, int(round(int(base.get("def") or 0) * float(pm["def"]))))
        expected_acc = max(1, int(round(int(base.get("acc") or 0) * float(pm["acc"]))))
        self.assertEqual(int(player_effective.get("atk") or 0), expected_atk)
        self.assertEqual(int(player_effective.get("def") or 0), expected_def)
        self.assertEqual(int(player_effective.get("acc") or 0), expected_acc)
        self.assertIn("ステージ補正:", payload.get("stage_modifier_line") or "")
        self.assertIn("ステージ補正:", payload.get("turn_stage_modifier_line") or "")

    def test_no_modifier_when_disabled(self):
        game_app.STAGE_MODIFIERS_ENABLED = False
        client = self._new_client()
        with patch.object(game_app, "render_template", side_effect=self._mock_battle_render), patch.object(
            game_app, "_world_current_environment", return_value=self._stable_weekly_env()
        ), patch.object(game_app, "resolve_attack", side_effect=self._resolve_for_quick_win):
            resp = client.post("/explore", data={"area_key": "layer_2_rush"})
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.get_data(as_text=True))
        self.assertIsNone(payload.get("stage_modifier"))
        self.assertIsNone(payload.get("stage_modifier_line"))
        self.assertIsNone(payload.get("turn_stage_modifier_line"))

    def test_home_and_map_tendency_visibility_follows_flag(self):
        game_app.STAGE_MODIFIERS_ENABLED = True
        client = self._new_client()
        home_on = client.get("/home")
        map_on = client.get("/map")
        self.assertEqual(home_on.status_code, 200)
        self.assertEqual(map_on.status_code, 200)
        self.assertIn("傾向：", home_on.get_data(as_text=True))
        self.assertIn("傾向：", map_on.get_data(as_text=True))

        game_app.STAGE_MODIFIERS_ENABLED = False
        home_off = client.get("/home")
        map_off = client.get("/map")
        self.assertEqual(home_off.status_code, 200)
        self.assertEqual(map_off.status_code, 200)
        self.assertNotIn("傾向：", home_off.get_data(as_text=True))
        self.assertNotIn("傾向：", map_off.get_data(as_text=True))

    def test_battle_html_shows_style_line_and_enemy_tendency_for_normal_enemy(self):
        game_app.STAGE_MODIFIERS_ENABLED = True
        client = self._new_client()
        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "resolve_attack", side_effect=self._resolve_for_quick_win
        ):
            resp = client.post("/explore", data={"area_key": "layer_2_rush"})
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("獲得コイン", html)
        self.assertIn("ドロップ:", html)
        self.assertIn("敵の特徴:", html)


if __name__ == "__main__":
    unittest.main()
