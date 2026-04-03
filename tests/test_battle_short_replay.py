import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class BattleShortReplayHelperTests(unittest.TestCase):
    def test_normal_replay_caps_at_three_events(self):
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
        self.assertLessEqual(len(replay["events"]), 3)
        self.assertEqual(replay["events"][-1]["type"], "player_finisher")

    def test_boss_replay_includes_warning_and_defeat(self):
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
        event_types = [item["type"] for item in replay["events"]]
        self.assertEqual(event_types[0], "boss_warning")
        self.assertIn("boss_defeated", event_types)
        self.assertEqual(replay["result_label"], "BOSS DEFEATED")


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
            self.assertIn('id="battle-short-replay-data"', html)
            self.assertIn('data-replay-skip="1"', html)
            self.assertIn('id="battle-replay-followup"', html)

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
