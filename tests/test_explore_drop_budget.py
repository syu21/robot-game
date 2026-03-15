import unittest
from unittest import mock

import app as game_app


class ExploreDropBudgetTests(unittest.TestCase):
    @staticmethod
    def _fake_weighted_pick(weight_map):
        keys = set(weight_map.keys())
        if "coin_only" in keys:
            return "parts_2"
        if 0 in keys:
            return 0
        return next(iter(weight_map.keys()))

    def test_normal_explore_part_drops_are_capped_at_one(self):
        budget = game_app._explore_part_drop_budget(1)
        counter = {"id": 0}

        def fake_add_part_drop(*_args, **_kwargs):
            counter["id"] += 1
            return {
                "part_instance_id": counter["id"],
                "part_type": "HEAD",
                "part_key": f"dummy_{counter['id']}",
                "rarity": "C",
                "plus": 0,
            }

        with mock.patch.object(game_app, "_weighted_pick", side_effect=self._fake_weighted_pick), mock.patch.object(
            game_app, "_add_part_drop", side_effect=fake_add_part_drop
        ):
            rewards = game_app._roll_battle_rewards(
                db=None,
                user_id=1,
                tier=1,
                part_drop_budget=budget,
            )

        self.assertEqual(budget, 1)
        self.assertEqual(len(rewards["dropped_parts"]), 1)
        self.assertEqual(int(rewards.get("suppressed_part_drops") or 0), 1)

    def test_chain_explore_part_drops_are_capped_at_two(self):
        budget = game_app._explore_part_drop_budget(2)
        counter = {"id": 0}

        def fake_add_part_drop(*_args, **_kwargs):
            counter["id"] += 1
            return {
                "part_instance_id": counter["id"],
                "part_type": "HEAD",
                "part_key": f"dummy_{counter['id']}",
                "rarity": "C",
                "plus": 0,
            }

        with mock.patch.object(game_app, "_weighted_pick", side_effect=self._fake_weighted_pick), mock.patch.object(
            game_app, "_add_part_drop", side_effect=fake_add_part_drop
        ):
            rewards = game_app._roll_battle_rewards(
                db=None,
                user_id=1,
                tier=1,
                part_drop_budget=budget,
            )

        self.assertEqual(budget, 2)
        self.assertEqual(len(rewards["dropped_parts"]), 2)
        self.assertEqual(int(rewards.get("suppressed_part_drops") or 0), 0)

    def test_chain_cap_remains_two_even_if_more_than_two_fights(self):
        self.assertEqual(game_app._explore_part_drop_budget(3), 2)
        self.assertEqual(game_app._explore_part_drop_budget(5), 2)


if __name__ == "__main__":
    unittest.main()
