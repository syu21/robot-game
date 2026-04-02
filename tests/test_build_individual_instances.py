import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class BuildIndividualInstanceSelectionTests(unittest.TestCase):
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
                "INSERT INTO users (username, password_hash, created_at, is_admin) VALUES (?, ?, ?, 0)",
                ("build_picker_user", "x", now),
            )
            self.user_id = int(
                db.execute("SELECT id FROM users WHERE username = ?", ("build_picker_user",)).fetchone()["id"]
            )
            game_app.initialize_new_user(db, self.user_id)
            starter_head = db.execute(
                "SELECT * FROM robot_parts WHERE part_type = 'HEAD' AND is_active = 1 ORDER BY id ASC LIMIT 1"
            ).fetchone()
            game_app._create_part_instance_from_master(db, self.user_id, starter_head, plus=0)
            self.head_ids = [
                int(row["id"])
                for row in db.execute(
                    """
                    SELECT pi.id
                    FROM part_instances pi
                    JOIN robot_parts rp ON rp.id = pi.part_id
                    WHERE pi.user_id = ? AND pi.status = 'inventory' AND rp.part_type = 'HEAD' AND rp.key = ?
                    ORDER BY pi.id ASC
                    """,
                    (self.user_id, starter_head["key"]),
                ).fetchall()
            ]
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
            sess["username"] = "build_picker_user"
        return client

    def test_build_lists_duplicate_instances_separately(self):
        client = self._client()
        resp = client.get("/build")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertGreaterEqual(len(self.head_ids), 2)
        self.assertIn(f'value="{self.head_ids[0]}"', html)
        self.assertIn(f'value="{self.head_ids[1]}"', html)
        self.assertIn("同名 1/2", html)
        self.assertIn("同名 2/2", html)
        self.assertIn(f"ID {self.head_ids[0]}", html)
        self.assertIn(f"ID {self.head_ids[1]}", html)
        self.assertNotIn("所持 2", html)


if __name__ == "__main__":
    unittest.main()
