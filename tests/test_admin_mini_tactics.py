import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db
from services.mini_tactics import (
    apply_manual_turn_action,
    apply_manual_action,
    attackable_cells,
    build_initial_map,
    build_initial_units,
    build_manual_initial_board_v1,
    build_manual_board_state,
    build_turn_order,
    can_attack_manual,
    check_manual_result,
    can_attack,
    get_legal_moves,
    get_legal_targets,
    manhattan,
    mini_shogi_4x4_action_options,
    manual_action_options,
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
        self.assertIn("mini-tactics-placement-board", html)
        self.assertIn("data-placement-board", html)
        self.assertIn('name="slot_1_x"', html)
        self.assertIn('name="slot_1_y"', html)
        self.assertIn('name="slot_1_ai_type"', html)
        self.assertIn('name="slot_1_weapon_type"', html)
        self.assertIn("前衛特攻", html)
        self.assertIn('data-slot-card="1"', html)

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

    def test_team_page_saves_ai_and_weapon_types(self):
        client = self._client(admin=True)
        resp = client.post(
            "/admin/lab/mini-tactics/team",
            data={
                "slot_1_mini_robot_id": "",
                "slot_1_x": "0",
                "slot_1_y": "0",
                "slot_1_ai_type": "cautious",
                "slot_1_weapon_type": "laser",
                "slot_2_mini_robot_id": "",
                "slot_2_x": "1",
                "slot_2_y": "2",
                "slot_2_ai_type": "guardian",
                "slot_2_weapon_type": "missile",
                "slot_3_mini_robot_id": "",
                "slot_3_x": "2",
                "slot_3_y": "4",
                "slot_3_ai_type": "assault",
                "slot_3_weapon_type": "melee",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("慎重 + レーザー = 後衛射撃", html)
        self.assertIn("守護 + ミサイル = 支援砲撃", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            team = db.execute("SELECT * FROM mini_tactics_teams WHERE user_id = ?", (self.admin_id,)).fetchone()
            self.assertEqual(team["slot_1_ai_type"], "cautious")
            self.assertEqual(team["slot_1_weapon_type"], "laser")
            self.assertEqual(team["slot_2_ai_type"], "guardian")
            self.assertEqual(team["slot_2_weapon_type"], "missile")

    def test_start_uses_saved_ai_and_weapon_types(self):
        client = self._client(admin=True)
        client.post(
            "/admin/lab/mini-tactics/team",
            data={
                "slot_1_x": "0",
                "slot_1_y": "0",
                "slot_1_ai_type": "cautious",
                "slot_1_weapon_type": "laser",
                "slot_2_x": "1",
                "slot_2_y": "2",
                "slot_2_ai_type": "guardian",
                "slot_2_weapon_type": "missile",
                "slot_3_x": "2",
                "slot_3_y": "4",
                "slot_3_ai_type": "assault",
                "slot_3_weapon_type": "melee",
            },
            follow_redirects=True,
        )
        resp = client.post("/admin/lab/mini-tactics/start", data={"seed": "555"}, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT units_json FROM mini_tactics_battles ORDER BY id DESC LIMIT 1").fetchone()
            allies = [u for u in json.loads(row["units_json"]) if u["side"] == "ally"]
            self.assertEqual(allies[0]["ai_type"], "cautious")
            self.assertEqual(allies[0]["weapon_type"], "laser")
            self.assertEqual(allies[0]["weapon_label"], "レーザー")
            self.assertEqual(allies[0]["attack_range"], 2)
            self.assertEqual(allies[1]["ai_type"], "guardian")
            self.assertEqual(allies[1]["weapon_type"], "missile")

    def test_invalid_ai_and_weapon_values_fall_back_to_defaults(self):
        client = self._client(admin=True)
        resp = client.post(
            "/admin/lab/mini-tactics/team",
            data={
                "slot_1_x": "0",
                "slot_1_y": "0",
                "slot_1_ai_type": "bad_ai",
                "slot_1_weapon_type": "bad_weapon",
                "slot_2_x": "1",
                "slot_2_y": "2",
                "slot_3_x": "2",
                "slot_3_y": "4",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            team = db.execute("SELECT * FROM mini_tactics_teams WHERE user_id = ?", (self.admin_id,)).fetchone()
            self.assertIsNone(team["slot_1_ai_type"])
            self.assertIsNone(team["slot_1_weapon_type"])
            units = game_app._mini_tactics_team_units_for_user(db, self.admin_id)
            self.assertEqual(units[0]["ai_type"], "assault")
            self.assertEqual(units[0]["weapon_type"], "melee")

    def test_team_page_saves_start_positions(self):
        client = self._client(admin=True)
        resp = client.post(
            "/admin/lab/mini-tactics/team",
            data={
                "slot_1_mini_robot_id": "",
                "slot_1_x": "0",
                "slot_1_y": "0",
                "slot_2_mini_robot_id": "",
                "slot_2_x": "1",
                "slot_2_y": "2",
                "slot_3_mini_robot_id": "",
                "slot_3_x": "2",
                "slot_3_y": "4",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            team = db.execute("SELECT * FROM mini_tactics_teams WHERE user_id = ?", (self.admin_id,)).fetchone()
            self.assertEqual((team["slot_1_x"], team["slot_1_y"]), (0, 0))
            self.assertEqual((team["slot_2_x"], team["slot_2_y"]), (1, 2))
            self.assertEqual((team["slot_3_x"], team["slot_3_y"]), (2, 4))
            units = game_app._mini_tactics_team_units_for_user(db, self.admin_id)
            self.assertEqual([(u["x"], u["y"]) for u in units], [(0, 0), (1, 2), (2, 4)])

    def test_team_page_rejects_invalid_positions(self):
        client = self._client(admin=True)
        duplicate = client.post(
            "/admin/lab/mini-tactics/team",
            data={
                "slot_1_x": "0",
                "slot_1_y": "1",
                "slot_2_x": "0",
                "slot_2_y": "1",
                "slot_3_x": "0",
                "slot_3_y": "3",
            },
            follow_redirects=True,
        )
        self.assertIn("同じマス", duplicate.get_data(as_text=True))

        wall = client.post(
            "/admin/lab/mini-tactics/team",
            data={
                "slot_1_x": "0",
                "slot_1_y": "1",
                "slot_2_x": "2",
                "slot_2_y": "1",
                "slot_3_x": "0",
                "slot_3_y": "3",
            },
            follow_redirects=True,
        )
        self.assertIn("壁マス", wall.get_data(as_text=True))

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

    def test_start_uses_saved_positions(self):
        client = self._client(admin=True)
        client.post(
            "/admin/lab/mini-tactics/team",
            data={
                "slot_1_x": "0",
                "slot_1_y": "0",
                "slot_2_x": "1",
                "slot_2_y": "2",
                "slot_3_x": "2",
                "slot_3_y": "4",
            },
            follow_redirects=True,
        )
        resp = client.post("/admin/lab/mini-tactics/start", data={"seed": "444"}, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT units_json FROM mini_tactics_battles ORDER BY id DESC LIMIT 1").fetchone()
            units = json.loads(row["units_json"])
            allies = [u for u in units if u["side"] == "ally"]
            self.assertEqual([(u["x"], u["y"]) for u in allies], [(0, 0), (1, 2), (2, 4)])

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

    def test_manual_routes_are_admin_only(self):
        anon = self._client(login=False).get("/admin/lab/mini-tactics/manual/start")
        self.assertIn(anon.status_code, (302, 401))

        user = self._client().get("/admin/lab/mini-tactics/manual/start")
        self.assertEqual(user.status_code, 404)

        admin = self._client(admin=True).get("/admin/lab/mini-tactics/manual/start?seed=777", follow_redirects=False)
        self.assertEqual(admin.status_code, 302)
        self.assertRegex(admin.headers.get("Location", ""), r"/admin/lab/mini-tactics/manual/\d+")

    def test_manual_start_creates_board_state(self):
        client = self._client(admin=True)
        resp = client.get("/admin/lab/mini-tactics/manual/start?seed=778", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT * FROM mini_tactics_battles ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual(row["mode"], "manual_board")
            self.assertEqual(row["status"], "manual_active")
            state = json.loads(row["board_state_json"])
            self.assertEqual(state["current_turn_side"], "ally")
            self.assertEqual(state["turn_number"], 1)
            self.assertTrue(any(u["unit_id"] == "ally_core" for u in state["units"]))
            self.assertTrue(any(u["unit_id"] == "enemy_core" for u in state["units"]))

        page = client.get(resp.headers["Location"])
        self.assertEqual(page.status_code, 200)
        self.assertIn("手動戦術試験", page.get_data(as_text=True))

    def test_manual_action_moves_one_ally_and_enemy_cpu_once(self):
        client = self._client(admin=True)
        start = client.get("/admin/lab/mini-tactics/manual/start?seed=779", follow_redirects=False)
        battle_id = int(start.headers["Location"].rstrip("/").split("/")[-1])
        resp = client.post(
            f"/admin/lab/mini-tactics/manual/{battle_id}/action",
            data={"actor_unit_id": "rental_cerberus", "move_x": "1", "move_y": "1"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT * FROM mini_tactics_battles WHERE id = ?", (battle_id,)).fetchone()
            state = json.loads(row["board_state_json"])
            logs = json.loads(row["action_log_json"])
            ally = next(u for u in state["units"] if u["unit_id"] == "rental_cerberus")
            self.assertEqual((ally["x"], ally["y"]), (1, 1))
            self.assertEqual(row["current_turn_side"], "ally")
            self.assertEqual(int(row["turn_number"]), 2)
            self.assertGreaterEqual(len(logs), 2)

    def test_manual_move_then_attack_is_allowed(self):
        state = build_manual_board_state(1)
        ally = next(u for u in state["units"] if u["unit_id"] == "ally_cerberus")
        enemy = next(u for u in state["units"] if u["unit_id"] == "enemy_dummy_a")
        ally.update({"x": 0, "y": 0, "weapon_type": "melee", "attack_range": 1, "atk": 8})
        enemy.update({"x": 2, "y": 0, "hp": 6, "max_hp": 6})

        next_state, logs, error = apply_manual_turn_action(
            state,
            ally["unit_id"],
            move_to={"x": 1, "y": 0},
            target_unit_id=enemy["unit_id"],
            map_payload=build_initial_map(),
        )
        self.assertIsNone(error)
        updated_enemy = next(u for u in next_state["units"] if u["unit_id"] == enemy["unit_id"])
        self.assertLess(updated_enemy["hp"], 6)
        self.assertTrue(any(log["type"] == "attack" for log in logs))

    def test_manual_attack_then_move_is_rejected(self):
        state = build_manual_board_state(1)
        ally = next(u for u in state["units"] if u["unit_id"] == "ally_cerberus")
        enemy = next(u for u in state["units"] if u["unit_id"] == "enemy_dummy_a")
        ally.update({"x": 1, "y": 1, "weapon_type": "melee", "attack_range": 1})
        enemy.update({"x": 2, "y": 1})
        _, _, error = apply_manual_turn_action(
            state,
            ally["unit_id"],
            move_to={"x": 1, "y": 0},
            target_unit_id=enemy["unit_id"],
            attack_first=True,
            map_payload=build_initial_map(),
        )
        self.assertIn("攻撃後の移動", error)

    def test_manual_weapon_ranges_and_line_of_sight(self):
        map_payload = build_initial_map()
        attacker = {"x": 1, "y": 1, "weapon_type": "melee", "attack_range": 1}
        target = {"x": 2, "y": 1, "defeated": False}
        self.assertTrue(can_attack(attacker, target, map_payload))
        target["x"] = 3
        self.assertFalse(can_attack(attacker, target, map_payload))

        laser = {"x": 1, "y": 1, "weapon_type": "laser", "attack_range": 2}
        blocked = {"x": 3, "y": 1, "defeated": False}
        self.assertFalse(can_attack(laser, blocked, map_payload))

        missile = {"x": 1, "y": 1, "weapon_type": "missile", "attack_range": 2}
        self.assertTrue(can_attack(missile, blocked, map_payload))

    def test_manual_core_destroy_sets_result(self):
        state = build_manual_board_state(1)
        ally = next(u for u in state["units"] if u["unit_id"] == "ally_cerberus")
        core = next(u for u in state["units"] if u["unit_id"] == "enemy_core")
        ally.update({"x": 3, "y": 2, "weapon_type": "melee", "attack_range": 1, "atk": 20})
        next_state, logs, error = apply_manual_turn_action(
            state,
            ally["unit_id"],
            target_unit_id=core["unit_id"],
            map_payload=build_initial_map(),
        )
        self.assertIsNone(error)
        self.assertEqual(next_state["result"], "ally_win")
        self.assertTrue(any(log["type"] == "result" for log in logs))

    def test_manual_enemy_defeat_sets_result_even_core_alive(self):
        state = build_manual_board_state(1)
        ally = next(u for u in state["units"] if u["unit_id"] == "ally_cerberus")
        enemies = [u for u in state["units"] if u["side"] == "enemy" and u.get("unit_type") != "core"]
        for enemy in enemies:
            enemy["defeated"] = True
            enemy["hp"] = 0
        last_enemy = enemies[0]
        last_enemy.update({"defeated": False, "hp": 1, "x": 2, "y": 0})
        ally.update({"x": 1, "y": 0, "weapon_type": "melee", "attack_range": 1, "atk": 20})
        next_state, _, error = apply_manual_turn_action(
            state,
            ally["unit_id"],
            target_unit_id=last_enemy["unit_id"],
            map_payload=build_initial_map(),
        )
        self.assertIsNone(error)
        self.assertEqual(next_state["result"], "ally_win")

    def test_manual_action_options_include_move_and_attack_cells(self):
        state = build_manual_board_state(1)
        ally = next(u for u in state["units"] if u["unit_id"] == "ally_phoenix")
        options = manual_action_options(state, ally["unit_id"], build_initial_map())
        self.assertIn({"x": 2, "y": 2}, options["move_cells"])
        self.assertTrue(options["attackable_cells"])

    def test_mini_shogi_4x4_new_route_is_admin_only(self):
        anon = self._client(login=False).get("/admin/lab/mini-tactics/manual/new")
        self.assertIn(anon.status_code, (302, 401))

        user = self._client().get("/admin/lab/mini-tactics/manual/new")
        self.assertEqual(user.status_code, 404)

        admin = self._client(admin=True).get("/admin/lab/mini-tactics/manual/new?seed=901", follow_redirects=False)
        self.assertEqual(admin.status_code, 302)
        self.assertRegex(admin.headers.get("Location", ""), r"/admin/lab/mini-tactics/manual/\d+")

    def test_mini_shogi_4x4_initial_state(self):
        state = build_manual_initial_board_v1(1)
        self.assertEqual(state["mode"], "mini_shogi_4x4")
        self.assertEqual(state["board_size"], 4)
        self.assertEqual(state["current_turn_side"], "ally")
        self.assertIsNone(state["result"])
        allies = [u for u in state["units"] if u["side"] == "ally"]
        enemies = [u for u in state["units"] if u["side"] == "enemy"]
        self.assertEqual(len(allies), 3)
        self.assertEqual(len(enemies), 3)
        self.assertEqual(len([u for u in allies if u["is_leader"]]), 1)
        self.assertEqual(len([u for u in enemies if u["is_leader"]]), 1)
        self.assertTrue(all("trait_key" in u for u in state["units"]))
        self.assertTrue(all("hp" not in u and "atk" not in u and "def" not in u and "spd" not in u for u in state["units"]))

    def test_mini_shogi_4x4_start_creates_battle(self):
        client = self._client(admin=True)
        resp = client.get("/admin/lab/mini-tactics/manual/new?seed=902", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT * FROM mini_tactics_battles ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual(row["mode"], "mini_shogi_4x4")
            state = json.loads(row["board_state_json"])
            self.assertEqual(state["board_size"], 4)
            self.assertEqual(len([u for u in state["units"] if u["side"] == "ally"]), 3)
            self.assertEqual(len([u for u in state["units"] if u["side"] == "enemy"]), 3)

        page = client.get(resp.headers["Location"])
        self.assertEqual(page.status_code, 200)
        self.assertIn("mini_shogi_4x4", page.get_data(as_text=True))
        self.assertIn("リーダー撃破で勝利", page.get_data(as_text=True))

    def test_mini_shogi_4x4_movement_rules(self):
        state = build_manual_initial_board_v1(1)
        walker = next(u for u in state["units"] if u["unit_id"] == "ally_cerberus")
        flyer = next(u for u in state["units"] if u["unit_id"] == "ally_phoenix")
        walker_moves = get_legal_moves(walker, state)
        flyer_moves = get_legal_moves(flyer, state)
        self.assertIn({"x": 1, "y": 1}, walker_moves)
        self.assertNotIn({"x": -1, "y": 1}, walker_moves)
        self.assertNotIn({"x": 1, "y": 2}, flyer_moves)
        self.assertIn({"x": 1, "y": 1}, flyer_moves)
        self.assertNotIn({"x": 0, "y": 1}, flyer_moves)

    def test_mini_shogi_4x4_has_no_zoc_blocking(self):
        state = build_manual_initial_board_v1(1)
        ally = next(u for u in state["units"] if u["unit_id"] == "ally_cerberus")
        enemy_a = next(u for u in state["units"] if u["unit_id"] == "enemy_dummy_a")
        enemy_b = next(u for u in state["units"] if u["unit_id"] == "enemy_dummy_b")
        ally.update({"x": 1, "y": 1})
        enemy_a.update({"x": 1, "y": 0})
        enemy_b.update({"x": 1, "y": 3})
        self.assertIn({"x": 1, "y": 2}, get_legal_moves(ally, state))

    def test_mini_shogi_4x4_attack_rules(self):
        state = build_manual_initial_board_v1(1)
        melee = next(u for u in state["units"] if u["unit_id"] == "ally_cerberus")
        laser = next(u for u in state["units"] if u["unit_id"] == "ally_phoenix")
        missile = next(u for u in state["units"] if u["unit_id"] == "ally_hydra")
        target = next(u for u in state["units"] if u["unit_id"] == "enemy_dummy_b")
        melee.update({"x": 1, "y": 1})
        target.update({"x": 2, "y": 1})
        self.assertTrue(can_attack_manual(melee, target, state))
        target.update({"x": 3, "y": 1})
        self.assertFalse(can_attack_manual(melee, target, state))

        laser.update({"x": 0, "y": 0})
        target.update({"x": 2, "y": 0})
        self.assertTrue(can_attack_manual(laser, target, state))
        self.assertFalse(can_attack_manual(laser, target, state, moved=True))

        missile.update({"x": 0, "y": 0})
        target.update({"x": 1, "y": 1})
        self.assertTrue(can_attack_manual(missile, target, state))
        self.assertFalse(can_attack_manual(missile, target, state, moved=True))

    def test_mini_shogi_4x4_melee_can_move_then_attack(self):
        state = build_manual_initial_board_v1(1)
        ally = next(u for u in state["units"] if u["unit_id"] == "ally_cerberus")
        target = next(u for u in state["units"] if u["unit_id"] == "enemy_dummy_b")
        ally.update({"x": 0, "y": 0})
        target.update({"x": 2, "y": 0})
        next_state, logs, error = apply_manual_action(
            state,
            {"actor_unit_id": ally["unit_id"], "move_to": {"x": 1, "y": 0}, "target_unit_id": target["unit_id"]},
        )
        self.assertIsNone(error)
        updated = next(u for u in next_state["units"] if u["unit_id"] == target["unit_id"])
        self.assertTrue(updated["defeated"])
        self.assertTrue(any(log["type"] == "attack" for log in logs))

    def test_mini_shogi_4x4_laser_cannot_move_then_attack(self):
        state = build_manual_initial_board_v1(1)
        ally = next(u for u in state["units"] if u["unit_id"] == "ally_phoenix")
        target = next(u for u in state["units"] if u["unit_id"] == "enemy_dummy_b")
        ally.update({"x": 0, "y": 0})
        target.update({"x": 3, "y": 1})
        _, _, error = apply_manual_action(
            state,
            {"actor_unit_id": ally["unit_id"], "move_to": {"x": 1, "y": 1}, "target_unit_id": target["unit_id"]},
        )
        self.assertIn("攻撃できない", error)

    def test_mini_shogi_4x4_leader_defeat_result(self):
        state = build_manual_initial_board_v1(1)
        ally = next(u for u in state["units"] if u["unit_id"] == "ally_cerberus")
        leader = next(u for u in state["units"] if u["side"] == "enemy" and u["is_leader"])
        ally.update({"x": 2, "y": 1})
        next_state, logs, error = apply_manual_action(
            state,
            {"actor_unit_id": ally["unit_id"], "target_unit_id": leader["unit_id"]},
        )
        self.assertIsNone(error)
        self.assertEqual(next_state["result"], "ally_win")
        self.assertEqual(check_manual_result(next_state), "ally_win")
        self.assertTrue(any("味方勝利" in log["text"] for log in logs))

    def test_mini_shogi_4x4_enemy_cpu_acts_once_and_turn_returns(self):
        state = build_manual_initial_board_v1(1)
        next_state, logs, error = apply_manual_action(
            state,
            {"actor_unit_id": "ally_hydra", "move_to": {"x": 1, "y": 2}},
        )
        self.assertIsNone(error)
        self.assertEqual(next_state["current_turn_side"], "ally")
        self.assertEqual(next_state["turn_number"], 2)
        self.assertGreaterEqual(len([log for log in logs if log["actor_unit_id"].startswith("enemy_")]), 1)

    def test_mini_shogi_4x4_action_options_include_after_move_targets(self):
        state = build_manual_initial_board_v1(1)
        ally = next(u for u in state["units"] if u["unit_id"] == "ally_cerberus")
        target = next(u for u in state["units"] if u["unit_id"] == "enemy_dummy_b")
        ally.update({"x": 0, "y": 0})
        target.update({"x": 2, "y": 0})
        options = mini_shogi_4x4_action_options(state, ally["unit_id"])
        self.assertIn({"x": 1, "y": 0}, options["move_cells"])
        self.assertIn(target["unit_id"], options["after_move"]["1,0"]["targetable_unit_ids"])

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
            self.assertTrue(all("weapon_type" in u and "weapon_label" in u and "attack_range" in u for u in units_payload))
            terrains = [tile["terrain"] for row in map_payload["tiles"] for tile in row]
            self.assertIn("wall", terrains)
            wall_positions = {(tile["x"], tile["y"]) for row in map_payload["tiles"] for tile in row if tile["terrain"] == "wall"}
            start_positions = {(unit["x"], unit["y"]) for unit in units_payload}
            self.assertFalse(wall_positions & start_positions)
            ai_by_species = {u["species_key"]: u["ai_type"] for u in units_payload if u["side"] == "ally"}
            self.assertEqual(ai_by_species["cerberus"], "assault")
            self.assertEqual(ai_by_species["phoenix"], "cautious")
            self.assertEqual(ai_by_species["hydra"], "guardian")
            self.assertTrue(all("ai_type" in u for frame in frames_payload for u in frame["units"]))
            self.assertTrue(all("spd" in u for u in units_payload))
            self.assertTrue(
                all("weapon_type" in u and "weapon_label" in u and "attack_range" in u for frame in frames_payload for u in frame["units"])
            )
            self.assertTrue(all("events" in frame for frame in frames_payload))
            self.assertTrue(all("acting_order" in frame for frame in frames_payload))
            self.assertTrue(all("attackable_cells" in frame for frame in frames_payload))
            self.assertTrue(all("targetable_unit_ids" in frame for frame in frames_payload))

        page = client.get(resp.headers["Location"])
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("miniTacticsBoard", html)
        self.assertIn("miniTacticsRoster", html)
        self.assertIn("ai_type", html)
        self.assertIn("miniTacticsOrder", html)
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

    def test_spd_controls_turn_order_and_seed_reproduces_ties(self):
        units = [
            {"unit_id": "slow", "name": "slow", "side": "ally", "x": 0, "y": 0, "hp": 10, "spd": 1},
            {"unit_id": "fast", "name": "fast", "side": "ally", "x": 0, "y": 1, "hp": 10, "spd": 9},
            {"unit_id": "tie_a", "name": "tie_a", "side": "ally", "x": 0, "y": 2, "hp": 10, "spd": 4},
            {"unit_id": "tie_b", "name": "tie_b", "side": "ally", "x": 0, "y": 3, "hp": 10, "spd": 4},
            {"unit_id": "defeated", "name": "defeated", "side": "ally", "x": 0, "y": 4, "hp": 0, "spd": 99, "defeated": True},
        ]
        first = [u["unit_id"] for u in build_turn_order(units, 123, 1)]
        second = [u["unit_id"] for u in build_turn_order(units, 123, 1)]
        self.assertEqual(first, second)
        self.assertEqual(first[0], "fast")
        self.assertNotIn("defeated", first)

    def test_spd_order_is_saved_in_frame(self):
        map_payload = build_initial_map()
        units_payload = [
            {
                "unit_id": "slow_ally",
                "side": "ally",
                "name": "ケルベロス",
                "species_key": "cerberus",
                "x": 0,
                "y": 0,
                "hp": 18,
                "max_hp": 18,
                "atk": 5,
                "def": 2,
                "spd": 1,
                "defeated": False,
                "ai_type": "assault",
                "weapon_type": "melee",
                "image_path": "",
                "direction": "right",
            },
            {
                "unit_id": "fast_enemy",
                "side": "enemy",
                "name": "ダミーA",
                "species_key": "dummy_a",
                "x": 4,
                "y": 0,
                "hp": 12,
                "max_hp": 12,
                "atk": 3,
                "def": 1,
                "spd": 9,
                "defeated": False,
                "ai_type": "assault",
                "image_path": "",
                "direction": "left",
            },
        ]
        frame = simulate_mini_tactics_battle(44, map_payload, units_payload)[0]
        self.assertEqual(frame["acting_order"][0]["unit_id"], "fast_enemy")
        self.assertEqual(frame["current_actor_unit_id"], "fast_enemy")

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
                "spd": 9,
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
                "spd": 1,
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
        attack_event = next(event for event in frame["events"] if event["type"] == "attack")
        self.assertEqual(attack_event["actor_unit_id"], "ally_laser")
        self.assertEqual(attack_event["target_unit_id"], "enemy_target")
        self.assertEqual(attack_event["weapon_type"], "laser")
        self.assertEqual(attack_event["damage"], 3)
        self.assertIn("レーザー", attack_event["text"])
        self.assertIn("enemy_target", frame["targetable_unit_ids"])

    def test_melee_does_not_attack_at_range_two(self):
        map_payload = build_initial_map()
        units_payload = [
            {
                "unit_id": "ally_melee",
                "side": "ally",
                "name": "ケルベロス",
                "species_key": "cerberus",
                "x": 0,
                "y": 0,
                "hp": 18,
                "max_hp": 18,
                "atk": 5,
                "def": 2,
                "spd": 9,
                "defeated": False,
                "ai_type": "assault",
                "weapon_type": "melee",
                "attack_range": 1,
                "image_path": "",
                "direction": "right",
            },
            {
                "unit_id": "enemy_target",
                "side": "enemy",
                "name": "ダミーA",
                "species_key": "dummy_a",
                "x": 2,
                "y": 0,
                "hp": 12,
                "max_hp": 12,
                "atk": 3,
                "def": 1,
                "spd": 1,
                "defeated": False,
                "ai_type": "assault",
                "image_path": "",
                "direction": "left",
            },
        ]
        frame = simulate_mini_tactics_battle(14, map_payload, units_payload)[0]
        enemy = next(u for u in frame["units"] if u["unit_id"] == "enemy_target")
        self.assertEqual(enemy["hp"], 12)
        self.assertTrue(any(event["type"] == "move" for event in frame["events"]))
        self.assertFalse(any(event["type"] == "attack" and event["actor_unit_id"] == "ally_melee" for event in frame["events"]))

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

    def test_attackable_cells_respect_weapon_and_walls(self):
        map_payload = build_initial_map()
        melee = {"x": 1, "y": 1, "weapon_type": "melee", "attack_range": 1}
        laser = {"x": 1, "y": 1, "weapon_type": "laser", "attack_range": 2}
        missile = {"x": 1, "y": 1, "weapon_type": "missile", "attack_range": 2}

        melee_cells = {(cell["x"], cell["y"]) for cell in attackable_cells(melee, map_payload)}
        self.assertEqual(melee_cells, {(0, 1), (1, 0), (1, 2)})

        laser_cells = {(cell["x"], cell["y"]) for cell in attackable_cells(laser, map_payload)}
        self.assertIn((0, 1), laser_cells)
        self.assertNotIn((2, 1), laser_cells)
        self.assertNotIn((3, 1), laser_cells)

        missile_cells = {(cell["x"], cell["y"]) for cell in attackable_cells(missile, map_payload)}
        self.assertIn((2, 1), missile_cells)
        self.assertIn((3, 1), missile_cells)

    def test_laser_wall_blocks_but_missile_hits_through_wall(self):
        map_payload = build_initial_map()
        laser = {
            "unit_id": "ally_laser",
            "side": "ally",
            "name": "フェニックス",
            "species_key": "phoenix",
            "x": 1,
            "y": 1,
            "hp": 14,
            "max_hp": 14,
            "atk": 4,
            "def": 1,
            "defeated": False,
            "ai_type": "assault",
            "weapon_type": "laser",
            "attack_range": 2,
            "image_path": "",
            "direction": "right",
        }
        missile = dict(laser)
        missile.update({"unit_id": "ally_missile", "name": "ヒュドラ", "species_key": "hydra", "weapon_type": "missile", "atk": 3})
        target = {
            "unit_id": "enemy_target",
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
        }
        self.assertFalse(can_attack(laser, target, map_payload))
        self.assertTrue(can_attack(missile, target, map_payload))

        laser_frame = simulate_mini_tactics_battle(55, map_payload, [laser, dict(target)])[0]
        laser_enemy = next(u for u in laser_frame["units"] if u["unit_id"] == "enemy_target")
        self.assertEqual(laser_enemy["hp"], 12)
        self.assertTrue(any("壁に遮られて狙えない" in line for line in laser_frame["logs"]))

        missile_frame = simulate_mini_tactics_battle(55, map_payload, [missile, dict(target)])[0]
        missile_enemy = next(u for u in missile_frame["units"] if u["unit_id"] == "enemy_target")
        self.assertEqual(missile_enemy["hp"], 10)

    def test_laser_attacks_straight_line_only(self):
        map_payload = build_initial_map()
        attacker = {"x": 0, "y": 0, "weapon_type": "laser", "attack_range": 2, "defeated": False}
        straight = {"x": 0, "y": 2, "defeated": False}
        diagonal = {"x": 1, "y": 1, "defeated": False}
        self.assertTrue(can_attack(attacker, straight, map_payload))
        self.assertFalse(can_attack(attacker, diagonal, map_payload))

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
                "spd": 9,
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
                "spd": 1,
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
        move_event = next(event for event in frame["events"] if event["type"] == "move" and event["actor_unit_id"] == "ally_attacker")
        self.assertEqual(move_event["from"], {"x": 0, "y": 0})
        self.assertIn("x", move_event["to"])
        self.assertIn("y", move_event["to"])

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
        self.assertTrue(any("フェニックスが距離" in line for line in frame["logs"]))

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
                "weapon_type": "melee",
                "attack_range": 1,
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
                "weapon_type": "melee",
                "attack_range": 1,
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
                "spd": 9,
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
                "spd": 1,
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
                "spd": 9,
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
                "spd": 1,
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
        self.assertTrue(any(event["type"] == "defeated" and event["actor_unit_id"] == "enemy_target" for event in frame["events"]))
        self.assertTrue(any(event["type"] == "result" and event["result"] == "ally_win" for event in frame["events"]))

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
