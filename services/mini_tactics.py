import json
import random
import time


BOARD_SIZE = 5
MAX_TURNS = 10
ALLY_START_POSITIONS = ((0, 1), (0, 2), (0, 3))
MINI_TACTICS_WALLS = ((2, 1), (2, 3))
WEAPON_SPECS = {
    "melee": {"range": 1, "label": "格闘"},
    "laser": {"range": 2, "label": "レーザー"},
    "missile": {"range": 2, "label": "ミサイル"},
}
MOVE_TYPE_LABELS = {
    "walk": "歩行",
    "flight": "飛行",
    "multi_leg": "多脚",
    "core": "コア",
}
SPECIES_MOVE_TYPES = {
    "cerberus": "walk",
    "phoenix": "flight",
    "hydra": "multi_leg",
    "sphinx": "walk",
    "dummy_a": "walk",
    "dummy_b": "walk",
    "dummy_c": "walk",
}
WEAPON_ROLES = {
    "melee": "assault",
    "laser": "shooting",
    "missile": "guard",
}
ROLE_LABELS = {
    "assault": "突撃",
    "shooting": "射撃",
    "guard": "守備",
    "core": "コア",
}
ROLE_ADVANTAGE = {
    "assault": "shooting",
    "shooting": "guard",
    "guard": "assault",
}
BOARD_V1_WIDTH = 3
BOARD_V1_HEIGHT = 4
BOARD_V1_SIZE = BOARD_V1_WIDTH
MANUAL_V1_ROLE_ADVANTAGE = {
    "assault": "sniper",
    "sniper": "guardian",
    "guardian": "assault",
}
MANUAL_V1_WEAPON_LABELS = {
    "melee": "格闘",
    "laser": "レーザー",
    "missile": "ミサイル",
}
MANUAL_V1_MOVE_LABELS = {
    "leader": "リーダー",
    "flyer": "飛行",
    "guardian": "守護",
    "sphinx": "スフィンクス",
}
MANUAL_V1_ROLE_LABELS = {
    "leader": "リーダー",
    "flyer": "飛行",
    "guardian": "守護",
    "sphinx": "知略型",
}
MANUAL_V1_TRAIT_LABELS = {
    "guard_dog": "番犬",
    "retreat_shot": "退き撃ち",
    "fortress": "要塞",
    "sphinx": "謎かけ",
}
MANUAL_V1_ALLY_SPECS = (
    ("ally_cerberus", "ケルベロス", "cerberus", True, 1, 3, "leader", "leader", "capture", "guard_dog", "up"),
    ("ally_phoenix", "フェニックス", "phoenix", False, 0, 3, "flyer", "flyer", "capture", "retreat_shot", "up"),
    ("ally_hydra", "ヒュドラ", "hydra", False, 2, 3, "guardian", "guardian", "capture", "fortress", "up"),
    ("ally_sphinx", "スフィンクス", "sphinx", False, 1, 2, "sphinx", "sphinx", "capture", "sphinx", "up"),
)
MANUAL_V1_ENEMY_SPECS = (
    ("enemy_cerberus", "敵ケルベロス", "cerberus", True, 1, 0, "leader", "leader", "capture", "guard_dog", "down"),
    ("enemy_phoenix", "敵フェニックス", "phoenix", False, 0, 0, "flyer", "flyer", "capture", "retreat_shot", "down"),
    ("enemy_hydra", "敵ヒュドラ", "hydra", False, 2, 0, "guardian", "guardian", "capture", "fortress", "down"),
    ("enemy_sphinx", "敵スフィンクス", "sphinx", False, 1, 1, "sphinx", "sphinx", "capture", "sphinx", "down"),
)
SPECIES_WEAPONS = {
    "cerberus": "melee",
    "phoenix": "laser",
    "hydra": "missile",
    "sphinx": "laser",
    "dummy_a": "melee",
    "dummy_b": "melee",
    "dummy_c": "melee",
}
SPECIES_SPD = {
    "cerberus": 4,
    "phoenix": 6,
    "hydra": 3,
    "sphinx": 5,
    "dummy_a": 4,
    "dummy_b": 4,
    "dummy_c": 4,
}
RENTAL_ALLY_SPECS = (
    ("rental_cerberus", "ケルベロス", "cerberus", "assault", "melee", 18, 5, 2, 4, "mini_robots/cerberus/normal.png"),
    ("rental_phoenix", "フェニックス", "phoenix", "cautious", "laser", 14, 4, 1, 6, "mini_robots/phoenix/normal.png"),
    ("rental_hydra", "ヒュドラ", "hydra", "guardian", "missile", 20, 3, 3, 3, "mini_robots/hydra/normal.png"),
)


def build_initial_map():
    return {
        "width": BOARD_SIZE,
        "height": BOARD_SIZE,
        "tiles": [
            [
                {
                    "x": x,
                    "y": y,
                    "terrain": "wall" if (x, y) in MINI_TACTICS_WALLS else "floor",
                }
                for x in range(BOARD_SIZE)
            ]
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
            "spd": 4,
            "defeated": False,
            "ai_type": "assault",
            "weapon_type": "melee",
            "weapon_label": "格闘",
            "attack_range": 1,
            "range": 1,
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
            "spd": 6,
            "defeated": False,
            "ai_type": "cautious",
            "weapon_type": "laser",
            "weapon_label": "レーザー",
            "attack_range": 2,
            "range": 2,
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
            "spd": 3,
            "defeated": False,
            "ai_type": "guardian",
            "weapon_type": "missile",
            "weapon_label": "ミサイル",
            "attack_range": 2,
            "range": 2,
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
            "spd": 4,
            "defeated": False,
            "ai_type": "assault",
            "weapon_type": "melee",
            "weapon_label": "格闘",
            "attack_range": 1,
            "range": 1,
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
            "spd": 4,
            "defeated": False,
            "ai_type": "assault",
            "weapon_type": "melee",
            "weapon_label": "格闘",
            "attack_range": 1,
            "range": 1,
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
            "spd": 4,
            "defeated": False,
            "ai_type": "assault",
            "weapon_type": "melee",
            "weapon_label": "格闘",
            "attack_range": 1,
            "range": 1,
            "image_path": "",
            "direction": "left",
        },
    ]


def build_rental_ally_units():
    units = []
    for index, (unit_id, name, species_key, ai_type, weapon_type, hp, atk, defense, spd, image_path) in enumerate(RENTAL_ALLY_SPECS):
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
                "spd": spd,
                "defeated": False,
                "ai_type": ai_type,
                "weapon_type": weapon_type,
                "weapon_label": weapon_label(weapon_type),
                "attack_range": resolve_weapon_range(weapon_type),
                "range": resolve_weapon_range(weapon_type),
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
        unit.setdefault("x", x)
        unit.setdefault("y", y)

    enemies = [dict(unit) for unit in build_initial_units() if unit.get("side") == "enemy"]
    return allies[:3] + enemies


def build_admin_tactics_team(ally_units=None):
    return build_units_with_allies(ally_units)


def manhattan(a, b):
    return abs(int(a["x"]) - int(b["x"])) + abs(int(a["y"]) - int(b["y"]))


def resolve_weapon_range(weapon_type):
    return int(WEAPON_SPECS.get(str(weapon_type or "melee"), WEAPON_SPECS["melee"])["range"])


def weapon_label(weapon_type):
    return str(WEAPON_SPECS.get(str(weapon_type or "melee"), WEAPON_SPECS["melee"])["label"])


def resolve_weapon_profile(species_key=None, ai_type=None, existing_unit=None):
    unit = existing_unit or {}
    weapon_type = str(unit.get("weapon_type") or "").strip()
    if not weapon_type:
        weapon_type = SPECIES_WEAPONS.get(str(species_key or unit.get("species_key") or ""), "melee")
    if weapon_type not in WEAPON_SPECS:
        weapon_type = "melee"
    return {
        "weapon_type": weapon_type,
        "weapon_label": weapon_label(weapon_type),
        "attack_range": resolve_weapon_range(weapon_type),
        "range": resolve_weapon_range(weapon_type),
    }


def normalize_unit(unit):
    normalized = dict(unit)
    profile = resolve_weapon_profile(
        normalized.get("species_key"),
        normalized.get("ai_type"),
        normalized,
    )
    normalized["max_hp"] = int(normalized.get("max_hp") or normalized.get("hp") or 10)
    normalized["hp"] = int(normalized.get("hp") or normalized["max_hp"])
    normalized["atk"] = int(normalized.get("atk") or 1)
    normalized["def"] = int(normalized.get("def") or 0)
    normalized["spd"] = int(normalized.get("spd") or SPECIES_SPD.get(str(normalized.get("species_key") or ""), 4))
    normalized["ai_type"] = str(normalized.get("ai_type") or "assault")
    normalized["weapon_type"] = profile["weapon_type"]
    normalized["weapon_label"] = profile["weapon_label"]
    normalized["attack_range"] = int(normalized.get("attack_range") or normalized.get("range") or profile["attack_range"])
    normalized["range"] = int(normalized["attack_range"])
    normalized["defeated"] = bool(normalized.get("defeated")) or int(normalized["hp"]) <= 0
    return normalized


def is_wall(map_payload, x, y):
    for row in map_payload.get("tiles") or []:
        for tile in row:
            if int(tile.get("x") or 0) == int(x) and int(tile.get("y") or 0) == int(y):
                return str(tile.get("terrain") or "floor") == "wall"
    return False


def in_bounds(map_payload, x, y):
    return 0 <= int(x) < int(map_payload.get("width") or BOARD_SIZE) and 0 <= int(y) < int(map_payload.get("height") or BOARD_SIZE)


def _tile_is_wall(map_payload, x, y):
    return is_wall(map_payload, x, y)


def is_occupied(units, x, y, *, except_unit_id=None):
    for unit in units:
        if except_unit_id is not None and str(unit.get("unit_id") or "") == str(except_unit_id):
            continue
        if int(unit.get("x") or 0) == int(x) and int(unit.get("y") or 0) == int(y):
            return True
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


def find_nearest_ally(unit, units):
    allies = living_allies(unit, units)
    if not allies:
        return None
    return min(allies, key=lambda ally: (manhattan(unit, ally), str(ally.get("unit_id") or "")))


def get_valid_moves(unit, units, map_payload):
    width = int(map_payload.get("width") or BOARD_SIZE)
    height = int(map_payload.get("height") or BOARD_SIZE)
    moves = []
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx = int(unit["x"]) + dx
        ny = int(unit["y"]) + dy
        if nx < 0 or ny < 0 or nx >= width or ny >= height:
            continue
        if is_occupied(units, nx, ny, except_unit_id=unit.get("unit_id")) or is_wall(map_payload, nx, ny):
            continue
        moves.append((nx, ny))
    return moves


def _choose_by_distance(unit, moves, target, rng, *, prefer="near"):
    if not target or not moves:
        return None
    current_distance = manhattan(unit, target)
    scored = []
    for nx, ny in moves:
        next_distance = abs(int(nx) - int(target["x"])) + abs(int(ny) - int(target["y"]))
        if prefer == "near" and next_distance < current_distance:
            scored.append((next_distance, nx, ny))
        elif prefer == "far" and next_distance > current_distance:
            scored.append((next_distance, nx, ny))
    if not scored:
        return None
    best_distance = min(item[0] for item in scored) if prefer == "near" else max(item[0] for item in scored)
    best = [(nx, ny) for dist, nx, ny in scored if dist == best_distance]
    return rng.choice(best)


def _action_move(unit, nx, ny, message):
    return {"type": "move", "x": int(nx), "y": int(ny), "message": message}


def _action_attack(unit, target, message=None):
    weapon_type = str(unit.get("weapon_type") or "melee")
    return {
        "type": "attack",
        "target_id": str(target.get("unit_id") or ""),
        "message": message or f"{unit['name']}が{weapon_label(weapon_type)}で{target['name']}を攻撃",
    }


def _action_wait(unit, message=None):
    return {"type": "wait", "message": message or f"{unit['name']}が待機"}


def build_move_event(unit, from_x, from_y, to_x, to_y, text):
    return {
        "type": "move",
        "actor_unit_id": str(unit.get("unit_id") or ""),
        "from": {"x": int(from_x), "y": int(from_y)},
        "to": {"x": int(to_x), "y": int(to_y)},
        "text": str(text),
    }


def build_attack_event(unit, target, weapon_type, damage, text):
    return {
        "type": "attack",
        "actor_unit_id": str(unit.get("unit_id") or ""),
        "target_unit_id": str(target.get("unit_id") or ""),
        "weapon_type": str(weapon_type or "melee"),
        "weapon_label": weapon_label(weapon_type),
        "damage": int(damage),
        "text": str(text),
    }


def build_defeated_event(unit, text):
    return {
        "type": "defeated",
        "actor_unit_id": str(unit.get("unit_id") or ""),
        "text": str(text),
    }


def build_wait_event(unit, text):
    return {
        "type": "wait",
        "actor_unit_id": str(unit.get("unit_id") or ""),
        "text": str(text),
    }


def build_result_event(result, text):
    return {
        "type": "result",
        "result": str(result),
        "text": str(text),
    }


def get_adjacent_enemy(unit, units):
    enemies = [
        u
        for u in units
        if u.get("side") != unit.get("side") and not u.get("defeated") and manhattan(unit, u) == 1
    ]
    if not enemies:
        return None
    return min(enemies, key=lambda enemy: (int(enemy.get("hp") or 0), str(enemy.get("unit_id") or "")))


def find_targets_in_range(unit, units, map_payload=None):
    targets = [
        enemy
        for enemy in living_enemies(unit, units)
        if can_attack(unit, enemy, map_payload)
    ]
    return sorted(targets, key=lambda enemy: (manhattan(unit, enemy), int(enemy.get("hp") or 0), str(enemy.get("unit_id") or "")))


def has_line_of_sight(attacker, target, map_payload, weapon_type=None):
    weapon = str(weapon_type or attacker.get("weapon_type") or "melee")
    if weapon == "missile":
        return True
    if weapon == "melee":
        return manhattan(attacker, target) == 1
    if weapon != "laser":
        return True
    ax = int(attacker["x"])
    ay = int(attacker["y"])
    tx = int(target["x"])
    ty = int(target["y"])
    if ax != tx and ay != ty:
        return False
    step_x = 0 if ax == tx else (1 if tx > ax else -1)
    step_y = 0 if ay == ty else (1 if ty > ay else -1)
    x = ax + step_x
    y = ay + step_y
    while (x, y) != (tx, ty):
        if is_wall(map_payload, x, y):
            return False
        x += step_x
        y += step_y
    return True


def can_attack(attacker, target, map_payload=None):
    if not target or target.get("defeated"):
        return False
    weapon_type = str(attacker.get("weapon_type") or "melee")
    attack_range = int(attacker.get("attack_range") or attacker.get("range") or resolve_weapon_range(weapon_type))
    distance = manhattan(attacker, target)
    if distance > attack_range:
        return False
    if weapon_type == "laser" and int(attacker["x"]) != int(target["x"]) and int(attacker["y"]) != int(target["y"]):
        return False
    if weapon_type == "melee" and distance != 1:
        return False
    return has_line_of_sight(attacker, target, map_payload or build_initial_map(), weapon_type)


def attackable_cells(unit, map_payload):
    weapon_type = str(unit.get("weapon_type") or "melee")
    attack_range = int(unit.get("attack_range") or unit.get("range") or resolve_weapon_range(weapon_type))
    origin_x = int(unit["x"])
    origin_y = int(unit["y"])
    cells = []
    if weapon_type == "laser":
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for distance in range(1, attack_range + 1):
                x = origin_x + dx * distance
                y = origin_y + dy * distance
                if not in_bounds(map_payload, x, y):
                    break
                if is_wall(map_payload, x, y):
                    break
                cells.append({"x": x, "y": y})
        return cells
    for y in range(origin_y - attack_range, origin_y + attack_range + 1):
        for x in range(origin_x - attack_range, origin_x + attack_range + 1):
            if x == origin_x and y == origin_y:
                continue
            if not in_bounds(map_payload, x, y):
                continue
            if manhattan(unit, {"x": x, "y": y}) > attack_range:
                continue
            if weapon_type == "melee" and is_wall(map_payload, x, y):
                continue
            cells.append({"x": x, "y": y})
    return cells


def targetable_unit_ids(unit, units, map_payload):
    return [str(target.get("unit_id") or "") for target in find_targets_in_range(unit, units, map_payload)]


def movement_type_for_species(species_key):
    return SPECIES_MOVE_TYPES.get(str(species_key or ""), "walk")


def role_for_weapon(weapon_type):
    return WEAPON_ROLES.get(str(weapon_type or "melee"), "assault")


def _manual_unit(unit):
    normalized = normalize_unit(unit)
    weapon_type = str(normalized.get("weapon_type") or "melee")
    move_type = str(normalized.get("move_type") or movement_type_for_species(normalized.get("species_key")))
    normalized["move_type"] = move_type
    normalized["move_type_label"] = MOVE_TYPE_LABELS.get(move_type, move_type)
    normalized["role_type"] = str(normalized.get("role_type") or role_for_weapon(weapon_type))
    normalized["role_label"] = ROLE_LABELS.get(normalized["role_type"], normalized["role_type"])
    normalized["unit_type"] = str(normalized.get("unit_type") or "robot")
    return normalized


def _manual_core(side):
    x = 0 if side == "ally" else 4
    return {
        "unit_id": f"{side}_core",
        "unit_type": "core",
        "side": side,
        "name": "味方コア" if side == "ally" else "敵コア",
        "species_key": "core",
        "x": x,
        "y": 2,
        "hp": 10,
        "max_hp": 10,
        "atk": 0,
        "def": 0,
        "spd": 0,
        "defeated": False,
        "weapon_type": "none",
        "weapon_label": "-",
        "attack_range": 0,
        "range": 0,
        "move_type": "core",
        "move_type_label": "コア",
        "role_type": "core",
        "role_label": "コア",
        "direction": "right" if side == "ally" else "left",
    }


def _manual_place_units(units, reserved):
    fallback = {
        "ally": [(0, 1), (1, 2), (0, 3), (1, 0), (1, 4)],
        "enemy": [(4, 1), (3, 2), (4, 3), (3, 0), (3, 4)],
    }
    placed = []
    occupied = set(reserved)
    side_counts = {"ally": 0, "enemy": 0}
    map_payload = build_initial_map()
    for raw in units:
        unit = _manual_unit(raw)
        side = str(unit.get("side") or "ally")
        candidates = [(int(unit.get("x") or 0), int(unit.get("y") or 0))] + fallback.get(side, [])
        chosen = None
        for x, y in candidates:
            if not in_bounds(map_payload, x, y) or is_wall(map_payload, x, y) or (x, y) in occupied:
                continue
            chosen = (x, y)
            break
        if chosen is None:
            chosen = fallback.get(side, [(0, 0)])[side_counts.get(side, 0) % len(fallback.get(side, [(0, 0)]))]
        unit["x"], unit["y"] = chosen
        occupied.add(chosen)
        side_counts[side] = side_counts.get(side, 0) + 1
        placed.append(unit)
    return placed


def build_manual_board_state(seed=None, ally_units=None):
    map_payload = build_initial_map()
    units = build_units_with_allies(ally_units) if ally_units is not None else build_initial_units()
    cores = [_manual_core("ally"), _manual_core("enemy")]
    reserved = {(int(core["x"]), int(core["y"])) for core in cores}
    robots = _manual_place_units(units, reserved)
    return {
        "mode": "manual_board",
        "seed": int(seed or 0),
        "turn_number": 1,
        "current_turn_side": "ally",
        "units": cores + robots,
        "result": None,
        "selected_unit_id": None,
    }


def living_manual_units(state, side=None, include_cores=True):
    units = []
    for unit in state.get("units") or []:
        if unit.get("defeated"):
            continue
        if side is not None and unit.get("side") != side:
            continue
        if not include_cores and unit.get("unit_type") == "core":
            continue
        units.append(unit)
    return units


def find_manual_unit(state, unit_id):
    for unit in state.get("units") or []:
        if str(unit.get("unit_id") or "") == str(unit_id):
            return unit
    return None


def _manual_occupied(state, x, y, except_unit_id=None):
    for unit in living_manual_units(state):
        if except_unit_id is not None and str(unit.get("unit_id") or "") == str(except_unit_id):
            continue
        if int(unit.get("x") or 0) == int(x) and int(unit.get("y") or 0) == int(y):
            return True
    return False


def manual_move_cells(unit, state, map_payload=None):
    if not unit or unit.get("defeated") or unit.get("unit_type") == "core":
        return []
    map_payload = map_payload or build_initial_map()
    x = int(unit.get("x") or 0)
    y = int(unit.get("y") or 0)
    side = str(unit.get("side") or "ally")
    move_type = str(unit.get("move_type") or movement_type_for_species(unit.get("species_key")))
    if move_type == "flight":
        forward = 1 if side == "ally" else -1
        deltas = ((forward, 0), (1, 1), (1, -1), (-1, 1), (-1, -1))
    else:
        deltas = ((1, 0), (-1, 0), (0, 1), (0, -1))
    cells = []
    for dx, dy in deltas:
        nx = x + dx
        ny = y + dy
        if not in_bounds(map_payload, nx, ny):
            continue
        if move_type != "flight" and is_wall(map_payload, nx, ny):
            continue
        if _manual_occupied(state, nx, ny, except_unit_id=unit.get("unit_id")):
            continue
        cells.append({"x": nx, "y": ny})
    return cells


def manual_attackable_cells(unit, map_payload=None):
    if not unit or unit.get("defeated") or unit.get("unit_type") == "core":
        return []
    return attackable_cells(unit, map_payload or build_initial_map())


def manual_targetable_unit_ids(unit, state, map_payload=None):
    if not unit:
        return []
    map_payload = map_payload or build_initial_map()
    return [
        str(target.get("unit_id") or "")
        for target in living_manual_units(state)
        if target.get("side") != unit.get("side") and can_attack(unit, target, map_payload)
    ]


def manual_action_options(state, unit_id, map_payload=None):
    unit = find_manual_unit(state, unit_id)
    return {
        "move_cells": manual_move_cells(unit, state, map_payload),
        "attackable_cells": manual_attackable_cells(unit, map_payload),
        "targetable_unit_ids": manual_targetable_unit_ids(unit, state, map_payload),
    }


def _manual_defense(unit, map_payload=None):
    defense = int(unit.get("def") or 0)
    if str(unit.get("move_type") or "") == "multi_leg":
        map_payload = map_payload or build_initial_map()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if is_wall(map_payload, int(unit.get("x") or 0) + dx, int(unit.get("y") or 0) + dy):
                return defense + 1
    return defense


def manual_damage(attacker, target, map_payload=None):
    base = max(1, int(attacker.get("atk") or 0) - _manual_defense(target, map_payload))
    attacker_role = str(attacker.get("role_type") or role_for_weapon(attacker.get("weapon_type")))
    target_role = str(target.get("role_type") or role_for_weapon(target.get("weapon_type")))
    if ROLE_ADVANTAGE.get(attacker_role) == target_role:
        base += 1
    elif ROLE_ADVANTAGE.get(target_role) == attacker_role:
        base -= 1
    return max(1, base)


def _manual_result(state):
    ally_core = find_manual_unit(state, "ally_core")
    enemy_core = find_manual_unit(state, "enemy_core")
    if ally_core and ally_core.get("defeated"):
        return "enemy_win"
    if enemy_core and enemy_core.get("defeated"):
        return "ally_win"
    ally_living = living_manual_units(state, "ally", include_cores=False)
    enemy_living = living_manual_units(state, "enemy", include_cores=False)
    if not ally_living:
        return "enemy_win"
    if not enemy_living:
        return "ally_win"
    return None


def _manual_log(logs, text, event_type="log", **payload):
    item = {"type": event_type, "text": str(text), **payload}
    logs.append(item)
    return item


def _apply_manual_attack(state, attacker, target, logs, map_payload=None):
    if not can_attack(attacker, target, map_payload or build_initial_map()):
        return False, "攻撃できない対象です。"
    damage = manual_damage(attacker, target, map_payload)
    target["hp"] = max(0, int(target.get("hp") or 0) - damage)
    _manual_log(
        logs,
        f"{attacker['name']}が{weapon_label(attacker.get('weapon_type'))}で{target['name']}を攻撃、{damage}ダメージ",
        "attack",
        actor_unit_id=attacker.get("unit_id"),
        target_unit_id=target.get("unit_id"),
        damage=damage,
        weapon_type=attacker.get("weapon_type"),
    )
    if int(target["hp"]) <= 0:
        target["defeated"] = True
        _manual_log(logs, f"{target['name']}を破壊", "defeated", actor_unit_id=target.get("unit_id"))
    return True, None


def _apply_manual_move(state, unit, x, y, logs, map_payload=None):
    allowed = {(cell["x"], cell["y"]) for cell in manual_move_cells(unit, state, map_payload)}
    if (int(x), int(y)) not in allowed:
        return False, "移動できないマスです。"
    from_x = int(unit["x"])
    from_y = int(unit["y"])
    unit["x"] = int(x)
    unit["y"] = int(y)
    unit["direction"] = _direction_from_delta(int(x) - from_x, int(y) - from_y, unit.get("direction"))
    _manual_log(
        logs,
        f"{unit['name']}が移動",
        "move",
        actor_unit_id=unit.get("unit_id"),
        **{"from": {"x": from_x, "y": from_y}, "to": {"x": int(x), "y": int(y)}},
    )
    return True, None


def _enemy_cpu_action(state, map_payload=None):
    logs = []
    map_payload = map_payload or build_initial_map()
    enemies = sorted(living_manual_units(state, "enemy", include_cores=False), key=lambda u: str(u.get("unit_id") or ""))
    for enemy in enemies:
        targets = [find_manual_unit(state, uid) for uid in manual_targetable_unit_ids(enemy, state, map_payload)]
        targets = [target for target in targets if target]
        if targets:
            target = min(targets, key=lambda u: (u.get("unit_type") != "core", int(u.get("hp") or 0), manhattan(enemy, u)))
            _apply_manual_attack(state, enemy, target, logs, map_payload)
            return logs
        living_targets = [u for u in living_manual_units(state, "ally") if not u.get("defeated")]
        if not living_targets:
            return logs
        target = min(living_targets, key=lambda u: (u.get("unit_type") != "core", manhattan(enemy, u), str(u.get("unit_id") or "")))
        moves = manual_move_cells(enemy, state, map_payload)
        if moves:
            best = min(moves, key=lambda cell: (abs(cell["x"] - int(target["x"])) + abs(cell["y"] - int(target["y"])), cell["x"], cell["y"]))
            _apply_manual_move(state, enemy, best["x"], best["y"], logs, map_payload)
            targets = [find_manual_unit(state, uid) for uid in manual_targetable_unit_ids(enemy, state, map_payload)]
            targets = [candidate for candidate in targets if candidate]
            if targets:
                _apply_manual_attack(state, enemy, targets[0], logs, map_payload)
            return logs
    return logs


def apply_manual_turn_action(state, actor_unit_id, move_to=None, target_unit_id=None, attack_first=False, map_payload=None):
    map_payload = map_payload or build_initial_map()
    next_state = dict(state)
    next_state["units"] = [dict(unit) for unit in state.get("units") or []]
    logs = []
    if next_state.get("result"):
        return next_state, logs, "すでに決着しています。"
    if str(next_state.get("current_turn_side") or "ally") != "ally":
        return next_state, logs, "現在は味方ターンではありません。"
    actor = find_manual_unit(next_state, actor_unit_id)
    if not actor or actor.get("side") != "ally" or actor.get("defeated") or actor.get("unit_type") == "core":
        return next_state, logs, "行動できないユニットです。"
    if attack_first and move_to:
        return next_state, logs, "攻撃後の移動はできません。"
    if move_to:
        ok, error = _apply_manual_move(next_state, actor, int(move_to["x"]), int(move_to["y"]), logs, map_payload)
        if not ok:
            return next_state, logs, error
    if target_unit_id:
        target = find_manual_unit(next_state, target_unit_id)
        if not target or target.get("side") == actor.get("side") or target.get("defeated"):
            return next_state, logs, "攻撃できない対象です。"
        ok, error = _apply_manual_attack(next_state, actor, target, logs, map_payload)
        if not ok:
            return next_state, logs, error
    if not move_to and not target_unit_id:
        return next_state, logs, "行動内容がありません。"
    result = _manual_result(next_state)
    if not result:
        next_state["current_turn_side"] = "enemy"
        logs.extend(_enemy_cpu_action(next_state, map_payload))
        result = _manual_result(next_state)
    next_state["result"] = result
    if result:
        next_state["current_turn_side"] = "finished"
        _manual_log(logs, "味方側の勝利" if result == "ally_win" else "敵側の勝利", "result", result=result)
    else:
        next_state["current_turn_side"] = "ally"
        next_state["turn_number"] = int(next_state.get("turn_number") or 1) + 1
    return next_state, logs, None


def build_manual_board_v1_map():
    return {
        "width": BOARD_V1_WIDTH,
        "height": BOARD_V1_HEIGHT,
        "board_width": BOARD_V1_WIDTH,
        "board_height": BOARD_V1_HEIGHT,
        "board_size": BOARD_V1_WIDTH,
        "tiles": [
            [
                {"x": x, "y": y, "terrain": "floor"}
                for x in range(BOARD_V1_WIDTH)
            ]
            for y in range(BOARD_V1_HEIGHT)
        ],
    }


def _manual_v1_attack_range(weapon_type):
    return 1 if str(weapon_type or "melee") == "melee" else 2


def _manual_v1_unit(spec, side, ally_unit=None):
    (
        unit_id,
        name,
        species_key,
        is_leader,
        x,
        y,
        move_type,
        role_type,
        weapon_type,
        trait_key,
        facing,
    ) = spec
    source = None
    image_path = f"mini_robots/{species_key}/normal.png"
    if ally_unit:
        name = str(ally_unit.get("name") or name)
        image_path = str(ally_unit.get("image_path") or image_path)
        source = ally_unit.get("source")
    return {
        "unit_id": unit_id,
        "side": side,
        "is_leader": bool(is_leader),
        "name": name,
        "species_key": species_key,
        "x": int(x),
        "y": int(y),
        "piece_type": species_key,
        "move_type": move_type,
        "move_pattern": move_type,
        "move_type_label": MANUAL_V1_MOVE_LABELS.get(move_type, move_type),
        "role_type": role_type,
        "role_label": MANUAL_V1_ROLE_LABELS.get(role_type, role_type),
        "weapon_type": weapon_type,
        "weapon_label": "移動撃破",
        "attack_pattern": move_type,
        "attack_range": 1,
        "range": 1,
        "can_attack_after_move": True,
        "trait_key": trait_key,
        "trait_label": MANUAL_V1_TRAIT_LABELS.get(trait_key, trait_key),
        "facing": facing,
        "direction": facing,
        "defeated": False,
        "unit_type": "robot",
        "image_path": image_path,
        "source": source,
    }


def build_manual_initial_board_v1(seed=None, ally_units=None):
    ally_by_species = {str(unit.get("species_key") or ""): unit for unit in ally_units or []}
    allies = [
        _manual_v1_unit(spec, "ally", ally_by_species.get(spec[2]))
        for spec in MANUAL_V1_ALLY_SPECS
    ]
    enemies = [_manual_v1_unit(spec, "enemy") for spec in MANUAL_V1_ENEMY_SPECS]
    state = {
        "mode": "mini_shogi_3x4",
        "display_name": "ミニロボどうぶつしょうぎ",
        "board_width": BOARD_V1_WIDTH,
        "board_height": BOARD_V1_HEIGHT,
        "board_size": BOARD_V1_WIDTH,
        "terrain": build_manual_board_v1_map()["tiles"],
        "seed": int(seed or 0),
        "turn_number": 1,
        "current_turn_side": "ally",
        "units": allies + enemies,
        "result": None,
        "previous_board_state": None,
        "current_board_state": None,
        "last_action_sequence": [],
    }
    return refresh_manual_board_v1_state(state)


def serialize_manual_board_state(state):
    return json.dumps(state, ensure_ascii=False, separators=(",", ":"))


def _manual_v1_units(state, side=None, include_defeated=False):
    units = []
    for unit in state.get("units") or []:
        if not include_defeated and unit.get("defeated"):
            continue
        if side is not None and unit.get("side") != side:
            continue
        units.append(unit)
    return units


def _manual_v1_unit_by_id(state, unit_id):
    for unit in state.get("units") or []:
        if str(unit.get("unit_id") or "") == str(unit_id):
            return unit
    return None


def _manual_v1_in_bounds(x, y):
    return 0 <= int(x) < BOARD_V1_WIDTH and 0 <= int(y) < BOARD_V1_HEIGHT


def _manual_v1_unit_at(state, x, y, except_unit_id=None):
    for unit in _manual_v1_units(state):
        if except_unit_id is not None and str(unit.get("unit_id") or "") == str(except_unit_id):
            continue
        if int(unit.get("x") or 0) == int(x) and int(unit.get("y") or 0) == int(y):
            return unit
    return None


def _manual_v1_occupied(state, x, y, except_unit_id=None):
    return _manual_v1_unit_at(state, x, y, except_unit_id=except_unit_id) is not None


def _manual_v1_same_side_occupied(state, side, x, y, except_unit_id=None):
    unit = _manual_v1_unit_at(state, x, y, except_unit_id=except_unit_id)
    if unit and unit.get("side") == side:
        return True
    return False


def _manual_v1_opponent_side(side):
    return "enemy" if str(side or "ally") == "ally" else "ally"


def _manual_v1_adjacent_cells(x, y):
    cells = []
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx = int(x) + dx
        ny = int(y) + dy
        if _manual_v1_in_bounds(nx, ny):
            cells.append({"x": nx, "y": ny})
    return cells


def get_zoc_cells(side, board_state):
    return []


def manual_board_v1_zoc_cells(state, side):
    return get_zoc_cells(side, state)


def _manual_v1_is_zoc(state, side, x, y):
    return (int(x), int(y)) in {(cell["x"], cell["y"]) for cell in get_zoc_cells(side, state)}


def is_in_enemy_zoc(unit, board_state):
    if not unit or unit.get("defeated"):
        return False
    return _manual_v1_is_zoc(board_state, unit.get("side"), unit.get("x") or 0, unit.get("y") or 0)


def is_move_blocked_by_zoc(unit, to_x, to_y, board_state):
    if not unit or unit.get("defeated"):
        return False
    if not is_in_enemy_zoc(unit, board_state):
        return False
    return _manual_v1_is_zoc(board_state, unit.get("side"), to_x, to_y)


def is_leader_guarded(leader, board_state):
    return False


def refresh_manual_board_v1_state(state):
    for unit in state.get("units") or []:
        if unit.get("is_leader"):
            unit["guarded"] = is_leader_guarded(unit, state)
        else:
            unit["guarded"] = False
    state["enemy_threat_cells"] = get_enemy_threat_cells("ally", state)
    return state


def _manual_v1_snapshot(state):
    snapshot = {
        key: value
        for key, value in state.items()
        if key not in {"previous_board_state", "current_board_state", "last_action_sequence"}
    }
    return json.loads(json.dumps(snapshot, ensure_ascii=False))


def _manual_v1_tag_phase(logs, phase):
    for log in logs:
        log["phase"] = phase
    return logs


def get_legal_moves(unit, board_state):
    if not unit or unit.get("defeated"):
        return []
    side = str(unit.get("side") or "ally")
    x = int(unit.get("x") or 0)
    y = int(unit.get("y") or 0)
    forward = -1 if side == "ally" else 1
    move_type = str(unit.get("move_type") or "sphinx")
    if move_type == "leader":
        deltas = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))
    elif move_type == "flyer":
        deltas = ((-1, forward), (1, forward), (0, -forward))
    elif move_type == "guardian":
        deltas = ((0, forward), (-1, 0), (1, 0), (-1, -forward), (1, -forward))
    elif move_type == "sphinx":
        deltas = ((-1, forward), (1, forward), (-1, 0), (1, 0), (0, -forward))
    else:
        deltas = ((0, forward), (-1, 0), (1, 0))
    moves = []
    for dx, dy in deltas:
        nx = x + dx
        ny = y + dy
        if not _manual_v1_in_bounds(nx, ny):
            continue
        if _manual_v1_same_side_occupied(board_state, side, nx, ny, except_unit_id=unit.get("unit_id")):
            continue
        occupant = _manual_v1_unit_at(board_state, nx, ny, except_unit_id=unit.get("unit_id"))
        moves.append({"x": nx, "y": ny, "capture": bool(occupant and occupant.get("side") != side)})
    return moves


def _manual_v1_attack_cells_from(unit):
    return [{"x": cell["x"], "y": cell["y"]} for cell in get_legal_moves(unit, {"units": [unit]})]


def can_attack_manual(attacker, target, board_state, moved=False):
    if not attacker or not target or attacker.get("defeated") or target.get("defeated"):
        return False
    if attacker.get("side") == target.get("side"):
        return False
    return any(int(cell["x"]) == int(target.get("x") or 0) and int(cell["y"]) == int(target.get("y") or 0) for cell in get_legal_moves(attacker, board_state))


def get_legal_targets(unit, board_state, moved=False):
    return [
        target
        for target in _manual_v1_units(board_state)
        if can_attack_manual(unit, target, board_state, moved=moved)
    ]


def get_enemy_threat_cells(side, board_state):
    cells = set()
    for unit in _manual_v1_units(board_state, _manual_v1_opponent_side(side)):
        for cell in _manual_v1_attack_cells_from(unit):
            cells.add((cell["x"], cell["y"]))
    return [{"x": x, "y": y} for x, y in sorted(cells, key=lambda p: (p[1], p[0]))]


def get_threatened_cells(board_state, side):
    cells = set()
    for unit in _manual_v1_units(board_state, side):
        for cell in _manual_v1_attack_cells_from(unit):
            cells.add((int(cell["x"]), int(cell["y"])))
    return [{"x": x, "y": y} for x, y in sorted(cells, key=lambda p: (p[1], p[0]))]


def get_piece_value(piece_type):
    values = {
        "leader": 1000,
        "guardian": 4,
        "flyer": 3,
        "sphinx": 2,
    }
    return int(values.get(str(piece_type or ""), 1))


def calculate_manual_damage(attacker, target):
    return 1


def check_manual_result(board_state):
    ally_leader = next((u for u in board_state.get("units") or [] if u.get("side") == "ally" and u.get("is_leader")), None)
    enemy_leader = next((u for u in board_state.get("units") or [] if u.get("side") == "enemy" and u.get("is_leader")), None)
    if ally_leader and ally_leader.get("defeated"):
        return "enemy_win"
    if enemy_leader and enemy_leader.get("defeated"):
        return "ally_win"
    if not _manual_v1_units(board_state, "ally"):
        return "enemy_win"
    if not _manual_v1_units(board_state, "enemy"):
        return "ally_win"
    return None


def _manual_v1_log(logs, text, event_type="log", **payload):
    item = {"type": event_type, "text": str(text), **payload}
    logs.append(item)
    return item


def _manual_v1_clone_state(state):
    return json.loads(json.dumps(state, ensure_ascii=False))


def _manual_v1_apply_attack(state, attacker, target, logs, moved=False):
    if not can_attack_manual(attacker, target, state, moved=moved):
        return False, "攻撃できない対象です。"
    from_x = int(attacker.get("x") or 0)
    from_y = int(attacker.get("y") or 0)
    target["defeated"] = True
    attacker["x"] = int(target.get("x") or 0)
    attacker["y"] = int(target.get("y") or 0)
    attacker["facing"] = _direction_from_delta(attacker["x"] - from_x, attacker["y"] - from_y, attacker.get("facing"))
    _manual_v1_log(
        logs,
        f"{attacker['name']}が{target['name']}を取った",
        "move_capture",
        phase="ally",
        actor_unit_id=attacker.get("unit_id"),
        target_unit_id=target.get("unit_id"),
        weapon_type=attacker.get("weapon_type"),
        weapon_label=attacker.get("weapon_label"),
        **{"from": {"x": from_x, "y": from_y}, "to": {"x": attacker["x"], "y": attacker["y"]}},
    )
    return True, None


def _manual_v1_apply_move(state, unit, move_to, logs):
    allowed = {(cell["x"], cell["y"]) for cell in get_legal_moves(unit, state)}
    dest = (int(move_to["x"]), int(move_to["y"]))
    if dest not in allowed:
        return False, "移動できないマスです。"
    occupant = _manual_v1_unit_at(state, dest[0], dest[1], except_unit_id=unit.get("unit_id"))
    if occupant and occupant.get("side") != unit.get("side"):
        return _manual_v1_apply_attack(state, unit, occupant, logs, moved=True)
    from_x = int(unit.get("x") or 0)
    from_y = int(unit.get("y") or 0)
    unit["x"], unit["y"] = dest
    unit["facing"] = _direction_from_delta(dest[0] - from_x, dest[1] - from_y, unit.get("facing"))
    _manual_v1_log(
        logs,
        f"{unit['name']}が前進",
        "move",
        phase="ally",
        actor_unit_id=unit.get("unit_id"),
        **{"from": {"x": from_x, "y": from_y}, "to": {"x": dest[0], "y": dest[1]}},
    )
    return True, None


def enumerate_manual_legal_actions(board_state, side):
    actions = []
    for unit in sorted(_manual_v1_units(board_state, side), key=lambda u: str(u.get("unit_id") or "")):
        for move in get_legal_moves(unit, board_state):
            target = _manual_v1_unit_at(board_state, move["x"], move["y"], except_unit_id=unit.get("unit_id"))
            actions.append(
                {
                    "actor_unit_id": unit.get("unit_id"),
                    "move_to": {"x": int(move["x"]), "y": int(move["y"])},
                    "target_unit_id": target.get("unit_id") if target and target.get("side") != side else None,
                    "is_capture": bool(target and target.get("side") != side),
                }
            )
    return actions


def _manual_v1_apply_action_to_state(state, action):
    actor = _manual_v1_unit_by_id(state, action.get("actor_unit_id"))
    if not actor:
        return False
    logs = []
    ok, _ = _manual_v1_apply_move(state, actor, action.get("move_to"), logs)
    return bool(ok)


def _manual_v1_leader(state, side):
    return next((u for u in _manual_v1_units(state, side) if u.get("is_leader")), None)


def _manual_v1_cell_in(cells, x, y):
    return any(int(cell.get("x") or 0) == int(x) and int(cell.get("y") or 0) == int(y) for cell in cells)


def _manual_v1_cpu_style(state):
    styles = ("balanced", "aggressive", "defensive")
    return styles[int(state.get("seed") or 0) % len(styles)]


def score_manual_cpu_action(board_state, action, rng=None):
    side = "enemy"
    opponent = "ally"
    actor = _manual_v1_unit_by_id(board_state, action.get("actor_unit_id"))
    target = _manual_v1_unit_by_id(board_state, action.get("target_unit_id"))
    if not actor:
        return -10000
    style = _manual_v1_cpu_style(board_state)
    score = 0
    if target:
        if target.get("is_leader"):
            score += 1000
        else:
            capture_score = 100 + get_piece_value(target.get("move_type") or target.get("piece_type"))
            if style == "aggressive":
                capture_score += 20
            score += capture_score
    before_leader = _manual_v1_leader(board_state, side)
    before_threats = get_threatened_cells(board_state, opponent)
    before_leader_threatened = bool(before_leader and _manual_v1_cell_in(before_threats, before_leader.get("x"), before_leader.get("y")))

    next_state = _manual_v1_clone_state(board_state)
    if not _manual_v1_apply_action_to_state(next_state, action):
        return -10000
    next_leader = _manual_v1_leader(next_state, side)
    next_threats = get_threatened_cells(next_state, opponent)
    next_leader_threatened = bool(next_leader and _manual_v1_cell_in(next_threats, next_leader.get("x"), next_leader.get("y")))
    if before_leader_threatened and not next_leader_threatened:
        score += 80
    if next_leader_threatened:
        score -= 200 if actor.get("is_leader") else 80
        if style == "defensive":
            score -= 40

    acted = _manual_v1_unit_by_id(next_state, action.get("actor_unit_id"))
    if acted and _manual_v1_cell_in(next_threats, acted.get("x"), acted.get("y")):
        score -= 60

    ally_leader = _manual_v1_leader(next_state, opponent)
    if ally_leader and acted:
        distance = abs(int(acted.get("x") or 0) - int(ally_leader.get("x") or 0)) + abs(int(acted.get("y") or 0) - int(ally_leader.get("y") or 0))
        score += max(0, 6 - distance) * 20
    return score


def choose_manual_cpu_action(board_state, rng=None):
    rng = rng or random.Random(int(board_state.get("seed") or 0))
    actions = enumerate_manual_legal_actions(board_state, "enemy")
    if not actions:
        return None
    scored = [(score_manual_cpu_action(board_state, action, rng), action) for action in actions]
    best_score = max(score for score, _ in scored)
    best_actions = [action for score, action in scored if score == best_score]
    return rng.choice(best_actions)


def run_enemy_manual_turn(board_state, rng=None):
    logs = []
    action = choose_manual_cpu_action(board_state, rng)
    if not action:
        enemy = next(iter(_manual_v1_units(board_state, "enemy")), None)
        if enemy:
            _manual_v1_log(logs, f"{enemy['name']}が待機", "wait", actor_unit_id=enemy.get("unit_id"))
        return logs
    enemy = _manual_v1_unit_by_id(board_state, action.get("actor_unit_id"))
    if not enemy:
        return logs
    ok, error = _manual_v1_apply_move(board_state, enemy, action.get("move_to"), logs)
    if error:
        _manual_v1_log(logs, f"{enemy['name']}が待機", "wait", actor_unit_id=enemy.get("unit_id"))
    return logs


def apply_manual_action(board_state, action_payload):
    state = dict(board_state)
    state["units"] = [dict(unit) for unit in board_state.get("units") or []]
    state.pop("previous_board_state", None)
    state.pop("current_board_state", None)
    state.pop("last_action_sequence", None)
    refresh_manual_board_v1_state(state)
    previous_snapshot = _manual_v1_snapshot(state)
    logs = []
    sequence = []
    if state.get("result"):
        return state, logs, "すでに決着しています。"
    if str(state.get("current_turn_side") or "ally") != "ally":
        return state, logs, "現在は味方ターンではありません。"
    actor = _manual_v1_unit_by_id(state, action_payload.get("actor_unit_id"))
    if not actor or actor.get("side") != "ally" or actor.get("defeated"):
        return state, logs, "行動できないユニットです。"
    move_to = action_payload.get("move_to")
    target_id = action_payload.get("target_unit_id")
    moved = False
    if move_to:
        start_index = len(logs)
        ok, error = _manual_v1_apply_move(state, actor, move_to, logs)
        if not ok:
            return state, logs, error
        sequence.extend(_manual_v1_tag_phase(logs[start_index:], "ally"))
        moved = True
    if target_id:
        target = _manual_v1_unit_by_id(state, target_id)
        if not target:
            return state, logs, "攻撃対象が見つかりません。"
        start_index = len(logs)
        ok, error = _manual_v1_apply_attack(state, actor, target, logs, moved=moved)
        if not ok:
            return state, logs, error
        sequence.extend(_manual_v1_tag_phase(logs[start_index:], "ally"))
    if not move_to and not target_id:
        return state, logs, "行動内容がありません。"
    result = check_manual_result(state)
    if not result:
        state["current_turn_side"] = "enemy"
        enemy_logs = run_enemy_manual_turn(state, random.Random(int(state.get("seed") or 0) + int(state.get("turn_number") or 1)))
        sequence.extend(_manual_v1_tag_phase(enemy_logs, "enemy"))
        logs.extend(enemy_logs)
        result = check_manual_result(state)
    state["result"] = result
    if result:
        state["current_turn_side"] = "finished"
        result_log = _manual_v1_log(logs, "味方側の勝利" if result == "ally_win" else "敵側の勝利", "result", phase="result", result=result)
        sequence.append(result_log)
    else:
        state["current_turn_side"] = "ally"
        state["turn_number"] = int(state.get("turn_number") or 1) + 1
    refresh_manual_board_v1_state(state)
    current_snapshot = _manual_v1_snapshot(state)
    state["previous_board_state"] = previous_snapshot
    state["current_board_state"] = current_snapshot
    state["last_action_sequence"] = sequence
    return state, logs, None


def get_manual_board_state(db, battle_id):
    row = db.execute("SELECT * FROM mini_tactics_battles WHERE id = ?", (int(battle_id),)).fetchone()
    if not row:
        return None
    return json.loads(row["board_state_json"] or "{}")


def manual_board_v1_action_options(board_state, unit_id):
    board_state = refresh_manual_board_v1_state(dict(board_state, units=[dict(u) for u in board_state.get("units") or []]))
    unit = _manual_v1_unit_by_id(board_state, unit_id)
    if not unit:
        return {"move_cells": [], "attackable_cells": [], "targetable_unit_ids": [], "after_move": {}}
    targets = get_legal_targets(unit, board_state, moved=False)
    threat_set = {(cell["x"], cell["y"]) for cell in get_enemy_threat_cells(unit.get("side"), board_state)}
    move_cells = get_legal_moves(unit, board_state)
    options = {
        "move_cells": [
            {**move, "danger": (move["x"], move["y"]) in threat_set}
            for move in move_cells
        ],
        "attackable_cells": [{"x": move["x"], "y": move["y"]} for move in move_cells],
        "targetable_unit_ids": [str(target.get("unit_id") or "") for target in targets],
        "after_move": {},
        "enemy_zoc_cells": get_zoc_cells(unit.get("side"), board_state),
        "enemy_threat_cells": get_enemy_threat_cells(unit.get("side"), board_state),
    }
    for move in options["move_cells"]:
        moved_state = dict(board_state)
        moved_state["units"] = [dict(u) for u in board_state.get("units") or []]
        moved_unit = _manual_v1_unit_by_id(moved_state, unit_id)
        moved_unit["x"] = int(move["x"])
        moved_unit["y"] = int(move["y"])
        moved_targets = get_legal_targets(moved_unit, moved_state, moved=True)
        options["after_move"][f"{move['x']},{move['y']}"] = {
            "attackable_cells": [],
            "targetable_unit_ids": [str(target.get("unit_id") or "") for target in moved_targets],
            "move_notice": "",
        }
    return options


mini_shogi_4x4_action_options = manual_board_v1_action_options
mini_shogi_4x4_zoc_cells = manual_board_v1_zoc_cells
mini_shogi_4x4_threat_cells = get_enemy_threat_cells


def create_manual_board_battle(db, admin_user_id, ally_units=None, seed=None):
    battle_seed = int(seed if seed is not None else random.randint(100000, 999999999))
    map_payload = build_manual_board_v1_map()
    board_state = build_manual_initial_board_v1(battle_seed, ally_units)
    units_payload = board_state.get("units") or []
    now = int(time.time())
    cur = db.execute(
        """
        INSERT INTO mini_tactics_battles
        (
            seed, status, mode, map_json, units_json, frames_json,
            board_state_json, action_log_json, current_turn_side, turn_number, result,
            created_at, created_by_user_id
        )
        VALUES (?, 'manual_active', 'mini_shogi_3x4', ?, ?, '[]', ?, '[]', 'ally', 1, NULL, ?, ?)
        """,
        (
            int(battle_seed),
            json.dumps(map_payload, ensure_ascii=False, separators=(",", ":")),
            json.dumps(units_payload, ensure_ascii=False, separators=(",", ":")),
            serialize_manual_board_state(board_state),
            int(now),
            int(admin_user_id),
        ),
    )
    db.commit()
    return int(cur.lastrowid)


def choose_attack_target(unit, units, ai_type=None, map_payload=None):
    targets = find_targets_in_range(unit, units, map_payload)
    if not targets:
        return None
    if str(ai_type or unit.get("ai_type") or "assault") == "guardian":
        allies = living_allies(unit, units)
        return min(
            targets,
            key=lambda enemy: (
                _enemy_pressure_score(enemy, allies),
                int(enemy.get("hp") or 0),
                manhattan(unit, enemy),
                str(enemy.get("unit_id") or ""),
            ),
        )
    return min(targets, key=lambda enemy: (manhattan(unit, enemy), int(enemy.get("hp") or 0), str(enemy.get("unit_id") or "")))


def get_attack_target(unit, units, map_payload=None):
    return choose_attack_target(unit, units, unit.get("ai_type"), map_payload)


def _enemy_pressure_score(enemy, allies):
    if not allies:
        return 999
    return min(manhattan(enemy, ally) for ally in allies)


def get_guardian_adjacent_enemy(unit, units, map_payload=None):
    return choose_attack_target(unit, units, "guardian", map_payload)


def find_guardian_enemy(unit, units):
    enemies = living_enemies(unit, units)
    if not enemies:
        return None
    allies = living_allies(unit, units)
    return min(
        enemies,
        key=lambda enemy: (_enemy_pressure_score(enemy, allies), manhattan(unit, enemy), str(enemy.get("unit_id") or "")),
    )


def blocked_laser_target(unit, units, map_payload):
    if str(unit.get("weapon_type") or "") != "laser":
        return None
    attack_range = int(unit.get("attack_range") or unit.get("range") or 2)
    for enemy in living_enemies(unit, units):
        same_line = int(unit["x"]) == int(enemy["x"]) or int(unit["y"]) == int(enemy["y"])
        if same_line and manhattan(unit, enemy) <= attack_range and not has_line_of_sight(unit, enemy, map_payload, "laser"):
            return enemy
    return None


def choose_assault_move(unit, units, map_payload, rng):
    target = get_attack_target(unit, units, map_payload)
    if target:
        return _action_attack(unit, target)
    blocked = blocked_laser_target(unit, units, map_payload)
    if blocked:
        return _action_wait(unit, f"{unit['name']}は壁に遮られて狙えない")
    target = find_nearest_enemy(unit, units)
    step = _choose_by_distance(unit, get_valid_moves(unit, units, map_payload), target, rng, prefer="near")
    if step:
        return _action_move(unit, step[0], step[1], f"{unit['name']}が突撃")
    return _action_wait(unit)


def choose_cautious_move(unit, units, map_payload, rng):
    target = find_nearest_enemy(unit, units)
    hp = int(unit.get("hp") or 0)
    max_hp = max(1, int(unit.get("max_hp") or hp or 1))
    is_low_hp = hp * 2 <= max_hp
    if is_low_hp:
        step = _choose_by_distance(unit, get_valid_moves(unit, units, map_payload), target, rng, prefer="far")
        if step:
            if get_attack_target(unit, units, map_payload):
                return _action_move(unit, step[0], step[1], f"{unit['name']}が距離を取りながら射程を維持")
            return _action_move(unit, step[0], step[1], f"{unit['name']}が距離を取った")
        adjacent = get_attack_target(unit, units, map_payload)
        if adjacent:
            return _action_attack(unit, adjacent, f"{unit['name']}は退路がなく反撃")
        return _action_wait(unit, f"{unit['name']}が慎重に様子を見た")
    adjacent = get_attack_target(unit, units, map_payload)
    if adjacent:
        return _action_attack(unit, adjacent)
    blocked = blocked_laser_target(unit, units, map_payload)
    if blocked:
        return _action_wait(unit, f"{unit['name']}は壁に遮られて狙えない")
    step = _choose_by_distance(unit, get_valid_moves(unit, units, map_payload), target, rng, prefer="near")
    if step:
        return _action_move(unit, step[0], step[1], f"{unit['name']}が慎重に前進")
    return _action_wait(unit)


def choose_guardian_move(unit, units, map_payload, rng):
    adjacent = get_guardian_adjacent_enemy(unit, units, map_payload)
    if adjacent:
        if str(unit.get("weapon_type") or "") == "missile":
            return _action_attack(unit, adjacent, f"{unit['name']}が味方を守る位置からミサイル支援")
        return _action_attack(unit, adjacent)
    blocked = blocked_laser_target(unit, units, map_payload)
    if blocked:
        return _action_wait(unit, f"{unit['name']}は壁に遮られて狙えない")
    nearest_ally = find_nearest_ally(unit, units)
    if nearest_ally and manhattan(unit, nearest_ally) > 1:
        step = _choose_by_distance(unit, get_valid_moves(unit, units, map_payload), nearest_ally, rng, prefer="near")
        if step:
            return _action_move(unit, step[0], step[1], f"{unit['name']}が味方を守る位置へ移動")
    target = find_guardian_enemy(unit, units)
    step = _choose_by_distance(unit, get_valid_moves(unit, units, map_payload), target, rng, prefer="near")
    if step:
        return _action_move(unit, step[0], step[1], f"{unit['name']}が味方を守る位置へ移動")
    return _action_wait(unit, f"{unit['name']}が守りを固めた")


def choose_action_for_unit(unit, units, map_payload, rng):
    ai_type = str(unit.get("ai_type") or "assault")
    if ai_type == "cautious":
        return choose_cautious_move(unit, units, map_payload, rng)
    if ai_type == "guardian":
        return choose_guardian_move(unit, units, map_payload, rng)
    return choose_assault_move(unit, units, map_payload, rng)


def get_next_step_toward_enemy(unit, units, map_payload, rng):
    action = choose_assault_move(unit, units, map_payload, rng)
    if action["type"] == "move":
        return int(action["x"]), int(action["y"]), "move"
    if action["type"] == "attack":
        return int(unit["x"]), int(unit["y"]), "contact"
    return int(unit["x"]), int(unit["y"]), "wait"


def _battle_result(units):
    ally_alive = any(u.get("side") == "ally" and not u.get("defeated") for u in units)
    enemy_alive = any(u.get("side") == "enemy" and not u.get("defeated") for u in units)
    if ally_alive and not enemy_alive:
        return "ally_win"
    if enemy_alive and not ally_alive:
        return "enemy_win"
    if not ally_alive and not enemy_alive:
        return "draw"
    return None


def _result_log(result):
    if result == "ally_win":
        return "味方側の勝利"
    if result == "enemy_win":
        return "敵側の勝利"
    return "10ターン経過で引き分け"


def serialize_frames(frames):
    return json.dumps(frames, ensure_ascii=False, separators=(",", ":"))


def build_turn_order(units, seed, turn):
    living = [unit for unit in units if not unit.get("defeated")]
    decorated = []
    for unit in living:
        tie = random.Random(f"{int(seed)}:{int(turn)}:{unit.get('unit_id')}:order").random()
        decorated.append((-int(unit.get("spd") or 0), tie, str(unit.get("unit_id") or ""), unit))
    decorated.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in decorated]


def _frame_actor_payload(actor, units, map_payload):
    if not actor:
        return None, [], []
    return (
        str(actor.get("unit_id") or ""),
        attackable_cells(actor, map_payload),
        targetable_unit_ids(actor, units, map_payload),
    )


def simulate_mini_tactics_battle(seed, map_payload, units_payload):
    units = [normalize_unit(unit) for unit in units_payload]
    frames = []
    result = None
    for turn in range(1, MAX_TURNS + 1):
        logs = []
        events = []
        acting_units = build_turn_order(units, seed, turn)
        acting_order = [
            {
                "unit_id": str(unit.get("unit_id") or ""),
                "name": str(unit.get("name") or ""),
                "side": str(unit.get("side") or ""),
                "spd": int(unit.get("spd") or 0),
            }
            for unit in acting_units
        ]
        order_text = "行動順: " + " → ".join(item["name"] for item in acting_order)
        logs.append(order_text)
        for unit in acting_units:
            if unit.get("defeated"):
                continue

            rng = random.Random(f"{int(seed)}:{turn}:{unit.get('unit_id')}")
            action = choose_action_for_unit(unit, units, map_payload, rng)

            if action["type"] == "attack":
                target = next(
                    (
                        other
                        for other in units
                        if str(other.get("unit_id") or "") == str(action.get("target_id") or "")
                        and not other.get("defeated")
                    ),
                    None,
                )
                if target is None:
                    text = f"{unit['name']}が待機"
                    logs.append(text)
                    events.append(build_wait_event(unit, text))
                    continue
                damage = max(1, int(unit.get("atk") or 1) - int(target.get("def") or 0))
                target["hp"] = max(0, int(target.get("hp") or 0) - int(damage))
                weapon_type = str(unit.get("weapon_type") or "melee")
                text = f"{action['message']}、{damage}ダメージ"
                logs.append(text)
                events.append(build_attack_event(unit, target, weapon_type, damage, text))
                if int(target["hp"]) <= 0 and not target.get("defeated"):
                    target["defeated"] = True
                    defeated_text = f"{target['name']}を撃破"
                    logs.append(defeated_text)
                    events.append(build_defeated_event(target, defeated_text))
                result = _battle_result(units)
                if result:
                    result_text = _result_log(result)
                    logs.append(result_text)
                    events.append(build_result_event(result, result_text))
                    break
                continue

            before_x = int(unit["x"])
            before_y = int(unit["y"])
            if action["type"] == "move":
                nx = int(action["x"])
                ny = int(action["y"])
                unit["x"] = int(nx)
                unit["y"] = int(ny)
                unit["direction"] = _direction_from_delta(nx - before_x, ny - before_y, unit.get("direction"))
                logs.append(action["message"])
                events.append(build_move_event(unit, before_x, before_y, nx, ny, action["message"]))
            else:
                logs.append(action["message"])
                events.append(build_wait_event(unit, action["message"]))
        if not result and turn >= MAX_TURNS:
            result = _battle_result(units) or "draw"
            result_text = _result_log(result)
            logs.append(result_text)
            events.append(build_result_event(result, result_text))
        current_actor = next((unit for unit in acting_units if not unit.get("defeated")), None)
        current_actor_unit_id, attackable, targetable = _frame_actor_payload(current_actor, units, map_payload)
        frames.append(
            {
                "turn": turn,
                "units": [dict(unit) for unit in units],
                "logs": logs,
                "events": events,
                "acting_order": acting_order,
                "current_actor_unit_id": current_acto