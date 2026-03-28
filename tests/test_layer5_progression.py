import json
import os
import tempfile
import time
import unittest
from unittest import mock

import app as game_app
import init_db


class Layer5ProgressionTests(unittest.TestCase):
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
                VALUES (?, ?, ?, 1, 60, 4)
                """,
                ("layer5_tester", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("layer5_tester",),
            ).fetchone()["id"]
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (self.user_id, "Layer5Bot", now, now),
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

            self.legs_part_key = pick_key("LEGS")
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
                    self.legs_part_key,
                ),
            )
            db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (self.robot_id, self.user_id))
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
            session["username"] = "layer5_tester"
        return client

    def _activate_boss_alert(self, area_key, boss_key):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
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

    def _insert_fixed_boss_defeat(self, area_key, enemy_key):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    now,
                    game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                    json.dumps(
                        {
                            "area_key": area_key,
                            "enemy_key": enemy_key,
                            "enemy_name": enemy_key,
                            "boss_kind": "fixed",
                        },
                        ensure_ascii=False,
                    ),
                    self.user_id,
                ),
            )
            db.commit()

    def test_layer5_enemy_pools_match_area_traits(self):
        expected = {
            "layer_5_labyrinth": ({"fast", "heavy"}, {"lab_guardian_veil", "lab_bulwark_node", "lab_trace_hound", "lab_fault_keeper"}),
            "layer_5_pinnacle": ({"unstable", "berserk"}, {"pin_flare_beast", "pin_rupture_eye", "pin_scorch_fang", "pin_crash_gear"}),
        }
        with game_app.app.app_context():
            db = game_app.get_db()
            for area_key, (traits, keys) in expected.items():
                seen = set()
                for _ in range(24):
                    enemy = dict(game_app._pick_enemy_for_area(db, area_key, weekly_env=self._stable_weekly_env()))
                    seen.add(str(enemy["key"]))
                    self.assertIn(str(enemy["key"]), keys)
                    self.assertIn(str(enemy.get("trait") or ""), traits)
                self.assertTrue(seen)

    def test_layer5_bosses_are_area_specific(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertEqual(game_app._pick_boss_enemy_for_area(db, "layer_5_labyrinth")["key"], "boss_5_labyrinth_nyx_array")
            self.assertEqual(game_app._pick_boss_enemy_for_area(db, "layer_5_pinnacle")["key"], "boss_5_pinnacle_ignition_king")
            self.assertEqual(game_app._pick_boss_enemy_for_area(db, "layer_5_final")["key"], "boss_5_final_omega_frame")

    def test_layer5_area_requires_unlock_then_allows_explore(self):
        client = self._new_client()
        locked_resp = client.post("/explore", data={"area_key": "layer_5_labyrinth"}, follow_redirects=True)
        self.assertEqual(locked_resp.status_code, 200)
        self.assertIn("その探索先は未解放です。第4層ボス撃破で解放", locked_resp.get_data(as_text=True))

        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET max_unlocked_layer = 5 WHERE id = ?", (self.user_id,))
            db.commit()
        with mock.patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), mock.patch.object(
            game_app, "_has_area_boss_candidates", return_value=False
        ), mock.patch.object(game_app, "resolve_attack", side_effect=self._resolve_for_win):
            open_resp = client.post("/explore", data={"area_key": "layer_5_labyrinth"}, follow_redirects=True)
        self.assertEqual(open_resp.status_code, 200)
        self.assertIn('name="area_key" value="layer_5_labyrinth"', open_resp.get_data(as_text=True))

    def test_layer5_final_unlock_requires_two_area_bosses(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET max_unlocked_layer = 5 WHERE id = ?", (self.user_id,))
            db.commit()
            user = db.execute("SELECT id, max_unlocked_layer FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertFalse(game_app._is_area_unlocked(user, "layer_5_final", db=db))

        self._insert_fixed_boss_defeat("layer_5_labyrinth", "boss_5_labyrinth_nyx_array")
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT id, max_unlocked_layer FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertFalse(game_app._is_area_unlocked(user, "layer_5_final", db=db))

        self._insert_fixed_boss_defeat("layer_5_pinnacle", "boss_5_pinnacle_ignition_king")
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT id, max_unlocked_layer FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertTrue(game_app._is_area_unlocked(user, "layer_5_final", db=db))

    def test_layer5_boss_defeat_grants_decor_without_duplicate(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET max_unlocked_layer = 5 WHERE id = ?", (self.user_id,))
            db.commit()
        self._activate_boss_alert("layer_5_labyrinth", "boss_5_labyrinth_nyx_array")
        client = self._new_client()
        with mock.patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), mock.patch.object(
            game_app, "resolve_attack", side_effect=self._resolve_for_win
        ):
            resp = client.post("/explore", data={"area_key": "layer_5_labyrinth", "boss_enter": "1"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("観測群冠", resp.get_data(as_text=True))

        with game_app.app.app_context():
            db = game_app.get_db()
            decor_count = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM user_decor_inventory udi
                JOIN robot_decor_assets rda ON rda.id = udi.decor_asset_id
                WHERE udi.user_id = ? AND rda.key = 'nyx_array_crest_001'
                """,
                (self.user_id,),
            ).fetchone()["c"]
            self.assertEqual(int(decor_count), 1)

        self._activate_boss_alert("layer_5_labyrinth", "boss_5_labyrinth_nyx_array")
        with mock.patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), mock.patch.object(
            game_app, "resolve_attack", side_effect=self._resolve_for_win
        ):
            client.post("/explore", data={"area_key": "layer_5_labyrinth", "boss_enter": "1"}, follow_redirects=True)
        with game_app.app.app_context():
            db = game_app.get_db()
            decor_count = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM user_decor_inventory udi
                JOIN robot_decor_assets rda ON rda.id = udi.decor_asset_id
                WHERE udi.user_id = ? AND rda.key = 'nyx_array_crest_001'
                """,
                (self.user_id,),
            ).fetchone()["c"]
            self.assertEqual(int(decor_count), 1)

    def test_layer5_drop_audit_payload_keeps_growth_tendency(self):
        payload = game_app._drop_audit_payload(
            "layer_5_labyrinth",
            1,
            {
                "drop_type": "parts_1",
                "part_type": "LEGS",
                "part_key": self.legs_part_key,
                "rarity": "N",
                "plus": 0,
                "growth_tendency_key": "labyrinth",
                "growth_tendency_label": "観測育成",
            },
        )
        self.assertEqual(payload.get("area_key"), "layer_5_labyrinth")
        self.assertEqual(int(payload.get("battle_no") or 0), 1)
        self.assertEqual(payload.get("growth_tendency_key"), "labyrinth")
        self.assertEqual(payload.get("growth_tendency_label"), "観測育成")


if __name__ == "__main__":
    unittest.main()
