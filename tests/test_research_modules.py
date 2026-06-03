import json
import os
import tempfile
import time
import unittest
from unittest import mock

import app as game_app
import init_db


class ResearchModuleTests(unittest.TestCase):
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
                VALUES (?, ?, ?, 1, 0, 4)
                """,
                ("module_tester", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("module_tester",)).fetchone()["id"])
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 0, 0, 4)
                """,
                ("module_other", "x", now),
            )
            self.other_user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("module_other",)).fetchone()["id"])
            self.robot_id = self._create_active_robot(db, self.user_id)
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "module_tester"
        return client

    def _create_active_robot(self, db, user_id):
        now = int(time.time())
        db.execute(
            """
            INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
            VALUES (?, ?, 'active', ?, ?)
            """,
            (int(user_id), "ModuleBot", now, now),
        )
        robot_id = int(db.execute("SELECT id FROM robot_instances WHERE user_id = ? ORDER BY id DESC LIMIT 1", (int(user_id),)).fetchone()["id"])

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
            "id": 990001,
            "key": "test_module_enemy",
            "name_ja": "研究テスト機",
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
    def _resolve_for_win(att_atk, *_args, **_kwargs):
        if int(att_atk) >= 5:
            return 999, False, {"miss": False, "base_damage": 999}
        return 0, False, {"miss": True, "base_damage": 0}

    def _run_explore(self, area_key):
        client = self._client()
        with mock.patch.object(game_app, "_world_current_environment", return_value=self._stable_weekly_env()), \
             mock.patch.object(game_app, "_pick_enemy_for_area", return_value=self._weak_enemy()), \
             mock.patch.object(game_app, "resolve_attack", side_effect=self._resolve_for_win), \
             mock.patch.object(game_app, "_has_area_boss_candidates", return_value=False), \
             mock.patch.object(game_app, "_roll_research_module_drop", return_value=None), \
             mock.patch.object(game_app.random, "choice", return_value="sniper_prototype"):
            return client.post("/explore", data={"area_key": area_key}, follow_redirects=True)

    def _grant_module(self, user_id, module_key, count=1):
        with game_app.app.app_context():
            db = game_app.get_db()
            ids = []
            now = int(time.time())
            for _ in range(int(count)):
                cur = db.execute(
                    """
                    INSERT INTO user_research_modules (user_id, module_key, status, created_at, updated_at)
                    VALUES (?, ?, 'inventory', ?, ?)
                    """,
                    (int(user_id), module_key, now, now),
                )
                ids.append(int(cur.lastrowid))
            db.commit()
            return ids

    def test_research_module_pity_column_exists(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            cols = {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}
            self.assertIn("research_module_pity", cols)

    def test_target_area_win_adds_pity(self):
        resp = self._run_explore("layer_3")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("研究ゲージ +2", resp.get_data(as_text=True))
        with game_app.app.app_context():
            db = game_app.get_db()
            pity = int(db.execute("SELECT research_module_pity FROM users WHERE id = ?", (self.user_id,)).fetchone()["research_module_pity"])
            self.assertEqual(pity, 2)

    def test_pity_grants_module_and_subtracts_100(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET research_module_pity = 99 WHERE id = ?", (self.user_id,))
            db.commit()
        resp = self._run_explore("layer_2")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("研究ゲージ達成: 狙撃モジュール 試作型を獲得", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            pity = int(db.execute("SELECT research_module_pity FROM users WHERE id = ?", (self.user_id,)).fetchone()["research_module_pity"])
            self.assertEqual(pity, 0)
            module_count = int(db.execute("SELECT COUNT(*) AS c FROM user_research_modules WHERE user_id = ? AND module_key = 'sniper_prototype'", (self.user_id,)).fetchone()["c"])
            self.assertEqual(module_count, 1)
            event = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ? ORDER BY id DESC LIMIT 1",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["MODULE_PITY_GRANT"]),
            ).fetchone()
            self.assertIsNotNone(event)
            payload = json.loads(event["payload_json"] or "{}")
            self.assertEqual(payload["module_key"], "sniper_prototype")

    def test_non_target_area_does_not_add_pity(self):
        resp = self._run_explore("layer_1")
        self.assertEqual(resp.status_code, 200)
        with game_app.app.app_context():
            db = game_app.get_db()
            pity = int(db.execute("SELECT research_module_pity FROM users WHERE id = ?", (self.user_id,)).fetchone()["research_module_pity"])
            self.assertEqual(pity, 0)

    def test_combine_three_prototypes_into_complete(self):
        source_ids = self._grant_module(self.user_id, "sniper_prototype", count=3)
        resp = self._client().post("/modules/combine", data={"source_module_key": "sniper_prototype"}, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            consumed = db.execute(
                f"SELECT COUNT(*) AS c FROM user_research_modules WHERE id IN ({','.join(['?'] * len(source_ids))}) AND status = 'consumed'",
                source_ids,
            ).fetchone()["c"]
            self.assertEqual(int(consumed), 3)
            result = db.execute(
                "SELECT id FROM user_research_modules WHERE user_id = ? AND module_key = 'sniper_complete' AND status = 'inventory'",
                (self.user_id,),
            ).fetchone()
            self.assertIsNotNone(result)
            event = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ? ORDER BY id DESC LIMIT 1",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["MODULE_COMBINE"]),
            ).fetchone()
            self.assertIsNotNone(event)
            payload = json.loads(event["payload_json"] or "{}")
            self.assertEqual(payload["source_module_key"], "sniper_prototype")
            self.assertEqual(payload["result_module_key"], "sniper_complete")
            self.assertEqual(payload["consumed_instance_ids"], source_ids)

    def test_cannot_combine_other_users_modules(self):
        self._grant_module(self.other_user_id, "heavy_prototype", count=3)
        resp = self._client().post("/modules/combine", data={"source_module_key": "heavy_prototype"}, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            count = int(db.execute("SELECT COUNT(*) AS c FROM user_research_modules WHERE user_id = ? AND module_key = 'heavy_complete'", (self.user_id,)).fetchone()["c"])
            self.assertEqual(count, 0)

    def test_cannot_combine_two_or_fewer_prototypes(self):
        self._grant_module(self.user_id, "assault_prototype", count=2)
        resp = self._client().post("/modules/combine", data={"source_module_key": "assault_prototype"}, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            complete_count = int(db.execute("SELECT COUNT(*) AS c FROM user_research_modules WHERE user_id = ? AND module_key = 'assault_complete'", (self.user_id,)).fetchone()["c"])
            self.assertEqual(complete_count, 0)
            inventory_count = int(db.execute("SELECT COUNT(*) AS c FROM user_research_modules WHERE user_id = ? AND module_key = 'assault_prototype' AND status = 'inventory'", (self.user_id,)).fetchone()["c"])
            self.assertEqual(inventory_count, 2)

    def test_complete_module_applies_battle_stats_bonus(self):
        ids = self._grant_module(self.user_id, "berserk_complete", count=1)
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET active_research_module_instance_id = ? WHERE id = ?", (ids[0], self.user_id))
            user = db.execute("SELECT * FROM users WHERE id = ?", (self.user_id,)).fetchone()
            module = game_app._active_research_module_for_user(db, self.user_id, user_row=user)
            adjusted = game_app._apply_research_module_to_stats(
                {"hp": 10, "atk": 10, "def": 10, "spd": 10, "acc": 10, "cri": 10},
                module,
            )
            self.assertEqual(adjusted["atk"], 28)
            self.assertEqual(adjusted["cri"], 19)
            self.assertEqual(adjusted["acc"], 1)


if __name__ == "__main__":
    unittest.main()
