import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class TowerRouteTests(unittest.TestCase):
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
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, max_unlocked_layer)
                VALUES ('tower_locked', 'x', ?, 0, 3)
                """,
                (now,),
            )
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, max_unlocked_layer)
                VALUES ('tower_user', 'x', ?, 0, 4)
                """,
                (now,),
            )
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, max_unlocked_layer)
                VALUES ('tower_admin', 'x', ?, 1, 4)
                """,
                (now,),
            )
            self.locked_user_id = int(db.execute("SELECT id FROM users WHERE username = 'tower_locked'").fetchone()["id"])
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = 'tower_user'").fetchone()["id"])
            self.admin_user_id = int(db.execute("SELECT id FROM users WHERE username = 'tower_admin'").fetchone()["id"])
            self.robot_ids = [self._create_robot(db, self.admin_user_id, f"TowerBot{i}") for i in range(1, 4)]
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        game_app.app.config["TESTING"] = self.old_testing
        self.tmpdir.cleanup()

    def _create_robot(self, db, user_id, name):
        now = int(time.time())
        cur = db.execute(
            """
            INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
            VALUES (?, ?, 'active', ?, ?)
            """,
            (int(user_id), name, now, now),
        )
        robot_id = int(cur.lastrowid)

        def key_for(part_type):
            row = db.execute(
                "SELECT key FROM robot_parts WHERE part_type = ? AND is_active = 1 ORDER BY id ASC LIMIT 1",
                (part_type,),
            ).fetchone()
            self.assertIsNotNone(row)
            return row["key"]

        db.execute(
            """
            INSERT INTO robot_instance_parts (robot_instance_id, head_key, r_arm_key, l_arm_key, legs_key)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                robot_id,
                key_for("HEAD"),
                key_for("RIGHT_ARM"),
                key_for("LEFT_ARM"),
                key_for("LEGS"),
            ),
        )
        return robot_id

    def _client(self, user_id=None, username="tower_admin"):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user_id or self.admin_user_id)
            session["username"] = username
        return client

    def test_home_tower_link_only_for_admin_users(self):
        locked_html = self._client(self.locked_user_id, "tower_locked").get("/home").get_data(as_text=True)
        self.assertNotIn("/tower", locked_html)

        user_html = self._client(self.user_id, "tower_user").get("/home").get_data(as_text=True)
        self.assertNotIn("/tower", user_html)

        admin_html = self._client().get("/home").get_data(as_text=True)
        self.assertIn("観測塔 -ASTRAL SPIRE-", admin_html)
        self.assertIn("/tower", admin_html)

    def test_non_admin_user_cannot_start_tower(self):
        resp = self._client(self.user_id, "tower_user").post(
            "/tower/start",
            data={"robot_1": "1", "robot_2": "2", "robot_3": "3"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/home", resp.headers["Location"])

    def test_start_requires_three_distinct_robots(self):
        client = self._client()
        resp = client.post(
            "/tower/start",
            data={"robot_1": self.robot_ids[0], "robot_2": self.robot_ids[0], "robot_3": self.robot_ids[1]},
            follow_redirects=True,
        )
        self.assertIn("重複選択できません", resp.get_data(as_text=True))
        with game_app.app.app_context():
            db = game_app.get_db()
            count = int(db.execute("SELECT COUNT(*) AS c FROM tower_runs").fetchone()["c"])
            self.assertEqual(count, 0)

    def test_start_creates_run_and_cooling_rows(self):
        client = self._client()
        resp = client.post(
            "/tower/start",
            data={"robot_1": self.robot_ids[0], "robot_2": self.robot_ids[1], "robot_3": self.robot_ids[2]},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            run = db.execute("SELECT * FROM tower_runs WHERE user_id = ?", (self.admin_user_id,)).fetchone()
            self.assertIsNotNone(run)
            self.assertEqual(run["status"], "active")
            cooling = int(db.execute("SELECT COUNT(*) AS c FROM tower_run_cooling WHERE run_id = ?", (run["id"],)).fetchone()["c"])
            self.assertEqual(cooling, 3)

    def _start_run(self):
        self._client().post(
            "/tower/start",
            data={"robot_1": self.robot_ids[0], "robot_2": self.robot_ids[1], "robot_3": self.robot_ids[2]},
        )
        with game_app.app.app_context():
            db = game_app.get_db()
            return int(db.execute("SELECT id FROM tower_runs WHERE user_id = ? ORDER BY id DESC LIMIT 1", (self.admin_user_id,)).fetchone()["id"])

    def test_cooling_rotation_blocks_reuse_and_resets_after_three_robots(self):
        run_id = self._start_run()
        win = {"win": True, "turns": 3, "timeout": False, "player_damage_total": 10, "enemy_damage_total": 1}
        with patch("services.tower.simulate_battle", return_value=win):
            client = self._client()
            client.post("/tower/battle", data={"run_id": run_id, "robot_instance_id": self.robot_ids[0]})
            with game_app.app.app_context():
                db = game_app.get_db()
                row = db.execute(
                    "SELECT used_in_current_cycle FROM tower_run_cooling WHERE run_id = ? AND robot_instance_id = ?",
                    (run_id, self.robot_ids[0]),
                ).fetchone()
                self.assertEqual(int(row["used_in_current_cycle"]), 1)

            blocked = client.post(
                "/tower/battle",
                data={"run_id": run_id, "robot_instance_id": self.robot_ids[0]},
                follow_redirects=True,
            )
            self.assertIn("冷却中", blocked.get_data(as_text=True))

            client.post("/tower/battle", data={"run_id": run_id, "robot_instance_id": self.robot_ids[1]})
            client.post("/tower/battle", data={"run_id": run_id, "robot_instance_id": self.robot_ids[2]})
            with game_app.app.app_context():
                db = game_app.get_db()
                rows = db.execute("SELECT used_in_current_cycle FROM tower_run_cooling WHERE run_id = ?", (run_id,)).fetchall()
                self.assertTrue(all(int(row["used_in_current_cycle"]) == 0 for row in rows))
                run = db.execute("SELECT current_floor FROM tower_runs WHERE id = ?", (run_id,)).fetchone()
                self.assertEqual(int(run["current_floor"]), 4)

    def test_completed_run_updates_record_and_world_logs(self):
        run_id = self._start_run()
        win = {"win": True, "turns": 2, "timeout": False, "player_damage_total": 10, "enemy_damage_total": 1}
        with patch("services.tower.simulate_battle", return_value=win):
            client = self._client()
            for index in range(10):
                client.post(
                    "/tower/battle",
                    data={"run_id": run_id, "robot_instance_id": self.robot_ids[index % 3]},
                )
        with game_app.app.app_context():
            db = game_app.get_db()
            run = db.execute("SELECT status, reached_floor FROM tower_runs WHERE id = ?", (run_id,)).fetchone()
            self.assertEqual(run["status"], "completed")
            self.assertEqual(int(run["reached_floor"]), 10)
            record = db.execute("SELECT best_floor, weekly_best_floor FROM user_tower_records WHERE user_id = ?", (self.admin_user_id,)).fetchone()
            self.assertEqual(int(record["best_floor"]), 10)
            self.assertEqual(int(record["weekly_best_floor"]), 10)
            events = [
                row["event_type"]
                for row in db.execute(
                    "SELECT event_type FROM world_events_log WHERE user_id = ?",
                    (self.admin_user_id,),
                ).fetchall()
            ]
            self.assertIn("TOWER_BEST_FLOOR", events)
            self.assertIn("TOWER_MILESTONE", events)
            self.assertIn("audit.tower.record.update", events)

    def test_failed_run_stores_reached_floor(self):
        run_id = self._start_run()
        lose = {"win": False, "turns": 4, "timeout": False, "player_damage_total": 2, "enemy_damage_total": 20}
        with patch("services.tower.simulate_battle", return_value=lose):
            self._client().post("/tower/battle", data={"run_id": run_id, "robot_instance_id": self.robot_ids[0]})
        with game_app.app.app_context():
            db = game_app.get_db()
            run = db.execute("SELECT status, reached_floor FROM tower_runs WHERE id = ?", (run_id,)).fetchone()
            self.assertEqual(run["status"], "failed")
            self.assertEqual(int(run["reached_floor"]), 0)

    def test_ranking_displays_record(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = "2026-06-08T00:00:00+00:00"
            db.execute(
                """
                INSERT INTO user_tower_records
                (user_id, best_floor, best_run_id, best_recorded_at, weekly_key, weekly_best_floor, weekly_best_run_id,
                 weekly_best_recorded_at, created_at, updated_at)
                VALUES (?, 7, 1, ?, ?, 7, 1, ?, ?, ?)
                """,
                (self.admin_user_id, now, game_app.get_current_tower_environment()["weekly_key"], now, now, now),
            )
            db.commit()
        resp = self._client().get("/tower/ranking")
        html = resp.get_data(as_text=True)
        self.assertIn("ランキング", html)
        self.assertIn("7階", html)

    def test_explore_route_still_works(self):
        resp = self._client().get("/home")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("出撃", resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
