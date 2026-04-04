import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class BattleShortReplayHelperTests(unittest.TestCase):
    def test_timeout_judgement_prefers_higher_hp_ratio(self):
        decision = game_app._battle_timeout_judgement(
            player_hp=15,
            player_hp_max=21,
            enemy_hp=1,
            enemy_hp_max=34,
        )
        self.assertTrue(decision["player_wins"])
        self.assertEqual(decision["outcome"], "win")
        self.assertEqual(decision["display_outcome"], "判定勝ち")

    def test_timeout_judgement_tie_stays_loss(self):
        decision = game_app._battle_timeout_judgement(
            player_hp=10,
            player_hp_max=20,
            enemy_hp=5,
            enemy_hp_max=10,
        )
        self.assertFalse(decision["player_wins"])
        self.assertEqual(decision["outcome"], "lose")
        self.assertEqual(decision["display_outcome"], "判定負け")

    def test_replay_summary_treats_timeout_win_as_player_victory(self):
        replay = game_app._build_battle_replay_summary(
            area_key="layer_2_mist",
            area_label="第二層",
            enemy_name="エンバーレンチ",
            enemy_image_url="/static/assets/placeholder_enemy.png",
            player_name="Starter Unit",
            player_image_url="/static/assets/placeholder_player.png",
            player_stats={"hp": 21, "atk": 9, "def": 10, "spd": 10, "acc": 9, "cri": 6},
            enemy_stats={"hp": 34, "atk": 7, "def": 9, "spd": 9, "acc": 8, "cri": 5, "trait": "heavy"},
            robot_style={"style_key": "stable"},
            turn_logs=[
                {
                    "turn": 8,
                    "player_action": "ドライブ",
                    "enemy_action": "攻撃",
                    "player_damage": 0,
                    "enemy_damage": 1,
                    "player_before": 16,
                    "enemy_before": 1,
                    "player_after": 15,
                    "enemy_after": 1,
                    "player_max": 21,
                    "enemy_max": 34,
                    "critical": False,
                }
            ],
            outcome="判定勝ち",
            is_boss=False,
        )
        self.assertEqual(replay["winner"], "player")
        self.assertEqual(replay["result_sub_label"], "判定勝ち")
        self.assertEqual(replay["summary_heading"], "今回の勝ち筋")

    def test_normal_replay_builds_turn_cards_until_finisher(self):
        replay = game_app._build_battle_replay_summary(
            area_key="layer_1",
            area_label="第一層",
            enemy_name="テスト敵",
            enemy_image_url="/static/assets/placeholder_enemy.png",
            player_name="テスト機",
            player_image_url="/static/assets/placeholder_player.png",
            player_stats={"hp": 15, "atk": 14, "def": 11, "spd": 14, "acc": 13, "cri": 9},
            enemy_stats={"hp": 12, "atk": 8, "def": 7, "spd": 9, "acc": 8, "cri": 5, "trait": "fast"},
            robot_style={"style_key": "burst"},
            turn_logs=[
                {
                    "turn": 1,
                    "player_action": "射撃",
                    "enemy_action": "攻撃",
                    "player_damage": 4,
                    "enemy_damage": 0,
                    "player_before": 15,
                    "enemy_before": 12,
                    "player_after": 15,
                    "enemy_after": 8,
                    "player_max": 15,
                    "enemy_max": 12,
                    "critical": False,
                },
                {
                    "turn": 2,
                    "player_action": "射撃",
                    "enemy_action": "攻撃",
                    "player_damage": 8,
                    "enemy_damage": 2,
                    "player_before": 15,
                    "enemy_before": 8,
                    "player_after": 13,
                    "enemy_after": 0,
                    "player_max": 15,
                    "enemy_max": 12,
                    "critical": True,
                },
            ],
            outcome="勝利",
            is_boss=False,
        )
        self.assertIsNotNone(replay)
        self.assertEqual(replay["version"], "v1")
        self.assertEqual(replay["battle_type"], "normal")
        self.assertEqual(replay["winner"], "player")
        self.assertEqual(len(replay["turns"]), 2)
        self.assertEqual(replay["turns"][0]["turn"], 1)
        self.assertEqual(replay["turns"][0]["opening_actor"], "player")
        self.assertTrue(any(step.get("critical") for step in replay["turns"][-1]["steps"]))
        self.assertEqual(replay["turns"][-1]["steps"][0]["target"], "enemy")
        self.assertEqual(replay["turns"][-1]["steps"][0]["enemy_hp_after"], 0)
        self.assertTrue(replay["turns"][-1]["steps"][0]["is_finisher"])
        self.assertEqual(replay["turns"][-1]["enemy_hp_after"], 0)
        self.assertEqual(replay["player_hp_start"], 15)
        self.assertEqual(replay["enemy_hp_start"], 12)
        self.assertGreaterEqual(replay["turns"][0]["standard_duration_ms"], 1550)
        self.assertGreaterEqual(replay["turns"][0]["fast_duration_ms"], 760)
        self.assertTrue(all(turn.get("steps") for turn in replay["turns"]))
        self.assertIn(replay["summary_label"], {"爆発力で押し切った", "命中安定で崩した", "先手制圧で押し切った", "装甲差で競り勝った"})

    def test_boss_replay_includes_turn_status_and_defeat_summary(self):
        replay = game_app._build_battle_replay_summary(
            area_key="layer_4_forge",
            area_label="第四層",
            enemy_name="試験場ボス",
            enemy_image_url="/static/assets/placeholder_enemy.png",
            player_name="テスト機",
            player_image_url="/static/assets/placeholder_player.png",
            player_stats={"hp": 17, "atk": 12, "def": 13, "spd": 10, "acc": 11, "cri": 8},
            enemy_stats={"hp": 20, "atk": 13, "def": 10, "spd": 12, "acc": 12, "cri": 7, "trait": "heavy"},
            robot_style={"style_key": "stable"},
            turn_logs=[
                {
                    "turn": 1,
                    "player_action": "射撃",
                    "enemy_action": "斬撃",
                    "player_damage": 0,
                    "enemy_damage": 4,
                    "player_before": 17,
                    "enemy_before": 20,
                    "player_after": 13,
                    "enemy_after": 20,
                    "player_max": 17,
                    "enemy_max": 20,
                    "critical": False,
                },
                {
                    "turn": 2,
                    "player_action": "反撃",
                    "enemy_action": "追撃",
                    "player_damage": 11,
                    "enemy_damage": 0,
                    "player_before": 13,
                    "enemy_before": 20,
                    "player_after": 13,
                    "enemy_after": 9,
                    "player_max": 17,
                    "enemy_max": 20,
                    "critical": False,
                },
                {
                    "turn": 3,
                    "player_action": "反撃",
                    "enemy_action": "追撃",
                    "player_damage": 9,
                    "enemy_damage": 0,
                    "player_before": 13,
                    "enemy_before": 9,
                    "player_after": 13,
                    "enemy_after": 0,
                    "player_max": 17,
                    "enemy_max": 20,
                    "critical": True,
                },
            ],
            outcome="勝利",
            is_boss=True,
        )
        self.assertIsNotNone(replay)
        self.assertEqual(replay["version"], "v1")
        self.assertTrue(replay["is_boss"])
        self.assertEqual(replay["result_label"], "BOSS DEFEATED")
        self.assertEqual(replay["summary_heading"], "今回の勝ち筋")
        self.assertGreaterEqual(replay["intro_delay_ms"], 760)
        self.assertGreaterEqual(replay["outro_hold_ms"], 1320)
        self.assertEqual(len(replay["turns"]), 3)
        self.assertEqual(replay["turns"][-1]["enemy_hp_after"], 0)
        self.assertTrue(replay["turns"][-1]["steps"][-1]["is_finisher"])
        self.assertTrue(any(turn.get("status_label") for turn in replay["turns"]))
        self.assertTrue(all(int(turn.get("standard_duration_ms") or 0) >= 2100 for turn in replay["turns"]))
        self.assertTrue(any(step.get("hit_type") == "crit" for turn in replay["turns"] for step in turn.get("steps") or []))


class BattleShortReplayRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        init_db.main()
        game_app.app.config["TESTING"] = True

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _create_user(self, username, is_admin=0):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            cur = db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins) VALUES (?, ?, ?, ?, 0)",
                (username, "x", now, int(is_admin)),
            )
            user_id = int(cur.lastrowid)
            game_app.initialize_new_user(db, user_id)
            db.commit()
            return user_id

    def _login(self, client, user_id, username, *, ui_effects_enabled=True):
        with client.session_transaction() as sess:
            sess["user_id"] = int(user_id)
            sess["username"] = username
            sess["ui_effects_enabled"] = bool(ui_effects_enabled)

    def test_explore_result_renders_short_replay_overlay(self):
        user_id = self._create_user("replay_user", is_admin=0)
        with game_app.app.test_client() as client:
            self._login(client, user_id, "replay_user", ui_effects_enabled=True)
            resp = client.post("/explore", data={"area_key": "layer_1"})
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn('id="battle-short-replay"', html)
            self.assertIn('data-cinematic-version="v1"', html)
            self.assertIn('id="battle-cinematic-v1-data"', html)
            self.assertIn('class="battle-cinematic-v1-title"', html)
            self.assertIn('class="battle-cinematic-v1-controls battle-mode-tabs"', html)
            self.assertIn('data-cinematic-mode="standard"', html)
            self.assertIn('data-cinematic-mode="fast"', html)
            self.assertIn('data-cinematic-mode="instant"', html)
            self.assertIn('data-cinematic-skip="1"', html)
            self.assertIn('data-cinematic-turn-indicator', html)
            self.assertIn('data-cinematic-projectile="1"', html)
            self.assertIn('data-cinematic-finish-call="1"', html)
            self.assertIn('data-cinematic-damage="player"', html)
            self.assertIn('data-cinematic-damage="enemy"', html)
            self.assertNotRegex(html, r'id="battle-short-replay"[^>]*\shidden')
            self.assertIn('data-cinematic-hp="player"', html)
            self.assertIn('data-cinematic-hp="enemy"', html)
            self.assertIn('id="battle-replay-followup"', html)
            self.assertNotIn('class="battle-title"', html)

    def test_ui_effects_off_skips_short_replay_markup(self):
        user_id = self._create_user("replay_no_fx", is_admin=0)
        with game_app.app.test_client() as client:
            self._login(client, user_id, "replay_no_fx", ui_effects_enabled=False)
            resp = client.post("/explore", data={"area_key": "layer_1"})
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertNotIn('id="battle-short-replay"', html)
            self.assertIn("戦利品", html)


if __name__ == "__main__":
    unittest.main()
