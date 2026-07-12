import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app as game_app
import init_db
import services.tower as tower_service
from services.simulate_balance import simulate_battle


class TowerRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        self.old_testing = game_app.app.config.get("TESTING")
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        init_db.main()
        game_app.app.config["TESTING"] = True
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, max_unlocked_layer)
                VALUES ('tower_locked', 'x', ?, 0, 3)
                """,
                (now,),
            )
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, max_unlocked_layer)
                VALUES ('tower_user', 'x', ?, 0, 4)
                """,
                (now,),
            )
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, max_unlocked_layer)
                VALUES ('tower_admin', 'x', ?, 1, 4)
                """,
                (now,),
            )
            self.locked_user_id = int(db.execute("SELECT id FROM users WHERE username = 'tower_locked'").fetchone()["id"])
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = 'tower_user'").fetchone()["id"])
            self.admin_user_id = int(db.execute("SELECT id FROM users WHERE username = 'tower_admin'").fetchone()["id"])
            self.robot_ids = [self._create_robot(db, self.admin_user_id, f"TowerBot{i}") for i in range(1, 4)]
            self.user_robot_ids = [self._create_robot(db, self.user_id, f"UserTowerBot{i}") for i in range(1, 4)]
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        game_app.app.config["TESTING"] = self.old_testing
        self.tmpdir.cleanup()

    def _create_robot(self, db, user_id, name):
        now = int(time.time())
        cur = db.execute(
            """
            INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
            VALUES (?, ?, 'active', ?, ?)
            """,
            (int(user_id), name, now, now),
        )
        robot_id = int(cur.lastrowid)

        def key_for(part_type):
            row = db.execute(
                "SELECT key FROM robot_parts WHERE part_type = ? AND is_active = 1 ORDER BY id ASC LIMIT 1",
                (part_type,),
            ).fetchone()
            self.assertIsNotNone(row)
            return row["key"]

        db.execute(
            """
            INSERT INTO robot_instance_parts (robot_instance_id, head_key, r_arm_key, l_arm_key, legs_key)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                robot_id,
                key_for("HEAD"),
                key_for("RIGHT_ARM"),
                key_for("LEFT_ARM"),
                key_for("LEGS"),
            ),
        )
        return robot_id

    def _client(self, user_id=None, username="tower_admin"):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user_id or self.admin_user_id)
            session["username"] = username
        return client

    def test_home_tower_link_private_only_for_admin_users(self):
        locked_html = self._client(self.locked_user_id, "tower_locked").get("/home").get_data(as_text=True)
        self.assertNotIn("/tower", locked_html)

        user_html = self._client(self.user_id, "tower_user").get("/home").get_data(as_text=True)
        self.assertNotIn("/tower", user_html)

        admin_html = self._client().get("/home").get_data(as_text=True)
        self.assertIn("観測塔 -ASTRAL SPIRE-", admin_html)
        self.assertIn("最高記録:", admin_html)
        self.assertNotIn("home-tower-cta", admin_html)
        admin_client = self._client()
        admin_client.post("/home/tower/expand", data={"next": "/home"})
        expanded_admin_html = admin_client.get("/home").get_data(as_text=True)
        self.assertIn("/tower", expanded_admin_html)
        self.assertIn("home-tower-cta", expanded_admin_html)
        self.assertIn("公開準備中", expanded_admin_html)

    def test_release_public_allows_layer4_user_only(self):
        admin_client = self._client()
        resp = admin_client.post(
            "/admin/release",
            data={"feature_key": "tower", "state": "public"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("観測塔 -ASTRAL SPIRE-", resp.get_data(as_text=True))

        user_html = self._client(self.user_id, "tower_user").get("/home").get_data(as_text=True)
        self.assertIn("観測塔 -ASTRAL SPIRE-", user_html)
        self.assertNotIn("home-tower-cta", user_html)
        user_client = self._client(self.user_id, "tower_user")
        user_client.post("/home/tower/expand", data={"next": "/home"})
        expanded_user_html = user_client.get("/home").get_data(as_text=True)
        self.assertIn("/tower", expanded_user_html)
        self.assertIn("home-tower-cta", expanded_user_html)

        locked_html = self._client(self.locked_user_id, "tower_locked").get("/home").get_data(as_text=True)
        self.assertNotIn("/tower", locked_html)

        tower_resp = self._client(self.user_id, "tower_user").get("/tower")
        self.assertEqual(tower_resp.status_code, 200)
        self.assertIn("3機のロボで、どこまで登れるか挑戦", tower_resp.get_data(as_text=True))

    def test_tower_top_shows_squad_before_environment_summary(self):
        html = self._client().get("/tower").get_data(as_text=True)
        self.assertIn("今週の塔環境:", html)
        self.assertIn("自分の最高記録:", html)
        self.assertIn("挑戦する3機を選ぶ", html)
        self.assertLess(html.index("挑戦する3機を選ぶ"), html.index("今週の塔環境:"))
        self.assertNotIn('<div class="home-explore-kicker">今週の観測環境</div>', html)
        self.assertNotIn('<div class="home-explore-kicker">自分の記録</div>', html)
        for old_copy in ("小隊交戦記録", "観測敵", "次階予告", "観測ログ"):
            self.assertNotIn(old_copy, html)
        self.assertIn("data-tower-start-button disabled", html)
        self.assertIn("tower-start-button", html)
        self.assertIn("static/tower.js", html)
        self.assertNotIn("global_error_guard", html)
        self.assertNotIn("base_cleanup", html)
        self.assertNotIn("header_scroll", html)
        self.assertNotIn("ui_probe", html)

    def test_tower_template_uses_external_js_without_inline_script(self):
        template_path = os.path.join(os.path.dirname(game_app.__file__), "templates", "tower.html")
        with open(template_path, encoding="utf-8") as fh:
            source = fh.read()
        self.assertNotIn("<script>\n", source)
        self.assertIn("static', filename='tower.js'", source)

    def test_tower_pages_do_not_use_inline_handlers_or_javascript_urls(self):
        root = os.path.dirname(game_app.__file__)
        paths = [
            os.path.join(root, "templates", "tower.html"),
            os.path.join(root, "templates", "tower_result.html"),
            os.path.join(root, "templates", "tower_battle_view.html"),
            os.path.join(root, "templates", "tower_ranking.html"),
            os.path.join(root, "static", "tower.js"),
        ]
        for path in paths:
            with self.subTest(path=os.path.basename(path)):
                with open(path, encoding="utf-8") as fh:
                    source = fh.read()
                self.assertNotIn("<script>\n", source)
                self.assertNotIn("onclick=", source)
                self.assertNotIn("onchange=", source)
                self.assertNotIn("onsubmit=", source)
                self.assertNotIn("javascript:", source)

    def test_non_admin_user_cannot_start_tower(self):
        resp = self._client(self.user_id, "tower_user").post(
            "/tower/start",
            data={"robot_1": "1", "robot_2": "2", "robot_3": "3"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/home", resp.headers["Location"])

    def test_start_requires_three_distinct_robots(self):
        client = self._client()
        resp = client.post(
            "/tower/start",
            data={"robot_1": self.robot_ids[0], "robot_2": self.robot_ids[0], "robot_3": self.robot_ids[1]},
            follow_redirects=True,
        )
        self.assertIn("重複選択できません", resp.get_data(as_text=True))
        with game_app.app.app_context():
            db = game_app.get_db()
            count = int(db.execute("SELECT COUNT(*) AS c FROM tower_runs").fetchone()["c"])
            self.assertEqual(count, 0)

    def test_start_creates_run_and_cooling_rows(self):
        client = self._client()
        resp = client.post(
            "/tower/start",
            data={"robot_1": self.robot_ids[0], "robot_2": self.robot_ids[1], "robot_3": self.robot_ids[2]},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            run = db.execute("SELECT * FROM tower_runs WHERE user_id = ?", (self.admin_user_id,)).fetchone()
            self.assertIsNotNone(run)
            self.assertEqual(run["status"], "active")
            cooling = int(db.execute("SELECT COUNT(*) AS c FROM tower_run_cooling WHERE run_id = ?", (run["id"],)).fetchone()["c"])
            self.assertEqual(cooling, 3)
        html = client.get("/tower").get_data(as_text=True)
        self.assertIn("次の階へ進む", html)
        self.assertIn("ここで終了する", html)
        self.assertIn("この機体で出撃", html)
        self.assertIn("次の敵", html)
        self.assertIn("長期戦あり", html)
        self.assertNotIn("挑戦する3機を選ぶ", html)

    def _start_run(self):
        self._client().post(
            "/tower/start",
            data={"robot_1": self.robot_ids[0], "robot_2": self.robot_ids[1], "robot_3": self.robot_ids[2]},
        )
        with game_app.app.app_context():
            db = game_app.get_db()
            return int(db.execute("SELECT id FROM tower_runs WHERE user_id = ? ORDER BY id DESC LIMIT 1", (self.admin_user_id,)).fetchone()["id"])

    def test_cooling_rotation_blocks_reuse_and_resets_after_three_robots(self):
        run_id = self._start_run()
        win = {"win": True, "turns": 3, "timeout": False, "player_damage_total": 10, "enemy_damage_total": 1, "enemy_final_hp": 0}
        with patch("services.tower.simulate_battle", return_value=win):
            client = self._client()
            client.post("/tower/battle", data={"run_id": run_id, "robot_instance_id": self.robot_ids[0]})
            with game_app.app.app_context():
                db = game_app.get_db()
                row = db.execute(
                    "SELECT used_in_current_cycle FROM tower_run_cooling WHERE run_id = ? AND robot_instance_id = ?",
                    (run_id, self.robot_ids[0]),
                ).fetchone()
                self.assertEqual(int(row["used_in_current_cycle"]), 1)

            blocked = client.post(
                "/tower/battle",
                data={"run_id": run_id, "robot_instance_id": self.robot_ids[0]},
                follow_redirects=True,
            )
            blocked_html = blocked.get_data(as_text=True)
            self.assertIn("休憩中", blocked_html)
            self.assertIn("disabled", blocked_html)

            client.post("/tower/battle", data={"run_id": run_id, "robot_instance_id": self.robot_ids[1]})
            client.post("/tower/battle", data={"run_id": run_id, "robot_instance_id": self.robot_ids[2]})
            with game_app.app.app_context():
                db = game_app.get_db()
                rows = db.execute("SELECT used_in_current_cycle FROM tower_run_cooling WHERE run_id = ?", (run_id,)).fetchall()
                self.assertTrue(all(int(row["used_in_current_cycle"]) == 0 for row in rows))
                run = db.execute("SELECT current_floor FROM tower_runs WHERE id = ?", (run_id,)).fetchone()
                self.assertEqual(int(run["current_floor"]), 4)

    def test_tower_battle_uses_safety_turn_cap_not_explore_cap(self):
        run_id = self._start_run()
        win = {"win": True, "turns": 9, "timeout": False, "player_damage_total": 12, "enemy_damage_total": 4, "enemy_final_hp": 0}
        with patch("services.tower.simulate_battle", return_value=win) as mocked:
            self._client().post(
                "/tower/battle",
                data={"run_id": run_id, "robot_instance_id": self.robot_ids[0]},
            )
        self.assertEqual(mocked.call_args.kwargs["max_turns"], tower_service.TOWER_BATTLE_MAX_TURNS)
        self.assertGreater(tower_service.TOWER_BATTLE_MAX_TURNS, game_app.EXPLORE_MAX_TURNS)
        self.assertEqual(tower_service.TOWER_BATTLE_MAX_TURNS, 100)

    def test_battle_result_displays_combatants_logs_and_next_action(self):
        run_id = self._start_run()
        win = {"win": True, "turns": 3, "timeout": False, "player_damage_total": 12, "enemy_damage_total": 4, "enemy_final_hp": 0}
        with patch("services.tower.simulate_battle", return_value=win):
            resp = self._client().post(
                "/tower/battle",
                data={"run_id": run_id, "robot_instance_id": self.robot_ids[0]},
                follow_redirects=True,
            )
        html = resp.get_data(as_text=True)
        self.assertIn("1F 踏破", html)
        self.assertIn("TowerBot1", html)
        self.assertIn("敵", html)
        self.assertIn("合計 12 ダメージ", html)
        self.assertIn("合計 4 ダメージ", html)
        self.assertIn("次の階へ進む", html)
        self.assertIn("戦闘結果", html)
        self.assertIn("tower-floor-rail", html)
        self.assertIn("tower-floor-node is-current", html)
        self.assertIn("tower-floor-node is-locked is-gate", html)
        self.assertIn("下層観測区", html)
        self.assertIn("tower-squad-strip", html)
        self.assertIn("tower-combatants", html)
        self.assertIn("次は 2F", html)
        self.assertIn("data-tower-battle-replay", html)
        self.assertIn("data-tower-log-line", html)
        self.assertIn('data-tower-log-actor="player"', html)
        self.assertIn("data-tower-replay-actions", html)
        self.assertIn("static/tower.js", html)
        self.assertIn("tower-replay-2", html)
        self.assertIn("長期戦あり", html)
        self.assertLess(html.index("tower-floor-rail"), html.index("tower-combatants"))
        self.assertLess(html.index("tower-combatants"), html.index("tower-log-box"))
        self.assertLess(html.index("tower-combatants"), html.index("次の階"))
        self.assertTrue(("robot_composed/instance_" in html) or ("assets/placeholder_player.png" in html))
        with game_app.app.app_context():
            db = game_app.get_db()
            battle = db.execute("SELECT enemy_id FROM tower_run_battles WHERE run_id = ? LIMIT 1", (run_id,)).fetchone()
            enemy = db.execute("SELECT image_path FROM enemies WHERE id = ?", (int(battle["enemy_id"]),)).fetchone()
            if enemy and enemy["image_path"]:
                self.assertIn(str(enemy["image_path"]).split("/")[-1], html)

    def test_tower_battle_redirects_to_battle_view(self):
        run_id = self._start_run()
        win = {"win": True, "turns": 3, "timeout": False, "player_damage_total": 12, "enemy_damage_total": 4, "enemy_final_hp": 0}
        with patch("services.tower.simulate_battle", return_value=win):
            resp = self._client().post(
                "/tower/battle",
                data={"run_id": run_id, "robot_instance_id": self.robot_ids[0]},
                follow_redirects=False,
            )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/tower/battle/view/", resp.headers["Location"])

    def test_tower_battle_view_direct_displays_requested_battle(self):
        run_id = self._start_run()
        win = {"win": True, "turns": 3, "timeout": False, "player_damage_total": 12, "enemy_damage_total": 4, "enemy_final_hp": 0}
        with patch("services.tower.simulate_battle", return_value=win):
            self._client().post(
                "/tower/battle",
                data={"run_id": run_id, "robot_instance_id": self.robot_ids[0]},
            )
        with game_app.app.app_context():
            db = game_app.get_db()
            battle_id = int(db.execute("SELECT id FROM tower_run_battles WHERE run_id = ?", (run_id,)).fetchone()["id"])
        html = self._client().get(f"/tower/battle/view/{battle_id}").get_data(as_text=True)
        self.assertIn("1F 踏破", html)
        self.assertIn("TowerBot1", html)
        self.assertIn("敵", html)
        self.assertIn("合計 12 ダメージ", html)
        self.assertIn("次の階へ進む", html)
        self.assertIn("観測塔 -ASTRAL SPIRE-", html)
        self.assertIn("下層観測区", html)
        self.assertIn("戦闘結果", html)
        self.assertIn("tower-floor-rail", html)
        self.assertIn("tower-floor-node is-current", html)
        self.assertIn("tower-floor-node is-locked is-gate", html)
        self.assertIn("tower-squad-strip", html)
        self.assertIn("tower-combatants", html)
        self.assertIn("is-active", html)
        self.assertIn("交戦準備", html)
        self.assertIn("data-tower-replay-status", html)
        self.assertIn("data-tower-replay-projectile", html)
        self.assertIn("data-tower-hp-meter=\"player\"", html)
        self.assertIn("data-tower-hp-meter=\"enemy\"", html)
        self.assertIn("data-tower-log-actor", html)
        self.assertLess(html.index("tower-floor-rail"), html.index("tower-combatants"))
        self.assertLess(html.index("tower-combatants"), html.index("tower-log-box"))
        self.assertLess(html.index("tower-combatants"), html.index("次の階"))
        self.assertNotIn("global_error_guard", html)
        self.assertNotIn("base_cleanup", html)
        self.assertNotIn("onclick=", html)
        self.assertNotIn("onchange=", html)
        self.assertNotIn("onsubmit=", html)

    def test_tower_overkill_sets_enemy_hp_zero_without_same_turn_counter(self):
        run_id = self._start_run()
        enemy = {"id": None, "key": "tower_hp_28", "name_ja": "HP検証敵", "hp": 28, "atk": 5, "def": 1, "spd": 1, "acc": 1, "cri": 1}
        battle = {"win": True, "turns": 1, "timeout": False, "player_damage_total": 34, "enemy_damage_total": 9}
        with patch("services.tower.get_tower_enemy_for_floor", return_value=enemy), patch(
            "services.tower.scale_tower_enemy", return_value=enemy
        ), patch("services.tower.simulate_battle", return_value=battle):
            self._client().post("/tower/battle", data={"run_id": run_id, "robot_instance_id": self.robot_ids[0]})
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT id, battle_result, turn_logs_json FROM tower_run_battles WHERE run_id = ?", (run_id,)).fetchone()
            payload = json.loads(row["turn_logs_json"])[0]
            self.assertEqual(row["battle_result"], "win")
            self.assertEqual(payload["enemy_hp_max"], 28)
            self.assertEqual(payload["enemy_final_hp"], 0)
            self.assertEqual(payload["player_damage_total"], 34)
            self.assertEqual(payload["enemy_damage_total"], 0)
            battle_id = int(row["id"])
        html = self._client().get(f"/tower/battle/view/{battle_id}").get_data(as_text=True)
        self.assertIn("HP <span data-tower-hp-text=\"enemy\">28</span> / 28", html)
        self.assertIn("data-final-value=\"0\"", html)
        self.assertIn("合計 34 ダメージ", html)
        self.assertNotIn("HP検証敵 の反撃。", html)
        self.assertIn("敵を撃破！", html)

    def test_tower_partial_damage_does_not_become_win(self):
        run_id = self._start_run()
        enemy = {"id": None, "key": "tower_hp_28", "name_ja": "HP検証敵", "hp": 28, "atk": 5, "def": 1, "spd": 1, "acc": 1, "cri": 1}
        battle = {"win": True, "turns": 1, "timeout": False, "player_damage_total": 24, "enemy_damage_total": 0}
        with patch("services.tower.get_tower_enemy_for_floor", return_value=enemy), patch(
            "services.tower.scale_tower_enemy", return_value=enemy
        ), patch("services.tower.simulate_battle", return_value=battle):
            self._client().post("/tower/battle", data={"run_id": run_id, "robot_instance_id": self.robot_ids[0]})
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT id, battle_result, turn_logs_json FROM tower_run_battles WHERE run_id = ?", (run_id,)).fetchone()
            run = db.execute("SELECT status, reached_floor FROM tower_runs WHERE id = ?", (run_id,)).fetchone()
            payload = json.loads(row["turn_logs_json"])[0]
            self.assertEqual(row["battle_result"], "lose")
            self.assertEqual(run["status"], "failed")
            self.assertEqual(int(run["reached_floor"]), 0)
            self.assertEqual(payload["enemy_hp_max"], 28)
            self.assertEqual(payload["enemy_final_hp"], 4)
            battle_id = int(row["id"])
        html = self._client().get(f"/tower/battle/view/{battle_id}").get_data(as_text=True)
        self.assertIn("data-final-value=\"4\"", html)
        self.assertIn("合計 24 ダメージ", html)
        self.assertIn("挑戦終了", html)
        self.assertNotIn("敵を撃破！", html)

    def test_tower_zero_damage_never_defeats_enemy(self):
        run_id = self._start_run()
        enemy = {"id": None, "key": "tower_hp_28", "name_ja": "HP検証敵", "hp": 28, "atk": 5, "def": 1, "spd": 1, "acc": 1, "cri": 1}
        battle = {"win": True, "turns": 1, "timeout": False, "player_damage_total": 0, "enemy_damage_total": 0}
        with patch("services.tower.get_tower_enemy_for_floor", return_value=enemy), patch(
            "services.tower.scale_tower_enemy", return_value=enemy
        ), patch("services.tower.simulate_battle", return_value=battle):
            self._client().post("/tower/battle", data={"run_id": run_id, "robot_instance_id": self.robot_ids[0]})
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT battle_result, turn_logs_json FROM tower_run_battles WHERE run_id = ?", (run_id,)).fetchone()
            payload = json.loads(row["turn_logs_json"])[0]
            self.assertEqual(row["battle_result"], "lose")
            self.assertEqual(payload["enemy_final_hp"], 28)
            self.assertEqual(payload["player_damage_total"], 0)

    def test_battle_result_uses_enemy_placeholder_when_image_missing(self):
        run_id = self._start_run()
        lose = {"win": False, "turns": 2, "timeout": False, "player_damage_total": 1, "enemy_damage_total": 30}
        with patch("services.tower.simulate_battle", return_value=lose):
            self._client().post(
                "/tower/battle",
                data={"run_id": run_id, "robot_instance_id": self.robot_ids[0]},
            )
        with game_app.app.app_context():
            db = game_app.get_db()
            battle_id = int(db.execute("SELECT id FROM tower_run_battles WHERE run_id = ? LIMIT 1", (run_id,)).fetchone()["id"])
            db.execute(
                "UPDATE tower_run_battles SET enemy_id = NULL, enemy_key = '', enemy_name = '画像なしの敵' WHERE id = ?",
                (battle_id,),
            )
            db.commit()
        resp = self._client().get(f"/tower/result/{run_id}?battle_id={battle_id}")
        html = resp.get_data(as_text=True)
        self.assertIn("enemies/_placeholder.png", html)
        self.assertIn("画像なしの敵", html)
        self.assertIn("新しく挑戦する", html)

    def test_result_without_battle_id_displays_latest_battle(self):
        run_id = self._start_run()
        win = {"win": True, "turns": 2, "timeout": False, "player_damage_total": 12, "enemy_damage_total": 4, "enemy_final_hp": 0}
        with patch("services.tower.simulate_battle", return_value=win):
            client = self._client()
            client.post("/tower/battle", data={"run_id": run_id, "robot_instance_id": self.robot_ids[0]})
            client.post("/tower/battle", data={"run_id": run_id, "robot_instance_id": self.robot_ids[1]})
        resp = self._client().get(f"/tower/result/{run_id}")
        html = resp.get_data(as_text=True)
        self.assertIn("直近戦闘", html)
        self.assertIn("2F 踏破", html)
        self.assertIn("合計 12 ダメージ", html)
        self.assertIn("戦闘ログ", html)
        self.assertIn("2戦", html)
        self.assertIn("tower-hp-meter", html)
        self.assertIn("この機体で出撃", html)
        self.assertLess(html.index("次の階"), html.index("観測塔 -ASTRAL SPIRE-"))
        self.assertLess(html.index("この機体で出撃"), html.index("戦闘ログ"))

    def test_result_battle_id_displays_requested_battle(self):
        run_id = self._start_run()
        win = {"win": True, "turns": 2, "timeout": False, "player_damage_total": 12, "enemy_damage_total": 4, "enemy_final_hp": 0}
        with patch("services.tower.simulate_battle", return_value=win):
            client = self._client()
            client.post("/tower/battle", data={"run_id": run_id, "robot_instance_id": self.robot_ids[0]})
            client.post("/tower/battle", data={"run_id": run_id, "robot_instance_id": self.robot_ids[1]})
        with game_app.app.app_context():
            db = game_app.get_db()
            first_battle_id = int(
                db.execute(
                    "SELECT id FROM tower_run_battles WHERE run_id = ? ORDER BY floor ASC, id ASC LIMIT 1",
                    (run_id,),
                ).fetchone()["id"]
            )
        resp = self._client().get(f"/tower/result/{run_id}?battle_id={first_battle_id}")
        html = resp.get_data(as_text=True)
        self.assertIn("<div><b>1F 踏破</b></div>", html)
        self.assertIn("最後に踏破した階: 1F。", html)

    def test_completed_run_updates_record_and_world_logs(self):
        run_id = self._start_run()
        win = {"win": True, "turns": 2, "timeout": False, "player_damage_total": 10, "enemy_damage_total": 1, "enemy_final_hp": 0}
        with patch("services.tower.simulate_battle", return_value=win):
            client = self._client()
            for index in range(10):
                client.post(
                    "/tower/battle",
                    data={"run_id": run_id, "robot_instance_id": self.robot_ids[index % 3]},
                )
        with game_app.app.app_context():
            db = game_app.get_db()
            run = db.execute("SELECT status, reached_floor FROM tower_runs WHERE id = ?", (run_id,)).fetchone()
            self.assertEqual(run["status"], "completed")
            self.assertEqual(int(run["reached_floor"]), 10)
            record = db.execute("SELECT best_floor, weekly_best_floor FROM user_tower_records WHERE user_id = ?", (self.admin_user_id,)).fetchone()
            self.assertEqual(int(record["best_floor"]), 10)
            self.assertEqual(int(record["weekly_best_floor"]), 10)
            events = [
                row["event_type"]
                for row in db.execute(
                    "SELECT event_type FROM world_events_log WHERE user_id = ?",
                    (self.admin_user_id,),
                ).fetchall()
            ]
            self.assertIn("TOWER_PERSONAL_BEST", events)
            self.assertIn("TOWER_MILESTONE_REACHED", events)
            self.assertIn("TOWER_WEEKLY_TOP", events)
            self.assertIn("TOWER_ALL_TIME_RECORD", events)
            self.assertIn("audit.tower.record.update", events)
            self.assertIn("audit.tower.reward.grant", events)
            reward = db.execute(
                "SELECT reward_key FROM tower_reward_grants WHERE user_id = ?",
                (self.admin_user_id,),
            ).fetchone()
            self.assertEqual(reward["reward_key"], "tower_floor_10")

    def test_tower_world_log_events_use_public_conditions_and_dedupe(self):
        now = "2026-06-08T00:00:00+00:00"
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                INSERT INTO user_tower_records
                (user_id, best_floor, best_run_id, best_recorded_at, weekly_key, weekly_best_floor, weekly_best_run_id,
                 weekly_best_recorded_at, created_at, updated_at)
                VALUES (?, 7, 999, ?, ?, 7, 999, ?, ?, ?)
                """,
                (self.user_id, now, tower_service.current_week_key(), now, now, now),
            )
            db.commit()

            result = tower_service.update_tower_record_if_needed(
                db,
                self.admin_user_id,
                101,
                4,
                self.robot_ids,
                "stable_week",
                now,
                robot_instance_id=self.robot_ids[0],
            )
            self.assertTrue(result["best_updated"])
            self.assertIsNone(
                db.execute(
                    "SELECT id FROM world_events_log WHERE event_type = 'TOWER_PERSONAL_BEST' AND user_id = ?",
                    (self.admin_user_id,),
                ).fetchone()
            )

            tower_service.update_tower_record_if_needed(
                db,
                self.admin_user_id,
                101,
                5,
                self.robot_ids,
                "stable_week",
                now,
                robot_instance_id=self.robot_ids[0],
            )
            tower_service.update_tower_record_if_needed(
                db,
                self.admin_user_id,
                101,
                5,
                self.robot_ids,
                "stable_week",
                now,
                robot_instance_id=self.robot_ids[0],
            )
            milestone_count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = 'TOWER_MILESTONE_REACHED' AND user_id = ? AND CAST(json_extract(payload_json, '$.floor') AS INTEGER) = 5",
                    (self.admin_user_id,),
                ).fetchone()["c"]
                or 0
            )
            self.assertEqual(milestone_count, 1)
            personal_payload = json.loads(
                db.execute(
                    "SELECT payload_json FROM world_events_log WHERE event_type = 'TOWER_PERSONAL_BEST' AND user_id = ? ORDER BY id DESC LIMIT 1",
                    (self.admin_user_id,),
                ).fetchone()["payload_json"]
            )
            self.assertEqual(personal_payload["floor"], 5)
            self.assertEqual(personal_payload["tower_run_id"], 101)
            self.assertEqual(personal_payload["robot_instance_id"], self.robot_ids[0])
            self.assertEqual(personal_payload["robot_name"], "TowerBot1")
            self.assertEqual(personal_payload["previous_weekly_top_floor"], 7)
            self.assertEqual(personal_payload["previous_all_time_record_floor"], 7)

            tower_service.update_tower_record_if_needed(
                db,
                self.admin_user_id,
                102,
                7,
                self.robot_ids,
                "stable_week",
                now,
                robot_instance_id=self.robot_ids[1],
            )
            self.assertIsNone(
                db.execute(
                    "SELECT id FROM world_events_log WHERE event_type = 'TOWER_WEEKLY_TOP' AND user_id = ?",
                    (self.admin_user_id,),
                ).fetchone()
            )

            tower_service.update_tower_record_if_needed(
                db,
                self.admin_user_id,
                103,
                8,
                self.robot_ids,
                "stable_week",
                now,
                robot_instance_id=self.robot_ids[1],
            )
            self.assertIsNotNone(
                db.execute(
                    "SELECT id FROM world_events_log WHERE event_type = 'TOWER_WEEKLY_TOP' AND user_id = ?",
                    (self.admin_user_id,),
                ).fetchone()
            )
            self.assertIsNotNone(
                db.execute(
                    "SELECT id FROM world_events_log WHERE event_type = 'TOWER_ALL_TIME_RECORD' AND user_id = ?",
                    (self.admin_user_id,),
                ).fetchone()
            )
            db.commit()

    def test_comms_world_shows_tower_world_log(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute("UPDATE release_flags SET is_public = 1, updated_at = ? WHERE key = 'tower'", (now,))
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                VALUES (?, 'TOWER_MILESTONE_REACHED', ?, ?)
                """,
                (
                    now,
                    json.dumps(
                        {
                            "user_id": self.user_id,
                            "username": "tower_user",
                            "display_name": "tower_user",
                            "robot_instance_id": self.user_robot_ids[0],
                            "robot_name": "UserTowerBot1",
                            "floor": 5,
                            "previous_best_floor": 4,
                            "previous_weekly_top_floor": 4,
                            "previous_all_time_record_floor": 4,
                            "event_label": "観測塔節目到達",
                            "tower_run_id": 200,
                        },
                        ensure_ascii=False,
                    ),
                    self.user_id,
                ),
            )
            db.commit()
        html = self._client(self.user_id, "tower_user").get("/comms/world").get_data(as_text=True)
        self.assertIn("UserTowerBot1 が観測塔 5階に到達しました。", html)
        self.assertIn("SYSTEM LOG", html)
        feed_html = self._client(self.user_id, "tower_user").get("/feed").get_data(as_text=True)
        self.assertIn("UserTowerBot1 が観測塔 5階に到達しました。", feed_html)

    def test_failed_run_stores_reached_floor(self):
        run_id = self._start_run()
        lose = {"win": False, "turns": 4, "timeout": False, "player_damage_total": 2, "enemy_damage_total": 20}
        with patch("services.tower.simulate_battle", return_value=lose):
            self._client().post("/tower/battle", data={"run_id": run_id, "robot_instance_id": self.robot_ids[0]})
        with game_app.app.app_context():
            db = game_app.get_db()
            run = db.execute("SELECT status, reached_floor FROM tower_runs WHERE id = ?", (run_id,)).fetchone()
            self.assertEqual(run["status"], "failed")
            self.assertEqual(int(run["reached_floor"]), 0)
        html = self._client().get(f"/tower/result/{run_id}").get_data(as_text=True)
        self.assertIn("1F 撤退", html)
        self.assertIn("最高到達: 0F", html)
        self.assertIn("敗れました", html)

    def test_abandon_active_run_updates_status_and_audit(self):
        run_id = self._start_run()
        resp = self._client().post("/tower/abandon", data={"run_id": run_id}, follow_redirects=True)
        html = resp.get_data(as_text=True)
        self.assertIn("挑戦を終了しました", html)
        self.assertIn("選んだ3機", html)
        self.assertIn("まだ戦闘ログはありません", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            run = db.execute("SELECT status FROM tower_runs WHERE id = ?", (run_id,)).fetchone()
            self.assertEqual(run["status"], "abandoned")
            event = db.execute(
                "SELECT event_type FROM world_events_log WHERE event_type = 'audit.tower.run.abandon' AND user_id = ?",
                (self.admin_user_id,),
            ).fetchone()
            self.assertIsNotNone(event)

    def test_abandoned_run_displays_latest_battle_card_without_battle_id(self):
        run_id = self._start_run()
        win = {"win": True, "turns": 3, "timeout": False, "player_damage_total": 12, "enemy_damage_total": 4, "enemy_final_hp": 0}
        with patch("services.tower.simulate_battle", return_value=win):
            self._client().post(
                "/tower/battle",
                data={"run_id": run_id, "robot_instance_id": self.robot_ids[0]},
            )
        resp = self._client().post("/tower/abandon", data={"run_id": run_id}, follow_redirects=True)
        html = resp.get_data(as_text=True)
        self.assertIn("最後の戦闘", html)
        self.assertIn("1F 踏破", html)
        self.assertIn("TowerBot1", html)
        self.assertIn("敵", html)
        self.assertIn("合計 12 ダメージ", html)
        self.assertIn("合計 4 ダメージ", html)
        self.assertIn("1戦", html)
        self.assertTrue(("robot_composed/instance_" in html) or ("assets/placeholder_player.png" in html))

    def test_ranking_displays_record(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = "2026-06-08T00:00:00+00:00"
            db.execute(
                """
                INSERT INTO user_tower_records
                (user_id, best_floor, best_run_id, best_recorded_at, weekly_key, weekly_best_floor, weekly_best_run_id,
                 weekly_best_recorded_at, created_at, updated_at)
                VALUES (?, 7, 1, ?, ?, 7, 1, ?, ?, ?)
                """,
                (self.admin_user_id, now, game_app.get_current_tower_environment()["weekly_key"], now, now, now),
            )
            db.commit()
        resp = self._client().get("/tower/ranking")
        html = resp.get_data(as_text=True)
        self.assertIn("観測塔 記録ランキング", html)
        self.assertIn("今週いちばん登った記録", html)
        self.assertIn("歴代最高記録", html)
        self.assertIn("7F", html)
        self.assertIn("低+値チャレンジ", html)

    def test_records_displays_tower_section_empty(self):
        resp = self._client(self.user_id, "tower_user").get("/records")
        html = resp.get_data(as_text=True)
        self.assertIn("観測塔の記録", html)
        self.assertIn("まだ記録がありません", html)

    def test_explore_route_still_works(self):
        resp = self._client().get("/home")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("出撃", resp.get_data(as_text=True))

    def test_explore_battle_template_does_not_use_tower_spire_card(self):
        template_path = os.path.join(os.path.dirname(game_app.__file__), "templates", "battle.html")
        with open(template_path, encoding="utf-8") as fh:
            source = fh.read()
        self.assertNotIn("tower-spire-card", source)
        self.assertNotIn("tower-combatants", source)

    def test_tower_replay_uses_unit_names_for_attack_direction(self):
        script_path = os.path.join(os.path.dirname(game_app.__file__), "static", "tower.js")
        with open(script_path, encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn('enemyName + " の攻撃"', source)
        self.assertIn('playerName + " の攻撃"', source)
        self.assertIn("dataset.towerLogActor", source)
        self.assertIn("is-enemy-shot", source)
        self.assertIn("is-player-shot", source)

    def test_tower_turn_log_does_not_show_counter_after_killing_hit(self):
        payload = {
            "enemy_name": "アイアンポーン",
            "result": "win",
            "turns": 1,
            "player_damage_total": 47,
            "enemy_damage_total": 1,
            "battle_turn_logs": [
                {
                    "turn": 1,
                    "actor": "player",
                    "target": "enemy",
                    "damage": 47,
                    "target_hp_after": 0,
                    "first_actor": "player",
                }
            ],
        }
        lines = game_app._tower_battle_log_lines(
            {
                "turn_logs_json": json.dumps([payload], ensure_ascii=False),
                "turn_count": 1,
                "enemy_name": "アイアンポーン",
                "battle_result": "win",
            },
            "Starter Unit",
        )
        text = "\n".join(lines)
        self.assertIn("Starter Unit の攻撃", text)
        self.assertIn("敵を撃破！", text)
        self.assertNotIn("アイアンポーン の攻撃", text)
        self.assertNotIn("反撃", text)
        items = game_app._tower_battle_log_items(
            {
                "turn_logs_json": json.dumps([payload], ensure_ascii=False),
                "turn_count": 1,
                "enemy_name": "アイアンポーン",
                "battle_result": "win",
            },
            "Starter Unit",
        )
        self.assertEqual(items[0]["actor"], "player")
        self.assertEqual(items[-1]["actor"], "system")

    def test_simulate_battle_uses_speed_for_first_actor_and_skips_dead_counter(self):
        player = {"hp": 21, "atk": 80, "def": 20, "spd": 30, "acc": 99, "cri": 1}
        enemy = {"hp": 33, "atk": 10, "def": 1, "spd": 5, "acc": 99, "cri": 1}
        result = simulate_battle(player, enemy, seed=1, max_turns=100)
        self.assertTrue(result["win"])
        self.assertEqual(result["first_actor"], "player")
        self.assertEqual(int(result["enemy_damage_total"]), 0)
        self.assertEqual([row["actor"] for row in result["turn_logs"]], ["player"])

        faster_enemy = {"hp": 33, "atk": 10, "def": 1, "spd": 50, "acc": 99, "cri": 1}
        result = simulate_battle(player, faster_enemy, seed=1, max_turns=100)
        self.assertEqual(result["first_actor"], "enemy")
        self.assertEqual(result["turn_logs"][0]["actor"], "enemy")

    def test_tower_turn_log_marks_enemy_first_kill_as_enemy_actor(self):
        payload = {
            "enemy_name": "焦牙機スコーチファング",
            "result": "lose",
            "turns": 1,
            "player_damage_total": 0,
            "enemy_damage_total": 65,
            "battle_turn_logs": [
                {
                    "turn": 1,
                    "actor": "enemy",
                    "target": "player",
                    "damage": 65,
                    "target_hp_after": 0,
                    "first_actor": "enemy",
                }
            ],
        }
        items = game_app._tower_battle_log_items(
            {
                "turn_logs_json": json.dumps([payload], ensure_ascii=False),
                "turn_count": 1,
                "enemy_name": "焦牙機スコーチファング",
                "battle_result": "lose",
            },
            "クワサソリ",
        )
        self.assertEqual(items[0]["actor"], "enemy")
        self.assertIn("焦牙機スコーチファング の攻撃", items[0]["text"])
        self.assertNotIn("クワサソリ の攻撃", "\n".join(item["text"] for item in items))


if __name__ == "__main__":
    unittest.main()
