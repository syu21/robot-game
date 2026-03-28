import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class AreaBossTests(unittest.TestCase):
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
                VALUES (?, ?, ?, 1, 30, 0, 2)
                """,
                ("area_boss_tester", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("area_boss_tester",),
            ).fetchone()["id"]
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (self.user_id, "BossRunner", now, now),
            )
            robot_id = db.execute(
                "SELECT id FROM robot_instances WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()["id"]

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
                (
                    robot_id,
                    pick_key("HEAD"),
                    pick_key("RIGHT_ARM"),
                    pick_key("LEFT_ARM"),
                    pick_key("LEGS"),
                ),
            )
            db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (robot_id, self.user_id))
            db.execute(
                """
                INSERT INTO enemies
                (key, name_ja, image_path, tier, element, hp, atk, def, spd, acc, cri, faction, is_boss, boss_area_key, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 1)
                ON CONFLICT(key) DO UPDATE SET
                    name_ja = excluded.name_ja,
                    image_path = excluded.image_path,
                    tier = excluded.tier,
                    element = excluded.element,
                    hp = excluded.hp,
                    atk = excluded.atk,
                    def = excluded.def,
                    spd = excluded.spd,
                    acc = excluded.acc,
                    cri = excluded.cri,
                    faction = excluded.faction,
                    is_boss = excluded.is_boss,
                    boss_area_key = excluded.boss_area_key,
                    is_active = excluded.is_active
                """,
                (
                    "test_layer2_boss",
                    "放電帯ボス",
                    "assets/placeholder_enemy.png",
                    2,
                    "THUNDER",
                    1,
                    1,
                    1,
                    1,
                    1,
                    1,
                    "ventra",
                    "layer_2",
                ),
            )
            db.execute(
                """
                UPDATE enemies
                SET is_active = 0
                WHERE COALESCE(is_boss, 0) = 1
                  AND boss_area_key = 'layer_2'
                  AND key <> 'test_layer2_boss'
                """
            )
            db.execute(
                """
                INSERT INTO robot_decor_assets (key, name_ja, image_path, is_active, created_at)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(key) DO UPDATE SET name_ja = excluded.name_ja, image_path = excluded.image_path, is_active = 1
                """,
                ("boss_emblem_ventra", "ヴェントラ紋章", "", now),
            )
            db.execute(
                """
                INSERT INTO user_boss_progress (user_id, area_key, no_boss_streak, updated_at)
                VALUES (?, 'layer_2', ?, ?)
                ON CONFLICT(user_id, area_key) DO UPDATE SET no_boss_streak = excluded.no_boss_streak, updated_at = excluded.updated_at
                """,
                (self.user_id, int(game_app.AREA_BOSS_PITY_MISSES["layer_2"]) - 1, now),
            )
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    @staticmethod
    def _stable_weekly_env():
        return {
            "element": "NORMAL",
            "mode": "安定",
            "enemy_spawn_bonus": 0.0,
            "drop_bonus": 0.0,
            "reason": "test",
        }

    @staticmethod
    def _resolve_for_win(att_atk, att_acc, att_cri, def_def, def_acc, **kwargs):
        if int(att_atk) >= 5:
            return 999, False
        return 0, False

    @staticmethod
    def _resolve_for_lose(att_atk, att_acc, att_cri, def_def, def_acc, **kwargs):
        if int(att_atk) >= 5:
            return 0, False
        return 999, False

    def _new_client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "area_boss_tester"
        return client

    def _set_boss_progress_for_area(self, area_key):
        pity_key = game_app._boss_area_key_for_route(area_key)
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                INSERT INTO user_boss_progress (user_id, area_key, no_boss_streak, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, area_key) DO UPDATE SET
                    no_boss_streak = excluded.no_boss_streak,
                    updated_at = excluded.updated_at
                """,
                (self.user_id, area_key, int(game_app.AREA_BOSS_PITY_MISSES[pity_key]) - 1, int(time.time())),
            )
            db.commit()

    def _run_layer2_boss_defeat_once(self, area_key="layer_2"):
        client = self._new_client()
        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "resolve_attack", side_effect=self._resolve_for_win
        ):
            resp = client.post("/explore", data={"area_key": area_key, "boss_enter": "1"})
        return resp

    def _run_layer2_boss_lose_once(self, area_key="layer_2"):
        client = self._new_client()
        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "resolve_attack", side_effect=self._resolve_for_lose
        ):
            resp = client.post("/explore", data={"area_key": area_key, "boss_enter": "1"})
        return resp

    def _trigger_layer2_boss_alert_once(self, area_key="layer_2"):
        client = self._new_client()
        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()):
            resp = client.post("/explore", data={"area_key": area_key}, follow_redirects=True)
        return resp

    def test_encounter_only_does_not_post_system_chat(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                UPDATE user_boss_progress
                SET no_boss_streak = ?, updated_at = ?
                WHERE user_id = ? AND area_key = 'layer_2'
                """,
                (int(game_app.AREA_BOSS_PITY_MISSES["layer_2"]) - 1, int(time.time()), self.user_id),
            )
            before_system = db.execute(
                "SELECT COUNT(*) AS c FROM chat_messages WHERE username = 'SYSTEM'"
            ).fetchone()["c"]
            before_encounter = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = 'audit.boss.encounter' AND user_id = ?",
                (self.user_id,),
            ).fetchone()["c"]
            before_defeat = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = 'audit.boss.defeat' AND user_id = ?",
                (self.user_id,),
            ).fetchone()["c"]
            db.commit()

        alert_resp = self._trigger_layer2_boss_alert_once()
        self.assertEqual(alert_resp.status_code, 200)
        self.assertIn("ボス警報", alert_resp.get_data(as_text=True))

        resp = self._run_layer2_boss_lose_once()
        self.assertEqual(resp.status_code, 200)
        self.assertIn("放電帯ボス", resp.get_data(as_text=True))

        with game_app.app.app_context():
            db = game_app.get_db()
            after_system = db.execute(
                "SELECT COUNT(*) AS c FROM chat_messages WHERE username = 'SYSTEM'"
            ).fetchone()["c"]
            after_encounter = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = 'audit.boss.encounter' AND user_id = ?",
                (self.user_id,),
            ).fetchone()["c"]
            after_defeat = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = 'audit.boss.defeat' AND user_id = ?",
                (self.user_id,),
            ).fetchone()["c"]

            self.assertEqual(int(after_system) - int(before_system), 0)
            self.assertEqual(int(after_encounter) - int(before_encounter), 1)
            self.assertEqual(int(after_defeat) - int(before_defeat), 0)

    def test_layer2_pity_boss_logs_and_decor_inventory(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            before_system = db.execute(
                "SELECT COUNT(*) AS c FROM chat_messages WHERE username = 'SYSTEM'"
            ).fetchone()["c"]

        alert1 = self._trigger_layer2_boss_alert_once()
        self.assertEqual(alert1.status_code, 200)
        self.assertIn("ボス警報", alert1.get_data(as_text=True))

        resp1 = self._run_layer2_boss_defeat_once()
        self.assertEqual(resp1.status_code, 200)
        html1 = resp1.get_data(as_text=True)
        self.assertIn("放電帯ボス", html1)
        self.assertIn("BOSS", html1)
        self.assertIn("警報：", html1)
        self.assertIn("BOSS DEFEATED", html1)
        self.assertIn("エリアボス報酬", html1)
        self.assertIn("報酬DECOR:", html1)
        self.assertIn("ヴェントラ紋章", html1)
        self.assertIn("《討伐記録》放電帯ボス撃破！", html1)
        with game_app.app.app_context():
            db = game_app.get_db()
            after_first_system = db.execute(
                "SELECT COUNT(*) AS c FROM chat_messages WHERE username = 'SYSTEM'"
            ).fetchone()["c"]
            self.assertEqual(int(after_first_system) - int(before_system), 1)

        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                UPDATE user_boss_progress
                SET no_boss_streak = ?, updated_at = ?
                WHERE user_id = ? AND area_key = 'layer_2'
                """,
                (int(game_app.AREA_BOSS_PITY_MISSES["layer_2"]) - 1, int(time.time()), self.user_id),
            )
            db.commit()

        alert2 = self._trigger_layer2_boss_alert_once()
        self.assertEqual(alert2.status_code, 200)
        self.assertIn("ボス警報", alert2.get_data(as_text=True))

        resp2 = self._run_layer2_boss_defeat_once()
        self.assertEqual(resp2.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            encounter_count = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = 'audit.boss.encounter' AND user_id = ?",
                (self.user_id,),
            ).fetchone()["c"]
            defeat_count = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = 'audit.boss.defeat' AND user_id = ?",
                (self.user_id,),
            ).fetchone()["c"]
            self.assertGreaterEqual(int(encounter_count), 1)
            self.assertGreaterEqual(int(defeat_count), 1)

            inv_count = db.execute(
                "SELECT COUNT(*) AS c FROM user_decor_inventory WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()["c"]
            self.assertEqual(int(inv_count), 1)

            payload_row = db.execute(
                """
                SELECT payload_json
                FROM world_events_log
                WHERE event_type = 'audit.boss.defeat' AND user_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (self.user_id,),
            ).fetchone()
            self.assertIsNotNone(payload_row)
            self.assertIn("reward_decor_asset_id", payload_row["payload_json"])
            self.assertIn("boss_emblem_ventra", payload_row["payload_json"])
            self.assertIn('"reward_missing": false', payload_row["payload_json"].lower())

            chats = db.execute(
                "SELECT message FROM chat_messages WHERE username = 'SYSTEM' ORDER BY id DESC LIMIT 5"
            ).fetchall()
            chat_text = "\n".join(row["message"] for row in chats)
            self.assertIn("【BOSS撃破】", chat_text)
            self.assertIn("『放電帯ボス』を討伐", chat_text)
            self.assertNotIn("遭遇", chat_text)
            after_system = db.execute(
                "SELECT COUNT(*) AS c FROM chat_messages WHERE username = 'SYSTEM'"
            ).fetchone()["c"]
            self.assertEqual(int(after_system) - int(before_system), 2)

    def test_layer2_side_routes_grant_ventra_reward(self):
        for area_key in ("layer_2_mist", "layer_2_rush"):
            with self.subTest(area_key=area_key):
                self._set_boss_progress_for_area(area_key)
                alert = self._trigger_layer2_boss_alert_once(area_key=area_key)
                self.assertEqual(alert.status_code, 200)
                self.assertIn("ボス警報", alert.get_data(as_text=True))

                resp = self._run_layer2_boss_defeat_once(area_key=area_key)
                self.assertEqual(resp.status_code, 200)
                html = resp.get_data(as_text=True)
                self.assertIn("ヴェントラ紋章", html)

                with game_app.app.app_context():
                    db = game_app.get_db()
                    payload_row = db.execute(
                        """
                        SELECT payload_json
                        FROM world_events_log
                        WHERE event_type = 'audit.boss.defeat' AND user_id = ?
                          AND COALESCE(json_extract(payload_json, '$.area_key'), '') = ?
                        ORDER BY id DESC
                        LIMIT 1
                        """,
                        (self.user_id, area_key),
                    ).fetchone()
                    self.assertIsNotNone(payload_row)
                    self.assertIn("boss_emblem_ventra", payload_row["payload_json"])
                    self.assertIn('"reward_missing": false', payload_row["payload_json"].lower())

    def test_reward_missing_does_not_break_explore(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                UPDATE user_boss_progress
                SET no_boss_streak = ?, updated_at = ?
                WHERE user_id = ? AND area_key = 'layer_2'
                """,
                (int(game_app.AREA_BOSS_PITY_MISSES["layer_2"]) - 1, int(time.time()), self.user_id),
            )
            db.commit()

        original = dict(game_app.AREA_BOSS_DECOR_REWARD_KEYS)
        game_app.AREA_BOSS_DECOR_REWARD_KEYS["layer_2"] = ["missing_decor_key_for_test"]
        try:
            alert_resp = self._trigger_layer2_boss_alert_once()
            self.assertEqual(alert_resp.status_code, 200)
            self.assertIn("ボス警報", alert_resp.get_data(as_text=True))

            resp = self._run_layer2_boss_defeat_once()
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn("放電帯ボス", html)
            self.assertIn("エリアボス報酬は今回はありません。撃破記録は正常に反映されています。", html)
            self.assertNotIn("報酬の表示に失敗しました", html)

            with game_app.app.app_context():
                db = game_app.get_db()
                inv_count = db.execute(
                    "SELECT COUNT(*) AS c FROM user_decor_inventory WHERE user_id = ?",
                    (self.user_id,),
                ).fetchone()["c"]
                self.assertEqual(int(inv_count), 0)

                payload_row = db.execute(
                    """
                    SELECT payload_json
                    FROM world_events_log
                    WHERE event_type = 'audit.boss.defeat' AND user_id = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (self.user_id,),
                ).fetchone()
                self.assertIsNotNone(payload_row)
                self.assertIn('"reward_missing": true', payload_row["payload_json"].lower())
        finally:
            game_app.AREA_BOSS_DECOR_REWARD_KEYS.clear()
            game_app.AREA_BOSS_DECOR_REWARD_KEYS.update(original)

    def test_home_hides_recent_drop_and_boss_pity_panels(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO user_boss_progress (user_id, area_key, no_boss_streak, updated_at)
                VALUES (?, 'layer_1', 7, ?)
                ON CONFLICT(user_id, area_key) DO UPDATE SET no_boss_streak = 7, updated_at = excluded.updated_at
                """,
                (self.user_id, now),
            )
            db.execute(
                """
                INSERT INTO user_boss_progress (user_id, area_key, no_boss_streak, updated_at)
                VALUES (?, 'layer_2', 14, ?)
                ON CONFLICT(user_id, area_key) DO UPDATE SET no_boss_streak = 14, updated_at = excluded.updated_at
                """,
                (self.user_id, now),
            )
            db.execute(
                """
                INSERT INTO user_boss_progress (user_id, area_key, no_boss_streak, updated_at)
                VALUES (?, 'layer_3', 0, ?)
                ON CONFLICT(user_id, area_key) DO UPDATE SET no_boss_streak = 0, updated_at = excluded.updated_at
                """,
                (self.user_id, now),
            )
            db.commit()

        client = self._new_client()
        with patch.object(game_app, "_compose_instance_image", return_value=None):
            resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertNotIn("直近ドロップ", html)
        self.assertNotIn("エリアボス天井", html)

    def test_layer2_main_route_keeps_baseline_bo