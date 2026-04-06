import json
import os
import tempfile
import time
import unittest
from unittest import mock

import app as game_app
import init_db
from services.weekly_champion import (
    get_current_week_key,
    get_or_create_weekly_champion,
    select_weekly_champion_candidate,
)


class WeeklyChampionTests(unittest.TestCase):
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

    def _create_user(self, username, *, is_admin=0, initialize=True):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            cur = db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins) VALUES (?, ?, ?, ?, 0)",
                (username, "x", now, int(is_admin)),
            )
            user_id = int(cur.lastrowid)
            if initialize:
                game_app.initialize_new_user(db, user_id)
            db.commit()
            return user_id

    def _active_robot_id(self, user_id):
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT active_robot_id FROM users WHERE id = ?", (int(user_id),)).fetchone()
            return int(row["active_robot_id"]) if row and row["active_robot_id"] else None

    def _rename_active_robot(self, user_id, robot_name):
        robot_id = self._active_robot_id(user_id)
        self.assertIsNotNone(robot_id)
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                "UPDATE robot_instances SET name = ?, updated_at = ? WHERE id = ?",
                (str(robot_name), int(time.time()), int(robot_id)),
            )
            db.commit()
        return int(robot_id)

    def _log_week_event(self, user_id, event_type, *, count=1, payload=None):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            body = json.dumps(payload or {}, ensure_ascii=False)
            for offset in range(int(count)):
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                    VALUES (?, ?, ?, ?)
                    """,
                    (now + offset, str(event_type), body, int(user_id)),
                )
            db.commit()

    def _login(self, client, user_id, username):
        with client.session_transaction() as sess:
            sess["user_id"] = int(user_id)
            sess["username"] = str(username)

    def test_select_weekly_champion_prefers_boss_and_excludes_admin_or_missing_active_robot(self):
        admin_id = self._create_user("champ_admin", is_admin=1)
        missing_active_id = self._create_user("inactive_candidate")
        boss_id = self._create_user("boss_owner")
        explore_id = self._create_user("explore_owner")

        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET active_robot_id = NULL WHERE id = ?", (int(missing_active_id),))
            db.commit()

        self._log_week_event(admin_id, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], count=6)
        self._log_week_event(missing_active_id, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], count=5)
        self._log_week_event(explore_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], count=7)
        self._log_week_event(boss_id, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], count=1)

        with game_app.app.app_context():
            db = game_app.get_db()
            candidate = select_weekly_champion_candidate(db, get_current_week_key())

        self.assertIsNotNone(candidate)
        self.assertEqual(int(candidate["user_id"]), int(boss_id))
        self.assertEqual(int(candidate["boss_count"]), 1)
        self.assertEqual(int(candidate["explore_count"]), 0)

    def test_get_or_create_weekly_champion_uses_previous_snapshot_as_fallback(self):
        owner_id = self._create_user("carry_owner")
        robot_id = self._rename_active_robot(owner_id, "前週王者")
        previous_week = get_current_week_key(int(time.time()) - 7 * 24 * 60 * 60)
        current_week = get_current_week_key()
        payload_json = json.dumps(
            {
                "user_id": int(owner_id),
                "robot_instance_id": int(robot_id),
                "owner_name": "carry_owner",
                "robot_name": "前週王者",
                "robot_image_url": "/static/robot_composed/example.png",
                "signature_label": "安定",
                "focus_line": "装甲差で受け切る",
                "stats": {"hp": 20, "atk": 10, "def": 11, "spd": 8, "acc": 9, "cri": 6},
            },
            ensure_ascii=False,
        )
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                INSERT INTO weekly_champion_snapshots (
                    week_key, robot_instance_id, user_id, robot_name, owner_name,
                    reason_key, score_value, payload_json, source_week_key, created_at,
                    challenge_count, win_count, loss_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0)
                """,
                (
                    previous_week,
                    int(robot_id),
                    int(owner_id),
                    "前週王者",
                    "carry_owner",
                    "weekly_boss",
                    1001,
                    payload_json,
                    previous_week,
                    int(time.time()) - 7 * 24 * 60 * 60,
                ),
            )
            db.commit()

            result = get_or_create_weekly_champion(
                db,
                week_key=current_week,
                payload_builder=lambda candidate: None,
                now_ts=int(time.time()),
            )

        self.assertTrue(result["created"])
        self.assertTrue(result["fallback"])
        self.assertEqual(result["snapshot"]["reason_key"], "carry_over")
        self.assertEqual(result["snapshot"]["source_week_key"], previous_week)
        self.assertEqual(int(result["snapshot"]["robot_instance_id"]), int(robot_id))

    def test_home_shows_weekly_champion_card(self):
        owner_id = self._create_user("champ_owner")
        challenger_id = self._create_user("challenger")
        self._rename_active_robot(owner_id, "王者零式")
        self._log_week_event(owner_id, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], count=2)

        client = game_app.app.test_client()
        self._login(client, challenger_id, "challenger")
        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("今週のチャンプ機体", html)
        self.assertIn("王者零式", html)
        self.assertIn("champ_owner", html)
        self.assertIn('action="/champion/challenge"', html)
        self.assertIn('href="/champion"', html)

    def test_champion_view_prompts_for_active_robot_when_missing(self):
        owner_id = self._create_user("view_owner")
        viewer_id = self._create_user("viewer_no_robot", initialize=False)
        self._rename_active_robot(owner_id, "看板機")
        self._log_week_event(owner_id, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], count=1)

        client = game_app.app.test_client()
        self._login(client, viewer_id, "viewer_no_robot")
        resp = client.get("/champion")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("出撃機体がないため挑戦できません。", html)
        self.assertIn("ロボを編成する", html)

    def test_champion_owner_cannot_challenge_self(self):
        owner_id = self._create_user("self_owner")
        self._log_week_event(owner_id, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], count=1)

        client = game_app.app.test_client()
        self._login(client, owner_id, "self_owner")
        resp = client.post("/champion/challenge", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("あなたの機体が今週のチャンプです。挑戦は受ける側になります。", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT COUNT(*) AS c FROM weekly_champion_battles").fetchone()
        self.assertEqual(int(row["c"]), 0)

    def test_champion_challenge_records_battle_and_world_log_on_win(self):
        owner_id = self._create_user("champion_owner")
        challenger_id = self._create_user("champion_challenger")
        owner_robot_id = self._rename_active_robot(owner_id, "王者機")
        challenger_robot_id = self._rename_active_robot(challenger_id, "挑戦機")
        self._log_week_event(owner_id, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], count=2)

        mocked_battle = {
            "win": True,
            "outcome": "勝利",
            "timeout": False,
            "timeout_decision": None,
            "turn_count": 1,
            "turn_logs": [
                {
                    "turn": 1,
                    "player_action": "挑戦機の決着打",
                    "enemy_action": "追撃不要",
                    "player_damage": 6,
                    "enemy_damage": 0,
                    "player_before": 18,
                    "enemy_before": 6,
                    "player_after": 18,
                    "enemy_after": 0,
                    "player_max": 18,
                    "enemy_max": 6,
                    "critical": False,
                    "result_line": "王者機を撃破！",
                }
            ],
            "player_final_hp": 18,
            "player_max_hp": 18,
            "enemy_final_hp": 0,
            "enemy_max_hp": 6,
            "summary_heading": "今回の勝ち筋",
            "summary_label": "命中安定で崩した",
            "result_label": "WIN",
            "critical_hits": 0,
        }

        client = game_app.app.test_client()
        self._login(client, challenger_id, "champion_challenger")
        with mock.patch.object(game_app, "run_champion_battle", return_value=mocked_battle):
            with mock.patch.object(game_app, "_battle_short_replay_open_for_viewer", return_value=False):
                resp = client.post("/champion/challenge")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("今週のチャンプを撃破！", html)
        self.assertIn("今週1人目の撃破者です。", html)
        self.assertIn("命中安定で崩した", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            battle_row = db.execute(
                """
                SELECT *
                FROM weekly_champion_battles
                WHERE challenger_user_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (int(challenger_id),),
            ).fetchone()
            self.assertIsNotNone(battle_row)
            self.assertEqual(battle_row["result"], "win")
            self.assertEqual(int(battle_row["challenger_robot_instance_id"]), int(challenger_robot_id))

            snapshot_row = db.execute(
                """
                SELECT *
                FROM weekly_champion_snapshots
                WHERE user_id = ? AND robot_instance_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (int(owner_id), int(owner_robot_id)),
            ).fetchone()
            self.assertIsNotNone(snapshot_row)
            self.assertEqual(int(snapshot_row["challenge_count"]), 1)
            self.assertEqual(int(snapshot_row["loss_count"]), 1)

            event_types = {
                row["event_type"]
                for row in db.execute(
                    "SELECT event_type FROM world_events_log WHERE request_id IS NOT NULL"
                ).fetchall()
            }
        self.assertIn(game_app.AUDIT_EVENT_TYPES["CHAMPION_CHALLENGE"], event_types)
        self.assertIn(game_app.AUDIT_EVENT_TYPES["CHAMPION_DEFEAT"], event_types)
        self.assertIn("CHAMPION_DEFEATED", event_types)


if __name__ == "__main__":
    unittest.main()
