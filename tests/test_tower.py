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
        self.assertIn("/tower", admin_html)
        self.assertIn("home-tower-cta", admin_html)
        self.assertIn("管理者確認中", admin_html)

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
        self.assertIn("/tower", user_html)
        self.assertIn("home-tower-cta", user_html)

        locked_html = self._client(self.locked_user_id, "tower_locked").get("/home").get_data(as_text=True)
        self.assertNotIn("/tower", locked_html)

        tower_resp = self._client(self.user_id, "tower_user").get("/tower")
        self.assertEqual(tower_resp.status_code, 200)
        self.assertIn("3機小隊で深層記録に挑む", tower_resp.get_data(as_text=True))

    def test_tower_top_shows_squad_before_environment_summary(self):
        html = self._client().get("/tower").get_data(as_text=True)
        self.assertIn("今週の観測環境:", html)
        self.assertIn("自分の記録:", html)
        self.assertIn("小隊選択", html)
        self.assertLess(html.index("小隊選択"), html.index("今週の観測環境:"))
        self.assertNotIn('<div class="home-explore-kicker">今週の観測環境</div>', html)
        self.assertNotIn('<div class="home-explore-kicker">自分の記録</div>', html)
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
        self.assertIn("挑戦を続ける", html)
        self.assertIn("撤退する", html)
        self.assertIn("この機体で出撃", html)
        self.assertIn("次の敵", html)
        self.assertIn("ターン制限なし", html)
        self.assertNotIn("小隊選択", html)

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
            self.assertIn("冷却中", blocked_html)
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
        self.assertIn("観測敵", html)
        self.assertIn("合計 12 ダメージ", html)
        self.assertIn("合計 4 ダメージ", html)
        self.assertIn("次の階へ進む", html)
        self.assertIn("小隊交戦記録", html)
        self.assertIn("tower-floor-rail", html)
        self.assertIn("tower-floor-node is-current", html)
        self.assertIn("tower-floor-node is-locked is-gate", html)
        self.assertIn("下層観測区", html)
        self.assertIn("tower-squad-strip", html)
        self.assertIn("tower-combatants", html)
        self.assertIn("次階 2F", html)
        self.assertIn("data-tower-battle-replay", html)
        self.assertIn("data-tower-log-line", html)
        self.assertIn("data-tower-replay-actions", html)
        self.assertIn("static/tower.js", html)
        self.assertIn("ターン制限なし", html)
        self.assertLess(html.index("tower-floor-rail"), html.index("tower-combatants"))
        self.assertLess(html.index("tower-combatants"), html.index("tower-log-box"))
        self.assertLess(html.index("tower-combatants"), html.index("次階予告"))
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
        self.assertIn("観測敵", html)
        self.assertIn("合計 12 ダメージ", html)
        self.assertIn("次の階へ進む", html)
        self.assertIn("観測塔 -ASTRAL SPIRE-", html)
        self.assertIn("下層観測区", html)
        self.assertIn("小隊交戦記録", html)
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
        self.assertLess(html.index("tower-floor-rail"), html.index("tower-combatants"))
        self.assertLess(html.index("tower-combatants"), html.index("tower-log-box"))
        self.assertLess(html.index("tower-combatants"), html.index("次階予告"))
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
        self.assertIn("撃破成功", html)

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
        self.assertIn("撤退判断", html)
        self.assertNotIn("撃破成功", html)

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
                "UPDATE tower_run_battles SET enemy_id = NULL, enemy_key = '', enemy_name = '画像なし観測敵' WHERE id = ?",
                (battle_id,),
            )
            db.commit()
        resp = self._client().get(f"/tower/result/{run_id}?battle_id={battle_id}")
        html = resp.get_data(as_text=True)
        self.assertIn("enemies/_placeholder.png", html)
        self.assertIn("画像なし観測敵", html)
        self.assertIn("もう一度挑戦", html)

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
        self.assertIn("観測ログ", html)
        self.assertIn("2戦", html)
        self.assertIn("tower-hp-meter", html)
        self.assertIn("この機体で出撃", html)
        self.assertLess(html.index("次の階"), html.index("観測塔 -ASTRAL SPIRE-"))
        self.assertLess(html.index("この機体で出撃"), html.index("観測ログ"))

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
        self.assertIn("最後の記録: 1F 踏破", html)

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
            self.assertIn("TOWER_BEST_FLOOR", events)
            self.assertIn("TOWER_MILESTONE", events)
            self.assertIn("TOWER_WEEKLY_LEADER", events)
            self.assertIn("TOWER_ALL_TIME_LEADER", events)
            self.assertIn("audit.tower.record.update", events)
            self.assertIn("audit.tower.reward.grant", events)
            reward = db.execute(
                "SELECT reward_key FROM tower_reward_grants WHERE user_id = ?",
                (self.admin_user_id,),
            ).fetchone()
            self.assertEqual(reward["reward_key"], "tower_floor_10")

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
        self.assertIn("到達記録: 0F", html)
        self.assertIn("阻止されました", html)

    def test_abandon_active_run_updates_status_and_audit(self):
        run_id = self._start_run()
        resp = self._client().post("/tower/abandon", data={"run_id": run_id}, follow_redirects=True)
        html = resp.get_data(as_text=True)
        self.assertIn("観測塔から撤退しました", html)
        self.assertIn("使用した小隊", html)
        self.assertIn("まだ観測ログがありません", html)
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
        self.assertIn("観測敵", html)
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
        self.assertIn("観測塔ランキング", html)
        self.assertIn("今週の最高到達小隊", html)
        self.assertIn("歴代最高到達小隊", html)
        self.assertIn("7F", html)
        self.assertIn("低+値小隊記録", html)

    def test_records_displays_tower_section_empty(self):
        resp = self._client(self.user_id, "tower_user").get("/records")
        html = resp.get_data(as_text=True)
        self.assertIn("観測塔記録", html)
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
        self.assertIn("撃破成功", text)
        self.assertNotIn("アイアンポーン の攻撃", text)
        self.assertNotIn("反撃", text)

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


if __name__ == "__main__":
    unittest.main()
