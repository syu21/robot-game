import copy
import json
import time
from datetime import datetime, timedelta, timezone

from constants import AUDIT_EVENT_TYPES


JST = timezone(timedelta(hours=9))
PRESENCE_STATE_LABELS = {
    "exploring": "出撃中",
    "lab": "実験室参加中",
    "comms": "会議室参加中",
    "home": "探索待機中",
    "idle_recent": "さっきまで参加",
}
HOME_SURFACES = {"home", "parts", "build", "world", "records", "showcase"}
RECENT_HOME_ROBOT_LIMIT = 8
RECENT_HOME_ROBOT_CACHE_TTL_SECONDS = 60
RECENT_HOME_MAIN_WINDOW_SECONDS = 72 * 60 * 60
RECENT_HOME_FALLBACK_WINDOW_SECONDS = 7 * 24 * 60 * 60
RECENT_HOME_ACTIVITY_EVENTS = (
    AUDIT_EVENT_TYPES["EXPLORE_START"],
    AUDIT_EVENT_TYPES["EXPLORE_END"],
    AUDIT_EVENT_TYPES["FUSE"],
    AUDIT_EVENT_TYPES["PART_EVOLVE"],
    AUDIT_EVENT_TYPES["BUILD_CONFIRM"],
    AUDIT_EVENT_TYPES["BOSS_ENCOUNTER"],
    AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
    AUDIT_EVENT_TYPES["CHAT_POST"],
    AUDIT_EVENT_TYPES["CHAMPION_DEFEAT"],
    "CHAMPION_DEFEATED",
)
RECENT_HOME_EXPLORE_EVENTS = (
    AUDIT_EVENT_TYPES["EXPLORE_START"],
    AUDIT_EVENT_TYPES["EXPLORE_END"],
)
RECENT_HOME_WORLD_EVENTS = tuple(
    dict.fromkeys(
        (
            "RESEARCH_UNLOCK",
            "CHAMPION_SELECTED",
            "CHAMPION_DEFEATED",
            AUDIT_EVENT_TYPES["CHAMPION_SELECT"],
            AUDIT_EVENT_TYPES["CHAMPION_DEFEAT"],
            "CHAMPION_DEFEATED",
            AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
            AUDIT_EVENT_TYPES["BOSS_ENCOUNTER"],
            AUDIT_EVENT_TYPES["PART_EVOLVE"],
            AUDIT_EVENT_TYPES["EXPLORE_END"],
            AUDIT_EVENT_TYPES["STYLE_RANK_UP"],
        )
    )
)
RECENT_HOME_REPRESENTATIVE_EVENTS = tuple(
    dict.fromkeys(
        (
            AUDIT_EVENT_TYPES["CHAMPION_DEFEAT"],
            "CHAMPION_DEFEATED",
            "RESEARCH_UNLOCK",
            AUDIT_EVENT_TYPES["STYLE_RANK_UP"],
            AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
            AUDIT_EVENT_TYPES["BOSS_ENCOUNTER"],
            AUDIT_EVENT_TYPES["PART_EVOLVE"],
            AUDIT_EVENT_TYPES["FUSE"],
            AUDIT_EVENT_TYPES["BUILD_CONFIRM"],
            AUDIT_EVENT_TYPES["EXPLORE_END"],
            AUDIT_EVENT_TYPES["EXPLORE_START"],
        )
    )
)
RECENT_HOME_STATUS_LABELS = {
    "exploring": "出撃中",
    "returned": "探索帰還",
    "fuse_success": "強化成功",
    "evolve_success": "進化完了",
    "build_update": "編成更新",
    "boss_found": "ボス遭遇",
    "record_update": "記録更新",
    "champion_break": "チャンプ撃破",
    "recent_seen": "最近観測",
    "weekly_hot": "今週活発",
}
RECENT_HOME_STATUS_META = {
    "champion_break": {"priority": 100, "icon": "#"},
    "record_update": {"priority": 90, "icon": "*"},
    "boss_found": {"priority": 80, "icon": "!"},
    "evolve_success": {"priority": 70, "icon": "^"},
    "fuse_success": {"priority": 60, "icon": "+"},
    "build_update": {"priority": 50, "icon": "="},
    "returned": {"priority": 40, "icon": "<"},
    "exploring": {"priority": 30, "icon": ">"},
    "recent_seen": {"priority": 10, "icon": ""},
    "weekly_hot": {"priority": 5, "icon": ""},
}
RECENT_HOME_EXCLUDED_USERNAMES = (
    "admin",
    "administrator",
    "root",
    "system",
    "test",
    "tester",
    "test_user",
)
RECENT_HOME_SUPPORTER_DECOR_KEYS = (
    "lab_badge_gold",
    "founder_badge_silver",
    "shien_trophy",
)
RECENT_HOME_SUPPORTER_PRODUCT_KEYS = (
    "support_pack_lab",
    "support_pack_founder",
    "support_pack_001",
)
_RECENT_HOME_ROBOT_CACHE = {}


def _now_jst(now=None):
    if now is None:
        return datetime.now(JST).replace(microsecond=0)
    if isinstance(now, (int, float)):
        return datetime.fromtimestamp(int(now), JST).replace(microsecond=0)
    if isinstance(now, str):
        parsed = datetime.fromisoformat(now)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=JST)
        return parsed.astimezone(JST).replace(microsecond=0)
    if isinstance(now, datetime):
        if now.tzinfo is None:
            now = now.replace(tzinfo=JST)
        return now.astimezone(JST).replace(microsecond=0)
    return datetime.now(JST).replace(microsecond=0)


def _iso_jst(dt):
    return _now_jst(dt).isoformat(timespec="seconds")


def _row_dict(row):
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    keys = row.keys() if hasattr(row, "keys") else []
    return {key: row[key] for key in keys}


def _parse_presence_time(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST).replace(microsecond=0)


def _minutes_ago(last_active_at, now=None):
    last_dt = _parse_presence_time(last_active_at)
    if not last_dt:
        return 0
    delta = _now_jst(now) - last_dt
    return max(0, int(delta.total_seconds() // 60))


def presence_state_for(surface, action_key=None, minutes_ago=0):
    if int(minutes_ago or 0) > 10:
        return "idle_recent"
    surface_key = str(surface or "").strip().lower()
    action = str(action_key or "").strip().lower()
    if surface_key == "explore" or action.startswith("explore."):
        return "exploring"
    if surface_key == "lab" or action.startswith("lab."):
        return "lab"
    if surface_key == "comms" or action.startswith("chat.") or action.startswith("comms."):
        return "comms"
    if surface_key in HOME_SURFACES:
        return "home"
    return "home"


def presence_tone(minutes_ago):
    minutes = max(0, int(minutes_ago or 0))
    if minutes <= 5:
        return "active"
    if minutes <= 10:
        return "warm"
    return "idle"


def touch_presence(
    db,
    user_id,
    surface,
    action_key,
    path=None,
    room_key=None,
    robot_instance_id=None,
    now=None,
):
    uid = int(user_id or 0)
    if uid <= 0:
        return None
    timestamp = _iso_jst(_now_jst(now))
    surface_key = str(surface or "").strip().lower()[:40]
    action = str(action_key or "").strip()[:80]
    clean_path = str(path or "").strip()[:240] or None
    clean_room = str(room_key or "").strip()[:80] or None
    rid = int(robot_instance_id) if str(robot_instance_id or "").isdigit() else None
    db.execute(
        """
        INSERT INTO user_presence
            (user_id, last_active_at, last_surface, last_action_key, last_path,
             last_room_key, last_robot_instance_id, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            last_active_at = excluded.last_active_at,
            last_surface = excluded.last_surface,
            last_action_key = excluded.last_action_key,
            last_path = excluded.last_path,
            last_room_key = excluded.last_room_key,
            last_robot_instance_id = excluded.last_robot_instance_id,
            updated_at = excluded.updated_at
        """,
        (uid, timestamp, surface_key, action, clean_path, clean_room, rid, timestamp),
    )
    return timestamp


def get_presence_count(db, within_minutes=20, include_admin=False, now=None):
    current = _now_jst(now)
    cutoff = _iso_jst(current - timedelta(minutes=max(1, int(within_minutes or 20))))
    admin_clause = "" if include_admin else "AND COALESCE(u.is_admin, 0) = 0"
    row = db.execute(
        f"""
        SELECT COUNT(*) AS c
        FROM user_presence up
        JOIN users u ON u.id = up.user_id
        WHERE up.last_active_at >= ?
          AND COALESCE(u.is_banned, 0) = 0
          {admin_clause}
        """,
        (cutoff,),
    ).fetchone()
    return int((row["c"] if row else 0) or 0)


def get_recent_presence(db, limit=12, within_minutes=20, include_admin=False, now=None):
    current = _now_jst(now)
    cutoff = _iso_jst(current - timedelta(minutes=max(1, int(within_minutes or 20))))
    fetch_limit = max(1, min(int(limit or 12), 24))
    admin_clause = "" if include_admin else "AND COALESCE(u.is_admin, 0) = 0"
    rows = db.execute(
        f"""
        SELECT
            up.user_id,
            up.last_active_at,
            up.last_surface,
            up.last_action_key,
            up.last_path,
            up.last_room_key,
            up.last_robot_instance_id,
            u.username,
            u.display_name,
            u.avatar_path,
            u.active_robot_id,
            u.is_admin,
            ri.icon_32_path AS robot_icon_32_path,
            ri.composed_image_path AS robot_composed_image_path,
            ri.updated_at AS robot_updated_at
        FROM user_presence up
        JOIN users u ON u.id = up.user_id
        LEFT JOIN robot_instances ri
          ON ri.id = COALESCE(up.last_robot_instance_id, u.active_robot_id)
         AND ri.user_id = u.id
         AND ri.status = 'active'
        WHERE up.last_active_at >= ?
          AND COALESCE(u.is_banned, 0) = 0
          {admin_clause}
        ORDER BY up.last_active_at DESC, up.user_id DESC
        LIMIT ?
        """,
        (cutoff, fetch_limit),
    ).fetchall()
    return [serialize_presence_entry(row, now=current) for row in rows]


def _sql_placeholders(values):
    return ", ".join("?" for _ in values)


def _home_user_eligibility_sql(user_alias="u", *, include_admin=False):
    admin_clause = "" if include_admin else f"AND COALESCE({user_alias}.is_admin, 0) = 0"
    return f"""
          AND COALESCE({user_alias}.is_banned, 0) = 0
          {admin_clause}
          AND LOWER(COALESCE({user_alias}.username, '')) NOT IN {RECENT_HOME_EXCLUDED_USERNAMES}
          AND LOWER(COALESCE({user_alias}.username, '')) NOT LIKE 'test\\_%' ESCAPE '\\'
          AND LOWER(COALESCE({user_alias}.username, '')) NOT LIKE '%\\_test' ESCAPE '\\'
          AND LOWER(COALESCE({user_alias}.username, '')) NOT LIKE 'admin\\_%' ESCAPE '\\'
    """


def _home_robot_select_columns(user_alias="u", robot_alias="ri"):
    return f"""
            {user_alias}.id AS user_id,
            {user_alias}.username,
            {user_alias}.display_name,
            {user_alias}.avatar_path,
            {user_alias}.active_robot_id,
            COALESCE({user_alias}.is_admin, 0) AS is_admin,
            COALESCE({user_alias}.is_banned, 0) AS is_banned,
            {robot_alias}.id AS robot_id,
            {robot_alias}.name AS robot_name,
            {robot_alias}.icon_32_path AS robot_icon_32_path,
            {robot_alias}.composed_image_path AS robot_composed_image_path,
            {robot_alias}.updated_at AS robot_updated_at,
            {robot_alias}.style_key AS robot_style_key
    """


def _db_cache_key(db):
    try:
        rows = db.execute("PRAGMA database_list").fetchall()
        parts = []
        for row in rows:
            data = _row_dict(row)
            parts.append(str(data.get("file") or ""))
        return "|".join(parts) or str(id(db))
    except Exception:
        return str(id(db))


def _week_bounds_for_ts(current_ts):
    dt = datetime.fromtimestamp(int(current_ts), JST)
    iso = dt.isocalendar()
    start = datetime.fromisocalendar(iso.year, iso.week, 1).replace(tzinfo=JST)
    end = start + timedelta(days=7)
    return int(start.timestamp()), int(end.timestamp()), f"{iso.year}-W{iso.week:02d}"


def _presence_datetime_ts(value):
    parsed = _parse_presence_time(value)
    return int(parsed.timestamp()) if parsed else 0


def _safe_json_loads(raw_value):
    try:
        data = json.loads(raw_value or "{}")
    except (TypeError, json.JSONDecodeError):
        data = {}
    return data if isinstance(data, dict) else {}


def _home_status_meta(status_key):
    return RECENT_HOME_STATUS_META.get(str(status_key or ""), RECENT_HOME_STATUS_META["weekly_hot"])


def _home_status_label(status_key):
    return RECENT_HOME_STATUS_LABELS.get(str(status_key or ""), RECENT_HOME_STATUS_LABELS["weekly_hot"])


def _home_event_action_from_row(row):
    data = _row_dict(row)
    event_type = str(data.get("event_type") or "").strip()
    payload = _safe_json_loads(data.get("payload_json"))
    created_at = int(data.get("created_at") or 0)
    row_id = int(data.get("id") or 0)
    status_key = None
    if event_type in {AUDIT_EVENT_TYPES["CHAMPION_DEFEAT"], "CHAMPION_DEFEATED"}:
        status_key = "champion_break"
    elif event_type in {"RESEARCH_UNLOCK", AUDIT_EVENT_TYPES["STYLE_RANK_UP"]}:
        status_key = "record_update"
    elif event_type == AUDIT_EVENT_TYPES["BOSS_DEFEAT"]:
        status_key = "record_update"
    elif event_type == AUDIT_EVENT_TYPES["BOSS_ENCOUNTER"]:
        status_key = "boss_found"
    elif event_type == AUDIT_EVENT_TYPES["PART_EVOLVE"]:
        status_key = "evolve_success"
    elif event_type == AUDIT_EVENT_TYPES["FUSE"]:
        outcome = str(payload.get("outcome") or "").strip().lower()
        from_plus = int(payload.get("from_plus") or 0)
        to_plus = int(payload.get("to_plus") or payload.get("new_plus") or 0)
        if outcome and outcome not in {"success", "great_success", "great"} and to_plus <= from_plus:
            return None
        status_key = "fuse_success"
    elif event_type == AUDIT_EVENT_TYPES["BUILD_CONFIRM"]:
        status_key = "build_update"
    elif event_type == AUDIT_EVENT_TYPES["EXPLORE_END"]:
        status_key = "returned"
    elif event_type == AUDIT_EVENT_TYPES["EXPLORE_START"]:
        status_key = "exploring"
    if not status_key:
        return None
    meta = _home_status_meta(status_key)
    return {
        "status_key": status_key,
        "status_label": _home_status_label(status_key),
        "status_icon": str(meta.get("icon") or ""),
        "status_priority": int(meta.get("priority") or 0),
        "last_event_at_ts": created_at,
        "last_event_at": _iso_jst(datetime.fromtimestamp(created_at, JST)) if created_at > 0 else "",
        "event_type": event_type,
        "event_id": row_id,
    }


def _merge_home_robot_candidate(
    candidates,
    row,
    *,
    source_key,
    source_rank,
    is_mvp=False,
    is_champion=False,
    is_ranker=False,
):
    data = _row_dict(row)
    robot_id = int(data.get("robot_id") or 0)
    user_id = int(data.get("user_id") or 0)
    if robot_id <= 0 or user_id <= 0:
        return
    latest_activity_at = int(data.get("latest_activity_at") or 0)
    latest_explore_at = int(data.get("latest_explore_at") or 0)
    existing = candidates.get(user_id)
    if not existing:
        robot_name = str(data.get("robot_name") or "").strip() or f"Robot #{robot_id}"
        display_name = str(data.get("display_name") or data.get("username") or "研究員").strip() or "研究員"
        existing = {
            "user_id": user_id,
            "username": str(data.get("username") or "").strip(),
            "display_name": display_name,
            "robot_id": robot_id,
            "robot_name": robot_name,
            "icon_path": data.get("robot_icon_32_path"),
            "robot_icon_32_path": data.get("robot_icon_32_path"),
            "robot_composed_image_path": data.get("robot_composed_image_path"),
            "composed_image_path": data.get("robot_composed_image_path"),
            "robot_updated_at": int(data.get("robot_updated_at") or 0),
            "avatar_path": data.get("avatar_path"),
            "style_key": str(data.get("robot_style_key") or "").strip(),
            "source_key": source_key,
            "source_keys": [],
            "source_rank": int(source_rank),
            "latest_activity_at": latest_activity_at,
            "latest_explore_at": latest_explore_at,
            "is_mvp": False,
            "is_champion": False,
            "is_ranker": False,
            "is_supporter": False,
            "supporter_label": "",
            "supporter_tier": "",
            "supporter_glow": False,
            "is_featured": False,
            "status_key": "",
            "status_label": "",
            "status_icon": "",
            "status_priority": 0,
            "last_event_at": "",
            "last_event_at_ts": 0,
            "event_type": "",
            "event_id": 0,
            "detail_url": None,
        }
        candidates[user_id] = existing
    existing["latest_activity_at"] = max(int(existing.get("latest_activity_at") or 0), latest_activity_at)
    existing["latest_explore_at"] = max(int(existing.get("latest_explore_at") or 0), latest_explore_at)
    existing["is_mvp"] = bool(existing.get("is_mvp") or is_mvp)
    existing["is_champion"] = bool(existing.get("is_champion") or is_champion)
    existing["is_ranker"] = bool(existing.get("is_ranker") or is_ranker)
    if source_key not in existing["source_keys"]:
        existing["source_keys"].append(source_key)
    if int(source_rank) < int(existing.get("source_rank") or source_rank):
        existing["source_key"] = source_key
        existing["source_rank"] = int(source_rank)


def _apply_presence_activity_to_home_candidates(db, candidates, current_ts):
    if not candidates:
        return
    user_ids = sorted({int(item["user_id"]) for item in candidates.values() if int(item.get("user_id") or 0) > 0})
    if not user_ids:
        return
    rows = db.execute(
        f"""
        SELECT user_id, last_active_at, last_surface, last_action_key
        FROM user_presence
        WHERE user_id IN ({_sql_placeholders(user_ids)})
        """,
        user_ids,
    ).fetchall()
    presence_by_user = {_row_dict(row).get("user_id"): _row_dict(row) for row in rows}
    active_cutoff = int(current_ts) - 10 * 60
    for item in candidates.values():
        row = presence_by_user.get(int(item.get("user_id") or 0))
        if not row:
            continue
        presence_ts = _presence_datetime_ts(row.get("last_active_at"))
        if presence_ts <= 0:
            continue
        item["latest_activity_at"] = max(int(item.get("latest_activity_at") or 0), presence_ts)
        surface = str(row.get("last_surface") or "").strip().lower()
        action = str(row.get("last_action_key") or "").strip().lower()
        if presence_ts >= active_cutoff and (surface == "explore" or action.startswith("explore.")):
            item["latest_explore_at"] = max(int(item.get("latest_explore_at") or 0), presence_ts)
            item["presence_explore_at"] = max(int(item.get("presence_explore_at") or 0), presence_ts)


def _decorate_home_candidates_with_recent_events(db, candidates, current_ts):
    if not candidates:
        return
    user_ids = sorted({int(item["user_id"]) for item in candidates.values() if int(item.get("user_id") or 0) > 0})
    if not user_ids:
        return
    rows = db.execute(
        f"""
        SELECT id, user_id, created_at, event_type, payload_json, action_key, entity_type, entity_id
        FROM world_events_log
        WHERE user_id IN ({_sql_placeholders(user_ids)})
          AND created_at >= ?
          AND event_type IN ({_sql_placeholders(RECENT_HOME_REPRESENTATIVE_EVENTS)})
        ORDER BY user_id ASC, created_at DESC, id DESC
        LIMIT ?
        """,
        [
            *user_ids,
            int(current_ts) - RECENT_HOME_FALLBACK_WINDOW_SECONDS,
            *RECENT_HOME_REPRESENTATIVE_EVENTS,
            max(240, len(user_ids) * 24),
        ],
    ).fetchall()
    best_by_user = {}
    for row in rows:
        data = _row_dict(row)
        user_id = int(data.get("user_id") or 0)
        action = _home_event_action_from_row(data)
        if not action:
            continue
        current = best_by_user.get(user_id)
        if current is None or (
            int(action.get("status_priority") or 0),
            int(action.get("last_event_at_ts") or 0),
            int(action.get("event_id") or 0),
        ) > (
            int(current.get("status_priority") or 0),
            int(current.get("last_event_at_ts") or 0),
            int(current.get("event_id") or 0),
        ):
            best_by_user[user_id] = action
    for item in candidates.values():
        user_id = int(item.get("user_id") or 0)
        action = best_by_user.get(user_id)
        if not action:
            continue
        item.update(action)
        item["latest_activity_at"] = max(
            int(item.get("latest_activity_at") or 0),
            int(action.get("last_event_at_ts") or 0),
        )


def _decorate_home_candidates_with_supporters(db, candidates):
    if not candidates:
        return
    user_ids = sorted({int(item["user_id"]) for item in candidates.values() if int(item.get("user_id") or 0) > 0})
    if not user_ids:
        return
    supporter_by_user = {}
    decor_rows = db.execute(
        f"""
        SELECT udi.user_id, da.key AS decor_key
        FROM user_decor_inventory udi
        JOIN robot_decor_assets da ON da.id = udi.decor_asset_id
        WHERE udi.user_id IN ({_sql_placeholders(user_ids)})
          AND da.key IN ({_sql_placeholders(RECENT_HOME_SUPPORTER_DECOR_KEYS)})
        """,
        [*user_ids, *RECENT_HOME_SUPPORTER_DECOR_KEYS],
    ).fetchall()
    tier_rank = {
        "lab_badge_gold": 3,
        "founder_badge_silver": 2,
        "shien_trophy": 1,
        "support_pack_lab": 3,
        "support_pack_founder": 2,
        "support_pack_001": 1,
    }
    for row in decor_rows:
        data = _row_dict(row)
        user_id = int(data.get("user_id") or 0)
        key = str(data.get("decor_key") or "").strip()
        if user_id <= 0 or not key:
            continue
        current = supporter_by_user.get(user_id)
        if current is None or tier_rank.get(key, 0) > tier_rank.get(current, 0):
            supporter_by_user[user_id] = key
    payment_rows = db.execute(
        f"""
        SELECT user_id, product_key
        FROM payment_orders
        WHERE user_id IN ({_sql_placeholders(user_ids)})
          AND product_key IN ({_sql_placeholders(RECENT_HOME_SUPPORTER_PRODUCT_KEYS)})
          AND status IN ('completed', 'granted')
        """,
        [*user_ids, *RECENT_HOME_SUPPORTER_PRODUCT_KEYS],
    ).fetchall()
    for row in payment_rows:
        data = _row_dict(row)
        user_id = int(data.get("user_id") or 0)
        key = str(data.get("product_key") or "").strip()
        if user_id <= 0 or user_id in supporter_by_user or not key:
            continue
        supporter_by_user[user_id] = key
    for item in candidates.values():
        key = supporter_by_user.get(int(item.get("user_id") or 0))
        if not key:
            continue
        item["is_supporter"] = True
        item["supporter_label"] = "ラボ支援者"
        item["supporter_tier"] = key
        item["supporter_glow"] = True


def _default_home_status_for_candidate(item, current_ts):
    active_cutoff = int(current_ts) - 10 * 60
    recent_cutoff = int(current_ts) - RECENT_HOME_MAIN_WINDOW_SECONDS
    if int(item.get("presence_explore_at") or item.get("latest_explore_at") or 0) >= active_cutoff:
        return "exploring"
    if int(item.get("latest_activity_at") or 0) >= recent_cutoff:
        return "recent_seen"
    return "weekly_hot"


def _mark_featured_home_robot(rows):
    if not rows:
        return rows
    for item in rows:
        item["is_featured"] = False
    best_index = 0
    best_score = None
    for index, item in enumerate(rows):
        score = (
            int(item.get("status_priority") or 0),
            1 if item.get("is_mvp") or item.get("is_champion") or item.get("is_ranker") else 0,
            1 if item.get("is_supporter") else 0,
            int(item.get("last_event_at_ts") or item.get("latest_activity_at") or 0),
            -index,
        )
        if best_score is None or score > best_score:
            best_score = score
            best_index = index
    rows[best_index]["is_featured"] = True
    return rows


def _finalize_home_robot_candidates(candidates, *, limit, current_ts):
    finalized = []
    for item in candidates.values():
        status_key = str(item.get("status_key") or "").strip() or _default_home_status_for_candidate(item, current_ts)
        status_meta = _home_status_meta(status_key)
        item["status_key"] = status_key
        item["status_label"] = _home_status_label(status_key)
        item["status_icon"] = str(item.get("status_icon") or status_meta.get("icon") or "")
        item["status_priority"] = int(item.get("status_priority") or status_meta.get("priority") or 0)
        item["tone"] = status_key
        item["stable_seed"] = (int(item["user_id"]) * 31 + int(item["robot_id"]) * 17) % 100000
        finalized.append(item)

    def sort_key(item):
        source_rank = int(item.get("source_rank") or 99)
        featured_rank = 0 if item.get("is_mvp") or item.get("is_champion") else 1
        return (
            -int(item.get("status_priority") or 0),
            source_rank,
            featured_rank,
            -int(item.get("last_event_at_ts") or item.get("latest_activity_at") or 0),
            -int(1 if item.get("is_supporter") else 0),
            int(item.get("stable_seed") or 0),
        )

    ordered = sorted(finalized, key=sort_key)
    display_limit = max(1, min(int(limit or RECENT_HOME_ROBOT_LIMIT), 12))
    if len(ordered) <= display_limit:
        return _mark_featured_home_robot(ordered)
    front_count = min(4, display_limit, len(ordered))
    needed = display_limit - front_count
    if needed <= 0:
        return _mark_featured_home_robot(ordered[:display_limit])
    tail = ordered[front_count:]
    offset = (int(current_ts) // 3600) % len(tail)
    rotated_tail = tail[offset:] + tail[:offset]
    return _mark_featured_home_robot(ordered[:front_count] + rotated_tail[:needed])


def get_recent_home_robot_presence(
    db,
    limit=RECENT_HOME_ROBOT_LIMIT,
    *,
    include_admin=False,
    include_champion=True,
    now=None,
    use_cache=True,
):
    """Build ambient home robot cards from real recent player activity."""
    current = _now_jst(now)
    current_ts = int(current.timestamp())
    display_limit = max(1, min(int(limit or RECENT_HOME_ROBOT_LIMIT), 12))
    if use_cache and now is None:
        cache_key = (_db_cache_key(db), display_limit, bool(include_admin), bool(include_champion))
        cached = _RECENT_HOME_ROBOT_CACHE.get(cache_key)
        if cached and float(cached.get("expires_at") or 0) > time.time():
            return copy.deepcopy(cached.get("rows") or [])

    candidates = {}
    user_filter = _home_user_eligibility_sql("u", include_admin=include_admin)
    select_cols = _home_robot_select_columns("u", "ri")
    activity_placeholders = _sql_placeholders(RECENT_HOME_ACTIVITY_EVENTS)
    explore_placeholders = _sql_placeholders(RECENT_HOME_EXPLORE_EVENTS)
    weekly_start_ts, weekly_end_ts, week_key = _week_bounds_for_ts(current_ts)

    recent_rows = db.execute(
        f"""
        SELECT
            {select_cols},
            MAX(wel.created_at) AS latest_activity_at,
            MAX(CASE WHEN wel.event_type IN ({explore_placeholders}) THEN wel.created_at ELSE 0 END) AS latest_explore_at
        FROM world_events_log wel
        JOIN users u ON u.id = wel.user_id
        JOIN robot_instances ri
          ON ri.id = u.active_robot_id
         AND ri.user_id = u.id
         AND ri.status = 'active'
        WHERE wel.user_id IS NOT NULL
          AND wel.created_at >= ?
          AND wel.event_type IN ({activity_placeholders})
          {user_filter}
        GROUP BY u.id, ri.id
        ORDER BY latest_activity_at DESC, u.id DESC
        LIMIT ?
        """,
        [*RECENT_HOME_EXPLORE_EVENTS, current_ts - RECENT_HOME_MAIN_WINDOW_SECONDS, *RECENT_HOME_ACTIVITY_EVENTS, max(16, display_limit * 3)],
    ).fetchall()
    for row in recent_rows:
        _merge_home_robot_candidate(candidates, row, source_key="recent_activity", source_rank=0)

    mvp_rows = db.execute(
        f"""
        SELECT
            {select_cols},
            mvp.latest_activity_at AS latest_activity_at,
            mvp.latest_explore_at AS latest_explore_at,
            mvp.metric_value AS metric_value
        FROM (
            SELECT
                user_id,
                COUNT(*) AS metric_value,
                MAX(created_at) AS latest_activity_at,
                MAX(created_at) AS latest_explore_at
            FROM world_events_log
            WHERE event_type = ?
              AND user_id IS NOT NULL
              AND created_at >= ?
              AND created_at < ?
              AND CAST(COALESCE(json_extract(payload_json, '$.result.win'), 0) AS INTEGER) = 1
            GROUP BY user_id
        ) mvp
        JOIN users u ON u.id = mvp.user_id
        JOIN robot_instances ri
          ON ri.id = u.active_robot_id
         AND ri.user_id = u.id
         AND ri.status = 'active'
        WHERE 1 = 1
          {user_filter}
        ORDER BY mvp.metric_value DESC, mvp.latest_activity_at DESC, u.id ASC
        LIMIT 1
        """,
        (AUDIT_EVENT_TYPES["EXPLORE_END"], weekly_start_ts, weekly_end_ts),
    ).fetchall()
    for row in mvp_rows:
        _merge_home_robot_candidate(candidates, row, source_key="mvp", source_rank=1, is_mvp=True)

    if include_champion:
        champion_rows = db.execute(
            f"""
            SELECT
                {select_cols},
                wcs.created_at AS latest_activity_at,
                0 AS latest_explore_at,
                wcs.score_value AS metric_value
            FROM weekly_champion_snapshots wcs
            JOIN users u ON u.id = wcs.user_id
            JOIN robot_instances ri
              ON ri.id = wcs.robot_instance_id
             AND ri.user_id = u.id
             AND ri.status = 'active'
            WHERE wcs.week_key = ?
              {user_filter}
            ORDER BY wcs.id DESC
            LIMIT 1
            """,
            (week_key,),
        ).fetchall()
        for row in champion_rows:
            _merge_home_robot_candidate(candidates, row, source_key="champion", source_rank=2, is_champion=True)

    for event_type in (AUDIT_EVENT_TYPES["EXPLORE_END"], AUDIT_EVENT_TYPES["BOSS_DEFEAT"]):
        rank_rows = db.execute(
            f"""
            SELECT
                {select_cols},
                ranks.latest_activity_at AS latest_activity_at,
                CASE WHEN ? = ? THEN ranks.latest_activity_at ELSE 0 END AS latest_explore_at,
                ranks.metric_value AS metric_value
            FROM (
                SELECT user_id, COUNT(*) AS metric_value, MAX(created_at) AS latest_activity_at
                FROM world_events_log
                WHERE event_type = ?
                  AND user_id IS NOT NULL
                  AND created_at >= ?
                  AND created_at < ?
                GROUP BY user_id
                ORDER BY metric_value DESC, latest_activity_at DESC, user_id ASC
                LIMIT 5
            ) ranks
            JOIN users u ON u.id = ranks.user_id
            JOIN robot_instances ri
              ON ri.id = u.active_robot_id
             AND ri.user_id = u.id
             AND ri.status = 'active'
            WHERE 1 = 1
              {user_filter}
            ORDER BY ranks.metric_value DESC, ranks.latest_activity_at DESC, u.id ASC
            """,
            (
                event_type,
                AUDIT_EVENT_TYPES["EXPLORE_END"],
                event_type,
                weekly_start_ts,
                weekly_end_ts,
            ),
        ).fetchall()
        for row in rank_rows:
            _merge_home_robot_candidate(candidates, row, source_key="weekly_rank", source_rank=3, is_ranker=True)

    world_placeholders = _sql_placeholders(RECENT_HOME_WORLD_EVENTS)
    world_rows = db.execute(
        f"""
        SELECT
            {select_cols},
            MAX(wel.created_at) AS latest_activity_at,
            MAX(CASE WHEN wel.event_type IN ({explore_placeholders}) THEN wel.created_at ELSE 0 END) AS latest_explore_at
        FROM world_events_log wel
        JOIN users u ON u.id = wel.user_id
        JOIN robot_instances ri
          ON ri.id = u.active_robot_id
         AND ri.user_id = u.id
         AND ri.status = 'active'
        WHERE wel.user_id IS NOT NULL
          AND wel.created_at >= ?
          AND wel.event_type IN ({world_placeholders})
          {user_filter}
        GROUP BY u.id, ri.id
        ORDER BY latest_activity_at DESC, u.id DESC
        LIMIT ?
        """,
        [*RECENT_HOME_EXPLORE_EVENTS, current_ts - RECENT_HOME_MAIN_WINDOW_SECONDS, *RECENT_HOME_WORLD_EVENTS, max(16, display_limit * 3)],
    ).fetchall()
    for row in world_rows:
        _merge_home_robot_candidate(candidates, row, source_key="world_event", source_rank=4)

    if len(candidates) < display_limit:
        fallback_rows = db.execute(
            f"""
            SELECT
                {select_cols},
                MAX(wel.created_at) AS latest_activity_at,
                MAX(CASE WHEN wel.event_type IN ({explore_placeholders}) THEN wel.created_at ELSE 0 END) AS latest_explore_at
            FROM world_events_log wel
            JOIN users u ON u.id = wel.user_id
            JOIN robot_instances ri
              ON ri.id = u.active_robot_id
             AND ri.user_id = u.id
             AND ri.status = 'active'
            WHERE wel.user_id IS NOT NULL
              AND wel.created_at >= ?
              AND wel.event_type IN ({activity_placeholders})
              {user_filter}
            GROUP BY u.id, ri.id
            ORDER BY latest_activity_at DESC, u.id DESC
            LIMIT ?
            """,
            [
                *RECENT_HOME_EXPLORE_EVENTS,
                current_ts - RECENT_HOME_FALLBACK_WINDOW_SECONDS,
                *RECENT_HOME_ACTIVITY_EVENTS,
                max(16, display_limit * 3),
            ],
        ).fetchall()
        for row in fallback_rows:
            _merge_home_robot_candidate(candidates, row, source_key="fallback_weekly", source_rank=5)

    if len(candidates) < display_limit:
        showcase_rows = db.execute(
            f"""
            SELECT
                {select_cols},
                0 AS latest_activity_at,
                0 AS latest_explore_at
            FROM user_showcase us
            JOIN users u ON u.id = us.user_id
            JOIN robot_instances ri
              ON ri.id = us.robot_instance_id
             AND ri.user_id = u.id
             AND ri.status = 'active'
            WHERE us.robot_instance_id IS NOT NULL
              {user_filter}
            ORDER BY ri.updated_at DESC, us.slot_no ASC, ri.id DESC
            LIMIT ?
            """,
            (max(16, display_limit * 3),),
        ).fetchall()
        for row in showcase_rows:
            _merge_home_robot_candidate(candidates, row, source_key="showcase", source_rank=6)

    if len(candidates) < display_limit:
        record_rows = db.execute(
            f"""
            SELECT
                {select_cols},
                0 AS latest_activity_at,
                0 AS latest_explore_at,
                COALESCE(u.wins, 0) AS metric_value
            FROM users u
            JOIN robot_instances ri
              ON ri.id = u.active_robot_id
             AND ri.user_id = u.id
             AND ri.status = 'active'
            WHERE u.active_robot_id IS NOT NULL
              {user_filter}
            ORDER BY COALESCE(u.wins, 0) DESC, ri.updated_at DESC, u.id ASC
            LIMIT ?
            """,
            (max(16, display_limit * 3),),
        ).fetchall()
        for row in record_rows:
            _merge_home_robot_candidate(candidates, row, source_key="record_archive", source_rank=7)

    _apply_presence_activity_to_home_candidates(db, candidates, current_ts)
    _decorate_home_candidates_with_recent_events(db, candidates, current_ts)
    _decorate_home_candidates_with_supporters(db, candidates)
    rows = _finalize_home_robot_candidates(candidates, limit=display_limit, current_ts=current_ts)
    if use_cache and now is None:
        _RECENT_HOME_ROBOT_CACHE[cache_key] = {
            "expires_at": time.time() + RECENT_HOME_ROBOT_CACHE_TTL_SECONDS,
            "rows": copy.deepcopy(rows),
        }
    return rows


def serialize_presence_entry(row, now=None):
    data = _row_dict(row)
    minutes = _minutes_ago(data.get("last_active_at"), now=now)
    state_key = presence_state_for(data.get("last_surface"), data.get("last_action_key"), minutes)
    display_name = str(data.get("display_name") or data.get("username") or "研究員").strip()
    return {
        "user_id": int(data.get("user_id") or 0),
        "display_name": display_name,
        "username": str(data.get("username") or "").strip(),
        "avatar_path": data.get("avatar_path"),
        "robot_icon_32_path": data.get("robot_icon_32_path"),
        "robot_composed_image_path": data.get("robot_composed_image_path"),
        "robot_updated_at": int(data.get("robot_updated_at") or 0),
        "active_robot_id": int(data.get("active_robot_id") or 0) if data.get("active_robot_id") else None,
        "state_key": state_key,
        "state_label": PRESENCE_STATE_LABELS[state_key],
        "tone": presence_tone(minutes),
        "minutes_ago": minutes,
        "last_active_at": _iso_jst(_parse_presence_time(data.get("last_active_at")) or _now_jst(now)),
        "last_surface": str(data.get("last_surface") or "").strip(),
        "last_action_key": str(data.get("last_action_key") or "").strip(),
        "last_room_key": str(data.get("last_room_key") or "").strip(),
    }
