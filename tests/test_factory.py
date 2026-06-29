import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactoryTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer, coins)
                VALUES (?, ?, ?, 0, 0, 1, 0)
                """,
                ("factory_user", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("factory_user",)).fetchone()["id"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "factory_user"
        return client

    def test_initial_access_creates_three_facilities(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            result = game_app.ensure_user_factory_facilities(db, self.user_id, request_id="factory-ensure")
            db.commit()
            self.assertEqual(result["created_count"], 3)
            count = int(db.execute("SELECT COUNT(*) AS c FROM user_factory_facilities WHERE user_id = ?", (self.user_id,)).fetchone()["c"])
            self.assertEqual(count, 3)
            event = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["FACTORY_ENSURE_DEFAULTS"]),
            ).fetchone()
            self.assertIsNotNone(event)
        html = self._client().get("/factory").get_data(as_text=True)
        self.assertIn("ロボ工場", html)
        self.assertIn("スクラップ回収機", html)
        self.assertIn("エネルギー炉", html)
        self.assertIn("研究端末", html)

    def test_pending_points_and_twelve_hour_cap(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_user_factory_facilities(db, self.user_id)
            now = int(time.time())
            db.execute(
                "UPDATE user_factory_facilities SET last_claimed_at = ? WHERE user_id = ? AND facility_key = 'scrap_collector'",
                (now - 3 * 3600, self.user_id),
            )
            row = db.execute("SELECT * FROM user_factory_facilities WHERE user_id = ? AND facility_key = 'scrap_collector'", (self.user_id,)).fetchone()
            self.assertEqual(game_app._factory_pending_points(row, now), 15)
            db.execute(
                "UPDATE user_factory_facilities SET last_claimed_at = ? WHERE user_id = ? AND facility_key = 'scrap_collector'",
                (now - 20 * 3600, self.user_id),
            )
            row = db.execute("SELECT * FROM user_factory_facilities WHERE user_id = ? AND facility_key = 'scrap_collector'", (self.user_id,)).fetchone()
            self.assertEqual(game_app._factory_pending_points(row, now), 60)

    def test_claim_adds_factory_points_and_updates_timestamp_and_audit(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_user_factory_facilities(db, self.user_id)
            db.execute("UPDATE users SET factory_points = 10 WHERE id = ?", (self.user_id,))
            db.execute(
                "UPDATE user_factory_facilities SET last_claimed_at = ? WHERE user_id = ? AND facility_key = 'scrap_collector'",
                (int(time.time()) - 2 * 3600, self.user_id),
            )
            before = int(db.execute("SELECT last_claimed_at FROM user_factory_facilities WHERE user_id = ? AND facility_key = 'scrap_collector'", (self.user_id,)).fetchone()["last_claimed_at"])
            result = game_app.claim_factory_facility_points(db, self.user_id, "scrap_collector", request_id="factory-claim")
            self.assertTrue(result["ok"])
            user = db.execute("SELECT factory_points FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(user["factory_points"]), 20)
            after = int(db.execute("SELECT last_claimed_at FROM user_factory_facilities WHERE user_id = ? AND facility_key = 'scrap_collector'", (self.user_id,)).fetchone()["last_claimed_at"])
            self.assertGreaterEqual(after, before)
            event = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ? ORDER BY id DESC LIMIT 1",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["FACTORY_CLAIM"]),
            ).fetchone()
            self.assertIsNotNone(event)
            payload = json.loads(event["payload_json"] or "{}")
            self.assertEqual(payload["points_gained"], 10)
            self.assertEqual(payload["factory_points_before"], 10)
            self.assertEqual(payload["factory_points_after"], 20)
            second = game_app.claim_factory_facility_points(db, self.user_id, "scrap_collector", request_id="factory-claim-2")
            self.assertFalse(second["ok"])

    def test_upgrade_spends_coins_levels_up_and_audits(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_user_factory_facilities(db, self.user_id)
            db.execute("UPDATE users SET coins = 1000 WHERE id = ?", (self.user_id,))
            result = game_app.upgrade_factory_facility(db, self.user_id, "energy_reactor", request_id="factory-upgrade")
            self.assertTrue(result["ok"])
            row = db.execute("SELECT level FROM user_factory_facilities WHERE user_id = ? AND facility_key = 'energy_reactor'", (self.user_id,)).fetchone()
            user = db.execute("SELECT coins FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(row["level"]), 2)
            self.assertEqual(int(user["coins"]), 500)
            for event_type in (game_app.AUDIT_EVENT_TYPES["FACTORY_UPGRADE"], game_app.AUDIT_EVENT_TYPES["COIN_DELTA"]):
                self.assertIsNotNone(
                    db.execute(
                        "SELECT id FROM world_events_log WHERE user_id = ? AND event_type = ?",
                        (self.user_id, event_type),
                    ).fetchone()
                )

    def test_upgrade_rejects_insufficient_coins_and_max_level(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_user_factory_facilities(db, self.user_id)
            db.execute("UPDATE users SET coins = 499 WHERE id = ?", (self.user_id,))
            poor = game_app.upgrade_factory_facility(db, self.user_id, "research_terminal")
            self.assertFalse(poor["ok"])
            row = db.execute("SELECT level FROM user_factory_facilities WHERE user_id = ? AND facility_key = 'research_terminal'", (self.user_id,)).fetchone()
            self.assertEqual(int(row["level"]), 1)
            db.execute("UPDATE user_factory_facilities SET level = 5 WHERE user_id = ? AND facility_key = 'research_terminal'", (self.user_id,))
            maxed = game_app.upgrade_factory_facility(db, self.user_id, "research_terminal")
            self.assertFalse(maxed["ok"])
            self.assertIn("最大Lv", maxed["reason"])

    def test_home_links_factory(self):
        html = self._client().get("/home").get_data(as_text=True)
        self.assertIn("ロボ工場", html)
        self.assertIn("/factory", html)

    def test_factory_prizes_initial_access_seeds_prizes(self):
        html = self._client().get("/factory/prizes").get_data(as_text=True)
        self.assertIn("工場交換所", html)
        self.assertIn("工場主任", html)
        self.assertIn("スクラップバッジ", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            count = int(db.execute("SELECT COUNT(*) AS c FROM factory_prizes").fetchone()["c"])
            self.assertEqual(count, 5)
            event = db.execute(
                "SELECT payload_json FROM world_events_log WHERE event_type = ? ORDER BY id DESC LIMIT 1",
                (game_app.AUDIT_EVENT_TYPES["FACTORY_PRIZE_ENSURE_DEFAULTS"],),
            ).fetchone()
            self.assertIsNotNone(event)

    def test_factory_prize_claim_spends_points_records_claim_and_audit(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_factory_prizes(db, user_id=self.user_id)
            db.execute("UPDATE users SET factory_points = 1000 WHERE id = ?", (self.user_id,))
            result = game_app.claim_factory_prize(db, self.user_id, "factory_title_foreman", request_id="factory-prize")
            self.assertTrue(result["ok"])
            points = int(db.execute("SELECT factory_points FROM users WHERE id = ?", (self.user_id,)).fetchone()["factory_points"])
            self.assertEqual(points, 700)
            claim = db.execute(
                "SELECT id FROM user_factory_prize_claims WHERE user_id = ? AND prize_key = ?",
                (self.user_id, "factory_title_foreman"),
            ).fetchone()
            self.assertIsNotNone(claim)
            event = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ? ORDER BY id DESC LIMIT 1",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["FACTORY_PRIZE_CLAIM"]),
            ).fetchone()
            self.assertIsNotNone(event)
            payload = json.loads(event["payload_json"] or "{}")
            self.assertEqual(payload["prize_key"], "factory_title_foreman")
            self.assertEqual(payload["factory_points_before"], 1000)
            self.assertEqual(payload["factory_points_after"], 700)

    def test_factory_prize_claim_rejects_duplicate_and_insufficient_points(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_factory_prizes(db, user_id=self.user_id)
            db.execute("UPDATE users SET factory_points = 300 WHERE id = ?", (self.user_id,))
            first = game_app.claim_factory_prize(db, self.user_id, "factory_title_foreman")
            self.assertTrue(first["ok"])
            second = game_app.claim_factory_prize(db, self.user_id, "factory_title_foreman")
            self.assertFalse(second["ok"])
            self.assertIn("交換済み", second["reason"])
            points = int(db.execute("SELECT factory_points FROM users WHERE id = ?", (self.user_id,)).fetchone()["factory_points"])
            self.assertEqual(points, 0)
            poor = game_app.claim_factory_prize(db, self.user_id, "factory_decor_scrap_badge")
            self.assertFalse(poor["ok"])
            self.assertIn("足りません", poor["reason"])
            count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM user_factory_prize_claims WHERE user_id = ?",
                    (self.user_id,),
                ).fetchone()["c"]
            )
            self.assertEqual(count, 1)

    def test_factory_prizes_hides_inactive_items_and_factory_links_exchange(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_factory_prizes(db, user_id=self.user_id)
            db.execute("UPDATE factory_prizes SET is_active = 0 WHERE prize_key = ?", ("factory_skin_blue_lab",))
            db.commit()
        client = self._client()
        factory_html = client.get("/factory").get_data(as_text=True)
        self.assertIn("/factory/prizes", factory_html)
        prizes_html = client.get("/factory/prizes").get_data(as_text=True)
        self.assertNotIn("工場背景：青い研究区画", prizes_html)

    def test_factory_research_initial_access_seeds_projects(self):
        html = self._client().get("/factory/research").get_data(as_text=True)
        self.assertIn("世界研究", html)
        self.assertIn("エネルギー研究", html)
        self.assertIn("塗装技術", html)
        self.assertIn("通信技術", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            count = int(db.execute("SELECT COUNT(*) AS c FROM world_research_projects").fetchone()["c"])
            self.assertEqual(count, 3)
            event = db.execute(
                "SELECT id FROM world_events_log WHERE event_type = ? ORDER BY id DESC LIMIT 1",
                (game_app.AUDIT_EVENT_TYPES["FACTORY_RESEARCH_ENSURE_DEFAULTS"],),
            ).fetchone()
            self.assertIsNotNone(event)

    def test_factory_research_donate_spends_points_adds_progress_and_audit(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_factory_research_projects(db, user_id=self.user_id)
            db.execute("UPDATE users SET factory_points = 1200 WHERE id = ?", (self.user_id,))
            result = game_app.donate_factory_research_points(db, self.user_id, "energy_research", 500, request_id="research-donate")
            self.assertTrue(result["ok"])
            self.assertFalse(result["completed"])
            points = int(db.execute("SELECT factory_points FROM users WHERE id = ?", (self.user_id,)).fetchone()["factory_points"])
            self.assertEqual(points, 700)
            project = db.execute("SELECT current_points FROM world_research_projects WHERE research_key = ?", ("energy_research",)).fetchone()
            self.assertEqual(int(project["current_points"]), 500)
            contrib = db.execute(
                "SELECT points FROM user_research_contributions WHERE user_id = ? AND research_key = ?",
                (self.user_id, "energy_research"),
            ).fetchone()
            self.assertEqual(int(contrib["points"]), 500)
            event = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ? ORDER BY id DESC LIMIT 1",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["FACTORY_RESEARCH_DONATE"]),
            ).fetchone()
            self.assertIsNotNone(event)
            payload = json.loads(event["payload_json"] or "{}")
            self.assertEqual(payload["amount"], 500)
            self.assertEqual(payload["factory_points_before"], 1200)
            self.assertEqual(payload["factory_points_after"], 700)

    def test_factory_research_rejects_insufficient_points(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_factory_research_projects(db, user_id=self.user_id)
            db.execute("UPDATE users SET factory_points = 99 WHERE id = ?", (self.user_id,))
            result = game_app.donate_factory_research_points(db, self.user_id, "paint_research", 100)
            self.assertFalse(result["ok"])
            self.assertIn("足りません", result["reason"])
            points = int(db.execute("SELECT factory_points FROM users WHERE id = ?", (self.user_id,)).fetchone()["factory_points"])
            self.assertEqual(points, 99)

    def test_factory_research_completion_logs_once(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_factory_research_projects(db, user_id=self.user_id)
            db.execute("UPDATE users SET factory_points = 1000 WHERE id = ?", (self.user_id,))
            db.execute("UPDATE world_research_projects SET current_points = 49950 WHERE research_key = ?", ("energy_research",))
            result = game_app.donate_factory_research_points(db, self.user_id, "energy_research", 100, request_id="research-complete")
            self.assertTrue(result["ok"])
            self.assertTrue(result["completed"])
            project = db.execute("SELECT is_completed FROM world_research_projects WHERE research_key = ?", ("energy_research",)).fetchone()
            self.assertEqual(int(project["is_completed"]), 1)
            complete_count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ?",
                    (game_app.AUDIT_EVENT_TYPES["FACTORY_RESEARCH_COMPLETE"],),
                ).fetchone()["c"]
            )
            self.assertEqual(complete_count, 1)
            second = game_app.donate_factory_research_points(db, self.user_id, "energy_research", 100)
            self.assertFalse(second["ok"])
            self.assertIn("完了済み", second["reason"])
            complete_count_after = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ?",
                    (game_app.AUDIT_EVENT_TYPES["FACTORY_RESEARCH_COMPLETE"],),
                ).fetchone()["c"]
            )
            self.assertEqual(complete_count_after, 1)

    def test_factory_research_links_from_factory_and_home(self):
        client = self._client()
        factory_html = client.get("/factory").get_data(as_text=True)
        self.assertIn("/factory/research", factory_html)
        home_html = client.get("/home").get_data(as_text=True)
        self.assertIn("世界研究", home_html)
        self.assertIn("/factory/research", home_html)

    def test_factory_customize_initial_access_grants_defaults(self):
        html = self._client().get("/factory/customize").get_data(as_text=True)
        self.assertIn("基地カスタマイズ", html)
        self.assertIn("通常研究所", html)
        self.assertIn("鉄床", html)
        self.assertIn("小型モニター", html)
        self.assertIn("工具箱", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            cosmetic_count = int(db.execute("SELECT COUNT(*) AS c FROM factory_cosmetics").fetchone()["c"])
            owned_count = int(db.execute("SELECT COUNT(*) AS c FROM user_factory_cosmetics WHERE user_id = ?", (self.user_id,)).fetchone()["c"])
            self.assertEqual(cosmetic_count, 4)
            self.assertEqual(owned_count, 4)
            user = db.execute(
                """
                SELECT equipped_factory_background, equipped_factory_floor,
                       equipped_factory_facility, equipped_factory_decoration
                FROM users
                WHERE id = ?
                """,
                (self.user_id,),
            ).fetchone()
            self.assertEqual(user["equipped_factory_background"], "factory_bg_default_lab")
            self.assertEqual(user["equipped_factory_floor"], "factory_floor_iron")
            self.assertEqual(user["equipped_factory_facility"], "factory_facility_small_monitor")
            self.assertEqual(user["equipped_factory_decoration"], "factory_decoration_toolbox")

    def test_factory_customize_equip_owned_item_and_audit(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_factory_cosmetics(db, self.user_id)
            now = int(time.time())
            db.execute(
                """
                INSERT INTO factory_cosmetics
                (cosmetic_key, cosmetic_type, name_ja, description, image_path, is_default, is_active, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 0, 1, 99, ?, ?)
                """,
                ("factory_bg_space_base", "background", "宇宙基地", "宇宙基地風の背景。", "", now, now),
            )
            db.execute(
                "INSERT INTO user_factory_cosmetics (user_id, cosmetic_key, unlocked_at) VALUES (?, ?, ?)",
                (self.user_id, "factory_bg_space_base", now),
            )
            result = game_app.equip_factory_cosmetic(db, self.user_id, "factory_bg_space_base", request_id="cosmetic-equip")
            self.assertTrue(result["ok"])
            user = db.execute("SELECT equipped_factory_background FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(user["equipped_factory_background"], "factory_bg_space_base")
            event = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ? ORDER BY id DESC LIMIT 1",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["FACTORY_COSMETIC_EQUIP"]),
            ).fetchone()
            self.assertIsNotNone(event)
            payload = json.loads(event["payload_json"] or "{}")
            self.assertEqual(payload["cosmetic_key"], "factory_bg_space_base")
            self.assertEqual(payload["cosmetic_type"], "background")

    def test_factory_customize_rejects_unowned_item(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_factory_cosmetics(db, self.user_id)
            now = int(time.time())
            db.execute(
                """
                INSERT INTO factory_cosmetics
                (cosmetic_key, cosmetic_type, name_ja, description, image_path, is_default, is_active, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 0, 1, 100, ?, ?)
                """,
                ("factory_floor_energy", "floor", "エネルギー床", "光る床。", "", now, now),
            )
            result = game_app.equip_factory_cosmetic(db, self.user_id, "factory_floor_energy")
            self.assertFalse(result["ok"])
            self.assertIn("未所持", result["reason"])
            user = db.execute("SELECT equipped_factory_floor FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(user["equipped_factory_floor"], "factory_floor_iron")

    def test_factory_customize_links_from_factory_and_home(self):
        client = self._client()
        factory_html = client.get("/factory").get_data(as_text=True)
        self.assertIn("/factory/customize", factory_html)
        home_html = client.get("/home").get_data(as_text=True)
        self.assertIn("MY BASE", home_html)
        self.assertIn("/factory/customize", home_html)

    def test_drone_initial_access_grants_three_drones(self):
        html = self._client().get("/drone").get_data(as_text=True)
        self.assertIn("ドローン研究所", html)
        self.assertIn("偵察ドローン", html)
        self.assertIn("回収ドローン", html)
        self.assertIn("整備ドローン", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            master_count = int(db.execute("SELECT COUNT(*) AS c FROM drone_masters").fetchone()["c"])
            owned_count = int(db.execute("SELECT COUNT(*) AS c FROM user_drones WHERE user_id = ?", (self.user_id,)).fetchone()["c"])
            user = db.execute("SELECT active_drone_key FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(master_count, 3)
            self.assertEqual(owned_count, 3)
            self.assertEqual(user["active_drone_key"], "scout_drone")

    def test_drone_equip_owned_drone_and_audit(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_drones(db, self.user_id)
            result = game_app.equip_drone(db, self.user_id, "collector_drone", request_id="drone-equip")
            self.assertTrue(result["ok"])
            user = db.execute("SELECT active_drone_key FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(user["active_drone_key"], "collector_drone")
            event = db.execute(
                "SELECT payload_json FROM world_events_log WHERE user_id = ? AND event_type = ? ORDER BY id DESC LIMIT 1",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["DRONE_EQUIP"]),
            ).fetchone()
            self.assertIsNotNone(event)
            payload = json.loads(event["payload_json"] or "{}")
            self.assertEqual(payload["drone_key"], "collector_drone")

    def test_drone_rejects_unowned_and_inactive_equip(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_drones(db, self.user_id)
            now = int(time.time())
            db.execute(
                """
                INSERT INTO drone_masters
                (drone_key, name_ja, description, effect_type, base_effect_value, image_path, is_active, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, 0, '', 1, 99, ?, ?)
                """,
                ("event_drone", "イベントドローン", "未所持テスト", "scout_note", now, now),
            )
            unowned = game_app.equip_drone(db, self.user_id, "event_drone")
            self.assertFalse(unowned["ok"])
            self.assertIn("未所持", unowned["reason"])
            db.execute("UPDATE drone_masters SET is_active = 0 WHERE drone_key = ?", ("collector_drone",))
            inactive = game_app.equip_drone(db, self.user_id, "collector_drone")
            self.assertFalse(inactive["ok"])

    def test_drone_upgrade_spends_factory_points_and_audits(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_drones(db, self.user_id)
            db.execute("UPDATE users SET factory_points = 500 WHERE id = ?", (self.user_id,))
            result = game_app.upgrade_drone(db, self.user_id, "collector_drone", request_id="drone-upgrade")
            self.assertTrue(result["ok"])
            row = db.execute("SELECT level FROM user_drones WHERE user_id = ? AND drone_key = ?", (self.user_id, "collector_drone")).fetchone()
            user = db.execute("SELECT factory_points FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(row["level"]), 2)
            self.assertEqual(int(user["factory_points"]), 200)
            for event_type in (game_app.AUDIT_EVENT_TYPES["DRONE_UPGRADE"], game_app.AUDIT_EVENT_TYPES["FACTORY_POINTS_DELTA"]):
                self.assertIsNotNone(
                    db.execute(
                        "SELECT id FROM world_events_log WHERE user_id = ? AND event_type = ?",
                        (self.user_id, event_type),
                    ).fetchone()
                )

    def test_drone_upgrade_rejects_insufficient_points_and_max_level(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_drones(db, self.user_id)
            db.execute("UPDATE users SET factory_points = 299 WHERE id = ?", (self.user_id,))
            poor = game_app.upgrade_drone(db, self.user_id, "collector_drone")
            self.assertFalse(poor["ok"])
            self.assertIn("足りません", poor["reason"])
            db.execute("UPDATE user_drones SET level = 5 WHERE user_id = ? AND drone_key = ?", (self.user_id, "collector_drone"))
            maxed = game_app.upgrade_drone(db, self.user_id, "collector_drone")
            self.assertFalse(maxed["ok"])
            self.assertIn("最大Lv", maxed["reason"])

    def test_collector_drone_adds_factory_claim_bonus(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_user_factory_facilities(db, self.user_id)
            game_app.ensure_drones(db, self.user_id)
            db.execute("UPDATE users SET factory_points = 0, active_drone_key = ? WHERE id = ?", ("collector_drone", self.user_id))
            db.execute("UPDATE user_drones SET level = 3 WHERE user_id = ? AND drone_key = ?", (self.user_id, "collector_drone"))
            db.execute(
                "UPDATE user_factory_facilities SET last_claimed_at = ? WHERE user_id = ? AND facility_key = 'scrap_collector'",
                (int(time.time()) - 20 * 3600, self.user_id),
            )
            result = game_app.claim_factory_facility_points(db, self.user_id, "scrap_collector")
            self.assertTrue(result["ok"])
            self.assertEqual(result["points_gained"], 61)
            self.assertEqual(result["bonus_points_gained"], 1)
            user = db.execute("SELECT factory_points FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(user["factory_points"]), 61)

    def test_maintenance_drone_extends_factory_storage_cap(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_user_factory_facilities(db, self.user_id)
            game_app.ensure_drones(db, self.user_id)
            db.execute("UPDATE users SET active_drone_key = ? WHERE id = ?", ("maintenance_drone", self.user_id))
            db.execute("UPDATE user_drones SET level = 5 WHERE user_id = ? AND drone_key = ?", (self.user_id, "maintenance_drone"))
            db.execute(
                "UPDATE user_factory_facilities SET last_claimed_at = ? WHERE user_id = ? AND facility_key = 'scrap_collector'",
                (int(time.time()) - 20 * 3600, self.user_id),
            )
            view = game_app.get_user_factory_view(db, self.user_id, ensure=False)
            self.assertEqual(view["storage_cap_hours"], 15)
            scrap = next(item for item in view["facilities"] if item["facility_key"] == "scrap_collector")
            self.assertEqual(scrap["pending_points"], 75)

    def test_drone_links_and_no_combat_stat_effect_types(self):
        client = self._client()
        factory_html = client.get("/factory").get_data(as_text=True)
        self.assertIn("/drone", factory_html)
        home_html = client.get("/home").get_data(as_text=True)
        self.assertIn("ドローン研究所", home_html)
        self.assertIn("/drone", home_html)
        combat_stats = {"hp", "atk", "def", "spd", "acc", "cri"}
        self.assertTrue(all(item["effect_type"] not in combat_stats for item in game_app.DRONE_DEFS))


if __name__ == "__main__":
    unittest.main()
