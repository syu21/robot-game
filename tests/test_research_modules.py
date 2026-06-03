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

    def test_research_module_trade_columns_and_prices_exist(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            module_cols = {row["name"] for row in db.execute("PRAGMA table_info(research_modules)").fetchall()}
            instance_cols = {row["name"] for row in db.execute("PRAGMA table_info(user_research_modules)").fetchall()}
            for col in ("tier", "trade_policy", "source_type", "is_limited", "npc_sell_price"):
                self.assertIn(col, module_cols)
            for col in ("is_locked", "sold_at"):
                self.assertIn(col, instance_cols)
            proto = db.execute("SELECT tier, trade_policy, source_type, is_limited, npc_sell_price FROM research_modules WHERE module_key = 'sniper_prototype'").fetchone()
            self.assertEqual(int(proto["tier"]), 1)
            self.assertEqual(proto["trade_policy"], "tradable")
            self.assertEqual(proto["source_type"], "normal_drop")
            self.assertEqual(int(proto["is_limited"]), 0)
            self.assertEqual(int(proto["npc_sell_price"]), 300)
            complete = db.execute("SELECT tier, trade_policy, source_type, is_limited, npc_sell_price FROM research_modules WHERE module_key = 'sniper_complete'").fetchone()
            self.assertEqual(int(complete["tier"]), 2)
            self.assertEqual(complete["trade_policy"], "tradable")
            self.assertEqual(complete["source_type"], "combine")
            self.assertEqual(int(complete["is_limited"]), 0)
            self.assertEqual(int(complete["npc_sell_price"]), 1500)

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
            catalog = db.execute("SELECT source.module_key FROM (SELECT module_key FROM user_research_module_catalog WHERE user_id = ?) AS source WHERE source.module_key = 'sniper_prototype'", (self.user_id,)).fetchone()
            self.assertIsNotNone(catalog)
            catalog_event = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ? ORDER BY id DESC LIMIT 1",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["MODULE_CATALOG_REGISTER"]),
            ).fetchone()
            self.assertIsNotNone(catalog_event)
            catalog_payload = json.loads(catalog_event["payload_json"] or "{}")
            self.assertEqual(catalog_payload["source"], "pity")
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
            catalog = db.execute("SELECT first_instance_id FROM user_research_module_catalog WHERE user_id = ? AND module_key = 'sniper_complete'", (self.user_id,)).fetchone()
            self.assertIsNotNone(catalog)
            self.assertEqual(int(catalog["first_instance_id"]), int(result["id"]))

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

    def test_catalog_rate_keeps_consumed_and_sold_modules(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            module = game_app._grant_research_module_instance(db, self.user_id, "heavy_prototype", source="drop")
            db.execute("UPDATE user_research_modules SET status = 'consumed' WHERE id = ?", (module["instance_id"],))
            sold = game_app._grant_research_module_instance(db, self.user_id, "analysis_prototype", source="drop")
            db.execute("UPDATE user_research_modules SET status = 'consumed', sold_at = ? WHERE id = ?", ("2026-06-03T00:00:00+00:00", sold["instance_id"]))
            db.commit()
            summary = game_app._research_module_catalog_summary(db, self.user_id)
            self.assertEqual(summary["registered"], 2)
            self.assertEqual(summary["total"], 12)
        html = self._client().get("/modules").get_data(as_text=True)
        self.assertIn("モジュール図鑑: 2/12", html)
        self.assertIn("狙撃モジュール 完成型", html)
        self.assertIn("未所持", html)

    def test_lock_and_unlock_own_module(self):
        module_id = self._grant_module(self.user_id, "stable_prototype", count=1)[0]
        client = self._client()
        self.assertEqual(client.post("/modules/lock", data={"module_instance_id": module_id}).status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            locked = int(db.execute("SELECT is_locked FROM user_research_modules WHERE id = ?", (module_id,)).fetchone()["is_locked"])
            self.assertEqual(locked, 1)
        self.assertEqual(client.post("/modules/unlock", data={"module_instance_id": module_id}).status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            locked = int(db.execute("SELECT is_locked FROM user_research_modules WHERE id = ?", (module_id,)).fetchone()["is_locked"])
            self.assertEqual(locked, 0)
            lock_event = db.execute("SELECT id FROM world_events_log WHERE user_id = ? AND event_type = ?", (self.user_id, game_app.AUDIT_EVENT_TYPES["MODULE_LOCK"])).fetchone()
            unlock_event = db.execute("SELECT id FROM world_events_log WHERE user_id = ? AND event_type = ?", (self.user_id, game_app.AUDIT_EVENT_TYPES["MODULE_UNLOCK"])).fetchone()
            self.assertIsNotNone(lock_event)
            self.assertIsNotNone(unlock_event)

    def test_cannot_lock_other_users_module(self):
        module_id = self._grant_module(self.other_user_id, "stable_prototype", count=1)[0]
        self.assertEqual(self._client().post("/modules/lock", data={"module_instance_id": module_id}).status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            locked = int(db.execute("SELECT is_locked FROM user_research_modules WHERE id = ?", (module_id,)).fetchone()["is_locked"])
            self.assertEqual(locked, 0)

    def test_locked_module_is_not_combined_or_sold_but_selectable(self):
        ids = self._grant_module(self.user_id, "heavy_prototype", count=3)
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE user_research_modules SET is_locked = 1 WHERE id = ?", (ids[0],))
            db.commit()
        html = self._client().get("/home").get_data(as_text=True)
        self.assertIn("重装モジュール 試作型", html)
        self._client().post("/modules/combine", data={"source_module_key": "heavy_prototype"}, follow_redirects=False)
        with game_app.app.app_context():
            db = game_app.get_db()
            complete_count = int(db.execute("SELECT COUNT(*) AS c FROM user_research_modules WHERE user_id = ? AND module_key = 'heavy_complete'", (self.user_id,)).fetchone()["c"])
            self.assertEqual(complete_count, 0)
        self._client().post("/modules/sell", data={"module_instance_id": ids[0], "confirm_sell": "1"}, follow_redirects=False)
        with game_app.app.app_context():
            db = game_app.get_db()
            status = db.execute("SELECT status FROM user_research_modules WHERE id = ?", (ids[0],)).fetchone()["status"]
            self.assertEqual(status, "inventory")

    def test_active_module_is_not_combined_or_sold(self):
        ids = self._grant_module(self.user_id, "assault_prototype", count=3)
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET active_research_module_instance_id = ? WHERE id = ?", (ids[0], self.user_id))
            db.commit()
        self._client().post("/modules/combine", data={"source_module_key": "assault_prototype"}, follow_redirects=False)
        with game_app.app.app_context():
            db = game_app.get_db()
            complete_count = int(db.execute("SELECT COUNT(*) AS c FROM user_research_modules WHERE user_id = ? AND module_key = 'assault_complete'", (self.user_id,)).fetchone()["c"])
            self.assertEqual(complete_count, 0)
        self._client().post("/modules/sell", data={"module_instance_id": ids[0], "confirm_sell": "1"}, follow_redirects=False)
        with game_app.app.app_context():
            db = game_app.get_db()
            status = db.execute("SELECT status FROM user_research_modules WHERE id = ?", (ids[0],)).fetchone()["status"]
            self.assertEqual(status, "inventory")

    def test_sell_inventory_unlocked_module(self):
        module_id = self._grant_module(self.user_id, "sniper_prototype", count=1)[0]
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET coins = 10 WHERE id = ?", (self.user_id,))
            db.commit()
        resp = self._client().post("/modules/sell", data={"module_instance_id": module_id, "confirm_sell": "1"}, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT coins FROM users WHERE id = ?", (self.user_id,)).fetchone()
            module = db.execute("SELECT status, sold_at FROM user_research_modules WHERE id = ?", (module_id,)).fetchone()
            self.assertEqual(int(user["coins"]), 310)
            self.assertEqual(module["status"], "consumed")
            self.assertTrue(module["sold_at"])
            sell_event = db.execute("SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ?", (self.user_id, game_app.AUDIT_EVENT_TYPES["MODULE_SELL"])).fetchone()
            coin_event = db.execute("SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ?", (self.user_id, game_app.AUDIT_EVENT_TYPES["COIN_DELTA"])).fetchone()
            self.assertIsNotNone(sell_event)
            self.assertIsNotNone(coin_event)

    def test_cannot_sell_other_user_or_zero_price_module(self):
        other_id = self._grant_module(self.other_user_id, "sniper_prototype", count=1)[0]
        self._client().post("/modules/sell", data={"module_instance_id": other_id, "confirm_sell": "1"}, follow_redirects=False)
        with game_app.app.app_context():
            db = game_app.get_db()
            status = db.execute("SELECT status FROM user_research_modules WHERE id = ?", (other_id,)).fetchone()["status"]
            self.assertEqual(status, "inventory")
        module_id = self._grant_module(self.user_id, "stable_prototype", count=1)[0]
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE research_modules SET npc_sell_price = 0 WHERE module_key = 'stable_prototype'")
            db.commit()
        self._client().post("/modules/sell", data={"module_instance_id": module_id, "confirm_sell": "1"}, follow_redirects=False)
        with game_app.app.app_context():
            db = game_app.get_db()
            status = db.execute("SELECT status FROM user_research_modules WHERE id = ?", (module_id,)).fetchone()["status"]
            self.assertEqual(status, "inventory")


if __name__ == "__main__":
    unittest.main()
