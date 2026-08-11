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
EVENT_ANOMALY_ATTEMPT = "audit.anomaly.attempt"

DAILY_RESEARCH_TASK_CREATE = "audit.daily_research.task.create"
DAILY_RESEARCH_TASK_PROGRESS = "audit.daily_research.progress"
DAILY_RESEARCH_TASK_COMPLETE = "audit.daily_research.complete"
DAILY_RESEARCH_TASK_CLAIM = "audit.daily_research.reward"
DAILY_RESEARCH_REWARD_RESERVE = "audit.daily_research.reward.reserve"
DAILY_RESEARCH_REWARD_CLAIM = "audit.daily_research.reward.claim"
DAILY_RESEARCH_MODAL_VIEW = "audit.daily_research.modal.view"
DAILY_RESEARCH_VIEW = "audit.daily_research.view"

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
    EVENT_ANOMALY_ATTEMPT,
}
DAILY_RESEARCH_REWARD_SOURCE_EVENTS = set()

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
DAILY_RESEARCH_MISSION_COIN_REWARD = 25
DAILY_RESEARCH_ALL_COMPLETE_COIN_REWARD = 50
DAILY_RESEARCH_MISSION_POOLS = {
    "sortie": [
        {
            "key": "patrol_sortie_3",
            "title": "巡回試験",
            "description": "戦場データが不足している。3回の出撃記録を提出せよ。",
            "mission_type": "sortie",
            "condition": "explore_complete",
            "target": 3,
            "reward_coins": 20,
        },
        {
            "key": "victory_data_5",
            "title": "勝利記録試験",
            "description": "任意の区画で勝利ログを5件集めよ。",
            "mission_type": "sortie",
            "condition": "win_any",
            "target": 5,
            "reward_coins": 25,
        },
        {
            "key": "same_area_patrol_3",
            "title": "定点巡回試験",
            "description": "同じ区画を3回巡回し、環境差分を記録せよ。",
            "mission_type": "sortie",
            "condition": "same_area_explore",
            "target": 3,
            "reward_coins": 20,
        },
        {
            "key": "different_area_2",
            "title": "比較巡回試験",
            "description": "異なる2区画へ出撃し、反応差を比較せよ。",
            "mission_type": "sortie",
            "condition": "distinct_area_explore",
            "target": 2,
            "reward_coins": 20,
        },
    ],
    "training": [
        {
            "key": "strengthen_process_1",
            "title": "強化試験",
            "description": "旧パーツを再利用し、強化工程を1回完了せよ。",
            "mission_type": "training",
            "condition": "strengthen",
            "target": 1,
            "reward_coins": 25,
        },
        {
            "key": "build_update_1",
            "title": "編成試験",
            "description": "機体構成を1回更新し、比較用の設計記録を残せ。",
            "mission_type": "training",
            "condition": "build_confirm",
            "target": 1,
            "reward_coins": 25,
        },
        {
            "key": "parts_collect_3",
            "title": "回収試験",
            "description": "回収パーツを3個記録し、素材候補を整理せよ。",
            "mission_type": "training",
            "condition": "drop_parts",
            "target": 3,
            "reward_coins": 20,
        },
    ],
    "tendency": [
        {
            "key": "armor_tendency_win_3",
            "title": "重装試験",
            "description": "装甲系統の挙動を再検証する。耐久寄り区画で戦闘データを採取せよ。",
            "mission_type": "tendency",
            "condition": "tendency_win",
            "tendency_key": "defense",
            "fallback_area_key": "layer_1",
            "target": 3,
            "reward_coins": 25,
        },
        {
            "key": "aim_tendency_win_3",
            "title": "照準試験",
            "description": "照準系統の反応を確認する。命中寄り区画で勝利記録を集めよ。",
            "mission_type": "tendency",
            "condition": "tendency_win",
            "tendency_key": "accuracy",
            "fallback_area_key": "layer_1",
            "target": 3,
            "reward_coins": 25,
        },
        {
            "key": "overload_tendency_win_3",
            "title": "過負荷試験",
            "description": "攻撃・会心寄り区画で出力変化を観測せよ。",
            "mission_type": "tendency",
            "condition": "tendency_win",
            "tendency_key": "attack",
            "fallback_area_key": "layer_1",
            "target": 3,
            "reward_coins": 25,
        },
    ],
    "anomaly": [
        {
            "key": "anomaly_observe_1",
            "title": "異常反応観測",
            "description": "今週の異常個体へ1回挑戦し、解析ログを提出せよ。",
            "mission_type": "anomaly",
            "condition": "anomaly_attempt",
            "target": 1,
            "reward_coins": 25,
        },
    ],
}
DAILY_RESEARCH_MISSION_BY_KEY = {
    mission["key"]: mission
    for missions in DAILY_RESEARCH_MISSION_POOLS.values()
    for mission in missions
}
DAILY_RESEARCH_AREA_TENDENCY = {
    "layer_1": {"defense", "accuracy", "attack"},
    "layer_2": {"attack"},
    "layer_2_mist": {"accuracy"},
    "layer_2_rush": {"attack"},
    "layer_3": {"defense"},
    "layer_3_fortress": {"defense"},
    "layer_3_sniper": {"accuracy"},
    "layer_3_burst": {"attack"},
    "layer_4_forge": {"defense"},
    "layer_4_haze": {"accuracy"},
    "layer_4_burst": {"attack"},
    "layer_5_reboot": {"defense"},
    "layer_5_overdrive": {"accuracy"},
    "layer_5_final": {"defense", "accuracy", "attack"},
    "layer_6_rebuild": {"defense"},
    "layer_6_core": {"accuracy"},
    "layer_6_final": {"defense", "accuracy", "attack"},
    "layer_7_echo": {"accuracy"},
    "layer_7_chaos": {"attack"},
    "layer_7_final": {"defense", "accuracy", "attack"},
}
DAILY_RESEARCH_AREA_LABELS = {
    "layer_1": "第1層",
    "layer_2": "第2層",
    "layer_2_mist": "霧区画",
    "layer_2_rush": "高速区画",
    "layer_3": "第3層",
    "layer_3_fortress": "重装区画",
    "layer_3_sniper": "照準区画",
    "layer_3_burst": "過負荷区画",
    "layer_4_forge": "第4層フォージ",
    "layer_4_haze": "第4層ヘイズ",
    "layer_4_burst": "第4層バースト",
    "layer_5_reboot": "第5層ラビリンス",
    "layer_5_overdrive": "第5層ピナクル",
    "layer_5_final": "第5層最終試験",
    "layer_6_rebuild": "第6層改修深域",
    "layer_6_core": "第6層中核炉心",
    "layer_6_final": "第6層最終試験",
    "layer_7_echo": "第7層深層残響域",
    "layer_7_chaos": "第7層終端暴走域",
    "layer_7_final": "第7層最終試験",
}
MISSION_KEY_ALIASES = {
    "explore_layer1_2": "patrol_sortie_3",
    "explore_layer2_1": "patrol_sortie_3",
    "strengthen_1": "strengthen_process_1",
    "build_view_1": "build_update_1",
    "world_view_1": "patrol_sortie_3",
}
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


def _audit(db, event_type, user_id, payload=None, action_key=None, entity_type=None, entity_id=None, delta_coins=None, request_id=None):
    try:
        db.execute(
            """
            INSERT INTO world_events_log
            (created_at, event_type, payload_json, user_id, request_id, action_key, entity_type, entity_id, delta_coins)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(time.time()),
                str(event_type),
                json.dumps(payload or {}, ensure_ascii=False),
                int(user_id) if user_id is not None else None,
                str(request_id) if request_id else None,
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


def _stable_index(seed_text, length):
    return int(hashlib.sha256(str(seed_text).encode("utf-8")).hexdigest()[:8], 16) % max(1, int(length))


def get_daily_research_missions(day_key=None):
    day_key = str(day_key or get_day_key())
    mission_types = ["sortie", "training", "tendency"]
    missions = []
    for mission_type in mission_types:
        pool = DAILY_RESEARCH_MISSION_POOLS[mission_type]
        missions.append(dict(pool[_stable_index(f"{day_key}:{mission_type}", len(pool))]))
    return missions


def _user_max_layer(user_row):
    if not user_row:
        return 1
    try:
        return max(1, int(user_row["max_unlocked_layer"] or 1))
    except Exception:
        return 1


def _area_layer(area_key):
    key = str(area_key or "")
    if key.startswith("layer_"):
        try:
            return int(key.split("_")[1])
        except Exception:
            return 1
    return 1


def _best_unlocked_tendency_area(tendency_key, max_layer):
    candidates = []
    for area_key, tendencies in DAILY_RESEARCH_AREA_TENDENCY.items():
        if str(tendency_key) in tendencies and _area_layer(area_key) <= int(max_layer):
            candidates.append(area_key)
    if not candidates:
        return "layer_1"
    candidates.sort(key=lambda key: (_area_layer(key), key))
    return candidates[-1]


def _mission_for_user(db, user_id, mission):
    user = db.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
    max_layer = _user_max_layer(user)
    item = dict(mission or {})
    if item.get("condition") == "tendency_win":
        area_key = _best_unlocked_tendency_area(item.get("tendency_key"), max_layer)
        if _area_layer(area_key) > max_layer:
            area_key = str(item.get("fallback_area_key") or "layer_1")
        item["target_area_key"] = area_key
        if area_key == "layer_1":
            item["title"] = "基礎" + str(item.get("title") or "研究試験")
            item["description"] = "まず第1層で基礎データを採取せよ。未解放区画の代替試験として扱う。"
        else:
            item["description"] = f"{DAILY_RESEARCH_AREA_LABELS.get(area_key, area_key)}で戦闘データを採取せよ。"
    return item


def _anomaly_daily_eligible(db, user_id):
    try:
        release = db.execute("SELECT is_public FROM release_flags WHERE key = 'anomaly' LIMIT 1").fetchone()
        if not release or int(release["is_public"] or 0) != 1:
            return False
        user = db.execute("SELECT is_admin FROM users WHERE id = ?", (int(user_id),)).fetchone()
        if user and int(user["is_admin"] or 0) == 1:
            return True
        explores = db.execute(
            "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
            (int(user_id), EVENT_EXPLORE_END),
        ).fetchone()
        return int((explores or {})["c"] or 0) >= 3
    except Exception:
        return False


def ensure_daily_research_progress_schema(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_research_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            day_key TEXT NOT NULL,
            mission_key TEXT NOT NULL,
            mission_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            condition_key TEXT NOT NULL,
            target INTEGER NOT NULL DEFAULT 1,
            progress INTEGER NOT NULL DEFAULT 0,
            reward_coins INTEGER NOT NULL DEFAULT 0,
            completed_at INTEGER,
            reward_claimed_at INTEGER,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            UNIQUE(user_id, day_key, mission_key)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_research_progress_receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            day_key TEXT NOT NULL,
            mission_key TEXT NOT NULL,
            source_key TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            UNIQUE(user_id, day_key, mission_key, source_key)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_research_day_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            day_key TEXT NOT NULL,
            completed_count INTEGER NOT NULL DEFAULT 0,
            two_completed_at INTEGER,
            all_completed_at INTEGER,
            all_reward_claimed_at INTEGER,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            UNIQUE(user_id, day_key)
        )
        """
    )
    user_cols = {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}
    if "daily_research_streak" not in user_cols:
        db.execute("ALTER TABLE users ADD COLUMN daily_research_streak INTEGER NOT NULL DEFAULT 0")
    if "daily_research_last_completed_day" not in user_cols:
        db.execute("ALTER TABLE users ADD COLUMN daily_research_last_completed_day TEXT")


def get_or_create_daily_research_missions(db, user_id, day_key=None):
    ensure_daily_research_progress_schema(db)
    day_key = str(day_key or get_day_key())
    now_ts = int(time.time())
    missions = get_daily_research_missions(day_key)
    if _anomaly_daily_eligible(db, user_id) and _stable_index(f"{day_key}:anomaly", 3) == 0:
        missions[-1] = dict(DAILY_RESEARCH_MISSION_POOLS["anomaly"][0])
    for mission in missions:
        item = _mission_for_user(db, user_id, mission)
        db.execute(
            """
            INSERT OR IGNORE INTO daily_research_progress
            (user_id, day_key, mission_key, mission_type, title, description, condition_key, target, reward_coins, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(user_id),
                day_key,
                item["key"],
                item["mission_type"],
                item["title"],
                item.get("description") or "",
                item["condition"],
                int(item.get("target") or 1),
                int(item.get("reward_coins") or DAILY_RESEARCH_MISSION_COIN_REWARD),
                now_ts,
                now_ts,
            ),
        )
    rows = db.execute(
        """
        SELECT *
        FROM daily_research_progress
        WHERE user_id = ? AND day_key = ?
        ORDER BY id ASC
        """,
        (int(user_id), day_key),
    ).fetchall()
    return [daily_research_mission_view(dict(row)) for row in rows]


def _progress_payload(row, before, after, source, reward_coins=0):
    return {
        "day_key": str(row["day_key"]),
        "mission_key": str(row["mission_key"]),
        "mission_type": str(row["mission_type"]),
        "progress_before": int(before),
        "progress_after": int(after),
        "target": int(row["target"] or 1),
        "source": str(source or ""),
        "reward_coins": int(reward_coins or 0),
    }


def _event_win(payload):
    result = (payload or {}).get("result")
    if isinstance(result, dict):
        return bool(result.get("win"))
    return str(result or (payload or {}).get("outcome") or "").lower() in {"win", "勝利", "true", "1"}


def _mission_event_delta(db, user_id, row, event_type, payload):
    condition = str(row["condition_key"] or "")
    if condition == "explore_complete":
        return 1 if str(event_type) == EVENT_EXPLORE_END else 0
    if condition == "win_any":
        return 1 if str(event_type) == EVENT_EXPLORE_END and _event_win(payload) else 0
    if condition == "same_area_explore":
        return 1 if str(event_type) == EVENT_EXPLORE_END else 0
    if condition == "distinct_area_explore":
        return 1 if str(event_type) == EVENT_EXPLORE_END else 0
    if condition == "strengthen":
        return 1 if str(event_type) == EVENT_FUSE else 0
    if condition == "build_confirm":
        return 1 if str(event_type) == EVENT_BUILD_CONFIRM else 0
    if condition == "drop_parts":
        if str(event_type) == EVENT_DROP:
            return max(1, int((payload or {}).get("drop_count") or (payload or {}).get("count") or 1))
        if str(event_type) == EVENT_EXPLORE_END:
            return max(0, int((payload or {}).get("dropped_parts_count") or 0))
    if condition == "tendency_win":
        if str(event_type) != EVENT_EXPLORE_END or not _event_win(payload):
            return 0
        mission = DAILY_RESEARCH_MISSION_BY_KEY.get(str(row["mission_key"]))
        area_key = str((payload or {}).get("area_key") or "").strip()
        tendencies = DAILY_RESEARCH_AREA_TENDENCY.get(area_key, set())
        target_tendency = str((mission or {}).get("tendency_key") or "")
        return 1 if target_tendency in tendencies else 0
    if condition == "anomaly_attempt":
        return 1 if str(event_type) == EVENT_ANOMALY_ATTEMPT else 0
    return 0


def _source_key(event_type, request_id=None, source_event_id=None, payload=None):
    if request_id:
        return f"request:{event_type}:{request_id}"
    if source_event_id:
        return f"event:{event_type}:{source_event_id}"
    payload = payload or {}
    battle_id = payload.get("battle_id") or payload.get("result_id")
    if battle_id:
        return f"battle:{event_type}:{battle_id}"
    return f"fallback:{event_type}:{hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()[:16]}"


def _refresh_day_record(db, user_id, day_key, *, source, request_id=None):
    ensure_daily_research_progress_schema(db)
    now_ts = int(time.time())
    completed_count = int(
        db.execute(
            """
            SELECT COUNT(*) AS c
            FROM daily_research_progress
            WHERE user_id = ? AND day_key = ? AND completed_at IS NOT NULL
            """,
            (int(user_id), str(day_key)),
        ).fetchone()["c"]
        or 0
    )
    db.execute(
        """
        INSERT OR IGNORE INTO daily_research_day_records
        (user_id, day_key, completed_count, created_at, updated_at)
        VALUES (?, ?, 0, ?, ?)
        """,
        (int(user_id), str(day_key), now_ts, now_ts),
    )
    row = db.execute(
        "SELECT * FROM daily_research_day_records WHERE user_id = ? AND day_key = ?",
        (int(user_id), str(day_key)),
    ).fetchone()
    before_completed = int(row["completed_count"] or 0) if row else 0
    updates = ["completed_count = ?", "updated_at = ?"]
    params = [completed_count, now_ts]
    if completed_count >= 2 and row and not row["two_completed_at"]:
        updates.append("two_completed_at = ?")
        params.append(now_ts)
        _audit(
            db,
            DAILY_RESEARCH_TASK_COMPLETE,
            user_id,
            {
                "day_key": str(day_key),
                "mission_key": "daily_research_2_of_3",
                "mission_type": "daily_summary",
                "progress_before": before_completed,
                "progress_after": completed_count,
                "target": 2,
                "source": str(source or ""),
                "reward_coins": 0,
            },
            action_key="daily_research.two_complete",
            entity_type="daily_research_day",
            request_id=request_id,
        )
    all_reward_coins = 0
    if completed_count >= 3 and row and not row["all_completed_at"]:
        updates.extend(["all_completed_at = ?", "all_reward_claimed_at = ?"])
        params.extend([now_ts, now_ts])
        all_reward_coins = DAILY_RESEARCH_ALL_COMPLETE_COIN_REWARD
        db.execute("UPDATE users SET coins = COALESCE(coins, 0) + ? WHERE id = ?", (all_reward_coins, int(user_id)))
        user = db.execute("SELECT daily_research_streak, daily_research_last_completed_day FROM users WHERE id = ?", (int(user_id),)).fetchone()
        previous_day = _prev_day_key(day_key)
        current_streak = int(user["daily_research_streak"] or 0) if user else 0
        next_streak = current_streak + 1 if user and str(user["daily_research_last_completed_day"] or "") == previous_day else 1
        db.execute(
            "UPDATE users SET daily_research_streak = ?, daily_research_last_completed_day = ? WHERE id = ?",
            (int(next_streak), str(day_key), int(user_id)),
        )
        _audit(
            db,
            DAILY_RESEARCH_TASK_CLAIM,
            user_id,
            {
                "day_key": str(day_key),
                "mission_key": "daily_research_all_complete",
                "mission_type": "daily_summary",
                "progress_before": before_completed,
                "progress_after": completed_count,
                "target": 3,
                "source": str(source or ""),
                "reward_coins": all_reward_coins,
                "streak": int(next_streak),
            },
            action_key="daily_research.all_reward",
            entity_type="daily_research_day",
            delta_coins=all_reward_coins,
            request_id=request_id,
        )
    params.extend([int(user_id), str(day_key)])
    db.execute(
        f"""
        UPDATE daily_research_day_records
        SET {', '.join(updates)}
        WHERE user_id = ? AND day_key = ?
        """,
        params,
    )
    return {"completed_count": completed_count, "all_reward_coins": all_reward_coins}


def update_daily_research_progress(db, user_id, event_type, payload=None, request_id=None, source_event_id=None):
    if not user_id or event_type not in DAILY_RESEARCH_TASK_EVENTS:
        return None
    ensure_daily_research_progress_schema(db)
    day_key = get_day_key()
    has_visible_missions = db.execute(
        """
        SELECT 1
        FROM daily_research_progress
        WHERE user_id = ? AND day_key = ?
        LIMIT 1
        """,
        (int(user_id), day_key),
    ).fetchone()
    if not has_visible_missions:
        return {"updates": [], "claimed": None}
    rows = db.execute(
        """
        SELECT *
        FROM daily_research_progress
        WHERE user_id = ? AND day_key = ? AND completed_at IS NULL
        ORDER BY id ASC
        """,
        (int(user_id), day_key),
    ).fetchall()
    source_key = _source_key(event_type, request_id=request_id, source_event_id=source_event_id, payload=payload)
    updates = []
    for row in rows:
        delta = _mission_event_delta(db, user_id, row, event_type, payload or {})
        if delta <= 0:
            continue
        try:
            db.execute(
                """
                INSERT INTO daily_research_progress_receipts
                (user_id, day_key, mission_key, source_key, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (int(user_id), day_key, str(row["mission_key"]), source_key, int(time.time())),
            )
        except Exception:
            continue
        before = int(row["progress"] or 0)
        target = max(1, int(row["target"] or 1))
        after = min(target, before + int(delta))
        completed = after >= target
        reward_coins = int(row["reward_coins"] or 0) if completed else 0
        if completed and reward_coins > 0:
            db.execute("UPDATE users SET coins = COALESCE(coins, 0) + ? WHERE id = ?", (reward_coins, int(user_id)))
        db.execute(
            """
            UPDATE daily_research_progress
            SET progress = ?,
                completed_at = CASE WHEN ? = 1 THEN COALESCE(completed_at, ?) ELSE completed_at END,
                reward_claimed_at = CASE WHEN ? = 1 THEN COALESCE(reward_claimed_at, ?) ELSE reward_claimed_at END,
                updated_at = ?
            WHERE id = ? AND completed_at IS NULL
            """,
            (after, 1 if completed else 0, int(time.time()), 1 if completed else 0, int(time.time()), int(time.time()), int(row["id"])),
        )
        progress_payload = _progress_payload(row, before, after, event_type, reward_coins=0)
        _audit(
            db,
            DAILY_RESEARCH_TASK_PROGRESS,
            user_id,
            progress_payload,
            action_key="daily_research.progress",
            entity_type="daily_research_progress",
            entity_id=int(row["id"]),
            request_id=request_id,
        )
        result = {"mission_key": str(row["mission_key"]), "title": str(row["title"]), "progress": after, "target": target, "completed": completed, "reward_coins": reward_coins}
        if completed:
            complete_payload = _progress_payload(row, before, after, event_type, reward_coins=reward_coins)
            _audit(
                db,
                DAILY_RESEARCH_TASK_COMPLETE,
                user_id,
                complete_payload,
                action_key="daily_research.complete",
                entity_type="daily_research_progress",
                entity_id=int(row["id"]),
                request_id=request_id,
            )
            _audit(
                db,
                DAILY_RESEARCH_TASK_CLAIM,
                user_id,
                complete_payload,
                action_key="daily_research.reward",
                entity_type="daily_research_progress",
                entity_id=int(row["id"]),
                delta_coins=reward_coins,
                request_id=request_id,
            )
        updates.append(result)
    if updates:
        day_record = _refresh_day_record(db, int(user_id), day_key, source=event_type, request_id=request_id)
        return {"updated": updates, "claimed": any(item["completed"] for item in updates), "day_record": day_record}
    return None


def daily_research_mission_view(row):
    data = dict(row)
    target = max(1, int(data.get("target") or data.get("target_count") or 1))
    progress = min(target, int(data.get("progress") or data.get("current_count") or 0))
    completed = bool(data.get("completed_at")) or str(data.get("status") or "") in {"completed", "claimed"}
    return {
        "id": int(data.get("id") or 0),
        "mission_key": str(data.get("mission_key") or data.get("task_key") or ""),
        "task_key": str(data.get("mission_key") or data.get("task_key") or ""),
        "mission_type": str(data.get("mission_type") or "daily"),
        "title": str(data.get("title") or "今日の研究指令"),
        "description": str(data.get("description") or ""),
        "progress": progress,
        "target": target,
        "target_count": target,
        "progress_line": f"{progress}/{target}",
        "reward_coins": int(data.get("reward_coins") or 0),
        "is_done": bool(completed),
        "is_completed": bool(completed),
        "is_claimed": bool(data.get("reward_claimed_at") or str(data.get("status") or "") == "claimed"),
        "status": "claimed" if completed else "active",
    }


def daily_research_home_summary(db, user_id, day_key=None):
    missions = get_or_create_daily_research_missions(db, user_id, day_key or get_day_key())
    done_count = sum(1 for item in missions if item["is_done"])
    user = db.execute("SELECT daily_research_streak FROM users WHERE id = ?", (int(user_id),)).fetchone()
    return {
        "day_key": str(day_key or get_day_key()),
        "missions": missions,
        "done_count": int(done_count),
        "total_count": len(missions),
        "title": f"今日の研究指令 {done_count}/{len(missions)}",
        "streak": int(user["daily_research_streak"] or 0) if user and "daily_research_streak" in user.keys() else 0,
    }


def daily_research_admin_summary(db, day_key=None):
    ensure_daily_research_progress_schema(db)
    day_key = str(day_key or get_day_key())
    missions = get_daily_research_missions(day_key)
    rows = []
    for mission in missions:
        row = db.execute(
            """
            SELECT COUNT(*) AS viewed_users,
                   SUM(CASE WHEN completed_at IS NOT NULL THEN 1 ELSE 0 END) AS completed_users,
                   AVG(CAST(progress AS REAL)) AS avg_progress
            FROM daily_research_progress
            WHERE day_key = ? AND mission_key = ?
            """,
            (day_key, mission["key"]),
        ).fetchone()
        target = int(mission.get("target") or 1)
        rows.append(
            {
                **mission,
                "viewed_users": int(row["viewed_users"] or 0) if row else 0,
                "completed_users": int(row["completed_users"] or 0) if row else 0,
                "avg_progress": float(row["avg_progress"] or 0.0) if row else 0.0,
                "target": target,
            }
        )
    two = db.execute(
        "SELECT COUNT(*) AS c FROM daily_research_day_records WHERE day_key = ? AND completed_count >= 2",
        (day_key,),
    ).fetchone()
    three = db.execute(
        "SELECT COUNT(*) AS c FROM daily_research_day_records WHERE day_key = ? AND completed_count >= 3",
        (day_key,),
    ).fetchone()
    progressed = db.execute(
        "SELECT COUNT(DISTINCT user_id) AS c FROM daily_research_progress WHERE day_key = ? AND progress > 0",
        (day_key,),
    ).fetchone()
    one_complete = db.execute(
        "SELECT COUNT(DISTINCT user_id) AS c FROM daily_research_progress WHERE day_key = ? AND completed_at IS NOT NULL",
        (day_key,),
    ).fetchone()
    viewed = db.execute(
        "SELECT COUNT(DISTINCT user_id) AS c FROM daily_research_progress WHERE day_key = ?",
        (day_key,),
    ).fetchone()
    return {
        "day_key": day_key,
        "missions": rows,
        "viewed_users": int(viewed["c"] or 0) if viewed else 0,
        "progressed_users": int(progressed["c"] or 0) if progressed else 0,
        "one_complete_users": int(one_complete["c"] or 0) if one_complete else 0,
        "two_complete_users": int(two["c"] or 0) if two else 0,
        "all_complete_users": int(three["c"] or 0) if three else 0,
    }


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
    missions = get_or_create_daily_research_missions(db, user_id, today_key)
    return missions[0] if missions else None


def get_or_create_daily_tasks(db, user_id, today_key):
    return get_or_create_daily_research_missions(db, user_id, today_key)


def get_or_create_legacy_daily_task(db, user_id, today_key):
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
    return update_daily_research_progress(db, user_id, event_type, payload=payload)


def update_legacy_daily_task_progress(db, user_id, event_type, payload=None):
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
