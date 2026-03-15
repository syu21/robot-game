import os
import tempfile
import time
import unittest
from unittest import mock

import app as game_app
import init_db


class TierGrowthStagingTests(unittest.TestCase):
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
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin) VALUES (?, ?, ?, 0)",
                ("tier_user", "x", int(time.time())),
            )
            self.user_id = int(
                db.execute("SELECT id FROM users WHERE username = ?", ("tier_user",)).fetchone()["id"]
            )
            # Rを解放しても layer_1/layer_2 プロファイルがN固定で働くことを確認する。
            db.execute("UPDATE robot_parts SET is_unlocked = 1 WHERE UPPER(COALESCE(rarity, '')) = 'R'")
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    @staticmethod
    def _pick_for_test(weight_map):
        keys = set(weight_map.keys())
        if "coin_only" in keys:
            return "parts_1"
        if keys == {"N"}:
            return "N"
        if "N" in keys and "R" in keys:
            return "R"
        if 0 in keys:
            return 0
        return next(iter(weight_map.keys()))

    def test_core_drop_rate_is_layer3_only(self):
        self.assertEqual(game_app._evolution_core_drop_rate_for_area("layer_1"), 0.0)
        self.assertEqual(game_app._evolution_core_drop_rate_for_area("layer_2"), 0.0)
        self.assertEqual(game_app._evolution_core_drop_rate_for_area("layer_2_mist"), 0.0)
        self.assertEqual(game_app._evolution_core_drop_rate_for_area("layer_2_rush"), 0.0)
        self.assertGreater(game_app._evolution_core_drop_rate_for_area("layer_3"), 0.0)

    def test_layer2_drop_profile_keeps_n_only(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            with mock.patch.object(game_app, "_weighted_pick", side_effect=self._pick_for_test):
                rewards = game_app._roll_battle_rewards(
                    db=db,
                    user_id=self.user_id,
                    tier=3,
                    part_drop_budget=1,
                    area_key="layer_2",
                )
        self.assertEqual(len(rewards["dropped_parts"]), 1)
        self.assertEqual((rewards["dropped_parts"][0].get("rarity") or "").upper(), "N")


if __name__ == "__main__":
    unittest.main()

