import json
import os
import tempfile
import time
import unittest
from unittest import mock

import app as game_app
from balance_config import ENEMY_SEED_STATS
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
            "layer_5_labyrinth": (
                {"fast", "heavy"},
                {
                    "lab_guardian_veil",
                    "lab_bulwark_node",
                    "lab_trace_hound",
                    "lab_fault_keeper",
                    "deep_layer_5_reboot_fort_ironbulk",
                    "deep_layer_5_reboot_fort_platehound",
                    "deep_layer_5_reboot_fort_bastion_eye",
                    "deep_layer_5_reboot_enemy_insect_kabuto",
                },
            ),
            "layer_5_pinnacle": (
                {"fast", "unstable", "berserk"},
                {
                    "pin_flare_beast",
                    "pin_rupture_eye",
                    "pin_scorch_fang",
                    "pin_crash_gear",
                    "deep_layer_5_overdrive_haze_mirage_mite",
                    "deep_layer_5_overdrive_haze_fog_lancer",
                    "deep_layer_5_overdrive_haze_glint_drone",
                    "deep_layer_5_overdrive_enemy_insect_bee",
                },
            ),
            "layer_5_reboot": (
                {"fast", "heavy"},
                {
                    "lab_guardian_veil",
                    "lab_bulwark_node",
                    "lab_trace_hound",
                    "lab_fault_keeper",
                    "deep_layer_5_reboot_fort_ironbulk",
                    "deep_layer_5_reboot_fort_platehound",
                    "deep_layer_5_reboot_fort_bastion_eye",
                    "deep_layer_5_reboot_enemy_insect_kabuto",
                },
            ),
            "layer_5_overdrive": (
                {"fast", "unstable", "berserk"},
                {
                    "pin_flare_beast",
                    "pin_rupture_eye",
                    "pin_scorch_fang",
                    "pin_crash_gear",
                    "deep_layer_5_overdrive_haze_mirage_mite",
                    "deep_layer_5_overdrive_haze_fog_lancer",
                    "deep_layer_5_overdrive_haze_glint_drone",
                    "deep_layer_5_overdrive_enemy_insect_bee",
                },
            ),
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

    def test_original_layer5_enemy_definitions_remain_active(self):
        original_normal_keys = {
            "lab_guardian_veil",
            "lab_bulwark_node",
            "lab_trace_hound",
            "lab_fault_keeper",
            "pin_flare_beast",
            "pin_rupture_eye",
            "pin_scorch_fang",
            "pin_crash_gear",
        }
        original_boss_keys = {
            "boss_5_labyrinth_nyx_array": "layer_5_labyrinth",
            "boss_5_pinnacle_ignition_king": "layer_5_pinnacle",
            "boss_5_final_omega_frame": "layer_5_final",
        }
        with game_app.app.app_context():
            db = game_app.get_db()
            for key in sorted(original_normal_keys):
                seed = ENEMY_SEED_STATS[key]
                row = db.execute(
                    "SELECT key, image_path, is_active, is_boss, boss_area_key FROM enemies WHERE key = ?",
                    (key,),
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["key"], key)
                self.assertEqual(row["image_path"], seed["image_path"])
                self.assertEqual(int(row["is_active"]), 1)
                self.assertEqual(int(row["is_boss"] or 0), 0)
                self.assertIsNone(row["boss_area_key"])

            for key, boss_area_key in original_boss_keys.items():
                seed = ENEMY_SEED_STATS[key]
                row = db.execute(
                    "SELECT key, image_path, is_active, is_boss, boss_area_key FROM enemies WHERE key = ?",
                    (key,),
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["key"], key)
                self.assertEqual(row["image_path"], seed["image_path"])
                self.assertEqual(int(row["is_active"]), 1)
                self.assertEqual(int(row["is_boss"] or 0), 1)
                self.assertEqual(row["boss_area_key"], boss_area_key)

    def test_layer5_original_and_deep_keys_do_not_collide(self):
        original_keys = {
            "lab_guardian_veil",
            "lab_bulwark_node",
            "lab_trace_hound",
            "lab_fault_keeper",
            "pin_flare_beast",
            "pin_rupture_eye",
            "pin_scorch_fang",
            "pin_crash_gear",
            "boss_5_labyrinth_nyx_array",
            "boss_5_pinnacle_ignition_king",
            "boss_5_final_omega_frame",
        }
        deep_keys = {key for key in ENEMY_SEED_STATS if key.startswith(("deep_layer_5_", "deep_boss_layer_5_"))}
        self.assertTrue(deep_keys)
        self.assertTrue(original_keys.isdisjoint(deep_keys))

    def test_layer5_enemy_candidate_sets_include_original_and_deep_variants(self):
        original_keys = {
            "lab_guardian_veil",
            "lab_bulwark_node",
            "lab_trace_hound",
            "lab_fault_keeper",
            "pin_flare_beast",
            "pin_rupture_eye",
            "pin_scorch_fang",
            "pin_crash_gear",
        }
        deep_keys = {key for key in ENEMY_SEED_STATS if key.startswith("deep_layer_5_")}
        with game_app.app.app_context():
            db = game_app.get_db()
            for area_key in ("layer_5_labyrinth", "layer_5_pinnacle", "layer_5_reboot", "layer_5_overdrive"):
                allowed = set(game_app.EXPLORE_AREA_ENEMY_KEYS[area_key])
                self.assertTrue(allowed & original_keys)
                self.assertTrue(allowed & deep_keys)
                placeholders = ",".join(["?"] * len(allowed))
                count = db.execute(
                    f"""
                    SELECT COUNT(*) AS c
                    FROM enemies
                    WHERE is_active = 1
                      AND COALESCE(is_boss, 0) = 0
                      AND key IN ({placeholders})
                    """,
                    tuple(allowed),
                ).fetchone()["c"]
                self.assertGreater(int(count), 0)

    def test_layer5_boss_candidate_sets_include_original_and_deep_variants(self):
        original_boss_keys = {
            "boss_5_labyrinth_nyx_array",
            "boss_5_pinnacle_ignition_king",
            "boss_5_final_omega_frame",
        }
        deep_boss_keys = {key for key in ENEMY_SEED_STATS if key.startswith("deep_boss_layer_5_")}
        with game_app.app.app_context():
            db = game_app.get_db()
            seen_boss_keys = set()
            for area_key in (
                "layer_5_labyrinth",
                "layer_5_pinnacle",
                "layer_5_reboot",
                "layer_5_overdrive",
                "layer_5_final",
            ):
                boss = game_app._pick_boss_enemy_for_area(db, area_key, weekly_env=self._stable_weekly_env())
                self.assertIsNotNone(boss)
                rows = db.execute(
                    """
                    SELECT key
                    FROM enemies
                    WHERE is_active = 1
                      AND COALESCE(is_boss, 0) = 1
                      AND boss_area_key = ?
                    """,
                    (area_key,),
                ).fetchall()
                self.assertTrue(rows)
                seen_boss_keys.update(str(row["key"]) for row in rows)
            self.assertTrue(seen_boss_keys & original_boss_keys)
            self.assertTrue(seen_boss_keys & deep_boss_keys)

    def test_layer5_bosses_are_area_specific(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertEqual(game_app._pick_boss_enemy_for_area(db, "layer_5_labyrinth")["key"], "boss_5_labyrinth_nyx_array")
            self.assertEqual(game_app._pick_boss_enemy_for_area(db, "layer_5_pinnacle")["key"], "boss_5_pinnacle_ignition_king")
            self.assertEqual(game_app._pick_boss_enemy_for_area(db, "layer_5_reboot")["key"], "deep_boss_layer_5_reboot_boss_4_forge_elguard")
            self.assertEqual(game_app._pick_boss_enemy_for_area(db, "layer_5_overdrive")["key"], "deep_boss_layer_5_overdrive_boss_4_haze_mirage")
            self.assertEqual(game_app._pick_boss_enemy_for_area(db, "layer_5_final")["key"], "deep_boss_layer_5_final_boss_4_final_ark_zero")

    def test_deep_layer_enemy_stats_exceed_layer4_sources(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            pairs = (
                ("fort_ironbulk", "deep_layer_5_reboot_fort_ironbulk"),
                ("haze_mirage_mite", "deep_layer_5_overdrive_haze_mirage_mite"),
                ("burst_coreling", "deep_layer_5_final_burst_coreling"),
                ("deep_layer_5_reboot_fort_ironbulk", "deep_layer_6_rebuild_deep_layer_5_reboot_fort_ironbulk"),
            )
            for base_key, deep_key in pairs:
                base = db.execute("SELECT hp, atk, def, spd, acc, cri FROM enemies WHERE key = ?", (base_key,)).fetchone()
                deep = db.execute("SELECT hp, atk, def, spd, acc, cri FROM enemies WHERE key = ?", (deep_key,)).fetchone()
                self.assertIsNotNone(base)
                self.assertIsNotNone(deep)
                self.assertGreater(int(deep["hp"]), int(base["hp"]))
                self.assertGreater(int(deep["atk"]), int(base["atk"]))

    def test_deep_layer_enemy_pools_do_not_mix_into_lower_layers(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            low_keys = set()
            for area_key in ("layer_1", "layer_2", "layer_3", "layer_4_forge", "layer_4_haze", "layer_4_burst"):
                for _ in range(16):
                    low_keys.add(str(game_app._pick_enemy_for_area(db, area_key, weekly_env=self._stable_weekly_env())["key"]))
            self.assertFalse(any(key.startswith("deep_layer_5") or key.startswith("deep_layer_6") for key in low_keys))

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
