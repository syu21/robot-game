import os
import tempfile
import time
import unittest
from unittest import mock

import app as game_app
import init_db


class ModuleOSPhase1Tests(unittest.TestCase):
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
                VALUES ('os_tester', 'x', ?, 1, 0, 4)
                """,
                (now,),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = 'os_tester'").fetchone()["id"])
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer)
                VALUES ('os_other', 'x', ?, 0, 0, 4)
                """,
                (now,),
            )
            self.other_user_id = int(db.execute("SELECT id FROM users WHERE username = 'os_other'").fetchone()["id"])
            self.robot_id = self._create_robot(db)
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "os_tester"
        return client

    def _create_robot(self, db):
        now = int(time.time())
        db.execute(
            "INSERT INTO robot_instances (user_id, name, status, created_at, updated_at) VALUES (?, 'OSBot', 'active', ?, ?)",
            (self.user_id, now, now),
        )
        robot_id = int(db.execute("SELECT id FROM robot_instances WHERE user_id = ?", (self.user_id,)).fetchone()["id"])
        part_keys = []
        for part_type in ("HEAD", "RIGHT_ARM", "LEFT_ARM", "LEGS"):
            part_keys.append(db.execute("SELECT key FROM robot_parts WHERE part_type = ? AND is_active = 1 LIMIT 1", (part_type,)).fetchone()["key"])
        db.execute(
            "INSERT INTO robot_instance_parts (robot_instance_id, head_key, r_arm_key, l_arm_key, legs_key) VALUES (?, ?, ?, ?, ?)",
            (robot_id, *part_keys),
        )
        db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (robot_id, self.user_id))
        return robot_id

    def _grant(self, user_id, module_key, brand_key=None, role_key=None):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            cur = db.execute(
                """
                INSERT INTO user_research_modules (user_id, module_key, status, brand_key, role_key, created_at, updated_at)
                VALUES (?, ?, 'inventory', ?, ?, ?, ?)
                """,
                (int(user_id), module_key, brand_key, role_key, now, now),
            )
            db.commit()
            return int(cur.lastrowid)

    def test_schema_and_brand_backfill_are_idempotent(self):
        module_id = self._grant(self.user_id, "heavy_prototype")
        with game_app.app.app_context():
            db = game_app.get_db()
            before = db.execute("SELECT * FROM user_research_modules WHERE id = ?", (module_id,)).fetchone()
            game_app.close_db()
            init_db.main()
            db = game_app.get_db()
            after = db.execute("SELECT * FROM user_research_modules WHERE id = ?", (module_id,)).fetchone()
            self.assertIn("brand_key", {row["name"] for row in db.execute("PRAGMA table_info(user_research_modules)").fetchall()})
            self.assertEqual(after["brand_key"], "titan")
            self.assertEqual(after["role_key"], "guard")
            self.assertEqual(int(after["is_locked"]), int(before["is_locked"]))
            self.assertEqual(after["module_key"], before["module_key"])

    def test_loadout_rejects_invalid_and_allows_locked(self):
        ids = [self._grant(self.user_id, "heavy_prototype", "titan", "guard") for _ in range(4)]
        other_id = self._grant(self.other_user_id, "heavy_prototype", "titan", "guard")
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE user_research_modules SET is_locked = 1 WHERE id = ?", (ids[0],))
            db.execute("UPDATE user_research_modules SET status = 'consumed' WHERE id = ?", (ids[3],))
            db.commit()
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertTrue(game_app._set_research_module_loadout(db, self.user_id, ids[:3])["ok"])
            self.assertFalse(game_app._set_research_module_loadout(db, self.user_id, ids[:4])["ok"])
            self.assertFalse(game_app._set_research_module_loadout(db, self.user_id, [ids[0], ids[0]])["ok"])
            self.assertFalse(game_app._set_research_module_loadout(db, self.user_id, [other_id])["ok"])
            self.assertFalse(game_app._set_research_module_loadout(db, self.user_id, [ids[3]])["ok"])

    def test_synergy_and_os_names(self):
        mods = [{"instance_id": 1, "brand_key": "titan", "hp_bonus": 1, "def_bonus": 1} for _ in range(3)]
        titan = game_app._module_loadout_summary(mods)
        self.assertEqual(titan["os_name"], "TITAN FORTRESS OS")
        self.assertEqual(titan["synergy_bonus"], {"hp": 8, "atk": 0, "def": 8, "spd": -2, "acc": 0, "cri": 0})
        hybrid = game_app._module_loadout_summary([
            {"instance_id": 1, "brand_key": "titan"},
            {"instance_id": 2, "brand_key": "volt"},
            {"instance_id": 3, "brand_key": "eden"},
        ])
        self.assertEqual(hybrid["os_name"], "HYBRID CONTROL OS")
        self.assertEqual(hybrid["synergy_bonus"], {"hp": 2, "atk": 2, "def": 2, "spd": 2, "acc": 2, "cri": 2})
        custom = game_app._module_loadout_summary([{"instance_id": 1, "brand_key": "titan"}, {"instance_id": 2, "brand_key": "volt"}])
        self.assertEqual(custom["synergy_label"], "なし")
        self.assertEqual(game_app._module_loadout_summary([])["os_name"], "NO MODULE OS")

    def test_loadout_bonus_applies_once_and_clears_after_explore(self):
        module_ids = [self._grant(self.user_id, "heavy_prototype", "titan", "guard") for _ in range(3)]
        client = self._client()
        client.post("/modules/select", data={"module_instance_ids": [str(mid) for mid in module_ids]})

        def capture_attack(att_atk, *_args, **_kwargs):
            self.captured_atk = int(att_atk)
            return 999, False, {"miss": False, "base_damage": 999}

        enemy = {"id": 990010, "key": "os_enemy", "name_ja": "OS検証機", "image_path": "assets/placeholder_enemy.png", "tier": 1, "element": "NORMAL", "faction": "neutral", "hp": 1, "atk": 1, "def": 1, "spd": 1, "acc": 1, "cri": 1}
        with mock.patch.object(game_app, "_world_current_environment", return_value={"element": "NORMAL", "mode": "安定", "enemy_spawn_bonus": 0, "drop_bonus": 0, "reason": "test", "week_key": "2026-W30"}), \
             mock.patch.object(game_app, "_pick_enemy_for_area", return_value=enemy), \
             mock.patch.object(game_app, "resolve_attack", side_effect=capture_attack), \
             mock.patch.object(game_app, "_has_area_boss_candidates", return_value=False), \
             mock.patch.object(game_app, "_roll_research_module_drop", return_value=None):
            resp = client.post("/explore", data={"area_key": "layer_2"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("今回の搭載OS: TITAN FORTRESS OS", resp.get_data(as_text=True))
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertEqual(int(db.execute("SELECT COUNT(*) AS c FROM user_module_loadouts WHERE user_id = ?", (self.user_id,)).fetchone()["c"]), 0)
            event = db.execute("SELECT payload_json FROM world_events_log WHERE event_type = ? ORDER BY id DESC LIMIT 1", (game_app.AUDIT_EVENT_TYPES["MODULE_CONSUME"],)).fetchone()
            self.assertIsNotNone(event)


if __name__ == "__main__":
    unittest.main()
