import json
import time

from constants import AUDIT_EVENT_TYPES
from services.audit import audit_log


ACHIEVEMENT_DEFAULTS = (
    {
        "key": "first_explore",
        "name_ja": "初出撃",
        "description_ja": "はじめて出撃した",
        "category": "出撃",
        "badge_icon": "🚀",
        "frame_key": None,
        "sort_order": 10,
    },
    {
        "key": "first_win",
        "name_ja": "初勝利",
        "description_ja": "はじめて戦闘に勝利した",
        "category": "出撃",
        "badge_icon": "🏅",
        "frame_key": None,
        "sort_order": 20,
    },
    {
        "key": "first_build",
        "name_ja": "初ロボ完成",
        "description_ja": "はじめてロボを編成した",
        "category": "編成",
        "badge_icon": "🤖",
        "frame_key": None,
        "sort_order": 30,
    },
    {
        "key": "first_strengthen",
        "name_ja": "初強化",
        "description_ja": "はじめてパーツを強化した",
        "category": "育成",
        "badge_icon": "🔧",
        "frame_key": None,
        "sort_order": 40,
    },
    {
        "key": "first_evolve",
        "name_ja": "初進化",
        "description_ja": "はじめてパーツを進化させた",
        "category": "育成",
        "badge_icon": "✨",
        "frame_key": None,
        "sort_order": 50,
    },
    {
        "key": "layer1_clear",
        "name_ja": "第1層突破",
        "description_ja": "第1層のボスを撃破した",
        "category": "層突破",
        "badge_icon": "🏁",
        "frame_key": None,
        "sort_order": 60,
    },
    {
        "key": "tower_challenger",
        "name_ja": "観測塔挑戦者",
        "description_ja": "観測塔に挑戦した",
        "category": "観測塔",
        "badge_icon": "🗼",
        "frame_key": None,
        "sort_order": 70,
    },
    {
        "key": "supporter",
        "name_ja": "支援研究員",
        "description_ja": "ロボらぼを応援した",
        "category": "支援",
        "badge_icon": "💎",
        "frame_key": "supporter_glow",
        "sort_order": 80,
    },
)


def ensure_achievement_schema(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            name_ja TEXT NOT NULL,
            description_ja TEXT NOT NULL,
            category TEXT NOT NULL,
            badge_icon TEXT,
            frame_key TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            achievement_key TEXT NOT NULL,
            unlocked_at INTEGER NOT NULL,
            source_event_type TEXT,
            source_payload_json TEXT,
            UNIQUE(user_id, achievement_key)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_profile_rewards (
            user_id INTEGER PRIMARY KEY,
            equipped_title_key TEXT,
            equipped_badge_key TEXT,
            equipped_frame_key TEXT,
            updated_at INTEGER NOT NULL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_achievements_active_sort ON achievements(is_active, sort_order)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_user_achievements_user ON user_achievements(user_id, unlocked_at)")


def ensure_achievement_defaults(db):
    ensure_achievement_schema(db)
    now_ts = int(time.time())
    for item in ACHIEVEMENT_DEFAULTS:
        db.execute(
            """
            INSERT INTO achievements
            (key, name_ja, description_ja, category, badge_icon, frame_key, is_active, sort_order, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                name_ja = excluded.name_ja,
                description_ja = excluded.description_ja,
                category = excluded.category,
                badge_icon = excluded.badge_icon,
                frame_key = excluded.frame_key,
                is_active = 1,
                sort_order = excluded.sort_order
            """,
            (
                item["key"],
                item["name_ja"],
                item["description_ja"],
                item["category"],
                item.get("badge_icon"),
                item.get("frame_key"),
                int(item.get("sort_order") or 0),
                now_ts,
            ),
        )


def _json_payload(payload):
    return json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)


def grant_achievement(db, user_id, achievement_key, source_event_type=None, payload=None, request_id=None, ip=None):
    ensure_achievement_defaults(db)
    user_id = int(user_id)
    achievement_key = str(achievement_key or "").strip()
    achievement = db.execute(
        """
        SELECT *
        FROM achievements
        WHERE key = ? AND is_active = 1
        LIMIT 1
        """,
        (achievement_key,),
    ).fetchone()
    if not achievement:
        return {"ok": False, "granted": False, "reason": "achievement_not_found"}
    now_ts = int(time.time())
    result = db.execute(
        """
        INSERT OR IGNORE INTO user_achievements
        (user_id, achievement_key, unlocked_at, source_event_type, source_payload_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, achievement_key, now_ts, source_event_type, _json_payload(payload)),
    )
    granted = int(result.rowcount or 0) > 0
    if granted:
        username_row = db.execute("SELECT username, display_name FROM users WHERE id = ?", (user_id,)).fetchone()
        display_name = (
            (username_row["display_name"] if username_row and "display_name" in username_row.keys() else None)
            or (username_row["username"] if username_row else None)
            or f"研究員#{user_id}"
        )
        audit_log(
            db,
            AUDIT_EVENT_TYPES["ACHIEVEMENT_GRANT"],
            user_id=user_id,
            request_id=request_id,
            action_key="achievement_grant",
            entity_type="achievement",
            entity_id=int(achievement["id"]),
            payload={
                "user_id": user_id,
                "achievement_key": achievement_key,
                "achievement_name": achievement["name_ja"],
                "source_event_type": source_event_type,
                "source_payload": payload or {},
                "world_message": f"{display_name}が研究実績『{achievement['name_ja']}』を獲得",
            },
            ip=ip,
        )
    return {"ok": True, "granted": granted, "achievement": dict(achievement)}


def get_user_achievements(db, user_id):
    ensure_achievement_defaults(db)
    rows = db.execute(
        """
        SELECT
            a.*,
            ua.unlocked_at,
            CASE WHEN ua.id IS NULL THEN 0 ELSE 1 END AS is_unlocked
        FROM achievements a
        LEFT JOIN user_achievements ua
          ON ua.achievement_key = a.key
         AND ua.user_id = ?
        WHERE a.is_active = 1
        ORDER BY a.category ASC, a.sort_order ASC, a.id ASC
        """,
        (int(user_id),),
    ).fetchall()
    return [dict(row) for row in rows]


def get_equipped_profile_rewards(db, user_id):
    ensure_achievement_defaults(db)
    user_id = int(user_id)
    now_ts = int(time.time())
    db.execute(
        """
        INSERT OR IGNORE INTO user_profile_rewards
        (user_id, equipped_title_key, equipped_badge_key, equipped_frame_key, updated_at)
        VALUES (?, NULL, NULL, NULL, ?)
        """,
        (user_id, now_ts),
    )
    row = db.execute("SELECT * FROM user_profile_rewards WHERE user_id = ?", (user_id,)).fetchone()
    result = {
        "equipped_title_key": row["equipped_title_key"] if row else None,
        "equipped_badge_key": row["equipped_badge_key"] if row else None,
        "equipped_frame_key": row["equipped_frame_key"] if row else None,
        "title": None,
        "badge": None,
        "frame": None,
        "frame_key": None,
    }
    for reward_type, key_name in (
        ("title", "equipped_title_key"),
        ("badge", "equipped_badge_key"),
        ("frame", "equipped_frame_key"),
    ):
        key_value = result.get(key_name)
        if not key_value:
            continue
        item = db.execute(
            """
            SELECT a.*
            FROM achievements a
            JOIN user_achievements ua
              ON ua.achievement_key = a.key
             AND ua.user_id = ?
            WHERE a.key = ? AND a.is_active = 1
            LIMIT 1
            """,
            (user_id, key_value),
        ).fetchone()
        if item:
            result[reward_type] = dict(item)
            if reward_type == "frame":
                result["frame_key"] = item["frame_key"]
    return result


def equip_profile_reward(db, user_id, reward_type, achievement_key, request_id=None, ip=None):
    ensure_achievement_defaults(db)
    user_id = int(user_id)
    reward_type = str(reward_type or "").strip().lower()
    achievement_key = str(achievement_key or "").strip()
    column_by_type = {
        "title": "equipped_title_key",
        "badge": "equipped_badge_key",
        "frame": "equipped_frame_key",
    }
    column = column_by_type.get(reward_type)
    if not column:
        return {"ok": False, "message": "装備タイプが不正です。"}
    row = db.execute(
        """
        SELECT a.*
        FROM achievements a
        JOIN user_achievements ua
          ON ua.achievement_key = a.key
         AND ua.user_id = ?
        WHERE a.key = ? AND a.is_active = 1
        LIMIT 1
        """,
        (user_id, achievement_key),
    ).fetchone()
    if not row:
        return {"ok": False, "message": "未獲得の研究実績は表示できません。"}
    if reward_type == "frame" and not str(row["frame_key"] or "").strip():
        return {"ok": False, "message": "この研究実績にはフレームがありません。"}
    now_ts = int(time.time())
    db.execute(
        """
        INSERT OR IGNORE INTO user_profile_rewards
        (user_id, equipped_title_key, equipped_badge_key, equipped_frame_key, updated_at)
        VALUES (?, NULL, NULL, NULL, ?)
        """,
        (user_id, now_ts),
    )
    db.execute(
        f"""
        UPDATE user_profile_rewards
        SET {column} = ?, updated_at = ?
        WHERE user_id = ?
        """,
        (achievement_key, now_ts, user_id),
    )
    audit_log(
        db,
        AUDIT_EVENT_TYPES["ACHIEVEMENT_EQUIP"],
        user_id=user_id,
        request_id=request_id,
        action_key="achievement_equip",
        entity_type="achievement",
        entity_id=int(row["id"]),
        payload={
            "user_id": user_id,
            "achievement_key": achievement_key,
            "reward_type": reward_type,
            "source_payload": {},
        },
        ip=ip,
    )
    return {"ok": True, "achievement": dict(row), "reward_type": reward_type}
