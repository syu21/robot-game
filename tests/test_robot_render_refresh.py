import os
import tempfile
import time
import unittest
from unittest import mock

import app as game_app
import init_db


class RobotRenderRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        self.old_compose_rev = game_app.COMPOSE_REV
        self.old_offset_cache_version = game_app.PART_OFFSET_CACHE_VERSION
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
                VALUES (?, ?, ?, 1, 0, 1)
                """,
                ("render_tester", "x", now),
            )
            self.user_id = int(
                db.execute("SELECT id FROM users WHERE username = ?", ("render_tester",)).fetchone()["id"]
            )
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (self.user_id, "RenderBot", now, now),
            )
            self.robot_id = int(
                db.execute(
                    "SELECT id FROM robot_instances WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                    (self.user_id,),
                ).fetchone()["id"]
            )

            def pick_key(part_type):
                row = db.execute(
                    "SELECT key FROM robot_parts WHERE part_type = ? AND is_active = 1 ORDER BY id ASC LIMIT 1",
                    (part_type,),
                ).fetchone()
                self.assertIsNotNone(row)
                return row["key"]

            self.legs_key = pick_key("LEGS")
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
                    self.legs_key,
                ),
            )
            db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (self.robot_id, self.user_id))
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        game_app.COMPOSE_REV = self.old_compose_rev
        game_app.PART_OFFSET_CACHE_VERSION = self.old_offset_cache_version
        self.tmpdir.cleanup()

    def test_get_active_robot_refreshes_when_render_revision_is_newer(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            first = game_app._get_active_robot(db, self.user_id)
            self.assertIsNotNone(first)
            old_updated_at = int(first["updated_at"] or 0)
            composed_rel = first["composed_image_path"]
            composed_abs = game_app._static_abs(composed_rel)
            with open(composed_abs, "rb") as fh:
                old_bytes = fh.read()

            db.execute(
                "UPDATE robot_parts SET offset_y = offset_y + 18 WHERE key = ?",
                (self.legs_key,),
            )
            db.commit()

            render_rev = old_updated_at + 30
            game_app.PART_OFFSET_CACHE_VERSION = render_rev
            game_app.COMPOSE_REV = render_rev

            with mock.patch.object(game_app.time, "time", return_value=render_rev + 5):
                refreshed = game_app._get_active_robot(db, self.user_id)

            self.assertIsNotNone(refreshed)
            self.assertGreater(int(refreshed["updated_at"] or 0), old_updated_at)
            with open(game_app._static_abs(refreshed["composed_image_path"]), "rb") as fh:
                new_bytes = fh.read()
            self.assertNotEqual(old_bytes, new_bytes)


if __name__ == "__main__":
    unittest.main()
