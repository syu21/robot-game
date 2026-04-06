import unittest

from services.balance_simulator import (
    export_matchup_matrix,
    simulate_all_matchups,
    simulate_match,
    simulate_series,
)
from services.balance_templates import BALANCE_FAMILY_ORDER, get_balance_template_catalog


class BalanceSimulatorTests(unittest.TestCase):
    def test_template_catalog_has_expected_families_and_variants(self):
        catalog = get_balance_template_catalog()
        for family_key in BALANCE_FAMILY_ORDER:
            self.assertIn(family_key, catalog)
            self.assertGreaterEqual(len(catalog[family_key]), 3)

    def test_simulate_match_is_reproducible_with_seed(self):
        catalog = get_balance_template_catalog()
        robot_a = catalog["tank"][0]
        robot_b = catalog["burst"][0]
        first = simulate_match(robot_a, robot_b, seed=42)
        second = simulate_match(robot_a, robot_b, seed=42)
        self.assertEqual(first["winner"], second["winner"])
        self.assertEqual(first["turns"], second["turns"])
        self.assertEqual(first["timeout"], second["timeout"])
        self.assertEqual(first["a"]["damage_dealt"], second["a"]["damage_dealt"])
        self.assertEqual(first["b"]["damage_dealt"], second["b"]["damage_dealt"])

    def test_simulate_series_reports_expected_metrics(self):
        catalog = get_balance_template_catalog()
        result = simulate_series(catalog["accuracy"][0], catalog["crit"][0], n=25, seed_base=500)
        self.assertEqual(result["total_trials"], 25)
        self.assertAlmostEqual(
            result["a_win_rate"] + result["b_win_rate"] + result["draw_rate"],
            1.0,
            places=6,
        )
        self.assertIn("seed_check", result)
        self.assertTrue(result["seed_check"]["verified"])
        self.assertGreaterEqual(result["timeout_rate"], 0.0)
        self.assertLessEqual(result["timeout_rate"], 1.0)

    def test_simulate_all_matchups_builds_matrix(self):
        catalog = get_balance_template_catalog()
        report = simulate_all_matchups(catalog, n=5, seed_base=700)
        self.assertEqual(report["n"], 5)
        self.assertIn("family_matrix", report)
        self.assertIn("tank", report["family_matrix"])
        self.assertIn("burst", report["family_matrix"]["tank"])
        cell = report["family_matrix"]["tank"]["burst"]
        self.assertIn("a_win_rate", cell)
        self.assertIn("summary", report)
        self.assertIn("family_overall", report["summary"])

    def test_export_matchup_matrix_returns_csv(self):
        catalog = get_balance_template_catalog()
        report = simulate_all_matchups(catalog, n=3, seed_base=900)
        csv_text = export_matchup_matrix(report, format="csv")
        self.assertIn("type", csv_text)
        self.assertIn("鉄壁型", csv_text)
        self.assertIn("爆発型", csv_text)


if __name__ == "__main__":
    unittest.main()
