import json
import random

from balance_config import ENEMY_SEED_STATS
from services.lab_casino_service import build_casino_entries
from services.lab_race_course import (
    LAB_RACE_COURSE_ALIASES,
    LAB_RACE_COURSES,
    LAB_RACE_ENTRY_COUNT,
    build_course_layout,
    course_meta,
)
from services.lab_race_simulator import simulate_race as simulate_shared_race


LAB_NPC_ARCHETYPES = (
    {"name": "ボルト", "role_type": "speed", "stats": {"hp": 18, "atk": 9, "def": 8, "spd": 16, "acc": 11, "cri": 9, "luck": 9}},
    {"name": "ガード", "role_type": "tank", "stats": {"hp": 25, "atk": 7, "def": 15, "spd": 8, "acc": 10, "cri": 6, "luck": 8}},
    {"name": "スナップ", "role_type": "balanced", "stats": {"hp": 17, "atk": 8, "def": 7, "spd": 11, "acc": 16, "cri": 8, "luck": 10}},
    {"name": "クラッシュ", "role_type": "chaos", "stats": {"hp": 19, "atk": 15, "def": 8, "spd": 10, "acc": 8, "cri": 7, "luck": 8}},
    {"name": "スパーク", "role_type": "miracle", "stats": {"hp": 16, "atk": 10, "def": 7, "spd": 14, "acc": 10, "cri": 15, "luck": 13}},
    {"name": "アンカー", "role_type": "heavy", "stats": {"hp": 24, "atk": 8, "def": 13, "spd": 9, "acc": 12, "cri": 5, "luck": 7}},
)

LAB_NPC_VISUALS = tuple(
    {
        "enemy_key": str(enemy_key),
        "display_name": str(item.get("name_ja") or enemy_key),
        "icon_path": str(item.get("image_path") or ""),
    }
    for enemy_key, item in sorted(ENEMY_SEED_STATS.items())
    if int(item.get("is_boss", 0) or 0) == 0 and str(item.get("image_path") or "").strip()
)


def _course_key(course_key, *, mode):
    if mode == "casino" and not course_key:
        return "casino_scrapyard_cup"
    key = str(course_key or "").strip().lower()
    key = LAB_RACE_COURSE_ALIASES.get(key, key)
    if key in LAB_RACE_COURSES:
        return key
    return "scrapyard_sprint"


def build_course(seed, *, mode="standard", course_key=None):
    return build_course_layout(int(seed), course_key=_course_key(course_key, mode=mode), mode=mode)


def serialize_course(course):
    return json.dumps(course or {}, ensure_ascii=False)


def load_course(payload_json, *, seed=None, mode="standard", course_key=None):
    if isinstance(payload_json, dict):
        return payload_json
    raw = str(payload_json or "").strip()
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return build_course(int(seed or 0), mode=mode, course_key=course_key)


def build_npc_entry(seed, slot_index):
    rng = random.Random(f"lab-standard-npc:{int(seed)}:{int(slot_index)}")
    archetype = dict(rng.choice(LAB_NPC_ARCHETYPES))
    visual = dict(rng.choice(LAB_NPC_VISUALS)) if LAB_NPC_VISUALS else {
        "enemy_key": "lab_enemy",
        "display_name": archetype["name"],
        "icon_path": None,
    }
    stats = {}
    for key, value in archetype["stats"].items():
        stats[key] = max(1, int(value + rng.randint(-2, 2)))
    serial = rng.randint(11, 98)
    return {
        "source_type": "npc",
        "display_name": f"{visual['display_name']}-{serial}",
        "user_id": None,
        "robot_instance_id": None,
        "submission_id": None,
        "icon_path": visual.get("icon_path"),
        "role_type": archetype["role_type"],
        **stats,
    }


def fill_standard_entries(entries, seed, *, target=LAB_RACE_ENTRY_COUNT):
    filled = []
    for idx, item in enumerate(entries or (), start=1):
        row = dict(item)
        row["entry_order"] = int(row.get("entry_order") or idx)
        row["lane_index"] = int(row.get("lane_index") if row.get("lane_index") is not None else (idx - 1))
        if "luck" not in row:
            row["luck"] = int(round((int(row.get("acc") or 10) * 0.6) + (int(row.get("cri") or 8) * 0.4)))
        row["role_type"] = str(row.get("role_type") or "balanced")
        filled.append(row)
    next_order = len(filled) + 1
    while len(filled) < int(target):
        npc = build_npc_entry(seed, next_order)
        npc["entry_order"] = next_order
        npc["lane_index"] = next_order - 1
        filled.append(npc)
        next_order += 1
    return filled[: int(target)]


def create_race(mode="standard", *, seed=None, course_key=None, entries=None, simulate=False):
    race_seed = int(seed or random.randint(100_000, 999_999))
    course = build_course(race_seed, mode=mode, course_key=course_key)
    if mode == "casino":
        roster = build_casino_entries(race_seed)
    else:
        roster = fill_standard_entries(entries or (), race_seed, target=LAB_RACE_ENTRY_COUNT)
    payload = {
        "seed": race_seed,
        "mode": str(mode),
        "course": course,
        "entries": roster,
    }
    if simulate:
        payload["simulation"] = simulate_shared_race(roster, race_seed, course, mode=mode)
    return payload


def simulate_mode_race(entries, seed, course, *, mode="standard"):
    return simulate_shared_race(entries, int(seed), course, mode=mode)


def visible_course_defs():
    return tuple(dict(item) for item in LAB_RACE_COURSES.values() if not int(item.get("hidden") or 0))


def default_course_key(mode="standard"):
    if mode == "casino":
        return "casino_scrapyard_cup"
    return "scrapyard_sprint"
