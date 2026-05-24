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


def find_nearest_ally(unit, units):
    allies = living_allies(unit, units)
    if not allies:
        return None
    return min(allies, key=lambda ally: (manhattan(unit, ally), str(ally.get("unit_id") or "")))


def get_valid_moves(unit, units, map_payload):
    occupied = {
        (int(other["x"]), int(other["y"]))
        for other in units
        if str(other.get("unit_id") or "") != str(unit.get("unit_id") or "")
    }
    width = int(map_payload.get("width") or BOARD_SIZE)
    height = int(map_payload.get("height") or BOARD_SIZE)
    moves = []
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx = int(unit["x"]) + dx
        ny = int(unit["y"]) + dy
        if nx < 0 or ny < 0 or nx >= width or ny >= height:
            continue
        if (nx, ny) in occupied or _tile_is_wall(map_payload, nx, ny):
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
    return {
        "type": "attack",
        "target_id": str(target.get("unit_id") or ""),
        "message": message or f"{unit['name']}が{target['name']}を攻撃",
    }


def _action_wait(unit, message=None):
    return {"type": "wait", "message": message or f"{unit['name']}が待機"}


def get_adjacent_enemy(unit, units):
    enemies = [
        u
        for u in units
        if u.get("side") != unit.get("side") and not u.get("defeated") and manhattan(unit, u) == 1
    ]
    if not enemies:
        return None
    return min(enemies, key=lambda enemy: (int(enemy.get("hp") or 0), str(enemy.get("unit_id") or "")))


def _enemy_pressure_score(enemy, allies):
    if not allies:
        return 999
    return min(manhattan(enemy, ally) for ally in allies)


def get_guardian_adjacent_enemy(unit, units):
    enemies = [
        u
        for u in units
        if u.get("side") != unit.get("side") and not u.get("defeated") and manhattan(unit, u) == 1
    ]
    if not enemies:
        return None
    allies = living_allies(unit, units)
    return min(
        enemies,
        key=lambda enemy: (_enemy_pressure_score(enemy, allies), int(enemy.get("hp") or 0), str(enemy.get("unit_id") or "")),
    )


def find_guardian_enemy(unit, units):
    enemies = living_enemies(unit, units)
    if not enemies:
        return None
    allies = living_allies(unit, units)
    return min(
        enemies,
        key=lambda enemy: (_enemy_pressure_score(enemy, allies), manhattan(unit, enemy), str(enemy.get("unit_id") or "")),
    )


def choose_assault_move(unit, units, map_payload, rng):
    target = get_adjacent_enemy(unit, units)
    if target:
        return _action_attack(unit, target)
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
            return _action_move(unit, step[0], step[1], f"{unit['name']}が距離を取った")
        adjacent = get_adjacent_enemy(unit, units)
        if adjacent:
            return _action_attack(unit, adjacent, f"{unit['name']}は退路がなく反撃")
        return _action_wait(unit, f"{unit['name']}が慎重に様子を見た")
    adjacent = get_adjacent_enemy(unit, units)
    if adjacent:
        return _action_attack(unit, adjacent)
    step = _choose_by_distance(unit, get_valid_moves(unit, units, map_payload), target, rng, prefer="near")
    if step:
        return _action_move(unit, step[0], step[1], f"{unit['name']}が慎重に前進")
    return _action_wait(unit)


def choose_guardian_move(unit, units, map_payload, rng):
    adjacent = get_guardian_adjacent_enemy(unit, units)
    if adjacent:
        return _action_attack(unit, adjacent)
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


def simulate_mini_tactics_battle(seed, map_payload, units_payload):
    units = [dict(unit) for unit in units_payload]
    for unit in units:
        unit["max_hp"] = int(unit.get("max_hp") or unit.get("hp") or 10)
        unit["hp"] = int(unit.get("hp") or unit["max_hp"])
        unit["atk"] = int(unit.get("atk") or 1)
        unit["def"] = int(unit.get("def") or 0)
        unit["ai_type"] = str(unit.get("ai_type") or "assault")
        unit["defeated"] = bool(unit.get("defeated")) or int(unit["hp"]) <= 0
    frames = []
    result = None
    for turn in range(1, MAX_TURNS + 1):
        logs = []
        for unit in sorted(units, key=lambda item: str(item.get("unit_id") or "")):
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
                    logs.append(f"{unit['name']}が待機")
                    continue
                damage = max(1, int(unit.get("atk") or 1) - int(target.get("def") or 0))
                target["hp"] = max(0, int(target.get("hp") or 0) - int(damage))
                logs.append(f"{action['message']}、{damage}ダメージ")
                if int(target["hp"]) <= 0 and not target.get("defeated"):
                    target["defeated"] = True
                    logs.append(f"{target['name']}を撃破")
                result = _battle_result(units)
                if result:
                    logs.append(_result_log(result))
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
            else:
                logs.append(action["message"])
        if not result and turn >= MAX_TURNS:
            result = _battle_result(units) or "draw"
            logs.append(_result_log(result))
        frames.append(
            {
                "turn": turn,
                "units": [dict(unit) for unit in units],
                "logs": logs,
                "result": result,
            }
        )
        if result:
            break
    return frames


def create_mini_tactics_battle(db, admin_user_id, seed=None, ally_units=None):
    battle_seed = int(seed if seed is not None else random.randint(100000, 999999999))
    map_payload = build_initial_map()
    units_payload = build_units_with_allies(ally_units) if ally_units is not None else build_initial_units()
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
