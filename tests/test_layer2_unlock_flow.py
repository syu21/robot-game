import json
import os
import tempfile
import time
import unittest
from unittest import mock

import app as game_app
import init_db


class Layer2UnlockFlowTests(unittest.TestCase):
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
                VALUES ('layer2_user', 'x', ?, 0, 0, 0, 1)
                """,
                (now,),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = 'layer2_user'").fetchone()["id"])
            self.robot_id = self._create_active_robot(db, self.user_id, now)
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
            sess["username"] = "layer2_user"
        return client

    def _create_active_robot(self, db, user_id, now):
        db.execute(
            """
            INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
            VALUES (?, 'Layer2Bot', 'active', ?, ?)
            """,
            (int(user_id), int(now), int(now)),
        )
        robot_id = int(db.execute("SELECT id FROM robot_instances WHERE user_id = ?", (int(user_id),)).fetchone()["id"])

        def pick_key(part_type):
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
            (robot_id, pick_key("HEAD"), pick_key("RIGHT_ARM"), pick_key("LEFT_ARM"), pick_key("LEGS")),
        )
        db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (robot_id, int(user_id)))
        return robot_id

    def _event(self, db, event_type, payload, created_at=None):
        db.execute(
            """
            INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
            VALUES (?, ?, ?, ?)
            """,
            (
                int(created_at or time.time()),
                event_type,
                json.dumps(payload, ensure_ascii=False),
                self.user_id,
            ),
        )

    def test_layer1_boss_defeat_unlocks_layer2_once(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT * FROM users WHERE id = ?", (self.user_id,)).fetchone()
            enemy = {"key": game_app.LAYER_BOSS_KEY_BY_LAYER[1]}

            unlocked = game_app._maybe_unlock_next_layer(db, self.user_id, user, "layer_1", enemy)
            row = db.execute(
                "SELECT max_unlocked_layer, layer2_unlocked, layer2_unlocked_at FROM users WHERE id = ?",
                (self.user_id,),
            ).fetchone()
            self.assertEqual(unlocked, 2)
            self.assertEqual(int(row["max_unlocked_layer"]), 2)
            self.assertEqual(int(row["layer2_unlocked"]), 1)
            self.assertIsNotNone(row["layer2_unlocked_at"])

            user_after = db.execute("SELECT * FROM users WHERE id = ?", (self.user_id,)).fetchone()
            unlocked_again = game_app._maybe_unlock_next_layer(db, self.user_id, user_after, "layer_1", enemy)
            row_again = db.execute("SELECT layer2_unlocked_at FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertIsNone(unlocked_again)
            self.assertEqual(int(row_again["layer2_unlocked_at"]), int(row["layer2_unlocked_at"]))

    def test_home_next_action_shows_layer2_until_first_layer2_explore(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            self._event(
                db,
                game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                {
                    "area_key": "layer_1",
                    "boss_kind": "fixed",
                    "boss_key": game_app.LAYER_BOSS_KEY_BY_LAYER[1],
                    "unlocked_layer": 2,
                    "is_first_defeat": True,
                    "layer_unlock_triggered": True,
                },
                created_at=now - 60,
            )
            db.execute(
                "UPDATE users SET max_unlocked_layer = 2, layer2_unlocked = 1, layer2_unlocked_at = ? WHERE id = ?",
                (now - 60, self.user_id),
            )
            db.commit()

        client = self._client()
        with mock.patch.object(game_app, "_enforce_explore_cooldown_or_wait", return_value=0):
            res = client.get("/home")
        body = res.get_data(as_text=True)
        self.assertIn("新区域 解放", body)
        self.assertIn("第2層へ出撃", body)
        self.assertIn('name="entry_source" value="layer2_unlock_home"', body)

        with game_app.app.app_context():
            db = game_app.get_db()
            self._event(
                db,
                game_app.AUDIT_EVENT_TYPES["EXPLORE_START"],
                {"area_key": "layer_2", "entry_source": "layer2_unlock_home", "is_first_layer2_explore": True},
            )
            db.commit()

        with mock.patch.object(game_app, "_enforce_explore_cooldown_or_wait", return_value=0):
            res_after = client.get("/home")
        self.assertNotIn("新区域 解放", res_after.get_data(as_text=True))

    def test_layer2_first_explore_payload_and_metrics(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time()) - 120
            self._event(
                db,
                game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                {
                    "area_key": "layer_1",
                    "boss_kind": "fixed",
                    "boss_key": game_app.LAYER_BOSS_KEY_BY_LAYER[1],
                    "unlocked_layer": 2,
                    "is_first_defeat": True,
                    "layer_unlock_triggered": True,
                },
                created_at=now,
            )
            self._event(
                db,
                game_app.AUDIT_EVENT_TYPES["LAYER_UNLOCK"],
                {
                    "from_layer": 1,
                    "unlocked_layer": 2,
                    "trigger_type": "boss_defeat",
                    "trigger_boss_key": game_app.LAYER_BOSS_KEY_BY_LAYER[1],
                    "is_first_unlock": True,
                },
                created_at=now,
            )
            db.execute(
                "UPDATE users SET max_unlocked_layer = 2, layer2_unlocked = 1, layer2_unlocked_at = ? WHERE id = ?",
                (now, self.user_id),
            )
            db.commit()

        client = self._client()
        with mock.patch.object(game_app, "_enforce_explore_cooldown_or_wait", return_value=0):
            res = client.post(
                "/explore",
                data={
                    "area_key": "layer_2",
                    "entry_source": "layer2_unlock_home",
                    "explore_submission_id": "layer2-first",
                },
            )
        self.assertEqual(res.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                """
                SELECT payload_json
                FROM world_events_log
                WHERE user_id = ? AND event_type = ? AND COALESCE(json_extract(payload_json, '$.area_key'), '') = 'layer_2'
                ORDER BY id ASC
                LIMIT 1
                """,
                (self.user_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_START"]),
            ).fetchone()
            self.assertIsNotNone(row)
            payload = json.loads(row["payload_json"])
            self.assertTrue(payload["is_first_layer2_explore"])
            self.assertEqual(payload["entry_source"], "layer2_unlock_home")
            self.assertGreaterEqual(int(payload["seconds_from_layer_unlock"]), 0)

            snapshot = game_app._admin_first_experience_snapshot(db)
            self.assertEqual(snapshot["layer2_unlock"]["layer1_first_defeat_users"], 1)
            self.assertEqual(snapshot["layer2_unlock"]["unlocked_users"], 1)
            self.assertEqual(snapshot["layer2_unlock"]["first_explore_users"], 1)

    def test_battle_result_layer2_unlock_card_is_primary_cta(self):
        with game_app.app.test_request_context("/battle/result"):
            html = game_app.render_template(
                "battle.html",
                state={"active": 0, "enemy_name": "ボス", "enemy_hp": 0},
                log=[],
                log_entries=[],
                message=None,
                new_robot=None,
                explore_mode=True,
                explore_area_key="layer_1",
                explore_area_label="第一層",
                active_robot={"name": "Layer2Bot"},
                no_active_robot=False,
                turn_logs=[],
                summary={
                    "outcome": "勝利",
                    "outcome_is_win": True,
                    "explore_ct_remain": 18,
                    "explore_ct_ready_at": int(time.time()) + 18,
                    "explore_ct_is_admin": False,
                    "explore_ct_button_label": "もう一度出撃（あと18秒）",
                    "explore_ct_status_label": "CT中: あと18秒",
                    "reward_front": {"coin": 1},
                    "next_explore_submission_id": "layer2-result",
                    "layer2_unlock_result": {
                        "title": "第2層 解放",
                        "badge": "NEW",
                        "desc": "第1層の戦闘データを突破しました。新しい探索区画へ出撃できます。",
                        "area_label": "第二層: 放電ノイズ帯",
                        "area_desc": "より精密な戦闘データが要求される区画。",
                        "area_tendency": "攻撃寄りのパーツを観測しやすい区域です。",
                        "cta_label": "第2層へ出撃する",
                        "entry_source": "layer2_unlock_result",
                        "parts_label": "入手したパーツを見る",
                        "secondary_label": "基地へ戻る",
                        "robot_name": "Layer2Bot",
                        "boss_name": "第1層固定ボス",
                        "ct_label": "第2層へ出撃 あと 00:18",
                        "helper": "敵の反応傾向が変化します。今の機体でまず調査を始めましょう。",
                    },
                },
                battle_log_mode="collapsed",
                battle_ritual_overlay_enabled=False,
                battle_short_replay_enabled=False,
            )
            self.assertIn("第2層 解放", html)
            self.assertIn("Layer2Bot", html)
            self.assertIn("第二層: 放電ノイズ帯", html)
            self.assertIn("攻撃寄りのパーツを観測しやすい", html)
            self.assertIn("第2層へ出撃 あと 00:18", html)
            self.assertIn("入手したパーツを見る", html)
            self.assertEqual(html.count('name="entry_source" value="layer2_unlock_result"'), 1)
            self.assertNotIn("第1層へもう一度", html)

    def test_battle_result_shows_first_layer2_intro_once(self):
        with game_app.app.test_request_context("/battle/result"):
            html = game_app.render_template(
                "battle.html",
                state={"active": 0, "enemy_name": "敵", "enemy_hp": 0},
                log=[],
                log_entries=[],
                message=None,
                new_robot=None,
                explore_mode=True,
                explore_area_key="layer_2",
                explore_area_label="第二層",
                active_robot={"name": "Layer2Bot"},
                no_active_robot=False,
                turn_logs=[],
                summary={
                    "outcome": "勝利",
                    "outcome_is_win": True,
                    "explore_ct_remain": 0,
                    "explore_ct_ready_at": 0,
                    "explore_ct_is_admin": False,
                    "explore_ct_button_label": "もう一度出撃",
                    "explore_ct_status_label": "出撃可能",
                    "reward_front": {"coin": 1},
                    "layer2_first_explore_intro": {
                        "title": "第2層 初回調査",
                        "desc": "ここから敵の反応傾向が変化します。",
                    },
                },
                battle_log_mode="collapsed",
                battle_ritual_overlay_enabled=False,
                battle_short_replay_enabled=False,
            )
            self.assertIn("第2層 初回調査", html)
            self.assertIn("ここから敵の反応傾向が変化します。", html)


if __name__ == "__main__":
    unittest.main()
