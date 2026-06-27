import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactionShopTests(unittest.TestCase):
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
            self.admin_id = self._create_user(db, "shop_admin", now, "aurix", is_admin=1, coins=5000)
            self.aurix_user = self._create_user(db, "shop_aurix", now, "aurix", coins=5000)
            self.ignis_user = self._create_user(db, "shop_ignis", now, "ignis", coins=5000)
            self.low_coin_user = self._create_user(db, "shop_low", now, "aurix", coins=10)
            self.week_key = game_app.get_current_week_key()
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _create_user(self, db, username, now, faction, *, is_admin=0, coins=0):
        db.execute(
            """
            INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer, faction, coins)
            VALUES (?, ?, ?, ?, 0, 1, ?, ?)
            """,
            (username, "x", now, int(is_admin), faction, int(coins)),
        )
        user_id = int(db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"])
        game_app.initialize_new_user(db, user_id)
        db.execute("UPDATE users SET coins = ? WHERE id = ?", (int(coins), user_id))
        return user_id

    def _client(self, user_id=None, username="shop_aurix"):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user_id or self.aurix_user)
            session["username"] = username
        return client

    def _item_id(self, db, item_key):
        return int(db.execute("SELECT id FROM faction_shop_items WHERE item_key = ?", (item_key,)).fetchone()["id"])

    def test_tables_defaults_and_no_new_currency(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertIn("item_key", {row["name"] for row in db.execute("PRAGMA table_info(faction_shop_items)").fetchall()})
            self.assertIn("item_key", {row["name"] for row in db.execute("PRAGMA table_info(user_faction_shop_purchases)").fetchall()})
            self.assertIn("slot_key", {row["name"] for row in db.execute("PRAGMA table_info(user_equipped_faction_shop_items)").fetchall()})
            first = game_app.ensure_default_faction_shop_items(db)
            second = game_app.ensure_default_faction_shop_items(db)
            self.assertGreaterEqual(first["created_count"], 8)
            self.assertEqual(second["created_count"], 0)
            tables = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            self.assertFalse(any("medal" in name.lower() for name in tables))
            user_cols = {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}
            self.assertNotIn("faction_medal", user_cols)

    def test_purchase_rules_coin_faction_duplicate_and_stats_safe(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_default_faction_shop_items(db)
            badge_id = self._item_id(db, "weekly_event_memorial_badge")
            aurix_item_id = self._item_id(db, "aurix_bastion_badge")
            before_robot = db.execute("SELECT * FROM robot_instances WHERE user_id = ? ORDER BY id LIMIT 1", (self.aurix_user,)).fetchone()
            before_coins = int(db.execute("SELECT coins FROM users WHERE id = ?", (self.aurix_user,)).fetchone()["coins"])

            low = game_app.purchase_faction_shop_item(db, self.low_coin_user, badge_id)
            self.assertFalse(low["ok"])
            self.assertIn("コイン", low["reason"])

            other = game_app.purchase_faction_shop_item(db, self.ignis_user, aurix_item_id)
            self.assertFalse(other["ok"])
            self.assertIn("オリクス", other["reason"])

            facility_block = game_app.purchase_faction_shop_item(db, self.aurix_user, aurix_item_id)
            self.assertFalse(facility_block["ok"])
            self.assertIn("施設レベル", facility_block["reason"])

            ok = game_app.purchase_faction_shop_item(db, self.aurix_user, badge_id)
            dup = game_app.purchase_faction_shop_item(db, self.aurix_user, badge_id)
            self.assertTrue(ok["ok"])
            self.assertFalse(dup["ok"])
            self.assertIn("購入済み", dup["reason"])
            after_coins = int(db.execute("SELECT coins FROM users WHERE id = ?", (self.aurix_user,)).fetchone()["coins"])
            self.assertEqual(after_coins, before_coins - 100)
            purchase_count = db.execute("SELECT COUNT(*) AS c FROM user_faction_shop_purchases WHERE user_id = ?", (self.aurix_user,)).fetchone()["c"]
            self.assertEqual(purchase_count, 1)
            after_robot = db.execute("SELECT * FROM robot_instances WHERE user_id = ? ORDER BY id LIMIT 1", (self.aurix_user,)).fetchone()
            self.assertEqual(dict(before_robot), dict(after_robot))

    def test_facility_title_territory_title_ticket_and_equip(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_default_faction_shop_items(db)
            game_app.ensure_faction_facilities(db)
            db.execute("UPDATE faction_facilities SET level = 3 WHERE faction_key = 'aurix'")
            title_item_id = self._item_id(db, "aurix_guard_title")
            result = game_app.purchase_faction_shop_item(db, self.aurix_user, title_item_id)
            self.assertTrue(result["ok"])
            title = db.execute(
                "SELECT * FROM user_faction_titles WHERE user_id = ? AND title_key = 'shop_aurix_guard'",
                (self.aurix_user,),
            ).fetchone()
            self.assertIsNotNone(title)

            db.execute(
                """
                INSERT INTO faction_shop_items
                (item_key, item_name, description, item_type, faction_key, price_coins, required_title_key,
                 required_territory_count, created_at, updated_at)
                VALUES ('aurix_title_locked_badge', '称号条件バッジ', 'test', 'faction_badge', 'aurix', 10,
                        'shop_aurix_guard', 1, ?, ?)
                """,
                (game_app.now_str(), game_app.now_str()),
            )
            locked_id = self._item_id(db, "aurix_title_locked_badge")
            check = game_app.can_purchase_faction_shop_item(db, self.aurix_user, locked_id)
            self.assertTrue(check["ok"])
            badge = game_app.purchase_faction_shop_item(db, self.aurix_user, locked_id)
            self.assertTrue(badge["ok"])
            equip = game_app.equip_faction_shop_item(db, self.aurix_user, int(badge["purchase_id"]), "faction_badge")
            self.assertTrue(equip["ok"])
            equipped = game_app.get_user_equipped_faction_shop_items(db, self.aurix_user)
            self.assertEqual(equipped["faction_badge"]["item_key"], "aurix_title_locked_badge")
            other_equip = game_app.equip_faction_shop_item(db, self.ignis_user, int(badge["purchase_id"]), "faction_badge")
            self.assertFalse(other_equip["ok"])

    def test_pages_and_admin_routes(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_default_faction_shop_items(db)
            db.commit()
        client = self._client()
        self.assertIn("陣営ショップ", client.get("/faction/shop").get_data(as_text=True))
        self.assertIn("陣営ショップ", client.get("/faction").get_data(as_text=True))
        self.assertIn("陣営ショップ", client.get("/world").get_data(as_text=True))
        self.assertIn("陣営ショップ", client.get("/comms/faction").get_data(as_text=True))
        self.assertEqual(client.get("/admin/factions/shop").status_code, 403)

        admin = self._client(self.admin_id, "shop_admin")
        self.assertEqual(admin.get("/admin/factions/shop").status_code, 200)
        self.assertEqual(admin.post("/admin/factions/shop/ensure-defaults").status_code, 302)
        create = admin.post(
            "/admin/factions/shop/create",
            data={
                "item_key": "admin_test_badge",
                "item_name": "管理テストバッジ",
                "description": "test",
                "item_type": "faction_badge",
                "faction_key": "aurix",
                "price_coins": "50",
                "is_active": "1",
                "sort_order": "999",
            },
        )
        self.assertEqual(create.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            item = db.execute("SELECT * FROM faction_shop_items WHERE item_key = 'admin_test_badge'").fetchone()
            self.assertIsNotNone(item)
            item_id = int(item["id"])
        update = admin.post(
            "/admin/factions/shop/update",
            data={
                "item_id": str(item_id),
                "item_key": "admin_test_badge",
                "item_name": "管理テストバッジ改",
                "description": "updated",
                "item_type": "faction_badge",
                "faction_key": "aurix",
                "price_coins": "60",
                "is_active": "1",
                "sort_order": "998",
            },
        )
        self.assertEqual(update.status_code, 302)


if __name__ == "__main__":
    unittest.main()
