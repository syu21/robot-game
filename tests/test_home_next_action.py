import os
import tempfile
import time
import unittest
import json
import re
from unittest import mock

import app as game_app
import init_db


class HomeNextActionTests(unittest.TestCase):
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
                VALUES (?, ?, ?, 1, 0, 1, 'ignis')
                """,
                ("home_next_tester", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("home_next_tester",),
            ).fetchone()["id"]
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _new_client(self, new_layer_badge=None):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "home_next_tester"
            if new_layer_badge is not None:
                session["home_new_layer_badge"] = int(new_layer_badge)
        return client

    def _create_active_robot(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (self.user_id, "GuideBot", now, now),
            )
            robot_id = db.execute(
                "SELECT id FROM robot_instances WHERE user_id = ? ORDER BY id DESC LIMIT 1",
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
            db.commit()

    def _set_boss_alert(self, area_key="layer_2", attempts=2):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            enemy_key = game_app.LAYER_BOSS_KEY_BY_LAYER[2 if area_key == "layer_2" else 1]
            enemy_id = db.execute("SELECT id FROM enemies WHERE key = ?", (enemy_key,)).fetchone()["id"]
            db.execute(
                """
                INSERT INTO user_boss_progress
                (user_id, area_key, no_boss_streak, active_boss_enemy_id, boss_attempts_left, boss_alert_expires_at, updated_at)
                VALUES (?, ?, 0, ?, ?, ?, ?)
                ON CONFLICT(user_id, area_key) DO UPDATE SET
                    active_boss_enemy_id = excluded.active_boss_enemy_id,
                    boss_attempts_left = excluded.boss_attempts_left,
                    boss_alert_expires_at = excluded.boss_alert_expires_at,
                    updated_at = excluded.updated_at
                """,
                (self.user_id, area_key, int(enemy_id), int(attempts), now + 3600, now),
            )
            db.commit()

    def _unlock_evolution_feature(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute("UPDATE users SET max_unlocked_layer = 3 WHERE id = ?", (self.user_id,))
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    now,
                    game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                    json.dumps({"area_key": "layer_2", "boss_kind": "fixed", "unlocked_layer": 3}, ensure_ascii=False),
                    self.user_id,
                ),
            )
            db.commit()

    def test_home_next_action_boss_alert_has_highest_priority(self):
        self._create_active_robot()
        self._set_boss_alert(area_key="layer_2", attempts=2)
        client = self._new_client(new_layer_badge=3)
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertEqual(html.count("next-action-card"), 1)
        self.assertIn("ボスに挑戦（残り●●）", html)
        self.assertNotIn("NEW 第3層へ行く", html)

    def test_home_next_action_new_layer_routes_to_map(self):
        self._create_active_robot()
        client = self._new_client(new_layer_badge=2)
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertEqual(html.count("next-action-card"), 1)
        self.assertIn("NEW 第2層へ行く", html)
        self.assertIn('href="/map"', html)

    def test_home_next_action_targets_current_layer_boss_when_not_max(self):
        self._create_active_robot()
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET max_unlocked_layer = 2 WHERE id = ?", (self.user_id,))
            db.commit()
        client = self._new_client()
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertEqual(html.count("next-action-card"), 1)
        self.assertIn("第2層ボスを狙う", html)
        self.assertIn('name="area_key" value="layer_2"', html)

    def test_home_next_action_falls_back_to_explore_at_layer3(self):
        self._create_active_robot()
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET max_unlocked_layer = 3 WHERE id = ?", (self.user_id,))
            db.commit()
        client = self._new_client()
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertEqual(html.count("next-action-card"), 1)
        self.assertIn(">出撃<", html)
        self.assertIn('name="area_key" value="layer_3"', html)

    def test_home_next_action_never_shows_showcase_or_ranking_links(self):
        self._create_active_robot()
        client = self._new_client()
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        m = re.search(r'<div class="card next-action-card">(.*?)</div>\s*</div>', html, re.DOTALL)
        self.assertIsNotNone(m)
        card_html = m.group(1)
        self.assertNotIn("/showcase", card_html)
        self.assertNotIn("/ranking", card_html)
        self.assertNotIn("ショーケース", card_html)
        self.assertNotIn("ランキング", card_html)

    def test_home_next_action_focuses_core_loop_even_when_faction_unmet(self):
        self._create_active_robot()
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET faction = NULL WHERE id = ?", (self.user_id,))
            now = int(time.time())
            for _ in range(20):
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                    VALUES (?, 'audit.explore.end', ?, ?)
                    """,
                    (now, '{"result":{"win":true}}', self.user_id),
                )
            for _ in range(5):
                db.execute(
                    "INSERT INTO world_events_log (created_at, event_type, payload_json, user_id) VALUES (?, 'audit.build.confirm', '{}', ?)",
                    (now, self.user_id),
                )
            db.commit()
        client = self._new_client()
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("出撃してパーツを集めよう", html)
        self.assertIn('name="area_key" value="layer_1"', html)

    def test_home_chat_dedupes_and_hides_build_system_log(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            db.execute(
                "INSERT INTO chat_messages (user_id, username, message, created_at) VALUES (?, ?, ?, ?)",
                (self.user_id, "alice", "同一ログ", now_text),
            )
            db.execute(
                "INSERT INTO chat_messages (user_id, username, message, created_at) VALUES (?, ?, ?, ?)",
                (self.user_id, "alice", "同一ログ", now_text),
            )
            db.execute(
                "INSERT INTO chat_messages (user_id, username, message, created_at) VALUES (?, ?, ?, ?)",
                (self.user_id, "alice", "同一ログ", now_text),
            )
            db.execute(
                "INSERT INTO chat_messages (user_id, username, message, created_at) VALUES (?, ?, ?, ?)",
                (self.user_id, "SYSTEM", "home_next_tester が新ロボ『GuideBot』を完成！", now_text),
            )
            db.commit()
        client = self._new_client()
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertEqual(html.count("同一ログ"), 1)
        self.assertNotIn("が新ロボ『GuideBot』を完成！", html)

    def test_home_shows_weekly_explore_ranking_below_social_log(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 1, 0, 1)
                """,
                ("ranking_rival", "x", now),
            )
            rival_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("ranking_rival",),
            ).fetchone()["id"]
            current_week = game_app._world_week_key()
            week_start, _ = game_app._world_week_bounds(current_week)
            ts = int(week_start.timestamp()) + 3600
            for _ in range(2):
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                    VALUES (?, ?, '{}', ?)
                    """,
                    (ts, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], self.user_id),
                )
            for _ in range(4):
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                    VALUES (?, ?, '{}', ?)
                    """,
                    (ts + 1, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], rival_id),
                )
            db.commit()
        client = self._new_client()
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("通信", html)
        self.assertIn("世界ログ", html)
        self.assertIn("会議室", html)
        self.assertIn("今週のランキング", html)
        self.assertIn("表示調整", html)
        self.assertIn("1位 ranking_rival", html)
        self.assertIn("4回", html)
        self.assertIn("2位 home_next_tester", html)
        self.assertIn('/ranking?metric=weekly_explores', html)
        self.assertNotIn("?comm_tab=", html)
        self.assertIn('id="home-comms-panel"', html)
        self.assertNotIn('class="home-lower-grid home-secondary-grid"', html)
        self.assertNotIn("home-invite-panel", html)
        self.assertLess(html.index("通信"), html.index("今週のランキング"))
        self.assertLess(html.index("今週のMVP"), html.index('id="home-comms-panel"'))
        m = re.search(r'<section class="panel home-ranking-panel">(.*?)</section>', html, re.DOTALL)
        self.assertIsNotNone(m)
        panel_html = m.group(1)
        self.assertIn('class="user-chip mini"', panel_html)
        self.assertIn("1位 ranking_rival", panel_html)
        self.assertIn("robot-badge-32", panel_html)
        nav = re.search(r'<section class="panel home-nav-panel">(.*?)</section>', html, re.DOTALL)
        self.assertIsNotNone(nav)
        nav_html = nav.group(1)
        self.assertIn("ロボ展示", nav_html)
        self.assertIn("記録庫", nav_html)
        self.assertNotIn("ランキング", nav_html)
        self.assertNotIn("世界戦況", nav_html)
        self.assertNotIn("通信", nav_html)

    def test_home_weekly_explore_ranking_handles_empty_state(self):
        client = self._new_client()
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("今週のランキング", html)
        self.assertIn("まだランキングデータがありません。", html)

    def test_home_defaults_explore_select_to_first_unlocked_area_when_unset(self):
        self._create_active_robot()
        client = self._new_client()
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertRegex(html, r'<option value="layer_1" selected>')
        self.assertNotIn("前回の出撃先で出撃", html)

    def test_home_uses_last_selected_explore_area_when_unlocked(self):
        self._create_active_robot()
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                "UPDATE users SET max_unlocked_layer = 2, last_explore_area_key = 'layer_2_rush' WHERE id = ?",
                (self.user_id,),
            )
            db.commit()
        client = self._new_client()
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertRegex(html, r'<option value="layer_2_rush" selected>')
        self.assertIn('class="panel home-return-explore-panel"', html)
        self.assertIn("前回の出撃先で出撃", html)
        self.assertIn('name="area_key" value="layer_2_rush"', html)
        self.assertLess(html.index("前回の出撃先"), html.index("最初のミッション"))

    def test_home_falls_back_when_saved_explore_area_is_locked(self):
        self._create_active_robot()
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET last_explore_area_key = 'layer_3' WHERE id = ?", (self.user_id,))
            db.commit()
        client = self._new_client()
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertRegex(html, r'<option value="layer_1" selected>')
        self.assertNotIn('value="layer_3"', html)
        self.assertNotIn("前回の出撃先で出撃", html)

    def test_home_beginner_focus_keeps_social_log_and_weekly_ranking(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET is_admin = 0, faction = NULL WHERE id = ?", (self.user_id,))
            db.commit()
        client = self._new_client()
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("最初のミッション", html)
        self.assertIn("通信", html)
        self.assertIn("今週のランキング", html)
        self.assertIn("表示調整", html)
        self.assertIn("今週の戦況", html)
        self.assertIn("まだランキングデータがありません。", html)
        self.assertNotIn("home-invite-panel", html)
        self.assertNotIn("最初は「ロボ編成」か「出撃」だけ見ればOKです。", html)
        self.assertLess(html.index("通信"), html.index("今週のランキング"))

    def test_home_comms_tabs_switch_room_and_personal_views(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO chat_messages (user_id, username, room_key, message, created_at, deleted_at)
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (
                    self.user_id,
                    "home_next_tester",
                    "beginner_room",
                    "初心者相談室のメッセージ",
                    game_app.now_str(),
                ),
            )
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    now,
                    game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"],
                    json.dumps({"part_type": "HEAD", "target_part_name": "試作ヘッド"}, ensure_ascii=False),
                    self.user_id,
                ),
            )
            db.commit()

        client = self._new_client()
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('data-home-comms-tab-button="world"', html)
        self.assertIn('data-home-comms-tab-button="rooms"', html)
        self.assertIn('data-home-comms-tab-button="faction"', html)
        self.assertIn('data-home-comms-tab-button="personal"', html)
        self.assertIn('data-home-comms-room-button="beginner_room"', html)
        self.assertIn('data-home-comms-scroll-list="1"', html)
        self.assertIn('data-home-comms-max-visible="5"', html)
        self.assertIn("世界の動きや、他のロボ使いの声がここに流れます。", html)
        self.assertIn("あなたのロボの成長や出来事がここに残ります。", html)
        self.assertIn("初心者相談室のメッセージ", html)
        self.assertIn("進化成功", html)
        self.assertNotIn("?comm_tab=", html)

    def test_home_shows_area_feature_cards_for_unlocked_areas(self):
        self._create_active_robot()
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET is_admin = 0, max_unlocked_layer = 2 WHERE id = ?", (self.user_id,))
            db.commit()
        client = self._new_client()
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("探索先メモ", html)
        self.assertIn("旧整備通路。最も安定した探索ルート。", html)
        self.assertIn("放電ノイズ帯。tier1/2が混在する中間層。", html)
        self.assertIn("推奨: 基本ステ確認と初期ドロップ回収。", html)

    def test_home_hides_evolution_actions_until_layer2_boss_defeat(self):
        self._create_active_robot()
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (self.user_id,))
            db.execute("UPDATE users SET evolution_core_progress = 72 WHERE id = ?", (self.user_id,))
            game_app._grant_player_core(db, self.user_id, game_app.EVOLUTION_CORE_KEY, qty=1)
            db.commit()
        client = self._new_client()
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertNotIn("次の目標", html)
        self.assertNotIn("進化合成", html)
        self.assertNotIn("あと28勝で進化コア", html)

    def test_home_shows_evolve_action_after_layer2_boss_defeat(self):
        self._create_active_robot()
        self._unlock_evolution_feature()
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (self.user_id,))
            game_app._grant_player_core(db, self.user_id, game_app.EVOLUTION_CORE_KEY, qty=1)
            db.commit()
        client = self._new_client()
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("進化合成", html)
        self.assertIn("進化コア 1個 / 次 0/100", html)

    def test_home_can_hide_and_restore_beginner_mission(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (self.user_id,))
            db.commit()
        client = self._new_client()
        hide_resp = client.post("/home/beginner-mission/hide", data={"next": "/home"})
        self.assertEqual(hide_resp.status_code, 302)
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertNotIn("🚀 最初のミッション", html)
        self.assertIn("最初のミッションを再表示", html)

        show_resp = client.post("/home/beginner-mission/show", data={"next": "/home"})
        self.assertEqual(show_resp.status_code, 302)
        resp = client.get("/home")
        html = resp.get_data(as_text=True)
        self.assertIn("🚀 最初のミッション", html)

    def test_home_can_collapse_and_expand_next_action(self):
        self._create_active_robot()
        client = self._new_client()
        collapse_resp = client.post("/home/next-action/collapse", data={"next": "/home"})
        self.assertEqual(collapse_resp.status_code, 302)
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Next Action を開く", html)
        self.assertNotIn("たたまれています。", html)
        self.assertEqual(html.count("next-action-card"), 0)

