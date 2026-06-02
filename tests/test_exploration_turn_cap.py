import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class ExplorationTurnCapTests(unittest.TestCase):
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
                "INSERT INTO users (username, password_hash, created_at, is_admin, max_unlocked_layer) VALUES (?, ?, ?, 1, 5)",
                ("turn_cap_tester", "x", now),
            )
            user_id = db.execute("SELECT id FROM users WHERE username = ?", ("turn_cap_tester",)).fetchone()["id"]
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (user_id, "TestBot", now, now),
            )
            robot_id = db.execute("SELECT id FROM robot_instances WHERE user_id = ?", (user_id,)).fetchone()["id"]

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
            db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (robot_id, user_id))
            db.commit()
            self.user_id = user_id

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _mock_battle_render(self, template_name, **context):
        if template_name != "battle.html" or not context.get("explore_mode"):
            return ""
        turn_logs = context.get("turn_logs") or []
        summary = context.get("summary") or {}
        turns = [int(log["turn"]) for log in turn_logs]
        return json.dumps(
            {
                "max_turn": max(turns) if turns else 0,
                "keys": sorted(list(turn_logs[0].keys())) if turn_logs else [],
                "outcome": summary.get("outcome"),
                "is_area_boss": bool(summary.get("is_area_boss")),
                "turn_limit_label": summary.get("turn_limit_label"),
                "timeout_decision_line": summary.get("timeout_decision_line"),
            },
            ensure_ascii=False,
        )

    def _install_layer2_test_boss(self, *, hp):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                INSERT INTO enemies
                (key, name_ja, image_path, tier, element, hp, atk, def, spd, acc, cri, faction, is_boss, boss_area_key, is_active)
                VALUES (?, ?, ?, 2, 'NORMAL', ?, 1, 1, 1, 1, 1, 'neutral', 1, 'layer_2', 1)
                ON CONFLICT(key) DO UPDATE SET
                    name_ja = excluded.name_ja,
                    image_path = excluded.image_path,
                    hp = excluded.hp,
                    atk = excluded.atk,
                    def = excluded.def,
                    spd = excluded.spd,
                    acc = excluded.acc,
                    cri = excluded.cri,
                    is_boss = 1,
                    boss_area_key = 'layer_2',
                    is_active = 1
                """,
                ("turn_cap_layer2_boss", "ターン検証ボス", "assets/placeholder_enemy.png", int(hp)),
            )
            db.execute(
                """
                UPDATE enemies
                SET is_active = 0
                WHERE COALESCE(is_boss, 0) = 1
                  AND boss_area_key = 'layer_2'
                  AND key <> 'turn_cap_layer2_boss'
                """
            )
            enemy_id = db.execute(
                "SELECT id FROM enemies WHERE key = ?",
                ("turn_cap_layer2_boss",),
            ).fetchone()["id"]
            game_app._activate_boss_alert(
                db,
                user_id=self.user_id,
                area_key="layer_2",
                enemy_id=int(enemy_id),
                now_ts=int(time.time()),
            )
            db.commit()

    @staticmethod
    def _stable_weekly_env():
        return {
            "element": "NORMAL",
            "mode": "安定",
            "enemy_spawn_bonus": 0.0,
            "drop_bonus": 0.0,
            "reason": "test",
        }

    def test_explore_turns_never_exceed_cap_across_multiple_runs(self):
        required_turn_log_keys = {
            "turn",
            "player_action",
            "enemy_action",
            "enemy_before",
            "enemy_after",
            "player_before",
            "player_after",
            "player_damage",
            "enemy_damage",
            "critical",
            "player_skill",
            "player_max",
            "enemy_max",
        }
        with patch.object(game_app, "render_template", side_effect=self._mock_battle_render):
            with game_app.app.test_client() as client:
                with client.session_transaction() as session:
                    session["user_id"] = self.user_id
                    session["username"] = "turn_cap_tester"

                for _ in range(20):
                    resp = client.post("/explore", data={"area_key": "layer_1"}, follow_redirects=True)
                    self.assertEqual(resp.status_code, 200)
                    body = resp.get_data(as_text=True)
                    if "<!doctype html>" in body.lower() or not body.strip():
                        # 0.5%ボス警報時はhomeへ戻るため、次ループで継続確認する。
                        continue
                    payload = json.loads(body)
                    self.assertLessEqual(payload["max_turn"], game_app.EXPLORE_MAX_TURNS)
                    if payload["keys"]:
                        self.assertTrue(required_turn_log_keys.issubset(set(payload["keys"])))

    def test_layer4_normal_enemy_keeps_eight_turn_cap(self):
        def no_damage(*args, **kwargs):
            return 0, False

        with patch.object(game_app, "render_template", side_effect=self._mock_battle_render), patch.object(
            game_app, "_world_current_environment", return_value=self._stable_weekly_env()
        ), patch.object(
            game_app, "_area_boss_spawn_check", return_value={"spawn": False, "probability": 0.0, "pity_forced": False, "streak_before": 0}
        ), patch.object(game_app, "resolve_attack", side_effect=no_damage):
            with game_app.app.test_client() as client:
                with client.session_transaction() as session:
                    session["user_id"] = self.user_id
                    session["username"] = "turn_cap_tester"

                resp = client.post("/explore", data={"area_key": "layer_4_forge"}, follow_redirects=True)
                self.assertEqual(resp.status_code, 200)
                payload = json.loads(resp.get_data(as_text=True))
                self.assertFalse(payload["is_area_boss"])
                self.assertEqual(payload["max_turn"], game_app.EXPLORE_MAX_TURNS)
                self.assertIn("8ターン", payload["turn_limit_label"])

    def test_boss_battle_continues_past_eight_turns(self):
        self._install_layer2_test_boss(hp=10)

        def player_chip_damage(att_atk, *_args, **_kwargs):
            return (1, False) if int(att_atk) >= 5 else (0, False)

        with patch.object(game_app, "render_template", side_effect=self._mock_battle_render), patch.object(
            game_app, "_world_current_environment", return_value=self._stable_weekly_env()
        ), patch.object(game_app, "resolve_attack", side_effect=player_chip_damage):
            with game_app.app.test_client() as client:
                with client.session_transaction() as session:
                    session["user_id"] = self.user_id
                    session["username"] = "turn_cap_tester"

                resp = client.post("/explore", data={"area_key": "layer_2", "boss_enter": "1"}, follow_redirects=True)
                self.assertEqual(resp.status_code, 200)
                payload = json.loads(resp.get_data(as_text=True))
                self.assertTrue(payload["is_area_boss"])
                self.assertGreater(payload["max_turn"], game_app.EXPLORE_MAX_TURNS)
                self.assertIn("ターン上限: なし", payload["turn_limit_label"])

    def test_boss_battle_safety_cap_ends_without_500(self):
        self._install_layer2_test_boss(hp=9999)

        def no_damage(*args, **kwargs):
            return 0, False

        with patch.object(game_app, "render_template", side_effect=self._mock_battle_render), patch.object(
            game_app, "_world_current_environment", return_value=self._stable_weekly_env()
        ), patch.object(game_app, "resolve_attack", side_effect=no_damage):
            with game_app.app.test_client() as client:
                with client.session_transaction() as session:
                    session["user_id"] = self.user_id
                    session["username"] = "turn_cap_tester"

                resp = client.post("/explore", data={"area_key": "layer_2", "boss_enter": "1"}, follow_redirects=True)
                self.assertEqual(resp.status_code, 200)
                payload = json.loads(resp.get_data(as_text=True))
                self.assertTrue(payload["is_area_boss"])
                self.assertEqual(payload["max_turn"], game_app.BOSS_BATTLE_SAFETY_MAX_TURNS)
                self.assertIn("試験継続不能", payload["timeout_decision_line"])

                with game_app.app.app_context():
                    db = game_app.get_db()
                    event = db.execute(
                        """
                        SELECT payload_json
                        FROM world_events_log
                        WHERE event_type = 'audit.explore.end' AND user_id = ?
                        ORDER BY id DESC
                        LIMIT 1
                        """,
                        (self.user_id,),
                    ).fetchone()
                    self.assertIsNotNone(event)
                    event_payload = json.loads(event["payload_json"])
                    self.assertTrue(event_payload["result"]["turn_limit_removed"])
                    self.assertEqual(event_payload["result"]["safety_turn_cap"], game_app.BOSS_BATTLE_SAFETY_MAX_TURNS)


if __name__ == "__main__":
    unittest.main()
