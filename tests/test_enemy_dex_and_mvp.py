import os
import tempfile
import time
import unittest
import json

import app as game_app
import init_db


class EnemyDexAndMvpTests(unittest.TestCase):
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
                "INSERT INTO users (username, password_hash, created_at, is_admin, faction) VALUES (?, ?, ?, 0, 'aurix')",
                ("viewer_user", "x", now),
            )
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin, faction) VALUES (?, ?, ?, 0, 'ignis')",
                ("mvp_user", "x", now),
            )
            self.viewer_id = db.execute("SELECT id FROM users WHERE username = 'viewer_user'").fetchone()["id"]
            self.mvp_user_id = db.execute("SELECT id FROM users WHERE username = 'mvp_user'").fetchone()["id"]
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _login(self, client, user_id, username):
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["username"] = username

    def test_home_shows_weekly_mvp_when_logs_exist(self):
        now = int(time.time())
        with game_app.app.app_context():
            db = game_app.get_db()
            for _ in range(3):
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                    VALUES (?, 'audit.explore.end', ?, ?)
                    """,
                    (now, json.dumps({"result": {"win": True}}, ensure_ascii=False), self.mvp_user_id),
                )
            db.commit()
        with game_app.app.test_client() as client:
            self._login(client, self.viewer_id, "viewer_user")
            resp = client.get("/home")
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn("今週のMVP", html)
            self.assertIn("mvp_user", html)

    def test_enemy_dex_unlocks_stats_after_defeat(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            enemy_key = db.execute("SELECT key FROM enemies ORDER BY id ASC LIMIT 1").fetchone()["key"]
            game_app._dex_upsert_enemy(db, user_id=self.viewer_id, enemy_key=enemy_key, is_defeat=False)
            db.commit()
        with game_app.app.test_client() as client:
            self._login(client, self.viewer_id, "viewer_user")
            detail1 = client.get(f"/dex/enemies/{enemy_key}")
            self.assertEqual(detail1.status_code, 200)
            self.assertIn("撃破で能力詳細が解禁されます。", detail1.get_data(as_text=True))
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app._dex_upsert_enemy(db, user_id=self.viewer_id, enemy_key=enemy_key, is_defeat=True)
            db.commit()
        with game_app.app.test_client() as client:
            self._login(client, self.viewer_id, "viewer_user")
            detail2 = client.get(f"/dex/enemies/{enemy_key}")
            self.assertEqual(detail2.status_code, 200)
            self.assertIn("耐久", detail2.get_data(as_text=True))

    def test_enemy_dex_detail_prefers_active_image_for_legacy_key(self):
        legacy_key = "legacy_steel_scout"
        active_key = "active_steel_scout"
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO enemies (key, name_ja, image_path, tier, element, hp, atk, def, spd, acc, cri, is_active)
                VALUES (?, ?, ?, 2, 'NORMAL', 30, 9, 8, 7, 8, 2, 0)
                """,
                (legacy_key, "スチールスカウト", "enemies/steel_scout.png"),
            )
            db.execute(
                """
                INSERT INTO enemies (key, name_ja, image_path, tier, element, hp, atk, def, spd, acc, cri, is_active)
                VALUES (?, ?, ?, 2, 'NORMAL', 30, 9, 8, 7, 8, 2, 1)
                """,
                (active_key, "スチールスカウト", "enemies/enemy14.png"),
            )
            db.execute(
                """
                INSERT INTO user_enemy_dex (user_id, enemy_key, first_seen_at, first_defeated_at, seen_count, defeat_count)
                VALUES (?, ?, ?, ?, 1, 1)
                """,
                (self.viewer_id, legacy_key, now, now),
            )
            db.commit()

        with game_app.app.test_client() as client:
            self._login(client, self.viewer_id, "viewer_user")
            detail = client.get(f"/dex/enemies/{legacy_key}")
            self.assertEqual(detail.status_code, 200)
            html = detail.get_data(as_text=True)
            self.assertIn("キー: legacy_steel_scout", html)
            self.assertIn("/static/enemies/enemy14.png", html)


if __name__ == "__main__":
    unittest.main()
