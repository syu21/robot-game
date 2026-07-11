import unittest

import app as game_app


class ModuleTraitBattleTests(unittest.TestCase):
    def test_opening_assault_only_boosts_first_turn(self):
        state = game_app._module_trait_state({"instance_id": 1, "name_ja": "試験", "trait_key": "opening_assault", "trait_value": 5})
        atk, acc, lines = game_app._module_before_player_attack(state, turn=1, is_boss=False, atk=10, acc=10)
        self.assertEqual(atk, 15)
        self.assertEqual(acc, 10)
        self.assertTrue(lines)
        atk2, _acc2, lines2 = game_app._module_before_player_attack(state, turn=2, is_boss=False, atk=10, acc=10)
        self.assertEqual(atk2, 10)
        self.assertFalse(lines2)

    def test_precision_retry_consumes_miss_state_once(self):
        state = game_app._module_trait_state({"instance_id": 1, "name_ja": "試験", "trait_key": "precision_retry", "trait_value": 7})
        game_app._module_after_player_attack(state, missed=True, critical=False)
        _atk, acc, lines = game_app._module_before_player_attack(state, turn=2, is_boss=False, atk=10, acc=10)
        self.assertEqual(acc, 17)
        self.assertTrue(lines)
        _atk2, acc2, lines2 = game_app._module_before_player_attack(state, turn=3, is_boss=False, atk=10, acc=10)
        self.assertEqual(acc2, 10)
        self.assertFalse(lines2)

    def test_boss_analysis_only_works_in_boss_battle(self):
        state = game_app._module_trait_state({"instance_id": 1, "name_ja": "試験", "trait_key": "boss_analysis", "trait_value": 4})
        _atk, normal_acc, normal_lines = game_app._module_before_player_attack(state, turn=1, is_boss=False, atk=10, acc=10)
        self.assertEqual(normal_acc, 10)
        self.assertFalse(normal_lines)
        _atk2, boss_acc, boss_lines = game_app._module_before_player_attack(state, turn=1, is_boss=True, atk=10, acc=10)
        self.assertEqual(boss_acc, 14)
        self.assertTrue(boss_lines)
        boss_def, def_lines = game_app._module_before_enemy_attack(state, is_boss=True, player_hp=10, player_max_hp=20, defense=10)
        self.assertEqual(boss_def, 14)
        self.assertTrue(def_lines)

    def test_trait_none_is_noop(self):
        state = game_app._module_trait_state({"instance_id": 1, "name_ja": "試験", "trait_key": None, "trait_value": 0})
        atk, acc, lines = game_app._module_before_player_attack(state, turn=1, is_boss=True, atk=10, acc=10)
        defense, def_lines = game_app._module_before_enemy_attack(state, is_boss=True, player_hp=1, player_max_hp=10, defense=10)
        self.assertEqual((atk, acc, defense), (10, 10, 10))
        self.assertFalse(lines)
        self.assertFalse(def_lines)


if __name__ == "__main__":
    unittest.main()
