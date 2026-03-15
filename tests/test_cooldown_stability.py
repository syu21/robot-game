import unittest

import app as game_app


class CooldownStabilityTests(unittest.TestCase):
    def test_remaining_cooldown_boundary_non_admin(self):
        now = 1_700_000_000
        user = {"is_admin": 0, "created_at": now - (80 * 3600)}
        ct = game_app._explore_ct_seconds_for_user(user, now_ts=now)
        self.assertEqual(game_app._remaining_cooldown_seconds(user, now - (ct - 1), now_ts=now), 1)
        self.assertEqual(game_app._remaining_cooldown_seconds(user, now - ct, now_ts=now), 0)
        self.assertEqual(game_app._remaining_cooldown_seconds(user, now - (ct + 1), now_ts=now), 0)

    def test_remaining_cooldown_admin_is_ignored(self):
        now = 1_700_000_000
        user = {"is_admin": 1, "created_at": now}
        self.assertEqual(game_app._remaining_cooldown_seconds(user, now, now_ts=now), 0)
        self.assertEqual(game_app._remaining_cooldown_seconds(user, now - 1, now_ts=now), 0)


if __name__ == "__main__":
    unittest.main()
