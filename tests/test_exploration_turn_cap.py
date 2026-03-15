import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class ExplorationTurnCapTests(unittest.TestCase):
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
                "INSERT INTO users (username, password_hash, created_at, is_admin) VALUES (?, ?, ?, 1)",
                ("turn_cap_tester", "x", now),
            )
            user_id = db.execute("SELECT id FROM users WHERE username = ?", ("turn_cap_tester",)).fetchone()["id"]
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (user_id, "TestBot", now, now),
            )
            robot_id = db.execute("SELECT id FROM robot_instances WHERE user_id = ?", (user_id,)).fetchone()["id"]

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
            db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (robot_id, user_id))
            db.commit()
            self.user_id = user_id

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _mock_battle_render(self, template_name, **context):
        if template_name != "battle.html" or not context.get("explore_mode"):
            return ""
        turn_logs = context.get("turn_logs") or []
        turns = [int(log["turn"]) for log in turn_logs]
        return json.dumps(
            {
                "max_turn": max(turns) if turns else 0,
                "keys": sorted(list(turn_logs[0].keys())) if turn_logs else [],
            },
            ensure_ascii=False,
        )

    def test_explore_turns_never_exceed_cap_across_multiple_runs(self):
        required_turn_log_keys = {
            "turn",
            "player_action",
            "enemy_action",
            "enemy_before",
            "enemy_after",
            "player_before",
            "player_after",
            "player_damage",
            "enemy_damage",
            "critical",
            "player_skill",
            "player_max",
            "enemy_max",
        }
        with patch.object(game_app, "render_template", side_effect=self._mock_battle_render):
            with game_app.app.test_client() as client:
                with client.session_transaction() as session:
                    session["user_id"] = self.user_id
                    session["username"] = "turn_cap_tester"

                for _ in range(20):
                    resp = client.post("/explore", data={"area_key": "layer_1"}, follow_redirects=True)
                    self.assertEqual(resp.status_code, 200)
                    body = resp.get_data(as_text=True)
                    if "<!doctype html>" in body.lower() or not body.strip():
                        # 0.5%ボス警報時はhomeへ戻るため、次ループで継続確認する。
                        continue
                    payload = json.loads(body)
                    self.assertLessEqual(payload["max_turn"], game_app.EXPLORE_MAX_TURNS)
                    if payload["keys"]:
                        self.assertTrue(required_turn_log_keys.issubset(set(payload["keys"])))


if __name__ == "__main__":
    unittest.main()
