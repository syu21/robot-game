import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class BuildModeTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        self.old_testing = game_app.app.config.get("TESTING")
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        init_db.main()
        game_app.app.config["TESTING"] = True
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin) VALUES (?, ?, ?, 0)",
                ("build_mode_user", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("build_mode_user",)).fetchone()["id"])
            game_app.initialize_new_user(db, self.user_id)
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin) VALUES (?, ?, ?, 0)",
                ("other_build_user", "x", now),
            )
            self.other_user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("other_build_user",)).fetchone()["id"])
            game_app.initialize_new_user(db, self.other_user_id)
            self.base_robot_id = int(db.execute("SELECT active_robot_id FROM users WHERE id = ?", (self.user_id,)).fetchone()["active_robot_id"])
            self.other_robot_id = int(db.execute("SELECT active_robot_id FROM users WHERE id = ?", (self.other_user_id,)).fetchone()["active_robot_id"])
            db.execute("UPDATE users SET robot_slot_limit = 5 WHERE id IN (?, ?)", (self.user_id, self.other_user_id))
            base_frame = db.execute(
                "SELECT COALESCE(frame_type, 'normal') AS frame_type FROM robot_instances WHERE id = ?",
                (self.base_robot_id,),
            ).fetchone()["frame_type"]
            head_part = db.execute(
                """
                SELECT *
                FROM robot_parts
                WHERE part_type = 'HEAD' AND is_active = 1
                  AND COALESCE(frame_type, 'normal') = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (base_frame,),
            ).fetchone()
            self.new_head_id = int(game_app._create_part_instance_from_master(db, self.user_id, head_part, plus=1))
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        game_app.app.config["TESTING"] = self.old_testing
        self.tmpdir.cleanup()

    def _client(self, user_id=None):
        client = game_app.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = user_id or self.user_id
            sess["username"] = "build_mode_user"
        return client

    def _create_inventory_part_for_slot(self, part_type, *, plus=0):
        with game_app.app.app_context():
            db = game_app.get_db()
            base_frame = db.execute(
                "SELECT COALESCE(frame_type, 'normal') AS frame_type FROM robot_instances WHERE id = ?",
                (self.base_robot_id,),
            ).fetchone()["frame_type"]
            part = db.execute(
                """
                SELECT *
                FROM robot_parts
                WHERE part_type = ? AND is_active = 1
                  AND COALESCE(frame_type, 'normal') = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (part_type, base_frame),
            ).fetchone()
            part_instance_id = int(game_app._create_part_instance_from_master(db, self.user_id, part, plus=plus))
            db.commit()
            return part_instance_id

    def test_build_defaults_to_modify_when_active_robot_exists(self):
        resp = self._client().get("/build")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("保存中ロボを改造する", html)
        self.assertIn("変えたいパーツだけ", html)

    def test_build_defaults_to_new_without_active_robot(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET active_robot_id = NULL WHERE id = ?", (self.user_id,))
            db.commit()
        resp = self._client().get("/build")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("新しくロボを組み立てる", html)
        self.assertIn("4部位を選んで", html)

    def test_build_new_requires_all_four_slots(self):
        resp = self._client().post(
            "/build/confirm",
            data={"mode": "new", "robot_name": "Missing"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("全カテゴリから1つずつ選択", resp.get_data(as_text=True))

    def test_build_modify_lists_saved_robots(self):
        resp = self._client().get("/build?mode=modify")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("保存中ロボを改造する", html)
        self.assertIn("build-base-robot", html)
        self.assertIn("未選択の部位は現在のパーツ", html)

    def test_build_modify_one_part_updates_existing_robot_without_consuming_slot(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            before_count = int(db.execute(
                "SELECT COUNT(*) AS c FROM robot_instances WHERE user_id = ? AND status != 'decomposed'",
                (self.user_id,),
            ).fetchone()["c"])
            base_mapping = game_app._ensure_robot_instance_part_instances(db, self.base_robot_id)
            old_head_id = int(base_mapping["head"])

        resp = self._client().post(
            "/build/confirm",
            data={
                "mode": "modify",
                "base_robot_id": str(self.base_robot_id),
                "robot_name": "Modified One",
                "head_key": str(self.new_head_id),
            },
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)

        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT active_robot_id FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(user["active_robot_id"]), self.base_robot_id)
            after_count = int(db.execute(
                "SELECT COUNT(*) AS c FROM robot_instances WHERE user_id = ? AND status != 'decomposed'",
                (self.user_id,),
            ).fetchone()["c"])
            self.assertEqual(after_count, before_count)
            robot = db.execute(
                "SELECT name, status, composed_image_path, icon_32_path FROM robot_instances WHERE id = ?",
                (self.base_robot_id,),
            ).fetchone()
            self.assertEqual(robot["name"], "Modified One")
            self.assertEqual(robot["status"], "active")
            self.assertTrue(robot["composed_image_path"])
            self.assertTrue(robot["icon_32_path"])
            new_mapping = game_app._ensure_robot_instance_part_instances(db, self.base_robot_id)
            self.assertEqual(int(new_mapping["head"]), self.new_head_id)
            for slot in ("r_arm", "l_arm", "legs"):
                self.assertEqual(int(new_mapping[slot]), int(base_mapping[slot]))
            old_head = db.execute("SELECT status FROM part_instances WHERE id = ?", (old_head_id,)).fetchone()
            new_head = db.execute("SELECT status FROM part_instances WHERE id = ?", (self.new_head_id,)).fetchone()
            self.assertEqual(old_head["status"], "inventory")
            self.assertEqual(new_head["status"], "equipped")

    def test_build_modify_rejects_other_users_base_robot(self):
        resp = self._client().post(
            "/build/confirm",
            data={
                "mode": "modify",
                "base_robot_id": str(self.other_robot_id),
                "robot_name": "Bad Modify",
                "head_key": str(self.new_head_id),
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("改造する保存中ロボが見つかりません", resp.get_data(as_text=True))

    def test_build_modify_allows_existing_robot_when_robot_slots_are_full(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            active_count = int(db.execute(
                "SELECT COUNT(*) AS c FROM robot_instances WHERE user_id = ? AND status != 'decomposed'",
                (self.user_id,),
            ).fetchone()["c"])
            before_mapping = game_app._ensure_robot_instance_part_instances(db, self.base_robot_id)
            db.execute("UPDATE users SET robot_slot_limit = ? WHERE id = ?", (active_count, self.user_id))
            db.commit()

        resp = self._client().post(
            "/build/confirm",
            data={
                "mode": "modify",
                "base_robot_id": str(self.base_robot_id),
                "robot_name": "Full Slot",
                "head_key": str(self.new_head_id),
            },
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT active_robot_id FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(user["active_robot_id"]), self.base_robot_id)
            after_count = int(db.execute(
                "SELECT COUNT(*) AS c FROM robot_instances WHERE user_id = ? AND status != 'decomposed'",
                (self.user_id,),
            ).fetchone()["c"])
            self.assertEqual(after_count, active_count)
            after_mapping = game_app._ensure_robot_instance_part_instances(db, self.base_robot_id)
            self.assertEqual(int(after_mapping["head"]), self.new_head_id)
            for slot in ("r_arm", "l_arm", "legs"):
                self.assertEqual(int(after_mapping[slot]), int(before_mapping[slot]))

    def test_build_new_still_blocks_when_robot_slots_are_full(self):
        head_id = self._create_inventory_part_for_slot("HEAD", plus=1)
        r_arm_id = self._create_inventory_part_for_slot("RIGHT_ARM", plus=1)
        l_arm_id = self._create_inventory_part_for_slot("LEFT_ARM", plus=1)
        legs_id = self._create_inventory_part_for_slot("LEGS", plus=1)
        with game_app.app.app_context():
            db = game_app.get_db()
            active_count = int(db.execute(
                "SELECT COUNT(*) AS c FROM robot_instances WHERE user_id = ? AND status != 'decomposed'",
                (self.user_id,),
            ).fetchone()["c"])
            db.execute("UPDATE users SET robot_slot_limit = ? WHERE id = ?", (active_count, self.user_id))
            db.commit()

        resp = self._client().post(
            "/build/confirm",
            data={
                "mode": "new",
                "robot_name": "New Full Slot",
                "head_key": str(head_id),
                "r_arm_key": str(r_arm_id),
                "l_arm_key": str(l_arm_id),
                "legs_key": str(legs_id),
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("保存枠がいっぱいです。不要なロボを整理してください", resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
