import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class RobotMaintenanceTests(unittest.TestCase):
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
                VALUES (?, ?, ?, 1, 0, 2)
                """,
                ("maintenance_tester", "x", now),
            )
            self.user_id = int(
                db.execute("SELECT id FROM users WHERE username = ?", ("maintenance_tester",)).fetchone()["id"]
            )
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (self.user_id, "TuneBot", now, now),
            )
            self.robot_id = int(
                db.execute(
                    "SELECT id FROM robot_instances WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                    (self.user_id,),
                ).fetchone()["id"]
            )

            def pick_part(part_type):
                row = db.execute(
                    "SELECT * FROM robot_parts WHERE part_type = ? AND is_active = 1 ORDER BY id ASC LIMIT 1",
                    (part_type,),
                ).fetchone()
                self.assertIsNotNone(row)
                return row

            self.head_part = pick_part("HEAD")
            self.r_arm_part = pick_part("RIGHT_ARM")
            self.l_arm_part = pick_part("LEFT_ARM")
            self.legs_part = pick_part("LEGS")

            db.execute(
                """
                INSERT INTO robot_instance_parts (robot_instance_id, head_key, r_arm_key, l_arm_key, legs_key)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self.robot_id,
                    self.head_part["key"],
                    self.r_arm_part["key"],
                    self.l_arm_part["key"],
                    self.legs_part["key"],
                ),
            )
            db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (self.robot_id, self.user_id))
            db.commit()

            game_app._ensure_robot_instance_part_instances(db, self.robot_id)
            parts_row = db.execute(
                "SELECT * FROM robot_instance_parts WHERE robot_instance_id = ?",
                (self.robot_id,),
            ).fetchone()
            self.current_head_instance_id = int(parts_row["head_part_instance_id"])
            self.candidate_head_instance_id = int(
                game_app._create_part_instance_from_master(
                    db,
                    self.user_id,
                    self.head_part,
                    plus=2,
                    status="inventory",
                )
            )
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
            sess["username"] = "maintenance_tester"
        return client

    def _fill_inventory_to(self, target_count):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET part_inventory_limit = 60 WHERE id = ?", (self.user_id,))
            part = db.execute(
                "SELECT * FROM robot_parts WHERE part_type = 'HEAD' AND is_active = 1 ORDER BY id ASC LIMIT 1"
            ).fetchone()
            while game_app._count_part_inventory(db, self.user_id) < int(target_count):
                game_app._create_part_instance_from_master(
                    db,
                    self.user_id,
                    part,
                    plus=0,
                    status="inventory",
                )
            db.commit()

    def test_robot_maintenance_swaps_slot_and_refreshes_assets(self):
        client = self._client()
        get_resp = client.get(f"/robots/{self.robot_id}/maintenance?slot=HEAD")
        self.assertEqual(get_resp.status_code, 200)
        html = get_resp.get_data(as_text=True)
        self.assertIn("機体整備", html)
        self.assertIn("この部位を整備する", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            before_robot = db.execute(
                "SELECT composed_image_path, icon_32_path, updated_at FROM robot_instances WHERE id = ?",
                (self.robot_id,),
            ).fetchone()
            before_updated_at = int(before_robot["updated_at"] or 0)

        post_resp = client.post(
            f"/robots/{self.robot_id}/maintenance",
            data={"slot": "HEAD", "part_instance_id": str(self.candidate_head_instance_id)},
            follow_redirects=False,
        )
        self.assertIn(post_resp.status_code, (302, 303))

        with game_app.app.app_context():
            db = game_app.get_db()
            parts_row = db.execute(
                "SELECT head_part_instance_id FROM robot_instance_parts WHERE robot_instance_id = ?",
                (self.robot_id,),
            ).fetchone()
            self.assertEqual(int(parts_row["head_part_instance_id"]), self.candidate_head_instance_id)

            candidate_row = db.execute(
                "SELECT status, plus FROM part_instances WHERE id = ?",
                (self.candidate_head_instance_id,),
            ).fetchone()
            self.assertEqual(str(candidate_row["status"]), "equipped")
            self.assertEqual(int(candidate_row["plus"]), 2)

            previous_row = db.execute(
                "SELECT status FROM part_instances WHERE id = ?",
                (self.current_head_instance_id,),
            ).fetchone()
            self.assertEqual(str(previous_row["status"]), "inventory")

            robot_row = db.execute(
                "SELECT composed_image_path, icon_32_path, updated_at FROM robot_instances WHERE id = ?",
                (self.robot_id,),
            ).fetchone()
            self.assertTrue(robot_row["composed_image_path"])
            self.assertTrue(robot_row["icon_32_path"])
            self.assertGreaterEqual(int(robot_row["updated_at"] or 0), before_updated_at)

            event_row = db.execute(
                """
                SELECT payload_json
                FROM world_events_log
                WHERE user_id = ? AND event_type = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (self.user_id, game_app.AUDIT_EVENT_TYPES["ROBOT_MAINTENANCE"]),
            ).fetchone()
            self.assertIsNotNone(event_row)
            payload = json.loads(event_row["payload_json"] or "{}")
            self.assertEqual(payload.get("robot_instance_id"), self.robot_id)
            self.assertEqual(payload.get("changed_slots"), ["HEAD"])
            self.assertEqual(int((payload.get("after_part_ids") or {}).get("HEAD") or 0), self.candidate_head_instance_id)

    def test_robot_decompose_blocks_when_returned_parts_exceed_inventory_limit(self):
        self._fill_inventory_to(57)
        client = self._client()

        resp = client.post(f"/robot-instance/{self.robot_id}/decompose", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

        with client.session_transaction() as sess:
            self.assertEqual(
                sess.get("message"),
                "分解すると所持パーツが上限を超えます。先にパーツを整理してから分解してください。",
            )

        with game_app.app.app_context():
            db = game_app.get_db()
            robot_row = db.execute("SELECT status FROM robot_instances WHERE id = ?", (self.robot_id,)).fetchone()
            self.assertEqual(robot_row["status"], "active")
            self.assertEqual(game_app._count_part_inventory(db, self.user_id), 57)

        self._fill_inventory_to(60)
        resp = client.post(f"/robot-instance/{self.robot_id}/decompose", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        with game_app.app.app_context():
            db = game_app.get_db()
            robot_row = db.execute("SELECT status FROM robot_instances WHERE id = ?", (self.robot_id,)).fetchone()
            self.assertEqual(robot_row["status"], "active")
            self.assertEqual(game_app._count_part_inventory(db, self.user_id), 60)

    def test_robot_decompose_allows_when_returned_parts_fit_inventory_limit(self):
        self._fill_inventory_to(56)
        client = self._client()

        resp = client.post(f"/robot-instance/{self.robot_id}/decompose", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

        with game_app.app.app_context():
            db = game_app.get_db()
            robot_row = db.execute("SELECT status FROM robot_instances WHERE id = ?", (self.robot_id,)).fetchone()
            self.assertEqual(robot_row["status"], "decomposed")
            self.assertEqual(game_app._count_part_inventory(db, self.user_id), 60)

    def test_robot_maintenance_updates_decor_after_backfilling_part_instances(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            decor = db.execute(
                "SELECT id FROM robot_decor_assets WHERE key = ?",
                ("boss_emblem_aurix",),
            ).fetchone()
            self.assertIsNotNone(decor)
            db.execute(
                "INSERT OR IGNORE INTO user_decor_inventory (user_id, decor_asset_id, acquired_at) VALUES (?, ?, ?)",
                (self.user_id, int(decor["id"]), int(time.time())),
            )
            db.execute(
                """
                UPDATE robot_instance_parts
                SET head_part_instance_id = NULL,
                    r_arm_part_instance_id = NULL,
                    l_arm_part_instance_id = NULL,
                    legs_part_instance_id = NULL,
                    decor_asset_id = NULL
                WHERE robot_instance_id = ?
                """,
                (self.robot_id,),
            )
            db.commit()

        resp = self._client().post(
            f"/robots/{self.robot_id}/maintenance?slot=DECOR",
            data={"slot": "DECOR", "decor_asset_id": str(int(decor["id"]))},
            follow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303))

        with game_app.app.app_context():
            db = game_app.get_db()
            parts_row = db.execute(
                "SELECT decor_asset_id FROM robot_instance_parts WHERE robot_instance_id = ?",
                (self.robot_id,),
            ).fetchone()
            self.assertEqual(int(parts_row["decor_asset_id"]), int(decor["id"]))
            slot_row = db.execute(
                """
                SELECT decor_asset_id, slot_index, offset_x, offset_y
                FROM robot_instance_decors
                WHERE robot_instance_id = ?
                """,
                (self.