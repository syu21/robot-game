import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class AdminBalanceRouteTests(unittest.TestCase):
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
                ("admin_balance_tester", "x", now),
            )
            user_id = db.execute("SELECT id FROM users WHERE username = ?", ("admin_balance_tester",)).fetchone()["id"]
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (user_id, "AdminBalanceBot", now, now),
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

    def _mock_render(self, template_name, **context):
        if template_name != "admin_balance.html":
            return ""
        payload = {
            "simulation_result": context.get("simulation_result"),
            "enemy_top_rows": context.get("enemy_top_rows"),
            "enemy_bottom_rows": context.get("enemy_bottom_rows"),
            "message": context.get("message"),
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def test_admin_balance_same_seed_returns_same_summary(self):
        query = "/admin/balance?run=1&area_key=layer_2&n=200&sample_mode=all_robots&seed=123"
        with patch.object(game_app, "render_template", side_effect=self._mock_render):
            with game_app.app.test_client() as client:
                with client.session_transaction() as session:
                    session["user_id"] = self.user_id
                    session["username"] = "admin_balance_tester"

                resp1 = client.get(query)
                resp2 = client.get(query)
                self.assertEqual(resp1.status_code, 200)
                self.assertEqual(resp2.status_code, 200)
                payload1 = json.loads(resp1.get_data(as_text=True))
                payload2 = json.loads(resp2.get_data(as_text=True))
                self.assertIsNotNone(payload1["simulation_result"])
                self.assertEqual(payload1, payload2)

    def test_admin_balance_same_seed_reproducible_with_archetype_on_off(self):
        q_on = "/admin/balance?run=1&area_key=layer_2&n=200&sample_mode=all_robots&seed=123&enable_archetype=1"
        q_off = "/admin/balance?run=1&area_key=layer_2&n=200&sample_mode=all_robots&seed=123"
        with patch.object(game_app, "render_template", side_effect=self._mock_render):
            with game_app.app.test_client() as client:
                with client.session_transaction() as session:
                    session["user_id"] = self.user_id
                    session["username"] = "admin_balance_tester"
                on1 = json.loads(client.get(q_on).get_data(as_text=True))
                on2 = json.loads(client.get(q_on).get_data(as_text=True))
                off1 = json.loads(client.get(q_off).get_data(as_text=True))
                off2 = json.loads(client.get(q_off).get_data(as_text=True))
                self.assertEqual(on1, on2)
                self.assertEqual(off1, off2)

    def test_admin_balance_power_filter_zero_rows(self):
        query = "/admin/balance?run=1&area_key=layer_3&n=200&sample_mode=all_robots&seed=42&power_min=999999"
        with patch.object(game_app, "render_template", side_effect=self._mock_render):
            with game_app.app.test_client() as client:
                with client.session_transaction() as session:
                    session["user_id"] = self.user_id
                    session["username"] = "admin_balance_tester"
                resp = client.get(query)
                self.assertEqual(resp.status_code, 200)
                payload = json.loads(resp.get_data(as_text=True))
                self.assertIsNone(payload["simulation_result"])
                self.assertIn("0件", payload["message"])


if __name__ == "__main__":
    unittest.main()
