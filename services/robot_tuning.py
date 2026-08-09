import hashlib
import math
import sqlite3
import time


TUNING_STAT_KEYS = ("hp", "atk", "def", "spd", "acc", "cri")
TUNING_STAT_LABELS = {
    "hp": "耐久",
    "atk": "攻撃",
    "def": "防御",
    "spd": "素早さ",
    "acc": "命中",
    "cri": "会心",
}
PER_STAT_LEVEL_CAP = 8
TOTAL_LEVEL_CAP = 24
XP_PER_LEVEL = 10
DAILY_GAIN_LIMIT = 10
TUNING_BONUS_RATE = 0.0075
RESET_COOLDOWN_SECONDS = 7 * 24 * 60 * 60
RESET_COST_COINS = 500


AREA_TUNING_WEIGHTS = {
    "layer_1": {"hp": 50, "def": 50},
    "layer_2": {"acc": 50, "def": 50},
    "layer_2_mist": {"acc": 70, "def": 20, "hp": 10},
    "layer_2_rush": {"spd": 60, "cri": 40},
    "layer_3": {"atk": 50, "hp": 50},
    "layer_4_forge": {"hp": 55, "def": 45},
    "layer_4_haze": {"acc": 60, "def": 25, "hp": 15},
    "layer_4_burst": {"atk": 50, "cri": 40, "spd": 10},
    "layer_4_final": {key: 1 for key in TUNING_STAT_KEYS},
    "layer_5_reboot": {"hp": 35, "acc": 35, "def": 30},
    "layer_5_overdrive": {"atk": 40, "cri": 35, "spd": 25},
    "layer_5_final": {key: 1 for key in TUNING_STAT_KEYS},
    "layer_6_rebuild": {"hp": 38, "def": 34, "atk": 18, "acc": 10},
    "layer_6_core": {"spd": 36, "acc": 34, "atk": 20, "cri": 10},
    "layer_6_final": {key: 1 for key in TUNING_STAT_KEYS},
    "layer_7_echo": {"spd": 36, "acc": 34, "def": 18, "atk": 12},
    "layer_7_chaos": {"atk": 38, "cri": 34, "spd": 18, "acc": 10},
    "layer_7_final": {key: 1 for key in TUNING_STAT_KEYS},
}


def ensure_robot_tuning_schema(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_tuning_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            robot_instance_id INTEGER NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            hp_level INTEGER NOT NULL DEFAULT 0,
            hp_xp INTEGER NOT NULL DEFAULT 0,
            atk_level INTEGER NOT NULL DEFAULT 0,
            atk_xp INTEGER NOT NULL DEFAULT 0,
            def_level INTEGER NOT NULL DEFAULT 0,
            def_xp INTEGER NOT NULL DEFAULT 0,
            spd_level INTEGER NOT NULL DEFAULT 0,
            spd_xp INTEGER NOT NULL DEFAULT 0,
            acc_level INTEGER NOT NULL DEFAULT 0,
            acc_xp INTEGER NOT NULL DEFAULT 0,
            cri_level INTEGER NOT NULL DEFAULT 0,
            cri_xp INTEGER NOT NULL DEFAULT 0,
            unassigned_points INTEGER NOT NULL DEFAULT 0,
            last_free_reset_at INTEGER,
            last_tuning_gain_at INTEGER,
            completed_at INTEGER,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            FOREIGN KEY (robot_instance_id) REFERENCES robot_instances(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_daily_tuning_progress (
            user_id INTEGER NOT NULL,
            day_key TEXT NOT NULL,
            eligible_win_count INTEGER NOT NULL DEFAULT 0,
            cap_logged_at INTEGER,
            last_gain_at INTEGER,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (user_id, day_key),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_tuning_gain_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            robot_instance_id INTEGER NOT NULL,
            area_key TEXT NOT NULL,
            stat_key TEXT,
            source_battle_id INTEGER UNIQUE,
            source_request_id TEXT,
            day_key TEXT NOT NULL,
            granted INTEGER NOT NULL DEFAULT 0,
            level_before INTEGER NOT NULL DEFAULT 0,
            level_after INTEGER NOT NULL DEFAULT 0,
            xp_before INTEGER NOT NULL DEFAULT 0,
            xp_after INTEGER NOT NULL DEFAULT 0,
            reason TEXT,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (robot_instance_id) REFERENCES robot_instances(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )


def _now(now_ts=None):
    return int(now_ts if now_ts is not None else time.time())


def get_tuning_area_weights(area_key):
    return dict(AREA_TUNING_WEIGHTS.get(str(area_key or "").strip()) or {})


def tuning_area_weight_labels(area_key):
    weights = get_tuning_area_weights(area_key)
    return [TUNING_STAT_LABELS[key] for key, _ in sorted(weights.items(), key=lambda item: (-int(item[1]), item[0]))]


def get_or_create_tuning_state(db, robot_instance_id, user_id, now_ts=None):
    now = _now(now_ts)
    db.execute(
        """
        INSERT INTO robot_tuning_states (robot_instance_id, user_id, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(robot_instance_id) DO NOTHING
        """,
        (int(robot_instance_id), int(user_id), now, now),
    )
    return db.execute(
        "SELECT * FROM robot_tuning_states WHERE robot_instance_id = ? LIMIT 1",
        (int(robot_instance_id),),
    ).fetchone()


def state_levels(state):
    if not state:
        return {key: 0 for key in TUNING_STAT_KEYS}
    return {key: max(0, min(PER_STAT_LEVEL_CAP, int(state[f"{key}_level"] or 0))) for key in TUNING_STAT_KEYS}


def state_xp(state):
    if not state:
        return {key: 0 for key in TUNING_STAT_KEYS}
    return {key: max(0, min(XP_PER_LEVEL - 1, int(state[f"{key}_xp"] or 0))) for key in TUNING_STAT_KEYS}


def total_tuning_level(state_or_levels):
    levels = state_or_levels if isinstance(state_or_levels, dict) else state_levels(state_or_levels)
    return sum(max(0, int(levels.get(key) or 0)) for key in TUNING_STAT_KEYS)


def _candidate_weights(area_key, levels):
    weights = get_tuning_area_weights(area_key)
    return {
        key: int(weight)
        for key, weight in weights.items()
        if key in TUNING_STAT_KEYS and int(weight) > 0 and int(levels.get(key) or 0) < PER_STAT_LEVEL_CAP
    }


def pick_tuning_stat(area_key, levels, *, seed_parts):
    candidates = _candidate_weights(area_key, levels)
    if not candidates:
        return None
    total = sum(candidates.values())
    seed = "|".join(str(part) for part in seed_parts)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    roll = int(digest[:12], 16) % total
    cursor = 0
    for key, weight in sorted(candidates.items()):
        cursor += int(weight)
        if roll < cursor:
            return key
    return next(iter(sorted(candidates.keys())))


def apply_tuning_bonus(stats, state_or_levels):
    levels = state_or_levels if isinstance(state_or_levels, dict) else state_levels(state_or_levels)
    adjusted = {key: int(value or 0) for key, value in dict(stats or {}).items()}
    rows = []
    for key in TUNING_STAT_KEYS:
        base = int(adjusted.get(key) or 0)
        level = max(0, min(PER_STAT_LEVEL_CAP, int(levels.get(key) or 0)))
        bonus = 0
        if base > 0 and level > 0:
            bonus = max(1, math.floor(base * level * TUNING_BONUS_RATE))
            adjusted[key] = base + bonus
        rows.append(
            {
                "key": key,
                "label": TUNING_STAT_LABELS[key],
                "level": level,
                "base": base,
                "bonus": bonus,
                "after": int(adjusted.get(key) or 0),
                "percent": level * TUNING_BONUS_RATE * 100.0,
            }
        )
    return adjusted, rows


def tuning_summary(state, *, base_stats=None):
    levels = state_levels(state)
    xp = state_xp(state)
    rows = []
    base_stats = dict(base_stats or {})
    for key in TUNING_STAT_KEYS:
        base = int(base_stats.get(key) or 0)
        level = int(levels[key])
        bonus = max(1, math.floor(base * level * TUNING_BONUS_RATE)) if base > 0 and level > 0 else 0
        rows.append(
            {
                "key": key,
                "label": TUNING_STAT_LABELS[key],
                "level": level,
                "xp": int(xp[key]),
                "xp_per_level": XP_PER_LEVEL,
                "percent": level * TUNING_BONUS_RATE * 100.0,
                "base": base,
                "after": base + bonus,
                "bonus": bonus,
            }
        )
    top_rows = sorted(rows, key=lambda row: (-int(row["level"]), row["key"]))[:3]
    return {
        "total_level": total_tuning_level(levels),
        "total_cap": TOTAL_LEVEL_CAP,
        "per_stat_cap": PER_STAT_LEVEL_CAP,
        "unassigned_points": int(state["unassigned_points"] or 0) if state else 0,
        "last_free_reset_at": int(state["last_free_reset_at"] or 0) if state and state["last_free_reset_at"] else None,
        "completed_at": int(state["completed_at"] or 0) if state and state["completed_at"] else None,
        "rows": rows,
        "top_rows": [row for row in top_rows if int(row["level"]) > 0],
    }


def grant_tuning_xp(
    db,
    *,
    user_id,
    robot_instance_id,
    area_key,
    won,
    day_key,
    source_battle_id,
    source_request_id=None,
    is_admin=False,
    feature_open=False,
    now_ts=None,
):
    now = _now(now_ts)
    area_key = str(area_key or "").strip()
    if not won:
        return {"granted": False, "reason": "not_win"}
    if is_admin:
        return {"granted": False, "reason": "admin"}
    if not feature_open:
        return {"granted": False, "reason": "feature_closed"}
    if area_key == "layer_1" or not get_tuning_area_weights(area_key):
        return {"granted": False, "reason": "area_not_eligible"}
    daily = db.execute(
        """
        SELECT * FROM user_daily_tuning_progress
        WHERE user_id = ? AND day_key = ?
        LIMIT 1
        """,
        (int(user_id), str(day_key)),
    ).fetchone()
    if not daily:
        db.execute(
            """
            INSERT INTO user_daily_tuning_progress
                (user_id, day_key, eligible_win_count, created_at, updated_at)
            VALUES (?, ?, 0, ?, ?)
            """,
            (int(user_id), str(day_key), now, now),
        )
        daily_count = 0
        cap_logged_at = None
    else:
        daily_count = int(daily["eligible_win_count"] or 0)
        cap_logged_at = daily["cap_logged_at"] if "cap_logged_at" in daily.keys() else None
    if daily_count >= DAILY_GAIN_LIMIT:
        return {
            "granted": False,
            "reason": "daily_cap",
            "daily_gain_count": daily_count,
            "daily_limit": DAILY_GAIN_LIMIT,
            "cap_audit_needed": not bool(cap_logged_at),
        }
    state = get_or_create_tuning_state(db, robot_instance_id, user_id, now_ts=now)
    levels = state_levels(state)
    if total_tuning_level(levels) >= TOTAL_LEVEL_CAP:
        return {"granted": False, "reason": "total_cap", "message": "機体調整は上限に達しています"}
    stat_key = pick_tuning_stat(
        area_key,
        levels,
        seed_parts=(int(user_id), int(robot_instance_id), area_key, str(day_key), int(source_battle_id or 0), str(source_request_id or "")),
    )
    if not stat_key:
        return {"granted": False, "reason": "stat_cap"}
    try:
        cursor = db.execute(
            """
            INSERT INTO robot_tuning_gain_events
                (user_id, robot_instance_id, area_key, stat_key, source_battle_id, source_request_id,
                 day_key, granted, level_before, level_after, xp_before, xp_after, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 'pending', ?)
            """,
            (
                int(user_id),
                int(robot_instance_id),
                area_key,
                stat_key,
                int(source_battle_id) if source_battle_id is not None else None,
                str(source_request_id or ""),
                str(day_key),
                now,
            ),
        )
        gain_event_id = int(cursor.lastrowid)
    except sqlite3.IntegrityError:
        return {"granted": False, "reason": "duplicate"}
    xp_col = f"{stat_key}_xp"
    level_col = f"{stat_key}_level"
    xp_before = int(state[xp_col] or 0)
    level_before = int(state[level_col] or 0)
    xp_after = xp_before + 1
    level_after = level_before
    leveled_up = False
    if xp_after >= XP_PER_LEVEL and level_before < PER_STAT_LEVEL_CAP:
        level_after = min(PER_STAT_LEVEL_CAP, level_before + 1)
        xp_after = 0
        leveled_up = True
    completed = total_tuning_level({**levels, stat_key: level_after}) >= TOTAL_LEVEL_CAP
    completed_at_expr = "completed_at"
    completed_at_value = None
    if completed and not state["completed_at"]:
        completed_at_expr = "?"
        completed_at_value = now
    params = [level_after, xp_after, now, now, int(robot_instance_id)]
    if completed_at_value is not None:
        params.insert(3, completed_at_value)
    db.execute(
        f"""
        UPDATE robot_tuning_states
        SET {level_col} = ?,
            {xp_col} = ?,
            last_tuning_gain_at = ?,
            completed_at = {completed_at_expr},
            updated_at = ?
        WHERE robot_instance_id = ?
        """,
        params,
    )
    db.execute(
        """
        UPDATE user_daily_tuning_progress
        SET eligible_win_count = eligible_win_count + 1,
            last_gain_at = ?,
            updated_at = ?
        WHERE user_id = ? AND day_key = ?
        """,
        (now, now, int(user_id), str(day_key)),
    )
    db.execute(
        """
        UPDATE robot_tuning_gain_events
        SET granted = 1,
            level_before = ?,
            level_after = ?,
            xp_before = ?,
            xp_after = ?,
            reason = NULL
        WHERE id = ?
        """,
        (level_before, level_after, xp_before, xp_after, gain_event_id),
    )
    daily_after = daily_count + 1
    return {
        "granted": True,
        "reason": "granted",
        "stat_key": stat_key,
        "stat_label": TUNING_STAT_LABELS[stat_key],
        "level_before": level_before,
        "level_after": level_after,
        "xp_before": xp_before,
        "xp_after": xp_after,
        "leveled_up": leveled_up,
        "daily_gain_count": daily_after,
        "daily_limit": DAILY_GAIN_LIMIT,
        "daily_cap_reached": daily_after >= DAILY_GAIN_LIMIT,
        "completed": bool(completed),
        "message": (
            f"{TUNING_STAT_LABELS[stat_key]} Lv{level_after}へ上昇"
            if leveled_up
            else f"{TUNING_STAT_LABELS[stat_key]}の調整経験 +1"
        ),
    }


def mark_daily_cap_logged(db, user_id, day_key, now_ts=None):
    now = _now(now_ts)
    db.execute(
        """
        UPDATE user_daily_tuning_progress
        SET cap_logged_at = COALESCE(cap_logged_at, ?),
            updated_at = ?
        WHERE user_id = ? AND day_key = ?
        """,
        (now, now, int(user_id), str(day_key)),
    )


def reset_tuning_state(db, *, user_id, robot_instance_id, now_ts=None):
    now = _now(now_ts)
    state = get_or_create_tuning_state(db, robot_instance_id, user_id, now_ts=now)
    levels = state_levels(state)
    returned = total_tuning_level(levels)
    free_available = not state["last_free_reset_at"] or (now - int(state["last_free_reset_at"] or 0)) >= RESET_COOLDOWN_SECONDS
    cost = 0 if free_available else RESET_COST_COINS
    user = db.execute("SELECT coins FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if cost > 0 and (not user or int(user["coins"] or 0) < cost):
        return {"ok": False, "reason": "not_enough_coins", "cost": cost, "free": False, "returned_points": returned}
    if cost > 0:
        db.execute("UPDATE users SET coins = coins - ? WHERE id = ?", (cost, int(user_id)))
    set_cols = []
    for key in TUNING_STAT_KEYS:
        set_cols.append(f"{key}_level = 0")
        set_cols.append(f"{key}_xp = 0")
    free_sql = ", last_free_reset_at = ?" if free_available else ""
    params = [returned, now]
    if free_available:
        params.append(now)
    params.append(int(robot_instance_id))
    db.execute(
        f"""
        UPDATE robot_tuning_states
        SET {", ".join(set_cols)},
            unassigned_points = unassigned_points + ?,
            completed_at = NULL,
            updated_at = ?
            {free_sql}
        WHERE robot_instance_id = ?
        """,
        params,
    )
    return {"ok": True, "cost": cost, "free": free_available, "returned_points": returned}


def allocate_tuning_points(db, *, user_id, robot_instance_id, allocations, now_ts=None):
    now = _now(now_ts)
    state = get_or_create_tuning_state(db, robot_instance_id, user_id, now_ts=now)
    clean = {}
    for key in TUNING_STAT_KEYS:
        try:
            value = int(allocations.get(key, 0) or 0)
        except (TypeError, ValueError):
            return {"ok": False, "reason": "invalid_value", "stat_key": key}
        if value < 0:
            return {"ok": False, "reason": "negative", "stat_key": key}
        clean[key] = value
    levels = state_levels(state)
    unassigned = int(state["unassigned_points"] or 0)
    spend = sum(clean.values())
    if spend > unassigned:
        return {"ok": False, "reason": "over_unassigned", "unassigned_points": unassigned}
    for key, value in clean.items():
        if int(levels[key]) + int(value) > PER_STAT_LEVEL_CAP:
            return {"ok": False, "reason": "per_stat_cap", "stat_key": key}
    if total_tuning_level(levels) + spend > TOTAL_LEVEL_CAP:
        return {"ok": False, "reason": "total_cap"}
    set_cols = []
    params = []
    for key, value in clean.items():
        if value:
            set_cols.append(f"{key}_level = {key}_level + ?")
            params.append(int(value))
    if not set_cols:
        return {"ok": True, "spent": 0, "unassigned_points": unassigned}
    params.extend([spend, now, int(robot_instance_id)])
    db.execute(
        f"""
        UPDATE robot_tuning_states
        SET {", ".join(set_cols)},
            unassigned_points = unassigned_points - ?,
            updated_at = ?
        WHERE robot_instance_id = ?
        """,
        params,
    )
    return {"ok": True, "spent": spend, "unassigned_points": unassigned - spend, "allocations": clean}
