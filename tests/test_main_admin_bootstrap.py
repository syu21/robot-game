import os
import tempfile
import time
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash

import app as game_app
import init_db


class MainAdminBootstrapTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, last_seen_at, is_admin, is_admin_protected, wins, coins, max_unlocked_layer)
                VALUES (?, ?, ?, ?, 0, 0, 0, 0, 1)
                """,
                ("admin", generate_password_hash("pw"), now, now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()["id"])
            db.commit()
            game_app._ensure_main_admin_account_ready(db)

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

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
            sess["username"] = game_app.MAIN_ADMIN_USERNAME
        return client

    def test_bootstrap_renames_and_grants_all_parts(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute(
                """
                SELECT id, username, is_admin, is_admin_protected, layer2_unlocked, max_unlocked_layer, active_robot_id
                FROM users
                WHERE id = ?
                """,
                (self.user_id,),
            ).fetchone()
            self.assertEqual(user["username"], game_app.MAIN_ADMIN_USERNAME)
            self.assertEqual(int(user["is_admin"] or 0), 1)
            self.assertEqual(int(user["is_admin_protected"] or 0), 1)
            self.assertEqual(int(user["layer2_unlocked"] or 0), 1)
            self.assertEqual(int(user["max_unlocked_layer"] or 0), game_app.MAX_UNLOCKABLE_LAYER)
            self.assertIsNotNone(user["active_robot_id"])

            total_parts = int(
                db.execute("SELECT COUNT(*) AS c FROM robot_parts WHERE is_active = 1").fetchone()["c"] or 0
            )
            owned_parts = int(
                db.execute(
                    """
                    SELECT COUNT(DISTINCT rp.key) AS c
                    FROM part_instances pi
                    JOIN robot_parts rp ON rp.id = pi.part_id
                    WHERE pi.user_id = ?
                    """,
                    (self.user_id,),
                ).fetchone()["c"]
                or 0
            )
            self.assertEqual(owned_parts, total_parts)

            rip = db.execute(
                """
                SELECT head_key, r_arm_key, l_arm_key, legs_key
                FROM robot_instance_parts
                WHERE robot_instance_id = ?
                """,
                (int(user["active_robot_id"]),),
            ).fetchone()
            self.assertEqual(rip["head_key"], game_app.MAIN_ADMIN_FIRE_LOADOUT["head"])
            self.assertEqual(rip["r_arm_key"], game_app.MAIN_ADMIN_FIRE_LOADOUT["r_arm"])
            self.assertEqual(rip["l_arm_key"], game_app.MAIN_ADMIN_FIRE_LOADOUT["l_arm"])
            self.assertEqual(rip["legs_key"], game_app.MAIN_ADMIN_FIRE_LOADOUT["legs"])

    def test_main_admin_can_access_all_special_areas(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute(
                "SELECT id, username, is_admin, max_unlocked_layer FROM users WHERE id = ?",
                (self.user_id,),
            ).fetchone()
            self.assertTrue(game_app._is_area_unlocked(user, "layer_4_final", db=db))
            self.assertTrue(game_app._is_area_unlocked(user, "layer_5_final", db=db))

    def test_home_shows_direct_boss_button_for_main_admin(self):
        client = self._client()
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ボスへ直行", resp.get_data(as_text=True))

    def test_main_admin_can_enter_boss_without_alert(self):
        client = self._client()
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                "UPDATE enemies SET hp = 1, atk = 1, def = 1, spd = 1, acc = 1, cri = 1 WHERE key = ?",
                ("boss_5_final_omega_frame",),
            )
            db.commit()
        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "resolve_attack", side_effect=self._resolve_for_win
        ):
            resp = client.post(
                "/explore",
                data={"area_key": "layer_5_final", "boss_enter": "1"},
                follow_redirects=True,
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        self.assertNotIn("有効なボス警報がありません", body)
        self.assertIn("終機オメガフレーム", body)


if __name__ == "__main__":
    unittest.main()
