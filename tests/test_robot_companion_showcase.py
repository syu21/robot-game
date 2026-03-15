import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class RobotCompanionShowcaseTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 1, 0, 1)
                """,
                ("owner_user", "x", now),
            )
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 1, 0, 1)
                """,
                ("liker_user", "x", now),
            )
            self.owner_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("owner_user",),
            ).fetchone()["id"]
            self.liker_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("liker_user",),
            ).fetchone()["id"]
            game_app.initialize_new_user(db, self.owner_id)
            game_app.initialize_new_user(db, self.liker_id)
            self.owner_robot_id = db.execute(
                "SELECT active_robot_id FROM users WHERE id = ?",
                (self.owner_id,),
            ).fetchone()["active_robot_id"]
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client_for(self, user_id, username):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = user_id
            session["username"] = username
        return client

    def test_robot_history_updates_once_for_same_submission(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                UPDATE enemies
                SET hp = 1, atk = 0, def = 0, spd = 0, acc = 0, cri = 0
                WHERE is_active = 1 AND is_boss = 0 AND tier = 1
                """
            )
            db.commit()
        client = self._client_for(self.owner_id, "owner_user")
        home = client.get("/home")
        self.assertEqual(home.status_code, 200)
        html = home.get_data(as_text=True)
        marker = 'name="explore_submission_id" value="'
        self.assertIn(marker, html)
        sid = html.split(marker, 1)[1].split('"', 1)[0]
        r1 = client.post("/explore", data={"area_key": "layer_1", "explore_submission_id": sid})
        self.assertEqual(r1.status_code, 200)
        r2 = client.post("/explore", data={"area_key": "layer_1", "explore_submission_id": sid})
        self.assertEqual(r2.status_code, 200)
        with game_app.app.app_context():
            db = game_app.get_db()
            hist = db.execute(
                "SELECT battles_total, wins_total, losses_total FROM robot_history WHERE robot_id = ?",
                (int(self.owner_robot_id),),
            ).fetchone()
            self.assertIsNotNone(hist)
            self.assertEqual(int(hist["battles_total"]), 1)
            self.assertEqual(int(hist["wins_total"]), 1)
            self.assertEqual(int(hist["losses_total"]), 0)

    def test_showcase_like_toggle_does_not_duplicate(self):
        client = self._client_for(self.liker_id, "liker_user")
        first = client.post(f"/showcase/{int(self.owner_robot_id)}/like", data={"sort": "new"})
        self.assertEqual(first.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            count1 = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM showcase_votes
                WHERE robot_id = ? AND user_id = ? AND vote_type = 'like'
                """,
                (int(self.owner_robot_id), int(self.liker_id)),
            ).fetchone()["c"]
            self.assertEqual(int(count1), 1)
        second = client.post(f"/showcase/{int(self.owner_robot_id)}/like", data={"sort": "new"})
        self.assertEqual(second.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            count2 = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM showcase_votes
                WHERE robot_id = ? AND user_id = ? AND vote_type = 'like'
                """,
                (int(self.owner_robot_id), int(self.liker_id)),
            ).fetchone()["c"]
            self.assertEqual(int(count2), 0)


if __name__ == "__main__":
    unittest.main()
