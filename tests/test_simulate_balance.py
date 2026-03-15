import random
import unittest

import app as game_app
from services.simulate_balance import resolve_attack, simulate_battle


class _FixedRng:
    def __init__(self, random_values, randint_value=0):
        self._vals = list(random_values)
        self._idx = 0
        self._randint_value = randint_value

    def random(self):
        if self._idx < len(self._vals):
            v = self._vals[self._idx]
            self._idx += 1
            return v
        return self._vals[-1] if self._vals else 0.0

    def randint(self, _a, _b):
        return self._randint_value

    def uniform(self, a, b):
        v = self.random()
        return a + (b - a) * v


class BalanceSimulationTests(unittest.TestCase):
    def test_simulate_battle_reproducible_with_seed(self):
        player = {"hp": 40, "atk": 10, "def": 8, "spd": 11, "acc": 12, "cri": 4}
        enemy = {"hp": 34, "atk": 9, "def": 7, "spd": 10, "acc": 11, "cri": 3}
        r1 = simulate_battle(player, enemy, seed=123, max_turns=8)
        r2 = simulate_battle(player, enemy, seed=123, max_turns=8)
        self.assertEqual(r1, r2)

    def test_simulate_battle_timeout_never_exceeds_max_turns(self):
        player = {"hp": 500, "atk": 1, "def": 999, "spd": 10, "acc": 1, "cri": 1}
        enemy = {"hp": 500, "atk": 1, "def": 999, "spd": 9, "acc": 1, "cri": 1}
        result = simulate_battle(player, enemy, seed=9, max_turns=8)
        self.assertLessEqual(result["turns"], 8)
        self.assertTrue(result["timeout"])

    def test_batch_simulation_reproducible_with_seed(self):
        players = [
            {"stats": {"hp": 40, "atk": 10, "def": 8, "spd": 11, "acc": 12, "cri": 4}},
            {"stats": {"hp": 32, "atk": 9, "def": 7, "spd": 13, "acc": 13, "cri": 5}},
        ]
        enemies = [
            {"key": "e1", "name_ja": "敵1", "hp": 34, "atk": 9, "def": 7, "spd": 10, "acc": 11, "cri": 3},
            {"key": "e2", "name_ja": "敵2", "hp": 45, "atk": 11, "def": 9, "spd": 9, "acc": 12, "cri": 4},
        ]
        s1 = game_app._run_balance_simulation(players, enemies, 300, random.Random(42))
        s2 = game_app._run_balance_simulation(players, enemies, 300, random.Random(42))
        self.assertAlmostEqual(s1["win_rate"], s2["win_rate"])
        self.assertAlmostEqual(s1["avg_turns"], s2["avg_turns"])
        self.assertAlmostEqual(s1["timeout_rate"], s2["timeout_rate"])
        self.assertEqual(s1["enemy_rows"], s2["enemy_rows"])

    def test_batch_simulation_respects_layer3_tier_weights(self):
        players = [{"stats": {"hp": 999, "atk": 999, "def": 999, "spd": 999, "acc": 999, "cri": 0}}]
        enemies = [
            {"key": "t2", "name_ja": "tier2", "tier": 2, "element": "WIND", "hp": 1, "atk": 1, "def": 1, "spd": 1, "acc": 1, "cri": 1},
            {"key": "t3", "name_ja": "tier3", "tier": 3, "element": "ICE", "hp": 1, "atk": 1, "def": 1, "spd": 1, "acc": 1, "cri": 1},
        ]
        s = game_app._run_balance_simulation(players, enemies, 5000, random.Random(7), area_key="layer_3")
        by_key = {r["key"]: r for r in s["enemy_rows"]}
        t2_rate = by_key["t2"]["battles"] / 5000.0
        t3_rate = by_key["t3"]["battles"] / 5000.0
        self.assertTrue(0.17 <= t2_rate <= 0.23)
        self.assertTrue(0.77 <= t3_rate <= 0.83)

    def test_swift_increases_first_strike_damage(self):
        rng = _FixedRng([0.0, 0.99], randint_value=0)
        dmg_plain, _ = resolve_attack(10, 10, 1, 0, 10, rng=rng)
        rng2 = _FixedRng([0.0, 0.99], randint_value=0)
        dmg_swift, _ = resolve_attack(
            10,
            10,
            1,
            0,
            10,
            rng=rng2,
            attacker_archetype={"key": "swift"},
            attacker_is_first_striker=True,
        )
        self.assertEqual(dmg_plain, 10)
        self.assertEqual(dmg_swift, 11)

    def test_fortress_reduces_incoming_damage(self):
        rng = _FixedRng([0.0, 0.99], randint_value=0)
        dmg_plain, _ = resolve_attack(10, 10, 1, 0, 10, rng=rng)
        rng2 = _FixedRng([0.0, 0.99], randint_value=0)
        dmg_fortress, _ = resolve_attack(
            10,
            10,
            1,
            0,
            10,
            rng=rng2,
            defender_archetype={"key": "fortress"},
        )
        self.assertEqual(dmg_plain, 10)
        self.assertEqual(dmg_fortress, 9)

    def test_sniper_increases_hit_rate(self):
        rng = _FixedRng([0.77], randint_value=0)
        dmg_plain, _ = resolve_attack(10, 10, 1, 0, 10, rng=rng)
        rng2 = _FixedRng([0.77, 0.99], randint_value=0)
        dmg_sniper, _ = resolve_attack(
            10,
            10,
            1,
            0,
            10,
            rng=rng2,
            attacker_archetype={"key": "sniper"},
        )
        self.assertEqual(dmg_plain, 0)
        self.assertGreater(dmg_sniper, 0)

    def test_simulate_battle_reproducible_with_archetype_toggle(self):
        player = {"hp": 40, "atk": 10, "def": 8, "spd": 11, "acc": 12, "cri": 4}
        enemy = {"hp": 34, "atk": 9, "def": 7, "spd": 10, "acc": 11, "cri": 3}
        r1 = simulate_battle(
            player,
            enemy,
            seed=222,
            max_turns=8,
            player_archetype={"key": "swift"},
            enable_archetype=True,
        )
        r2 = simulate_battle(
            player,
            enemy,
            seed=222,
            max_turns=8,
            player_archetype={"key": "swift"},
            enable_archetype=True,
        )
        r3 = simulate_battle(
            player,
            enemy,
            seed=222,
            max_turns=8,
            player_archetype={"key": "swift"},
            enable_archetype=False,
        )
        r4 = simulate_battle(
            player,
            enemy,
            seed=222,
            max_turns=8,
            player_archetype={"key": "swift"},
            enable_archetype=False,
        )
        self.assertEqual(r1, r2)
        self.assertEqual(r3, r4)

    def test_damage_noise_range_applies_in_resolve_attack(self):
        rng = _FixedRng([0.0, 0.5, 0.99], randint_value=0)
        dmg, _crit, detail = resolve_attack(
            20,
            10,
            1,
            0,
            10,
            rng=rng,
            return_detail=True,
            damage_noise_range=(0.95, 1.05),
        )
        self.assertGreaterEqual(dmg, 19)
        self.assertLessEqual(dmg, 21)
        self.assertEqual(detail.get("damage_noise_low"), 0.95)
        self.assertEqual(detail.get("damage_noise_high"), 1.05)


if __name__ == "__main__":
    unittest.main()
