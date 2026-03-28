import unittest

from services.lab_casino_service import build_casino_entries
from services.lab_race_course import LAB_RACE_SEGMENT_COUNT, build_course_layout
from services.lab_race_engine import LAB_RACE_ENTRY_COUNT, create_race


class LabRaceCourseTests(unittest.TestCase):
    def test_course_generation_has_start_goal_and_2_to_5_specials(self):
        for seed in range(100, 120):
            course = build_course_layout(seed, course_key="scrapyard_sprint", mode="standard")
            self.assertEqual(len(course["segments"]), LAB_RACE_SEGMENT_COUNT)
            self.assertEqual(course["segments"][0]["kind"], "start")
            self.assertEqual(course["segments"][-1]["kind"], "goal")
            self.assertGreaterEqual(int(course["special_count"]), 2)
            self.assertLessEqual(int(course["special_count"]), 5)
            specials = [segment for segment in course["segments"] if segment["kind"] == "special"]
            self.assertEqual(len(specials), int(course["special_count"]))
            keys = [segment["feature_key"] for segment in specials]
            self.assertEqual(len(keys), len(set(keys)))
            indices = [segment["index"] for segment in specials]
            triple_special = any(indices[idx] + 1 == indices[idx + 1] and indices[idx + 1] + 1 == indices[idx + 2] for idx in range(len(indices) - 2))
            self.assertFalse(triple_special)

    def test_casino_entries_and_odds_change_by_seed(self):
        first = build_casino_entries(111111)
        second = build_casino_entries(222222)
        self.assertEqual(len(first), LAB_RACE_ENTRY_COUNT)
        self.assertEqual(len(second), LAB_RACE_ENTRY_COUNT)
        self.assertTrue(any(a["odds"] != b["odds"] or a["condition_key"] != b["condition_key"] for a, b in zip(first, second)))


class LabRaceEngineTests(unittest.TestCase):
    def test_standard_engine_fills_to_six_and_simulates(self):
        race = create_race(
            mode="standard",
            seed=333333,
            course_key="scrapyard_sprint",
            entries=[
                {
                    "entry_order": 1,
                    "display_name": "Starter",
                    "source_type": "robot_instance",
                    "user_id": 1,
                    "robot_instance_id": 10,
                    "icon_path": "defaults/robot_badge_default.png",
                    "hp": 18,
                    "atk": 11,
                    "def": 10,
                    "spd": 13,
                    "acc": 12,
                    "cri": 9,
                }
            ],
            simulate=True,
        )
        self.assertEqual(len(race["entries"]), LAB_RACE_ENTRY_COUNT)
        self.assertEqual(len({row["lane_index"] for row in race["entries"]}), LAB_RACE_ENTRY_COUNT)
        self.assertTrue(race["simulation"]["frames"])
        self.assertEqual(len(race["simulation"]["results"]), LAB_RACE_ENTRY_COUNT)

    def test_casino_engine_uses_shared_course_and_simulates(self):
        race = create_race(mode="casino", seed=444444, simulate=True)
        self.assertEqual(len(race["entries"]), LAB_RACE_ENTRY_COUNT)
        self.assertTrue(race["simulation"]["frames"])
        self.assertEqual(race["course"]["segments"][0]["kind"], "start")
        self.assertEqual(race["course"]["segments"][-1]["kind"], "goal")


if __name__ == "__main__":
    unittest.main()
