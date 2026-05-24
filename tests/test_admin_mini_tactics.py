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
        self.assertIn("laser", html)

    def test_team_page_saves_three_slots_and_rental_fill(self):
        client = self._client(admin=True)
        client.post("/lab/mini/select", data={"species_key": "hydra"}, follow_redirects=True)

        with game_app.app.app_context():
            db = game_app.get_db()
            owned = db.execute(
                "SELECT id FROM user_mini_robots WHERE user_id = ? ORDER BY id LIMIT 1",
                (self.admin_id,),
            ).fetchone()
            mini_robot_id = int(owned["id"])

        resp = client.post(
            "/admin/lab/mini-tactics/team",
            data={
                "slot_1_mini_robot_id": "",
                "slot_2_mini_robot_id": str(mini_robot_id),
                "slot_3_mini_robot_id": "",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            team = db.execute("SELECT * FROM mini_tactics_teams WHERE user_id = ?", (self.admin_id,)).fetchone()
            self.assertIsNone(team["slot_1_mini_robot_id"])
            self.assertEqual(int(team["slot_2_mini_robot_id"]), mini_robot_id)
            self.assertIsNone(team["slot_3_mini_robot_id"])
            units = game_app._mini_tactics_team_units_for_user(db, self.admin_id)
            self.assertEqual(units[0]["source"], "rental")
            self.assertEqual(units[1]["source"], "owned")
            self.assertEqual(units[1]["species_key"], "hydra")
            self.assertEqual(units[2]["source"], "rental")

    def test_team_page_rejects_duplicate_owned_robot(self):
        client = self._client(admin=True)
        client.post("/lab/mini/select", data={"species_key": "cerberus"}, follow_redirects=True)

        with game_app.app.app_context():
            db = game_app.get_db()
            owned = db.execute(
                "SELECT id FROM user_mini_robots WHERE user_id = ? ORDER BY id LIMIT 1",
                (self.admin_id,),
            ).fetchone()
            mini_robot_id = int(owned["id"])

        resp = client.post(
            "/admin/lab/mini-tactics/team",
            data={
                "slot_1_mini_robot_id": str(mini_robot_id),
                "slot_2_mini_robot_id": str(mini_robot_id),
                "slot_3_mini_robot_id": "",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("同じ所持ミニロボ", resp.get_data(as_text=True))

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
                VALUES (?, 'prototype', ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    json.dumps(build_initial_map(), ensure_ascii=False),
                    json.dumps(build_initial_units(), ensure_ascii=False),
                    json.dumps([{"turn": 1, "units": build_initial_units(), "logs": [], "result": None}], ensure_ascii=False),
                    int(time.time()),
                    self.admin_id,
                ),
            )
            battle_id = int(cur.lastrowid)
            db.commit()

        resp = self._client(admin=True).get(f"/admin/lab/mini-tactics/watch/{battle_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("miniTacticsBoard", resp.get_data(as_text=True))

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
            self.assertTrue(all("weapon_type" in u and "range" in u for u in units_payload))
            terrains = [tile["terrain"] for row in map_payload["tiles"] for tile in row]
            self.assertIn("wall", terrains)
            ai_by_species = {u["species_key"]: u["ai_type"] for u in units_payload if u["side"] == "ally"}
            self.assertEqual(ai_by_species["cerberus"], "assault")
            self.assertEqual(ai_by_species["phoenix"], "cautious")
            self.assertEqual(ai_by_species["hydra"], "guardian")
            self.assertTrue(all("ai_type" in u for frame in frames_payload for u in frame["units"]))
            self.assertTrue(all("weapon_type" in u and "range" in u for frame in frames_payload for u in frame["units"]))

        page = client.get(resp.headers["Location"])
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("miniTacticsBoard", html)
        self.assertIn("miniTacticsRoster", html)
        self.assertIn("ai_type", html)
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
                self.assertNotEqual(map_payload["tiles"][pos[1]][pos[0]]["terrain"], "wall")
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
        self.assertTrue(any("ケルベロスが格闘でダミーAを攻撃、4ダメージ" in line for line in frame["logs"]))

    def test_laser_attacks_at_range_two(self):
        map_payload = build_initial_map()
        units_payload = [
            {
                "unit_id": "ally_laser",
                "side": "ally",
                "name": "フェニックス",
                "species_key": "phoenix",
                "x": 0,
                "y": 0,
                "hp": 14,
                "max_hp": 14,
                "atk": 4,
                "def": 1,
                "defeated": False,
                "ai_type": "assault",
                "weapon_type": "laser",
                "range": 2,
                "image_path": "",
                "direction": "right",
            },
            {
                "unit_id": "enemy_target",
                "side": "enemy",
                "name": "ダミーB",
                "species_key": "dummy_b",
                "x": 2,
                "y": 0,
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
        frame = simulate_mini_tactics_battle(11, map_payload, units_payload)[0]
        enemy = next(u for u in frame["units"] if u["unit_id"] == "enemy_target")
        self.assertEqual(enemy["hp"], 9)
        self.assertTrue(any("フェニックスがレーザーでダミーBを攻撃、3ダメージ" in line for line in frame["logs"]))

    def test_missile_attacks_at_range_two(self):
        map_payload = build_initial_map()
        units_payload = [
            {
                "unit_id": "ally_missile",
                "side": "ally",
                "name": "ヒュドラ",
                "species_key": "hydra",
                "x": 0,
                "y": 0,
                "hp": 20,
                "max_hp": 20,
                "atk": 3,
                "def": 3,
                "defeated": False,
                "ai_type": "assault",
                "weapon_type": "missile",
                "range": 2,
                "image_path": "",
                "direction": "right",
            },
            {
                "unit_id": "enemy_target",
                "side": "enemy",
                "name": "ダミーA",
                "species_key": "dummy_a",
                "x": 1,
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
        frame = simulate_mini_tactics_battle(12, map_payload, units_payload)[0]
        enemy = next(u for u in frame["units"] if u["unit_id"] == "enemy_target")
        self.assertEqual(enemy["hp"], 10)
        self.assertTrue(any("ヒュドラがミサイルでダミーAを攻撃、2ダメージ" in line for line in frame["logs"]))

    def test_out_of_range_unit_moves(self):
        map_payload = build_initial_map()
        units_payload = [
            {
                "unit_id": "ally_attacker",
                "side": "ally",
                "name": "ケルベロス",
                "species_key": "cerberus",
                "x": 0,
                "y": 0,
                "hp": 18,
                "max_hp": 18,
                "atk": 5,
                "def": 2,
                "defeated": False,
                "ai_type": "assault",
                "weapon_type": "melee",
                "range": 1,
                "image_path": "",
                "direction": "right",
            },
            {
                "unit_id": "enemy_target",
                "side": "enemy",
                "name": "ダミーA",
                "species_key": "dummy_a",
                "x": 4,
                "y": 0,
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
        frame = simulate_mini_tactics_battle(13, map_payload, units_payload)[0]
        attacker = next(u for u in frame["units"] if u["unit_id"] == "ally_attacker")
        enemy = next(u for u in frame["units"] if u["unit_id"] == "enemy_target")
        self.assertEqual(enemy["hp"], 12)
        self.assertLess(manhattan(attacker, enemy), 4)
        self.assertTrue(any("ケルベロスが突撃" in line for line in frame["logs"]))

    def test_cautious_retreats_when_low_hp(self):
        map_payload = build_initial_map()
        units_payload = [
            {
                "unit_id": "ally_cautious",
                "side": "ally",
                "name": "フェニックス",
                "species_key": "phoenix",
                "x": 1,
                "y": 1,
                "hp": 7,
                "max_hp": 14,
                "atk": 4,
                "def": 1,
                "defeated": False,
                "ai_type": "cautious",
                "image_path": "",
                "direction": "right",
            },
            {
                "unit_id": "enemy_near",
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
        frame = simulate_mini_tactics_battle(2, map_payload, units_payload)[0]
        phoenix = next(u for u in frame["units"] if u["unit_id"] == "ally_cautious")
        self.assertGreater(manhattan(phoenix, {"x": 2, "y": 1}), 1)
        self.assertTrue(any("フェニックスが距離を取った" in line for line in frame["logs"]))

    def test_cautious_attacks_when_no_retreat(self):
        map_payload = build_initial_map()
        map_payload["tiles"][1][0]["terrain"] = "wall"
        units_payload = [
            {
                "unit_id": "ally_cautious",
                "side": "ally",
                "name": "フェニックス",
                "species_key": "phoenix",
                "x": 0,
                "y": 0,
                "hp": 7,
                "max_hp": 14,
                "atk": 4,
                "def": 1,
                "defeated": False,
                "ai_type": "cautious",
                "image_path": "",
                "direction": "right",
            },
            {
                "unit_id": "enemy_near",
                "side": "enemy",
                "name": "ダミーA",
                "species_key": "dummy_a",
                "x": 1,
                "y": 0,
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
        frame = simulate_mini_tactics_battle(2, map_payload, units_payload)[0]
        enemy = next(u for u in frame["units"] if u["unit_id"] == "enemy_near")
        self.assertEqual(enemy["hp"], 9)
        self.assertTrue(any("フェニックスは退路がなく反撃、3ダメージ" in line for line in frame["logs"]))

    def test_guardian_moves_toward_isolated_ally(self):
        map_payload = build_initial_map()
        units_payload = [
            {
                "unit_id": "a_guardian",
                "side": "ally",
                "name": "ヒュドラ",
                "species_key": "hydra",
                "x": 0,
                "y": 0,
                "hp": 20,
                "max_hp": 20,
                "atk": 3,
                "def": 3,
                "defeated": False,
                "ai_type": "guardian",
                "image_path": "",
                "direction": "right",
            },
            {
                "unit_id": "ally_friend",
                "side": "ally",
                "name": "フェニックス",
                "species_key": "phoenix",
                "x": 4,
                "y": 4,
                "hp": 14,
                "max_hp": 14,
                "atk": 4,
                "def": 1,
                "defeated": False,
                "ai_type": "cautious",
                "image_path": "",
                "direction": "left",
            },
            {
                "unit_id": "enemy_far",
                "side": "enemy",
                "name": "ダミーA",
                "species_key": "dummy_a",
                "x": 4,
                "y": 0,
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
        frame = simulate_mini_tactics_battle(3, map_payload, units_payload)[0]
        hydra = next(u for u in frame["units"] if u["unit_id"] == "a_guardian")
        self.assertLess(manhattan(hydra, {"x": 4, "y": 4}), 8)
        self.assertTrue(any("ヒュドラが味方を守る位置へ移動" in line for line in frame["logs"]))

    def test_guardian_prioritizes_enemy_near_ally(self):
        map_payload = build_initial_map()
        units_payload = [
            {
                "unit_id": "a_guardian",
                "side": "ally",
                "name": "ヒュドラ",
                "species_key": "hydra",
                "x": 2,
                "y": 2,
                "hp": 20,
                "max_hp": 20,
                "atk": 3,
                "def": 3,
                "defeated": False,
                "ai_type": "guardian",
                "image_path": "",
                "direction": "right",
            },
            {
                "unit_id": "ally_friend",
                "side": "ally",
                "name": "フェニックス",
                "species_key": "phoenix",
                "x": 4,
                "y": 3,
                "hp": 14,
                "max_hp": 14,
                "atk": 4,
                "def": 1,
                "defeated": False,
                "ai_type": "cautious",
                "image_path": "",
                "direction": "left",
            },
            {
                "unit_id": "enemy_far_from_ally",
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
            {
                "unit_id": "enemy_near_ally",
                "side": "enemy",
                "name": "ダミーB",
                "species_key": "dummy_b",
                "x": 2,
                "y": 3,
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
        frame = simulate_mini_tactics_battle(3, map_payload, units_payload)[0]
        near_ally_enemy = next(u for u in frame["units"] if u["unit_id"] == "enemy_near_ally")
        far_ally_enemy = next(u for u in frame["units"] if u["unit_id"] == "enemy_far_from_ally")
        self.assertEqual(near_ally_enemy["hp"], 10)
        self.assertEqual(far_ally_enemy["hp"], 12)

    def test_defeated_enemy_is_not_targeted(self):
        map_payload = build_initial_map()
        map_payload["tiles"][1][2]["terrain"] = "floor"
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
                "unit_id": "enemy_defeated",
                "side": "enemy",
                "name": "撃破済み",
                "species_key": "dummy_a",
                "x": 1,
                "y": 2,
                "hp": 0,
                "max_hp": 12,
                "atk": 3,
                "def": 1,
                "defeated": True,
                "ai_type": "assault",
                "image_path": "",
                "direction": "left",
            },
            {
                "unit_id": "enemy_alive",
                "side": "enemy",
                "name": "ダミーA",
                "species_key": "dummy_a",
                "x": 3,
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
        frame = simulate_mini_tactics_battle(4, map_payload, units_payload)[0]
        attacker = next(u for u in frame["units"] if u["unit_id"] == "ally_attacker")
        self.assertEqual((attacker["x"], attacker["y"]), (2, 1))
        self.assertFalse(any("撃破済みを攻撃" in line for line in frame["logs"]))

    def test_seed_reproduces_frames(self):
        map_payload = build_initial_map()
        units_payload = build_initial_units()
        first = simulate_mini_tactics_battle(999, map_payload, units_payload)
        second = simulate_mini_tactics_battle(999, map_payload, units_payload)
        self.assertEqual(first, second)

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
