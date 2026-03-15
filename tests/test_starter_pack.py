import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class StarterPackTests(unittest.TestCase):
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

    def _session_login(self, client, user_id, username):
        with client.session_transaction() as session:
            session["user_id"] = user_id
            session["username"] = username

    def test_register_initializes_starter_robot_and_equipment(self):
        with game_app.app.test_client() as client:
            resp = client.post(
                "/register",
                data={"username": "starter_reg", "password": "pass123"},
                follow_redirects=False,
            )
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/home", resp.headers.get("Location", ""))

        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT id, max_unlocked_layer, active_robot_id FROM users WHERE username = ?", ("starter_reg",)).fetchone()
            self.assertIsNotNone(user)
            self.assertEqual(int(user["max_unlocked_layer"]), 1)
            robots = db.execute(
                "SELECT COUNT(*) AS c FROM robot_instances WHERE user_id = ? AND status != 'decomposed'",
                (user["id"],),
            ).fetchone()["c"]
            self.assertGreaterEqual(int(robots), 1)
            self.assertIsNotNone(user["active_robot_id"])
            rip = db.execute(
                "SELECT * FROM robot_instance_parts WHERE robot_instance_id = ?",
                (int(user["active_robot_id"]),),
            ).fetchone()
            self.assertIsNotNone(rip)
            self.assertIsNotNone(rip["head_part_instance_id"])
            self.assertIsNotNone(rip["r_arm_part_instance_id"])
            self.assertIsNotNone(rip["l_arm_part_instance_id"])
            self.assertIsNotNone(rip["legs_part_instance_id"])

    def test_home_shows_build_cta_when_user_has_no_robot(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins) VALUES (?, ?, ?, 0, 0)",
                ("no_robot_user", "x", now),
            )
            db.commit()
            user_id = db.execute("SELECT id FROM users WHERE username = ?", ("no_robot_user",)).fetchone()["id"]

        with game_app.app.test_client() as client:
            self._session_login(client, user_id, "no_robot_user")
            resp = client.get("/home")
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn("ロボを編成する", html)
            self.assertNotIn("スターターパックを受け取る", html)
            self.assertNotIn("探索する", html)

    def test_starter_pack_claim_creates_robot_and_returns_normal_next_action(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins) VALUES (?, ?, ?, 0, 0)",
                ("claim_user", "x", now),
            )
            db.commit()
            user_id = db.execute("SELECT id FROM users WHERE username = ?", ("claim_user",)).fetchone()["id"]

        with game_app.app.test_client() as client:
            self._session_login(client, user_id, "claim_user")
            before = client.get("/home")
            self.assertIn("ロボを編成する", before.get_data(as_text=True))
            claim = client.post("/starter-pack/claim", follow_redirects=True)
            self.assertEqual(claim.status_code, 200)
            html = claim.get_data(as_text=True)
            self.assertNotIn("スターターパックを受け取る", html)
            self.assertIn("陣営選択まで:", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            robots = db.execute(
                "SELECT COUNT(*) AS c FROM robot_instances WHERE user_id = ? AND status != 'decomposed'",
                (user_id,),
            ).fetchone()["c"]
            self.assertEqual(int(robots), 1)

    def test_initialize_new_user_is_idempotent(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins) VALUES (?, ?, ?, 0, 0)",
                ("idempotent_user", "x", now),
            )
            user_id = db.execute("SELECT id FROM users WHERE username = ?", ("idempotent_user",)).fetchone()["id"]
            first = game_app.initialize_new_user(db, user_id)
            second = game_app.initialize_new_user(db, user_id)
            db.commit()
            self.assertTrue(first.get("ok"))
            self.assertTrue(second.get("ok"))

            robots = db.execute(
                "SELECT COUNT(*) AS c FROM robot_instances WHERE user_id = ? AND status != 'decomposed'",
                (user_id,),
            ).fetchone()["c"]
            self.assertEqual(int(robots), 1)

            inv_rows = db.execute(
                """
                SELECT rp.part_type, COUNT(*) AS c
                FROM part_instances pi
                JOIN robot_parts rp ON rp.id = pi.part_id
                WHERE pi.user_id = ? AND pi.status = 'inventory'
                GROUP BY rp.part_type
                """,
                (user_id,),
            ).fetchall()
            counts = {row["part_type"]: int(row["c"] or 0) for row in inv_rows}
            self.assertGreaterEqual(counts.get("HEAD", 0), 1)
            self.assertGreaterEqual(counts.get("RIGHT_ARM", 0), 1)
            self.assertGreaterEqual(counts.get("LEFT_ARM", 0), 1)
            self.assertGreaterEqual(counts.get("LEGS", 0), 1)


if __name__ == "__main__":
    unittest.main()
