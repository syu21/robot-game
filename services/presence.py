from datetime import datetime, timedelta, timezone


JST = timezone(timedelta(hours=9))
PRESENCE_STATE_LABELS = {
    "exploring": "出撃中",
    "lab": "実験室参加中",
    "comms": "会議室参加中",
    "home": "探索待機中",
    "idle_recent": "さっきまで参加",
}
HOME_SURFACES = {"home", "parts", "build", "world", "records", "showcase"}


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
