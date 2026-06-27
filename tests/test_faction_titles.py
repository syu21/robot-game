import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactionTitleTests(unittest.TestCase):
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
            self.admin_id = self._create_user(db, "title_admin", now, "aurix", is_admin=1)
            self.aurix_user = self._create_user(db, "title_aurix", now, "aurix")
            self.ignis_user = self._create_user(db, "title_ignis", now, "ignis")
            self.ventra_user = self._create_user(db, "title_ventra", now, "ventra")
            self.week_key = game_app.get_current_week_key()
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _create_user(self, db, username, now, faction, *, is_admin=0):
        db.execute(
            """
            INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer, faction)
            VALUES (?, ?, ?, ?, 0, 1, ?)
            """,
            (username, "x", now, int(is_admin), faction),
        )
        user_id = int(db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"])
        game_app.initialize_new_user(db, user_id)
        return user_id

    def _client(self, user_id=None, username="title_aurix"):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user_id or self.aurix_user)
            session["username"] = username
        return client

    def _seed_weekly_sources(self, db):
        db.execute(
            """
            INSERT INTO faction_guardian_attacks
            (week_key, attacker_faction_key, target_faction_key, guardian_id, attacker_user_id,
             source_event_type, source_event_id, request_id, damage, created_at)
            VALUES (?, 'aurix', 'ignis', 1, ?, 'test.title.guardian', 1, 'title-guardian', 150, ?)
            """,
            (self.week_key, self.aurix_user, game_app.now_str()),
        )
        db.execute(
            """
            INSERT INTO faction_representatives
            (week_key, faction_key, user_id, robot_id, robot_name, selection_type, selection_reason, created_at, updated_at)
            VALUES (?, 'ignis', ?, 1, 'Title Rep', 'auto', '守護戦貢献', ?, ?)
            """,
            (self.week_key, self.ignis_user, game_app.now_str(), game_app.now_str()),
        )
        db.execute(
            """
            INSERT INTO faction_facility_contributions
            (week_key, faction_key, user_id, source_event_type, source_event_id, material_amount, created_at)
            VALUES (?, 'ventra', ?, 'test.title.facility', 1, 90, ?)
            """,
            (self.week_key, self.ventra_user, game_app.now_str()),
        )
        db.execute(
            """
            INSERT INTO faction_guardians
            (week_key, faction_key, guardian_name, source_type, author_user_id, max_hp, current_hp, created_at, updated_at)
            VALUES (?, 'aurix', 'Title Guardian', 'submission', ?, 1000, 1000, ?, ?)
            """,
            (self.week_key, self.aurix_user, game_app.now_str(), game_app.now_str()),
        )

    def test_tables_and_manual_grant_are_idempotent(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            title_cols = {row["name"] for row in db.execute("PRAGMA table_info(user_faction_titles)").fetchall()}
            log_cols = {row["name"] for row in db.execute("PRAGMA table_info(faction_title_grant_logs)").fetchall()}
            self.assertIn("is_equipped", title_cols)
            self.assertIn("granted_count", log_cols)
            first = game_app.grant_user_faction_title(db, self.aurix_user, "aurix", "guardian_main", self.week_key, "manual")
            second = game_app.grant_user_faction_title(db, self.aurix_user, "aurix", "guardian_main", self.week_key, "manual")
            self.assertTrue(first["granted"])
            self.assertFalse(second["granted"])
            with self.assertRaises(ValueError):
                game_app.grant_user_faction_title(db, self.aurix_user, "aurix", "missing_title", self.week_key, "manual")

    def test_weekly_title_grant_sources_and_world_log_are_idempotent(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._seed_weekly_sources(db)
            first = game_app.grant_weekly_faction_titles(db, self.week_key)
            second = game_app.grant_weekly_faction_titles(db, self.week_key)
            self.assertGreaterEqual(first["granted_count"], 4)
            self.assertEqual(second["granted_count"], 0)
            title_keys = {
                row["title_key"]
                for row in db.execute("SELECT title_key FROM user_faction_titles WHERE week_key = ?", (self.week_key,)).fetchall()
            }
            self.assertIn("guardian_main", title_keys)
            self.assertIn("faction_representative", title_keys)
            self.assertIn("facility_leader", title_keys)
            self.assertIn("guardian_author", title_keys)
            world_count = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ?",
                (game_app.FACTION_TITLE_GRANT_RESULT_EVENT_TYPE,),
            ).fetchone()["c"]
            self.assertEqual(world_count, 1)

    def test_equip_pages_admin_and_stats_are_safe(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            before = db.execute("SELECT * FROM robot_instances WHERE user_id = ? ORDER BY id LIMIT 1", (self.aurix_user,)).fetchone()
            self._seed_weekly_sources(db)
            game_app.grant_weekly_faction_titles(db, self.week_key)
            title = db.execute(
                "SELECT * FROM user_faction_titles WHERE user_id = ? ORDER BY id LIMIT 1",
                (self.aurix_user,),
            ).fetchone()
            after = db.execute("SELECT * FROM robot_instances WHERE user_id = ? ORDER BY id LIMIT 1", (self.aurix_user,)).fetchone()
            self.assertEqual(dict(before), dict(after))
            db.commit()

        client = self._client()
        self.assertIn("あなたの陣営称号", client.get("/faction").get_data(as_text=True))
        self.assertIn("今週の陣営称号", client.get("/world").get_data(as_text=True))
        self.assertIn("今週の陣営称号", client.get("/comms/faction").get_data(as_text=True))
        self.assertEqual(client.post("/faction/title/equip", data={"title_id": int(title["id"])}).status_code, 302)
        self.assertEqual(client.post("/faction/title/equip", data={"title_id": 999999}).status_code, 302)
        self.assertEqual(client.get("/admin/factions/titles").status_code, 403)

        admin = self._client(self.admin_id, "title_admin")
        self.assertEqual(admin.get("/admin/factions/titles").status_code, 200)
        self.assertEqual(admin.post("/admin/factions/titles/grant-weekly", data={"week_key": self.week_key}).status_code, 302)
        self.assertEqual(
            admin.post(
                "/admin/factions/titles/grant-manual",
                data={"week_key": self.week_key, "user_id": self.ignis_user, "faction_key": "ignis", "title_key": "guardian_analyst"},
            ).status_code,
            302,
        )


if __name__ == "__main__":
    unittest.main()
