import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class CommsRoutesTests(unittest.TestCase):
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
                VALUES (?, ?, ?, 0, 0, 1)
                """,
                ("comms_tester", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("comms_tester",),
            ).fetchone()["id"]
            game_app.initialize_new_user(db, self.user_id)
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 0, 0, 1)
                """,
                ("roommate", "x", now),
            )
            self.other_user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("roommate",),
            ).fetchone()["id"]
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "comms_tester"
        return client

    def test_comms_hub_lists_all_surfaces(self):
        client = self._client()
        resp = client.get("/comms")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("世界ログ", html)
        self.assertIn("会議室", html)
        self.assertIn("陣営通信", html)
        self.assertIn("個人ログ", html)
        self.assertIn("準備中", html)
        self.assertIn("世界の動きや、他のロボ使いの声がここに流れます。", html)
        self.assertIn("ロボ使いたちが集まって話せる場所です。", html)
        self.assertIn("あなたのロボの成長や出来事がここに残ります。", html)

    def test_comms_world_shows_world_scale_events_and_public_posts_only(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    now,
                    game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                    json.dumps(
                        {
                            "enemy_name": "試験機イグニス",
                            "area_key": "layer_1",
                            "area_label": "第一層",
                            "unlocked_layer": 2,
                        },
                        ensure_ascii=False,
                    ),
                    self.user_id,
                ),
            )
            db.execute(
                """
                INSERT INTO chat_messages (user_id, username, room_key, message, created_at, deleted_at)
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (
                    self.other_user_id,
                    "roommate",
                    game_app.COMM_WORLD_ROOM_KEY,
                    "みんなの動きが見えていい感じ",
                    game_app.now_str(),
                ),
            )
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    now + 1,
                    game_app.AUDIT_EVENT_TYPES["DROP"],
                    json.dumps(
                        {
                            "part_key": "head_1",
                            "part_type": "HEAD",
                            "rarity": "N",
                            "plus": 0,
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
                    now + 2,
                    game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"],
                    json.dumps(
                        {
                            "part_type": "HEAD",
                            "target_part_name": "秘密進化ヘッド",
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
                    now + 3,
                    game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                    json.dumps(
                        {
                            "area_key": "layer_1",
                            "result": {"win": True, "battle_count": 1, "timeout": False},
                            "battles": [{"enemy": {"name_ja": "試験ドローン"}}],
                            "rewards": {"coins": 3, "cores": 0, "drops": []},
                            "boss": {"is_area_boss": False},
                        },
                        ensure_ascii=False,
                    ),
                    self.user_id,
                ),
            )
            db.commit()

        client = self._client()
        resp = client.get("/comms/world")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("SYSTEM LOG", html)
        self.assertIn("PUBLIC SIGNAL", html)
        self.assertIn("ボス初討伐", html)
        self.assertIn("試験機イグニス", html)
        self.assertIn("層解放", html)
        self.assertIn("みんなの動きが見えていい感じ", html)
        self.assertIn("roommate", html)
        self.assertNotIn("秘密進化ヘッド", html)
        self.assertNotIn("試験ドローン", html)

    def test_comms_world_post_creates_world_public_message_and_audit(self):
        client = self._client()
        first = client.post("/comms/world", data={"message": "世界ログへ送信", "next": "/comms/world"})
        self.assertEqual(first.status_code, 302)

        second = client.post("/comms/world", data={"message": "連投チェック", "next": "/comms/world"}, follow_redirects=True)
        self.assertEqual(second.status_code, 200)
        html = second.get_data(as_text=True)
        self.assertIn("連投はあと", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            rows = db.execute(
                """
                SELECT room_key, message
                FROM chat_messages
                WHERE user_id = ?
                ORDER BY id DESC
                """,
                (self.user_id,),
            ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["room_key"], game_app.COMM_WORLD_ROOM_KEY)
            self.assertEqual(rows[0]["message"], "世界ログへ送信")
            audit_row = db.execute(
                """
                SELECT event_type, request_id, payload_json
                FROM world_events_log
                WHERE event_type = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (game_app.AUDIT_EVENT_TYPES["CHAT_POST"],),
            ).fetchone()
            self.assertIsNotNone(audit_row)
            self.assertTrue(audit_row["request_id"])
            payload = json.loads(audit_row["payload_json"] or "{}")
            self.assertEqual(payload.get("room_key"), game_app.COMM_WORLD_ROOM_KEY)

    def test_comms_rooms_filters_messages_by_room(self):
        client = self._client()
        resp = client.post(
            "/comms/rooms?room=beginner_room",
            data={
                "room_key": "beginner_room",
                "message": "初心者向けの相談です",
                "next": "/comms/rooms?room=beginner_room",
            },
        )
        self.assertEqual(resp.status_code, 302)

        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                INSERT INTO chat_messages (user_id, username, room_key, message, created_at, deleted_at)
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (
                    self.other_user_id,
                    "roommate",
                    "global_room",
                    "全体会議室の話題",
                    game_app.now_str(),
                ),
            )
            db.commit()

        beginner_resp = client.get("/comms/rooms?room=beginner_room")
        self.assertEqual(beginner_resp.status_code, 200)
        beginner_html = beginner_resp.get_data(as_text=True)
        self.assertIn("初心者相談室", beginner_html)
        self.assertIn("初心者向けの相談です", beginner_html)
        self.assertNotIn("全体会議室の話題", beginner_html)

        global_resp = client.get("/comms/rooms?room=global_room")
        self.assertEqual(global_resp.status_code, 200)
        global_html = global_resp.get_data(as_text=True)
        self.assertIn("全体会議室", global_html)
        self.assertIn("全体会議室の話題", global_html)

    def test_comms_personal_collects_growth_battle_and_acquisition_logs(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            week_key = game_app._world_week_key()
            week_start, _ = game_app._world_week_bounds(week_key)
            now = int(week_start.timestamp()) + 3600
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                VALUES (?, 