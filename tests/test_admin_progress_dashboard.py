import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class AdminProgressDashboardTests(unittest.TestCase):
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
            users = [
                ("progress_admin", 1, 1),
                ("stuck_layer1", 0, 1),
                ("stuck_layer2", 0, 2),
                ("stuck_layer4", 0, 4),
                ("cleared_layer5", 0, 5),
            ]
            self.user_ids = {}
            for username, is_admin, max_layer in users:
                db.execute(
                    """
                    INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer, last_seen_at)
                    VALUES (?, ?, ?, ?, 0, ?, ?)
                    """,
                    (username, "x", now, is_admin, max_layer, now),
                )
                self.user_ids[username] = int(
                    db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"]
                )

            def add_event(username, event_type, payload, created_at):
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        int(created_at),
                        str(event_type),
                        json.dumps(payload, ensure_ascii=False),
                        int(self.user_ids[username]),
                    ),
                )

            base = now - 300
            add_event("stuck_layer1", game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], {"area_key": "layer_1"}, base + 1)

            add_event(
                "stuck_layer2",
                game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                {"area_key": "layer_1", "boss_kind": "fixed", "unlocked_layer": 2},
                base + 2,
            )
            add_event("stuck_layer2", game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], {"area_key": "layer_2"}, base + 3)

            for idx, area_key in enumerate(("layer_4_forge", "layer_4_haze")):
                add_event("stuck_layer4", game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], {"area_key": area_key}, base + 10 + idx)
                add_event(
                    "stuck_layer4",
                    game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                    {"area_key": area_key, "boss_kind": "fixed"},
                    base + 20 + idx,
                )

            add_event(
                "cleared_layer5",
                game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                {"area_key": "layer_4_final", "boss_kind": "fixed", "unlocked_layer": 5},
                base + 30,
            )
            add_event("cleared_layer5", game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], {"area_key": "layer_5_labyrinth"}, base + 31)
            add_event(
                "cleared_layer5",
                game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                {"area_key": "layer_5_labyrinth", "boss_kind": "fixed"},
                base + 32,
            )
            add_event(
                "cleared_layer5",
                game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                {"area_key": "layer_5_pinnacle", "boss_kind": "fixed"},
                base + 33,
            )
            add_event(
                "cleared_layer5",
                game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                {"area_key": "layer_5_final", "boss_kind": "fixed"},
                base + 34,
            )
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def test_progression_snapshot_reaggregates_layers_and_boss_blockers(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            snapshot = game_app._admin_progression_snapshot(db)

        self.assertEqual(snapshot["total_users"], 4)
        self.assertEqual(snapshot["admin_only_count"], 1)
        self.assertEqual(snapshot["deepest_layer"], 5)
        self.assertEqual(snapshot["boss_blocker_total"], 3)

        reach_by_layer = {row["layer"]: int(row["count"]) for row in snapshot["layer_reach_rows"]}
        self.assertEqual(reach_by_layer[1], 4)
        self.assertEqual(reach_by_layer[2], 3)
        self.assertEqual(reach_by_layer[4], 2)
        self.assertEqual(reach_by_layer[5], 1)

        stop_by_layer = {row["layer"]: int(row["count"]) for row in snapshot["layer_stop_rows"]}
        self.assertEqual(stop_by_layer[1], 1)
        self.assertEqual(stop_by_layer[2], 1)
        self.assertEqual(stop_by_layer[4], 1)
        self.assertEqual(stop_by_layer[5], 1)

        blockers = {row["layer"]: int(row["count"]) for row in snapshot["boss_block_rows"]}
        self.assertEqual(blockers[1], 1)
        self.assertEqual(blockers[2], 1)
        self.assertEqual(blockers[4], 1)

        rows_by_name = {row["username"]: row for row in snapshot["user_rows"]}
        self.assertEqual(rows_by_name["stuck_layer1"]["boss_status"], "第1層ボス未撃破")
        self.assertEqual(rows_by_name["stuck_layer2"]["boss_status"], "第2層ボス未撃破")
        self.assertIn("第4層試験ボス", rows_by_name["stuck_layer4"]["boss_status"])
        self.assertEqual(rows_by_name["cleared_layer5"]["boss_status"], "第5層最終試験撃破済み")


if __name__ == "__main__":
    unittest.main()
