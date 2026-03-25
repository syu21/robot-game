import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class EvolveRouteTests(unittest.TestCase):
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
                "INSERT INTO users (username, password_hash, created_at, is_admin) VALUES (?, ?, ?, 1)",
                ("evolve_tester", "x", now),
            )
            self.user_id = db.execute("SELECT id FROM users WHERE username = ?", ("evolve_tester",)).fetchone()["id"]
            game_app.initialize_new_user(db, self.user_id)
            row = db.execute(
                """
                SELECT pi.id, pi.part_id, rp.part_type, rp.element, rp.image_path
                FROM part_instances pi
                JOIN robot_parts rp ON rp.id = pi.part_id
                WHERE pi.user_id = ? AND pi.status = 'inventory' AND UPPER(COALESCE(pi.rarity, 'N')) = 'N'
                ORDER BY pi.id ASC
                LIMIT 1
                """,
                (self.user_id,),
            ).fetchone()
            self.part_instance_id = int(row["id"])
            self.source_part_id = int(row["part_id"])
            source_part_type = str(row["part_type"]).lower()
            source_element = str(row["element"] or "normal").lower()
            source_key = f"{source_part_type}_n_{source_element}"
            target_key = f"{source_part_type}_r_{source_element}"
            db.execute("UPDATE robot_parts SET key = ?, rarity = 'N' WHERE id = ?", (source_key, self.source_part_id))
            db.execute(
                """
                INSERT INTO robot_parts
                    (part_type, key, image_path, rarity, element, series, display_name_ja, offset_x, offset_y, is_active, is_unlocked, created_at)
                VALUES (?, ?, ?, 'R', ?, 'S1', ?, 0, 0, 1, 0, ?)
                ON CONFLICT(key) DO UPDATE SET is_active = 1, rarity = 'R'
                """,
                (
                    str(row["part_type"]),
                    target_key,
                    str(row["image_path"]),
                    str(row["element"] or "NORMAL"),
                    "テストRパーツ",
                    now,
                ),
            )
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
            sess["username"] = "evolve_tester"
        return client

    def test_evolve_success_preserves_plus(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                UPDATE part_instances
                SET plus = 3, rarity = 'N', w_hp = 1234, w_atk = 2234, w_def = 3234, w_spd = 4234, w_acc = 5234, w_cri = 6234
                WHERE id = ? AND user_id = ?
                """,
                (self.part_instance_id, self.user_id),
            )
            core_asset_id = db.execute(
                "SELECT id FROM core_assets WHERE core_key = ?",
                (game_app.EVOLUTION_CORE_KEY,),
            ).fetchone()["id"]
            db.execute(
                "INSERT OR REPLACE INTO user_core_inventory (user_id, core_asset_id, quantity, updated_at) VALUES (?, ?, 1, datetime('now'))",
                (self.user_id, int(core_asset_id)),
            )
            db.commit()

        client = self._client()
        resp = client.post(
            "/parts/evolve",
            data={"part_instance_id": str(self.part_instance_id)},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("進化成功", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            source_row = db.execute(
                "SELECT id FROM part_instances WHERE id = ? AND user_id = ?",
                (self.part_instance_id, self.user_id),
            ).fetchone()
            self.assertIsNone(source_row)
            row = db.execute(
                """
                SELECT rarity, plus, w_hp, w_atk, w_def, w_spd, w_acc, w_cri, part_id
                FROM part_instances
                WHERE user_id = ? AND status = 'inventory' AND UPPER(COALESCE(rarity, 'N')) = 'R'
                ORDER BY id DESC
                LIMIT 1
                """,
                (self.user_id,),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(str(row["rarity"]).upper(), "R")
            self.assertEqual(int(row["plus"]), 3)
            self.assertEqual(int(row["w_hp"]), 1234)
            self.assertEqual(int(row["w_atk"]), 2234)
            self.assertEqual(int(row["w_def"]), 3234)
            self.assertEqual(int(row["w_spd"]), 4234)
            self.assertEqual(int(row["w_acc"]), 5234)
            self.assertEqual(int(row["w_cri"]), 6234)
            core_row = db.execute(
                """
                SELECT uci.quantity
                FROM user_core_inventory uci
                JOIN core_assets ca ON ca.id = uci.core_asset_id
                WHERE uci.user_id = ? AND ca.core_key = ?
                """,
                (self.user_id, game_app.EVOLUTION_CORE_KEY),
            ).fetchone()
            self.assertEqual(int(core_row["quantity"]), 0)
            event = db.execute(
                """
                SELECT event_type, payload_json
                FROM world_events_log
                WHERE user_id = ? AND event_type = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (self.user_id, game_app.AUDIT_EVENT_TYPES["PART_EVOLVE"]),
            ).fetchone()
            self.assertIsNotNone(event)

    def test_evolve_requires_core(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                "UPDATE part_instances SET plus = 2, rarity = 'N' WHERE id = ? AND user_id = ?",
                (self.part_instance_id, self.user_id),
            )
            core_asset_id = db.execute(
                "SELECT id FROM core_assets WHERE core_key = ?",
                (game_app.EVOLUTION_CORE_KEY,),
            ).fetchone()["id"]
            db.execute(
                "INSERT OR REPLACE INTO user_core_inventory (user_id, core_asset_id, quantity, updated_at) VALUES (?, ?, 0, datetime('now'))",
                (self.user_id, int(core_asset_id)),
            )
            db.commit()

        client = self._client()
        resp = client.post(
            "/parts/evolve",
            data={"part_instance_id": str(self.part_instance_id)},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("進化コアが不足", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT rarity, plus FROM part_instances WHERE id = ? AND user_id = ?",
                (self.part_instance_id, self.user_id),
            ).fetchone()
            self.assertEqual(str(row["rarity"]).upper(), "N")
            self.assertEqual(int(row["plus"]), 2)

    def test_evolve_target_missing_shows_error(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE robot_parts SET key = ? WHERE id = ?", ("head_n_unknown", self.source_part_id))
            db.execute("DELETE FROM robot_parts WHERE key = ?", ("head_r_unknown",))
            core_asset_id = db.execute(
                "SELECT id FROM core_assets WHERE core_key = ?",
                (game_app.EVOLUTION_CORE_KEY,),
            ).fetchone()["id"]
            db.execute(
                "INSERT OR REPLACE INTO user_core_inventory (user_id, core_asset_id, quantity, updated_at) VALUES (?, ?, 1, datetime('now'))",
                (self.user_id, int(core_asset_id)),
            )
            db.commit()

        client = self._client()
        resp = client.post(
            "/parts/evolve",
            data={"part_instance_id": str(self.part_instance_id)},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("このパーツは進化できません", resp.get_data(as_text=True))

    def test_evolve_screen_shows_overview_after_unlock(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    now,
                    game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                    '{"area_key":"layer_2","boss_kind":"fixed","unlocked_layer":3}',
                    self.user_id,
                ),
            )
            db.execute("UPDATE users SET evolution_core_progress = 12 WHERE id = ?", (self.user_id,))
            db.commit()

        client = self._client()
        resp = client.get("/parts/evolve")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("今の進化状況", html)
        self.assertIn("進化コア進捗 12/100", html)
        self.assertIn("同じNパーツをRへ進化できます。", html)


if __name__ == "__main__":
    unittest.main()
