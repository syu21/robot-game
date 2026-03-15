import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class BattleOverlayCleanupTests(unittest.TestCase):
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
                ("overlay_tester", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("overlay_tester",),
            ).fetchone()["id"]
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (self.user_id, "OverlayRunner", now, now),
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
            session["username"] = "overlay_tester"
        return client

    def _activate_alert_for_layer1(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            boss_key = game_app.LAYER_BOSS_KEY_BY_LAYER[1]
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
                (self.user_id, "layer_1", int(boss_id), now + 3600, now),
            )
            db.commit()

    def test_overlay_absent_on_home_after_battle_to_home_transition(self):
        self._activate_alert_for_layer1()
        client = self._new_client()
        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "resolve_attack", side_effect=self._resolve_for_win
        ):
            battle_resp = client.post("/explore", data={"area_key": "layer_1", "boss_enter": "1"})
        self.assertEqual(battle_resp.status_code, 200)
        battle_html = battle_resp.get_data(as_text=True)
        self.assertIn('id="battle-ritual-overlay"', battle_html)

        home_resp = client.get("/home")
        self.assertEqual(home_resp.status_code, 200)
        home_html = home_resp.get_data(as_text=True)
        self.assertEqual(home_html.count('id="battle-ritual-overlay"'), 0)

    def test_overlay_absent_on_home_direct_access(self):
        client = self._new_client()
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertEqual(html.count('id="battle-ritual-overlay"'), 0)

    def test_overlay_absent_on_build_direct_access(self):
        client = self._new_client()
        resp = client.get("/build")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertEqual(html.count('id="battle-ritual-overlay"'), 0)

    def test_overlay_absent_on_build_after_battle_transition(self):
        self._activate_alert_for_layer1()
        client = self._new_client()
        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "resolve_attack", side_effect=self._resolve_for_win
        ):
            battle_resp = client.post("/explore", data={"area_key": "layer_1", "boss_enter": "1"})
        self.assertEqual(battle_resp.status_code, 200)
        self.assertIn('id="battle-ritual-overlay"', battle_resp.get_data(as_text=True))

        build_resp = client.get("/build")
        self.assertEqual(build_resp.status_code, 200)
        build_html = build_resp.get_data(as_text=True)
        self.assertEqual(build_html.count('id="battle-ritual-overlay"'), 0)

    def test_feature_flag_off_does_not_render_overlay_dom(self):
        self._activate_alert_for_layer1()
        client = self._new_client()
        with patch.object(game_app, "BATTLE_RITUAL_OVERLAY_ENABLED", False), patch.object(
            game_app, "_world_current_environment", return_value=self._stable_weekly_env()
        ), patch.object(game_app, "resolve_attack", side_effect=self._resolve_for_win):
            battle_resp = client.post("/explore", data={"area_key": "layer_1", "boss_enter": "1"})
        self.assertEqual(battle_resp.status_code, 200)
        battle_html = battle_resp.get_data(as_text=True)
        self.assertEqual(battle_html.count('id="battle-ritual-overlay"'), 0)

    def test_base_registers_pageshow_cleanup_hook(self):
        client = self._new_client()
        resp = client.get("/build")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('/static/base_cleanup_v2.js', html)

    def test_debug_ui_effects_off_sets_body_class(self):
        client = self._new_client()
        resp = client.get("/debug/ui_effects_off", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        build_resp = client.get("/build")
        self.assertEqual(build_resp.status_code, 200)
        html = build_resp.get_data(as_text=True)
        self.assertIn("ui-effects-off", html)

    def test_ui_effects_off_session_disables_battle_overlay(self):
        self._activate_alert_for_layer1()
        client = self._new_client()
        with client.session_transaction() as session:
            session["ui_effects_enabled"] = False
        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "resolve_attack", side_effect=self._resolve_for_win
        ):
            battle_resp = client.post("/explore", data={"area_key": "layer_1", "boss_enter": "1"})
        self.assertEqual(battle_resp.status_code, 200)
        battle_html = battle_resp.get_data(as_text=True)
        self.assertEqual(battle_html.count('id="battle-ritual-overlay"'), 0)


if __name__ == "__main__":
    unittest.main()
