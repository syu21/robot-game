import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class BuildTypeBattleProfileTests(unittest.TestCase):
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
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins) VALUES (?, ?, ?, 1, 0)",
                ("build_type_tester", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("build_type_tester",),
            ).fetchone()["id"]
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (self.user_id, "ProfileBot", now, now),
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
            self.robot_id = robot_id

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
    def _resolve_for_fast_battle(att_atk, att_acc, att_cri, def_def, def_acc, **kwargs):
        if int(att_atk) >= 5:
            return 999, False, {"miss": False, "hit_chance": 1.0, "att_acc": int(att_acc), "def_acc": int(def_acc), "hit_bonus": 0.0}
        return 0, False, {"miss": False, "hit_chance": 1.0, "att_acc": int(att_acc), "def_acc": int(def_acc), "hit_bonus": 0.0}

    @staticmethod
    def _mock_battle_render(template_name, **context):
        if template_name != "battle.html" or not context.get("explore_mode"):
            return ""
        logs = context.get("turn_logs") or []
        first = logs[0] if logs else {}
        return json.dumps(
            {
                "build_profile_line": first.get("build_profile_line"),
                "keys": sorted(list(first.keys())) if first else [],
                "max_turn": max(int(r["turn"]) for r in logs) if logs else 0,
            },
            ensure_ascii=False,
        )

    def _set_all_part_instance_elements(self, element):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app._ensure_robot_instance_part_instances(db, self.robot_id)
            row = db.execute(
                """
                SELECT head_part_instance_id, r_arm_part_instance_id, l_arm_part_instance_id, legs_part_instance_id
                FROM robot_instance_parts WHERE robot_instance_id = ?
                """,
                (self.robot_id,),
            ).fetchone()
            ids = [int(row["head_part_instance_id"]), int(row["r_arm_part_instance_id"]), int(row["l_arm_part_instance_id"]), int(row["legs_part_instance_id"])]
            for pid in ids:
                db.execute("UPDATE part_instances SET element = ? WHERE id = ?", (element, pid))
            db.commit()

    def _set_mixed_part_instance_elements(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app._ensure_robot_instance_part_instances(db, self.robot_id)
            row = db.execute(
                """
                SELECT head_part_instance_id, r_arm_part_instance_id, l_arm_part_instance_id, legs_part_instance_id
                FROM robot_instance_parts WHERE robot_instance_id = ?
                """,
                (self.robot_id,),
            ).fetchone()
            ids = [int(row["head_part_instance_id"]), int(row["r_arm_part_instance_id"]), int(row["l_arm_part_instance_id"]), int(row["legs_part_instance_id"])]
            elems = ["FIRE", "FIRE", "WATER", "FIRE"]
            for pid, elem in zip(ids, elems):
                db.execute("UPDATE part_instances SET element = ? WHERE id = ?", (elem, pid))
            db.commit()

    def _run_and_get_payload(self):
        with patch.object(game_app, "render_template", side_effect=self._mock_battle_render), patch.object(
            game_app, "_world_current_environment", return_value=self._stable_weekly_env()
        ), patch.object(game_app, "resolve_attack", side_effect=self._resolve_for_fast_battle):
            with game_app.app.test_client() as client:
                with client.session_transaction() as session:
                    session["user_id"] = self.user_id
                    session["username"] = "build_type_tester"
                resp = client.post("/explore", data={"area_key": "layer_1"})
                self.assertEqual(resp.status_code, 200)
                return json.loads(resp.get_data(as_text=True))

    def test_stable_build_shows_stable_range_line_and_crit_modifier(self):
        self._set_all_part_instance_elements("FIRE")
        payload = self._run_and_get_payload()
        line = payload.get("build_profile_line") or ""
        self.assertIn("ビルド: 安定型", line)
        self.assertIn("0.95-1.05", line)
        self.assertIn("会心倍率補正: x1.00", line)
        self.assertLessEqual(payload.get("max_turn", 0), game_app.EXPLORE_MAX_TURNS)
        self.assertIn("turn", payload.get("keys", []))

    def test_burst_build_shows_burst_range_line_and_crit_modifier(self):
        self._set_mixed_part_instance_elements()
        payload = self._run_and_get_payload()
        line = payload.get("build_profile_line") or ""
        self.assertIn("ビルド: 爆発型", line)
        self.assertIn("0.80-1.25", line)
        self.assertIn("会心倍率補正: x1.15", line)
        self.assertLessEqual(payload.get("max_turn", 0), game_app.EXPLORE_MAX_TURNS)


if __name__ == "__main__":
    unittest.main()
