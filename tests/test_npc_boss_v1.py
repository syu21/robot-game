import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class NpcBossV1Tests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, coins, max_unlocked_layer, faction)
                VALUES (?, ?, ?, 1, 40, 0, 3, 'ventra')
                """,
                ("npc_boss_tester", "x", now),
            )
            self.user_id = int(
                db.execute("SELECT id FROM users WHERE username = ?", ("npc_boss_tester",)).fetchone()["id"]
            )
            game_app.initialize_new_user(db, self.user_id)
            self.robot_id = int(
                db.execute("SELECT active_robot_id FROM users WHERE id = ?", (self.user_id,)).fetchone()["active_robot_id"]
            )
            db.execute(
                "UPDATE enemies SET hp=1, atk=1, def=1, spd=1, acc=1, cri=1 WHERE key IN ('boss_aurix_guardian','boss_ventra_sentinel','boss_ignis_reaver')"
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
        if kwargs.get("attacker_archetype") is not None:
            return 999, False
        return 0, False

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
            sess["username"] = "npc_boss_tester"
        return client

    def _activate_fixed_alert(self, area_key, boss_key):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            boss_id = int(db.execute("SELECT id FROM enemies WHERE key = ?", (boss_key,)).fetchone()["id"])
            db.execute(
                """
                INSERT INTO user_boss_progress
                (user_id, area_key, no_boss_streak, active_boss_enemy_id, boss_attempts_left, boss_alert_expires_at, updated_at)
                VALUES (?, ?, 0, ?, 3, ?, ?)
                ON CONFLICT(user_id, area_key) DO UPDATE SET
                    active_boss_enemy_id = excluded.active_boss_enemy_id,
                    boss_attempts_left = excluded.boss_attempts_left,
                    boss_alert_expires_at = excluded.boss_alert_expires_at,
                    updated_at = excluded.updated_at
                """,
                (self.user_id, area_key, boss_id, now + 3600, now),
            )
            db.commit()

    def test_layer2_fixed_boss_defeat_creates_npc_template(self):
        self._activate_fixed_alert("layer_2", "boss_ventra_sentinel")
        client = self._client()
        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "resolve_attack", side_effect=self._resolve_for_win
        ):
            resp = client.post("/explore", data={"area_key": "layer_2", "boss_enter": "1"})
        self.assertEqual(resp.status_code, 200)
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT COUNT(*) AS c FROM npc_boss_templates WHERE source_robot_instance_id = ? AND boss_area_key = 'layer_2'",
                (self.robot_id,),
            ).fetchone()
            self.assertEqual(int(row["c"] or 0), 1)

    def test_layer1_fixed_boss_defeat_does_not_create_npc_template(self):
        self._activate_fixed_alert("layer_1", "boss_aurix_guardian")
        client = self._client()
        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "resolve_attack", side_effect=self._resolve_for_win
        ):
            resp = client.post("/explore", data={"area_key": "layer_1", "boss_enter": "1"})
        self.assertEqual(resp.status_code, 200)
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT COUNT(*) AS c FROM npc_boss_templates").fetchone()
            self.assertEqual(int(row["c"] or 0), 0)

    def test_npc_boss_pick_only_layer2_layer3(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.create_npc_boss_from_active_robot(self.user_id, "layer_2")
            db.commit()
            self.assertIsNone(game_app.pick_npc_boss_for_area(db, "layer_1"))
            self.assertIsNotNone(game_app.pick_npc_boss_for_area(db, "layer_2"))
            self.assertIsNone(game_app.pick_npc_boss_for_area(db, "layer_2_mist"))

    def test_npc_boss_defeat_grants_core_and_logs_kind(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            tpl = game_app.create_npc_boss_from_active_robot(self.user_id, "layer_2")
            now = int(time.time())
            alert_enemy_id = game_app._encode_npc_boss_alert_id(int(tpl["id"]))
            db.execute(
                """
                INSERT INTO user_boss_progress
                (user_id, area_key, no_boss_streak, active_boss_enemy_id, boss_attempts_left, boss_alert_expires_at, updated_at)
                VALUES (?, 'layer_2', 0, ?, 3, ?, ?)
                ON CONFLICT(user_id, area_key) DO UPDATE SET
                    active_boss_enemy_id = excluded.active_boss_enemy_id,
                    boss_attempts_left = excluded.boss_attempts_left,
                    boss_alert_expires_at = excluded.boss_alert_expires_at,
                    updated_at = excluded.updated_at
                """,
                (self.user_id, int(alert_enemy_id), now + 3600, now),
            )
            before_core = int(game_app._get_player_core_qty(db, self.user_id, game_app.EVOLUTION_CORE_KEY))
            db.commit()

        client = self._client()
        with patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), patch.object(
            game_app, "resolve_attack", side_effect=self._resolve_for_win
        ):
            resp = client.post("/explore", data={"area_key": "layer_2", "boss_enter": "1"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("進化コア", html)
        self.assertIn("解析完了", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            after_core = int(game_app._get_player_core_qty(db, self.user_id, game_app.EVOLUTION_CORE_KEY))
            self.assertEqual(after_core - before_core, 1)
            boss_defeat = db.execute(
                """
                SELECT payload_json FROM world_events_log
                WHERE user_id = ? AND event_type = ?
                ORDER BY id DESC LIMIT 1
                """,
                (self.user_id, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"]),
            ).fetchone()
            self.assertIsNotNone(boss_defeat)
            self.assertIn('"boss_kind": "npc"', boss_defeat["payload_json"])


if __name__ == "__main__":
    unittest.main()
