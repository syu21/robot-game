import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class PartMechanismTraitTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, coins, max_unlocked_layer)
                VALUES ('mechanism_user', 'x', ?, 0, 20, 100, 6)
                """,
                (now,),
            )
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, coins, max_unlocked_layer)
                VALUES ('mechanism_admin', 'x', ?, 1, 20, 100, 6)
                """,
                (now,),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = 'mechanism_user'").fetchone()["id"])
            self.admin_id = int(db.execute("SELECT id FROM users WHERE username = 'mechanism_admin'").fetchone()["id"])
            game_app.initialize_new_user(db, self.user_id)
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self, *, admin=False):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.admin_id if admin else self.user_id
            session["username"] = "mechanism_admin" if admin else "mechanism_user"
        return client

    def test_master_mapping_and_rarity_activation(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            n_row = db.execute("SELECT * FROM robot_parts WHERE key = 'right_arm_kuwagata'").fetchone()
            r_row = db.execute("SELECT * FROM robot_parts WHERE key = 'right_arm_r_kuwagata'").fetchone()
            self.assertEqual(n_row["mechanism_trait_key"], "armor_piercer")
            self.assertEqual(r_row["mechanism_trait_key"], "armor_piercer")
            n_view = game_app._part_mechanism_trait_view(n_row)
            r_view = game_app._part_mechanism_trait_view(r_row)
            self.assertFalse(n_view["active"])
            self.assertEqual(n_view["display_label"], "進化で解放")
            self.assertTrue(r_view["active"])
            self.assertEqual(r_view["label"], "装甲穿孔")

    def test_schema_sync_rejects_unknown_trait_and_restores_known_mapping(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE robot_parts SET mechanism_trait_key = 'bad_trait' WHERE key = 'head_1'")
            db.execute("UPDATE robot_parts SET mechanism_trait_key = 'bad_trait' WHERE key = 'right_arm_r_kuwagata'")
            changed = game_app._sync_part_mechanism_traits(db)
            db.commit()
            self.assertGreater(changed, 0)
            normal = db.execute("SELECT mechanism_trait_key FROM robot_parts WHERE key = 'head_1'").fetchone()
            insect_r = db.execute("SELECT mechanism_trait_key FROM robot_parts WHERE key = 'right_arm_r_kuwagata'").fetchone()
            self.assertEqual(normal["mechanism_trait_key"], "precision_processor")
            self.assertEqual(insect_r["mechanism_trait_key"], "armor_piercer")

    def test_battle_mechanism_modifiers_are_conditional_and_capped(self):
        snapshot = {
            "active": [
                {"key": "precision_processor", "label": "精密演算", "slot": "HEAD", "active": True},
                {"key": "tracking_array", "label": "追尾補正", "slot": "LEFT_ARM", "active": True},
                {"key": "armor_piercer", "label": "装甲穿孔", "slot": "RIGHT_ARM", "active": True},
                {"key": "stability_drive", "label": "姿勢制御", "slot": "LEGS", "active": True},
            ],
            "active_trait_keys": ["armor_piercer", "precision_processor", "stability_drive", "tracking_array"],
            "triggered_trait_keys": [],
            "triggered_labels": [],
        }
        state = game_app._part_mechanism_battle_state(snapshot, enemy_trait_key="fast")
        atk, acc, lines = game_app._part_mechanism_before_player_attack(
            state, turn=1, enemy_trait_key="fast", atk=100, acc=100
        )
        self.assertEqual(atk, 100)
        self.assertEqual(acc, 112)
        self.assertTrue(any("精密演算" in line for line in lines))
        damage, lines = game_app._part_mechanism_apply_outgoing_damage(state, 100, enemy_trait_key="heavy")
        self.assertEqual(damage, 107)
        self.assertTrue(any("装甲穿孔" in line for line in lines))
        incoming, lines = game_app._part_mechanism_apply_incoming_damage(state, 100, turn=3, enemy_trait_key="unstable")
        self.assertEqual(incoming, 96)
        self.assertTrue(any("姿勢制御" in line for line in lines))

    def test_parts_page_displays_locked_mechanism_trait_for_n_parts(self):
        response = self._client().get("/parts")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("機構特性", body)
        self.assertIn("進化で解放", body)

    def test_anomaly_mechanism_adjustment_records_active_and_triggered_keys(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            part = db.execute("SELECT * FROM robot_parts WHERE key = 'right_arm_r_kuwagata'").fetchone()
            part_instance_id = game_app._create_part_instance_from_master(db, self.user_id, part, status="equipped")
            db.execute("UPDATE part_instances SET rarity = 'R' WHERE id = ?", (part_instance_id,))
            db.commit()
            rows = db.execute(
                """
                SELECT pi.*, rp.part_type, rp.key, rp.mechanism_trait_key
                FROM part_instances pi
                JOIN robot_parts rp ON rp.id = pi.part_id
                WHERE pi.id = ?
                """,
                (part_instance_id,),
            ).fetchall()
            snapshot = game_app._part_mechanism_snapshot([dict(row) for row in rows])
            result = game_app._part_mechanism_apply_anomaly_player_stats(
                snapshot,
                {"hp": 100, "atk": 100, "def": 100, "spd": 100, "acc": 100, "cri": 5},
                {"stats": {"trait": "heavy_anomaly"}},
            )
            self.assertEqual(result["enemy_trait_key"], "heavy")
            self.assertIn("armor_piercer", result["triggered_trait_keys"])
            self.assertGreater(result["stats"]["atk"], 100)

    def test_admin_part_mechanism_snapshot_and_access_control(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            part = db.execute("SELECT * FROM robot_parts WHERE key = 'right_arm_r_kuwagata'").fetchone()
            part_instance_id = game_app._create_part_instance_from_master(db, self.user_id, part, status="equipped")
            db.execute("UPDATE part_instances SET rarity = 'R' WHERE id = ?", (part_instance_id,))
            payload = {
                "area_key": "layer_6_core",
                "player": {"triggered_trait_keys": ["armor_piercer"], "active_trait_keys": ["armor_piercer"]},
                "result": {"win": True},
            }
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, user_id, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (int(time.time()), game_app.AUDIT_EVENT_TYPES["EXPLORE_END"], self.user_id, json.dumps(payload)),
            )
            db.commit()
            snapshot = game_app._admin_part_mechanism_snapshot(db, window_days=7)
            armor = next(row for row in snapshot["rows"] if row["trait_key"] == "armor_piercer")
            self.assertEqual(snapshot["r_plus_equipped_users"], 1)
            self.assertEqual(armor["triggered_battles"], 1)
            self.assertEqual(armor["layer6_win_rate"], 100.0)
        self.assertEqual(self._client().get("/admin/metrics").status_code, 403)
        self.assertEqual(self._client(admin=True).get("/admin/metrics").status_code, 200)


if __name__ == "__main__":
    unittest.main()
