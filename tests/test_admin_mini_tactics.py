import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db
from services.mini_tactics import (
    build_initial_map,
    build_initial_units,
    manhattan,
    simulate_mini_tactics_battle,
)


class AdminMiniTacticsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        self.old_testing = game_app.app.config.get("TESTING")
        self.old_bypass = game_app.app.config.get("BYPASS_RELEASE_GATES_IN_TESTS")
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
                INSERT INTO users (username, password_hash, created_at, is_admin)
                VALUES (?, ?, ?, 0)
                """,
                ("mini_user", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("mini_user",)).fetchone()["id"])
            game_app.initialize_new_user(db, self.user_id)
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin)
                VALUES (?, ?, ?, 1)
                """,
                ("mini_admin", "x", now),
            )
            self.admin_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("mini_admin",)).fetchone()["id"])
            game_app.initialize_new_user(db, self.admin_id)
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        game_app.app.config["TESTING"] = self.old_testing
        if self.old_bypass is None:
            game_app.app.config.pop("BYPASS_RELEASE_GATES_IN_TESTS", None)
        else:
            game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = self.old_bypass
        self.tmpdir.cleanup()

    def _client(self, *, admin=False, login=True):
        client = game_app.app.test_client()
        if login:
            with client.session_transaction() as session:
                if admin:
                    session["user_id"] = self.admin_id
                    session["username"] = "mini_admin"
                else:
                    session["user_id"] = self.user_id
                    session["username"] = "mini_user"
        return client

    def test_admin_only_access(self):
        anon = self._client(login=False).get("/admin/lab/mini-tactics")
        self.assertIn(anon.status_code, (302, 401))

        user = self._client().get("/admin/lab/mini-tactics")
        self.assertEqual(user.status_code, 404)

        admin = self._client(admin=True).get("/admin/lab/mini-tactics")
        self.assertEqual(admin.status_code, 200)
        self.assertIn("ミニロボ戦術試験", admin.get_data(as_text=True))
        self.assertIn("試験開始", admin.get_data(as_text=True))

    def test_team_page_is_admin_only(self):
        anon = self._client(login=False).get("/admin/lab/mini-tactics/team")
        self.assertIn(anon.status_code, (302, 401))

        user = self._client().get("/admin/lab/mini-tactics/team")
        self.assertEqual(user.status_code, 404)

        admin = self._client(admin=True).get("/admin/lab/mini-tactics/team")
        self.assertEqual(admin.status_code, 200)
        html = admin.get_data(as_text=True)
        self.assertIn("戦術チーム確認", html)
        self.assertIn("レンタル機", html)

    def test_team_page_uses_existing_mini_robot_and_rentals(self):
        client = self._client(admin=True)
        resp = client.post("/lab/mini/select", data={"species_key": "phoenix"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        page = client.get("/admin/lab/mini-tactics/team")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("フェニックス幼体", html)
        self.assertIn("育成個体", html)
        self.assertIn("レンタル", html)

    def test_start_uses_existing_mini_robot_with_rental_fill(self):
        client = self._client(admin=True)
        client.post("/lab/mini/select", data={"species_key": "hydra"}, follow_redirects=True)
        resp = client.post("/admin/lab/mini-tactics/start", data={"seed": "222"}, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT units_json FROM mini_tactics_battles ORDER BY id DESC LIMIT 1").fetchone()
            units = json.loads(row["units_json"])
            allies = [u for u in units if u["side"] == "ally"]
            self.assertEqual(len(allies), 3)
            self.assertEqual(allies[0]["source"], "owned")
            self.assertEqual(allies[0]["species_key"], "hydra")
            self.assertEqual(allies[0]["ai_type"], "guardian")
            self.assertEqual(len([u for u in allies if u["source"] == "rental"]), 2)

    def test_start_without_mini_robot_uses_three_rentals(self):
        client = self._client(admin=True)
        resp = client.post("/admin/lab/mini-tactics/start", data={"seed": "333"}, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT units_json FROM mini_tactics_battles ORDER BY id DESC LIMIT 1").fetchone()
            units = json.loads(row["units_json"])
            allies = [u for u in units if u["side"] == "ally"]
            self.assertEqual(len(allies), 3)
            self.assertTrue(all(u["source"] == "rental" for u in allies))

    def test_existing_mini_tactics_battle_without_source_still_watches(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            cur = db.execute(
                """
                INSERT INTO mini_tactics_battles
                (seed, status, map_json, units_json, frames_json, created_at, created_by_user_id)
            