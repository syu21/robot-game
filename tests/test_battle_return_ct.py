import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class BattleReturnCooldownTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        init_db.main()
        game_app.app.config["TESTING"] = True

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _create_user(self, username, is_admin=0):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            cur = db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins) VALUES (?, ?, ?, ?, 0)",
                (username, "x", now, int(is_admin)),
            )
            user_id = int(cur.lastrowid)
            game_app.initialize_new_user(db, user_id)
            db.commit()
            return user_id

    def _login(self, client, user_id, username):
        with client.session_transaction() as sess:
            sess["user_id"] = int(user_id)
            sess["username"] = username

    def test_non_admin_sees_explore_return_cooldown(self):
        user_id = self._create_user("ct_user", is_admin=0)
        with game_app.app.test_client() as client:
            self._login(client, user_id, "ct_user")
            resp = client.post("/explore", data={"area_key": "layer_1"})
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn('id="explore-return-btn"', html)
            self.assertIn("もう一度出撃（あと", html)
            self.assertIn("disabled", html)

    def test_admin_can_return_to_explore_without_cooldown_lock(self):
        user_id = self._create_user("ct_admin", is_admin=1)
        with game_app.app.test_client() as client:
            self._login(client, user_id, "ct_admin")
            resp = client.post("/explore", data={"area_key": "layer_1"})
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn('id="explore-return-btn"', html)
            self.assertIn(">もう一度出撃<", html)
            self.assertNotIn("もう一度出撃（あと", html)


if __name__ == "__main__":
    unittest.main()
