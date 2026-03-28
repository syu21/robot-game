import os
import tempfile
import time
import unittest
from unittest import mock

import app as game_app
import init_db


class AreaGrowthTendencyTests(unittest.TestCase):
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
                ("tendency_tester", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("tendency_tester",),
            ).fetchone()["id"]
            game_app.initialize_new_user(db, self.user_id)
            self.right_arm_part = db.execute(
                """
                SELECT *
                FROM robot_parts
                WHERE is_active = 1 AND part_type = 'RIGHT_ARM'
                ORDER BY id ASC
                LIMIT 1
                """
            ).fetchone()
            self.legs_part = db.execute(
                """
                SELECT *
                FROM robot_parts
                WHERE is_active = 1 AND part_type = 'LEGS'
                ORDER BY id ASC
                LIMIT 1
                """
            ).fetchone()
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def test_create_part_instance_applies_area_bias_to_weights(self):
        with game_app.app.app_context(), mock.patch("services.stats.random.uniform", return_value=0.0):
            db = game_app.get_db()
            mist_id = game_app._create_part_instance_from_master(
                db,
                self.user_id,
                self.right_arm_part,
                area_key="layer_2_mist",
            )
            rush_id = game_app._create_part_instance_from_master(
                db,
                self.user_id,
                self.right_arm_part,
                area_key="layer_2_rush",
            )
            db.commit()
            mist = db.execute("SELECT * FROM part_instances WHERE id = ?", (int(mist_id),)).fetchone()
            rush = db.execute("SELECT * FROM part_instances WHERE id = ?", (int(rush_id),)).fetchone()

        self.assertGreater(float(mist["w_acc"]), float(rush["w_acc"]))
        self.assertGreater(float(rush["w_spd"]), float(mist["w_spd"]))
        self.assertGreater(float(rush["w_atk"]), float(mist["w_atk"]))

    def test_layer4_area_biases_are_stronger_and_distinct(self):
        with game_app.app.app_context(), mock.patch("services.stats.random.uniform", return_value=0.0):
            db = game_app.get_db()
            forge_id = game_app._create_part_instance_from_master(
                db,
                self.user_id,
                self.right_arm_part,
                area_key="layer_4_forge",
            )
            haze_id = game_app._create_part_instance_from_master(
                db,
                self.user_id,
                self.right_arm_part,
                area_key="layer_4_haze",
            )
            burst_id = game_app._create_part_instance_from_master(
                db,
                self.user_id,
                self.right_arm_part,
                area_key="layer_4_burst",
            )
            db.commit()
            forge = db.execute("SELECT * FROM part_instances WHERE id = ?", (int(forge_id),)).fetchone()
            haze = db.execute("SELECT * FROM part_instances WHERE id = ?", (int(haze_id),)).fetchone()
            burst = db.execute("SELECT * FROM part_instances WHERE id = ?", (int(burst_id),)).fetchone()

        self.assertGreater(float(forge["w_hp"]), float(burst["w_hp"]))
        self.assertGreater(float(forge["w_def"]), float(burst["w_def"]))
        self.assertGreater(float(haze["w_acc"]), float(forge["w_acc"]))
        self.assertGreater(float(burst["w_atk"]), float(haze["w_atk"]))
        self.assertGreater(float(burst["w_cri"]), float(forge["w_cri"]))

    def test_add_part_drop_returns_growth_tendency_metadata(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            result = game_app._add_part_drop(
                db,
                self.user_id,
                part_type=self.legs_part["part_type"],
                part_key=self.legs_part["key"],
                rarity=self.legs_part["rarity"],
                plus=0,
                as_instance=True,
                area_key="layer_2_rush",
            )
            db.commit()

        self.assertIsNotNone(result)
        self.assertEqual(result["growth_tendency_key"], "fastest")
        self.assertEqual(result["growth_tendency_label"], "速攻育成")
        self.assertIsNotNone(result["part_instance_id"])

    def test_add_part_drop_returns_layer4_growth_tendency_metadata(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            result = game_app._add_part_drop(
                db,
                self.user_id,
                part_type=self.legs_part["part_type"],
                part_key=self.legs_part["key"],
                rarity=self.legs_part["rarity"],
                plus=0,
                as_instance=True,
                area_key="layer_4_forge",
            )
            db.commit()

        self.assertIsNotNone(result)
        self.assertEqual(result["growth_tendency_key"], "fortress")
        self.assertEqual(result["growth_tendency_label"], "要塞育成")
        self.assertIsNotNone(result["part_instance_id"])

    def test_layer5_area_biases_are_distinct(self):
        with game_app.app.app_context(), mock.patch("services.stats.random.uniform", return_value=0.0):
            db = game_app.get_db()
            labyrinth_id = game_app._create_part_instance_from_master(
                db,
                self.user_id,
                self.right_arm_part,
                area_key="layer_5_labyrinth",
            )
            pinnacle_id = game_app._create_part_instance_from_master(
                db,
                self.user_id,
                self.right_arm_part,
                area_key="layer_5_pinnacle",
            )
            db.commit()
            labyrinth = db.execute("SELECT * FROM part_instances WHERE id = ?", (int(labyrinth_id),)).fetchone()
            pinnacle = db.execute("SELECT * FROM part_instances WHERE id = ?", (int(pinnacle_id),)).fetchone()

        self.assertGreater(float(labyrinth["w_hp"]), float(pinnacle["w_hp"]))
        self.assertGreater(float(labyrinth["w_def"]), float(pinnacle["w_def"]))
        self.assertGreater(float(labyrinth["w_acc"]), float(pinnacle["w_acc"]))
        self.assertGreater(float(pinnacle["w_atk"]), float(labyrinth["w_atk"]))
        self.assertGreater(float(pinnacle["w_cri"]), float(labyrinth["w_cri"]))

    def test_add_part_drop_returns_layer5_growth_tendency_metadata(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            result = game_app._add_part_drop(
                db,
                self.user_id,
                part_type=self.legs_part["part_type"],
                part_key=self.legs_part["key"],
                rarity=self.legs_part["rarity"],
                plus=0,
                as_instance=True,
                area_key="layer_5_labyrinth",
            )
            db.commit()

        self.assertIsNotNone(result)
        self.assertEqual(result["growth_tendency_key"], "labyrinth")
        self.assertEqual(result["growth_tendency_label"], "観測育成")
        self.assertIsNotNone(result["part_instance_id"])


if __name__ == "__main__":
    unittest.main()
