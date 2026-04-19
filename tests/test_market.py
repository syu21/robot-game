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
        self.assertIn("まとめて売る", html)
        self.assertIn("marketSellTotal", html)
        self.assertIn('id="marketSellSubmit">まとめて売る', html)
        with game_app.app.app_context():
            db = game_app.get_db()
            count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM market_daily_listings WHERE user_id = ?",
                    (self.admin_id,),
                ).fetchone()["c"]
            )
            self.assertEqual(count, 6)

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
            self.assertEqual(int(user["coins"]), 1100)
            gone = db.execute("SELECT id FROM part_instances WHERE id = ?", (int(inventory_id),)).fetchone()
            self.assertIsNone(gone)
            history = db.execute(
                "SELECT price FROM market_sell_history WHERE user_id = ? AND part_instance_id = ? LIMIT 1",
                (self.admin_id, int(inventory_id)),
            ).fetchone()
            self.assertEqual(int(history["price"]), 100)

        blocked = client.post("/market/sell", data={"part_instance_id": int(equipped_id)}, follow_redirects=False)
        self.assertEqual(blocked.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT coins FROM users WHERE id = ?", (self.admin_id,)).fetchone()
            still_there = db.execute("SELECT id FROM part_instances WHERE id = ?", (int(equipped_id),)).fetchone()
            self.assertEqual(int(user["coins"]), 1100)
            self.assertIsNotNone(still_there)

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
            self.assertEqual(int(user["coins"]), 1140)
            remaining = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM part_instances WHERE id IN (?, ?)",
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
