import unittest

import app as game_app
from services import battle_codes
from services import weekly_anomaly


class CombatSignalTests(unittest.TestCase):
    def test_layer1_enemy_has_no_signal_by_default(self):
        enemy = {"key": "enemy1", "name_ja": "通常敵"}
        self.assertIsNone(game_app._combat_signal_view(enemy))
        self.assertIsNone(game_app._combat_signal_battle_state(game_app._combat_signal_pattern_for_enemy(enemy)))

    def test_layer6_enemy_resolves_fixed_signal_snapshot(self):
        enemy = {"key": "deep_layer_6_final_deep_layer_5_final_burst_coreling", "name_ja": "深層核"}
        view = game_app._combat_signal_view(enemy)
        self.assertEqual(view["key"], "overcharge")
        self.assertEqual(view["label"], "OVERCHARGE")
        self.assertEqual(view["telegraph_turn"], 2)
        self.assertEqual(view["trigger_turn"], 3)

    def test_signal_telegraphs_before_triggering(self):
        state = game_app._combat_signal_battle_state("lock_on")
        self.assertIsNone(game_app._combat_signal_turn_start(state, 1))
        telegraph = game_app._combat_signal_turn_start(state, 2)
        self.assertEqual(telegraph["phase"], "telegraph")
        self.assertIn("LOCK-ON", telegraph["line"])
        trigger = game_app._combat_signal_turn_start(state, 3)
        self.assertEqual(trigger["phase"], "trigger")
        self.assertTrue(game_app._combat_signal_is_active(state, 3))
        self.assertFalse(game_app._combat_signal_is_active(state, 4))

    def test_overcharge_attack_and_cooling_are_bounded(self):
        state = game_app._combat_signal_battle_state("overcharge")
        game_app._combat_signal_turn_start(state, 2)
        game_app._combat_signal_turn_start(state, 3)
        atk, acc, cri, lines = game_app._combat_signal_apply_enemy_attack_stats(
            state,
            atk=100,
            acc=50,
            cri=10,
            turn=3,
        )
        self.assertEqual(atk, 120)
        self.assertEqual(acc, 50)
        self.assertEqual(cri, 10)
        self.assertTrue(lines)
        game_app._combat_signal_after_enemy_attack(state, 3)
        damage, cooling_lines = game_app._combat_signal_apply_player_damage(state, 100, 4)
        self.assertEqual(damage, 108)
        self.assertTrue(cooling_lines)

    def test_aegis_reduces_player_damage_only_on_trigger_turn(self):
        state = game_app._combat_signal_battle_state("aegis")
        game_app._combat_signal_turn_start(state, 2)
        game_app._combat_signal_turn_start(state, 3)
        damage, lines = game_app._combat_signal_apply_player_damage(state, 100, 3)
        self.assertEqual(damage, 80)
        self.assertTrue(lines)
        next_damage, next_lines = game_app._combat_signal_apply_player_damage(state, 100, 4)
        self.assertEqual(next_damage, 100)
        self.assertEqual(next_lines, [])

    def test_battle_code_enemy_signal_condition_triggers_on_telegraph(self):
        state = battle_codes.init_state(battle_codes.snapshot("enemy_signal_phase_shift", "speed_up_15"))
        hp, lines = battle_codes.enemy_signal(state, 2, "phase_shift", 100, 100)
        self.assertEqual(hp, 100)
        self.assertTrue(lines)
        self.assertEqual(battle_codes.effective_speed(state, 100, 2), 115)

    def test_dual_battle_code_can_use_enemy_signal_fallback(self):
        state = battle_codes.init_state(
            battle_codes.snapshot_dual("enemy_signal_lock_on", "attack_up_15", "enemy_signal_overcharge", "defense_up_15")
        )
        hp, lines = battle_codes.enemy_signal(state, 2, "overcharge", 100, 100)
        self.assertEqual(hp, 100)
        self.assertTrue(lines)
        summary = battle_codes.summary(state)
        self.assertEqual(summary["triggered_logic"], "B")
        self.assertEqual(summary["triggered_condition_key"], "enemy_signal_overcharge")

    def test_weekly_anomaly_cycle_exposes_combat_signal(self):
        config = weekly_anomaly.build_cycle_config("2026-W33")
        signal = config.get("combat_signal") or {}
        self.assertIn(signal.get("key"), {"phase_shift", "aegis", "overcharge", "lock_on"})
        self.assertTrue(signal.get("label"))


if __name__ == "__main__":
    unittest.main()
