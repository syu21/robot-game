import json
import os
import tempfile
import time
import unittest

import app as game_app
from balance_config import DEEP_LAYER_VARIANT_MULTIPLIERS, ENEMY_SEED_STATS
import init_db


RESERVED_NORMAL_KEYS = {
    "lab_guardian_veil",
    "lab_bulwark_node",
    "lab_trace_hound",
    "lab_fault_keeper",
    "pin_flare_beast",
    "pin_rupture_eye",
    "pin_scorch_fang",
    "pin_crash_gear",
}
RESERVED_BOSS_KEYS = {
    "boss_5_labyrinth_nyx_array": "reserved_future_labyrinth",
    "boss_5_pinnacle_ignition_king": "reserved_future_pinnacle",
    "boss_5_final_omega_frame": "reserved_future_omega",
}
PUBLIC_DEEP_AREAS = (
    "layer_5_reboot",
    "layer_5_overdrive",
    "layer_5_final",
    "layer_6_rebuild",
    "layer_6_core",
    "layer_6_final",
    "layer_7_echo",
    "layer_7_chaos",
    "layer_7_final",
)


class Layer5ProgressionTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        init_db.main()
        game_app.app.config["TESTING"] = True
        game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = True

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
            self.user_id = db.execute("SELECT id FROM users WHERE username = ?", ("layer5_tester",)).fetchone()["id"]
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = True
        self.tmpdir.cleanup()

    @staticmethod
    def _stable_weekly_env():
        return {"element": "NORMAL", "mode": "安定", "enemy_spawn_bonus": 0.0, "drop_bonus": 0.0, "reason": "test"}

    def _insert_fixed_boss_defeat(self, area_key, enemy_key):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    int(time.time()),
                    game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                    json.dumps(
                        {"area_key": area_key, "enemy_key": enemy_key, "enemy_name": enemy_key, "boss_kind": "fixed"},
                        ensure_ascii=False,
                    ),
                    self.user_id,
                ),
            )
            db.commit()

    def test_reserved_layer5_enemy_definitions_remain_active(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            for key in sorted(RESERVED_NORMAL_KEYS):
                seed = ENEMY_SEED_STATS[key]
                row = db.execute("SELECT key, image_path, is_active, is_boss, boss_area_key FROM enemies WHERE key = ?", (key,)).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["image_path"], seed["image_path"])
                self.assertEqual(int(row["is_active"]), 1)
                self.assertEqual(int(row["is_boss"] or 0), 0)
                self.assertIsNone(row["boss_area_key"])

            for key, reserved_area in RESERVED_BOSS_KEYS.items():
                seed = ENEMY_SEED_STATS[key]
                row = db.execute("SELECT key, image_path, is_active, is_boss, boss_area_key FROM enemies WHERE key = ?", (key,)).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["image_path"], seed["image_path"])
                self.assertEqual(int(row["is_active"]), 1)
                self.assertEqual(int(row["is_boss"] or 0), 1)
                self.assertEqual(row["boss_area_key"], reserved_area)

    def test_reserved_layer5_content_is_not_in_public_layer5_to_7_pools(self):
        reserved = RESERVED_NORMAL_KEYS | set(RESERVED_BOSS_KEYS)
        for area_key in PUBLIC_DEEP_AREAS:
            self.assertTrue(set(game_app.EXPLORE_AREA_ENEMY_KEYS[area_key]))
            self.assertTrue(set(game_app.EXPLORE_AREA_ENEMY_KEYS[area_key]).isdisjoint(reserved))
            self.assertNotIn(game_app.FIXED_BOSS_KEY_BY_AREA[area_key], reserved)

    def test_public_layer5_to_7_boss_picks_are_current_deep_variants(self):
        expected = {
            "layer_5_reboot": "deep_boss_layer_5_reboot_boss_4_forge_elguard",
            "layer_5_overdrive": "deep_boss_layer_5_overdrive_boss_4_haze_mirage",
            "layer_5_final": "deep_boss_layer_5_final_boss_4_final_ark_zero",
            "layer_6_rebuild": "deep_boss_layer_6_rebuild_deep_boss_layer_5_reboot_boss_4_forge_elguard",
            "layer_6_core": "deep_boss_layer_6_core_deep_boss_layer_5_overdrive_boss_4_haze_mirage",
            "layer_6_final": "deep_boss_layer_6_final_deep_boss_layer_5_final_boss_4_final_ark_zero",
            "layer_7_echo": "deep_boss_layer_7_echo_boss_4_haze_mirage",
            "layer_7_chaos": "deep_boss_layer_7_chaos_boss_4_burst_volterio",
            "layer_7_final": "deep_boss_layer_7_final_boss_4_final_ark_zero",
        }
        with game_app.app.app_context():
            db = game_app.get_db()
            for area_key, boss_key in expected.items():
                self.assertEqual(game_app._pick_boss_enemy_for_area(db, area_key, weekly_env=self._stable_weekly_env())["key"], boss_key)

    def test_layer5_to_7_areas_exist_and_are_nonempty(self):
        area_keys = {area["key"] for area in game_app.EXPLORE_AREAS}
        for area_key in PUBLIC_DEEP_AREAS:
            self.assertIn(area_key, area_keys)
            self.assertGreater(len(game_app.EXPLORE_AREA_ENEMY_KEYS[area_key]), 0)
            self.assertIn(area_key, game_app.AREA_BOSS_KEYS)

        for retired_key in ("layer_5_labyrinth", "layer_5_pinnacle"):
            self.assertNotIn(retired_key, area_keys)
            self.assertNotIn(retired_key, game_app.AREA_BOSS_KEYS)
            self.assertNotIn(retired_key, game_app.AREA_BOSS_ALERT_AREAS)

    def test_deep_keys_do_not_collide_with_reserved_keys(self):
        reserved = RESERVED_NORMAL_KEYS | set(RESERVED_BOSS_KEYS)
        deep_keys = {key for key in ENEMY_SEED_STATS if key.startswith(("deep_layer_", "deep_boss_layer_"))}
        self.assertTrue(deep_keys)
        self.assertTrue(reserved.isdisjoint(deep_keys))

    def test_deep_layer_enemy_stats_progress_by_total_power(self):
        pairs = (
            ("fort_ironbulk", "deep_layer_5_reboot_fort_ironbulk"),
            ("haze_mirage_mite", "deep_layer_5_overdrive_haze_mirage_mite"),
            ("deep_layer_5_reboot_fort_ironbulk", "deep_layer_6_rebuild_deep_layer_5_reboot_fort_ironbulk"),
            ("deep_layer_6_rebuild_deep_layer_5_reboot_fort_ironbulk", "deep_layer_7_echo_enemy16"),
        )
        with game_app.app.app_context():
            db = game_app.get_db()
            for base_key, deep_key in pairs:
                base = db.execute("SELECT hp, atk, def, spd, acc, cri FROM enemies WHERE key = ?", (base_key,)).fetchone()
                deep = db.execute("SELECT hp, atk, def, spd, acc, cri FROM enemies WHERE key = ?", (deep_key,)).fetchone()
                self.assertIsNotNone(base)
                self.assertIsNotNone(deep)
                base_total = sum(int(base[stat]) for stat in ("hp", "atk", "def", "spd", "acc", "cri"))
                deep_total = sum(int(deep[stat]) for stat in ("hp", "atk", "def", "spd", "acc", "cri"))
                self.assertGreater(deep_total, base_total)

    def test_deep_layer_enemy_pools_do_not_mix_into_lower_layers(self):
        low_keys = set()
        with game_app.app.app_context():
            db = game_app.get_db()
            for area_key in ("layer_1", "layer_2", "layer_3", "layer_4_forge", "layer_4_haze", "layer_4_burst"):
                for _ in range(12):
                    low_keys.add(str(game_app._pick_enemy_for_area(db, area_key, weekly_env=self._stable_weekly_env())["key"]))
        self.assertFalse(any(key.startswith("deep_layer_5") or key.startswith("deep_layer_6") or key.startswith("deep_layer_7") for key in low_keys))

    def test_final_unlock_chain_uses_current_deep_bosses_only(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET max_unlocked_layer = 5 WHERE id = ?", (self.user_id,))
            db.commit()
            user = db.execute("SELECT id, max_unlocked_layer, is_admin FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertFalse(game_app._is_area_unlocked(user, "layer_5_final", db=db))

        self._insert_fixed_boss_defeat("layer_5_reboot", "deep_boss_layer_5_reboot_boss_4_forge_elguard")
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT id, max_unlocked_layer, is_admin FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertFalse(game_app._is_area_unlocked(user, "layer_5_final", db=db))

        self._insert_fixed_boss_defeat("layer_5_overdrive", "deep_boss_layer_5_overdrive_boss_4_haze_mirage")
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT id, max_unlocked_layer, is_admin FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertTrue(game_app._is_area_unlocked(user, "layer_5_final", db=db))

            boss = db.execute("SELECT * FROM enemies WHERE key = 'deep_boss_layer_5_final_boss_4_final_ark_zero'").fetchone()
            self.assertEqual(game_app._maybe_unlock_next_layer(db, self.user_id, user, "layer_5_final", boss), 6)
            user = db.execute("SELECT id, max_unlocked_layer, is_admin FROM users WHERE id = ?", (self.user_id,)).fetchone()
            boss6 = db.execute("SELECT * FROM enemies WHERE key = 'deep_boss_layer_6_final_deep_boss_layer_5_final_boss_4_final_ark_zero'").fetchone()
            self.assertEqual(game_app._maybe_unlock_next_layer(db, self.user_id, user, "layer_6_final", boss6), 7)
            user = db.execute("SELECT id, max_unlocked_layer, is_admin FROM users WHERE id = ?", (self.user_id,)).fetchone()
            boss7 = db.execute("SELECT * FROM enemies WHERE key = 'deep_boss_layer_7_final_boss_4_final_ark_zero'").fetchone()
            self.assertIsNone(game_app._maybe_unlock_next_layer(db, self.user_id, user, "layer_7_final", boss7))

    def test_old_layer5_boss_defeats_do_not_unlock_current_final(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET max_unlocked_layer = 5 WHERE id = ?", (self.user_id,))
            db.commit()
        self._insert_fixed_boss_defeat("reserved_future_labyrinth", "boss_5_labyrinth_nyx_array")
        self._insert_fixed_boss_defeat("reserved_future_pinnacle", "boss_5_pinnacle_ignition_king")
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT id, max_unlocked_layer, is_admin FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertFalse(game_app._is_area_unlocked(user, "layer_5_final", db=db))

    def test_release_flags_are_independent_and_private_by_default(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            rows = {row["key"]: int(row["is_public"] or 0) for row in db.execute("SELECT key, is_public FROM release_flags").fetchall()}
        self.assertEqual(rows.get("layer5"), 0)
        self.assertEqual(rows.get("layer6"), 0)
        self.assertEqual(rows.get("layer7"), 0)
        self.assertEqual(DEEP_LAYER_VARIANT_MULTIPLIERS[7]["normal"]["layer_7_echo"], 1.22)

    def test_non_public_direct_access_denied_for_general_user_but_admin_can_view(self):
        game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = False
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET is_admin = 0, max_unlocked_layer = 7 WHERE id = ?", (self.user_id,))
            db.commit()
            user = db.execute("SELECT id, is_admin, max_unlocked_layer FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertFalse(game_app._area_visible_for_viewer(db, "layer_7_echo", user_row=user))

            db.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (self.user_id,))
            db.commit()
            admin = db.execute("SELECT id, is_admin, max_unlocked_layer FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertTrue(game_app._area_visible_for_viewer(db, "layer_7_echo", user_row=admin))

    def test_reserved_areas_are_not_general_sortie_targets(self):
        area_keys = {area["key"] for area in game_app.EXPLORE_AREAS}
        for area_key in game_app.RESERVED_FUTURE_LAYER5_AREA_KEYS:
            self.assertNotIn(area_key, area_keys)
            self.assertIn(area_key, game_app.AREA_BOSS_KEYS)
            self.assertIsNone(game_app._release_feature_for_area(area_key))


if __name__ == "__main__":
    unittest.main()
