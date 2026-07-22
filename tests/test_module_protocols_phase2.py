import os
import tempfile
import time
import unittest
from unittest import mock

import app as game_app
import init_db
from services import module_protocols


class FixedRng:
    def __init__(self, values):
        self.values = list(values)

    def random(self):
        return self.values.pop(0) if self.values else 1.0


class ModuleProtocolPhase2Tests(unittest.TestCase):
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
                VALUES ('protocol_tester', 'x', ?, 1, 0, 4)
                """,
                (now,),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = 'protocol_tester'").fetchone()["id"])
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
            session["username"] = "protocol_tester"
        return client

    def _create_robot(self, db):
        now = int(time.time())
        db.execute(
            "INSERT INTO robot_instances (user_id, name, status, created_at, updated_at) VALUES (?, 'ProtocolBot', 'active', ?, ?)",
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

    def _grant(self, module_key, brand_key, role_key="guard"):
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

    def test_unlocks_basic_advanced_and_hybrid_protocols(self):
        titan2 = game_app._module_loadout_summary([{"brand_key": "titan"}, {"brand_key": "titan"}])
        options = {item["protocol_key"]: item["is_unlocked"] for item in module_protocols.available_protocols(titan2)}
        self.assertTrue(options["fortress_guard"])
        self.assertFalse(options["emergency_repair"])

        titan3 = game_app._module_loadout_summary([{"brand_key": "titan"}, {"brand_key": "titan"}, {"brand_key": "titan"}])
        options = {item["protocol_key"]: item["is_unlocked"] for item in module_protocols.available_protocols(titan3)}
        self.assertTrue(options["fortress_guard"])
        self.assertTrue(options["emergency_repair"])

        hybrid = game_app._module_loadout_summary([{"brand_key": "titan"}, {"brand_key": "volt"}, {"brand_key": "eden"}])
        options = {item["protocol_key"]: item["is_unlocked"] for item in module_protocols.available_protocols(hybrid)}
        self.assertTrue(options["adaptive_shift"])
        self.assertFalse(options["fortress_guard"])

    def test_protocol_effect_helpers_cover_core_rules(self):
        loadout = game_app._module_loadout_summary([{"brand_key": "titan"}, {"brand_key": "titan"}, {"brand_key": "titan"}])
        state = module_protocols.init_protocol_state("fortress_guard", loadout)
        self.assertEqual(module_protocols.apply_incoming_damage(state, 100, turn=1)[0], 85)
        self.assertEqual(module_protocols.apply_incoming_damage(state, 100, turn=4)[0], 100)

        repair = module_protocols.init_protocol_state("emergency_repair", loadout)
        hp, lines = module_protocols.after_player_damage(repair, turn=2, player_hp=25, player_max_hp=100)
        self.assertEqual(hp, 37)
        self.assertTrue(lines)
        hp2, lines2 = module_protocols.after_player_damage(repair, turn=3, player_hp=20, player_max_hp=100)
        self.assertEqual(hp2, 20)
        self.assertFalse(lines2)
        hp0, _ = module_protocols.after_player_damage(module_protocols.init_protocol_state("emergency_repair", loadout), turn=2, player_hp=0, player_max_hp=100)
        self.assertEqual(hp0, 0)

        volt = game_app._module_loadout_summary([{"brand_key": "volt"}, {"brand_key": "volt"}, {"brand_key": "volt"}])
        accel = module_protocols.init_protocol_state("opening_acceleration", volt)
        self.assertEqual(module_protocols.effective_speed(accel, 10, 1), 12)
        self.assertEqual(module_protocols.effective_speed(accel, 10, 3), 10)
        chain = module_protocols.init_protocol_state("critical_chain", volt)
        self.assertTrue(module_protocols.after_player_attack(chain, turn=1, missed=False, critical=True))
        self.assertEqual(module_protocols.apply_attack_modifiers(chain, atk=10, acc=10, cri=5, force_hit=False, turn=2)[2], 20)
        self.assertFalse(chain.get("pending_critical_bonus"))

        eden = game_app._module_loadout_summary([{"brand_key": "eden"}, {"brand_key": "eden"}, {"brand_key": "eden"}])
        analysis = module_protocols.init_protocol_state("target_analysis", eden)
        self.assertEqual(module_protocols.apply_attack_modifiers(analysis, atk=10, acc=5, cri=1, force_hit=False, turn=1)[1], 15)
        correction = module_protocols.init_protocol_state("miss_correction", eden)
        module_protocols.after_player_attack(correction, turn=1, missed=True, critical=False)
        self.assertTrue(module_protocols.apply_attack_modifiers(correction, atk=10, acc=5, cri=1, force_hit=False, turn=2)[3])

        scrap = game_app._module_loadout_summary([{"brand_key": "scrap_x"}, {"brand_key": "scrap_x"}, {"brand_key": "scrap_x"}])
        limit_break = module_protocols.init_protocol_state("limit_break", scrap)
        module_protocols.turn_start(limit_break, 1, 35, 100, 100, 100)
        self.assertEqual(module_protocols.apply_attack_modifiers(limit_break, atk=10, acc=5, cri=1, force_hit=False, turn=1)[0], 12)
        self.assertEqual(module_protocols.apply_defense_modifiers(limit_break, 10, 1), 9)
        overdrive = module_protocols.init_protocol_state("unstable_overdrive", scrap)
        damage, recoil, _ = module_protocols.apply_outgoing_damage(overdrive, 20, turn=1, player_max_hp=100, rng=FixedRng([0.0]))
        self.assertEqual(damage, 30)
        self.assertEqual(recoil, 5)

        nova = game_app._module_loadout_summary([{"brand_key": "nova"}, {"brand_key": "nova"}, {"brand_key": "nova"}])
        adaptive = module_protocols.init_protocol_state("adaptive_shift", nova)
        module_protocols.battle_start(adaptive, {"atk": 50, "def": 10, "spd": 10, "acc": 10})
        self.assertEqual(adaptive["selected_adaptation"], "def")
        tie = module_protocols.init_protocol_state("adaptive_shift", nova)
        module_protocols.battle_start(tie, {"atk": 10, "def": 10, "spd": 10, "acc": 10})
        self.assertEqual(tie["selected_adaptation"], "hp")
        reconf = module_protocols.init_protocol_state("emergency_reconfiguration", nova)
        lines = module_protocols.turn_start(reconf, 4, 80, 100, 30, 100)
        self.assertTrue(lines)
        self.assertEqual(reconf["temporary_bonus"], {"atk_pct": 0.15})

    def test_route_rejects_tampered_protocol_and_auto_clears_on_loadout_change(self):
        ids = [self._grant("heavy_prototype", "titan") for _ in range(3)]
        client = self._client()
        client.post("/modules/select", data={"module_instance_ids": [str(mid) for mid in ids]})
        client.post("/modules/protocol", data={"protocol_key": "emergency_repair"})
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertEqual(db.execute("SELECT selected_module_protocol_key FROM users WHERE id = ?", (self.user_id,)).fetchone()["selected_module_protocol_key"], "emergency_repair")

        volt_id = self._grant("assault_prototype", "volt", role_key="speed")
        client.post("/modules/select", data={"module_instance_ids": [str(ids[0]), str(volt_id)]})
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertIsNone(db.execute("SELECT selected_module_protocol_key FROM users WHERE id = ?", (self.user_id,)).fetchone()["selected_module_protocol_key"])
            event = db.execute("SELECT id FROM world_events_log WHERE event_type = ? ORDER BY id DESC LIMIT 1", (game_app.AUDIT_EVENT_TYPES["MODULE_PROTOCOL_AUTO_CLEAR"],)).fetchone()
            self.assertIsNotNone(event)

        client.post("/modules/protocol", data={"protocol_key": "fortress_guard"})
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertIsNone(db.execute("SELECT selected_module_protocol_key FROM users WHERE id = ?", (self.user_id,)).fetchone()["selected_module_protocol_key"])

    def test_protocol_start_finish_and_clear_after_explore(self):
        ids = [self._grant("heavy_prototype", "titan") for _ in range(3)]
        client = self._client()
        client.post("/modules/select", data={"module_instance_ids": [str(mid) for mid in ids]})
        client.post("/modules/protocol", data={"protocol_key": "fortress_guard"})

        calls = {"count": 0}

        def attack(att_atk, att_acc, *_args, force_hit=False, return_detail=False, **_kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return 1, False, {"miss": False, "hit_forced": bool(force_hit)}
            return 20, False, {"miss": False, "hit_forced": bool(force_hit)}

        enemy = {"id": 990020, "key": "protocol_enemy", "name_ja": "プロトコル検証機", "image_path": "assets/placeholder_enemy.png", "tier": 1, "element": "NORMAL", "faction": "neutral", "hp": 30, "atk": 30, "def": 1, "spd": 999, "acc": 999, "cri": 1}
        with mock.patch.object(game_app, "_world_current_environment", return_value={"element": "NORMAL", "mode": "安定", "enemy_spawn_bonus": 0, "drop_bonus": 0, "reason": "test", "week_key": "2026-W30"}), \
             mock.patch.object(game_app, "_pick_enemy_for_area", return_value=enemy), \
             mock.patch.object(game_app, "resolve_attack", side_effect=attack), \
             mock.patch.object(game_app, "_has_area_boss_candidates", return_value=False), \
             mock.patch.object(game_app, "_roll_research_module_drop", return_value=None):
            resp = client.post("/explore", data={"area_key": "layer_2"}, follow_redirects=True)
        html = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("今回起動した秘匿命令", html)
        self.assertIn("絶対防衛機構《アイギス・ウォール》", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertIsNone(db.execute("SELECT selected_module_protocol_key FROM users WHERE id = ?", (self.user_id,)).fetchone()["selected_module_protocol_key"])
            self.assertIsNotNone(db.execute("SELECT id FROM world_events_log WHERE event_type = ? LIMIT 1", (game_app.AUDIT_EVENT_TYPES["MODULE_PROTOCOL_START"],)).fetchone())
            self.assertIsNotNone(db.execute("SELECT id FROM world_events_log WHERE event_type = ? LIMIT 1", (game_app.AUDIT_EVENT_TYPES["MODULE_PROTOCOL_TRIGGER"],)).fetchone())
            finish_count = int(db.execute("SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ?", (game_app.AUDIT_EVENT_TYPES["MODULE_PROTOCOL_FINISH"],)).fetchone()["c"])
            self.assertEqual(finish_count, 1)


if __name__ == "__main__":
    unittest.main()
