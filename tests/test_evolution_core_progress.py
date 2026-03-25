import os
import tempfile
import time
import unittest
import json
from unittest import mock

import app as game_app
import init_db


class EvolutionCoreProgressTests(unittest.TestCase):
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
                ("core_progress_tester", "x", now),
            )
            self.user_id = int(
                db.execute(
                    "SELECT id FROM users WHERE username = ?",
                    ("core_progress_tester",),
                ).fetchone()["id"]
            )
            game_app.initialize_new_user(db, self.user_id)
            db.commit()
        self._create_active_robot()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "core_progress_tester"
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
                (self.user_id, "GaugeRunner", now, now),
            )
            robot_id = int(
                db.execute(
                    "SELECT id FROM robot_instances WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                    (self.user_id,),
                ).fetchone()["id"]
            )

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

    @staticmethod
    def _stable_weekly_env():
        return {
            "element": "NORMAL",
            "mode": "安定",
            "enemy_spawn_bonus": 0.0,
            "drop_bonus": 0.0,
            "reason": "test",
            "week_key": "2026-W13",
        }

    @staticmethod
    def _weak_enemy():
        return {
            "id": 999001,
            "key": "test_core_enemy",
            "name_ja": "進捗テスト機",
            "image_path": "assets/placeholder_enemy.png",
            "tier": 1,
            "element": "NORMAL",
            "faction": "neutral",
            "hp": 1,
            "atk": 1,
            "def": 1,
            "spd": 1,
            "acc": 1,
            "cri": 1,
        }

    @staticmethod
    def _resolve_for_win(att_atk, att_acc, att_cri, def_def, def_acc, **kwargs):
        if int(att_atk) >= 5:
            return 999, False, {"miss": False, "base_damage": 999}
        return 0, False, {"miss": True, "base_damage": 0}

    def _run_explore(self, area_key, *, progress_target=None, core_drop=False):
        client = self._client()
        patchers = [
            mock.patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()),
            mock.patch.object(game_app, "_pick_enemy_for_area", return_value=self._weak_enemy()),
            mock.patch.object(game_app, "resolve_attack", side_effect=self._resolve_for_win),
            mock.patch.object(game_app, "_has_area_boss_candidates", return_value=False),
            mock.patch.object(game_app, "_roll_evolution_core_drop", return_value=bool(core_drop)),
        ]
        if progress_target is not None:
            patchers.append(mock.patch.object(game_app, "EVOLUTION_CORE_PROGRESS_TARGET", int(progress_target)))
        with patchers[0], patchers[1], patchers[2], patchers[3], patchers[4]:
            if len(patchers) == 6:
                with patchers[5]:
                    return client.post("/explore", data={"area_key": area_key}, follow_redirects=True)
            return client.post("/explore", data={"area_key": area_key}, follow_redirects=True)

    def test_evolution_ui_unlocks_after_layer2_boss_defeat(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET evolution_core_progress = 72 WHERE id = ?", (self.user_id,))
            db.commit()

        client = self._client()
        home = client.get("/home")
        self.assertEqual(home.status_code, 200)
        home_html = home.get_data(as_text=True)
        self.assertNotIn("進化合成", home_html)
        self.assertNotIn("あと28勝で進化コア", home_html)

        evolve = client.get("/parts/evolve", follow_redirects=True)
        self.assertEqual(evolve.status_code, 200)
        self.assertIn("進化合成は第2層ボス撃破後に解放されます。", evolve.get_data(as_text=True))

        self._unlock_evolution_feature()

        home = client.get("/home")
        self.assertEqual(home.status_code, 200)
        self.assertIn("あと28勝で進化コア", home.get_data(as_text=True))

        evolve = client.get("/parts/evolve")
        self.assertEqual(evolve.status_code, 200)
        html = evolve.get_data(as_text=True)
        self.assertIn("進化コア進捗 72/100", html)
        self.assertIn("あと28勝で進化コア", html)

    def test_explore_before_unlock_does_not_grant_or_progress_core(self):
        resp = self._run_explore("layer_1")
        self.assertEqual(resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            user_row = db.execute(
                "SELECT evolution_core_progress FROM users WHERE id = ?",
                (self.user_id,),
            ).fetchone()
            self.assertEqual(int(user_row["evolution_core_progress"]), 0)
            core_qty = game_app._get_player_core_qty(db, self.user_id, game_app.EVOLUTION_CORE_KEY)
            self.assertEqual(core_qty, 0)
            progress_event = db.execute(
                """
                SELECT payload_json
                FROM world_events_log
                WHERE user_id = ? AND event_type = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (self.user_id, game_app.AUDIT_EVENT_TYPES["CORE_PROGRESS"]),
            ).fetchone()
            self.assertIsNone(progress_event)

    def test_explore_win_increments_progress_and_logs_progress_audit(self):
        self._unlock_evolution_feature()

        resp = self._run_explore("layer_1")
        self.assertEqual(resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            user_row = db.execute(
                "SELECT evolution_core_progress FROM users WHERE id = ?",
                (self.user_id,),
            ).fetchone()
            self.assertEqual(int(user_row["evolution_core_progress"]), 1)
            core_qty = game_app._get_player_core_qty(db, self.user_id, game_app.EVOLUTION_CORE_KEY)
            self.assertEqual(core_qty, 0)
            progress_event = db.execute(
                """
                SELECT payload_json
                FROM world_events_log
                WHERE user_id = ? AND event_type = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (self.user_id, game_app.AUDIT_EVENT_TYPES["CORE_PROGRESS"]),
            ).fetchone()
            self.assertIsNotNone(progress_event)
            payload = json.loads(progress_event["payload_json"] or "{}")
            self.assertEqual(int(payload.get("battle_wins") or 0), 1)
            self.assertEqual(int(payload.get("progress_after") or 0), 1)

    def test_progress_guarantee_grants_core_and_resets_progress(self):
        self._unlock_evolution_feature()
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET evolution_core_progress = 2 WHERE id = ?", (self.user_id,))
            db.commit()

        resp = self._run_explore("layer_1", progress_target=3, core_drop=False)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("進化コア保証達成", html)
        self.assertIn("勝利ゲージが満了しました", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            user_row = db.execute(
                "SELECT evolution_core_progress FROM users WHERE id = ?",
                (self.user_id,),
            ).fetchone()
            self.assertEqual(int(user_row["evolution_core_progress"]), 0)
            core_qty = game_app._get_player_core_qty(db, self.user_id, game_app.EVOLUTION_CORE_KEY)
            self.assertEqual(core_qty, 1)
            guarantee_event = db.execute(
                """
                SELECT payload_json
                FROM world_events_log
                WHERE user_id = ? AND event_type = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (self.user_id, game_app.AUDIT_EVENT_TYPES["CORE_GUARANTEE"]),
            ).fetchone()
            self.assertIsNotNone(guarantee_event)

    def test_direct_drop_still_grants_core_without_breaking_progress(self):
        self._unlock_evolution_feature()
        resp = self._run_explore("layer_3", progress_target=100, core_drop=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("進化コアを発見", resp.get_data(as_text=True))

        with game_app.app.app_context():
            db = game_app.get_db()
            user_row = db.execute(
                "SELECT evolution_core_progress FROM users WHERE id = ?",
                (self.user_id,),
            ).fetchone()
            self.assertEqual(int(user_row["evolution_core_progress"]), 1)
            core_qty = game_app._get_player_core_qty(db, self.user_id, game_app.EVOLUTION_CORE_KEY)
            self.assertEqual(core_qty, 1)
            drop_event = db.execute(
                """
                SELECT payload_json
                FROM world_events_log
                WHERE user_id = ? AND event_type = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (self.user_id, game_app.AUDIT_EVENT_TYPES["CORE_DROP"]),
            ).fetchone()
            self.assertIsNotNone(drop_event)
            payload = json.loads(drop_event["payload_json"] or "{}")
            self.assertNotEqual(payload.get("source"), "progress_guarantee")


if __name__ == "__main__":
    unittest.main()
