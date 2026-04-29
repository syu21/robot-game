import unittest

from services.battle_affinity import apply_affinity_damage, get_type_affinity


class BattleAffinityTests(unittest.TestCase):
    def test_affinity_triangle(self):
        cases = [
            ("burst", "desperate"),
            ("desperate", "stable"),
            ("stable", "burst"),
            ("burst", "desperation"),
        ]
        for attacker, defender in cases:
            with self.subTest(attacker=attacker, defender=defender):
                affinity = get_type_affinity(attacker, defender)
                self.assertEqual(affinity["result"], "advantage")
                self.assertGreater(float(affinity["attack_multiplier"]), 1.0)

    def test_reverse_and_same_type(self):
        self.assertEqual(get_type_affinity("desperate", "burst")["result"], "disadvantage")
        self.assertLess(float(get_type_affinity("desperate", "burst")["attack_multiplier"]), 1.0)
        self.assertEqual(get_type_affinity("stable", "stable")["result"], "neutral")

    def test_unknown_is_safe_and_zero_damage_stays_zero(self):
        affinity = get_type_affinity(None, "burst")
        self.assertEqual(affinity["result"], "unknown")
        self.assertEqual(apply_affinity_damage(0, affinity), 0)
        self.assertEqual(apply_affinity_damage(10, affinity), 10)


if __name__ == "__main__":
    unittest.main()
