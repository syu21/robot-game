import os
import tempfile
import time
import unittest
from unittest import mock

import app as game_app
import init_db


class TacticalPresetTests(unittest.TestCase):
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
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer) VALUES ('preset_user', 'x', ?, 1, 10, 4)",
                (now,),
            )
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer) VALUES ('preset_other', 'x', ?, 0, 0, 1)",
                (now,),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = 'preset_user'").fetchone()["id"])
            self.other_user_id = int(db.execute("SELECT id FROM users WHERE username = 'preset_other'").fetchone()["id"])
            self.robot_id = self._create_robot(db, "PresetBot")
            db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (self.robot_id, self.user_id))
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "preset_user"
        return client

    def _part_master(self, db, part_type, offset=0):
        rows = db.execute(
            "SELECT * FROM robot_parts WHERE part_type = ? AND is_active = 1 ORDER BY id ASC",
            (part_type,),
        ).fetchall()
        self.assertGreater(len(rows), offset)
        return rows[offset]

    def _grant_part(self, db, part_type, offset=0, status="inventory", user_id=None):
        part = self._part_master(db, part_type, offset=offset)
        return game_app._create_part_instance_from_master(
            db,
            int(user_id or self.user_id),
            part,
            plus=0,
            status=status,
        ), str(part["key"])

    def _create_robot(self, db, name, offsets=None):
        offsets = offsets or {"HEAD": 0, "RIGHT_ARM": 0, "LEFT_ARM": 0, "LEGS": 0}
        now = int(time.time())
        db.execute(
            "INSERT INTO robot_instances (user_id, name, status, frame_type, created_at, updated_at) VALUES (?, ?, 'active', 'normal', ?, ?)",
            (self.user_id, name, now, now),
        )
        robot_id = int(db.execute("SELECT id FROM robot_instances WHERE name = ?", (name,)).fetchone()["id"])
        slots = {}
        keys = {}
        for slot, part_type in (("head", "HEAD"), ("r_arm", "RIGHT_ARM"), ("l_arm", "LEFT_ARM"), ("legs", "LEGS")):
            pid, key = self._grant_part(db, part_type, offset=int(offsets.get(part_type, 0)), status="equipped")
            slots[slot] = pid
            keys[slot] = key
        db.execute(
            """
            INSERT INTO robot_instance_parts (
                robot_instance_id, head_key, r_arm_key, l_arm_key, legs_key,
                head_part_instance_id, r_arm_part_instance_id, l_arm_part_instance_id, legs_part_instance_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                robot_id,
                keys["head"],
                keys["r_arm"],
                keys["l_arm"],
                keys["legs"],
                slots["head"],
                slots["r_arm"],
                slots["l_arm"],
                slots["legs"],
            ),
        )
        return robot_id

    def _grant_module(self, key="heavy_prototype"):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            cur = db.execute(
                "INSERT INTO user_research_modules (user_id, module_key, status, created_at, updated_at) VALUES (?, ?, 'inventory', ?, ?)",
                (self.user_id, key, now, now),
            )
            db.commit()
            return int(cur.lastrowid)

    def _mapping(self, db):
        row = db.execute("SELECT * FROM robot_instance_parts WHERE robot_instance_id = ?", (self.robot_id,)).fetchone()
        return {
            "head": int(row["head_part_instance_id"]),
            "r_arm": int(row["r_arm_part_instance_id"]),
            "l_arm": int(row["l_arm_part_instance_id"]),
            "legs": int(row["legs_part_instance_id"]),
        }

    def test_save_rename_delete_and_three_fixed_slots(self):
        client = self._client()
        resp = client.post(f"/robots/{self.robot_id}/presets/save", data={"preset_slot": "A"})
        self.assertEqual(resp.status_code, 302)
        resp = client.post(f"/robots/{self.robot_id}/presets/rename", data={"preset_slot": "B", "display_name": "高速 対策 <x>"})
        self.assertEqual(resp.status_code, 302)
        resp = client.post(f"/robots/{self.robot_id}/presets/save", data={"preset_slot": "D"})
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            rows = db.execute("SELECT preset_slot, display_name, config_json FROM robot_loadout_presets WHERE robot_instance_id = ? ORDER BY preset_slot", (self.robot_id,)).fetchall()
            self.assertEqual([row["preset_slot"] for row in rows], ["A", "B"])
            self.assertIn("高速 対策 x", rows[1]["display_name"])
            self.assertIsNone(rows[1]["config_json"])
        resp = client.post(f"/robots/{self.robot_id}/presets/delete", data={"preset_slot": "A"})
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertIsNone(db.execute("SELECT 1 FROM robot_loadout_presets WHERE robot_instance_id = ? AND preset_slot = 'A'", (self.robot_id,)).fetchone())

    def test_apply_switches_parts_and_modules_without_duplication(self):
        module_a = self._grant_module("heavy_prototype")
        module_b = self._grant_module("sniper_prototype")
        client = self._client()
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app._set_research_module_loadout(db, self.user_id, [module_a])
            before_count = int(db.execute("SELECT COUNT(*) AS c FROM part_instances WHERE user_id = ?", (self.user_id,)).fetchone()["c"])
            original = self._mapping(db)
            db.commit()
        client.post(f"/robots/{self.robot_id}/presets/save", data={"preset_slot": "A"})
        with game_app.app.app_context():
            db = game_app.get_db()
            replacement = {}
            replacement_keys = {}
            for slot, part_type in (("head", "HEAD"), ("r_arm", "RIGHT_ARM"), ("l_arm", "LEFT_ARM"), ("legs", "LEGS")):
                pid, key = self._grant_part(db, part_type, offset=1, status="inventory")
                replacement[slot] = pid
                replacement_keys[slot] = key
            game_app._return_part_instance_to_pool(db, self.user_id, original["head"])
            game_app._return_part_instance_to_pool(db, self.user_id, original["r_arm"])
            game_app._return_part_instance_to_pool(db, self.user_id, original["l_arm"])
            game_app._return_part_instance_to_pool(db, self.user_id, original["legs"])
            db.execute(
                """
                UPDATE robot_instance_parts
                SET head_part_instance_id = ?, r_arm_part_instance_id = ?, l_arm_part_instance_id = ?, legs_part_instance_id = ?,
                    head_key = ?, r_arm_key = ?, l_arm_key = ?, legs_key = ?
                WHERE robot_instance_id = ?
                """,
                (
                    replacement["head"], replacement["r_arm"], replacement["l_arm"], replacement["legs"],
                    replacement_keys["head"], replacement_keys["r_arm"], replacement_keys["l_arm"], replacement_keys["legs"],
                    self.robot_id,
                ),
            )
            for pid in replacement.values():
                db.execute("UPDATE part_instances SET status = 'equipped' WHERE id = ?", (pid,))
            game_app._set_research_module_loadout(db, self.user_id, [module_b])
            db.commit()
        client.post(f"/robots/{self.robot_id}/presets/save", data={"preset_slot": "B"})
        with mock.patch.object(game_app, "_compose_instance_assets_no_commit", return_value=("robot_composed/test.png", "robot_icons/test.png")):
            resp = client.post(f"/robots/{self.robot_id}/presets/apply", data={"preset_slot": "A"})
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertEqual(self._mapping(db), original)
            module_ids = game_app._current_module_instance_ids(db, self.user_id)
            self.assertEqual(module_ids, [module_a])
            after_count = int(db.execute("SELECT COUNT(*) AS c FROM part_instances WHERE user_id = ?", (self.user_id,)).fetchone()["c"])
            self.assertEqual(after_count, before_count + 4)

    def test_apply_restores_protocol_and_battle_code_atomically(self):
        module_a = self._grant_module("heavy_prototype")
        module_b = self._grant_module("heavy_prototype")
        client = self._client()
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app._set_research_module_loadout(db, self.user_id, [module_a, module_b])
            loadout = game_app._active_research_module_loadout_for_user(db, self.user_id)
            protocol_result = game_app._set_module_protocol(db, self.user_id, "fortress_guard", loadout)
            self.assertTrue(protocol_result["ok"])
            code_result = game_app._battle_code_library_save(
                db,
                self.user_id,
                1,
                "enemy_fast",
                "guaranteed_hit",
                "boss",
                condition_key_b="enemy_heavy",
                effect_key_b="attack_up_15",
            )
            self.assertTrue(code_result["ok"])
            select_result = game_app._battle_code_library_select(db, self.user_id, code_result["code"]["id"])
            self.assertTrue(select_result["ok"])
            db.commit()
        client.post(f"/robots/{self.robot_id}/presets/save", data={"preset_slot": "A"})
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app._set_research_module_loadout(db, self.user_id, [])
            game_app._clear_module_protocol(db, self.user_id)
            game_app._battle_code_library_unselect(db, self.user_id)
            db.commit()
        with mock.patch.object(game_app, "_compose_instance_assets_no_commit", return_value=("robot_composed/test.png", "robot_icons/test.png")):
            resp = client.post(f"/robots/{self.robot_id}/presets/apply", data={"preset_slot": "A"})
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT selected_module_protocol_key FROM users WHERE id = ?", (self.user_id,)).fetchone()
            active_code = game_app._active_battle_code_for_user(db, self.user_id)
            self.assertEqual(user["selected_module_protocol_key"], "fortress_guard")
            self.assertEqual(active_code["condition_key_b"], "enemy_heavy")
            self.assertEqual(active_code["code_version"], "dual")

    def test_invalid_part_rolls_back_without_partial_apply(self):
        client = self._client()
        client.post(f"/robots/{self.robot_id}/presets/save", data={"preset_slot": "A"})
        with game_app.app.app_context():
            db = game_app.get_db()
            saved = self._mapping(db)
            db.execute("UPDATE part_instances SET status = 'consumed' WHERE id = ?", (saved["l_arm"],))
            current = dict(saved)
            pid, key = self._grant_part(db, "LEFT_ARM", offset=1, status="equipped")
            current["l_arm"] = pid
            db.execute("UPDATE robot_instance_parts SET l_arm_part_instance_id = ?, l_arm_key = ? WHERE robot_instance_id = ?", (pid, key, self.robot_id))
            db.commit()
        with mock.patch.object(game_app, "_compose_instance_assets_no_commit", return_value=("robot_composed/test.png", "robot_icons/test.png")):
            resp = client.post(f"/robots/{self.robot_id}/presets/apply", data={"preset_slot": "A"})
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertEqual(self._mapping(db), current)

    def test_client_config_is_ignored_when_saving(self):
        client = self._client()
        with game_app.app.app_context():
            db = game_app.get_db()
            original = self._mapping(db)
            other_pid, _key = self._grant_part(db, "HEAD", offset=1, status="inventory", user_id=self.other_user_id)
            db.commit()
        client.post(f"/robots/{self.robot_id}/presets/save", data={"preset_slot": "A", "head": str(other_pid)})
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT config_json FROM robot_loadout_presets WHERE robot_instance_id = ? AND preset_slot = 'A'", (self.robot_id,)).fetchone()
            config = game_app._normalize_tactical_config(row["config_json"])
            self.assertEqual(config["parts"], original)


if __name__ == "__main__":
    unittest.main()
