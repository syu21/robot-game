import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactionWeeklyQuestTests(unittest.TestCase):
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
            self.admin_id = self._create_user(db, "quest_admin", now, "aurix", is_admin=1)
            self.aurix_user = self._create_user(db, "quest_aurix", now, "aurix")
            self.ignis_user = self._create_user(db, "quest_ignis", now, "ignis")
            self.week_key = game_app.get_current_week_key()
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _create_user(self, db, username, now, faction, *, is_admin=0):
        db.execute(
            """
            INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer, faction, coins)
            VALUES (?, ?, ?, ?, 0, 1, ?, 0)
            """,
            (username, "x", now, int(is_admin), faction),
        )
        user_id = int(db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"])
        game_app.initialize_new_user(db, user_id)
        return user_id

    def _client(self, user_id=None, username="quest_aurix"):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user_id or self.aurix_user)
            session["username"] = username
        return client

    def _quest(self, db, faction_key, quest_key):
        return db.execute(
            "SELECT * FROM faction_weekly_quests WHERE week_key = ? AND faction_key = ? AND quest_key = ?",
            (self.week_key, faction_key, quest_key),
        ).fetchone()

    def test_tables_generate_event_and_idempotent(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertIn("quest_key", {row["name"] for row in db.execute("PRAGMA table_info(faction_weekly_quests)").fetchall()})
            self.assertIn("contribution_value", {row["name"] for row in db.execute("PRAGMA table_info(faction_weekly_quest_participants)").fetchall()})
            self.assertIn("payload_json", {row["name"] for row in db.execute("PRAGMA table_info(faction_weekly_quest_logs)").fetchall()})
            game_app.set_faction_weekly_event(db, self.week_key, "facility_focus", admin_user_id=self.admin_id)
            game_app.activate_faction_weekly_event(db, self.week_key, admin_user_id=self.admin_id)
            first = game_app.generate_faction_weekly_quests(db, self.week_key)
            second = game_app.generate_faction_weekly_quests(db, self.week_key)
            self.assertEqual(first["created_count"], 9)
            self.assertEqual(second["created_count"], 0)
            quest_keys = {row["quest_key"] for row in db.execute("SELECT quest_key FROM faction_weekly_quests WHERE faction_key = 'aurix'").fetchall()}
            self.assertEqual(quest_keys, {"explore_basic", "boss_basic", "facility_basic"})

    def test_progress_completion_world_log_and_reward_claim(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.generate_faction_weekly_quests(db, self.week_key)
            db.execute("UPDATE faction_weekly_quests SET target_value = 2 WHERE quest_key = 'explore_basic'")
            before_robot = db.execute("SELECT * FROM robot_instances WHERE user_id = ? ORDER BY id LIMIT 1", (self.aurix_user,)).fetchone()
            before_coins = int(db.execute("SELECT coins FROM users WHERE id = ?", (self.aurix_user,)).fetchone()["coins"])
            game_app.add_faction_quest_progress(db, self.aurix_user, "aurix", "explore_count", 1, "test", 1, self.week_key)
            game_app.add_faction_quest_progress(db, self.aurix_user, "aurix", "explore_count", 1, "test", 2, self.week_key)
            quest = self._quest(db, "aurix", "explore_basic")
            self.assertEqual(quest["status"], "completed")
            self.assertEqual(int(quest["current_value"]), 2)
            world_count = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ?",
                (game_app.FACTION_WEEKLY_QUEST_COMPLETED_EVENT_TYPE,),
            ).fetchone()["c"]
            self.assertEqual(world_count, 1)

            no_contrib = game_app.claim_faction_weekly_quest_reward(db, self.ignis_user, int(quest["id"]))
            self.assertFalse(no_contrib["ok"])
            claim = game_app.claim_faction_weekly_quest_reward(db, self.aurix_user, int(quest["id"]))
            again = game_app.claim_faction_weekly_quest_reward(db, self.aurix_user, int(quest["id"]))
            self.assertTrue(claim["ok"])
            self.assertFalse(again["ok"])
            after_coins = int(db.execute("SELECT coins FROM users WHERE id = ?", (self.aurix_user,)).fetchone()["coins"])
            self.assertEqual(after_coins, before_coins + int(quest["reward_coins"]))
            after_robot = db.execute("SELECT * FROM robot_instances WHERE user_id = ? ORDER BY id LIMIT 1", (self.aurix_user,)).fetchone()
            self.assertEqual(dict(before_robot), dict(after_robot))

    def test_existing_facility_sync_advances_quest_types_and_finalize(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.generate_faction_weekly_quests(db, self.week_key)
            db.execute("UPDATE faction_weekly_quests SET target_value = 1 WHERE quest_key IN ('boss_basic', 'guardian_basic')")
            boss = game_app.grant_faction_facility_material(db, "aurix", self.aurix_user, game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"], 501, 20, self.week_key)
            self.assertTrue(boss["granted"])
            self.assertEqual(self._quest(db, "aurix", "boss_basic")["status"], "completed")
            db.execute(
                """
                INSERT INTO faction_guardian_attacks
                (week_key, attacker_faction_key, target_faction_key, guardian_id, attacker_user_id,
                 source_event_type, source_event_id, request_id, damage, created_at)
                VALUES (?, 'aurix', 'ignis', 1, ?, 'test.guardian', 1, 'quest-guardian', 50, ?)
                """,
                (self.week_key, self.aurix_user, game_app.now_str()),
            )
            game_app.sync_faction_facility_materials(db, self.week_key)
            self.assertEqual(self._quest(db, "aurix", "guardian_basic")["status"], "completed")
            game_app.set_faction_weekly_event(db, self.week_key, "territory_focus", admin_user_id=self.admin_id)
            game_app.activate_faction_weekly_event(db, self.week_key, admin_user_id=self.admin_id)
            game_app.generate_faction_weekly_quests(db, self.week_key)
            db.execute("UPDATE faction_weekly_quests SET target_value = 1 WHERE quest_key = 'territory_basic'")
            game_app.calculate_faction_territory_scores(db, self.week_key)
            self.assertEqual(self._quest(db, "aurix", "territory_basic")["status"], "completed")
            first = game_app.finalize_faction_weekly_quests(db, self.week_key)
            second = game_app.finalize_faction_weekly_quests(db, self.week_key)
            self.assertTrue(first["emitted_world_event"])
            self.assertFalse(second["emitted_world_event"])

    def test_pages_and_admin_routes_are_safe(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.generate_faction_weekly_quests(db, self.week_key)
            db.commit()
        client = self._client()
        self.assertIn("今週の陣営クエスト", client.get("/faction").get_data(as_text=True))
        self.assertIn("今週の陣営クエスト状況", client.get("/world").get_data(as_text=True))
        self.assertIn("今週の陣営クエスト", client.get("/comms/faction").get_data(as_text=True))
        self.assertEqual(client.get("/admin/factions/quests").status_code, 403)
        admin = self._client(self.admin_id, "quest_admin")
        self.assertEqual(admin.get("/admin/factions/quests").status_code, 200)
        self.assertEqual(admin.post("/admin/factions/quests/generate", data={"week_key": self.week_key}).status_code, 302)
        self.assertEqual(admin.post("/admin/factions/quests/finalize", data={"week_key": self.week_key}).status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            quest_id = int(self._quest(db, "aurix", "explore_basic")["id"])
        self.assertEqual(admin.post("/admin/factions/quests/cancel", data={"quest_id": quest_id}).status_code, 302)


if __name__ == "__main__":
    unittest.main()
