import os
import tempfile
import time
import unittest

from werkzeug.security import generate_password_hash

import app as game_app
import init_db


class Layer6RecordTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        init_db.main()
        game_app.app.config["TESTING"] = True
        self.now = int(time.time())
        self.week_key = game_app._world_week_key(self.now)

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _login(self, client, user_id, username):
        with client.session_transaction() as sess:
            sess["user_id"] = int(user_id)
            sess["username"] = username

    def _create_user(self, db, username, *, is_admin=0, analytics_excluded=0, max_layer=6):
        db.execute(
            """
            INSERT INTO users
            (username, password_hash, created_at, last_seen_at, is_admin, is_admin_protected, analytics_excluded, max_unlocked_layer)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                generate_password_hash("pw"),
                self.now,
                self.now,
                int(is_admin),
                int(is_admin),
                int(analytics_excluded),
                int(max_layer),
            ),
        )
        return int(db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"])

    def _create_robot(self, db, user_id, name):
        db.execute(
            """
            INSERT INTO robot_instances (user_id, name, status, style_key, style_current_key, created_at, updated_at)
            VALUES (?, ?, 'active', 'stable', 'stable', ?, ?)
            """,
            (int(user_id), name, self.now, self.now),
        )
        robot_id = int(db.execute("SELECT id FROM robot_instances WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()["id"])
        db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (robot_id, int(user_id)))
        return robot_id

    def _insert_explore_end(self, db, user_id, robot_id, *, area_key="layer_6_rebuild", win=True, turns=5, request_id=None, ts_offset=0):
        payload = {
            "area_key": area_key,
            "player": {"robot_instance_id": int(robot_id), "hp_max": 100},
            "result": {
                "win": bool(win),
                "turns": int(turns),
                "battle_id": f"battle-{user_id}-{area_key}-{ts_offset}-{turns}",
                "is_area_boss": False,
                "damage_taken_total": 20,
            },
        }
        db.execute(
            """
            INSERT INTO world_events_log (created_at, event_type, payload_json, user_id, request_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                int(self.now + ts_offset),
                game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                game_app.json.dumps(payload, ensure_ascii=False),
                int(user_id),
                request_id,
            ),
        )

    def _insert_boss_defeat(self, db, user_id, robot_id):
        payload = {
            "area_key": "layer_6_final",
            "enemy_name": "暴走制御核",
            "robot_instance_id": int(robot_id),
            "robot_name": "BossBot",
        }
        db.execute(
            """
            INSERT INTO world_events_log (created_at, event_type, payload_json, user_id, request_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                self.now,
                game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                game_app.json.dumps(payload, ensure_ascii=False),
                int(user_id),
                "boss-clear-1",
            ),
        )

    def test_layer6_snapshot_builds_records_and_dedupes_request_id(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            user_id = self._create_user(db, "layer6_runner")
            robot_id = self._create_robot(db, user_id, "Runner")
            for index, turns in enumerate([7, 5, 4, 6, 3]):
                self._insert_explore_end(db, user_id, robot_id, turns=turns, request_id=f"run-{index}", ts_offset=index)
            self._insert_explore_end(db, user_id, robot_id, turns=2, request_id="run-4", ts_offset=99)
            self._insert_boss_defeat(db, user_id, robot_id)
            db.commit()

            snapshot = game_app._layer_record_snapshot(db, 6, week_key=self.week_key, limit=3)

            self.assertEqual(snapshot["fastest"][0]["record_label"], "最短攻略 3ターン")
            self.assertEqual(snapshot["heat"][0]["sortie_count"], 5)
            self.assertEqual(snapshot["stability"][0]["record_label"], "安定攻略 100%")
            self.assertEqual(snapshot["boss"][0]["record_label"], "第6層最終試験 初撃破")

    def test_layer6_records_exclude_admin_test_and_marked_users(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            real_id = self._create_user(db, "real_layer6")
            admin_id = self._create_user(db, "admin_layer6", is_admin=1)
            test_id = self._create_user(db, "test_layer6")
            excluded_id = self._create_user(db, "excluded_layer6", analytics_excluded=1)
            ids = [real_id, admin_id, test_id, excluded_id]
            robots = {uid: self._create_robot(db, uid, f"R{uid}") for uid in ids}
            for offset, uid in enumerate(ids):
                self._insert_explore_end(db, uid, robots[uid], turns=offset + 2, request_id=f"exclude-{uid}", ts_offset=offset)
            db.commit()

            snapshot = game_app._layer_record_snapshot(db, 6, week_key=self.week_key, limit=10)

            self.assertEqual([row["user_id"] for row in snapshot["fastest"]], [real_id])
            self.assertEqual([row["user_id"] for row in snapshot["heat"]], [real_id])

    def test_ranking_and_records_pages_render_layer6_research(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            user_id = self._create_user(db, "route_layer6")
            robot_id = self._create_robot(db, user_id, "RouteBot")
            self._insert_explore_end(db, user_id, robot_id, turns=4, request_id="route-1")
            db.commit()

        with game_app.app.test_client() as client:
            self._login(client, user_id, "route_layer6")
            ranking = client.get("/ranking?metric=layer6_research")
            self.assertEqual(ranking.status_code, 200)
            self.assertIn("今週の第6層研究ランキング".encode(), ranking.data)
            self.assertIn("route_layer6".encode(), ranking.data)
            records = client.get("/records")
            self.assertEqual(records.status_code, 200)
            self.assertIn("第6層研究記録".encode(), records.data)
            self.assertIn("最短攻略 4ターン".encode(), records.data)

    def test_admin_metrics_layer6_panel_is_admin_only(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            user_id = self._create_user(db, "normal_metrics")
            admin_id = self._create_user(db, "admin_metrics", is_admin=1)
            robot_id = self._create_robot(db, user_id, "MetricBot")
            self._insert_explore_end(db, user_id, robot_id, turns=6, request_id="metric-1")
            db.commit()

        with game_app.app.test_client() as client:
            self._login(client, user_id, "normal_metrics")
            self.assertEqual(client.get("/admin/metrics").status_code, 403)

        with game_app.app.test_client() as client:
            self._login(client, admin_id, "admin_metrics")
            response = client.get("/admin/metrics")
            self.assertEqual(response.status_code, 200)
            self.assertIn("第6層研究記録".encode(), response.data)
            self.assertIn("通常戦出撃".encode(), response.data)


if __name__ == "__main__":
    unittest.main()
