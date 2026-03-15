import unittest

from services.stats import (
    FUSE_SUCCESS_RATE,
    apply_set_bonus,
    compute_part_stats,
    generate_noisy_weights,
    plus_common,
    plus_hp_common,
)


class PartStatsTests(unittest.TestCase):
    def test_weight_normalization(self):
        w = generate_noisy_weights("HEAD")
        vals = [w["w_hp"], w["w_atk"], w["w_def"], w["w_spd"], w["w_acc"], w["w_cri"]]
        self.assertTrue(all(v > 0 for v in vals))
        self.assertAlmostEqual(sum(vals), 1.0, places=6)

    def test_plus_monotonic(self):
        commons = [plus_common(i) for i in range(8)]
        hps = [plus_hp_common(i) for i in range(8)]
        self.assertEqual(commons, sorted(commons))
        self.assertEqual(hps, sorted(hps))

    def test_part_stats_structure(self):
        part = {
            "rarity": "SR",
            "plus": 2,
            "w_hp": 0.3,
            "w_atk": 0.2,
            "w_def": 0.15,
            "w_spd": 0.15,
            "w_acc": 0.1,
            "w_cri": 0.1,
        }
        s = compute_part_stats(part)
        self.assertEqual(set(s.keys()), {"hp", "atk", "def", "spd", "acc", "cri"})
        self.assertTrue(all(v > 0 for v in s.values()))

    def test_set_bonus_condition(self):
        base = {"hp": 10, "atk": 10, "def": 10, "spd": 10, "acc": 10, "cri": 10}
        parts_same = [{"element": "FIRE"}] * 4
        out, elem = apply_set_bonus(base, parts_same)
        self.assertEqual(elem, "FIRE")
        self.assertGreater(out["atk"], base["atk"])
        parts_mixed = [{"element": "FIRE"}, {"element": "WATER"}, {"element": "FIRE"}, {"element": "FIRE"}]
        out2, elem2 = apply_set_bonus(base, parts_mixed)
        self.assertIsNone(elem2)
        self.assertEqual(out2, base)

    def test_fuse_rate_bounds(self):
        self.assertEqual(FUSE_SUCCESS_RATE[0], 90)
        self.assertEqual(FUSE_SUCCESS_RATE[9], 7)


if __name__ == "__main__":
    unittest.main()
