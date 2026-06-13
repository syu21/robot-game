import json
import random
import time
from datetime import datetime, timedelta, timezone

from constants import AUDIT_EVENT_TYPES
from services.audit import audit_log
from services.simulate_balance import simulate_battle


TOWER_ACCESS_LAYER = 4
TOWER_RUN_MAX_FLOOR = 10
TOWER_BATTLE_MAX_TURNS = 100
TOWER_BOSS_FLOOR_INTERVAL = 10
TOWER_LOW_PLUS_LIMIT = 15
TOWER_WORLD_BEST_EVENT = "TOWER_BEST_FLOOR"
TOWER_WORLD_MILESTONE_EVENT = "TOWER_MILESTONE"
TOWER_WORLD_WEEKLY_LEADER_EVENT = "TOWER_WEEKLY_LEADER"
TOWER_WORLD_ALL_TIME_LEADER_EVENT = "TOWER_ALL_TIME_LEADER"

TOWER_ENVIRONMENTS = (
    {
        "key": "stable_week",
        "display_name": "安定の週",
        "description": "命中と耐久が記録を伸ばしやすい週です。",
        "enemy_order": ["layer_2_mist", "layer_3", "layer_2"],
        "mult": {"hp": 1.00, "atk": 0.96, "def": 1.00, "spd": 0.98, "acc": 1.04, "cri": 1.00},
    },
    {
        "key": "speed_week",
        "display_name": "機動の週",
        "description": "素早さと短期突破が活きやすい週です。",
        "enemy_order": ["layer_2_rush", "layer_3", "layer_2"],
        "mult": {"hp": 0.98, "atk": 1.00, "def": 0.98, "spd": 1.05, "acc": 1.00, "cri": 1.00},
    },
    {
        "key": "power_week",
        "display_name": "暴走の週",
        "description": "攻撃と会心が伸びやすい一方、事故も起きやすい週です。",
        "enemy_order": ["layer_2_rush", "layer_4_burst", "layer_3"],
        "mult": {"hp": 0.98, "atk": 1.06, "def": 0.96, "spd": 1.00, "acc": 0.98, "cri": 1.06},
    },
    {
        "key": "heavy_week",
        "display_name": "重装の週",
        "description": "長期戦になりやすく、防御と耐久が重要な週です。",
        "enemy_order": ["layer_4_forge", "layer_3", "layer_2"],
        "mult": {"hp": 1.06, "atk": 0.98, "def": 1.05, "spd": 0.96, "acc": 1.00, "cri": 1.00},
    },
    {
        "key": "mist_week",
        "display_name": "霧界の週",
        "description": "命中不足を咎める敵が多い週です。",
        "enemy_order": ["layer_4_haze", "layer_2_mist", "layer_3"],
        "mult": {"hp": 1.00, "atk": 1.00, "def": 1.00, "spd": 1.00, "acc": 1.07, "cri": 0.98},
    },
)
TOWER_ENVIRONMENT_BY_KEY = {item["key"]: item for item in TOWER_ENVIRONMENTS}


def ensure_tower_schema(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS tower_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            squad_robot_1_id INTEGER NOT NULL,
            squad_robot_2_id INTEGER NOT NULL,
            squad_robot_3_id INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            start_floor INTEGER NOT NULL DEFAULT 1,
            current_floor INTEGER NOT NULL DEFAULT 1,
            reached_floor INTEGER NOT NULL DEFAULT 0,
            max_floor_in_run INTEGER NOT NULL DEFAULT 10,
            status TEXT NOT NULL DEFAULT 'active',
            environment_key TEXT,
            weekly_key TEXT,
            squad_plus_total INTEGER NOT NULL DEFAULT 0,
            seed INTEGER,
            result_summary_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS tower_run_battles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            floor INTEGER NOT NULL,
            robot_instance_id INTEGER NOT NULL,
            enemy_id INTEGER,
            enemy_key TEXT,
            enemy_name TEXT,
            enemy_scaled_stats_json TEXT,
            battle_result TEXT NOT NULL,
            turn_count INTEGER,
            turn_logs_json TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS tower_run_cooling (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            robot_instance_id INTEGER NOT NULL,
            cooling_cycle_index INTEGER NOT NULL DEFAULT 1,
            used_in_current_cycle INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            UNIQUE(run_id, robot_instance_id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_tower_records (
            user_id INTEGER PRIMARY KEY,
            best_floor INTEGER NOT NULL DEFAULT 0,
            best_run_id INTEGER,
            best_squad_robot_1_id INTEGER,
            best_squad_robot_2_id INTEGER,
            best_squad_robot_3_id INTEGER,
            best_recorded_at TEXT,
            weekly_key TEXT,
            weekly_best_floor INTEGER NOT NULL DEFAULT 0,
            weekly_best_run_id INTEGER,
            weekly_best_recorded_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS tower_weekly_environment (
            weekly_key TEXT PRIMARY KEY,
            environment_key TEXT NOT NULL,
            display_name TEXT NOT NULL,
            description TEXT NOT NULL,
            starts_at TEXT NOT NULL,
            ends_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_tower_runs_user_status ON tower_runs(user_id, status, created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_tower_run_battles_run_floor ON tower_run_battles(run_id, floor)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_user_tower_records_best ON user_tower_records(best_floor DESC, best_recorded_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_user_tower_records_weekly ON user_tower_records(weekly_key, weekly_best_floor DESC, weekly_best_recorded_at DESC)")
    cols = {row["name"] if hasattr(row, "keys") else row[1] for row in db.execute("PRAGMA table_info(tower_runs)").fetchall()}
    if "weekly_key" not in cols:
        db.execute("ALTER TABLE tower_runs ADD COLUMN weekly_key TEXT")
    if "squad_plus_total" not in cols:
        db.execute("ALTER TABLE tower_runs ADD COLUMN squad_plus_total INTEGER NOT NULL DEFAULT 0")
    db.execute("CREATE INDEX IF NOT EXISTS idx_tower_runs_weekly_plus ON tower_runs(weekly_key, squad_plus_total, reached_floor DESC)")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS tower_reward_grants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            reward_key TEXT NOT NULL,
            reward_type TEXT NOT NULL,
            source_run_id INTEGER,
            granted_at TEXT NOT NULL,
            UNIQUE(user_id, reward_key)
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_tower_reward_grants_user ON tower_reward_grants(user_id, granted_at DESC)")


def can_access_tower(user, *, is_public=True):
    if not user:
        return False
    try:
        if int(user["is_admin"] if hasattr(user, "keys") else user.get("is_admin") or 0) == 1:
            return True
    except Exception:
        pass
    if not is_public:
        return False
    try:
        return int(user["max_unlocked_layer"] if hasattr(user, "keys") else user.get("max_unlocked_layer") or 1) >= TOWER_ACCESS_LAYER
    except Exception:
        return False


def can_see_tower_entry(user, *, is_public=True):
    return can_access_tower(user, is_public=is_public)


def current_week_key(now_ts=None):
    jst = timezone(timedelta(hours=9))
    now = datetime.fromtimestamp(int(now_ts or time.time()), tz=jst)
    iso = now.isocalendar()
    return f"{iso.year}-W{int(iso.week):02d}"


def _week_bounds_iso(now_ts=None):
    jst = timezone(timedelta(hours=9))
    now = datetime.fromtimestamp(int(now_ts or time.time()), tz=jst)
    start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.isoformat(), (start + timedelta(days=7)).isoformat()


def _deterministic_environment_for_week(week_key):
    week_num = int(str(week_key).split("W")[-1])
    return dict(TOWER_ENVIRONMENTS[week_num % len(TOWER_ENVIRONMENTS)])


def get_current_tower_environment(db=None, now_ts=None):
    if db is not None and not hasattr(db, "execute"):
        now_ts = db
        db = None
    week_key = current_week_key(now_ts)
    if db is not None:
        row = db.execute("SELECT * FROM tower_weekly_environment WHERE weekly_key = ? LIMIT 1", (week_key,)).fetchone()
        if row:
            env = dict(TOWER_ENVIRONMENT_BY_KEY.get(str(row["environment_key"] or ""), TOWER_ENVIRONMENTS[0]))
            env.update(
                {
                    "key": str(row["environment_key"] or env["key"]),
                    "display_name": str(row["display_name"] or env["display_name"]),
                    "description": str(row["description"] or env["description"]),
                    "weekly_key": week_key,
                    "starts_at": row["starts_at"],
                    "ends_at": row["ends_at"],
                }
            )
            return env
        env = _deterministic_environment_for_week(week_key)
        starts_at, ends_at = _week_bounds_iso(now_ts)
        db.execute(
            """
            INSERT INTO tower_weekly_environment
            (weekly_key, environment_key, display_name, description, starts_at, ends_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (week_key, env["key"], env["display_name"], env["description"], starts_at, ends_at, datetime.now(timezone.utc).isoformat()),
        )
    else:
        env = _deterministic_environment_for_week(week_key)
    env["weekly_key"] = week_key
    return env


def get_user_tower_record(db, user_id):
    row = db.execute("SELECT * FROM user_tower_records WHERE user_id = ?", (int(user_id),)).fetchone()
    if row:
        return row
    return {
        "user_id": int(user_id),
        "best_floor": 0,
        "best_run_id": None,
        "weekly_key": current_week_key(),
        "weekly_best_floor": 0,
        "weekly_best_run_id": None,
    }


def _robot_plus_total(db, robot_ids):
    clean_ids = [int(x) for x in (robot_ids or []) if int(x or 0) > 0]
    if not clean_ids:
        return 0
    placeholders = ",".join(["?"] * len(clean_ids))
    row = db.execute(
        f"""
        SELECT COALESCE(SUM(pi.plus), 0) AS plus_total
        FROM robot_instance_parts rip
        JOIN part_instances pi
          ON pi.id IN (
              rip.head_part_instance_id,
              rip.r_arm_part_instance_id,
              rip.l_arm_part_instance_id,
              rip.legs_part_instance_id
          )
        WHERE rip.robot_instance_id IN ({placeholders})
        """,
        clean_ids,
    ).fetchone()
    return int(row["plus_total"] or 0) if row else 0


def create_tower_run(db, user_id, robot_ids, *, now_text=None, seed=None, environment_key=None):
    clean_ids = [int(x) for x in robot_ids]
    if len(clean_ids) != 3 or len(set(clean_ids)) != 3:
        return {"ok": False, "reason": "duplicate_robots"}
    placeholders = ",".join(["?"] * len(clean_ids))
    rows = db.execute(
        f"""
        SELECT id
        FROM robot_instances
        WHERE user_id = ? AND status = 'active' AND id IN ({placeholders})
        """,
        [int(user_id), *clean_ids],
    ).fetchall()
    if len(rows) != 3:
        return {"ok": False, "reason": "robots_not_found"}
    now = now_text or datetime.now(timezone.utc).isoformat()
    env = get_current_tower_environment(db)
    env_key = environment_key or env["key"]
    week_key = str(env.get("weekly_key") or current_week_key())
    plus_total = _robot_plus_total(db, clean_ids)
    run_seed = int(seed if seed is not None else random.randint(1, 2_000_000_000))
    cur = db.execute(
        """
        INSERT INTO tower_runs
        (user_id, squad_robot_1_id, squad_robot_2_id, squad_robot_3_id, started_at, start_floor,
         current_floor, reached_floor, max_floor_in_run, status, environment_key, weekly_key, squad_plus_total,
         seed, result_summary_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 1, 1, 0, ?, 'active', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(user_id),
            clean_ids[0],
            clean_ids[1],
            clean_ids[2],
            now,
            int(TOWER_RUN_MAX_FLOOR),
            env_key,
            week_key,
            int(plus_total),
            run_seed,
            json.dumps({"cooling_cycle_index": 1}, ensure_ascii=False),
            now,
            now,
        ),
    )
    run_id = int(cur.lastrowid)
    for robot_id in clean_ids:
        db.execute(
            """
            INSERT INTO tower_run_cooling (run_id, robot_instance_id, cooling_cycle_index, used_in_current_cycle, updated_at)
            VALUES (?, ?, 1, 0, ?)
            """,
            (run_id, int(robot_id), now),
        )
    audit_log(
        db,
        AUDIT_EVENT_TYPES.get("TOWER_RUN_START", "audit.tower.run.start"),
        user_id=int(user_id),
        action_key="tower.start",
        entity_type="tower_run",
        entity_id=run_id,
        payload={
            "user_id": int(user_id),
            "run_id": run_id,
            "squad_robot_ids": clean_ids,
            "environment_key": env_key,
            "weekly_key": week_key,
            "squad_plus_total": int(plus_total),
            "status": "active",
        },
    )
    return {"ok": True, "run_id": run_id}


def get_tower_run(db, run_id, user_id=None):
    if user_id is None:
        return db.execute("SELECT * FROM tower_runs WHERE id = ?", (int(run_id),)).fetchone()
    return db.execute(
        "SELECT * FROM tower_runs WHERE id = ? AND user_id = ?",
        (int(run_id), int(user_id)),
    ).fetchone()


def get_tower_cooling(db, run_id):
    return db.execute(
        """
        SELECT *
        FROM tower_run_cooling
        WHERE run_id = ?
        ORDER BY robot_instance_id ASC
        """,
        (int(run_id),),
    ).fetchall()


def _floor_area_candidates(floor, environment_key):
    env = TOWER_ENVIRONMENT_BY_KEY.get(str(environment_key or ""), TOWER_ENVIRONMENTS[0])
    if int(floor) <= 10:
        base = ["layer_1", "layer_2", "layer_2_mist", "layer_2_rush"]
    elif int(floor) <= 20:
        base = ["layer_2", "layer_2_mist", "layer_2_rush", "layer_3"]
    elif int(floor) <= 30:
        base = ["layer_3", "layer_4_forge", "layer_4_haze", "layer_4_burst"]
    else:
        base = ["layer_4_forge", "layer_4_haze", "layer_4_burst", "layer_5_labyrinth", "layer_5_pinnacle"]
    return list(dict.fromkeys(list(env.get("enemy_order") or []) + base))


def get_tower_enemy_for_floor(db, floor, environment_key, seed):
    floor_num = int(floor)
    is_boss = floor_num % TOWER_BOSS_FLOOR_INTERVAL == 0
    area_candidates = _floor_area_candidates(floor_num, environment_key)
    rng = random.Random(int(seed or 1) + floor_num * 7919)
    for area_key in area_candidates:
        if is_boss:
            row = db.execute(
                """
                SELECT *
                FROM enemies
                WHERE is_active = 1 AND is_boss = 1 AND boss_area_key = ?
                ORDER BY id ASC
                """,
                (area_key,),
            ).fetchall()
        else:
            row = db.execute(
                """
                SELECT *
                FROM enemies
                WHERE is_active = 1 AND COALESCE(is_boss, 0) = 0 AND (boss_area_key IS NULL OR boss_area_key = ?)
                ORDER BY id ASC
                """,
                (area_key,),
            ).fetchall()
        if row:
            return dict(rng.choice(list(row)))
    row = db.execute(
        """
        SELECT *
        FROM enemies
        WHERE is_active = 1 AND COALESCE(is_boss, 0) = ?
        ORDER BY id ASC
        LIMIT 1
        """,
        (1 if is_boss else 0,),
    ).fetchone()
    return dict(row) if row else None


def scale_tower_enemy(enemy, floor, environment_key):
    floor_num = max(1, int(floor))
    env = TOWER_ENVIRONMENT_BY_KEY.get(str(environment_key or ""), TOWER_ENVIRONMENTS[0])
    floor_mult = 0.78 + (floor_num - 1) * 0.045
    if floor_num % TOWER_BOSS_FLOOR_INTERVAL == 0:
        floor_mult += 0.10
    env_mult = env.get("mult") or {}
    out = dict(enemy or {})
    for key in ("hp", "atk", "def", "spd", "acc", "cri"):
        base = int(out.get(key) or 1)
        mult = float(env_mult.get(key, 1.0))
        out[key] = max(1, int(round(base * floor_mult * mult)))
    out["_tower_floor_multiplier"] = float(floor_mult)
    out["_tower_environment_key"] = env.get("key")
    return out


def _update_cooling_after_win(db, run_id, robot_instance_id, now_text):
    db.execute(
        """
        UPDATE tower_run_cooling
        SET used_in_current_cycle = 1, updated_at = ?
        WHERE run_id = ? AND robot_instance_id = ?
        """,
        (now_text, int(run_id), int(robot_instance_id)),
    )
    rows = get_tower_cooling(db, run_id)
    if rows and all(int(row["used_in_current_cycle"] or 0) == 1 for row in rows):
        next_cycle = max(int(row["cooling_cycle_index"] or 1) for row in rows) + 1
        db.execute(
            """
            UPDATE tower_run_cooling
            SET used_in_current_cycle = 0, cooling_cycle_index = ?, updated_at = ?
            WHERE run_id = ?
            """,
            (int(next_cycle), now_text, int(run_id)),
        )
        return {"cycle_reset": True, "cooling_cycle_index": int(next_cycle)}
    return {"cycle_reset": False, "cooling_cycle_index": max([int(row["cooling_cycle_index"] or 1) for row in rows] or [1])}


def _run_robot_ids(run):
    return [
        int(run["squad_robot_1_id"]),
        int(run["squad_robot_2_id"]),
        int(run["squad_robot_3_id"]),
    ]


def run_tower_battle(db, run_id, robot_instance_id, robot_stats_provider, *, now_text=None):
    run = get_tower_run(db, run_id)
    if not run:
        return {"ok": False, "reason": "run_not_found"}
    if str(run["status"]) != "active":
        return {"ok": False, "reason": "run_not_active", "run": run}
    robot_id = int(robot_instance_id)
    squad_ids = _run_robot_ids(run)
    if robot_id not in squad_ids:
        return {"ok": False, "reason": "robot_not_in_squad", "run": run}
    cooling = db.execute(
        """
        SELECT *
        FROM tower_run_cooling
        WHERE run_id = ? AND robot_instance_id = ?
        LIMIT 1
        """,
        (int(run_id), robot_id),
    ).fetchone()
    if cooling and int(cooling["used_in_current_cycle"] or 0) == 1:
        return {"ok": False, "reason": "robot_cooling", "run": run}
    stat_obj = robot_stats_provider(db, robot_id)
    if not stat_obj or not stat_obj.get("stats"):
        return {"ok": False, "reason": "robot_stats_missing", "run": run}
    floor = int(run["current_floor"] or 1)
    enemy = get_tower_enemy_for_floor(db, floor, run["environment_key"], run["seed"])
    if not enemy:
        return {"ok": False, "reason": "enemy_missing", "run": run}
    scaled_enemy = scale_tower_enemy(enemy, floor, run["environment_key"])
    battle = simulate_battle(
        stat_obj["stats"],
        {key: int(scaled_enemy[key]) for key in ("hp", "atk", "def", "spd", "acc", "cri")},
        seed=int(run["seed"] or 1) + floor * 1009 + robot_id,
        max_turns=TOWER_BATTLE_MAX_TURNS,
    )
    player_hp_max = max(1, int(stat_obj["stats"].get("hp") or 1))
    enemy_hp_max = max(1, int(scaled_enemy.get("hp") or 1))
    player_damage_total = max(0, int(battle.get("player_damage_total") or 0))
    enemy_damage_total = max(0, int(battle.get("enemy_damage_total") or 0))
    player_final_hp = int(
        battle.get("player_final_hp")
        if battle.get("player_final_hp") is not None
        else max(0, player_hp_max - enemy_damage_total)
    )
    enemy_final_hp = int(
        battle.get("enemy_final_hp")
        if battle.get("enemy_final_hp") is not None
        else max(0, enemy_hp_max - player_damage_total)
    )
    player_final_hp = max(0, min(player_hp_max, player_final_hp))
    enemy_final_hp = max(0, min(enemy_hp_max, enemy_final_hp))
    if player_damage_total <= 0 and enemy_final_hp <= 0:
        enemy_final_hp = enemy_hp_max
    win = enemy_final_hp <= 0 and player_damage_total > 0
    if win and int(battle.get("turns") or 0) <= 1:
        enemy_damage_total = 0
        player_final_hp = player_hp_max
    now = now_text or datetime.now(timezone.utc).isoformat()
    result = "win" if win else "lose"
    turn_logs = [
        {
            "floor": floor,
            "robot_instance_id": robot_id,
            "enemy_key": scaled_enemy.get("key"),
            "enemy_name": scaled_enemy.get("name_ja"),
            "result": result,
            "turns": int(battle.get("turns") or 0),
            "player_hp_start": player_hp_max,
            "player_hp_max": player_hp_max,
            "player_final_hp": player_final_hp,
            "enemy_hp_start": enemy_hp_max,
            "enemy_hp_max": enemy_hp_max,
            "enemy_final_hp": enemy_final_hp,
            "player_damage_total": player_damage_total,
            "enemy_damage_total": enemy_damage_total,
            "battle_turn_logs": list(battle.get("turn_logs") or []),
            "first_actor": str(battle.get("first_actor") or ""),
        }
    ]
    battle_cur = db.execute(
        """
        INSERT INTO tower_run_battles
        (run_id, user_id, floor, robot_instance_id, enemy_id, enemy_key, enemy_name,
         enemy_scaled_stats_json, battle_result, turn_count, turn_logs_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(run_id),
            int(run["user_id"]),
            floor,
            robot_id,
            int(enemy["id"]) if enemy.get("id") else None,
            str(enemy.get("key") or ""),
            str(enemy.get("name_ja") or "敵"),
            json.dumps({key: scaled_enemy.get(key) for key in ("hp", "atk", "def", "spd", "acc", "cri", "key", "name_ja")}, ensure_ascii=False),
            result,
            int(battle.get("turns") or 0),
            json.dumps(turn_logs, ensure_ascii=False),
            now,
        ),
    )
    battle_id = int(battle_cur.lastrowid)
    reached_floor = max(int(run["reached_floor"] or 0), floor if win else floor - 1)
    status = "active"
    ended_at = None
    cooling_result = {"cycle_reset": False}
    if win:
        cooling_result = _update_cooling_after_win(db, run_id, robot_id, now)
        if floor >= int(run["max_floor_in_run"] or TOWER_RUN_MAX_FLOOR):
            status = "completed"
            ended_at = now
        next_floor = floor + 1
    else:
        status = "failed"
        ended_at = now
        next_floor = floor
    summary = {
        "last_floor": floor,
        "last_result": result,
        "last_enemy_key": enemy.get("key"),
        "last_enemy_name": enemy.get("name_ja"),
        "last_robot_instance_id": robot_id,
        "cooling": cooling_result,
    }
    db.execute(
        """
        UPDATE tower_runs
        SET current_floor = ?, reached_floor = ?, status = ?, ended_at = COALESCE(?, ended_at),
            result_summary_json = ?, updated_at = ?
        WHERE id = ?
        """,
        (next_floor, reached_floor, status, ended_at, json.dumps(summary, ensure_ascii=False), now, int(run_id)),
    )
    record_result = update_tower_record_if_needed(db, int(run["user_id"]), int(run_id), reached_floor, _run_robot_ids(run), run["environment_key"], now)
    reward_result = grant_tower_rewards_if_needed(db, int(run["user_id"]), int(run_id), reached_floor, now)
    audit_event = "TOWER_BATTLE"
    if status == "completed":
        audit_event = "TOWER_RUN_COMPLETE"
    elif status == "failed":
        audit_event = "TOWER_RUN_FAILED"
    audit_log(
        db,
        AUDIT_EVENT_TYPES.get("TOWER_BATTLE", "audit.tower.battle"),
        user_id=int(run["user_id"]),
        action_key="tower.battle",
        entity_type="tower_run",
        entity_id=int(run_id),
        payload={
            "user_id": int(run["user_id"]),
            "run_id": int(run_id),
            "floor": floor,
            "robot_instance_id": robot_id,
            "enemy_key": enemy.get("key"),
            "result": result,
            "reached_floor": int(reached_floor),
            "previous_best_floor": int(record_result.get("previous_best_floor") or 0),
            "status": status,
            "environment_key": run["environment_key"],
        },
    )
    if audit_event != "TOWER_BATTLE":
        audit_log(
            db,
            AUDIT_EVENT_TYPES.get(audit_event, f"audit.tower.run.{status}"),
            user_id=int(run["user_id"]),
            action_key=f"tower.run.{status}",
            entity_type="tower_run",
            entity_id=int(run_id),
            payload={
                "user_id": int(run["user_id"]),
                "run_id": int(run_id),
                "floor": floor,
                "robot_instance_id": robot_id,
                "enemy_key": enemy.get("key"),
                "result": result,
                "reached_floor": int(reached_floor),
                "previous_best_floor": int(record_result.get("previous_best_floor") or 0),
                "status": status,
                "environment_key": run["environment_key"],
            },
        )
    if record_result.get("best_updated") or record_result.get("weekly_updated"):
        audit_log(
            db,
            AUDIT_EVENT_TYPES.get("TOWER_RECORD_UPDATE", "audit.tower.record.update"),
            user_id=int(run["user_id"]),
            action_key="tower.record.update",
            entity_type="tower_run",
            entity_id=int(run_id),
            payload={
                "user_id": int(run["user_id"]),
                "run_id": int(run_id),
                "floor": floor,
                "robot_instance_id": robot_id,
                "enemy_key": enemy.get("key"),
                "result": result,
                "reached_floor": int(reached_floor),
                "previous_best_floor": int(record_result.get("previous_best_floor") or 0),
                "status": status,
                "environment_key": run["environment_key"],
            },
        )
    return {
        "ok": True,
        "run_id": int(run_id),
        "battle_id": int(battle_id),
        "floor": floor,
        "result": result,
        "win": win,
        "status": status,
        "reached_floor": int(reached_floor),
        "enemy": scaled_enemy,
        "battle": battle,
        "turn_logs": turn_logs,
        "record": record_result,
        "rewards": reward_result,
        "cooling": cooling_result,
    }


def abandon_tower_run(db, run_id, user_id, *, now_text=None):
    run = get_tower_run(db, int(run_id), int(user_id))
    if not run:
        return {"ok": False, "reason": "run_not_found"}
    if str(run["status"]) != "active":
        return {"ok": False, "reason": "run_not_active", "run": run}
    now = now_text or datetime.now(timezone.utc).isoformat()
    db.execute(
        """
        UPDATE tower_runs
        SET status = 'abandoned', ended_at = ?, updated_at = ?,
            result_summary_json = ?
        WHERE id = ? AND user_id = ?
        """,
        (
            now,
            now,
            json.dumps({"abandoned": True, "reached_floor": int(run["reached_floor"] or 0)}, ensure_ascii=False),
            int(run_id),
            int(user_id),
        ),
    )
    audit_log(
        db,
        AUDIT_EVENT_TYPES.get("TOWER_RUN_ABANDON", "audit.tower.run.abandon"),
        user_id=int(user_id),
        action_key="tower.run.abandon",
        entity_type="tower_run",
        entity_id=int(run_id),
        payload={
            "user_id": int(user_id),
            "run_id": int(run_id),
            "reached_floor": int(run["reached_floor"] or 0),
            "current_floor": int(run["current_floor"] or 1),
            "environment_key": run["environment_key"],
        },
    )
    return {"ok": True, "run_id": int(run_id)}


def _insert_world_tower_event(db, event_type, user_id, payload):
    db.execute(
        """
        INSERT INTO world_events_log (created_at, event_type, payload_json, user_id, action_key, entity_type, entity_id)
        VALUES (?, ?, ?, ?, ?, 'tower_run', ?)
        """,
        (
            int(time.time()),
            str(event_type),
            json.dumps(payload or {}, ensure_ascii=False),
            int(user_id),
            "tower",
            payload.get("run_id") if isinstance(payload, dict) else None,
        ),
    )


def update_tower_record_if_needed(db, user_id, run_id, reached_floor, squad_robot_ids, environment_key, now_text):
    week_key = current_week_key()
    existing = db.execute("SELECT * FROM user_tower_records WHERE user_id = ?", (int(user_id),)).fetchone()
    previous_best = int(existing["best_floor"] or 0) if existing else 0
    existing_week = str(existing["weekly_key"] or "") if existing else ""
    previous_weekly = int(existing["weekly_best_floor"] or 0) if existing and existing_week == week_key else 0
    best_updated = int(reached_floor) > previous_best
    weekly_updated = int(reached_floor) > previous_weekly
    all_time_leader_before = int(
        db.execute(
            "SELECT COALESCE(MAX(best_floor), 0) AS floor FROM user_tower_records WHERE user_id != ?",
            (int(user_id),),
        ).fetchone()["floor"]
        or 0
    )
    weekly_leader_before = int(
        db.execute(
            "SELECT COALESCE(MAX(weekly_best_floor), 0) AS floor FROM user_tower_records WHERE weekly_key = ? AND user_id != ?",
            (week_key, int(user_id)),
        ).fetchone()["floor"]
        or 0
    )
    if not existing:
        db.execute(
            """
            INSERT INTO user_tower_records
            (user_id, best_floor, best_run_id, best_squad_robot_1_id, best_squad_robot_2_id, best_squad_robot_3_id,
             best_recorded_at, weekly_key, weekly_best_floor, weekly_best_run_id, weekly_best_recorded_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(user_id),
                int(reached_floor),
                int(run_id),
                int(squad_robot_ids[0]),
                int(squad_robot_ids[1]),
                int(squad_robot_ids[2]),
                now_text,
                week_key,
                int(reached_floor),
                int(run_id),
                now_text,
                now_text,
                now_text,
            ),
        )
        best_updated = int(reached_floor) > 0
        weekly_updated = int(reached_floor) > 0
    elif best_updated or weekly_updated or existing_week != week_key:
        best_floor = int(reached_floor) if best_updated else previous_best
        best_run_id = int(run_id) if best_updated else existing["best_run_id"]
        best_at = now_text if best_updated else existing["best_recorded_at"]
        weekly_floor = int(reached_floor) if weekly_updated or existing_week != week_key else previous_weekly
        weekly_run_id = int(run_id) if weekly_updated or existing_week != week_key else existing["weekly_best_run_id"]
        weekly_at = now_text if weekly_updated or existing_week != week_key else existing["weekly_best_recorded_at"]
        db.execute(
            """
            UPDATE user_tower_records
            SET best_floor = ?, best_run_id = ?, best_squad_robot_1_id = ?, best_squad_robot_2_id = ?,
                best_squad_robot_3_id = ?, best_recorded_at = ?, weekly_key = ?, weekly_best_floor = ?,
                weekly_best_run_id = ?, weekly_best_recorded_at = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (
                int(best_floor),
                best_run_id,
                int(squad_robot_ids[0]),
                int(squad_robot_ids[1]),
                int(squad_robot_ids[2]),
                best_at,
                week_key,
                int(weekly_floor),
                weekly_run_id,
                weekly_at,
                now_text,
                int(user_id),
            ),
        )
    payload = {
        "user_id": int(user_id),
        "run_id": int(run_id),
        "reached_floor": int(reached_floor),
        "previous_best_floor": int(previous_best),
        "weekly_key": week_key,
        "environment_key": environment_key,
        "environment_display_name": TOWER_ENVIRONMENT_BY_KEY.get(str(environment_key or ""), TOWER_ENVIRONMENTS[0])["display_name"],
        "squad_robot_ids": [int(x) for x in squad_robot_ids],
    }
    if best_updated:
        _insert_world_tower_event(db, TOWER_WORLD_BEST_EVENT, int(user_id), payload)
    if int(reached_floor) > 0 and int(reached_floor) % TOWER_BOSS_FLOOR_INTERVAL == 0:
        _insert_world_tower_event(db, TOWER_WORLD_MILESTONE_EVENT, int(user_id), payload)
    if weekly_updated and int(reached_floor) > weekly_leader_before:
        _insert_world_tower_event(db, TOWER_WORLD_WEEKLY_LEADER_EVENT, int(user_id), payload)
    if best_updated and int(reached_floor) > all_time_leader_before:
        _insert_world_tower_event(db, TOWER_WORLD_ALL_TIME_LEADER_EVENT, int(user_id), payload)
    return {
        "best_updated": bool(best_updated),
        "weekly_updated": bool(weekly_updated),
        "previous_best_floor": int(previous_best),
        "previous_weekly_best_floor": int(previous_weekly),
        "weekly_key": week_key,
    }


def grant_tower_rewards_if_needed(db, user_id, run_id, reached_floor, now_text):
    if int(reached_floor or 0) < 10:
        return {"granted": []}
    reward_key = "tower_floor_10"
    inserted = db.execute(
        """
        INSERT OR IGNORE INTO tower_reward_grants (user_id, reward_key, reward_type, source_run_id, granted_at)
        VALUES (?, ?, 'badge', ?, ?)
        """,
        (int(user_id), reward_key, int(run_id), now_text),
    ).rowcount
    audit_log(
        db,
        AUDIT_EVENT_TYPES.get(
            "TOWER_REWARD_GRANT" if inserted else "TOWER_REWARD_SKIP_DUPLICATE",
            "audit.tower.reward.grant" if inserted else "audit.tower.reward.skip_duplicate",
        ),
        user_id=int(user_id),
        action_key="tower.reward.grant" if inserted else "tower.reward.skip_duplicate",
        entity_type="tower_run",
        entity_id=int(run_id),
        payload={"user_id": int(user_id), "run_id": int(run_id), "reward_key": reward_key, "reached_floor": int(reached_floor)},
    )
    return {"granted": [reward_key] if inserted else []}


def get_tower_run_battles(db, run_id):
    return db.execute(
        """
        SELECT *
        FROM tower_run_battles
        WHERE run_id = ?
        ORDER BY floor ASC, id ASC
        """,
        (int(run_id),),
    ).fetchall()


def get_tower_rankings(db, *, weekly_key=None, limit=20):
    week_key = weekly_key or current_week_key()
    weekly = db.execute(
        """
        SELECT r.*, u.username, u.display_name
        FROM user_tower_records r
        JOIN users u ON u.id = r.user_id
        WHERE r.weekly_key = ? AND r.weekly_best_floor > 0
        ORDER BY r.weekly_best_floor DESC, r.weekly_best_recorded_at ASC
        LIMIT ?
        """,
        (week_key, int(limit)),
    ).fetchall()
    all_time = db.execute(
        """
        SELECT r.*, u.username, u.display_name
        FROM user_tower_records r
        JOIN users u ON u.id = r.user_id
        WHERE r.best_floor > 0
        ORDER BY r.best_floor DESC, r.best_recorded_at ASC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    low_plus = db.execute(
        """
        SELECT tr.*, u.username, u.display_name
        FROM tower_runs tr
        JOIN users u ON u.id = tr.user_id
        WHERE tr.weekly_key = ?
          AND tr.reached_floor > 0
          AND tr.squad_plus_total <= ?
          AND tr.status IN ('completed', 'failed')
        ORDER BY tr.reached_floor DESC, tr.squad_plus_total ASC, tr.ended_at ASC
        LIMIT ?
        """,
        (week_key, int(TOWER_LOW_PLUS_LIMIT), int(limit)),
    ).fetchall()
    return {
        "weekly_key": week_key,
        "weekly": weekly,
        "all_time": all_time,
        "low_plus": low_plus,
        "low_plus_limit": int(TOWER_LOW_PLUS_LIMIT),
    }
