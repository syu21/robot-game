import hashlib
import json
import time

from services.lab_level import grant_lab_exp, lab_level_view


EVENT_EXPLORE_END = "audit.explore.end"
EVENT_DROP = "audit.drop"
EVENT_FUSE = "audit.fuse"
EVENT_PART_EVOLVE = "audit.part.evolve"
EVENT_BUILD_CONFIRM = "audit.build.confirm"
EVENT_BOSS_ENCOUNTER = "audit.boss.encounter"
EVENT_BOSS_DEFEAT = "audit.boss.defeat"

RESEARCH_AUDIT_EVENTS = {
    "assign": "audit.research.task.assign",
    "progress": "audit.research.task.progress",
    "complete": "audit.research.task.complete",
    "claim": "audit.research.task.claim",
    "hold": "audit.research.task.hold",
    "level_up": "audit.research.level.up",
    "discovery": "audit.research.discovery",
    "personal_record": "audit.personal_record.update",
}

RESEARCH_TASK_EVENTS = {
    EVENT_EXPLORE_END,
    EVENT_DROP,
    EVENT_FUSE,
    EVENT_PART_EVOLVE,
    EVENT_BUILD_CONFIRM,
}

RESEARCH_COLLECTION_EVENTS = {
    EVENT_EXPLORE_END,
    EVENT_DROP,
    EVENT_BUILD_CONFIRM,
    EVENT_BOSS_ENCOUNTER,
    EVENT_BOSS_DEFEAT,
}

RESEARCH_DISCOVERY_EXP = {
    "part_model": 1,
    "part_rarity": 1,
    "part_series_complete": 20,
    "enemy_encounter": 1,
    "enemy_defeat": 3,
    "boss_encounter": 5,
    "boss_defeat": 20,
    "first_design": 2,
}

PART_TYPE_LABELS = {
    "head": "ヘッド",
    "r_arm": "右アーム",
    "l_arm": "左アーム",
    "legs": "レッグ",
    "decor": "装飾",
}

RECORD_LABELS = {
    "area_fastest_win_turns": "エリア最短勝利",
    "area_max_damage_dealt": "最大与ダメージ",
    "area_min_damage_taken": "最小被ダメージ",
    "area_longest_survival_turns": "最長戦闘ターン",
    "boss_fastest_win_turns": "ボス最短勝利",
    "boss_min_damage_taken": "ボス最小被ダメージ",
    "build_highest_power": "設計時最高パワー",
}

RESEARCH_TASK_SEEDS = [
    {
        "task_key": "basic_layer1_explore_3",
        "category": "basic",
        "title": "第1層の廃品調査",
        "description": "第1層で廃品反応を3回調べる。",
        "difficulty": 1,
        "condition_type": "explore_area",
        "condition_payload": {"area_key": "layer_1"},
        "reward_exp": 30,
        "min_layer": 1,
    },
    {
        "task_key": "basic_any_win_3",
        "category": "basic",
        "title": "通常戦闘データ収集",
        "description": "通常探索で3回勝利する。",
        "difficulty": 1,
        "condition_type": "win_any",
        "condition_payload": {},
        "reward_exp": 35,
        "min_layer": 1,
    },
    {
        "task_key": "basic_part_drop_1",
        "category": "basic",
        "title": "回収部品の初期解析",
        "description": "パーツを1個入手する。",
        "difficulty": 1,
        "condition_type": "part_drop",
        "condition_payload": {},
        "reward_exp": 25,
        "min_layer": 1,
    },
    {
        "task_key": "build_change_1",
        "category": "build",
        "title": "試作機の再調整",
        "description": "ロボの編成を1回確定する。",
        "difficulty": 1,
        "condition_type": "build_confirm",
        "condition_payload": {},
        "reward_exp": 35,
        "min_layer": 1,
    },
    {
        "task_key": "build_appliance_win_2",
        "category": "build",
        "title": "家電シリーズ実地試験",
        "description": "家電シリーズを含む構成で2回勝利する。",
        "difficulty": 2,
        "condition_type": "win_series",
        "condition_payload": {"series_key": "appliance"},
        "reward_exp": 45,
        "min_layer": 1,
    },
    {
        "task_key": "special_fast_win_5",
        "category": "special",
        "title": "短期決戦ログ",
        "description": "5ターン以内に1回勝利する。",
        "difficulty": 2,
        "condition_type": "fast_win",
        "condition_payload": {"turns": 5},
        "reward_exp": 45,
        "min_layer": 1,
    },
    {
        "task_key": "special_layer2_win_3",
        "category": "special",
        "title": "第2層適応試験",
        "description": "第2層で3回勝利する。",
        "difficulty": 2,
        "condition_type": "win_area",
        "condition_payload": {"area_key": "layer_2"},
        "reward_exp": 55,
        "min_layer": 2,
    },
    {
        "task_key": "special_boss_defeat_1",
        "category": "special",
        "title": "ボス反応の制圧",
        "description": "ボスを1体撃破する。",
        "difficulty": 3,
        "condition_type": "boss_win",
        "condition_payload": {},
        "reward_exp": 80,
        "min_layer": 1,
    },
]

CATEGORY_LABELS = {
    "basic": "基礎研究",
    "build": "構成研究",
    "special": "特別研究",
}


def _now():
    return int(time.time())


def _json(data):
    return json.dumps(data or {}, ensure_ascii=False)


def _audit(db, event_type, user_id, payload=None, entity_type=None, entity_id=None, delta_count=None):
    db.execute(
        """
        INSERT INTO world_events_log
        (created_at, event_type, payload_json, user_id, action_key, entity_type, entity_id, delta_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _now(),
            str(event_type),
            _json(payload),
            int(user_id),
            str(event_type).replace("audit.", ""),
            entity_type,
            entity_id,
            delta_count,
        ),
    )


def seed_research_task_definitions(db):
    for task in RESEARCH_TASK_SEEDS:
        db.execute(
            """
            INSERT INTO research_task_definitions
                (task_key, category, title, description, difficulty, condition_type,
                 condition_payload_json, reward_exp, min_layer, required_feature, is_active, version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 1, 1)
            ON CONFLICT(task_key) DO UPDATE SET
                category = excluded.category,
                title = excluded.title,
                description = excluded.description,
                difficulty = excluded.difficulty,
                condition_type = excluded.condition_type,
                condition_payload_json = excluded.condition_payload_json,
                reward_exp = excluded.reward_exp,
                min_layer = excluded.min_layer,
                version = excluded.version
            """,
            (
                task["task_key"],
                task["category"],
                task["title"],
                task["description"],
                int(task["difficulty"]),
                task["condition_type"],
                _json(task.get("condition_payload")),
                int(task["reward_exp"]),
                int(task["min_layer"]),
            ),
        )


def ensure_research_profile(db, user_id):
    user = db.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if not user:
        return None
    row = db.execute("SELECT * FROM user_research_profiles WHERE user_id = ?", (int(user_id),)).fetchone()
    if not row:
        db.execute(
            """
            INSERT OR IGNORE INTO user_research_profiles
            (user_id, research_level, research_exp, lifetime_research_exp, active_task_slots, created_at, updated_at)
            VALUES (?, ?, ?, ?, 3, ?, ?)
            """,
            (
                int(user_id),
                int(user["lab_level"] if "lab_level" in user.keys() else 1) or 1,
                int(user["lab_exp"] if "lab_exp" in user.keys() else 0) or 0,
                int(user["lab_total_exp"] if "lab_total_exp" in user.keys() else 0) or 0,
                _now(),
                _now(),
            ),
        )
        row = db.execute("SELECT * FROM user_research_profiles WHERE user_id = ?", (int(user_id),)).fetchone()
    return row


def sync_research_profile_from_user(db, user_id):
    user = db.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if not user:
        return None
    ensure_research_profile(db, user_id)
    db.execute(
        """
        UPDATE user_research_profiles
        SET research_level = ?,
            research_exp = ?,
            lifetime_research_exp = ?,
            updated_at = ?
        WHERE user_id = ?
        """,
        (
            int(user["lab_level"] if "lab_level" in user.keys() else 1) or 1,
            int(user["lab_exp"] if "lab_exp" in user.keys() else 0) or 0,
            int(user["lab_total_exp"] if "lab_total_exp" in user.keys() else 0) or 0,
            _now(),
            int(user_id),
        ),
    )
    return db.execute("SELECT * FROM user_research_profiles WHERE user_id = ?", (int(user_id),)).fetchone()


def _table_columns(db, table_name):
    return {row["name"] for row in db.execute(f"PRAGMA table_info({table_name})").fetchall()}


def ensure_research_phase2_schema(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_discoveries (
            user_id INTEGER NOT NULL,
            discovery_type TEXT NOT NULL,
            discovery_key TEXT NOT NULL,
            first_discovered_at INTEGER NOT NULL,
            source_key TEXT,
            metadata_json TEXT,
            PRIMARY KEY (user_id, discovery_type, discovery_key)
        )
        """
    )
    columns = _table_columns(db, "user_discoveries")
    for name, ddl in {
        "first_source_key": "ALTER TABLE user_discoveries ADD COLUMN first_source_key TEXT",
        "first_request_id": "ALTER TABLE user_discoveries ADD COLUMN first_request_id TEXT",
        "created_at": "ALTER TABLE user_discoveries ADD COLUMN created_at INTEGER",
        "updated_at": "ALTER TABLE user_discoveries ADD COLUMN updated_at INTEGER",
    }.items():
        if name not in columns:
            db.execute(ddl)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS research_processed_events (
            user_id INTEGER NOT NULL,
            event_uid TEXT NOT NULL,
            processed_at INTEGER NOT NULL,
            PRIMARY KEY (user_id, event_uid)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_enemy_research_stats (
            user_id INTEGER NOT NULL,
            enemy_key TEXT NOT NULL,
            first_encountered_at INTEGER,
            first_defeated_at INTEGER,
            encounter_count INTEGER NOT NULL DEFAULT 0,
            defeat_count INTEGER NOT NULL DEFAULT 0,
            best_win_turns INTEGER,
            total_damage_taken INTEGER NOT NULL DEFAULT 0,
            last_seen_at INTEGER,
            metadata_json TEXT,
            PRIMARY KEY (user_id, enemy_key)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_boss_research_stats (
            user_id INTEGER NOT NULL,
            boss_key TEXT NOT NULL,
            first_encountered_at INTEGER,
            first_defeated_at INTEGER,
            encounter_count INTEGER NOT NULL DEFAULT 0,
            defeat_count INTEGER NOT NULL DEFAULT 0,
            best_win_turns INTEGER,
            total_damage_taken INTEGER NOT NULL DEFAULT 0,
            last_seen_at INTEGER,
            metadata_json TEXT,
            PRIMARY KEY (user_id, boss_key)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_design_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            robot_instance_id INTEGER,
            loadout_hash TEXT NOT NULL,
            robot_name TEXT,
            head_key TEXT,
            r_arm_key TEXT,
            l_arm_key TEXT,
            legs_key TEXT,
            decor_asset_id INTEGER,
            combat_mode TEXT,
            frame_type TEXT,
            image_path TEXT,
            icon_path TEXT,
            snapshot_json TEXT,
            build_count INTEGER NOT NULL DEFAULT 1,
            first_built_at INTEGER NOT NULL,
            last_built_at INTEGER NOT NULL,
            UNIQUE(user_id, loadout_hash)
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_robot_design_records_user_last ON robot_design_records(user_id, last_built_at)")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_daily_research_stats (
            user_id INTEGER NOT NULL,
            day_key TEXT NOT NULL,
            explore_count INTEGER NOT NULL DEFAULT 0,
            win_count INTEGER NOT NULL DEFAULT 0,
            part_drop_count INTEGER NOT NULL DEFAULT 0,
            enemy_encounter_count INTEGER NOT NULL DEFAULT 0,
            boss_encounter_count INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (user_id, day_key)
        )
        """
    )


def _event_receipt(db, user_id, event_uid):
    if not event_uid:
        return True
    cur = db.execute(
        "INSERT OR IGNORE INTO research_processed_events (user_id, event_uid, processed_at) VALUES (?, ?, ?)",
        (int(user_id), str(event_uid), _now()),
    )
    return int(cur.rowcount or 0) > 0


def _collection_event_uid(event_type, payload, request_id=None, entity_type=None, entity_id=None):
    payload = payload or {}
    result = payload.get("result") or {}
    battle_id = result.get("battle_id") or payload.get("battle_id")
    if battle_id:
        return f"{event_type}:battle:{battle_id}"
    if request_id and entity_id:
        return f"{event_type}:request:{request_id}:entity:{entity_type or ''}:{entity_id}"
    if request_id:
        return f"{event_type}:request:{request_id}"
    if entity_id:
        return f"{event_type}:entity:{entity_type or ''}:{entity_id}"
    return ""


def _part_model_key(part):
    series_key = part["series_key"] if "series_key" in part.keys() else None
    display_name = part["display_name_ja"] if "display_name_ja" in part.keys() else None
    part_type = part["part_type"] if "part_type" in part.keys() else ""
    if series_key and display_name:
        return f"{series_key}:{part_type}:{display_name}"
    return str(part["key"])


def _part_model_label(part):
    display_name = part["display_name_ja"] if "display_name_ja" in part.keys() else None
    return display_name or str(part["key"]).replace("_", " ")


def _discovery_row(db, user_id, discovery_type, discovery_key):
    return db.execute(
        """
        SELECT * FROM user_discoveries
        WHERE user_id = ? AND discovery_type = ? AND discovery_key = ?
        """,
        (int(user_id), str(discovery_type), str(discovery_key)),
    ).fetchone()


def _insert_discovery(db, user_id, discovery_type, discovery_key, source_key=None, request_id=None, metadata=None):
    ensure_research_phase2_schema(db)
    existing = _discovery_row(db, user_id, discovery_type, discovery_key)
    if existing:
        return None
    now_ts = _now()
    db.execute(
        """
        INSERT OR IGNORE INTO user_discoveries
            (user_id, discovery_type, discovery_key, first_discovered_at, source_key,
             first_source_key, first_request_id, metadata_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(user_id),
            str(discovery_type),
            str(discovery_key),
            now_ts,
            source_key,
            source_key,
            request_id,
            _json(metadata),
            now_ts,
            now_ts,
        ),
    )
    if int(db.total_changes or 0) < 0:
        return None
    return {
        "type": str(discovery_type),
        "key": str(discovery_key),
        "label": (metadata or {}).get("label") or str(discovery_key),
        "exp": int(RESEARCH_DISCOVERY_EXP.get(discovery_type, 0)),
    }


def _grant_discovery_exp(db, user_id, discovery):
    if not discovery:
        return None
    amount = int(discovery.get("exp") or 0)
    if amount <= 0:
        return None
    result = grant_lab_exp(
        db,
        int(user_id),
        "research.discovery",
        amount,
        source_entity_type="research_discovery",
        payload={"discovery_type": discovery.get("type"), "discovery_key": discovery.get("key"), "label": discovery.get("label")},
    )
    sync_research_profile_from_user(db, user_id)
    _audit(db, RESEARCH_AUDIT_EVENTS["discovery"], user_id, discovery, entity_type="research_discovery", delta_count=amount)
    return result


def _task_payload(row):
    try:
        return json.loads(row["condition_payload_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def _task_snapshot(row):
    return {
        "task_key": row["task_key"],
        "category": row["category"],
        "category_label": CATEGORY_LABELS.get(row["category"], row["category"]),
        "title": row["title"],
        "description": row["description"],
        "condition_type": row["condition_type"],
        "condition_payload": _task_payload(row),
        "reward_exp": int(row["reward_exp"] or 0),
        "target": _target_for_task(row),
    }


def _target_for_task(row):
    condition_type = str(row["condition_type"] or "")
    payload = _task_payload(row)
    if condition_type in {"part_drop", "build_confirm", "fast_win", "boss_win"}:
        return 1
    if condition_type == "win_series":
        return 2
    if condition_type in {"explore_area", "win_any", "win_area"}:
        return 3
    return int(payload.get("target") or 1)


def _eligible_tasks(db, user_id, category=None):
    user = db.execute("SELECT max_unlocked_layer FROM users WHERE id = ?", (int(user_id),)).fetchone()
    max_layer = int(user["max_unlocked_layer"] or 1) if user else 1
    params = [max_layer]
    where = "WHERE is_active = 1 AND COALESCE(min_layer, 1) <= ?"
    if category:
        where += " AND category = ?"
        params.append(str(category))
    rows = db.execute(
        f"""
        SELECT *
        FROM research_task_definitions
        {where}
        ORDER BY difficulty ASC, task_key ASC
        """,
        tuple(params),
    ).fetchall()
    if not rows:
        return []
    recent = [
        row["task_key"]
        for row in db.execute(
            """
            SELECT task_key
            FROM user_research_tasks
            WHERE user_id = ?
            ORDER BY assigned_at DESC, id DESC
            LIMIT 5
            """,
            (int(user_id),),
        ).fetchall()
    ]
    active = {
        row["task_key"]
        for row in db.execute(
            "SELECT task_key FROM user_research_tasks WHERE user_id = ? AND status IN ('active', 'held', 'completed')",
            (int(user_id),),
        ).fetchall()
    }
    filtered = [row for row in rows if row["task_key"] not in active and row["task_key"] not in recent]
    return filtered or [row for row in rows if row["task_key"] not in active] or rows


def assign_research_task(db, user_id, slot_index, category=None):
    eligible = _eligible_tasks(db, user_id, category=category)
    if not eligible:
        return None
    index = (int(user_id) + int(slot_index or 0) + _now()) % len(eligible)
    definition = eligible[index]
    snapshot = _task_snapshot(definition)
    cur = db.execute(
        """
        INSERT INTO user_research_tasks
            (user_id, task_key, status, slot_index, progress, target, snapshot_json, assigned_at)
        VALUES (?, ?, 'active', ?, 0, ?, ?, ?)
        """,
        (
            int(user_id),
            definition["task_key"],
            int(slot_index),
            int(snapshot["target"]),
            _json(snapshot),
            _now(),
        ),
    )
    _audit(
        db,
        RESEARCH_AUDIT_EVENTS["assign"],
        user_id,
        {"task_id": int(cur.lastrowid), "slot_index": int(slot_index), **snapshot},
        entity_type="research_task",
        entity_id=int(cur.lastrowid),
    )
    return db.execute("SELECT * FROM user_research_tasks WHERE id = ?", (int(cur.lastrowid),)).fetchone()


def ensure_research_board(db, user_id):
    seed_research_task_definitions(db)
    profile = ensure_research_profile(db, user_id)
    slot_count = int(profile["active_task_slots"] or 3) if profile else 3
    rows = db.execute(
        """
        SELECT *
        FROM user_research_tasks
        WHERE user_id = ? AND status IN ('active', 'completed')
        ORDER BY slot_index ASC, assigned_at ASC, id ASC
        """,
        (int(user_id),),
    ).fetchall()
    used_slots = {int(row["slot_index"] or 0) for row in rows}
    categories = ["basic", "build", "special"]
    for slot in range(1, slot_count + 1):
        if slot not in used_slots:
            assign_research_task(db, user_id, slot, category=categories[(slot - 1) % len(categories)])
    return research_board_view(db, user_id)


def _task_view(row):
    if not row:
        return None
    try:
        snapshot = json.loads(row["snapshot_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        snapshot = {}
    progress = min(int(row["progress"] or 0), int(row["target"] or 1))
    target = max(1, int(row["target"] or 1))
    return {
        "id": int(row["id"]),
        "task_key": row["task_key"],
        "status": row["status"],
        "slot_index": int(row["slot_index"] or 0),
        "title": snapshot.get("title") or row["task_key"],
        "description": snapshot.get("description") or "",
        "category": snapshot.get("category") or "basic",
        "category_label": snapshot.get("category_label") or CATEGORY_LABELS.get(snapshot.get("category"), "研究課題"),
        "reward_exp": int(snapshot.get("reward_exp") or 0),
        "progress": progress,
        "target": target,
        "progress_line": f"{progress} / {target}",
        "is_completed": str(row["status"]) in {"completed", "claimed"},
    }


def research_board_view(db, user_id):
    rows = db.execute(
        """
        SELECT *
        FROM user_research_tasks
        WHERE user_id = ? AND status IN ('active', 'completed')
        ORDER BY slot_index ASC, assigned_at ASC, id ASC
        """,
        (int(user_id),),
    ).fetchall()
    return [_task_view(row) for row in rows]


def held_task_view(db, user_id):
    row = db.execute(
        "SELECT * FROM user_research_tasks WHERE user_id = ? AND status = 'held' ORDER BY assigned_at DESC, id DESC LIMIT 1",
        (int(user_id),),
    ).fetchone()
    return _task_view(row)


def _event_matches_task(task, event_type, payload):
    try:
        snapshot = json.loads(task["snapshot_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        snapshot = {}
    condition_type = str(snapshot.get("condition_type") or "")
    condition_payload = snapshot.get("condition_payload") or {}
    if condition_type == "explore_area":
        return event_type == EVENT_EXPLORE_END and str(payload.get("area_key") or "") == str(condition_payload.get("area_key") or "")
    if condition_type == "win_any":
        return event_type == EVENT_EXPLORE_END and bool(((payload.get("result") or {}).get("win")))
    if condition_type == "win_area":
        return (
            event_type == EVENT_EXPLORE_END
            and bool(((payload.get("result") or {}).get("win")))
            and str(payload.get("area_key") or "") == str(condition_payload.get("area_key") or "")
        )
    if condition_type == "part_drop":
        return event_type == EVENT_DROP or (
            event_type == EVENT_EXPLORE_END and bool(((payload.get("rewards") or {}).get("drops") or []))
        )
    if condition_type == "build_confirm":
        return event_type == EVENT_BUILD_CONFIRM
    if condition_type == "fast_win":
        turns = int(((payload.get("result") or {}).get("turns")) or 0)
        return event_type == EVENT_EXPLORE_END and bool(((payload.get("result") or {}).get("win"))) and turns > 0 and turns <= int(condition_payload.get("turns") or 5)
    if condition_type == "boss_win":
        return event_type == EVENT_EXPLORE_END and bool(((payload.get("result") or {}).get("win"))) and bool(((payload.get("boss") or {}).get("is_area_boss")))
    if condition_type == "win_series":
        series_key = str(condition_payload.get("series_key") or "")
        module = payload.get("player") or {}
        series_keys = set(module.get("series_keys") or [])
        return event_type == EVENT_EXPLORE_END and bool(((payload.get("result") or {}).get("win"))) and series_key in series_keys
    return False


def update_research_tasks_for_event(db, user_id, event_type, payload=None):
    if not user_id or event_type not in RESEARCH_TASK_EVENTS:
        return []
    seed_research_task_definitions(db)
    ensure_research_profile(db, user_id)
    event_uid = _event_uid(event_type, payload or {})
    if event_uid:
        cur = db.execute(
            "INSERT OR IGNORE INTO user_research_event_receipts (user_id, event_uid, created_at) VALUES (?, ?, ?)",
            (int(user_id), event_uid, _now()),
        )
        if int(cur.rowcount or 0) <= 0:
            return []
    existing_rows = db.execute(
        """
        SELECT *
        FROM user_research_tasks
        WHERE user_id = ? AND status = 'active'
        ORDER BY slot_index ASC, id ASC
        """,
        (int(user_id),),
    ).fetchall()
    ensure_research_board(db, user_id)
    payload = payload or {}
    if existing_rows:
        ids = [int(row["id"]) for row in existing_rows]
        placeholders = ",".join("?" for _ in ids)
        rows = db.execute(
            f"""
            SELECT *
            FROM user_research_tasks
            WHERE user_id = ? AND status = 'active' AND id IN ({placeholders})
            ORDER BY slot_index ASC, id ASC
            """,
            (int(user_id), *ids),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT *
            FROM user_research_tasks
            WHERE user_id = ? AND status = 'active'
            ORDER BY slot_index ASC, id ASC
            """,
            (int(user_id),),
        ).fetchall()
    updates = []
    for row in rows:
        if not _event_matches_task(row, event_type, payload):
            continue
        before = int(row["progress"] or 0)
        target = int(row["target"] or 1)
        after = min(target, before + 1)
        status = "completed" if after >= target else "active"
        completed_at = _now() if status == "completed" else None
        db.execute(
            """
            UPDATE user_research_tasks
            SET progress = ?,
                status = ?,
                completed_at = COALESCE(completed_at, ?)
            WHERE id = ? AND status = 'active'
            """,
            (after, status, completed_at, int(row["id"])),
        )
        view = _task_view(db.execute("SELECT * FROM user_research_tasks WHERE id = ?", (int(row["id"]),)).fetchone())
        event_payload = {
            "task_id": int(row["id"]),
            "task_key": row["task_key"],
            "progress_before": before,
            "progress": after,
            "target": target,
            "completed": status == "completed",
        }
        _audit(db, RESEARCH_AUDIT_EVENTS["progress"], user_id, event_payload, entity_type="research_task", entity_id=int(row["id"]))
        if status == "completed":
            reward_exp = int(view.get("reward_exp") or 0)
            result = grant_lab_exp(
                db,
                int(user_id),
                "research.task.complete",
                reward_exp,
                source_entity_type="research_task",
                source_entity_id=int(row["id"]),
                payload={"task_key": row["task_key"], "task_title": view.get("title")},
            )
            sync_research_profile_from_user(db, user_id)
            _audit(
                db,
                RESEARCH_AUDIT_EVENTS["complete"],
                user_id,
                {**event_payload, "reward_exp": reward_exp, "level_after": int(result.get("level_after") or 1)},
                entity_type="research_task",
                entity_id=int(row["id"]),
                delta_count=reward_exp,
            )
            _audit(
                db,
                RESEARCH_AUDIT_EVENTS["claim"],
                user_id,
                {"task_id": int(row["id"]), "task_key": row["task_key"], "reward_exp": reward_exp},
                entity_type="research_task",
                entity_id=int(row["id"]),
                delta_count=reward_exp,
            )
            if result.get("leveled_up"):
                _audit(
                    db,
                    RESEARCH_AUDIT_EVENTS["level_up"],
                    user_id,
                    {
                        "level_before": int(result.get("level_before") or 1),
                        "level_after": int(result.get("level_after") or 1),
                        "rank_after": result.get("rank_after"),
                        "task_key": row["task_key"],
                    },
                    entity_type="user_research_profile",
                    entity_id=int(user_id),
                )
            db.execute(
                "UPDATE user_research_tasks SET status = 'claimed', claimed_at = ? WHERE id = ? AND status = 'completed'",
                (_now(), int(row["id"])),
            )
            assign_research_task(db, user_id, int(row["slot_index"] or 1), category=view.get("category"))
            view["reward_result"] = result
        updates.append(view)
    return updates


def _event_uid(event_type, payload):
    result = payload.get("result") or {}
    battle_id = result.get("battle_id") or payload.get("battle_id")
    if battle_id:
        return f"{event_type}:battle:{battle_id}"
    request_id = payload.get("request_id")
    if request_id:
        return f"{event_type}:request:{request_id}"
    return ""


def hold_research_task(db, user_id, task_id):
    row = db.execute(
        "SELECT * FROM user_research_tasks WHERE id = ? AND user_id = ? AND status = 'active'",
        (int(task_id), int(user_id)),
    ).fetchone()
    if not row:
        return {"ok": False, "reason": "保留できない研究課題です"}
    held = db.execute("SELECT id FROM user_research_tasks WHERE user_id = ? AND status = 'held' LIMIT 1", (int(user_id),)).fetchone()
    if held:
        return {"ok": False, "reason": "保留できる研究課題は1件だけです"}
    slot = int(row["slot_index"] or 1)
    db.execute("UPDATE user_research_tasks SET status = 'held', slot_index = 0 WHERE id = ?", (int(task_id),))
    _audit(db, RESEARCH_AUDIT_EVENTS["hold"], user_id, {"task_id": int(task_id), "task_key": row["task_key"]}, entity_type="research_task", entity_id=int(task_id))
    assign_research_task(db, user_id, slot)
    return {"ok": True}


def resume_held_research_task(db, user_id, task_id):
    held = db.execute(
        "SELECT * FROM user_research_tasks WHERE id = ? AND user_id = ? AND status = 'held'",
        (int(task_id), int(user_id)),
    ).fetchone()
    if not held:
        return {"ok": False, "reason": "再開できない研究課題です"}
    active_slots = {
        int(row["slot_index"] or 0)
        for row in db.execute(
            "SELECT slot_index FROM user_research_tasks WHERE user_id = ? AND status IN ('active', 'completed')",
            (int(user_id),),
        ).fetchall()
    }
    slot = next((slot for slot in (1, 2, 3) if slot not in active_slots), 1)
    current = db.execute(
        "SELECT id FROM user_research_tasks WHERE user_id = ? AND status = 'active' AND slot_index = ? LIMIT 1",
        (int(user_id), slot),
    ).fetchone()
    if current:
        db.execute("UPDATE user_research_tasks SET status = 'held', slot_index = 0 WHERE id = ?", (int(current["id"]),))
    db.execute("UPDATE user_research_tasks SET status = 'active', slot_index = ? WHERE id = ?", (slot, int(task_id)))
    return {"ok": True}


def update_personal_records_from_explore(db, user_id, payload, include_extended=False):
    result = payload.get("result") or {}
    area_key = str(payload.get("area_key") or "layer_1")
    turns = int(result.get("turns") or 0)
    if turns <= 0:
        return []
    robot_instance_id = int(((payload.get("player") or {}).get("robot_instance_id")) or 0) or None
    base_payload = {"area_key": area_key, "turns": turns, "battle_id": result.get("battle_id"), "robot_instance_id": robot_instance_id}
    updates = []
    if bool(result.get("win")):
        updates.extend(_record_update(db, user_id, "area_fastest_win_turns", area_key, turns, payload=base_payload, lower_is_better=True))
    if not include_extended:
        return updates
    damage_taken = int(payload.get("damage_taken_total") or 0)
    damage_dealt = int(result.get("damage_dealt_total") or payload.get("damage_dealt_total") or 0)
    if bool(result.get("win")):
        updates.extend(_record_update(db, user_id, "area_min_damage_taken", area_key, damage_taken, payload=base_payload, lower_is_better=True))
        boss = payload.get("boss") or {}
        if boss.get("is_area_boss"):
            enemy_key = ((payload.get("enemy") or {}).get("key")) or boss.get("enemy_key") or area_key
            updates.extend(_record_update(db, user_id, "boss_fastest_win_turns", enemy_key, turns, payload=base_payload, lower_is_better=True))
            updates.extend(_record_update(db, user_id, "boss_min_damage_taken", enemy_key, damage_taken, payload=base_payload, lower_is_better=True))
    updates.extend(_record_update(db, user_id, "area_longest_survival_turns", area_key, turns, payload=base_payload, lower_is_better=False))
    if damage_dealt > 0:
        updates.extend(_record_update(db, user_id, "area_max_damage_dealt", area_key, damage_dealt, payload=base_payload, lower_is_better=False))
    return updates


def _upsert_record(db, user_id, record_key, scope_key, value, payload=None, lower_is_better=True):
    existing = db.execute(
        """
        SELECT *
        FROM user_personal_records
        WHERE user_id = ? AND record_key = ? AND scope_key = ?
        """,
        (int(user_id), str(record_key), str(scope_key)),
    ).fetchone()
    previous = int(existing["best_value"]) if existing else None
    improved = existing is None or (int(value) < previous if lower_is_better else int(value) > previous)
    if not improved:
        return []
    now_ts = _now()
    db.execute(
        """
        INSERT INTO user_personal_records
            (user_id, record_key, scope_key, best_value, best_payload_json, robot_instance_id, achieved_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, record_key, scope_key) DO UPDATE SET
            best_value = excluded.best_value,
            best_payload_json = excluded.best_payload_json,
            robot_instance_id = excluded.robot_instance_id,
            achieved_at = excluded.achieved_at,
            updated_at = excluded.updated_at
        """,
        (
            int(user_id),
            str(record_key),
            str(scope_key),
            int(value),
            _json(payload),
            int((payload or {}).get("robot_instance_id") or 0) or None,
            now_ts,
            now_ts,
        ),
    )
    update = {
        "record_key": str(record_key),
        "scope_key": str(scope_key),
        "previous_value": previous,
        "best_value": int(value),
        "lower_is_better": bool(lower_is_better),
    }
    _audit(db, RESEARCH_AUDIT_EVENTS["personal_record"], user_id, update, entity_type="personal_record")
    return [update]


def research_home_view(db, user_id):
    board = ensure_research_board(db, user_id)
    user = db.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
    level = lab_level_view(user) if user else {}
    held = held_task_view(db, user_id)
    recent_records = recent_personal_records(db, user_id, limit=3)
    next_task = next((task for task in board if not task.get("is_completed")), None)
    summary = research_summary_view(db, user_id)
    return {
        "level": level,
        "tasks": board,
        "held_task": held,
        "recent_records": recent_records,
        "next_task": next_task,
        "summary": summary,
        "next_series": next_series_hint(db, user_id),
    }


def recent_personal_records(db, user_id, limit=5):
    rows = db.execute(
        """
        SELECT *
        FROM user_personal_records
        WHERE user_id = ?
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (int(user_id), int(limit)),
    ).fetchall()
    return [
        {
            "record_key": row["record_key"],
            "scope_key": row["scope_key"],
            "best_value": int(row["best_value"] or 0),
            "label": _record_label(row["record_key"], row["scope_key"], int(row["best_value"] or 0)),
            "updated_at": int(row["updated_at"] or 0),
        }
        for row in rows
    ]


def _record_label(record_key, scope_key, value):
    if record_key in {"area_fastest_win_turns", "boss_fastest_win_turns"}:
        return f"{scope_key} 最短勝利 {value}T"
    if record_key in {"area_max_damage_dealt"}:
        return f"{scope_key} 最大与ダメージ {value}"
    if record_key in {"area_min_damage_taken", "boss_min_damage_taken"}:
        return f"{scope_key} 最小被ダメージ {value}"
    if record_key == "area_longest_survival_turns":
        return f"{scope_key} 最長戦闘 {value}T"
    if record_key == "build_highest_power":
        return f"設計時最高パワー {value}"
    return f"{record_key}: {value}"


def _record_update(db, user_id, record_key, scope_key, value, payload=None, lower_is_better=True):
    if value is None:
        return []
    try:
        value = int(value)
    except (TypeError, ValueError):
        return []
    return _upsert_record(db, user_id, record_key, scope_key, value, payload=payload, lower_is_better=lower_is_better)


def _day_key(ts=None):
    return time.strftime("%Y-%m-%d", time.localtime(int(ts or _now())))


def _enemy_row(db, enemy_key):
    if not enemy_key:
        return None
    return db.execute("SELECT * FROM enemies WHERE key = ?", (str(enemy_key),)).fetchone()


def _enemy_label(row, enemy_key):
    if row and "name_ja" in row.keys() and row["name_ja"]:
        return row["name_ja"]
    return str(enemy_key or "不明な敵")


def _upsert_enemy_stats(db, user_id, enemy_key, win=False, turns=None, damage_taken=0, metadata=None, is_boss=False):
    if not enemy_key:
        return []
    ensure_research_phase2_schema(db)
    table = "user_boss_research_stats" if is_boss else "user_enemy_research_stats"
    key_col = "boss_key" if is_boss else "enemy_key"
    now_ts = _now()
    row = db.execute(f"SELECT * FROM {table} WHERE user_id = ? AND {key_col} = ?", (int(user_id), str(enemy_key))).fetchone()
    encounter_before = int(row["encounter_count"] or 0) if row else 0
    defeat_before = int(row["defeat_count"] or 0) if row else 0
    best_before = int(row["best_win_turns"]) if row and row["best_win_turns"] is not None else None
    best_after = best_before
    if win and turns:
        best_after = int(turns) if best_before is None else min(best_before, int(turns))
    db.execute(
        f"""
        INSERT INTO {table}
            (user_id, {key_col}, first_encountered_at, first_defeated_at, encounter_count,
             defeat_count, best_win_turns, total_damage_taken, last_seen_at, metadata_json)
        VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, {key_col}) DO UPDATE SET
            first_encountered_at = COALESCE({table}.first_encountered_at, excluded.first_encountered_at),
            first_defeated_at = COALESCE({table}.first_defeated_at, excluded.first_defeated_at),
            encounter_count = {table}.encounter_count + 1,
            defeat_count = {table}.defeat_count + excluded.defeat_count,
            best_win_turns = CASE
                WHEN excluded.best_win_turns IS NULL THEN {table}.best_win_turns
                WHEN {table}.best_win_turns IS NULL THEN excluded.best_win_turns
                WHEN excluded.best_win_turns < {table}.best_win_turns THEN excluded.best_win_turns
                ELSE {table}.best_win_turns
            END,
            total_damage_taken = {table}.total_damage_taken + excluded.total_damage_taken,
            last_seen_at = excluded.last_seen_at,
            metadata_json = excluded.metadata_json
        """,
        (
            int(user_id),
            str(enemy_key),
            now_ts,
            now_ts if win else None,
            1 if win else 0,
            int(turns) if win and turns else None,
            int(damage_taken or 0),
            now_ts,
            _json(metadata),
        ),
    )
    enemy = _enemy_row(db, enemy_key)
    label = _enemy_label(enemy, enemy_key)
    updates = []
    if encounter_before <= 0:
        dtype = "boss_encounter" if is_boss else "enemy_encounter"
        discovery = _insert_discovery(db, user_id, dtype, enemy_key, source_key="battle", metadata={"label": label})
        _grant_discovery_exp(db, user_id, discovery)
        if discovery:
            updates.append({"priority": 30 if is_boss else 20, "label": f"{label}を初記録", "exp": discovery["exp"]})
    if win and defeat_before <= 0:
        dtype = "boss_defeat" if is_boss else "enemy_defeat"
        discovery = _insert_discovery(db, user_id, dtype, enemy_key, source_key="battle", metadata={"label": label})
        _grant_discovery_exp(db, user_id, discovery)
        if discovery:
            updates.append({"priority": 95 if is_boss else 25, "label": f"{label}を初撃破", "exp": discovery["exp"]})
    if win and turns and (best_before is None or int(turns) < best_before):
        updates.append({"priority": 10, "label": f"{label} 最短勝利 {int(turns)}T", "exp": 0})
    return updates


def _series_model_keys(db, series_key):
    rows = db.execute(
        """
        SELECT *
        FROM robot_parts
        WHERE COALESCE(is_active, 1) = 1
          AND COALESCE(is_unlocked, 1) = 1
          AND COALESCE(is_admin_only, 0) = 0
          AND COALESCE(series_key, '') = ?
          AND COALESCE(part_type, '') != 'decor'
        ORDER BY part_type ASC, key ASC
        """,
        (str(series_key),),
    ).fetchall()
    return {f"part_model:{_part_model_key(row)}" for row in rows}, rows


def _check_series_completion(db, user_id, series_key, series_label=None, source_key=None, request_id=None):
    if not series_key:
        return None
    required, rows = _series_model_keys(db, series_key)
    if not required:
        return None
    found = {
        f"part_model:{row['discovery_key']}"
        for row in db.execute(
            "SELECT discovery_key FROM user_discoveries WHERE user_id = ? AND discovery_type = 'part_model'",
            (int(user_id),),
        ).fetchall()
    }
    if len(required & found) < len(required):
        return None
    label = series_label or (rows[0]["series_label"] if rows and "series_label" in rows[0].keys() else series_key)
    discovery = _insert_discovery(
        db,
        user_id,
        "part_series_complete",
        str(series_key),
        source_key=source_key,
        request_id=request_id,
        metadata={"label": label, "required": len(required)},
    )
    _grant_discovery_exp(db, user_id, discovery)
    if not discovery:
        return None
    return {"priority": 100, "label": f"{label}シリーズ完成", "exp": discovery["exp"]}


def discover_part_from_key(db, user_id, part_key, source_key=None, request_id=None):
    if not part_key:
        return []
    ensure_research_phase2_schema(db)
    part = db.execute("SELECT * FROM robot_parts WHERE key = ?", (str(part_key),)).fetchone()
    if not part:
        return []
    model_key = _part_model_key(part)
    label = _part_model_label(part)
    rarity = (part["rarity"] if "rarity" in part.keys() else None) or "N"
    series_key = part["series_key"] if "series_key" in part.keys() else None
    series_label = part["series_label"] if "series_label" in part.keys() else None
    updates = []
    model = _insert_discovery(
        db,
        user_id,
        "part_model",
        model_key,
        source_key=source_key,
        request_id=request_id,
        metadata={"label": label, "part_key": part_key, "part_type": part["part_type"], "series_key": series_key, "series_label": series_label},
    )
    _grant_discovery_exp(db, user_id, model)
    if model:
        updates.append({"priority": 80, "label": f"{label}を初解析", "exp": model["exp"]})
    rarity_key = f"{model_key}:{rarity}"
    rarity_discovery = _insert_discovery(
        db,
        user_id,
        "part_rarity",
        rarity_key,
        source_key=source_key,
        request_id=request_id,
        metadata={"label": f"{label} {rarity}", "model_key": model_key, "rarity": rarity, "part_key": part_key},
    )
    _grant_discovery_exp(db, user_id, rarity_discovery)
    if rarity_discovery:
        updates.append({"priority": 70, "label": f"{label} {rarity}を記録", "exp": rarity_discovery["exp"]})
    completed = _check_series_completion(db, user_id, series_key, series_label=series_label, source_key=source_key, request_id=request_id)
    if completed:
        updates.append(completed)
    return updates


def record_robot_design_from_build(db, user_id, payload=None, request_id=None, robot_instance_id=None):
    ensure_research_phase2_schema(db)
    payload = payload or {}
    robot_instance_id = robot_instance_id or payload.get("robot_instance_id")
    if not robot_instance_id:
        return []
    robot = db.execute("SELECT * FROM robot_instances WHERE id = ? AND user_id = ?", (int(robot_instance_id), int(user_id))).fetchone()
    parts = db.execute("SELECT * FROM robot_instance_parts WHERE robot_instance_id = ?", (int(robot_instance_id),)).fetchone()
    if not robot or not parts:
        return []
    loadout = {
        "head_key": parts["head_key"],
        "r_arm_key": parts["r_arm_key"],
        "l_arm_key": parts["l_arm_key"],
        "legs_key": parts["legs_key"],
        "decor_asset_id": parts["decor_asset_id"] if "decor_asset_id" in parts.keys() else None,
        "combat_mode": robot["combat_mode"] if "combat_mode" in robot.keys() else payload.get("combat_mode"),
        "frame_type": robot["frame_type"] if "frame_type" in robot.keys() else payload.get("build_mode"),
    }
    loadout_hash = hashlib.sha256(json.dumps(loadout, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
    existing = db.execute(
        "SELECT * FROM robot_design_records WHERE user_id = ? AND loadout_hash = ?",
        (int(user_id), loadout_hash),
    ).fetchone()
    now_ts = _now()
    snapshot = {"loadout": loadout, "robot_instance_id": int(robot_instance_id), "request_id": request_id}
    image_path = robot["composed_image_path"] if "composed_image_path" in robot.keys() else None
    icon_path = robot["icon_32_path"] if "icon_32_path" in robot.keys() else None
    if existing:
        db.execute(
            """
            UPDATE robot_design_records
            SET robot_instance_id = ?, robot_name = ?, image_path = ?, icon_path = ?,
                snapshot_json = ?, build_count = build_count + 1, last_built_at = ?
            WHERE id = ?
            """,
            (int(robot_instance_id), robot["name"], image_path, icon_path, _json(snapshot), now_ts, int(existing["id"])),
        )
        return [{"priority": 5, "label": "設計機記録を更新", "exp": 0}]
    db.execute(
        """
        INSERT INTO robot_design_records
            (user_id, robot_instance_id, loadout_hash, robot_name, head_key, r_arm_key, l_arm_key, legs_key,
             decor_asset_id, combat_mode, frame_type, image_path, icon_path, snapshot_json, build_count, first_built_at, last_built_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (
            int(user_id),
            int(robot_instance_id),
            loadout_hash,
            robot["name"],
            loadout["head_key"],
            loadout["r_arm_key"],
            loadout["l_arm_key"],
            loadout["legs_key"],
            loadout["decor_asset_id"],
            loadout["combat_mode"],
            loadout["frame_type"],
            image_path,
            icon_path,
            _json(snapshot),
            now_ts,
            now_ts,
        ),
    )
    discovery = _insert_discovery(db, user_id, "first_design", loadout_hash, source_key="build", request_id=request_id, metadata={"label": robot["name"] or "設計機"})
    _grant_discovery_exp(db, user_id, discovery)
    _record_update(db, user_id, "build_highest_power", "all", payload.get("power") or payload.get("total_power"), payload={"robot_instance_id": robot_instance_id}, lower_is_better=False)
    return [{"priority": 60, "label": "新しい設計機を記録", "exp": int((discovery or {}).get("exp") or 0)}]


def update_daily_research_stats(db, user_id, payload):
    ensure_research_phase2_schema(db)
    result = payload.get("result") or {}
    rewards = payload.get("rewards") or {}
    battles = payload.get("battles") or []
    boss = payload.get("boss") or {}
    day = _day_key()
    db.execute(
        """
        INSERT INTO user_daily_research_stats
            (user_id, day_key, explore_count, win_count, part_drop_count, enemy_encounter_count, boss_encounter_count, updated_at)
        VALUES (?, ?, 1, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, day_key) DO UPDATE SET
            explore_count = explore_count + 1,
            win_count = win_count + excluded.win_count,
            part_drop_count = part_drop_count + excluded.part_drop_count,
            enemy_encounter_count = enemy_encounter_count + excluded.enemy_encounter_count,
            boss_encounter_count = boss_encounter_count + excluded.boss_encounter_count,
            updated_at = excluded.updated_at
        """,
        (
            int(user_id),
            day,
            1 if result.get("win") else 0,
            len(rewards.get("drops") or []),
            len(battles) or (1 if payload.get("enemy") else 0),
            1 if boss.get("is_area_boss") else 0,
            _now(),
        ),
    )


def process_research_collection_event(db, user_id, event_type, payload=None, request_id=None, entity_type=None, entity_id=None):
    if not user_id or event_type not in RESEARCH_COLLECTION_EVENTS:
        return []
    ensure_research_phase2_schema(db)
    payload = payload or {}
    event_uid = _collection_event_uid(event_type, payload, request_id=request_id, entity_type=entity_type, entity_id=entity_id)
    if not _event_receipt(db, user_id, event_uid):
        return []
    updates = []
    if event_type == EVENT_DROP:
        updates.extend(discover_part_from_key(db, user_id, payload.get("part_key"), source_key=payload.get("source") or "drop", request_id=request_id))
    elif event_type == EVENT_BUILD_CONFIRM:
        updates.extend(record_robot_design_from_build(db, user_id, payload=payload, request_id=request_id, robot_instance_id=entity_id or payload.get("robot_instance_id")))
    elif event_type in {EVENT_BOSS_ENCOUNTER, EVENT_BOSS_DEFEAT}:
        enemy_key = payload.get("enemy_key") or entity_id
        updates.extend(
            _upsert_enemy_stats(
                db,
                user_id,
                enemy_key,
                win=event_type == EVENT_BOSS_DEFEAT,
                turns=payload.get("turns"),
                damage_taken=payload.get("damage_taken_total") or 0,
                metadata=payload,
                is_boss=True,
            )
        )
    elif event_type == EVENT_EXPLORE_END:
        update_daily_research_stats(db, user_id, payload)
        result = payload.get("result") or {}
        turns = int(result.get("turns") or 0) or None
        damage_taken = int(payload.get("damage_taken_total") or 0)
        for drop in ((payload.get("rewards") or {}).get("drops") or []):
            updates.extend(discover_part_from_key(db, user_id, drop.get("part_key"), source_key="explore", request_id=request_id))
        battles = payload.get("battles") or []
        if not battles and payload.get("enemy"):
            battles = [{"enemy": payload.get("enemy"), "win": result.get("win"), "turns": turns}]
        for battle in battles:
            enemy = battle.get("enemy") or {}
            enemy_key = enemy.get("key") or payload.get("enemy_key")
            updates.extend(
                _upsert_enemy_stats(
                    db,
                    user_id,
                    enemy_key,
                    win=bool(battle.get("win")),
                    turns=battle.get("turns") or turns,
                    damage_taken=damage_taken,
                    metadata=enemy,
                    is_boss=bool(enemy.get("is_boss") or (payload.get("boss") or {}).get("is_area_boss")),
                )
            )
        boss = payload.get("boss") or {}
        if boss.get("is_area_boss"):
            enemy_key = (payload.get("enemy") or {}).get("key") or boss.get("enemy_key")
            updates.extend(_upsert_enemy_stats(db, user_id, enemy_key, win=bool(result.get("win")), turns=turns, damage_taken=damage_taken, metadata=boss, is_boss=True))
    updates.sort(key=lambda item: int(item.get("priority") or 0), reverse=True)
    return updates[:8]


def _percent(done, total):
    total = int(total or 0)
    if total <= 0:
        return 0
    return int(round((int(done or 0) / total) * 100))


def research_summary_view(db, user_id):
    ensure_research_phase2_schema(db)
    parts_total = int(db.execute("SELECT COUNT(*) AS c FROM robot_parts WHERE COALESCE(is_active,1)=1 AND COALESCE(is_unlocked,1)=1 AND COALESCE(is_admin_only,0)=0 AND COALESCE(part_type,'')!='decor'").fetchone()["c"] or 0)
    part_models_total = len({_part_model_key(row) for row in db.execute("SELECT * FROM robot_parts WHERE COALESCE(is_active,1)=1 AND COALESCE(is_unlocked,1)=1 AND COALESCE(is_admin_only,0)=0 AND COALESCE(part_type,'')!='decor'").fetchall()})
    parts_done = int(db.execute("SELECT COUNT(*) AS c FROM user_discoveries WHERE user_id=? AND discovery_type='part_model'", (int(user_id),)).fetchone()["c"] or 0)
    series_done = int(db.execute("SELECT COUNT(*) AS c FROM user_discoveries WHERE user_id=? AND discovery_type='part_series_complete'", (int(user_id),)).fetchone()["c"] or 0)
    enemy_done = int(db.execute("SELECT COUNT(*) AS c FROM user_enemy_research_stats WHERE user_id=? AND encounter_count > 0", (int(user_id),)).fetchone()["c"] or 0)
    design_count = int(db.execute("SELECT COUNT(*) AS c FROM robot_design_records WHERE user_id=?", (int(user_id),)).fetchone()["c"] or 0)
    recent_records = recent_personal_records(db, user_id, limit=3)
    user = db.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
    return {
        "level": lab_level_view(user) if user else {},
        "parts_done": parts_done,
        "parts_total": part_models_total or parts_total,
        "parts_percent": _percent(parts_done, part_models_total or parts_total),
        "series_done": series_done,
        "enemy_done": enemy_done,
        "design_count": design_count,
        "recent_records": recent_records,
    }


def next_series_hint(db, user_id):
    ensure_research_phase2_schema(db)
    discovered = {
        row["discovery_key"]
        for row in db.execute("SELECT discovery_key FROM user_discoveries WHERE user_id=? AND discovery_type='part_model'", (int(user_id),)).fetchall()
    }
    best = None
    for series in db.execute("SELECT DISTINCT series_key, series_label FROM robot_parts WHERE COALESCE(series_key,'') != '' ORDER BY series_key").fetchall():
        keys, rows = _series_model_keys(db, series["series_key"])
        if not keys:
            continue
        done = len({_key.split("part_model:", 1)[1] for _key in keys} & discovered)
        if done >= len(keys):
            continue
        item = {"series_key": series["series_key"], "label": series["series_label"] or series["series_key"], "done": done, "total": len(keys)}
        if best is None or item["done"] > best["done"]:
            best = item
    return best


def parts_catalog_view(db, user_id):
    ensure_research_phase2_schema(db)
    discovered = {
        row["discovery_key"]: row
        for row in db.execute("SELECT * FROM user_discoveries WHERE user_id=? AND discovery_type='part_model'", (int(user_id),)).fetchall()
    }
    rows = db.execute(
        """
        SELECT * FROM robot_parts
        WHERE COALESCE(is_active,1)=1 AND COALESCE(is_unlocked,1)=1 AND COALESCE(is_admin_only,0)=0
          AND COALESCE(part_type,'')!='decor'
        ORDER BY COALESCE(series_key, 'zz'), part_type, key
        """
    ).fetchall()
    seen = set()
    items = []
    for row in rows:
        key = _part_model_key(row)
        if key in seen:
            continue
        seen.add(key)
        found = key in discovered
        items.append({
            "key": key,
            "label": _part_model_label(row) if found else "未発見パーツ",
            "part_type_label": PART_TYPE_LABELS.get(row["part_type"], row["part_type"]),
            "series_label": row["series_label"] if "series_label" in row.keys() else "",
            "rarity": row["rarity"] if found and "rarity" in row.keys() else "?",
            "image_path": row["image_path"] if found else None,
            "found": found,
        })
    return {"summary": research_summary_view(db, user_id), "items": items, "hint": next_series_hint(db, user_id)}


def series_catalog_view(db, user_id):
    ensure_research_phase2_schema(db)
    completed = {row["discovery_key"] for row in db.execute("SELECT discovery_key FROM user_discoveries WHERE user_id=? AND discovery_type='part_series_complete'", (int(user_id),)).fetchall()}
    discovered = {row["discovery_key"] for row in db.execute("SELECT discovery_key FROM user_discoveries WHERE user_id=? AND discovery_type='part_model'", (int(user_id),)).fetchall()}
    items = []
    for row in db.execute("SELECT DISTINCT series_key, series_label FROM robot_parts WHERE COALESCE(series_key,'') != '' ORDER BY series_key").fetchall():
        keys, _rows = _series_model_keys(db, row["series_key"])
        total = len(keys)
        done = len({_key.split("part_model:", 1)[1] for _key in keys} & discovered)
        items.append({"key": row["series_key"], "label": row["series_label"] or row["series_key"], "done": done, "total": total, "percent": _percent(done, total), "completed": row["series_key"] in completed})
    return {"summary": research_summary_view(db, user_id), "items": items, "hint": next_series_hint(db, user_id)}


def enemies_catalog_view(db, user_id, bosses=False):
    ensure_research_phase2_schema(db)
    table = "user_boss_research_stats" if bosses else "user_enemy_research_stats"
    key_col = "boss_key" if bosses else "enemy_key"
    rows = db.execute(
        f"""
        SELECT e.*, s.encounter_count, s.defeat_count, s.best_win_turns, s.first_encountered_at, s.first_defeated_at
        FROM enemies e
        LEFT JOIN {table} s ON s.{key_col} = e.key AND s.user_id = ?
        WHERE COALESCE(e.is_boss,0) = ?
        ORDER BY COALESCE(e.tier, 1), e.key
        """,
        (int(user_id), 1 if bosses else 0),
    ).fetchall()
    items = []
    for row in rows:
        found = int(row["encounter_count"] or 0) > 0
        items.append({
            "key": row["key"],
            "label": row["name_ja"] if found else ("未確認ボス" if bosses else "未確認の敵"),
            "tier": row["tier"] if found else "?",
            "element": row["element"] if found else "?",
            "trait": row["trait"] if found and "trait" in row.keys() else "",
            "image_path": row["image_path"] if found else None,
            "encounter_count": int(row["encounter_count"] or 0),
            "defeat_count": int(row["defeat_count"] or 0),
            "best_win_turns": row["best_win_turns"],
            "found": found,
            "defeated": bool(row["first_defeated_at"]),
        })
    return {"summary": research_summary_view(db, user_id), "items": items, "bosses": bosses}


def bosses_catalog_view(db, user_id):
    return enemies_catalog_view(db, user_id, bosses=True)


def designs_catalog_view(db, user_id):
    ensure_research_phase2_schema(db)
    rows = db.execute("SELECT * FROM robot_design_records WHERE user_id=? ORDER BY last_built_at DESC, id DESC", (int(user_id),)).fetchall()
    return {"summary": research_summary_view(db, user_id), "items": [dict(row) for row in rows]}


def records_catalog_view(db, user_id):
    ensure_research_phase2_schema(db)
    rows = db.execute("SELECT * FROM user_personal_records WHERE user_id=? ORDER BY record_key, scope_key", (int(user_id),)).fetchall()
    items = []
    for row in rows:
        items.append({
            "record_key": row["record_key"],
            "record_label": RECORD_LABELS.get(row["record_key"], row["record_key"]),
            "scope_key": row["scope_key"],
            "best_value": int(row["best_value"] or 0),
            "label": _record_label(row["record_key"], row["scope_key"], int(row["best_value"] or 0)),
            "updated_at": int(row["updated_at"] or 0),
        })
    return {"summary": research_summary_view(db, user_id), "items": items}


def backfill_research(db, user_id=None, dry_run=False):
    ensure_research_phase2_schema(db)
    params = []
    where = ""
    if user_id:
        where = "WHERE id = ?"
        params.append(int(user_id))
    users = db.execute(f"SELECT id FROM users {where} ORDER BY id", tuple(params)).fetchall()
    result = {"users": len(users), "discoveries": 0, "designs": 0, "errors": []}
    for user in users:
        uid = int(user["id"])
        try:
            part_rows = db.execute(
                """
                SELECT DISTINCT p.key
                FROM part_instances pi
                JOIN robot_parts p ON p.id = pi.part_id
                WHERE pi.user_id = ?
                """,
                (uid,),
            ).fetchall()
            design_rows = db.execute("SELECT id FROM robot_instances WHERE user_id = ? AND COALESCE(status,'') != 'deleted'", (uid,)).fetchall()
            if dry_run:
                result["discoveries"] += len(part_rows)
                result["designs"] += len(design_rows)
                continue
            before = research_summary_view(db, uid)
            for part in part_rows:
                discover_part_from_key(db, uid, part["key"], source_key="backfill")
            for robot in design_rows:
                record_robot_design_from_build(db, uid, payload={}, robot_instance_id=int(robot["id"]))
            after = research_summary_view(db, uid)
            result["discoveries"] += max(0, int(after["parts_done"] or 0) - int(before["parts_done"] or 0))
            result["designs"] += max(0, int(after["design_count"] or 0) - int(before["design_count"] or 0))
        except Exception as exc:
            result["errors"].append({"user_id": uid, "error": str(exc)})
    return result


def rebuild_research_records(db, user_id=None, dry_run=False):
    ensure_research_phase2_schema(db)
    robot_columns = _table_columns(db, "robot_instances")
    params = []
    where = ""
    if user_id:
        where = "WHERE id = ?"
        params.append(int(user_id))
    users = db.execute(f"SELECT id FROM users {where} ORDER BY id", tuple(params)).fetchall()
    result = {"users": len(users), "records": 0, "errors": []}
    if "power_score" not in robot_columns:
        return result
    if dry_run:
        result["records"] = sum(
            int(db.execute("SELECT COUNT(*) AS c FROM user_personal_records WHERE user_id = ?", (int(user["id"]),)).fetchone()["c"] or 0)
            for user in users
        )
        return result
    for user in users:
        uid = int(user["id"])
        try:
            power_row = db.execute(
                "SELECT MAX(COALESCE(power_score, 0)) AS value FROM robot_instances WHERE user_id = ?",
                (uid,),
            ).fetchone()
            if power_row and power_row["value"]:
                updates = _record_update(db, uid, "build_highest_power", "all", int(power_row["value"]), payload={}, lower_is_better=False)
                result["records"] += len(updates)
        except Exception as exc:
            result["errors"].append({"user_id": uid, "error": str(exc)})
    return result


def notebook_view(db, user_id):
    return {
        "home": research_home_view(db, user_id),
        "summary": research_summary_view(db, user_id),
        "next_series": next_series_hint(db, user_id),
        "completed_tasks": [
            _task_view(row)
            for row in db.execute(
                """
                SELECT *
                FROM user_research_tasks
                WHERE user_id = ? AND status = 'claimed'
                ORDER BY claimed_at DESC, completed_at DESC, id DESC
                LIMIT 50
                """,
                (int(user_id),),
            ).fetchall()
        ],
        "definitions": [
            dict(row)
            for row in db.execute(
                "SELECT * FROM research_task_definitions ORDER BY category ASC, difficulty ASC, task_key ASC"
            ).fetchall()
        ],
    }
