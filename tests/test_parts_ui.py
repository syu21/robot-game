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

    def _create_custom_part(self, part_type, key, name, *, rarity="N", frame_type="normal"):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            image_path = self.starter_rows[part_type]["image_path"]
            part_type_norm = game_app._norm_part_type(part_type)
            db.execute(
                """
                INSERT INTO robot_parts
                (part_type, key, image_path, rarity, element, series, frame_type, display_name_ja, offset_x, offset_y, is_active, created_at)
                VALUES (?, ?, ?, ?, 'NORMAL', 'TST', ?, ?, 0, 0, 1, ?)
                """,
                (part_type_norm, key, image_path, rarity, frame_type, name, now),
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
        self.assertIn("廃品市場", html)
        self.assertIn("完全削除はコインにならず元に戻せません", html)
        self.assertIn("完全削除（コインなし）", html)
        self.assertIn("選んだパーツを見比べる", html)
        self.assertNotIn("選択した所持パーツを破棄", html)
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

    def test_parts_page_hides_legacy_storage_and_excludes_it_from_usable_candidates(self):
        overflow_part = self._create_custom_part("HEAD", "overflow_head_proto", "旧保管試作ヘッド")
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
        self.assertNotIn("旧保管試作ヘッド", html)
        self.assertNotIn("保管中の個体パーツ", html)
        self.assertNotIn("所持へ戻す", html)
        self.assertIn("所持上限を超えた新規戦利品は自動売却されます。", html)

        strengthen_html = client.get("/parts/strengthen?part_type=HEAD").get_data(as_text=True)
        build_html = client.get("/build").get_data(as_text=True)
        self.assertNotIn("旧保管試作ヘッド", strengthen_html)
        self.assertNotIn("旧保管試作ヘッド", build_html)

    def test_strengthen_page_no_longer_surfaces_storage_blocked_groups(self):
        blocked_part = self._create_custom_part("HEAD", "blocked_strengthen_head", "旧保管強化ヘッド")
        self._create_extra_instance(blocked_part, plus=0, status="inventory")
        self._create_extra_instance(blocked_part, plus=0, status="overflow")
        self._create_extra_instance(blocked_part, plus=1, status="overflow")

        client = self._client()
        resp = client.get("/parts/strengthen?part_type=HEAD")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertNotIn("保管中の個体があるため", html)
        self.assertNotIn("旧保管強化ヘッド", html)
        self.assertIn("#part-storage", html)

    def test_parts_restore_route_is_legacy_noop(self):
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
            self.assertEqual(str(status), "overflow")

    def test_parts_restore_redirects_without_reactivating_overflow_when_inventory_is_full(self):
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
        self.assertNotIn("所持へ戻す", get_resp.get_data(as_text=True))
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

    def test_parts_locked_card_shows_clear_state_and_discard_keeps_it(self):
        locked_part = self._create_custom_part("HEAD", "locked_head_proto", "保護ヘッド")
        self._create_extra_instance(locked_part, plus=0, status="inventory")
        with game_app.app.app_context():
            db = game_app.get_db()
            locked_id = db.execute(
                """
                SELECT pi.id
                FROM part_instances pi
                JOIN robot_parts rp ON rp.id = pi.part_id
                WHERE pi.user_id = ? AND rp.key = ?
                ORDER BY pi.id DESC
                LIMIT 1
                """,
                (self.user_id, "locked_head_proto"),
            ).fetchone()["id"]
            db.execute("UPDATE part_instances SET locked = 1 WHERE id = ?", (locked_id,))
            db.commit()

        client = self._client()
        page = client.get("/parts?part_type=HEAD")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("part-lock-badge", html)
        self.assertIn("保護中", html)
        self.assertIn("保護解除", html)
        self.assertIn("btn-unlock", html)
        self.assertIn("保護中：素材・売却・処分に使えません", html)
        self.assertEqual(html.count("保護中：素材・売却・処分に使えません"), 2)
        self.assertIn("注目能力は、この個体で高く出やすい能力です。", html)

        resp = client.post(
            "/parts/discard",
            data={"instance_ids": [str(locked_id)], "confirm": "yes", "part_type": "HEAD"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT locked, status FROM part_instances WHERE id = ?", (locked_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(int(row["locked"]), 1)
            self.assertEqual(str(row["status"]), "inventory")

    def test_parts_discard_requires_confirm_and_keeps_filters(self):
        discard_part = self._create_custom_part("HEAD", "confirm_discard_head", "確認削除ヘッド", frame_type="insect")
        self._create_extra_instance(discard_part, plus=0, status="inventory")
        with game_app.app.app_context():
            db = game_app.get_db()
            part_id = int(
                db.execute(
                    """
                    SELECT pi.id
                    FROM part_instances pi
                    JOIN robot_parts rp ON rp.id = pi.part_id
                    WHERE pi.user_id = ? AND rp.key = ?
                    ORDER BY pi.id DESC
                    LIMIT 1
                    """,
                    (self.user_id, "confirm_discard_head"),
                ).fetchone()["id"]
            )

        client = self._client()
        resp = client.post(
            "/parts/discard",
            data={"instance_ids": [str(part_id)], "part_type": "HEAD", "frame_type": "insect", "sort": "part_type", "page": "2"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        location = resp.headers.get("Location", "")
        self.assertIn("part_type=HEAD", location)
        self.assertIn("frame_type=insect", location)
        self.assertIn("sort=part_type", location)
        self.assertIn("page=2", location)
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT id FROM part_instances WHERE id = ?", (part_id,)).fetchone()
            self.assertIsNotNone(row)

    def test_part_lock_redirect_keeps_frame_type_filter(self):
        insect_part = self._create_custom_part("HEAD", "lock_insect_head_proto", "保護虫ヘッド", frame_type="insect")
        self._create_extra_instance(insect_part, plus=0, status="inventory")
        with game_app.app.app_context():
            db = game_app.get_db()
            part_id = int(
                db.execute(
                    """
                    SELECT pi.id
                    FROM part_instances pi
                    JOIN robot_parts rp ON rp.id = pi.part_id
                    WHERE pi.user_id = ? AND rp.key = ?
                    ORDER BY pi.id DESC
                    LIMIT 1
                    """,
                    (self.user_id, "lock_insect_head_proto"),
                ).fetchone()["id"]
            )

        client = self._client()
        resp = client.post(
            f"/parts/{part_id}/lock",
            data={"part_type": "HEAD", "frame_type": "insect", "sort": "plus", "page": "2"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        location = resp.headers.get("Location", "")
        self.assertIn("/parts?", location)
        self.assertIn("part_type=HEAD", location)
        self.assertIn("frame_type=insect", location)
        self.assertIn("sort=plus", location)
        self.assertIn("page=2", location)
        self.assertIn(f"#part-{part_id}", location)

    def test_parts_sort_orders_by_plus_and_keeps_sort_in_pagination_and_forms(self):
        strong_head = self._create_custom_part("HEAD", "sort_head_strong", "高強化ヘッド")
        weak_head = self._create_custom_part("HEAD", "sort_head_weak", "低強化ヘッド")
        self._create_extra_instance(strong_head, plus=5, status="inventory")
        self._create_extra_instance(weak_head, plus=1, status="inventory")
        for _ in range(26):
            self._create_extra_instance(weak_head, plus=0, status="inventory")

        client = self._client()
        first_page = client.get("/parts?part_type=HEAD&sort=plus")
        self.assertEqual(first_page.status_code, 200)
        first_html = first_page.get_data(as_text=True)
        self.assertIn("並び替え", first_html)
        self.assertIn("高強化ヘッド", first_html)
        self.assertIn("低強化ヘッド", first_html)
        self.assertLess(first_html.index("高強化ヘッド"), first_html.index("低強化ヘッド"))

        second_page = client.get("/parts?part_type=HEAD&sort=plus&page=2")
        self.assertEqual(second_page.status_code, 200)
        second_html = second_page.get_data(as_text=True)
        self.assertIn("/parts?page=1&amp;part_type=HEAD&amp;sort=plus", second_html)
        self.assertIn('name="sort" value="plus"', second_html)

    def test_parts_type_sort_groups_same_part_instances(self):
        alpha = self._create_custom_part("HEAD", "aa_group_head_proto", "まとまりヘッド")
        beta = self._create_custom_part("HEAD", "zz_group_head_proto", "別ヘッド")
        self._create_extra_instance(alpha, plus=0, status="inventory")
        self._create_extra_instance(beta, plus=5, status="inventory")
        self._create_extra_instance(alpha, plus=2, status="inventory")

        client = self._client()
        resp = client.get("/parts?part_type=HEAD&sort=part_type")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("部位・種類順", html)
        first_alpha = html.index("まとまりヘッド")
        second_alpha = html.index("まとまりヘッド", first_alpha + 1)
        beta_pos = html.index("別ヘッド")
        self.assertLess(second_alpha, beta_pos)

    def test_battle_drop_over_capacity_auto_sells_part(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("DELETE FROM part_instances WHERE user_id = ? AND status = 'inventory'", (self.user_id,))
            db.execute("UPDATE users SET part_inventory_limit = 0 WHERE id = ?", (self.user_id,))
            coins_before = int(db.execute("SELECT coins FROM users WHERE id = ?", (self.user_id,)).fetchone()["coins"] or 0)
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
            self.assertEqual(dropped["storage_status"], "sold")
            self.assertTrue(dropped["auto_sold"])
            self.assertEqual(dropped["auto_sell_price"], game_app.AUTO_SELL_PRICE_BY_RARITY["N"])
            self.assertEqual(game_app._count_part_inventory(db, self.user_id), 0)
            sold_count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM part_instances WHERE user_id = ? AND status = 'sold'",
                    (self.user_id,),
                ).fetchone()["c"]
            )
            coins_after = int(db.execute("SELECT coins FROM users WHERE id = ?", (self.user_id,)).fetchone()["coins"] or 0)
            audit = db.execute(
                "SELECT id FROM world_events_log WHERE user_id = ? AND event_type = ? LIMIT 1",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["PART_AUTO_SELL"]),
            ).fetchone()
            self.assertEqual(sold_count, 1)
            self.assertEqual(coins_after, coins_before + game_app.AUTO_SELL_PRICE_BY_RARITY["N"])
            self.assertIsNotNone(audit)

    def test_battle_reward_front_keeps_part_instance_id_and_lock_button_rules(self):
        with game_app.app.app_context():
            inventory_front = game_app._build_battle_reward_front(
                reward_coin=1,
                reward_core=0,
                dropped_core_name=None,
                drop_items=[
                    {
                        "part_instance_id": 123,
                        "part_key": "test_part",
                        "part_display_name": "テストパーツ",
                        "plus": 0,
                        "storage_status": "inventory",
                        "auto_sold": False,
                        "image_url": "/static/test.png",
                    }
                ],
            )
            sold_front = game_app._build_battle_reward_front(
                reward_coin=1,
                reward_core=0,
                dropped_core_name=None,
                drop_items=[
                    {
                        "part_instance_id": 456,
                        "part_key": "sold_part",
                        "part_display_name": "売却パーツ",
                        "plus": 0,
                        "storage_status": "sold",
                        "auto_sold": True,
                        "auto_sell_price": 3,
                        "image_url": "/static/test.png",
                    }
                ],
            )
            self.assertEqual(inventory_front["part_rows"][0]["part_instance_id"], 123)
            self.assertEqual(inventory_front["part_rows"][0]["storage_status"], "inventory")
            self.assertTrue(sold_front["part_rows"][0]["auto_sold"])

            base_summary = {
                "enemy_name": "敵",
                "outcome": "勝利",
                "outcome_is_win": True,
                "reward_coin": 1,
                "reward_front": inventory_front,
                "highlight_core_drop": False,
            }
            with game_app.app.test_request_context("/explore"):
                html = game_app.render_template(
                    "battle.html",
                    summary=base_summary,
                    state={},
                    active_robot={"name": "R", "image_url": ""},
                    explore_mode=True,
                    explore_area_key="layer_1",
                    message=None,
                    ui_effects_enabled=False,
                    battle_ritual_overlay_enabled=False,
                    battle_short_replay_enabled=False,
                )
            self.assertIn("part_instance_id", str(inventory_front["part_rows"][0]))
            self.assertIn("保護する", html)
            self.assertIn("/parts/123/lock", html)

            base_summary["reward_front"] = sold_front
            with game_app.app.test_request_context("/explore"):
                sold_html = game_app.render_template(
                    "battle.html",
                    summary=base_summary,
                    state={},
                    active_robot={"name": "R", "image_url": ""},
                    explore_mode=True,
                    explore_area_key="layer_1",
                    message=None,
                    ui_effects_enabled=False,
                    battle_ritual_overlay_enabled=False,
                    battle_short_replay_enabled=False,
                )
            self.assertNotIn("/parts/456/lock", sold_html)
            self.assertNotIn("保護する</button>", sold_html)

    def test_legacy_materialization_respects_capacity_and_does_not_create_overflow(self):
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
            self.assertIsNone(part_instance_id)
            self.assertEqual(game_app._count_part_inventory(db, self.user_id), 0)
            self.assertEqual(game_app._count_part_legacy_storage(db, self.user_id), 1)

    def test_strengthen_page_shows_compare_cards_and_legacy_route_still_works(self):
        self._create_extra_instance(self.starter_rows["HEAD"], plus=0)
        self._create_extra_instance(self.starter_rows["HEAD"], plus=1)

        client = self._client()
        resp = client.get("/parts/strengthen?part_type=HEAD")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("パーツ強化", html)
        self.assertIn("注目能力は、この個体で高く出やすい能力です。", html)
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

    def test_evolve_keeps_weight_tendency(self):
        self._unlock_evolution()
        head_part = self._seed_evolvable_pair("HEAD", "weight_head", "傾向ヘッド")
        self._create_extra_instance(head_part, plus=1)
        with game_app.app.app_context():
            db = game_app.get_db()
            source = db.execute(
                """
                SELECT pi.*
                FROM part_instances pi
                JOIN robot_parts rp ON rp.id = pi.part_id
                WHERE pi.user_id = ? AND rp.key = ?
                ORDER BY pi.id DESC
                LIMIT 1
                """,
                (self.user_id, "weight_head_n_proto"),
            ).fetchone()
            source_id = int(source["id"])
            before_weights = tuple(float(source[f"w_{key}"]) for key in game_app.PART_STAT_KEYS)

        client = self._client()
        resp = client.post("/parts/evolve", data={"part_instance_id": str(source_id)}, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            evolved = db.execute(
                """
                SELECT pi.*
                FROM part_instances pi
                JOIN robot_parts rp ON rp.id = pi.part_id
                WHERE pi.user_id = ? AND rp.key = ?
                ORDER BY pi.id DESC
                LIMIT 1
                """,
                (self.user_id, "weight_head_r_proto"),
            ).fetchone()
            self.assertIsNotNone(evolved)
            after_weights = tuple(float(evolved[f"w_{key}"]) for key in game_app.PART_STAT_KEYS)
            self.assertEqual(after_weights, before_weights)

    def test_build_picker_shows_total_and_stats_for_each_part_option(self):
        client = self._client()
        resp = client.get("/build")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("ロボを組み立てる", html)
        self.assertIn("HEAD（頭）", html)
        self.assertIn("RIGHT_ARM（右腕）", html)
        self.assertIn("現在装備", html)
        self.assertIn("総合差分", html)
        self.assertIn("詳細を開く", html)
        self.assertIn("注目能力は、この個体で高く出やすい能力です。", html)
        for label in ("耐久", "攻撃", "防御", "素早さ", "命中", "会心"):
            self.assertIn(label, html)


if __name__ == "__main__":
    unittest.main()
