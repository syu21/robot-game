import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class MarketRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        self.old_testing = game_app.app.config.get("TESTING")
        self.old_bypass = game_app.app.config.get("BYPASS_RELEASE_GATES_IN_TESTS")
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        init_db.main()
        game_app.app.config["TESTING"] = True
        game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = False

        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO users (username, password_hash, coins, created_at, is_admin, is_admin_protected, wins, max_unlocked_layer)
                VALUES (?, ?, ?, ?, 0, 0, 200, 1)
                """,
                ("market_user", "x", 1000, now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("market_user",)).fetchone()["id"])
            game_app.initialize_new_user(db, self.user_id)
            db.execute("UPDATE users SET coins = 1000 WHERE id = ?", (self.user_id,))
            db.execute(
                """
                INSERT INTO users (username, password_hash, coins, created_at, is_admin, is_admin_protected, wins, max_unlocked_layer)
                VALUES (?, ?, ?, ?, 1, 1, 200, 1)
                """,
                ("market_admin", "x", 1000, now),
            )
            self.admin_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("market_admin",)).fetchone()["id"])
            game_app.initialize_new_user(db, self.admin_id)
            db.execute("UPDATE users SET coins = 1000 WHERE id = ?", (self.admin_id,))
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        game_app.app.config["TESTING"] = self.old_testing
        if self.old_bypass is None:
            game_app.app.config.pop("BYPASS_RELEASE_GATES_IN_TESTS", None)
        else:
            game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = self.old_bypass
        self.tmpdir.cleanup()

    def _client(self, *, admin=False):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            if admin:
                session["user_id"] = self.admin_id
                session["username"] = "market_admin"
            else:
                session["user_id"] = self.user_id
                session["username"] = "market_user"
        return client

    def _first_listing(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            return db.execute(
                "SELECT * FROM market_daily_listings WHERE user_id = ? ORDER BY id ASC LIMIT 1",
                (self.admin_id,),
            ).fetchone()

    def test_market_is_admin_only_until_release(self):
        user_resp = self._client().get("/market")
        self.assertEqual(user_resp.status_code, 404)

        admin_resp = self._client(admin=True).get("/market")
        self.assertEqual(admin_resp.status_code, 200)
        self.assertIn("廃品市場", admin_resp.get_data(as_text=True))

    def test_market_generates_six_daily_listings(self):
        resp = self._client(admin=True).get("/market")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("今日の入荷", html)
        self.assertIn("パーツ所持枠拡張", html)
        self.assertIn("所持パーツ：", html)
        self.assertIn("保管", html)
        self.assertIn("まとめて売る", html)
        self.assertIn("marketSellTotal", html)
        self.assertIn('id="marketSellSubmit">まとめて売る', html)
        self.assertIn("market-part-stat-preview", html)
        self.assertIn("総合", html)
        self.assertIn("注目", html)
        for label in ("耐久", "攻撃", "防御", "素早さ", "命中", "会心"):
            self.assertIn(label, html)
        for key in ("hp", "atk", "def", "spd", "acc", "cri"):
            self.assertNotIn(f">{key}<", html)
        self.assertIn("static/market.js", html)
        self.assertNotIn("<script>\n(function ()", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM market_daily_listings WHERE user_id = ?",
                    (self.admin_id,),
                ).fetchone()["c"]
            )
            self.assertEqual(count, 6)

    def test_market_stat_preview_handles_missing_stat_source(self):
        client = self._client(admin=True)
        self.assertEqual(client.get("/market").status_code, 200)
        listing = self._first_listing()
        self.assertIsNotNone(listing)
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                "UPDATE market_daily_listings SET part_type = ? WHERE id = ?",
                ("UNKNOWN", int(listing["id"])),
            )
            db.commit()

        resp = client.get("/market")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("性能未設定", html)

    def test_market_part_inventory_expand_60_to_70(self):
        client = self._client(admin=True)
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET coins = 1000, part_inventory_limit = 60 WHERE id = ?", (self.admin_id,))
            db.commit()

        resp = client.post(
            "/market/part-inventory/expand",
            data={"current_limit": "60"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT coins, part_inventory_limit FROM users WHERE id = ?", (self.admin_id,)).fetchone()
            self.assertEqual(int(user["part_inventory_limit"]), 70)
            self.assertEqual(int(user["coins"]), 600)
            event = db.execute(
                """
                SELECT payload_json, delta_coins
                FROM world_events_log
                WHERE user_id = ? AND event_type = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (self.admin_id, game_app.AUDIT_EVENT_TYPES["PART_INVENTORY_EXPAND"]),
            ).fetchone()
            self.assertIsNotNone(event)
            self.assertEqual(int(event["delta_coins"]), -400)
            self.assertIn('"before_limit": 60', event["payload_json"])
            self.assertIn('"after_limit": 70', event["payload_json"])

    def test_market_part_inventory_expand_uses_price_table(self):
        client = self._client(admin=True)
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET coins = 5000, part_inventory_limit = 90 WHERE id = ?", (self.admin_id,))
            db.commit()

        resp = client.post(
            "/market/part-inventory/expand",
            data={"current_limit": "90"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT coins, part_inventory_limit FROM users WHERE id = ?", (self.admin_id,)).fetchone()
            self.assertEqual(int(user["part_inventory_limit"]), 100)
            self.assertEqual(int(user["coins"]), 2800)

    def test_market_part_inventory_expand_blocks_insufficient_coins(self):
        client = self._client(admin=True)
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET coins = 399, part_inventory_limit = 60 WHERE id = ?", (self.admin_id,))
            db.commit()

        resp = client.post(
            "/market/part-inventory/expand",
            data={"current_limit": "60"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT coins, part_inventory_limit FROM users WHERE id = ?", (self.admin_id,)).fetchone()
            self.assertEqual(int(user["part_inventory_limit"]), 60)
            self.assertEqual(int(user["coins"]), 399)
            events = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (self.admin_id, game_app.AUDIT_EVENT_TYPES["PART_INVENTORY_EXPAND"]),
            ).fetchone()
            self.assertEqual(int(events["c"] or 0), 0)

    def test_market_part_inventory_expand_blocks_at_120(self):
        client = self._client(admin=True)
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET coins = 99999, part_inventory_limit = 120 WHERE id = ?", (self.admin_id,))
            db.commit()

        page = client.get("/market")
        self.assertEqual(page.status_code, 200)
        self.assertIn("最大拡張済み", page.get_data(as_text=True))

        resp = client.post(
            "/market/part-inventory/expand",
            data={"current_limit": "120"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT coins, part_inventory_limit FROM users WHERE id = ?", (self.admin_id,)).fetchone()
            self.assertEqual(int(user["part_inventory_limit"]), 120)
            self.assertEqual(int(user["coins"]), 99999)

    def test_market_part_inventory_expand_rejects_stale_double_post(self):
        client = self._client(admin=True)
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET coins = 5000, part_inventory_limit = 60 WHERE id = ?", (self.admin_id,))
            db.commit()

        first = client.post(
            "/market/part-inventory/expand",
            data={"current_limit": "60"},
            follow_redirects=False,
        )
        second = client.post(
            "/market/part-inventory/expand",
            data={"current_limit": "60"},
            follow_redirects=False,
        )
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT coins, part_inventory_limit FROM users WHERE id = ?", (self.admin_id,)).fetchone()
            self.assertEqual(int(user["part_inventory_limit"]), 70)
            self.assertEqual(int(user["coins"]), 4600)
            events = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (self.admin_id, game_app.AUDIT_EVENT_TYPES["PART_INVENTORY_EXPAND"]),
            ).fetchone()
            self.assertEqual(int(events["c"] or 0), 1)

    def test_market_part_inventory_expand_updates_space_and_keeps_overflow_storage(self):
        client = self._client(admin=True)
        with game_app.app.app_context():
            db = game_app.get_db()
            part = db.execute(
                "SELECT * FROM robot_parts WHERE is_active = 1 AND UPPER(COALESCE(rarity, 'N')) = 'N' ORDER BY id ASC LIMIT 1"
            ).fetchone()
            db.execute("DELETE FROM part_instances WHERE user_id = ?", (self.admin_id,))
            db.execute("UPDATE users SET coins = 1000, part_inventory_limit = 60 WHERE id = ?", (self.admin_id,))
            for _ in range(60):
                game_app._create_part_instance_from_master(db, self.admin_id, part, plus=0, status="inventory")
            overflow_id = game_app._create_part_instance_from_master(db, self.admin_id, part, plus=0, status="overflow")
            db.commit()
            self.assertEqual(game_app._inventory_space_remaining(db, self.admin_id), 0)

        resp = client.post(
            "/market/part-inventory/expand",
            data={"current_limit": "60"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertEqual(game_app._inventory_space_remaining(db, self.admin_id), 10)
            overflow = db.execute("SELECT status FROM part_instances WHERE id = ?", (int(overflow_id),)).fetchone()
            self.assertEqual(str(overflow["status"]), "overflow")
            storage = game_app._part_storage_snapshot(db, self.admin_id)
            self.assertEqual(int(storage["overflow_count"]), 1)

    def test_market_refresh_first_free_then_paid(self):
        client = self._client(admin=True)
        self.assertEqual(client.get("/market").status_code, 200)

        first = client.post("/market/refresh", follow_redirects=False)
        self.assertEqual(first.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT coins, market_refresh_count_today FROM users WHERE id = ?",
                (self.admin_id,),
            ).fetchone()
            self.assertEqual(int(row["coins"]), 1000)
            self.assertEqual(int(row["market_refresh_count_today"]), 1)

        second = client.post("/market/refresh", follow_redirects=False)
        self.assertEqual(second.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT coins, market_refresh_count_today FROM users WHERE id = ?",
                (self.admin_id,),
            ).fetchone()
            self.assertEqual(int(row["coins"]), 900)
            self.assertEqual(int(row["market_refresh_count_today"]), 2)
            refresh_rows = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM market_refresh_history WHERE user_id = ?",
                    (self.admin_id,),
                ).fetchone()["c"]
            )
            self.assertEqual(refresh_rows, 2)

    def test_market_buy_consumes_coins_and_creates_part_instance(self):
        client = self._client(admin=True)
        self.assertEqual(client.get("/market").status_code, 200)
        listing = self._first_listing()
        self.assertIsNotNone(listing)

        resp = client.post(f"/market/buy/{int(listing['id'])}", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT coins FROM users WHERE id = ?", (self.admin_id,)).fetchone()
            self.assertEqual(int(user["coins"]), 1000 - int(listing["price"]))
            sold = db.execute("SELECT is_sold FROM market_daily_listings WHERE id = ?", (int(listing["id"]),)).fetchone()
            self.assertEqual(int(sold["is_sold"]), 1)
            instance = db.execute(
                "SELECT id FROM part_instances WHERE user_id = ? AND part_id = ? ORDER BY id DESC LIMIT 1",
                (self.admin_id, int(db.execute("SELECT id FROM robot_parts WHERE key = ?", (listing["part_key"],)).fetchone()["id"])),
            ).fetchone()
            self.assertIsNotNone(instance)
            event = db.execute(
                "SELECT id FROM world_events_log WHERE user_id = ? AND event_type = ? LIMIT 1",
                (self.admin_id, game_app.AUDIT_EVENT_TYPES["MARKET_BUY"]),
            ).fetchone()
            self.assertIsNotNone(event)
            history = db.execute(
                "SELECT id FROM market_purchase_history WHERE user_id = ? AND listing_id = ? LIMIT 1",
                (self.admin_id, int(listing["id"])),
            ).fetchone()
            self.assertIsNotNone(history)

        sold_page = client.get("/market")
        self.assertEqual(sold_page.status_code, 200)
        sold_html = sold_page.get_data(as_text=True)
        self.assertIn("market-buy-button is-sold", sold_html)
        self.assertIn("market-listing-card is-sold", sold_html)
        self.assertIn("market-part-stat-preview", sold_html)
        self.assertIn("disabled aria-disabled=\"true\"", sold_html)
        self.assertIn("購入済み", sold_html)

        blocked = client.post(f"/market/buy/{int(listing['id'])}", follow_redirects=False)
        self.assertEqual(blocked.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            count = db.execute(
                "SELECT COUNT(*) AS c FROM market_purchase_history WHERE user_id = ? AND listing_id = ?",
                (self.admin_id, int(listing["id"])),
            ).fetchone()
            self.assertEqual(int(count["c"] or 0), 1)

    def test_market_sell_only_inventory_parts(self):
        client = self._client(admin=True)
        with game_app.app.app_context():
            db = game_app.get_db()
            part = db.execute(
                "SELECT * FROM robot_parts WHERE is_active = 1 AND UPPER(COALESCE(rarity, 'N')) = 'N' ORDER BY id ASC LIMIT 1"
            ).fetchone()
            inventory_id = game_app._create_part_instance_from_master(db, self.admin_id, part, plus=2, status="inventory")
            equipped_id = game_app._create_part_instance_from_master(db, self.admin_id, part, plus=0, status="equipped")
            db.commit()

        sold = client.post("/market/sell", data={"part_instance_id": int(inventory_id)}, follow_redirects=False)
        self.assertEqual(sold.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT coins FROM users WHERE id = ?", (self.admin_id,)).fetchone()
            self.assertEqual(int(user["coins"]), 1010)
            sold_status = db.execute("SELECT status FROM part_instances WHERE id = ?", (int(inventory_id),)).fetchone()["status"]
            self.assertEqual(str(sold_status), "sold")
            history = db.execute(
                "SELECT price FROM market_sell_history WHERE user_id = ? AND part_instance_id = ? LIMIT 1",
                (self.admin_id, int(inventory_id)),
            ).fetchone()
            self.assertEqual(int(history["price"]), 10)

        blocked = client.post("/market/sell", data={"part_instance_id": int(equipped_id)}, follow_redirects=False)
        self.assertEqual(blocked.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT coins FROM users WHERE id = ?", (self.admin_id,)).fetchone()
            still_there = db.execute("SELECT id FROM part_instances WHERE id = ?", (int(equipped_id),)).fetchone()
            self.assertEqual(int(user["coins"]), 1010)
            self.assertIsNotNone(still_there)

    def test_market_excludes_and_blocks_locked_parts(self):
        client = self._client(admin=True)
        with game_app.app.app_context():
            db = game_app.get_db()
            part = db.execute(
                "SELECT * FROM robot_parts WHERE is_active = 1 AND UPPER(COALESCE(rarity, 'N')) = 'N' ORDER BY id ASC LIMIT 1"
            ).fetchone()
            locked_id = game_app._create_part_instance_from_master(db, self.admin_id, part, plus=2, status="inventory")
            unlocked_id = game_app._create_part_instance_from_master(db, self.admin_id, part, plus=0, status="inventory")
            db.execute("UPDATE part_instances SET locked = 1 WHERE id = ?", (int(locked_id),))
            db.commit()

        page = client.get("/market")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("保護中のパーツは売却候補から外れます。解除は所持パーツ画面から行えます。", html)
        self.assertIn("保護中パーツ 1個は売却候補から除外されています。", html)
        self.assertNotIn(f'value="{int(locked_id)}"', html)
        self.assertIn(f'value="{int(unlocked_id)}"', html)

        blocked = client.post("/market/sell", data={"part_instance_id": int(locked_id)}, follow_redirects=False)
        self.assertEqual(blocked.status_code, 302)
        bulk = client.post(
            "/market/sell-bulk",
            data={"part_instance_ids": [str(locked_id), str(unlocked_id)]},
            follow_redirects=False,
        )
        self.assertEqual(bulk.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            locked_row = db.execute("SELECT status, locked FROM part_instances WHERE id = ?", (int(locked_id),)).fetchone()
            unlocked_row = db.execute("SELECT status FROM part_instances WHERE id = ?", (int(unlocked_id),)).fetchone()
            self.assertEqual(str(locked_row["status"]), "inventory")
            self.assertEqual(int(locked_row["locked"]), 1)
            self.assertEqual(str(unlocked_row["status"]), "sold")

    def test_market_sell_bulk_sells_checked_inventory_parts(self):
        client = self._client(admin=True)
        with game_app.app.app_context():
            db = game_app.get_db()
            part = db.execute(
                "SELECT * FROM robot_parts WHERE is_active = 1 AND UPPER(COALESCE(rarity, 'N')) = 'N' ORDER BY id ASC LIMIT 1"
            ).fetchone()
            first_id = game_app._create_part_instance_from_master(db, self.admin_id, part, plus=0, status="inventory")
            second_id = game_app._create_part_instance_from_master(db, self.admin_id, part, plus=1, status="inventory")
            db.commit()

        sold = client.post(
            "/market/sell-bulk",
            data={"part_instance_ids": [str(first_id), str(second_id)]},
            follow_redirects=False,
        )
        self.assertEqual(sold.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT coins FROM users WHERE id = ?", (self.admin_id,)).fetchone()
            self.assertEqual(int(user["coins"]), 1020)
            remaining = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM part_instances WHERE id IN (?, ?) AND status != 'sold'",
                    (int(first_id), int(second_id)),
                ).fetchone()["c"]
                or 0
            )
            self.assertEqual(remaining, 0)
            history_count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM market_sell_history WHERE user_id = ? AND part_instance_id IN (?, ?)",
                    (self.admin_id, int(first_id), int(second_id)),
                ).fetchone()["c"]
                or 0
            )
            self.assertEqual(history_count, 2)


if __name__ == "__main__":
    unittest.main()
