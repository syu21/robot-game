import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class MaterialsTests(unittest.TestCase):
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
                VALUES (?, ?, ?, 0, 0, 1, 1234)
                """,
                ("material_user", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("material_user",)).fetchone()["id"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "material_user"
        return client

    def test_material_masters_are_seeded(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            result = game_app.ensure_material_masters(db, user_id=self.user_id, request_id="material-seed")
            db.commit()
            self.assertEqual(result["created_count"], 4)
            rows = db.execute("SELECT material_key FROM material_masters ORDER BY sort_order").fetchall()
            self.assertEqual([row["material_key"] for row in rows], ["scrap", "circuit_board", "coolant", "ai_chip"])
            event = db.execute(
                "SELECT id FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["MATERIAL_ENSURE_DEFAULTS"]),
            ).fetchone()
            self.assertIsNotNone(event)

    def test_dispatch_start_fixes_material_rewards_and_claim_grants_once(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_companions(db, self.user_id)
            coins_before = int(db.execute("SELECT coins FROM users WHERE id = ?", (self.user_id,)).fetchone()["coins"])
            start = game_app.start_companion_dispatch(db, self.user_id, "scrap_search", request_id="material-start")
            self.assertTrue(start["ok"])
            dispatch = db.execute(
                "SELECT * FROM user_companion_dispatches WHERE id = ?",
                (int(start["dispatch_id"]),),
            ).fetchone()
            fixed_rewards = game_app._parse_dispatch_material_rewards(dispatch["material_rewards_json"])
            self.assertGreaterEqual(len(fixed_rewards), 2)
            self.assertIn("scrap", {row["material_key"] for row in fixed_rewards})
            self.assertIn("circuit_board", {row["material_key"] for row in fixed_rewards})

            db.execute(
                "UPDATE user_companion_dispatches SET completes_at = ? WHERE id = ?",
                (int(time.time()) - 1, int(start["dispatch_id"])),
            )
            claim = game_app.claim_companion_dispatch(db, self.user_id, request_id="material-claim")
            self.assertTrue(claim["ok"])
            self.assertEqual(
                [(row["material_key"], row["quantity"]) for row in claim["material_rewards"]],
                [(row["material_key"], row["quantity"]) for row in game_app._dispatch_material_reward_view(db, dispatch["material_rewards_json"])],
            )
            for reward in fixed_rewards:
                row = db.execute(
                    """
                    SELECT quantity
                    FROM user_material_inventory
                    WHERE user_id = ? AND material_key = ?
                    """,
                    (self.user_id, reward["material_key"]),
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(int(row["quantity"]), int(reward["quantity"]))

            second_claim = game_app.claim_companion_dispatch(db, self.user_id)
            self.assertFalse(second_claim["ok"])
            for reward in fixed_rewards:
                row = db.execute(
                    "SELECT quantity FROM user_material_inventory WHERE user_id = ? AND material_key = ?",
                    (self.user_id, reward["material_key"]),
                ).fetchone()
                self.assertEqual(int(row["quantity"]), int(reward["quantity"]))

            coins_after = int(db.execute("SELECT coins FROM users WHERE id = ?", (self.user_id,)).fetchone()["coins"])
            self.assertEqual(coins_after, coins_before)
            for event_type in (
                game_app.AUDIT_EVENT_TYPES["MATERIAL_DELTA"],
                game_app.AUDIT_EVENT_TYPES["COMPANION_DISPATCH_MATERIAL_REWARD"],
            ):
                event = db.execute(
                    "SELECT id FROM world_events_log WHERE user_id = ? AND event_type = ?",
                    (self.user_id, event_type),
                ).fetchone()
                self.assertIsNotNone(event)

    def test_factory_materials_page_shows_inventory(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_material_masters(db, user_id=self.user_id)
            game_app.grant_user_material(
                db,
                self.user_id,
                "scrap",
                5,
                source="test",
                source_id=1,
            )
            db.commit()
        html = self._client().get("/factory/materials").get_data(as_text=True)
        self.assertIn("工場素材", html)
        self.assertIn("スクラップ", html)
        self.assertIn("所持 5", html)
        self.assertIn("電子基板", html)


if __name__ == "__main__":
    unittest.main()
