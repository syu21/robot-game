import unittest

import app as game_app


def _power_score(enemy):
    return sum(
        int(enemy.get(stat) or 0)
        for stat in ("hp", "atk", "def", "spd", "acc", "cri")
    )


class HighLayerEnemyScaleTests(unittest.TestCase):
    def test_layer4_and_layer5_regular_enemies_outscale_layer3_boss_baseline(self):
        base_boss = dict(game_app.ENEMY_SEED_STATS["boss_ignis_reaver"])
        effective_boss = game_app._apply_boss_type_modifiers(dict(base_boss))
        base_boss_hp = int(base_boss["hp"])
        effective_boss_score = _power_score(effective_boss)

        for enemy_key, enemy in game_app.ENEMY_SEED_STATS.items():
            if enemy.get("is_boss"):
                continue
            if int(enemy.get("tier") or 0) not in {4, 5}:
                continue
            self.assertGreaterEqual(
                int(enemy["hp"]),
                base_boss_hp,
                f"{enemy_key} should have at least layer3 boss-class HP",
            )
            self.assertGreater(
                _power_score(enemy),
                effective_boss_score,
                f"{enemy_key} should outscale the effective layer3 boss baseline",
            )

    def test_layer4_and_layer5_bosses_stay_above_regular_enemy_band(self):
        layer4_regular_keys = (
            "fort_ironbulk",
            "fort_platehound",
            "fort_bastion_eye",
            "haze_mirage_mite",
            "haze_fog_lancer",
            "haze_glint_drone",
            "burst_coreling",
            "burst_shockfang",
            "burst_ruptgear",
        )
        layer5_regular_keys = (
            "lab_guardian_veil",
            "lab_bulwark_node",
            "lab_trace_hound",
            "lab_fault_keeper",
            "pin_flare_beast",
            "pin_rupture_eye",
            "pin_scorch_fang",
            "pin_crash_gear",
        )
        layer4_boss_keys = (
            "boss_4_forge_elguard",
            "boss_4_haze_mirage",
            "boss_4_burst_volterio",
            "boss_4_final_ark_zero",
        )
        layer5_boss_keys = (
            "boss_5_labyrinth_nyx_array",
            "boss_5_pinnacle_ignition_king",
            "boss_5_final_omega_frame",
        )

        max_layer4_regular = max(_power_score(game_app.ENEMY_SEED_STATS[key]) for key in layer4_regular_keys)
        max_layer5_regular = max(_power_score(game_app.ENEMY_SEED_STATS[key]) for key in layer5_regular_keys)

        for key in layer4_boss_keys:
            self.assertGreater(
                _power_score(game_app.ENEMY_SEED_STATS[key]),
                max_layer4_regular,
                f"{key} should stay above layer4 regular enemies",
            )
        for key in layer5_boss_keys:
            self.assertGreater(
                _power_score(game_app.ENEMY_SEED_STATS[key]),
                max_layer5_regular,
                f"{key} should stay above layer5 regular enemies",
            )


if __name__ == "__main__":
    unittest.main()
