import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class BuildArchetypeUiTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, coins, max_unlocked_layer)
                VALUES (?, ?, ?, 1, 0, 0, 1)
                """,
                ("archetype_tester", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("archetype_tester",),
            ).fetchone()["id"]
            game_app.initialize_new_user(db, self.user_id)
            self.robot_id = db.execute(
                "SELECT active_robot_id FROM users WHERE id = ?",
                (self.user_id,),
            ).fetchone()["active_robot_id"]
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _new_client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "archetype_tester"
        return client

    def test_style_classification_deterministic_from_stats(self):
        stable = game_app._robot_style_from_final_stats({"hp": 120, "atk": 20, "def": 90, "spd": 25, "acc": 40, "cri": 10})
        burst = game_app._robot_style_from_final_stats({"hp": 160, "atk": 180, "def": 10, "spd": 15, "acc": 20, "cri": 220})
        desperate = game_app._robot_style_from_final_stats({"hp": 15, "atk": 90, "def": 15, "spd": 80, "acc": 30, "cri": 40})
        self.assertEqual(stable["style_key"], "stable")
        self.assertEqual(burst["style_key"], "burst")
        self.assertEqual(desperate["style_key"], "desperate")
        self.assertEqual(stable.get("style_description"), "防御・命中寄り（長期戦向き）")

    def test_style_tie_break_prefers_stable_then_burst(self):
        self.assertEqual(
            game_app._pick_robot_style_key({"stable": 0.5, "burst": 0.5, "desperate": 0.5}),
            "stable",
        )
        self.assertEqual(
            game_app._pick_robot_style_key({"stable": 0.2, "burst": 0.6, "desperate": 0.6}),
            "burst",
        )

    def test_home_and_build_show_current_archetype(self):
        client = self._new_client()
        home = client.get("/home")
        self.assertEqual(home.status_code, 200)
        home_html = home.get_data(as_text=True)
        self.assertIn("思想:", home_html)
        self.assertIn("出撃機体", home_html)
        self.assertIn("スタイル実績", home_html)
        self.assertRegex(home_html, "思想: .+")
        self.assertRegex(home_html, "(耐久|攻撃|防御|素早さ|命中|会心) [0-9]+ / (耐久|攻撃|防御|素早さ|命中|会心) [0-9]+")

        build = client.get("/build")
        self.assertEqual(build.status_code, 200)
        build_html = build.get_data(as_text=True)
        self.assertIn("ステータス比較", build_html)
        self.assertIn("組み立て中（プレビュー）", build_html)
        self.assertIn("現装備（起動中ロボ）", build_html)
        self.assertIn("現在装備", build_html)
        self.assertIn("総合差分", build_html)
        self.assertNotIn('style="', build_html)
        self.assertNotIn('type="application/json"', build_html)

    def test_build_stat_comparison_rows(self):
        rows = game_app._build_stat_comparison_rows(
            current_stats={"hp": 10, "atk": 14, "def": 8, "power": 20.0},
            candidate_stats={"hp": 11, "atk": 16, "def": 7, "power": 22.5},
        )
        by_key = {r["key"]: r for r in rows}
        self.assertEqual(by_key["atk"]["delta"], 2)
        self.assertEqual(by_key["atk"]["delta_text"], "+2")
        self.assertEqual(by_key["def"]["delta"], -1)
        self.assertEqual(by_key["power"]["delta"], 2.5)

    def test_attack_note_uses_abstract_categories_by_default(self):
        miss_note = game_app._attack_note(
            "攻撃",
            0,
            {"miss": True, "att_acc": 10, "def_acc": 20, "hit_chance": 0.61, "hit_bonus": -0.02},
        )
        guard_note = game_app._attack_note(
            "攻撃",
            0,
            {"miss": False, "att_acc": 30, "def_acc": 20, "hit_chance": 0.9, "hit_bonus": 0.0},
        )
        debug_note = game_app._attack_note(
            "攻撃",
            0,
            {"miss": True, "att_acc": 10, "def_acc": 20, "hit_chance": 0.61, "hit_bonus": -0.02},
            debug=True,
        )
        self.assertIn("MISS（相手が速い）", miss_note)
        self.assertIn("0ダメ（装甲が硬い）", guard_note)
        self.assertIn("命中率", debug_note)

    def test_style_achievement_progress_is_idempotent_by_battle_id(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            applied1 = game_app._apply_style_achievement_progress_once(
                db,
                user_id=self.user_id,
                robot_id=self.robot_id,
                battle_id="battle-idempotent-1",
                stable_no_damage_inc=1,
                burst_crit_finisher_inc=2,
                desperate_low_hp_inc=1,
            )
            applied2 = game_app._apply_style_achievement_progress_once(
                db,
                user_id=self.user_id,
                robot_id=self.robot_id,
                battle_id="battle-idempotent-1",
                stable_no_damage_inc=1,
                burst_crit_finisher_inc=2,
                desperate_low_hp_inc=1,
            )
            db.commit()
            self.assertTrue(applied1)
            self.assertFalse(applied2)
            row = db.execute(
                """
                SELECT style_stats_json
                FROM robot_instances
                WHERE id = ?
                """,
                (self.robot_id,),
            ).fetchone()
            stats = game_app._decode_style_stats_json(row["style_stats_json"])
            self.assertEqual(int(stats["stable"]["hitless_wins"]), 1)
            self.assertEqual(int(stats["burst"]["crit_finishes"]), 2)
            self.assertEqual(int(stats["desperate"]["low_hp_wins"]), 1)

    def test_no_damage_victory_definition_uses_damage_taken_total(self):
        self.assertFalse(game_app._is_no_damage_victory(1))
        self.assertFalse(game_app._is_no_damage_victory(3.5))
        self.assertTrue(game_app._is_no_damage_victory(0))
        self.assertTrue(game_app._is_no_damage_victory(None))


if __name__ == "__main__":
    unittest.main()
