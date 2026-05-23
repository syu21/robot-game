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

    def test_start_creates_battle_payloads(self):
        client = self._client(admin=True)
        resp = client.post("/admin/lab/mini-tactics/start", data={"seed": "12345"}, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertRegex(resp.headers.get("Location", ""), r"/admin/lab/mini-tactics/watch/\d+")

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT * FROM mini_tactics_battles ORDER BY id DESC LIMIT 1").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(int(row["seed"]), 12345)
            self.assertEqual(row["status"], "finished")
            self.assertEqual(int(row["created_by_user_id"]), self.admin_id)
            map_payload = json.loads(row["map_json"])
            units_payload = json.loads(row["units_json"])
            frames_payload = json.loads(row["frames_json"])
            self.assertEqual(int(map_payload["width"]), 5)
            self.assertEqual(int(map_payload["height"]), 5)
            self.assertTrue(frames_payload)
            self.assertEqual(len([u for u in units_payload if u["side"] == "ally"]), 3)
            self.assertEqual(len([u for u in units_payload if u["side"] == "enemy"]), 3)
            self.assertTrue(all("max_hp" in u and "atk" in u and "def" in u for u in units_payload))

        page = client.get(resp.headers["Location"])
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("miniTacticsBoard", html)
        self.assertIn("miniTacticsRoster", html)
        self.assertIn("最初から再生", html)

    def test_simulation_bounds_collision_and_assault(self):
        map_payload = build_initial_map()
        units_payload = build_initial_units()
        initial_by_id = {u["unit_id"]: dict(u) for u in units_payload}
        frames = simulate_mini_tactics_battle(777, map_payload, units_payload)
        self.assertLessEqual(len(frames), 10)

        width = int(map_payload["width"])
        height = int(map_payload["height"])
        for frame in frames:
            occupied = set()
            for unit in frame["units"]:
                pos = (int(unit["x"]), int(unit["y"]))
                self.assertGreaterEqual(pos[0], 0)
                self.assertGreaterEqual(pos[1], 0)
                self.assertLess(pos[0], width)
                self.assertLess(pos[1], height)
                self.assertNotIn(pos, occupied)
                occupied.add(pos)

        first_frame = frames[0]
        for unit in first_frame["units"]:
            before = initial_by_id[unit["unit_id"]]
            before_enemies = [u for u in initial_by_id.values() if u["side"] != before["side"]]
            after_enemies = [u for u in first_frame["units"] if u["side"] != unit["side"]]
            before_distance = min(manhattan(before, enemy) for enemy in before_enemies)
            after_distance = min(manhattan(unit, enemy) for enemy in after_enemies)
            self.assertLessEqual(after_distance, before_distance)

    def test_adjacent_units_attack_and_reduce_hp(self):
        map_payload = build_initial_map()
        units_payload = [
            {
                "unit_id": "ally_attacker",
                "side": "ally",
                "name": "ケルベロス",
                "species_key": "cerberus",
                "x": 1,
                "y": 1,
                "hp": 18,
                "max_hp": 18,
                "atk": 5,
                "def": 2,
                "defeated": False,
                "ai_type": "assault",
                "image_path": "",
                "direction": "right",
            },
            {
                "unit_id": "enemy_target",
                "side": "enemy",
                "name": "ダミーA",
                "species_key": "dummy_a",
                "x": 2,
                "y": 1,
                "hp": 12,
                "max_hp": 12,
                "atk": 3,
                "def": 1,
                "defeated": False,
                "ai_type": "assault",
                "image_path": "",
                "direction": "left",
            },
        ]
        frame = simulate_mini_tactics_battle(1, map_payload, units_payload)[0]
        enemy = next(u for u in frame["units"] if u["unit_id"] == "enemy_target")
        self.assertEqual(enemy["hp"], 8)
        self.assertFalse(enemy["defeated"])
        self.assertTrue(any("ケルベロスがダミーAを攻撃、4ダメージ" in line for line in frame["logs"]))

    def test_defeated_unit_stops_acting_and_ally_win(self):
        map_payload = build_initial_map()
        units_payload = [
            {
                "unit_id": "ally_attacker",
                "side": "ally",
                "name": "ケルベロス",
                "species_key": "cerberus",
                "x": 1,
                "y": 1,
                "hp": 18,
                "max_hp": 18,
                "atk": 5,
                "def": 2,
                "defeated": False,
                "ai_type": "assault",
                "image_path": "",
                "direction": "right",
            },
            {
                "unit_id": "enemy_target",
                "side": "enemy",
                "name": "ダミーA",
                "species_key": "dummy_a",
                "x": 2,
                "y": 1,
                "hp": 4,
                "max_hp": 12,
                "atk": 3,
                "def": 1,
                "defeated": False,
                "ai_type": "assault",
                "image_path": "",
                "direction": "left",
            },
        ]
        frame = simulate_mini_tactics_battle(1, map_payload, units_payload)[0]
        enemy = next(u for u in frame["units"] if u["unit_id"] == "enemy_target")
        self.assertEqual(enemy["hp"], 0)
        self.assertTrue(enemy["defeated"])
        self.assertEqual(frame["result"], "ally_win")
        self.assertTrue(any("ダミーAを撃破" in line for line in frame["logs"]))
        self.assertTrue(any("味方側の勝利" in line for line in frame["logs"]))
        self.assertFalse(any("ダミーAが" in line for line in frame["logs"]))

    def test_not_exposed_on_public_lab(self):
        html = self._client().get("/lab").get_data(as_text=True)
        self.assertNotIn("ミニロボ戦術試験", html)
        self.assertNotIn("/admin/lab/mini-tactics", html)

    def test_admin_lab_shows_mini_tactics_link(self):
        html = self._client(admin=True).get("/lab").get_data(as_text=True)
        self.assertIn("ミニロボ戦術試験", html)
        self.assertIn("/admin/lab/mini-tactics", html)


if __name__ == "__main__":
    unittest.main()
