import unittest
from unittest import mock

import app as game_app


class ExploreDropBudgetTests(unittest.TestCase):
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

        with mock.patch.object(game_app.random, "random", return_value=0.0), mock.patch.object(
            game_app, "_add_part_drop", side_effect=fake_add_part_drop
        ) as add_mock:
            rewards = game_app._roll_battle_rewards(
                db=None,
                user_id=1,
                tier=1,
                part_drop_budget=budget,
            )

        self.assertEqual(budget, 1)
        self.assertEqual(len(rewards["dropped_parts"]), 1)
        self.assertEqual(add_mock.call_args.kwargs["rarity"], "N")
        self.assertEqual(add_mock.call_args.kwargs["plus"], 0)
        self.assertEqual(int(rewards.get("suppressed_part_drops") or 0), 0)

    def test_chain_explore_still_drops_at_most_one_part(self):
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

        with mock.patch.object(game_app.random, "random", return_value=0.0), mock.patch.object(
            game_app, "_add_part_drop", side_effect=fake_add_part_drop
        ):
            rewards = game_app._roll_battle_rewards(
                db=None,
                user_id=1,
                tier=1,
                part_drop_budget=budget,
            )

        self.assertEqual(budget, 2)
        self.assertEqual(len(rewards["dropped_parts"]), 1)
        self.assertEqual(int(rewards.get("suppressed_part_drops") or 0), 0)

    def test_chain_cap_remains_two_even_if_more_than_two_fights(self):
        self.assertEqual(game_app._explore_part_drop_budget(3), 2)
        self.assertEqual(game_app._explore_part_drop_budget(5), 2)


if __name__ == "__main__":
    unittest.main()
