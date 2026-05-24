import json
import random
import time


BOARD_SIZE = 5
MAX_TURNS = 10
ALLY_START_POSITIONS = ((0, 1), (0, 2), (0, 3))
RENTAL_ALLY_SPECS = (
    ("rental_cerberus", "ケルベロス", "cerberus", "assault", 18, 5, 2, "mini_robots/cerberus/normal.png"),
    ("rental_phoenix", "フェニックス", "phoenix", "cautious", 14, 4, 1, "mini_robots/phoenix/normal.png"),
    ("rental_hydra", "ヒュドラ", "hydra", "guardian", 20, 3, 3, "mini_robots/hydra/normal.png"),
)


def build_initial_map():
    return {
        "width": BOARD_SIZE,
        "height": BOARD_SIZE,
        "tiles": [
            [{"x": x, "y": y, "terrain": "floor"} for x in range(BOARD_SIZE)]
            for y in range(BOARD_SIZE)
        ],
    }


def build_initial_units():
    return [
        {
            "unit_id": "ally_cerberus",
            "side": "ally",
            "name": "ケルベロス",
            "species_key": "cerberus",
            "x": 0,
            "y": 1,
            "hp": 18,
            "max_hp": 18,
            "atk": 5,
            "def": 2,
            "defeated": False,
            "ai_type": "assault",
            "image_path": "mini_robots/cerberus/normal.png",
            "direction": "right",
        },
        {
            "unit_id": "ally_phoenix",
            "side": "ally",
            "name": "フェニックス",
            "species_key": "phoenix",
            "x": 0,
            "y": 2,
            "hp": 14,
            "max_hp": 14,
            "atk": 4,
            "def": 1,
            "defeated": False,
            "ai_type": "cautious",
            "image_path": "mini_robots/phoenix/normal.png",
            "direction": "right",
        },
        {
            "unit_id": "ally_hydra",
            "side": "ally",
            "name": "ヒュドラ",
            "species_key": "hydra",
            "x": 0,
            "y": 3,
            "hp": 20,
            "max_hp": 20,
            "atk": 3,
            "def": 3,
            "defeated": False,
            "ai_type": "guardian",
            "image_path": "mini_robots/hydra/normal.png",
            "direction": "right",
        },
        {
            "unit_id": "enemy_dummy_a",
            "side": "enemy",
            "name": "ダミーA",
            "species_key": "dummy_a",
            "x": 4,
            "y": 1,
            "hp": 12,
            "max_hp": 12,
            "atk": 3,
            "def": 1,
            "defeated": False,
            "ai_type": "assault",
            "image_path": "",
            "direction": "left",
        },
        {
            "unit_id": "enemy_dummy_b",
            "side": "enemy",
            "name": "ダミーB",
            "species_key": "dummy_b",
            "x": 4,
            "y": 2,
            "hp": 12,
            "max_hp": 12,
            "atk": 3,
            "def": 1,
            "defeated": False,
            "ai_type": "assault",
            "image_path": "",
            "direction": "left",
        },
        {
            "unit_id": "enemy_dummy_c",
            "side": "enemy",
            "name": "ダミーC",
            "species_key": "dummy_c",
            "x": 4,
            "y": 3,
            "hp": 12,
            "max_hp": 12,
            "atk": 3,
            "def": 1,
            "defeated": False,
            "ai_type": "assault",
            "image_path": "",
            "direction": "left",
        },
    ]


def build_rental_ally_units():
    units = []
    for index, (unit_id, name, species_key, ai_type, hp, atk, defense, image_path) in enumerate(RENTAL_ALLY_SPECS):
        x, y = ALLY_START_POSITIONS[index]
        units.append(
            {
                "unit_id": unit_id,
                "side": "ally",
                "name": name,
                "species_key": species_key,
                "x": x,
                "y": y,
                "hp": hp,
                "max_hp": hp,
                "atk": atk,
                "def": defense,
                "defeated": False,
                "ai_type": ai_type,
                "image_path": image_path,
                "direction": "right",
                "source": "rental",
            }
        )
    return units


def build_units_with_allies(ally_units=None):
    rentals = build_rental_ally_units()
    allies = []
    used_species = set()
    for unit in ally_units or []:
        if len(allies) >= 3:
            break
        copied = dict(unit)
        copied["side"] = "ally"
        copied["defeated"] = bool(copied.get("defeated"))
        copied.setdefault("direction", "right")
        copied.setdefault("source", "owned")
        allies.append(copied)
        used_species.add(str(copied.get("species_key") or ""))
    for rental in rentals:
        if len(allies) >= 3:
            break
        if str(rental.get("species_key") or "") in used_species and len(rentals) - len(used_species) >= 3 - len(allies):
            continue
        allies.append(dict(rental))
        used_species.add(str(rental.get("species_key") or ""))
    while len(allies) < 3:
        rental = rentals[len(allies) % len(rentals)]
        copied = dict(rental)
        copied["unit_id"] = f"{copied['unit_id']}_{len(allies) + 1}"
        allies.append(copied)
    for index, unit in enumerate(allies[:3]):
        x, y = ALLY_START_POSITIONS[index]
        unit["x"] = x
        unit["y"] = y

    enemies = [dict(unit) for unit in build_initial_units() if unit.get("side") == "enemy"]
    return allies[:3] + enemies


def manhattan(a, b):
    return abs(int(a["x"]) - int(b["x"])) + abs(int(a["y"]) - int(b["y"]))


def _tile_is_wall(map_payload, x, y):
    for row in map_payload.get("tiles") or []:
        for tile in row:
            if int(tile.get("x") or 0) == int(x) and int(tile.get("y") or 0) == int(y):
                return str(tile.get("terrain") or "floor") == "wall"
    return False


def _direction_from_delta(dx, dy, fallback):
    if dx > 0:
        return "right"
    if dx < 0:
        return "left"
    if dy > 0:
        return "down"
    if dy < 0:
        return "up"
    return fallback or "right"


def living_enemies(unit, units):
    return [u for u in units if u.get("side") != unit.get("side") and not u.get("defeated")]


def living_allies(unit, units):
    return [
        u
        for u in units
        if u.get("side") == unit.get("side")
        and str(u.get("unit_id") or "") != str(unit.get("unit_id") or "")
        and not u.get("defeated")
    ]


def find_nearest_enemy(unit, units):
    enemies = living_enemies(unit, units)
    if not enemies:
        return None
    return min(enemies, key=lambda enemy: (manhattan(unit, enemy), str(enemy.get("unit_id") or "")))


def f