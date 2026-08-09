import sqlite3
import unittest

from services.robot_tuning import (
    DAILY_GAIN_LIMIT,
    TOTAL_LEVEL_CAP,
    allocate_tuning_points,
    apply_tuning_bonus,
    ensure_robot_tuning_schema,
    get_or_create_tuning_state,
    grant_tuning_xp,
    reset_tuning_state,
    tuning_summary,
)


class RobotTuningServiceTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, coins INTEGER NOT NULL DEFAULT 0)")
        self.db.execute(
            """
            CREATE TABLE robot_instances (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
            )
            """
        )
        ensure_robot_tuning_schema(self.db)
        self.db.execute("INSERT INTO users (id, coins) VALUES (1, 1000)")
        self.db.execute("INSERT INTO robot_instances (id, user_id) VALUES (10, 1)")
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_layer1_is_not_eligible_in_v1(self):
        result = grant_tuning_xp(
            self.db,
            user_id=1,
            robot_instance_id=10,
            area_key="layer_1",
            won=True,
            day_key="2026-08-04",
            source_battle_id=100,
            feature_open=True,
        )
        self.assertFalse(result["granted"])
        self.assertEqual(result["reason"], "area_not_eligible")

    def test_grant_is_idempotent_by_battle_id(self):
        first = grant_tuning_xp(
            self.db,
            user_id=1,
            robot_instance_id=10,
            area_key="layer_2",
            won=True,
            day_key="2026-08-04",
            source_battle_id=101,
            source_request_id="req-1",
            feature_open=True,
        )
        second = grant_tuning_xp(
            self.db,
            user_id=1,
            robot_instance_id=10,
            area_key="layer_2",
            won=True,
            day_key="2026-08-04",
            source_battle_id=101,
            source_request_id="req-1",
            feature_open=True,
        )
        state = get_or_create_tuning_state(self.db, 10, 1)
        xp_total = sum(int(state[f"{key}_xp"] or 0) for key in ("hp", "atk", "def", "spd", "acc", "cri"))
        self.assertTrue(first["granted"])
        self.assertFalse(second["granted"])
        self.assertEqual(second["reason"], "duplicate")
        self.assertEqual(xp_total, 1)

    def test_layer6_win_is_eligible_for_tuning_xp(self):
        result = grant_tuning_xp(
            self.db,
            user_id=1,
            robot_instance_id=10,
            area_key="layer_6_rebuild",
            won=True,
            day_key="2026-08-04",
            source_battle_id=1060,
            source_request_id="layer6-win",
            feature_open=True,
        )
        self.assertTrue(result["granted"])
        self.assertIn(result["stat_key"], {"hp", "def", "atk", "acc"})

    def test_daily_gain_limit_is_account_wide(self):
        for idx in range(DAILY_GAIN_LIMIT):
            result = grant_tuning_xp(
                self.db,
                user_id=1,
                robot_instance_id=10,
                area_key="layer_2",
                won=True,
                day_key="2026-08-04",
                source_battle_id=200 + idx,
                source_request_id=f"req-{idx}",
                feature_open=True,
            )
            self.assertTrue(result["granted"])
        capped = grant_tuning_xp(
            self.db,
            user_id=1,
            robot_instance_id=10,
            area_key="layer_2",
            won=True,
            day_key="2026-08-04",
            source_battle_id=999,
            source_request_id="req-cap",
            feature_open=True,
        )
        self.assertFalse(capped["granted"])
        self.assertEqual(capped["reason"], "daily_cap")

    def test_tuning_bonus_has_minimum_one_for_positive_base(self):
        adjusted, rows = apply_tuning_bonus({"hp": 10, "atk": 200, "def": 0, "spd": 1, "acc": 1, "cri": 1}, {"hp": 1, "atk": 4, "def": 8})
        self.assertEqual(adjusted["hp"], 11)
        self.assertEqual(adjusted["atk"], 206)
        self.assertEqual(adjusted["def"], 0)
        self.assertEqual(next(row for row in rows if row["key"] == "atk")["bonus"], 6)

    def test_reset_returns_levels_to_unassigned_and_allocate_validates_caps(self):
        self.db.execute(
            """
            INSERT INTO robot_tuning_states
                (robot_instance_id, user_id, hp_level, hp_xp, def_level, def_xp, created_at, updated_at)
            VALUES (10, 1, 3, 7, 2, 4, 1, 1)
            """
        )
        reset = reset_tuning_state(self.db, user_id=1, robot_instance_id=10, now_ts=100)
        self.assertTrue(reset["ok"])
        self.assertEqual(reset["returned_points"], 5)
        summary = tuning_summary(get_or_create_tuning_state(self.db, 10, 1))
        self.assertEqual(summary["total_level"], 0)
        self.assertEqual(summary["unassigned_points"], 5)
        bad = allocate_tuning_points(self.db, user_id=1, robot_instance_id=10, allocations={"hp": 9})
        self.assertFalse(bad["ok"])
        good = allocate_tuning_points(self.db, user_id=1, robot_instance_id=10, allocations={"hp": 3, "atk": 2})
        self.assertTrue(good["ok"])
        summary = tuning_summary(get_or_create_tuning_state(self.db, 10, 1))
        self.assertEqual(summary["total_level"], 5)
        self.assertEqual(summary["unassigned_points"], 0)

    def test_total_level_cap_blocks_growth(self):
        cols = []
        values = []
        for key in ("hp", "atk", "def"):
            cols.append(f"{key}_level")
            values.append(8)
        placeholders = ",".join(["?"] * len(values))
        self.db.execute(
            f"""
            INSERT INTO robot_tuning_states
                (robot_instance_id, user_id, {",".join(cols)}, created_at, updated_at)
            VALUES (10, 1, {placeholders}, 1, 1)
            """,
            values,
        )
        result = grant_tuning_xp(
            self.db,
            user_id=1,
            robot_instance_id=10,
            area_key="layer_2",
            won=True,
            day_key="2026-08-04",
            source_battle_id=300,
            feature_open=True,
        )
        self.assertFalse(result["granted"])
        self.assertEqual(result["reason"], "total_cap")
        self.assertEqual(tuning_summary(get_or_create_tuning_state(self.db, 10, 1))["total_level"], TOTAL_LEVEL_CAP)


if __name__ == "__main__":
    unittest.main()
