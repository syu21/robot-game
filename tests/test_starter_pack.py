import os
import json
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

    def test_register_redirect_lands_on_first_explore_home_flow(self):
        with game_app.app.test_client() as client:
            resp = client.post(
                "/register",
                data={"username": "starter_flow", "password": "pass123"},
                follow_redirects=True,
            )
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn("出撃準備完了", html)
            self.assertIn("まずは第1層で1勝して、最初のパーツを持ち帰ろう。", html)
            self.assertIn("第1層へ出撃する", html)
            self.assertIn('name="area_key" value="layer_1"', html)
            self.assertIn('name="entry_source" value="next_action_first_explore"', html)
            self.assertEqual(html.count('data-explore-cta="1"'), 1)
            self.assertNotIn('id="intro-guide-modal"', html)

    def test_first_sortie_focus_missing_entry_source_is_inferred_from_home(self):
        with game_app.app.test_client() as client:
            resp = client.post(
                "/register",
                data={"username": "starter_source", "password": "pass123"},
                follow_redirects=True,
            )
            self.assertEqual(resp.status_code, 200)
            explore = client.post(
                "/explore",
                data={"area_key": "layer_1"},
                follow_redirects=False,
            )
            self.assertIn(explore.status_code, {200, 302})

        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT id FROM users WHERE username = ?", ("starter_source",)).fetchone()
            rows = db.execute(
                """
                SELECT event_type, payload_json
                FROM world_events_log
                WHERE user_id = ?
                """,
                (int(user["id"]),),
            ).fetchall()
        payloads = [
            json.loads(row["payload_json"] or "{}")
            for row in rows
            if row["event_type"] == game_app.AUDIT_EVENT_TYPES["EXPLORE_START"]
        ]
        self.assertTrue(any(payload.get("entry_source") == "next_action_first_explore" for payload in payloads))

    def test_first_sortie_focus_ends_after_explore_start(self):
        with game_app.app.test_client() as client:
            resp = client.post(
                "/register",
                data={"username": "starter_done", "password": "pass123"},
                follow_redirects=True,
            )
            self.assertEqual(resp.status_code, 200)
            explore = client.post(
                "/explore",
                data={"area_key": "layer_1", "entry_source": "next_action_first_explore"},
                follow_redirects=False,
            )
            self.assertIn(explore.status_code, {200, 302})
            home = client.get("/home")
            self.assertEqual(home.status_code, 200)
            html = home.get_data(as_text=True)
            self.assertNotIn("出撃準備完了", html)
            self.assertNotIn('name="entry_source" value="next_action_first_explore"', html)

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
            self.assertIn("組み立てる", html)
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
            self.assertIn("組み立てる", before.get_data(as_text=True))
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
