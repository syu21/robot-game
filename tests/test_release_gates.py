import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
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
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 0, 0, 20, 5)
                """,
                ("release_user", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("release_user",)).fetchone()["id"])
            game_app.initialize_new_user(db, self.user_id)
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 1, 1, 20, 5)
                """,
                ("release_admin", "x", now),
            )
            self.admin_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("release_admin",)).fetchone()["id"])
            game_app.initialize_new_user(db, self.admin_id)
            db.commit()

    def tearDown(self):
        game_app.app.config.pop("BYPASS_RELEASE_GATES_IN_TESTS", None)
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self, *, admin=False):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            if admin:
                session["user_id"] = self.admin_id
                session["username"] = "release_admin"
            else:
                session["user_id"] = self.user_id
                session["username"] = "release_user"
        return client

    def test_lab_is_hidden_for_public_until_released(self):
        user_client = self._client()
        admin_client = self._client(admin=True)

        hidden = user_client.get("/lab", follow_redirects=False)
        self.assertEqual(hidden.status_code, 302)
        self.assertIn("/home", hidden.headers.get("Location", ""))

        visible_for_admin = admin_client.get("/lab")
        self.assertEqual(visible_for_admin.status_code, 200)

        home = user_client.get("/home")
        self.assertEqual(home.status_code, 200)
        html = home.get_data(as_text=True)
        self.assertNotIn("実験室", html)

    def test_layer4_and_layer5_are_hidden_until_released(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT id, is_admin, max_unlocked_layer FROM users WHERE id = ?", (self.user_id,)).fetchone()
            admin = db.execute("SELECT id, is_admin, max_unlocked_layer FROM users WHERE id = ?", (self.admin_id,)).fetchone()
            self.assertFalse(game_app._is_area_unlocked(user, "layer_4_forge", db=db))
            self.assertFalse(game_app._is_area_unlocked(user, "layer_5_labyrinth", db=db))
            self.assertTrue(game_app._is_area_unlocked(admin, "layer_4_forge", db=db))
            self.assertTrue(game_app._is_area_unlocked(admin, "layer_5_labyrinth", db=db))

    def test_admin_can_toggle_release_flags_and_dependencies(self):
        admin_client = self._client(admin=True)
        user_client = self._client()

        resp = admin_client.post(
            "/admin/release",
            data={"feature_key": "lab", "state": "public"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("一般公開しました", resp.get_data(as_text=True))
        self.assertEqual(user_client.get("/lab").status_code, 200)

        admin_client.post(
            "/admin/release",
            data={"feature_key": "layer5", "state": "public"},
            follow_redirects=True,
        )
        with game_app.app.app_context():
            db = game_app.get_db()
            flags = {
                row["key"]: int(row["is_public"] or 0)
                for row in db.execute("SELECT key, is_public FROM release_flags").fetchall()
            }
            self.assertEqual(flags.get("layer4"), 1)
            self.assertEqual(flags.get("layer5"), 1)
            user = db.execute("SELECT id, is_admin, max_unlocked_layer FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertTrue(game_app._is_area_unlocked(user, "layer_4_forge", db=db))
            self.assertTrue(game_app._is_area_unlocked(user, "layer_5_labyrinth", db=db))

        admin_client.post(
            "/admin/release",
            data={"feature_key": "layer4", "state": "private"},
            follow_redirects=True,
        )
        with game_app.app.app_context():
            db = game_app.get_db()
            flags = {
                row["key"]: int(row["is_public"] or 0)
                for row in db.execute("SELECT key, is_public FROM release_flags").fetchall()
            }
            self.assertEqual(flags.get("layer4"), 0)
            self.assertEqual(flags.get("layer5"), 0)

    def test_records_hide_unreleased_layer_records(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    now,
                    game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                    json.dumps({"area_key": "layer_4_forge"}, ensure_ascii=False),
                    self.user_id,
                ),
            )
            db.commit()

        user_client = self._client()
        hidden = user_client.get("/records")
        self.assertEqual(hidden.status_code, 200)
        self.assertNotIn("第四層", hidden.get_data(as_text=True))

        admin_client = self._client(admin=True)
        admin_client.post(
            "/admin/release",
            data={"feature_key": "layer4", "state": "public"},
            follow_redirects=True,
        )
        visible = user_client.get("/records")
        self.assertEqual(visible.status_code, 200)
        self.assertIn("第四層", visible.get_data(as_text=True))
