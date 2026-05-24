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
SPECIES_WEAPONS = {
    "cerberus": "melee",
    "phoenix": "laser",
    "hydra": "missile",
    "dummy_a": "melee",
    "dummy_b": "melee",
    "dummy_c": "melee",
}
SPECIES_SPD = {
    "cerberus": 4,
    "phoenix": 6,
    "hydra": 3,
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
                "current_actor_unit_id": current_actor_unit_id,
                "attackable_cells": attackable,
                "targetable_unit_ids": targetable,
                "result": result,
            }
        )
        if result:
            break
    return frames


def create_mini_tactics_battle(db, admin_user_id, seed=None, ally_units=None):
    battle_seed = int(seed if seed is not None else random.randint(100000, 999999999))
    map_payload = build_initial_map()
    units_payload = [normalize_unit(unit) for unit in (build_units_with_allies(ally_units) if ally_units is not None else build_initial_units())]
    frames = simulate_mini_tactics_battle(battle_seed, map_payload, units_payload)
    now = int(time.time())
    cur = db.execute(
        """
        INSERT INTO mini_tactics_battles
        (seed, status, map_json, units_json, frames_json, created_at, created_by_user_id)
        VALUES (?, 'finished', ?, ?, ?, ?, ?)
        """,
        (
            int(battle_seed),
            json.dumps(map_payload, ensure_ascii=False, separators=(",", ":")),
            json.dumps(units_payload, ensure_ascii=False, separators=(",", ":")),
            serialize_frames(frames),
            int(now),
            int(admin_user_id),
        ),
    )
    db.commit()
    return int(cur.lastrowid)
