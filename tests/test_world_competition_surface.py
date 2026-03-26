import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class WorldCompetitionSurfaceTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer, faction)
                VALUES (?, ?, ?, 1, 0, 3, 'ignis')
                """,
                ("world_surface_user", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("world_surface_user",),
            ).fetchone()["id"]
            game_app.initialize_new_user(db, self.user_id)

            for username, faction in (("ventra_member", "ventra"), ("aurix_member", "aurix")):
                db.execute(
                    """
                    INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer, faction)
                    VALUES (?, ?, ?, 0, 0, 3, ?)
                    """,
                    (username, "x", now, faction),
                )
                other_id = db.execute(
                    "SELECT id FROM users WHERE username = ?",
                    (username,),
                ).fetchone()["id"]
                game_app.initialize_new_user(db, other_id)
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "world_surface_user"
        return client

    def test_world_page_shows_weekly_environment_and_faction_meaning(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            week_key = game_app._world_week_key()
            prev_week_key = game_app._faction_prev_week_key(week_key)
            game_app._ensure_world_week_environment(db)
            db.execute(
                """
                UPDATE world_weekly_environment
                SET element = 'FIRE', mode = '暴走', enemy_spawn_bonus = 0.25, drop_bonus = 0.10
                WHERE week_key = ?
                """,
                (week_key,),
            )
            db.execute(
                """
                INSERT INTO world_weekly_counters (week_key, metric_key, value)
                VALUES (?, 'builds_FIRE', 5), (?, 'builds_WIND', 3)
                ON CONFLICT(week_key, metric_key) DO UPDATE SET value = excluded.value
                """,
                (week_key, week_key),
            )
            now = int(time.time())
            for offset, area_key in enumerate(("layer_2", "layer_2", "layer_3")):
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        now + offset,
                        game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                        json.dumps({"area_key": area_key, "result": {"win": True}}, ensure_ascii=False),
                        self.user_id,
                    ),
                )
            for faction, points in (("ignis", 120), ("ventra", 90), ("aurix", 70)):
                db.execute(
                    """
                    INSERT INTO world_faction_weekly_scores (week_key, faction, points, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(week_key, faction) DO UPDATE SET points = excluded.points, updated_at = excluded.updated_at
                    """,
                    (week_key, faction, points, now),
                )
            db.execute(
                """
                INSERT INTO world_faction_weekly_result (week_key, winner_faction, scores_json, computed_at)
                VALUES (?, 'ignis', ?, ?)
                """,
                (prev_week_key, json.dumps({"ignis": 88, "ventra": 55, "aurix": 40}, ensure_ascii=False), now),
            )
            db.commit()

        client = self._client()
        resp = client.get("/world")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("世界戦況", html)
        self.assertIn("今週の熱源", html)
        self.assertIn("第二層: 放電ノイズ帯", html)
        self.assertIn("陣営戦", html)
        self.assertIn("突破主義", html)
        self.assertIn("勝利陣営バフ発動中", html)
        self.assertIn("user-chip mini", html)
        self.assertIn("world-mvp-thumb", html)

    def test_records_page_shows_first_records_and_weekly_records(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            week_key = game_app._world_week_key()
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    now - 200,
                    game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                    json.dumps(
                        {
                            "area_key": "layer_1",
                            "enemy_name": "オリクス・ガーディアン",
                            "robot_name": "RecordBot",
                        },
                        ensure_ascii=False,
                    ),
                    self.user_id,
                ),
            )
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    now - 150,
                    game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"],
                    json.dumps(
                        {
                            "part_type": "HEAD",
                            "target_part_name": "機巧頭冠改",
                        },
                        ensure_ascii=False,
                    ),
                    self.user_id,
                ),
            )
            for offset in range(3):
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        now + offset,
                        game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                        json.dumps({"week_key": week_key, "result": {"win": True}}, ensure_ascii=False),
                        self.user_id,
                    ),
                )
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    now + 20,
                    game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                    json.dumps({"area_key": "layer_2", "enemy_name": "ヴェントラ・センチネル"}, ensure_ascii=False),
                    self.user_id,
                ),
            )
            db.commit()

        client = self._client()
        resp = client.get("/records")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("記録庫", html)
        self.assertIn("第一層: 風化した整備通路 初撃破", html)
        self.assertIn("機巧頭冠改", html)
        self.assertIn("今週探索数ランキング", html)
        self.assertIn("最速ロボランキング", html)
        self.assertIn("話題ロボ", html)
        self.assertIn("user-chip mini", html)
        self.assertIn("ranking-robot-thumb", html)

    def test_home_links_world_and_records_pages(self):
        client = self._client()
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("/world", html)
        self.assertIn("/records", html)


if __name__ == "__main__":
    unittest.main()
