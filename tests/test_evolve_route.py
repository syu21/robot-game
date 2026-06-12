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

    def _client_for(self, user_id, username):
        client = game_app.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = int(user_id)
            sess["username"] = username
        return client

    def _grant_evolution_core(self, user_id, qty=1):
        db = game_app.get_db()
        core_asset_id = db.execute(
            "SELECT id FROM core_assets WHERE core_key = ?",
            (game_app.EVOLUTION_CORE_KEY,),
        ).fetchone()["id"]
        db.execute(
            """
            INSERT OR REPLACE INTO user_core_inventory (user_id, core_asset_id, quantity, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (int(user_id), int(core_asset_id), int(qty)),
        )

    def _create_insect_part_instance(self, user_id, part_key="head_kabuto", plus=0):
        db = game_app.get_db()
        part = game_app._get_part_by_key(db, part_key)
        self.assertIsNotNone(part)
        return game_app._create_part_instance_from_master(
            db,
            int(user_id),
            part,
            plus=int(plus),
            status="inventory",
        )

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

    def test_insect_r_evolve_candidates_follow_release_flag(self):
        old_bypass = game_app.app.config.get("BYPASS_RELEASE_GATES_IN_TESTS", True)
        game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = False
        try:
            with game_app.app.app_context():
                db = game_app.get_db()
                db.execute("UPDATE users SET max_unlocked_layer = 3 WHERE id = ?", (self.user_id,))
                self._create_insect_part_instance(self.user_id, "head_kabuto")
                db.commit()

            admin_html = self._client().get("/parts/evolve").get_data(as_text=True)
            self.assertIn("豪角ヘッド", admin_html)
            self.assertNotIn("Rカブトヘッド", admin_html)

            with game_app.app.app_context():
                db = game_app.get_db()
                now = int(time.time())
                db.execute(
                    """
                    INSERT INTO users (username, password_hash, created_at, is_admin, max_unlocked_layer)
                    VALUES (?, ?, ?, 0, 3)
                    """,
                    ("insect_evolve_user", "x", now),
                )
                public_user_id = int(
                    db.execute("SELECT id FROM users WHERE username = ?", ("insect_evolve_user",)).fetchone()["id"]
                )
                game_app.initialize_new_user(db, public_user_id)
                self._create_insect_part_instance(public_user_id, "head_kabuto")
                db.commit()

            user_client = self._client_for(public_user_id, "insect_evolve_user")
            private_html = user_client.get("/parts/evolve").get_data(as_text=True)
            self.assertNotIn("豪角ヘッド", private_html)

            with game_app.app.app_context():
                db = game_app.get_db()
                db.execute(
                    "UPDATE release_flags SET is_public = 1 WHERE key = ?",
                    (game_app.INSECT_R_PARTS_FEATURE_KEY,),
                )
                db.commit()
            public_html = user_client.get("/parts/evolve").get_data(as_text=True)
            self.assertIn("豪角ヘッド", public_html)
            self.assertNotIn("Rカブトヘッド", public_html)
        finally:
            game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = old_bypass

    def test_insect_r_evolve_preserves_plus_weights_and_consumes_core(self):
        old_bypass = game_app.app.config.get("BYPASS_RELEASE_GATES_IN_TESTS", True)
        game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = False
        try:
            with game_app.app.app_context():
                db = game_app.get_db()
                insect_instance_id = self._create_insect_part_instance(self.user_id, "head_kabuto", plus=4)
                db.execute(
                    """
                    UPDATE part_instances
                    SET w_hp = 0.11, w_atk = 0.12, w_def = 0.13, w_spd = 0.14, w_acc = 0.15, w_cri = 0.16
                    WHERE id = ?
                    """,
                    (int(insect_instance_id),),
                )
                self._grant_evolution_core(self.user_id, qty=1)
                db.commit()

            resp = self._client().post(
                "/parts/evolve",
                data={"part_instance_id": str(insect_instance_id)},
                follow_redirects=True,
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIn("進化成功", resp.get_data(as_text=True))
            self.assertIn("豪角ヘッド", resp.get_data(as_text=True))

            with game_app.app.app_context():
                db = game_app.get_db()
                row = db.execute(
                    """
                    SELECT pi.rarity, pi.plus, pi.w_hp, pi.w_atk, pi.w_def, pi.w_spd, pi.w_acc, pi.w_cri,
                           rp.key, rp.frame_type, rp.series
                    FROM part_instances pi
                    JOIN robot_parts rp ON rp.id = pi.part_id
                    WHERE pi.user_id = ? AND UPPER(COALESCE(pi.rarity, 'N')) = 'R'
                      AND rp.key = 'head_r_kabuto'
                    LIMIT 1
                    """,
                    (self.user_id,),
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(str(row["rarity"]).upper(), "R")
                self.assertEqual(int(row["plus"]), 4)
                self.assertEqual(str(row["frame_type"]), "insect")
                self.assertEqual(str(row["series"]), "insect_kabuto")
                for key, expected in {
                    "w_hp": 0.11,
                    "w_atk": 0.12,
                    "w_def": 0.13,
                    "w_spd": 0.14,
                    "w_acc": 0.15,
                    "w_cri": 0.16,
                }.items():
                    self.assertAlmostEqual(float(row[key]), expected)
                core_qty = game_app._get_player_core_qty(db, self.user_id, game_app.EVOLUTION_CORE_KEY)
                self.assertEqual(core_qty, 0)
        finally:
            game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = old_bypass

    def test_evolve_plus_five_stays_plus_five_and_hits_strengthen_cap(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET max_unlocked_layer = 3 WHERE id = ?", (self.user_id,))
            db.execute(
                "UPDATE part_instances SET plus = 5, rarity = 'N' WHERE id = ? AND user_id = ?",
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
        self.assertIn("+5", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            evolved = db.execute(
                """
                SELECT id, rarity, plus
                FROM part_instances
                WHERE user_id = ? AND status = 'inventory' AND UPPER(COALESCE(rarity, 'N')) = 'R'
                ORDER BY id DESC
                LIMIT 1
                """,
                (self.user_id,),
            ).fetchone()
            self.assertIsNotNone(evolved)
            self.assertEqual(int(evolved["plus"]), 5)
            with game_app.app.test_request_context():
                result = game_app._strengthen_parts_selected(db, self.user_id, int(evolved["id"]))
            self.assertFalse(result["ok"])
            self.assertIn("最大強化", result["message"])

    def test_evolved_r_plus_five_is_strengthen_candidate_after_layer4(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET max_unlocked_layer = 4, coins = 999 WHERE id = ?", (self.user_id,))
            db.execute(
                "UPDATE part_instances SET plus = 5, rarity = 'N' WHERE id = ? AND user_id = ?",
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

        with game_app.app.app_context():
            db = game_app.get_db()
            evolved = db.execute(
                """
                SELECT id, part_id, part_type, rarity, element, series, plus
                FROM part_instances
                WHERE user_id = ? AND status = 'inventory' AND UPPER(COALESCE(rarity, 'N')) = 'R'
                ORDER BY id DESC
                LIMIT 1
                """,
                (self.user_id,),
            ).fetchone()
            self.assertIsNotNone(evolved)
            for offset in (1, 2):
                db.execute(
                    """
                    INSERT INTO part_instances
                    (part_id, user_id, part_type, rarity, element, series, plus, w_hp, w_atk, w_def, w_spd, w_acc, w_cri, status, created_at, updated_at)
                    VALUES (?, ?, ?, 'R', ?, ?, 0, 1, 1, 1, 1, 1, 1, 'inventory', ?, datetime('now'))
                    """,
                    (
                        int(evolved["part_id"]),
                        int(self.user_id),
                        evolved["part_type"],
                        evolved["element"],
                        evolved["series"],
                        int(time.time()) + offset,
                    ),
                )
            db.commit()

        page = client.get("/parts/strengthen?rarity=R&plus=5")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn(f'value="{int(evolved["id"])}"', html)
        self.assertIn("+5 → +6", html)

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

    def test_evolve_equipped_part_refreshes_robot_render(self):
        slot_map = (
            ("head_part_instance_id", "head_key"),
            ("r_arm_part_instance_id", "r_arm_key"),
            ("l_arm_part_instance_id", "l_arm_key"),
            ("legs_part_instance_id", "legs_key"),
        )
        with game_app.app.app_context():
            db = game_app.get_db()
            active_robot_id = int(
                db.execute("SELECT active_robot_id FROM users WHERE id = ?", (self.user_id,)).fetchone()["active_robot_id"]
            )
            equipped_parts = db.execute(
                "SELECT * FROM robot_instance_parts WHERE robot_instance_id = ?",
                (active_robot_id,),
            ).fetchone()
            self.assertIsNotNone(equipped_parts)

            chosen = None
            for instance_col, key_col in slot_map:
                candidate_id = int(equipped_parts[instance_col] or 0)
                if candidate_id <= 0:
                    continue
                candidate_row = db.execute(
                    """
                    SELECT
                        pi.id, pi.part_id, pi.status, pi.plus, pi.w_hp, pi.w_atk, pi.w_def, pi.w_spd, pi.w_acc, pi.w_cri,
                        rp.part_type, rp.element, rp.image_path
                    FROM part_instances pi
                    JOIN robot_parts rp ON rp.id = pi.part_id
                    WHERE pi.id = ? AND pi.user_id = ?
                    LIMIT 1
                    """,
                    (candidate_id, self.user_id),
                ).fetchone()
                if candidate_row:
                    chosen = (candidate_row, key_col)
                    break
            self.assertIsNotNone(chosen)
            part_row, slot_key_col = chosen
            source_key = f"{str(part_row['part_type']).lower()}_n_{str(part_row['element'] or 'normal').lower()}"
            target_key = f"{str(part_row['part_type']).lower()}_r_{str(part_row['element'] or 'normal').lower()}"
            db.execute("UPDATE robot_parts SET key = ?, rarity = 'N' WHERE id = ?", (source_key, int(part_row["part_id"])))
            db.execute(
                """
                INSERT INTO robot_parts
                    (part_type, key, image_path, rarity, element, series, display_name_ja, offset_x, offset_y, is_active, is_unlocked, created_at)
                VALUES (?, ?, ?, 'R', ?, 'S1', ?, 0, 0, 1, 0, ?)
                ON CONFLICT(key) DO UPDATE SET is_active = 1, rarity = 'R'
                """,
                (
                    str(part_row["part_type"]),
                    target_key,
                    str(part_row["image_path"]),
                    str(part_row["element"] or "NORMAL"),
                    "装備進化テストR",
                    int(time.time()),
                ),
            )
            db.execute(
                """
                UPDATE part_instances
                SET plus = 4, rarity = 'N', w_hp = 1111, w_atk = 2111, w_def = 3111, w_spd = 4111, w_acc = 5111, w_cri = 6111
                WHERE id = ? AND user_id = ?
                """,
                (int(part_row["id"]), self.user_id),
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
            data={"part_instance_id": str(int(part_row["id"]))},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("進化成功", resp.get_data(as_text=True))

        with game_app.app.app_context():
            db = game_app.get_db()
            evolved_row = db.execute(
                """
                SELECT id, part_id, rarity, status, plus, w_hp, w_atk, w_def, w_spd, w_acc, w_cri
                FROM part_instances
                WHERE id = ? AND user_id = ?
                """,
                (int(part_row["id"]), self.user_id),
            ).fetchone()
            self.assertIsNotNone(evolved_row)
            self.assertEqual(str(evolved_row["rarity"]).upper(), "R")
            self.assertEqual(str(evolved_row["status"]).lower(), "equipped")
            self.assertEqual(int(evolved_row["plus"]), 4)
            self.assertEqual(int(evolved_row["w_hp"]), 1111)
            self.assertEqual(int(evolved_row["w_atk"]), 2111)
            self.assertEqual(int(evolved_row["w_def"]), 3111)
            self.assertEqual(int(evolved_row["w_spd"]), 4111)
            self.assertEqual(int(evolved_row["w_acc"]), 5111)
            self.assertEqual(int(evolved_row["w_cri"]), 6111)

            parts_row = db.execute(
                "SELECT * FROM robot_instance_parts WHERE robot_instance_id = ?",
                (active_robot_id,),
            ).fetchone()
            self.assertEqual(parts_row[slot_key_col], target_key)

            robot_row = db.execute(
                "SELECT composed_image_path, icon_32_path FROM robot_instances WHERE id = ?",
                (active_robot_id,),
            ).fetchone()
            self.assertTrue(robot_row["composed_image_path"])
            self.assertTrue(robot_row["icon_32_path"])
            self.assertTrue(
                os.path.exists(os.path.join(game_app.BASE_DIR, "static", robot_row["composed_image_path"]))
            )
            self.assertTrue(
                os.path.exists(os.path.join(game_app.BASE_DIR, "static", robot_row["icon_32_path"]))
            )

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
        self.assertIn("Nパーツを、対応するRパーツへ進化できます。", html)


if __name__ == "__main__":
    unittest.main()
