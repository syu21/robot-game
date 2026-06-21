import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class AdminFactionCommsTests(unittest.TestCase):
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
            self.admin_id = self._create_user(db, "comms_admin", now, "aurix", is_admin=1)
            self.user_id = self._create_user(db, "comms_user", now, "aurix")
            self._insert_message(db, self.user_id, "comms_user", "faction_aurix", "aurix note")
            self._insert_message(db, self.user_id, "comms_user", "faction_ignis", "ignis note")
            self._insert_message(db, self.user_id, "comms_user", "faction_ventra", "<script>alert(1)</script>")
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

    def _insert_message(self, db, user_id, username, room_key, message):
        db.execute(
            """
            INSERT INTO chat_messages (user_id, username, room_key, message, created_at, deleted_at)
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (int(user_id), username, room_key, message, game_app.now_str()),
        )

    def _client(self, user_id, username):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user_id)
            session["username"] = username
        return client

    def test_admin_can_view_all_faction_comms(self):
        html = self._client(self.admin_id, "comms_admin").get("/admin/comms/factions").get_data(as_text=True)
        self.assertIn("陣営通信確認", html)
        self.assertIn("aurix note", html)
        self.assertIn("ignis note", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)

    def test_non_admin_is_forbidden(self):
        resp = self._client(self.user_id, "comms_user").get("/admin/comms/factions")
        self.assertEqual(resp.status_code, 403)

    def test_faction_filter_works(self):
        html = self._client(self.admin_id, "comms_admin").get("/admin/comms/factions?faction_key=aurix").get_data(as_text=True)
        self.assertIn("aurix note", html)
        self.assertNotIn("ignis note", html)

    def test_keyword_filter_works(self):
        html = self._client(self.admin_id, "comms_admin").get("/admin/comms/factions?keyword=ignis").get_data(as_text=True)
        self.assertIn("ignis note", html)
        self.assertNotIn("aurix note", html)


if __name__ == "__main__":
    unittest.main()
