import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class PartsUiTests(unittest.TestCase):
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
                VALUES (?, ?, ?, 1, 0, 1)
                """,
                ("parts_ui_tester", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("parts_ui_tester",),
            ).fetchone()["id"]
            game_app.initialize_new_user(db, self.user_id)
            self.starter_rows = {}
            for part_type in ("HEAD", "RIGHT_ARM", "LEFT_ARM", "LEGS"):
                row = db.execute(
                    """
                    SELECT *
                    FROM robot_parts
                    WHERE part_type = ? AND is_active = 1
                    ORDER BY id ASC
                    LIMIT 1
                    """,
                    (part_type,),
                ).fetchone()
                self.starter_rows[part_type] = row
            self.head_name = game_app._part_display_name_ja(self.starter_rows["HEAD"])
            self.right_arm_name = game_app._part_display_name_ja(self.starter_rows["RIGHT_ARM"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "parts_ui_tester"
        return client

    def _unlock_evolution(self):
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
            game_app._grant_player_core(db, self.user_id, game_app.EVOLUTION_CORE_KEY, qty=1)
            db.commit()

    def _create_extra_instance(self, part_row, *, plus=0, status="inventory"):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app._create_part_instance_from_master(db, self.user_id, part_row, plus=plus, status=status)
            db.commit()

    def _create_custom_part(self, part_type, key, name, *, rarity="N"):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            image_path = self.starter_rows[part_type]["image_path"]
            part_type_norm = game_app._norm_part_type(part_type)
            db.execute(
                """
                INSERT INTO robot_parts
                (part_type, key, image_path, rarity, element, series, display_name_ja, offset_x, offset_y, is_active, created_at)
                VALUES (?, ?, ?, ?, 'NORMAL', 'TST', ?, 0, 0, 1, ?)
                """,
                (part_type_norm, key, image_path, rarity, name, now),
            )
            row = db.execute("SELECT * FROM robot_parts WHERE key = ?", (key,)).fetchone()
            db.commit()
            return row

    def _seed_evolvable_pair(self, part_type, key_prefix, name_prefix):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            image_path = self.starter_rows[part_type]["image_path"]
            part_type_norm = game_app._norm_part_type(part_type)
            n_key = f"{key_prefix}_n_proto"
            r_key = f"{key_prefix}_r_proto"
            db.execute(
                """
                INSERT INTO robot_parts
                (part_type, key, image_path, rarity, element, series, display_name_ja, offset_x, offset_y, is_active, created_at)
                VALUES (?, ?, ?, 'N', 'NORMAL', 'TST', ?, 0, 0, 1, ?)
                """,
                (part_type_norm, n_key, image_path, f"{name_prefix}試作", now),
            )
            db.execute(
                """
                INSERT INTO robot_parts
                (part_type, key, image_path, rarity, element, series, display_name_ja, offset_x, offset_y, is_active, created_at)
                VALUES (?, ?, ?, 'R', 'NORMAL', 'TST', ?, 0, 0, 1, ?)
                """,
                (part_type_norm, r_key, image_path, f"{name_prefix}改試作", now),
            )
            row = db.execute("SELECT * FROM robot_parts WHERE key = ?", (n_key,)).fetchone()
            db.commit()
            return row

    def test_parts_inventory_comparison_filter_and_safe_pagination(self):
        client = self._client()
        resp = client.get("/parts?part_type=HEAD")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("所持パーツ", html)
        self.assertIn("すべて", html)
        self.assertIn("頭", html)
        self.assertIn("右腕", html)
        self.assertIn("脚", html)
        self.assertIn(self.head_name, html)
        self.assertNotIn(self.right_arm_name, html)
        self.assertIn("装備中", html)
        self.assertIn("強化素材に使える", html)
        self.assertIn("選んだパーツを見比べる", html)
        self.assertIn("選択した所持パーツを破棄", html)
        self.assertIn(">選択<", html)
        for label in ("耐久", "攻撃", "防御", "素早さ", "命中", "会心"):
            self.assertIn(label, html)
        self.assertIn("次のページはありません", html)
        self.assertNotIn("旧在庫", html)

    def test_parts_compare_focus_shows_only_selected_cards(self):
        compare_part = self._create_custom_part("HEAD", "compare_head_proto", "比較ヘッド")
        self._create_extra_instance(compare_part, plus=3, status="inventory")
        with game_app.app.app_context():
            db = game_app.get_db()
            equipped_id = db.execute(
                """
                SELECT pi.id
                FROM part_instances pi
                JOIN robot_parts rp ON rp.id = pi.part_id
                WHERE pi.user_id = ? AND pi.status = 'equipped' AND rp.part_type = 'HEAD'
                ORDER BY pi.id ASC
                LIMIT 1
                """,
                (self.user_id,),
            ).fetchone()["id"]
            compare_id = db.execute(
                """
                SELECT pi.id
                FROM part_instances pi
                JOIN robot_parts rp ON rp.id = pi.part_id
                WHERE pi.user_id = ? AND pi.status = 'inventory' AND rp.key = ?
                ORDER BY pi.id DESC
                LIMIT 1
                """,
                (self.user_id, "compare_head_proto"),
            ).fetchone()["id"]

        client = self._client()
        resp = client.post(
            "/parts/compare",
            data={"instance_ids": [str(equipped_id), str(compare_id)], "part_type": "HEAD"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("選んだパーツを見比べる", html)
        self.assertIn("比較ヘッド", html)
        self.assertIn(self.head_name, html)
        self.assertIn("見比べを閉じる", html)

    def test_parts_page_shows_storage_separately_and_excludes_it_from_usable_candidates(self):
        overflow_part = self._create_custom_part("HEAD", "overflow_head_proto", "保管試作ヘッド")
        self._create_extra_instance(overflow_part, plus=2, status="overflow")
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                INSERT INTO user_parts_inventory (user_id, part_type, part_key, obtained_at, source)
                VALUES (?, ?, ?, ?, ?)
                """,
                (self.user_id, "HEAD", self.starter_rows["HEAD"]["key"], int(time.time()), "legacy_test"),
            )
            db.commit()

        client = self._client()
        resp = client.get("/parts?part_type=HEAD")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("保管中 2", html)
        self.assertIn("保管中の個体パーツ", html)
        self.assertIn("保管試作ヘッド", html)
        self.assertIn("選択した保管個体を所持へ戻す", html)
        self.assertIn("所持枠がいっぱいだったため自動で保管に回った個体です。", html)

        strengthen_html = client.get("/parts/strengthen?part_type=HEAD").get_data(as_text=True)
        build_html = client.get("/build").get_data(as_text=True)
        self.assertNotIn("保管試作ヘッド", strengthen_html)
        self.assertNotIn("保管試作ヘッド", build_html)

    def test_parts_restore_moves_selected_overflow_items_back_to_inventory(self):
        overflow_part = self._create_custom_part("HEAD", "restore_head_proto", "復帰ヘッド")
        self._create_extra_instance(overflow_part, plus=1, status="overflow")
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET part_inventory_limit = 5 WHERE id = ?", (self.user_id,))
            overflow_id = db.execute(
                "SELECT id FROM part_instances WHERE user_id = ? AND status = 'overflow' ORDER BY id DESC LIMIT 1",
                (self.user_id,),
            ).fetchone()["id"]
            db.commit()

        client = self._client()
        resp = client.post(
            "/parts/restore",
            data={"overflow_instance_ids": str(overflow_id), "part_type": "HEAD"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/parts?part_type=HEAD", resp.headers.get("Location", ""))
        with game_app.app.app_context():
            db = game_app.get_db()
            status = db.execute("SELECT status FROM part_instances WHERE id = ?", (overflow_id,)).fetchone()["status"]
            self.assertEqual(str(status), "inventory")

    def test_parts_restore_shows_reason_when_inventory_is_full(self):
        overflow_part = self._create_custom_part("HEAD", "restore_blocked_proto", "満杯ヘッド")
        self._create_extra_instance(overflow_part, plus=1, status="overflow")
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET part_inventory_limit = 4 WHERE id = ?", (self.user_id,))
            overflow_id = db.execute(
                "SELECT id FROM part_instances WHERE user_id = ? AND status = 'overflow' ORDER BY id DESC LIMIT 1",
                (self.user_id,),
            ).fetchone()["id"]
            db.commit()

        client = self._client()
        get_resp = client.get("/parts?part_type=HEAD")
        self.assertEqual(get_resp.status_code, 200)
        self.assertIn("今は所持枠がいっぱいです。先に所持中パーツを破棄すると戻せます。", get_resp.get_data(as_text=True))
        post_resp = client.post(
            "/parts/restore",
            data={"overflow_instance_ids": str(overflow_id), "part_type": "HEAD"},
            follow_redirects=False,
        )
        self.assertEqual(post_resp.status_code, 302)
        self.assertIn("/parts?part_type=HEAD", post_resp.headers.get("Location", ""))
        with game_app.app.app_context():
            db = game_app.get_db()
            status = db.execute("SELECT status FROM part_instances WHERE id = ?", (overflow_id,)).fetchone()["status"]
            self.assertEqual(str(status), "overflow")

    def test_parts_discard_keeps_equipped_items_even_if_selected(self):
        discard_part = self._create_custom_part("HEAD", "discard_head_proto", "破棄ヘッド")
        self._create_extra_instance(discard_part, plus=0, status="inventory")
        with game_app.app.app_context():
            db = game_app.get_db()
            equipped_id = db.execute(
                """
                SELECT pi.id
                FROM part_instances pi
                JOIN robot_parts rp ON rp.id = pi.part_id
                WHERE pi.user_id = ? AND pi.status = 'equipped' AND rp.part_type = 'HEAD'
                ORDER BY pi.id ASC
                LIMIT 1
                """,
                (self.user_id,),
            ).fetchone()["id"]
            inventory_id = db.execute(
                """
                SELECT pi.id
                FROM part_instances pi
                JOIN robot_parts rp ON rp.id = pi.part_id
                WHERE pi.user_id = ? AND pi.status = 'inventory' AND rp.key = ?
                ORDER BY pi.id DESC
                LIMIT 1
                """,
                (self.user_id, "discard_head_proto"),
            ).fetchone()["id"]

        client = self._client()
        resp = client.post(
            "/parts/discard",
            data={"instance_ids": [str(equipped_id), str(inventory_id)], "confirm": "yes", "part_type": "HEAD"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            equipped_status = db.execute("SELECT status FROM part_instances WHERE id = ?", (equipped_id,)).fetchone()["status"]
            removed_row = db.execute("SELECT id FROM part_instances WHERE id = ?", (inventory_id,)).fetchone()
            self.assertEqual(str(equipped_status), "equipped")
            self.assertIsNone(removed_row)

    def test_battle_drop_over_capacity_goes_to_overflow(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("DELETE FROM part_instances WHERE user_id = ? AND status = 'inventory'", (self.user_id,))
            db.execute("UPDATE users SET part_inventory_limit = 0 WHERE id = ?", (self.user_id,))
            dropped = game_app._add_part_drop(
                db,
                self.user_id,
                source="battle_drop",
                rarity="N",
                plus=2,
                as_instance=True,
            )
            db.commit()
            self.assertIsNotNone(dropped)
            self.assertEqual(dropped["storage_status"], "overflow")
            self.assertEqual(game_app._count_part_inventory(db, self.user_id), 0)
            self.assertEqual(game_app._count_part_overflow(db, self.user_id), 1)

    def test_legacy_materialization_respects_capacity_and_uses_overflow(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("DELETE FROM part_instances WHERE user_id = ? AND status = 'inventory'", (self.user_id,))
            db.execute("UPDATE users SET part_inventory_limit = 0 WHERE id = ?", (self.user_id,))
            db.execute(
                """
                INSERT INTO user_parts_inventory (user_id, part_type, part_key, obtained_at, source)
                VALUES (?, ?, ?, ?, ?)
                """,
                (self.user_id, "HEAD", self.starter_rows["HEAD"]["key"], int(time.time()), "legacy_materialize"),
            )
            part_instance_id = game_app._take_or_materialize_part_instance(
                db,
                self.user_id,
                self.starter_rows["HEAD"]["key"],
            )
            row = db.execute("SELECT status FROM part_instances WHERE id = ?", (part_instance_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(str(row["status"]), "overflow")
            self.assertEqual(game_app._count_part_inventory(db, self.user_id), 0)
            self.assertEqual(game_app._count_part_legacy_storage(db, self.user_id), 0)

    def test_strengthen_page_shows_compare_cards_and_legacy_route_still_works(self):
        self._create_extra_instance(self.starter_rows["HEAD"], plus=0)
        self._create_extra_instance(self.starter_rows["HEAD"], plus=1)

        client = self._client()
        resp = client.get("/parts/strengthen?part_type=HEAD")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("パーツ強化", html)
        self.assertIn(self.head_name, html)
        self.assertNotIn(self.right_arm_name, html)
        self.assertIn("素材として使う2個", html)
        self.assertIn("装備中", html)
        self.assertIn("→", html)
        self.assertIn("選んだ個体を強化する", html)

        legacy_resp = client.get("/parts/fuse?part_type=HEAD")
        self.assertEqual(legacy_resp.status_code, 200)
        self.assertIn("パーツ強化", legacy_resp.get_data(as_text=True))

    def test_evolve_page_shows_before_after_compare_and_part_filter(self):
        self._unlock_evolution()
        head_part = self._seed_evolvable_pair("HEAD", "test_head", "試作ヘッド")
        right_arm_part = self._seed_evolvable_pair("RIGHT_ARM", "test_arm", "試作アーム")
        self._create_extra_instance(head_part, plus=1)
        self._create_extra_instance(right_arm_part, plus=0)
        head_name = game_app._part_display_name_ja(head_part)
        right_arm_name = game_app._part_display_name_ja(right_arm_part)

        client = self._client()
        resp = client.get("/parts/evolve?part_type=HEAD")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("進化合成", html)
        self.assertIn(head_name, html)
        self.assertNotIn(right_arm_name, html)
        self.assertIn("強化値と個体性能はそのまま引き継がれます。", html)
        self.assertIn("進化するとこう変わる", html)
        self.assertIn("進化 →", html)
        for label in ("耐久", "攻撃", "防御", "素早さ", "命中", "会心"):
            self.assertIn(label, html)

    def test_build_picker_shows_total_and_stats_for_each_part_option(self):
        client = self._client()
        resp = client.get("/build")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("ロボ編成", html)
        self.assertIn("HEAD（頭）", html)
        self.assertIn("RIGHT_ARM（右腕）", html)
        self.assertIn("総合値", html)
        for label in ("耐久", "攻撃", "防御", "素早さ", "命中", "会心"):
            self.assertIn(label, html)


if __name__ == "__main__":
    unittest.main()
