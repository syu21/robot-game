import json
from datetime import datetime, timedelta, timezone


JST = timezone(timedelta(hours=9))
LAB_TYPING_DURATION_MS = 30000
LAB_TYPING_MAX_SCORE = 5_000_000
LAB_TYPING_MAX_TYPED_COUNT = 300

EASY_COMMANDS = ["FIRE", "DASH", "CORE", "SHOT", "LAB", "BOSS", "PART", "SCAN"]
NORMAL_COMMANDS = ["BOOST", "GUARD", "LOCKON", "RELOAD", "CHARGE", "SHIELD", "ROCKET", "BARRIER"]
HARD_COMMANDS = ["MISSILE", "CRITICAL", "OVERDRIVE", "FULLBURST", "OMEGACORE", "LIMITBREAK", "SYSTEMCALL", "FINALSHOT"]

TYPING_COMMANDS = {
    "easy": EASY_COMMANDS,
    "normal": NORMAL_COMMANDS,
    "hard": HARD_COMMANDS,
}

TYPING_ENEMIES = [
    {"key": "scrap_drone", "name": "スクラップドローン", "hp": 100, "score_multiplier": 1.0, "kind": "normal"},
    {"key": "bolt_bug", "name": "ボルトバグ", "hp": 160, "score_multiplier": 1.0, "kind": "normal"},
    {"key": "guard_mech", "name": "ガードメック", "hp": 240, "score_multiplier": 1.0, "kind": "normal"},
    {"key": "mirage_bit", "name": "ミラージュビット", "hp": 360, "score_multiplier": 1.5, "kind": "normal"},
    {"key": "type_zero_core", "name": "タイプゼロ・コア", "hp": 1000, "score_multiplier": 3.0, "kind": "boss"},
]


def _int_value(data, key, default=0):
    try:
        return int(data.get(key, default))
    except (TypeError, ValueError):
        return int(default)


def validate_typing_result(data):
    payload = data if isinstance(data, dict) else {}
    score = _int_value(payload, "score")
    max_combo = _int_value(payload, "max_combo")
    typed_count = _int_value(payload, "typed_count")
    miss_count = _int_value(payload, "miss_count")
    defeated_count = _int_value(payload, "defeated_count")
    duration_ms = _int_value(payload, "duration_ms")

    if duration_ms < 25000 or duration_ms > 35000:
        return False, "invalid_duration"
    if score < 0 or score > LAB_TYPING_MAX_SCORE:
        return False, "invalid_score"
    if typed_count < 0 or typed_count > LAB_TYPING_MAX_TYPED_COUNT:
        return False, "invalid_typed_count"
    if miss_count < 0:
        return False, "invalid_miss_count"
    if max_combo < 0 or max_combo > typed_count:
        return False, "invalid_combo"
    if defeated_count < 0 or defeated_count > len(TYPING_ENEMIES):
        return False, "invalid_defeated_count"
    return True, None


def normalize_typing_result(data):
    payload = data if isinstance(data, dict) else {}
    remaining_raw = payload.get("remaining_boss_hp")
    try:
        remaining_boss_hp = int(remaining_raw) if remaining_raw is not None else None
    except (TypeError, ValueError):
        remaining_boss_hp = None
    if remaining_boss_hp is not None:
        remaining_boss_hp = max(0, min(remaining_boss_hp, int(TYPING_ENEMIES[-1]["hp"])))
    return {
        "score": _int_value(payload, "score"),
        "max_combo": _int_value(payload, "max_combo"),
        "typed_count": _int_value(payload, "typed_count"),
        "miss_count": _int_value(payload, "miss_count"),
        "defeated_count": _int_value(payload, "defeated_count"),
        "boss_reached": 1 if bool(payload.get("boss_reached")) else 0,
        "boss_defeated": 1 if bool(payload.get("boss_defeated")) else 0,
        "remaining_boss_hp": remaining_boss_hp,
        "duration_ms": _int_value(payload, "duration_ms", LAB_TYPING_DURATION_MS),
        "client_payload": payload.get("client_payload") if isinstance(payload.get("client_payload"), dict) else {},
    }


def save_typing_run(conn, user_id, data):
    normalized = normalize_typing_result(data)
    created_at = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        """
        INSERT INTO lab_typing_runs (
            user_id, score, max_combo, typed_count, miss_count, defeated_count,
            boss_reached, boss_defeated, remaining_boss_hp, duration_ms,
            client_payload_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(user_id),
            int(normalized["score"]),
            int(normalized["max_combo"]),
            int(normalized["typed_count"]),
            int(normalized["miss_count"]),
            int(normalized["defeated_count"]),
            int(normalized["boss_reached"]),
            int(normalized["boss_defeated"]),
            normalized["remaining_boss_hp"],
            int(normalized["duration_ms"]),
            json.dumps(normalized["client_payload"], ensure_ascii=False),
            created_at,
        ),
    )
    normalized["id"] = int(cur.lastrowid)
    normalized["created_at"] = created_at
    return normalized


def is_today_best(conn, user_id, score):
    row = conn.execute(
        """
        SELECT COALESCE(MAX(score), 0) AS best
        FROM lab_typing_runs
        WHERE user_id = ?
          AND date(created_at) = date('now', 'localtime')
        """,
        (int(user_id),),
    ).fetchone()
    return int(score or 0) >= int((row["best"] if row else 0) or 0)


def is_personal_best(conn, user_id, score):
    row = conn.execute(
        "SELECT COALESCE(MAX(score), 0) AS best FROM lab_typing_runs WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    return int(score or 0) >= int((row["best"] if row else 0) or 0)


def get_typing_history(conn, user_id, limit=20):
    return conn.execute(
        """
        SELECT *
        FROM lab_typing_runs
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (int(user_id), int(limit)),
    ).fetchall()


def get_today_best(conn, user_id):
    return conn.execute(
        """
        SELECT *
        FROM lab_typing_runs
        WHERE user_id = ?
          AND date(created_at) = date('now', 'localtime')
        ORDER BY score DESC, id DESC
        LIMIT 1
        """,
        (int(user_id),),
    ).fetchone()


def get_personal_best(conn, user_id):
    return conn.execute(
        """
        SELECT *
        FROM lab_typing_runs
        WHERE user_id = ?
        ORDER BY score DESC, id DESC
        LIMIT 1
        """,
        (int(user_id),),
    ).fetchone()


def get_weekly_rankings(conn, limit=10):
    return conn.execute(
        """
        SELECT r.*, u.display_name, u.username
        FROM lab_typing_runs r
        JOIN users u ON u.id = r.user_id
        WHERE r.created_at >= datetime('now', '-7 days')
        ORDER BY r.score DESC, r.id DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
