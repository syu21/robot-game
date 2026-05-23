import json
import random
import time


BOARD_SIZE = 5
MAX_TURNS = 10


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
            "ai_type": "assault",
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
            "ai_type": "assault",
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


def get_next_step_toward_enemy(unit, units, map_payload, rng):
    enemies = [u for u in units if u.get("side") != unit.get("side") and not u.get("defeated")]
    if not enemies:
        return int(unit["x"]), int(unit["y"]), "wait"

    target = min(enemies, key=lambda enemy: (manhattan(unit, enemy), str(enemy.get("unit_id") or "")))
    current_distance = manhattan(unit, target)
    if current_distance <= 1:
        return int(unit["x"]), int(unit["y"]), "contact"

    occupied = {
        (int(other["x"]), int(other["y"]))
        for other in units
        if str(other.get("unit_id") or "") != str(unit.get("unit_id") or "")
    }
    width = int(map_payload.get("width") or BOARD_SIZE)
    height = int(map_payload.get("height") or BOARD_SIZE)
    candidates = []
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx = int(unit["x"]) + dx
        ny = int(unit["y"]) + dy
        if nx < 0 or ny < 0 or nx >= width or ny >= height:
            continue
        if (nx, ny) in occupied or _tile_is_wall(map_payload, nx, ny):
            continue
        next_distance = abs(nx - int(target["x"])) + abs(ny - int(target["y"]))
        if next_distance < current_distance:
            candidates.append((next_distance, nx, ny))
    if not candidates:
        return int(unit["x"]), int(unit["y"]), "wait"

    best_distance = min(item[0] for item in candidates)
    best = [(nx, ny) for dist, nx, ny in candidates if dist == best_distance]
    nx, ny = rng.choice(best)
    return int(nx), int(ny), "move"


def get_adjacent_enemy(unit, units):
    enemies = [
        u
        for u in units
        if u.get("side") != unit.get("side") and not u.get("defeated") and manhattan(unit, u) == 1
    ]
    if not enemies:
        return None
    return min(enemies, key=lambda enemy: (int(enemy.get("hp") or 0), str(enemy.get("unit_id") or "")))


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
        unit["defeated"] = bool(unit.get("defeated")) or int(unit["hp"]) <= 0
    frames = []
    result = None
    for turn in range(1, MAX_TURNS + 1):
        logs = []
        for unit in sorted(units, key=lambda item: str(item.get("unit_id") or "")):
            if unit.get("defeated"):
                continue

            target = get_adjacent_enemy(unit, units)
            if target is not None:
                damage = max(1, int(unit.get("atk") or 1) - int(target.get("def") or 0))
                target["hp"] = max(0, int(target.get("hp") or 0) - int(damage))
                logs.append(f"{unit['name']}が{target['name']}を攻撃、{damage}ダメージ")
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
            rng = random.Random(f"{int(seed)}:{turn}:{unit.get('unit_id')}")
            nx, ny, action = get_next_step_toward_enemy(unit, units, map_payload, rng)
            unit["x"] = int(nx)
            unit["y"] = int(ny)
            unit["direction"] = _direction_from_delta(nx - before_x, ny - before_y, unit.get("direction"))
            if action == "move":
                logs.append(f"{unit['name']}が前進")
            elif action == "contact":
                logs.append(f"{unit['name']}が接敵")
            else:
                logs.append(f"{unit['name']}が待機")
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


def create_mini_tactics_battle(db, admin_user_id, seed=None):
    battle_seed = int(seed if seed is not None else random.randint(100000, 999999999))
    map_payload = build_initial_map()
    units_payload = build_initial_units()
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
