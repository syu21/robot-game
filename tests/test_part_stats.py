import unittest

from services.stats import (
    FUSE_SUCCESS_RATE,
    apply_series_bonus,
    apply_set_bonus,
    compute_part_stats,
    compute_robot_stats,
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

    def test_series_bonus_condition_and_progression(self):
        base = {"hp": 20, "atk": 20, "def": 20, "spd": 20, "acc": 20, "cri": 20}
        defs = {
            "insect_kabuto": [
                {"pieces_required": 2, "stat_key": "def", "value": 0.03},
                {"pieces_required": 4, "stat_key": "hp", "value": 0.05},
            ]
        }
        parts = [{"series": "insect_kabuto"}] * 4
        out_l1, counts_l1, applied_l1 = apply_series_bonus(base, parts[:2], defs, progress_layer=1)
        self.assertEqual(counts_l1["insect_kabuto"], 2)
        self.assertEqual(out_l1, base)
        self.assertEqual(applied_l1, [])

        out_l2, counts_l2, applied_l2 = apply_series_bonus(base, parts[:2], defs, progress_layer=2)
        self.assertEqual(counts_l2["insect_kabuto"], 2)
        self.assertGreater(out_l2["def"], base["def"])
        self.assertEqual(applied_l2[0]["stage_label"], "弱")

        out_l5, counts_l5, applied_l5 = apply_series_bonus(base, parts, defs, progress_layer=5)
        self.assertEqual(counts_l5["insect_kabuto"], 4)
        self.assertGreater(out_l5["def"], base["def"])
        self.assertGreater(out_l5["hp"], base["hp"])
        self.assertEqual({row["stat_key"] for row in applied_l5}, {"def", "hp"})

    def test_compute_robot_stats_returns_series_metadata(self):
        parts = [
            {
                "element": "NORMAL",
                "series": "insect_batta",
                "rarity": "N",
                "plus": 0,
                "w_hp": 0.3,
                "w_atk": 0.2,
                "w_def": 0.1,
                "w_spd": 0.2,
                "w_acc": 0.1,
                "w_cri": 0.1,
            }
            for _ in range(4)
        ]
        result = compute_robot_stats(
            parts,
            series_bonus_defs={
                "insect_batta": [
                    {"pieces_required": 2, "stat_key": "spd", "value": 0.03},
                    {"pieces_required": 4, "stat_key": "acc", "value": 0.05},
                ]
            },
            series_progress_layer=5,
        )
        self.assertEqual(result["series_counts"]["insect_batta"], 4)
        self.assertTrue(result["series_bonus"])
        self.assertEqual(result["set_bonus"], "NORMAL")

    def test_fuse_rate_bounds(self):
        self.assertEqual(FUSE_SUCCESS_RATE[0], 90)
        self.assertEqual(FUSE_SUCCESS_RATE[9], 7)


if __name__ == "__main__":
    unittest.main()
