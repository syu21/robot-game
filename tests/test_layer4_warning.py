import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FixedRandom:
    def __init__(self, value):
        self.value = float(value)

    def random(self):
        return self.value


class Layer4WarningTests(unittest.TestCase):
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
                VALUES (?, 'x', ?, 0, 0, 0, 4)
                """,
                ("layer4_warning_tester", now),
            )
            self.user_id = db.execute("SELECT id FROM users WHERE username = ?", ("layer4_warning_tester",)).fetchone()["id"]
            for area_key in game_app.LAYER4_SUBAREA_KEYS:
                db.execute(
                    """
                    INSERT INTO enemies
                    (key, name_ja, image_path, tier, element, hp, atk, def, spd, acc, cri, faction, is_boss, boss_area_key, is_active)
                    VALUES (?, ?, 'assets/placeholder_enemy.png', 4, 'NORMAL', 10, 1, 1, 1, 1, 1, 'neutral', 1, ?, 1)
                    ON CONFLICT(key) DO UPDATE SET is_active = 1, is_boss = 1, boss_area_key = excluded.boss_area_key
                    """,
                    (f"test_{area_key}_boss", f"{area_key}試験機", area_key),
                )
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def test_warning_spawn_profile_steps(self):
        self.assertEqual(game_app._layer4_warning_spawn_profile(0)["probability"], 0.005)
        self.assertEqual(game_app._layer4_warning_spawn_profile(29)["probability"], 0.005)
        self.assertEqual(game_app._layer4_warning_spawn_profile(30)["probability"], 0.01)
        self.assertEqual(game_app._layer4_warning_spawn_profile(40)["probability"], 0.02)
        self.assertEqual(game_app._layer4_warning_spawn_profile(50)["probability"], 0.10)
        self.assertTrue(game_app._layer4_warning_spawn_profile(75)["guaranteed"])

    def test_warning_progress_is_per_area(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app._advance_layer4_warning_progress(db, self.user_id, "layer_4_forge")
            game_app._advance_layer4_warning_progress(db, self.user_id, "layer_4_forge")
            game_app._advance_layer4_warning_progress(db, self.user_id, "layer_4_haze")
            db.commit()
            self.assertEqual(game_app._get_layer4_warning_progress(db, self.user_id, "layer_4_forge"), 2)
            self.assertEqual(game_app._get_layer4_warning_progress(db, self.user_id, "layer_4_haze"), 1)
            self.assertEqual(game_app._get_layer4_warning_progress(db, self.user_id, "layer_4_burst"), 0)

    def test_guaranteed_encounter_resets_only_that_area(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app._set_layer4_warning_progress(db, self.user_id, "layer_4_forge", 75)
            game_app._set_layer4_warning_progress(db, self.user_id, "layer_4_haze", 44)
            db.commit()
            result = game_app._area_boss_spawn_check(db, self.user_id, "layer_4_forge", rng=FixedRandom(0.99))
            db.commit()
            self.assertTrue(result["spawn"])
            self.assertTrue(result["layer4_warning_guaranteed"])
            self.assertEqual(result["layer4_warning_encounter_source"], "guaranteed")
            self.assertEqual(game_app._get_layer4_warning_progress(db, self.user_id, "layer_4_forge"), 0)
            self.assertEqual(game_app._get_layer4_warning_progress(db, self.user_id, "layer_4_haze"), 44)
            reset_count = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["LAYER4_WARNING_RESET"]),
            ).fetchone()["c"]
            self.assertEqual(int(reset_count), 1)

    def test_boosted_natural_encounter_resets_warning(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app._set_layer4_warning_progress(db, self.user_id, "layer_4_burst", 35)
            db.commit()
            result = game_app._area_boss_spawn_check(db, self.user_id, "layer_4_burst", rng=FixedRandom(0.0))
            db.commit()
            self.assertTrue(result["spawn"])
            self.assertEqual(result["layer4_warning_encounter_source"], "boosted")
            self.assertEqual(game_app._get_layer4_warning_progress(db, self.user_id, "layer_4_burst"), 0)

    def test_warning_status_hidden_before_layer4_and_after_three_clears(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET max_unlocked_layer = 3 WHERE id = ?", (self.user_id,))
            db.commit()
            self.assertEqual(game_app.get_layer4_warning_status_for_user(db, self.user_id), [])
            db.execute("UPDATE users SET max_unlocked_layer = 4 WHERE id = ?", (self.user_id,))
            now = int(time.time())
            for area_key in game_app.LAYER4_SUBAREA_KEYS:
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        now,
                        game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                        json.dumps({"area_key": area_key, "boss_kind": "fixed"}),
                        self.user_id,
                    ),
                )
            db.commit()
            self.assertEqual(game_app.get_layer4_warning_status_for_user(db, self.user_id), [])

    def test_warning_status_contains_phase_labels(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app._set_layer4_warning_progress(db, self.user_id, "layer_4_forge", 55)
            db.commit()
            rows = game_app.get_layer4_warning_status_for_user(db, self.user_id)
            forge = next(row for row in rows if row["area_key"] == "layer_4_forge")
            self.assertEqual(forge["label"], "強")
            self.assertIn("試験ボス反応", forge["helper_text"])


if __name__ == "__main__":
    unittest.main()
