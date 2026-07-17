import json
import hashlib
import time
from datetime import datetime, timedelta, timezone


JST = timezone(timedelta(hours=9))

EVENT_EXPLORE_END = "audit.explore.end"
EVENT_DROP = "audit.drop"
EVENT_FUSE = "audit.fuse"
EVENT_PART_EVOLVE = "audit.part.evolve"
EVENT_BUILD_CONFIRM = "audit.build.confirm"
EVENT_BUILD_VIEW = "audit.daily_research.build_view"
EVENT_WORLD_VIEW = "audit.daily_research.world_view"
EVENT_BOSS_ENCOUNTER = "audit.boss.encounter"
EVENT_BOSS_DEFEAT = "audit.boss.defeat"

DAILY_RESEARCH_TASK_CREATE = "audit.daily_research.task.create"
DAILY_RESEARCH_TASK_PROGRESS = "audit.daily_research.progress"
DAILY_RESEARCH_TASK_COMPLETE = "audit.daily_research.complete"
DAILY_RESEARCH_TASK_CLAIM = "audit.daily_research.claim"
DAILY_RESEARCH_REWARD_RESERVE = "audit.daily_research.reward.reserve"
DAILY_RESEARCH_REWARD_CLAIM = "audit.daily_research.reward.claim"
DAILY_RESEARCH_MODAL_VIEW = "audit.daily_research.modal.view"

DAILY_RESEARCH_TASK_EVENTS = {
    EVENT_EXPLORE_END,
    EVENT_FUSE,
    EVENT_BUILD_VIEW,
    EVENT_WORLD_VIEW,
    EVENT_PART_EVOLVE,
    EVENT_BUILD_CONFIRM,
    EVENT_BOSS_ENCOUNTER,
    EVENT_BOSS_DEFEAT,
    EVENT_DROP,
}
DAILY_RESEARCH_REWARD_SOURCE_EVENTS = {EVENT_EXPLORE_END, EVENT_FUSE, EVENT_BUILD_CONFIRM}

DAILY_RESEARCH_TASKS = [
    {
        "key": "explore_layer1_2",
        "title": "家電パーツを探そう",
        "description": "第1層で家電シリーズの発見データを集めます。",
        "target_event": EVENT_EXPLORE_END,
        "target_area_key": "layer_1",
        "target_count": 2,
        "reward_coins": 30,
    },
    {
        "key": "explore_layer2_1",
        "title": "電子レンジパーツを探そう",
        "description": "第2層で家電シリーズの反応を調査します。",
        "target_event": EVENT_EXPLORE_END,
        "target_area_key": "layer_2",
        "target_count": 1,
        "reward_coins": 35,
    },
    {
        "key": "strengthen_1",
        "title": "パーツ強化を1回行う",
        "description": "パーツを1回強化します。",
        "target_event": EVENT_FUSE,
        "target_count": 1,
        "reward_coins": 40,
    },
    {
        "key": "build_view_1",
        "title": "家電ロボの編成を見る",
        "description": "ロボ編成画面で家電パーツの組み合わせを確認します。",
        "target_event": EVENT_BUILD_VIEW,
        "target_count": 1,
        "reward_coins": 25,
    },
    {
        "key": "world_view_1",
        "title": "世界ログを見る",
        "description": "世界ログで研究員たちの記録を確認します。",
        "target_event": EVENT_WORLD_VIEW,
        "target_count": 1,
        "reward_coins": 25,
    },
]
DAILY_RESEARCH_TASK_BY_KEY = {task["key"]: task for task in DAILY_RESEARCH_TASKS}
LEGACY_DAILY_RESEARCH_TASK_ALIASES = {
    "explore_3": "explore_layer1_2",
    "explore_5": "explore_layer1_2",
    "build_1": "build_view_1",
    "boss_check": "explore_layer1_2",
}


def get_day_key(dt=None):
    target = dt or datetime.now(JST)
    if isinstance(target, (int, float)):
        target = datetime.fromtimestamp(target, JST)
    elif target.tzinfo is None:
        target = target.replace(tzinfo=JST)
    else:
        target = target.astimezone(JST)
    return target.strftime("%Y-%m-%d")


def _day_bounds(day_key):
    start = datetime.strptime(day_key, "%Y-%m-%d").replace(tzinfo=JST)
    return int(start.timestamp()), int((start + timedelta(days=1)).timestamp())


def _next_day_key(day_key):
    start = datetime.strptime(day_key, "%Y-%m-%d").replace(tzinfo=JST)
    return (start + timedelta(days=1)).strftime("%Y-%m-%d")


def _prev_day_key(day_key):
    start = datetime.strptime(day_key, "%Y-%m-%d").replace(tzinfo=JST)
    return (start - timedelta(days=1)).strftime("%Y-%m-%d")


def _row_to_task(row):
    if not row:
        return None
    data = dict(row)
    task_key = str(data.get("task_key") or "")
    canonical = DAILY_RESEARCH_TASK_BY_KEY.get(task_key)
    if not canonical and task_key in LEGACY_DAILY_RESEARCH_TASK_ALIASES:
        canonical = DAILY_RESEARCH_TASK_BY_KEY.get(LEGACY_DAILY_RESEARCH_TASK_ALIASES[task_key])
    if canonical:
        data["task_key"] = canonical["key"]
        data["title"] = canonical["title"]
        data["description"] = canonical["description"]
        data["target_event"] = canonical["target_event"]
        data["target_area_key"] = canonical.get("target_area_key")
    data["current_count_display"] = min(int(data.get("current_count") or 0), int(data.get("target_count") or 1))
    data["is_completed"] = data.get("status") in {"completed", "claimed"}
    data["is_claimed"] = data.get("status") == "claimed"
    return data


def _audit(db, event_type, user_id, payload=None, action_key=None, entity_type=None, entity_id=None, delta_coins=None):
    try:
        db.execute(
            """
            INSERT INTO world_events_log
            (created_at, event_type, payload_json, user_id, action_key, entity_type, entity_id, delta_coins)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(time.time()),
                str(event_type),
                json.dumps(payload or {}, ensure_ascii=False),
                int(user_id) if user_id is not None else None,
                action_key,
                entity_type,
                entity_id,
                delta_coins,
            ),
        )
    except Exception:
        db.execute(
            "INSERT INTO world_events_log (created_at, event_type, payload_json) VALUES (?, ?, ?)",
            (int(time.time()), str(event_type), json.dumps(payload or {}, ensure_ascii=False)),
        )


def _event_count(db, user_id, event_type, day_key):
    start_ts, end_ts = _day_bounds(day_key)
    return int(
        db.execute(
            """
            SELECT COUNT(*) AS c
            FROM world_events_log
            WHERE user_id = ? AND event_type = ? AND created_at >= ? AND created_at < ?
            """,
            (int(user_id), str(event_type), int(start_ts), int(end_ts)),
        ).fetchone()["c"]
        or 0
    )


def _choose_task(db, user_id, today_key):
    user = db.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
    max_layer = int(user["max_unlocked_layer"] or 1) if user and "max_unlocked_layer" in user.keys() else 1
    active_robot_id = int(user["active_robot_id"] or 0) if user and "active_robot_id" in user.keys() and user["active_robot_id"] else 0
    total_explores = int(
        db.execute(
            "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
            (int(user_id), EVENT_EXPLORE_END),
        ).fetchone()["c"]
        or 0
    )
    if max_layer <= 1 or total_explores < 5:
        return DAILY_RESEARCH_TASK_BY_KEY["explore_layer1_2"]

    fuse_count = int(
        db.execute(
            "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
            (int(user_id), EVENT_FUSE),
        ).fetchone()["c"]
        or 0
    )
    inventory_count = int(
        db.execute(
            "SELECT COUNT(*) AS c FROM part_instances WHERE user_id = ? AND status = 'inventory'",
            (int(user_id),),
        ).fetchone()["c"]
        or 0
    )
    if fuse_count < 2 and inventory_count >= 2:
        return DAILY_RESEARCH_TASK_BY_KEY["strengthen_1"]

    eligible = [
        DAILY_RESEARCH_TASK_BY_KEY["explore_layer1_2"],
        DAILY_RESEARCH_TASK_BY_KEY["strengthen_1"],
        DAILY_RESEARCH_TASK_BY_KEY["build_view_1"],
        DAILY_RESEARCH_TASK_BY_KEY["world_view_1"],
    ]
    if max_layer >= 2:
        eligible.append(DAILY_RESEARCH_TASK_BY_KEY["explore_layer2_1"])
    if not active_robot_id:
        eligible = [
            DAILY_RESEARCH_TASK_BY_KEY["explore_layer1_2"],
            DAILY_RESEARCH_TASK_BY_KEY["build_view_1"],
            DAILY_RESEARCH_TASK_BY_KEY["world_view_1"],
        ]
    seed = f"{int(user_id)}:{today_key}".encode("utf-8")
    index = int(hashlib.sha256(seed).hexdigest()[:8], 16) % len(eligible)
    return eligible[index]


def get_or_create_daily_task(db, user_id, today_key):
    row = db.execute(
        "SELECT * FROM daily_research_tasks WHERE user_id = ? AND day_key = ? LIMIT 1",
        (int(user_id), str(today_key)),
    ).fetchone()
    if row:
        return _row_to_task(row)

    task = _choose_task(db, user_id, today_key)
    db.execute(
        """
        INSERT OR IGNORE INTO daily_research_tasks
        (user_id, day_key, task_key, title, description, target_event, target_count, reward_coins)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(user_id),
            str(today_key),
            task["key"],
            task["title"],
            task["description"],
            task["target_event"],
            int(task["target_count"]),
            int(task["reward_coins"]),
        ),
    )
    row = db.execute(
        "SELECT * FROM daily_research_tasks WHERE user_id = ? AND day_key = ? LIMIT 1",
        (int(user_id), str(today_key)),
    ).fetchone()
    created = _row_to_task(row)
    if created:
        _audit(
            db,
            DAILY_RESEARCH_TASK_CREATE,
            user_id,
            {
                "day_key": str(today_key),
                "task_id": int(created["id"]),
                "task_key": created["task_key"],
                "target_event": created["target_event"],
                "target_count": int(created["target_count"]),
                "reward_coins": int(created["reward_coins"]),
            },
            action_key="daily_research.task.create",
            entity_type="daily_research_task",
            entity_id=int(created["id"]),
        )
    return created


def _task_event_matches(task_row, event_type, payload=None):
    if str(task_row["target_event"]) != str(event_type):
        return False
    task = DAILY_RESEARCH_TASK_BY_KEY.get(str(task_row["task_key"] or ""))
    target_area_key = task.get("target_area_key") if task else None
    if not target_area_key:
        return True
    event_area_key = str((payload or {}).get("area_key") or "").strip()
    return event_area_key == str(target_area_key)


def update_daily_task_progress(db, user_id, event_type, payload=None):
    if not user_id or event_type not in DAILY_RESEARCH_TASK_EVENTS:
        return None
    today_key = get_day_key()
    row = db.execute(
        """
        SELECT * FROM daily_research_tasks
        WHERE user_id = ? AND day_key = ? AND status = 'active'
        LIMIT 1
        """,
        (int(user_id), today_key),
    ).fetchone()
    if not row or not _task_event_matches(row, event_type, payload=payload):
        return None
    before_count = int(row["current_count"] or 0)
    next_count = before_count + 1
    target_count = int(row["target_count"] or 1)
    reached_target = next_count >= target_count
    next_status = "claimed" if reached_target else "active"
    completed_at = datetime.now(JST).isoformat(timespec="seconds") if reached_target else None
    reward_coins = int(row["reward_coins"] or 0)
    db.execute(
        """
        UPDATE daily_research_tasks
        SET current_count = ?,
            status = ?,
            completed_at = COALESCE(completed_at, ?),
            claimed_at = CASE WHEN ? = 'claimed' THEN COALESCE(claimed_at, CURRENT_TIMESTAMP) ELSE claimed_at END,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND status = 'active'
        """,
        (int(next_count), next_status, completed_at, next_status, int(row["id"])),
    )
    updated = int(db.execute("SELECT changes() AS c").fetchone()["c"] or 0)
    if not updated:
        return None
    payload = {
        "task_date": today_key,
        "day_key": today_key,
        "task_id": int(row["id"]),
        "task_key": row["task_key"],
        "progress": int(next_count),
        "current_count": int(next_count),
        "target": int(target_count),
        "target_count": int(target_count),
        "reward_coins": int(reward_coins),
    }
    _audit(
        db,
        DAILY_RESEARCH_TASK_PROGRESS,
        user_id,
        payload,
        action_key="daily_research.task.progress",
        entity_type="daily_research_task",
        entity_id=int(row["id"]),
    )
    if reached_target:
        if reward_coins > 0:
            db.execute("UPDATE users SET coins = COALESCE(coins, 0) + ? WHERE id = ?", (reward_coins, int(user_id)))
        _audit(
            db,
            DAILY_RESEARCH_TASK_COMPLETE,
            user_id,
            payload,
            action_key="daily_research.task.complete",
            entity_type="daily_research_task",
            entity_id=int(row["id"]),
        )
        _audit(
            db,
            DAILY_RESEARCH_TASK_CLAIM,
            user_id,
            payload,
            action_key="daily_research.claim",
            entity_type="daily_research_task",
            entity_id=int(row["id"]),
            delta_coins=reward_coins,
        )
        return {"completed": True, "claimed": True, "reward_coins": reward_coins, "task_key": row["task_key"]}
    return {"completed": False, "claimed": False, "reward_coins": 0, "task_key": row["task_key"]}


def claim_daily_task_reward(db, user_id, task_id):
    row = db.execute(
        "SELECT * FROM daily_research_tasks WHERE id = ? AND user_id = ? LIMIT 1",
        (int(task_id), int(user_id)),
    ).fetchone()
    if not row or str(row["status"]) != "completed":
        return {"ok": False, "reason": "not_completed"}
    reward_coins = int(row["reward_coins"] or 0)
    db.execute("UPDATE users SET coins = COALESCE(coins, 0) + ? WHERE id = ?", (reward_coins, int(user_id)))
    db.execute(
        """
        UPDATE daily_research_tasks
        SET status = 'claimed', claimed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ? AND status = 'completed'
        """,
        (int(task_id), int(user_id)),
    )
    _audit(
        db,
        DAILY_RESEARCH_TASK_CLAIM,
        user_id,
        {"task_id": int(task_id), "task_key": row["task_key"], "reward_coins": reward_coins},
        action_key="daily_research.task.claim",
        entity_type="daily_research_task",
        entity_id=int(task_id),
        delta_coins=reward_coins,
    )
    return {"ok": True, "reward_coins": reward_coins, "task_key": row["task_key"]}


def build_yesterday_report(db, user_id, today_key):
    day_key = _prev_day_key(today_key)
    counts = {
        "explore_count": _event_count(db, user_id, EVENT_EXPLORE_END, day_key),
        "drop_count": _event_count(db, user_id, EVENT_DROP, day_key),
        "strengthen_count": _event_count(db, user_id, EVENT_FUSE, day_key),
        "evolve_count": _event_count(db, user_id, EVENT_PART_EVOLVE, day_key),
        "build_count": _event_count(db, user_id, EVENT_BUILD_CONFIRM, day_key),
        "boss_encounter_count": _event_count(db, user_id, EVENT_BOSS_ENCOUNTER, day_key),
        "boss_defeat_count": _event_count(db, user_id, EVENT_BOSS_DEFEAT, day_key),
    }
    if sum(counts.values()) <= 0:
        return None
    if counts["strengthen_count"] == 0 and counts["explore_count"] >= 3:
        suggestion = "次は、拾ったパーツを1つ強化してみると良さそうです。"
    elif counts["build_count"] == 0 and counts["drop_count"] > 0:
        suggestion = "持ち帰ったパーツで新しいロボを組み立ててみましょう。"
    elif counts["boss_encounter_count"] > 0 and counts["boss_defeat_count"] == 0:
        suggestion = "ボス反応がありました。少し強化して再挑戦してみましょう。"
    else:
        suggestion = "今日も少しずつ研究データを集めていきましょう。"
    return {"day_key": day_key, **counts, "suggestion": suggestion}


def ensure_tomorrow_research_reward(db, user_id, today_key):
    explore_count = _event_count(db, user_id, EVENT_EXPLORE_END, today_key)
    fuse_count = _event_count(db, user_id, EVENT_FUSE, today_key)
    build_count = _event_count(db, user_id, EVENT_BUILD_CONFIRM, today_key)
    if explore_count < 3 and fuse_count < 1 and build_count < 1:
        return None
    if explore_count >= 10 or fuse_count >= 2:
        reward_coins = 200
    elif explore_count >= 5 or fuse_count >= 1:
        reward_coins = 150
    else:
        reward_coins = 100
    claim_day_key = _next_day_key(today_key)
    before_row = db.execute(
        "SELECT * FROM daily_research_rewards WHERE user_id = ? AND source_day_key = ? LIMIT 1",
        (int(user_id), str(today_key)),
    ).fetchone()
    db.execute(
        """
        INSERT OR IGNORE INTO daily_research_rewards
        (user_id, source_day_key, claim_day_key, reward_coins, core_progress_delta, reason)
        VALUES (?, ?, ?, ?, 0, ?)
        """,
        (int(user_id), str(today_key), claim_day_key, int(reward_coins), "今日の研究データ解析"),
    )
    row = db.execute(
        "SELECT * FROM daily_research_rewards WHERE user_id = ? AND source_day_key = ? LIMIT 1",
        (int(user_id), str(today_key)),
    ).fetchone()
    if row and int(row["reward_coins"] or 0) < reward_coins and str(row["status"]) == "pending":
        db.execute(
            """
            UPDATE daily_research_rewards
            SET reward_coins = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'pending'
            """,
            (int(reward_coins), int(row["id"])),
        )
        row = db.execute("SELECT * FROM daily_research_rewards WHERE id = ?", (int(row["id"]),)).fetchone()
    should_audit = bool(
        row
        and (
            before_row is None
            or int(before_row["reward_coins"] or 0) != int(row["reward_coins"] or 0)
            or str(before_row["status"] or "") != str(row["status"] or "")
        )
    )
    if row and should_audit:
        _audit(
            db,
            DAILY_RESEARCH_REWARD_RESERVE,
            user_id,
            {
                "reward_id": int(row["id"]),
                "source_day_key": str(today_key),
                "claim_day_key": str(row["claim_day_key"]),
                "reward_coins": int(row["reward_coins"] or 0),
                "core_progress_delta": int(row["core_progress_delta"] or 0),
            },
            action_key="daily_research.reward.reserve",
            entity_type="daily_research_reward",
            entity_id=int(row["id"]),
        )
    return dict(row) if row else None


def claim_pending_research_rewards(db, user_id, today_key):
    rows = db.execute(
        """
        SELECT *
        FROM daily_research_rewards
        WHERE user_id = ? AND claim_day_key <= ? AND status = 'pending'
        ORDER BY source_day_key ASC, id ASC
        """,
        (int(user_id), str(today_key)),
    ).fetchall()
    claimed = []
    for row in rows:
        reward_coins = int(row["reward_coins"] or 0)
        if reward_coins > 0:
            db.execute("UPDATE users SET coins = COALESCE(coins, 0) + ? WHERE id = ?", (reward_coins, int(user_id)))
        db.execute(
            """
            UPDATE daily_research_rewards
            SET status = 'claimed', claimed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'pending'
            """,
            (int(row["id"]),),
        )
        item = {
            "reward_id": int(row["id"]),
            "source_day_key": str(row["source_day_key"]),
            "reward_coins": reward_coins,
            "core_progress_delta": int(row["core_progress_delta"] or 0),
            "reason": row["reason"],
        }
        claimed.append(item)
        _audit(
            db,
            DAILY_RESEARCH_REWARD_CLAIM,
            user_id,
            item,
            action_key="daily_research.reward.claim",
            entity_type="daily_research_reward",
            entity_id=int(row["id"]),
            delta_coins=reward_coins,
        )
    return claimed


def should_show_daily_research_modal(db, user_id, today_key, modal_payload):
    user = db.execute("SELECT last_daily_research_modal_day FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if user and str(user["last_daily_research_modal_day"] or "") == str(today_key):
        return False
    if not modal_payload:
        return False
    return bool(
        modal_payload.get("claimed_rewards")
        or modal_payload.get("yesterday_report")
        or modal_payload.get("daily_task")
    )


def mark_daily_research_modal_viewed(db, user_id, today_key, modal_payload=None):
    db.execute(
        "UPDATE users SET last_daily_research_modal_day = ? WHERE id = ?",
        (str(today_key), int(user_id)),
    )
    payload = modal_payload or {}
    _audit(
        db,
        DAILY_RESEARCH_MODAL_VIEW,
        user_id,
        {
            "day_key": str(today_key),
            "has_claimed_rewards": bool(payload.get("claimed_rewards")),
            "has_yesterday_report": bool(payload.get("yesterday_report")),
            "has_daily_task": bool(payload.get("daily_task")),
        },
        action_key="daily_research.modal.view",
        entity_type="daily_research_modal",
    )
