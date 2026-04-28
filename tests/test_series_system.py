import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class SeriesSystemTests(unittest.TestCase):
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
                VALUES (?, ?, ?, 0, 0, 0, 5)
                """,
                ("series_tester", "x", now),
            )
            self.user_id = int(
                db.execute("SELECT id FROM users WHERE username = ?", ("series_tester",)).fetchone()["id"]
            )
            game_app.initialize_new_user(db, self.user_id)
            self.robot_id = int(
                db.execute("SELECT active_robot_id FROM users WHERE id = ?", (self.user_id,)).fetchone()["active_robot_id"]
            )
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "series_tester"
        return client

    def test_series_master_seeded_and_part_mapping_applied(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            count = int(db.execute("SELECT COUNT(*) AS c FROM series_master").fetchone()["c"])
            self.assertGreaterEqual(count, 7)
            row = db.execute(
                """
                SELECT rp.series, rp.image_path, sm.frame_type, sm.max_rarity, sm.can_evolve
                FROM robot_parts rp
                LEFT JOIN series_master sm ON sm.series_key = rp.series
                WHERE rp.key = 'head_kabuto'
                """
            ).fetchone()
            self.assertEqual(row["series"], "insect_kabuto")
            self.assertEqual(row["image_path"], "parts/head/head_kabuto.png")
            self.assertEqual(row["frame_type"], "insect")
            self.assertEqual(row["max_rarity"], "N")
            self.assertEqual(int(row["can_evolve"]), 0)

    def test_series_release_gate_defaults_to_admin_only(self):
        old_bypass = game_app.app.config.get("BYPASS_RELEASE_GATES_IN_TESTS", True)
        game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = False
        try:
            with game_app.app.app_context():
                db = game_app.get_db()
                self.assertFalse(game_app._series_system_enabled_for_user(db, user_id=self.user_id))
                db.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (self.user_id,))
                db.commit()
                self.assertTrue(game_app._series_system_enabled_for_user(db, user_id=self.user_id))
        finally:
            game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = old_bypass

    def test_robot_stats_apply_series_bonus_for_equipped_kabuto_set(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            keys = {
                "head": "head_kabuto",
                "r_arm": "right_arm_kabuto",
                "l_arm": "left_arm_kabuto",
                "legs": "legs_kabuto",
            }
            part_instance_ids = {}
            for slot, key in keys.items():
                part = game_app._get_part_by_key(db, key)
                part_instance_ids[slot] = game_app._create_part_instance_from_master(
                    db,
                    self.user_id,
                    part,
                    plus=0,
                    status="inventory",
                )
            game_app._equip_part_instances_on_robot(db, self.robot_id, part_instance_ids)
            db.execute(
                """
                UPDATE robot_instance_parts
                SET head_key = ?, r_arm_key = ?, l_arm_key = ?, legs_key = ?
                WHERE robot_instance_id = ?
                """,
                (keys["head"], keys["r_arm"], keys["l_arm"], keys["legs"], self.robot_id),
            )
            db.commit()

            stat_obj = game_app._compute_robot_stats_for_instance(db, self.robot_id)
            self.assertEqual(stat_obj["series_counts"]["insect_kabuto"], 4)
            self.assertTrue(any(row["stat_key"] == "def" for row in stat_obj["series_bonus"]))
            self.assertTrue(any(row["stat_key"] == "hp" for row in stat_obj["series_bonus"]))

    def test_build_and_robot_detail_show_series_section(self):
        client = self._client()
        build_resp = client.get("/build")
        self.assertEqual(build_resp.status_code, 200)
        build_html = build_resp.get_data(as_text=True)
        self.assertIn("シリーズ効果:", build_html)
        self.assertIn("同シリーズ 2部位 / 4部位で発動", build_html)

        detail_resp = client.get(f"/robots/{self.robot_id}")
        self.assertEqual(detail_resp.status_code, 200)
        detail_html = detail_resp.get_data(as_text=True)
        self.assertIn("シリーズ効果:", detail_html)


if __name__ == "__main__":
    unittest.main()
