from services.lab_race_course import LAB_RACE_COURSES, LAB_RACE_GOAL as SHARED_LAB_RACE_GOAL
from services.lab_race_engine import build_npc_entry, build_course, fill_standard_entries, simulate_mode_race


LAB_RACE_ENTRY_TARGET = 6
LAB_RACE_FRAME_MS = 320
LAB_RACE_TOTAL_FRAMES = 82
LAB_RACE_GOAL = SHARED_LAB_RACE_GOAL


def fill_npc_entries(entries, seed, target=LAB_RACE_ENTRY_TARGET):
    return fill_standard_entries(entries, seed, target=int(target))


def simulate_race(entries, seed, course_key):
    course = build_course(seed, mode="standard", course_key=course_key if isinstance(course_key, str) else None)
    if isinstance(course_key, dict):
        course = dict(course_key)
    return simulate_mode_race(entries, seed, course, mode="standard")
