import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class ExploreAreaLockTests(unittest.TestCase):
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
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins) VALUES (?, ?, ?, 0, 0)",
                ("lock_tester", "x", now),
            )
            db.commit()
            self.user_id = db.execute("SELECT id FROM users WHERE username = ?", ("lock_tester",)).fetchone()["id"]

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def test_explore_locked_area_redirects_home(self):
        with game_app.app.test_client() as client:
            with client.session_transaction() as session:
                session["user_id"] = self.user_id
                session["username"] = "lock_tester"

            resp = client.post("/explore", data={"area_key": "layer_3"}, follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/home", resp.headers.get("Location", ""))

            home = client.get("/home")
            self.assertEqual(home.status_code, 200)
            self.assertIn("未解放", home.get_data(as_text=True))

    def test_explore_locked_layer2_rush_redirects_home(self):
        with game_app.app.test_client() as client:
            with client.session_transaction() as session:
                session["user_id"] = self.user_id
                session["username"] = "lock_tester"

            resp = client.post("/explore", data={"area_key": "layer_2_rush"}, follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/home", resp.headers.get("Location", ""))

            home = client.get("/home")
            self.assertEqual(home.status_code, 200)
            self.assertIn("未解放", home.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
