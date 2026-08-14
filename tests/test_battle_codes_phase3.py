import os
import tempfile
import time
import unittest
from unittest import mock

import app as game_app
import init_db
from services import battle_codes, module_protocols


class BattleCodePhase3Tests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer)
                VALUES ('code_tester', 'x', ?, 1, 0, 4)
                """,
                (now,),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = 'code_tester'").fetchone()["id"])
            self.robot_id = self._create_robot(db)
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "code_tester"
        return client

    def _create_robot(self, db):
        now = int(time.time())
        db.execute(
            "INSERT INTO robot_instances (user_id, name, status, created_at, updated_at) VALUES (?, 'CodeBot', 'active', ?, ?)",
            (self.user_id, now, now),
        )
        robot_id = int(db.execute("SELECT id FROM robot_instances WHERE user_id = ?", (self.user_id,)).fetchone()["id"])
        part_keys = []
        for part_type in ("HEAD", "RIGHT_ARM", "LEFT_ARM", "LEGS"):
            part_keys.append(db.execute("SELECT key FROM robot_parts WHERE part_type = ? AND is_active = 1 LIMIT 1", (part_type,)).fetchone()["key"])
        db.execute(
            "INSERT INTO robot_instance_parts (robot_instance_id, head_key, r_arm_key, l_arm_key, legs_key) VALUES (?, ?, ?, ?, ?)",
            (robot_id, *part_keys),
        )
        db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (robot_id, self.user_id))
        return robot_id

    def _grant(self, module_key="sniper_prototype", brand_key="eden", role_key="precision"):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            cur = db.execute(
                """
                INSERT INTO user_research_modules (user_id, module_key, status, brand_key, role_key, created_at, updated_at)
                VALUES (?, ?, 'inventory', ?, ?, ?, ?)
                """,
                (self.user_id, module_key, brand_key, role_key, now, now),
            )
            db.commit()
            return int(cur.lastrowid)

    def test_defines_six_conditions_six_effects_and_names_all_pairs(self):
        self.assertEqual(len(battle_codes.active_conditions()), 10)
        self.assertEqual(len(battle_codes.active_effects()), 6)
        for condition in battle_codes.active_conditions():
            for effect in battle_codes.active_effects():
                name = battle_codes.display_name(condition["condition_key"], effect["effect_key"])
                self.assertIn("《", name)
                self.assertIn(effect["code_name"], name)
        self.assertEqual(
            battle_codes.display_name("after_miss", "guaranteed_hit"),
            "誤差修正式《REWRITE-FATE-LOCK》",
        )

    def test_save_rejects_partial_invalid_and_clear(self):
        client = self._client()
        self._grant()
        resp = client.post("/modules/battle-code", data={"action": "save", "condition_key": "after_miss"}, follow_redirects=True)
        self.assertIn("条件コードと効果コード", resp.get_data(as_text=True))
        client.post("/modules/battle-code", data={"action": "save", "condition_key": "after_miss", "effect_key": "guaranteed_hit"})
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT selected_battle_code_condition_key, selected_battle_code_effect_key FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(row["selected_battle_code_condition_key"], "after_miss")
            self.assertEqual(row["selected_battle_code_effect_key"], "guaranteed_hit")
            self.assertIsNotNone(db.execute("SELECT id FROM world_events_log WHERE event_type = ? LIMIT 1", (game_app.AUDIT_EVENT_TYPES["MODULE_BATTLE_CODE_SET"],)).fetchone())
        client.post("/modules/battle-code", data={"action": "clear"})
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT selected_battle_code_condition_key, selected_battle_code_effect_key FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertIsNone(row["selected_battle_code_condition_key"])
            self.assertIsNone(row["selected_battle_code_effect_key"])

    def test_effect_helpers_cover_core_rules(self):
        state = battle_codes.init_state(battle_codes.snapshot("battle_start", "attack_up_15"))
        hp, lines = battle_codes.battle_start(state, 100, 100)
        self.assertEqual(hp, 100)
        self.assertTrue(lines)
        atk, cri, force_hit, _ = battle_codes.apply_attack_modifiers(state, atk=100, cri=5, force_hit=False, turn=1)
        self.assertEqual(atk, 115)
        atk3, _, _, _ = battle_codes.apply_attack_modifiers(state, atk=100, cri=5, force_hit=False, turn=3)
        self.assertEqual(atk3, 100)

        low = battle_codes.init_state(battle_codes.snapshot("low_hp_30", "defense_up_15"))
        hp, lines = battle_codes.turn_start(low, 1, 30, 100, 100, 100)
        self.assertTrue(lines)
        self.assertEqual(battle_codes.apply_defense_modifiers(low, 100, 1), 115)
        hp, off_lines = battle_codes.turn_start(low, 2, 31, 100, 100, 100)
        self.assertTrue(off_lines)
        self.assertEqual(battle_codes.apply_defense_modifiers(low, 100, 2), 100)

        miss = battle_codes.init_state(battle_codes.snapshot("after_miss", "guaranteed_hit"))
        hp, lines = battle_codes.after_player_attack(miss, turn=1, missed=True, critical=False, enemy_hp=100, enemy_max_hp=100, player_hp=100, player_max_hp=100)
        self.assertTrue(lines)
        _, _, force_hit, consume = battle_codes.apply_attack_modifiers(miss, atk=10, cri=1, force_hit=False, turn=2)
        self.assertTrue(force_hit)
        self.assertTrue(consume)

        heal = battle_codes.init_state(battle_codes.snapshot("low_hp_30", "heal_8"))
        hp, lines = battle_codes.turn_start(heal, 1, 25, 100, 100, 100)
        self.assertEqual(hp, 33)
        self.assertTrue(lines)
        hp0, _ = battle_codes.turn_start(battle_codes.init_state(battle_codes.snapshot("battle_start", "heal_8")), 1, 0, 100, 100, 100)
        self.assertEqual(hp0, 0)

    def test_dual_logic_prioritizes_a_and_locks_after_first_activation(self):
        state = battle_codes.init_state(
            battle_codes.snapshot_dual("battle_start", "attack_up_15", "enemy_heavy", "defense_up_15")
        )
        hp, lines = battle_codes.battle_start(state, 100, 100, enemy_trait_key="heavy")
        self.assertEqual(hp, 100)
        self.assertTrue(lines)
        summary = battle_codes.summary(state)
        self.assertEqual(summary["code_version"], "dual")
        self.assertEqual(summary["activation_count"], 1)
        self.assertEqual(summary["triggered_logic"], "A")
        self.assertEqual(summary["triggered_condition_key"], "battle_start")
        hp, lines = battle_codes.turn_start(state, 2, 20, 100, 100, 100)
        self.assertEqual(hp, 20)
        self.assertEqual(lines, [])

    def test_dual_logic_uses_b_when_a_does_not_match_enemy_trait(self):
        state = battle_codes.init_state(
            battle_codes.snapshot_dual("enemy_fast", "guaranteed_hit", "enemy_heavy", "attack_up_15")
        )
        hp, lines = battle_codes.battle_start(state, 100, 100, enemy_trait_key="heavy")
        self.assertEqual(hp, 100)
        self.assertTrue(lines)
        summary = battle_codes.summary(state)
        self.assertEqual(summary["triggered_logic"], "B")
        self.assertTrue(summary["fallback_success"])

    def test_dual_selection_rejects_same_condition(self):
        result = battle_codes.validate_dual_selection("low_hp_30", "heal_8", "low_hp_30", "defense_up_15")
        self.assertFalse(result["ok"])
        self.assertIn("同じ条件", result["reason"])

    def test_modules_page_shows_cards_preview_and_current_code(self):
        self._grant()
        client = self._client()
        html = client.get("/modules").get_data(as_text=True)
        self.assertIn("戦闘命令構築 / BATTLE CODE", html)
        self.assertEqual(html.count("IF "), 10)
        self.assertEqual(html.count("THEN "), 6)
        self.assertIn("誤差修正式《REWRITE-FATE-LOCK》", html)
        client.post("/modules/battle-code", data={"action": "save", "condition_key": "after_miss", "effect_key": "guaranteed_hit"})
        html = client.get("/modules").get_data(as_text=True)
        self.assertIn("誤差修正式《REWRITE-FATE-LOCK》", html)

    def test_explore_records_summary_audit_and_clears_selected_code(self):
        self._grant()
        client = self._client()
        client.post("/modules/battle-code", data={"action": "save", "condition_key": "battle_start", "effect_key": "speed_up_15"})

        def attack(att_atk, att_acc, *_args, force_hit=False, return_detail=False, **_kwargs):
            return 20, False, {"miss": False, "hit_forced": bool(force_hit)}

        enemy = {"id": 990030, "key": "battle_code_enemy", "name_ja": "コード検証機", "image_path": "assets/placeholder_enemy.png", "tier": 1, "element": "NORMAL", "faction": "neutral", "hp": 20, "atk": 1, "def": 1, "spd": 1, "acc": 1, "cri": 1}
        with mock.patch.object(game_app, "_world_current_environment", return_value={"element": "NORMAL", "mode": "安定", "enemy_spawn_bonus": 0, "drop_bonus": 0, "reason": "test", "week_key": "2026-W30"}), \
             mock.patch.object(game_app, "_pick_enemy_for_area", return_value=enemy), \
             mock.patch.object(game_app, "resolve_attack", side_effect=attack), \
             mock.patch.object(game_app, "_has_area_boss_candidates", return_value=False), \
             mock.patch.object(game_app, "_roll_research_module_drop", return_value=None):
            resp = client.post("/explore", data={"area_key": "layer_2"}, follow_redirects=True)
        html = resp.get_data(as_text=True)
        self.assertIn("今回のBATTLE CODE", html)
        self.assertIn("先制起動式《ZERO-CHRONO-CODE》", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT selected_battle_code_condition_key FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertIsNone(row["selected_battle_code_condition_key"])
            self.assertEqual(int(db.execute("SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ?", (game_app.AUDIT_EVENT_TYPES["MODULE_BATTLE_CODE_FINISH"],)).fetchone()["c"]), 1)


if __name__ == "__main__":
    unittest.main()
