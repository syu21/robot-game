import json
import time

from services.lab_level import grant_lab_exp, lab_level_view


EVENT_EXPLORE_END = "audit.explore.end"
EVENT_DROP = "audit.drop"
EVENT_FUSE = "audit.fuse"
EVENT_PART_EVOLVE = "audit.part.evolve"
EVENT_BUILD_CONFIRM = "audit.build.confirm"

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
    ensure_research_board(db, user_id)
    payload = payload or {}
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


def update_personal_records_from_explore(db, user_id, payload):
    result = payload.get("result") or {}
    if not bool(result.get("win")):
        return []
    area_key = str(payload.get("area_key") or "layer_1")
    turns = int(result.get("turns") or 0)
    if turns <= 0:
        return []
    return _upsert_record(
        db,
        user_id,
        "area_fastest_win_turns",
        area_key,
        turns,
        payload={"area_key": area_key, "turns": turns, "battle_id": result.get("battle_id")},
        lower_is_better=True,
    )


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
    return {
        "level": level,
        "tasks": board,
        "held_task": held,
        "recent_records": recent_records,
        "next_task": next_task,
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
    if record_key == "area_fastest_win_turns":
        return f"{scope_key} 最短勝利 {value}T"
    return f"{record_key}: {value}"


def notebook_view(db, user_id):
    return {
        "home": research_home_view(db, user_id),
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
