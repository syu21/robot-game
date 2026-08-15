import hashlib
import json
import random
import sqlite3
import time
from datetime import datetime, timedelta, timezone


JST = timezone(timedelta(hours=9))
ANOMALY_FEATURE_KEY = "anomaly"
ANOMALY_MAX_TURNS = 8
ANOMALY_RETRY_CT_SECONDS = 10
ANOMALY_CLEAR_REWARD_COINS = 60
ANOMALY_COMBAT_SIGNAL_PATTERNS = {
    "veil_runner": {"key": "phase_shift", "label": "PHASE SHIFT"},
    "gravemass": {"key": "aegis", "label": "AEGIS"},
    "redline": {"key": "overcharge", "label": "OVERCHARGE"},
    "paradox": {"key": "lock_on", "label": "LOCK-ON"},
}

ANOMALY_CLASSES = {
    "observe": {"label": "観測級", "min_layer": 1, "max_layer": 2, "stat_scale": 0.52},
    "field": {"label": "実戦級", "min_layer": 3, "max_layer": 4, "stat_scale": 0.9},
    "deep": {"label": "深層級", "min_layer": 5, "max_layer": 99, "stat_scale": 1.35},
}

ANOMALY_TEMPLATES = [
    {
        "key": "veil_runner",
        "code_name": "VEIL RUNNER",
        "display_name": "異常個体《VEIL RUNNER》",
        "template_label": "高速異常機",
        "theme": "命中 / 安定",
        "trait": "fast_anomaly",
        "style_key": "speed",
        "observation_trait": "高速機動",
        "observation_note": "高速機動反応を確認。照準精度の低い機体では捕捉が困難です。",
        "stats": {"hp": 980, "atk": 145, "def": 92, "spd": 190, "acc": 175, "cri": 18},
    },
    {
        "key": "gravemass",
        "code_name": "GRAVEMASS",
        "display_name": "異常個体《GRAVEMASS》",
        "template_label": "超重装異常機",
        "theme": "火力 / 会心",
        "trait": "heavy_anomaly",
        "style_key": "durable",
        "observation_trait": "超重装甲",
        "observation_note": "異常な装甲密度を確認。通常火力では有効打が通りにくいようです。",
        "stats": {"hp": 1100, "atk": 135, "def": 145, "spd": 78, "acc": 128, "cri": 12},
    },
    {
        "key": "redline",
        "code_name": "REDLINE",
        "display_name": "異常個体《REDLINE》",
        "template_label": "臨界暴走機",
        "theme": "速攻 vs 耐久",
        "trait": "berserk_anomaly",
        "style_key": "burst",
        "observation_trait": "臨界暴走",
        "observation_note": "損傷率の上昇とともに出力が増大しています。長期戦は危険です。",
        "stats": {"hp": 940, "atk": 165, "def": 100, "spd": 132, "acc": 138, "cri": 28},
    },
    {
        "key": "paradox",
        "code_name": "PARADOX",
        "display_name": "異常個体《PARADOX》",
        "template_label": "位相不安定機",
        "theme": "安定 / 耐久 / 上振れ対応",
        "trait": "unstable_anomaly",
        "style_key": "unstable",
        "observation_trait": "位相不安定",
        "observation_note": "出力波形が安定していません。戦闘結果に大きな振幅が発生しています。",
        "stats": {"hp": 980, "atk": 158, "def": 112, "spd": 145, "acc": 142, "cri": 24},
    },
]
ANOMALY_TEMPLATE_BY_KEY = {row["key"]: row for row in ANOMALY_TEMPLATES}


def current_week_key(ts=None):
    dt = datetime.now(JST) if ts is None else datetime.fromtimestamp(int(ts), JST)
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_bounds(week_key):
    year_s, week_s = str(week_key or "").split("-W")
    start = datetime.fromisocalendar(int(year_s), int(week_s), 1).replace(tzinfo=JST)
    end = start + timedelta(days=7)
    return start, end


def _stable_index(seed_text, length):
    digest = hashlib.sha256(str(seed_text).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % max(1, int(length))


def template_for_week(week_key):
    return dict(ANOMALY_TEMPLATES[_stable_index(f"weekly-anomaly:{week_key}", len(ANOMALY_TEMPLATES))])


def class_for_layer(max_layer):
    layer = max(1, int(max_layer or 1))
    if layer <= 2:
        return "observe"
    if layer <= 4:
        return "field"
    return "deep"


def class_label(challenge_class):
    return ANOMALY_CLASSES.get(str(challenge_class), ANOMALY_CLASSES["observe"])["label"]


def build_class_stats(template, challenge_class):
    cls = ANOMALY_CLASSES.get(str(challenge_class), ANOMALY_CLASSES["observe"])
    scale = float(cls["stat_scale"])
    base = dict((template or {}).get("stats") or {})
    # HP/DEF are scaled a little less aggressively so deep-class fights do not become pure sponges.
    return {
        "hp": max(1, int(round(float(base.get("hp") or 1) * scale))),
        "atk": max(1, int(round(float(base.get("atk") or 1) * scale))),
        "def": max(1, int(round(float(base.get("def") or 1) * (0.85 + scale * 0.15)))),
        "spd": max(1, int(round(float(base.get("spd") or 1) * scale))),
        "acc": max(1, int(round(float(base.get("acc") or 1) * scale))),
        "cri": max(1, int(round(float(base.get("cri") or 1) * (0.8 + scale * 0.2)))),
    }


def build_cycle_config(week_key):
    template = template_for_week(week_key)
    seed = hashlib.sha256(f"weekly-anomaly-cycle:{week_key}:{template['key']}".encode("utf-8")).hexdigest()[:16]
    config = {
        **template,
        "week_key": str(week_key),
        "seed": seed,
        "combat_signal": dict(ANOMALY_COMBAT_SIGNAL_PATTERNS.get(template["key"]) or {}),
        "max_turns": ANOMALY_MAX_TURNS,
        "classes": {
            key: {
                "key": key,
                "label": meta["label"],
                "stats": build_class_stats(template, key),
            }
            for key, meta in ANOMALY_CLASSES.items()
        },
    }
    return config


def ensure_schema(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS weekly_anomaly_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL UNIQUE,
            template_key TEXT NOT NULL,
            display_name TEXT NOT NULL,
            seed TEXT NOT NULL,
            config_json TEXT NOT NULL DEFAULT '{}',
            starts_at INTEGER NOT NULL,
            ends_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS anomaly_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            robot_instance_id INTEGER NOT NULL,
            challenge_class TEXT NOT NULL,
            template_key TEXT NOT NULL,
            result TEXT NOT NULL,
            turns INTEGER NOT NULL DEFAULT 0,
            player_hp_remaining INTEGER NOT NULL DEFAULT 0,
            player_hp_max INTEGER NOT NULL DEFAULT 0,
            enemy_hp_remaining INTEGER NOT NULL DEFAULT 0,
            enemy_hp_max INTEGER NOT NULL DEFAULT 0,
            damage_dealt INTEGER NOT NULL DEFAULT 0,
            analysis_rate INTEGER NOT NULL DEFAULT 0,
            request_id TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at INTEGER NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS anomaly_weekly_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            challenge_class TEXT NOT NULL,
            reward_granted_at INTEGER NOT NULL,
            reward_coins INTEGER NOT NULL DEFAULT 0,
            request_id TEXT,
            UNIQUE(week_key, user_id, challenge_class)
        )
        """
    )
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_anomaly_attempts_request ON anomaly_attempts(request_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_attempts_week_class ON anomaly_attempts(week_key, challenge_class, result, analysis_rate DESC, turns ASC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_attempts_user_week ON anomaly_attempts(user_id, week_key, challenge_class, created_at DESC)")


def get_cycle(db, week_key):
    ensure_schema(db)
    row = db.execute("SELECT * FROM weekly_anomaly_cycles WHERE week_key = ? LIMIT 1", (str(week_key),)).fetchone()
    return dict(row) if row else None


def get_or_create_cycle(db, week_key=None, now_ts=None):
    ensure_schema(db)
    wk = str(week_key or current_week_key(now_ts))
    existing = get_cycle(db, wk)
    if existing:
        return {"cycle": existing, "created": False}
    config = build_cycle_config(wk)
    start_dt, end_dt = week_bounds(wk)
    now_value = int(now_ts or time.time())
    try:
        db.execute(
            """
            INSERT INTO weekly_anomaly_cycles
            (week_key, template_key, display_name, seed, config_json, starts_at, ends_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                wk,
                config["key"],
                config["display_name"],
                config["seed"],
                json.dumps(config, ensure_ascii=False),
                int(start_dt.timestamp()),
                int(end_dt.timestamp()),
                now_value,
            ),
        )
        created = True
    except sqlite3.IntegrityError:
        created = False
    return {"cycle": get_cycle(db, wk), "created": created}


def cycle_config(cycle_row):
    try:
        return json.loads((cycle_row or {}).get("config_json") or "{}")
    except Exception:
        return {}


def enemy_payload_for_class(cycle_row, challenge_class):
    config = cycle_config(cycle_row)
    cls = (config.get("classes") or {}).get(str(challenge_class)) or {}
    stats = dict(cls.get("stats") or {})
    stats["trait"] = str(config.get("trait") or "anomaly")
    return {
        "name": str(config.get("display_name") or "異常個体"),
        "style_key": str(config.get("style_key") or "stable"),
        "signature_label": str(config.get("template_label") or "異常個体"),
        "focus_labels": [str(config.get("theme") or "解析")],
        "trait_summary": str(config.get("observation_trait") or ""),
        "stats": stats,
    }


def summarize_battle_result(battle_result):
    result = battle_result or {}
    enemy_max = max(1, int(result.get("enemy_max_hp") if result.get("enemy_max_hp") is not None else 1))
    enemy_remaining = max(0, int(result.get("enemy_final_hp") if result.get("enemy_final_hp") is not None else enemy_max))
    damage_dealt = max(0, enemy_max - enemy_remaining)
    clear = enemy_remaining <= 0
    analysis_rate = 100 if clear else max(0, min(99, int(round((damage_dealt / enemy_max) * 100))))
    return {
        "result": "clear" if clear else "incomplete",
        "clear": bool(clear),
        "turns": int((battle_result or {}).get("turn_count") or 0),
        "player_hp_remaining": max(0, int((battle_result or {}).get("player_final_hp") or 0)),
        "player_hp_max": max(1, int((battle_result or {}).get("player_max_hp") or 1)),
        "enemy_hp_remaining": enemy_remaining,
        "enemy_hp_max": enemy_max,
        "damage_dealt": damage_dealt,
        "analysis_rate": analysis_rate,
    }


def is_better_attempt(candidate, current):
    if not current:
        return True
    cand_clear = str(candidate.get("result") or "") == "clear"
    curr_clear = str(current.get("result") or "") == "clear"
    if cand_clear != curr_clear:
        return cand_clear
    if cand_clear:
        cand_key = (int(candidate.get("turns") or 999), -_hp_ratio(candidate), int(candidate.get("created_at") or 0))
        curr_key = (int(current.get("turns") or 999), -_hp_ratio(current), int(current.get("created_at") or 0))
        return cand_key < curr_key
    cand_key = (-int(candidate.get("analysis_rate") or 0), -_hp_ratio(candidate), -int(candidate.get("damage_dealt") or 0))
    curr_key = (-int(current.get("analysis_rate") or 0), -_hp_ratio(current), -int(current.get("damage_dealt") or 0))
    return cand_key < curr_key


def _hp_ratio(row):
    return float(row.get("player_hp_remaining") or 0) / float(max(1, int(row.get("player_hp_max") or 1)))


def user_best_attempt(db, *, user_id, week_key, challenge_class):
    ensure_schema(db)
    rows = db.execute(
        """
        SELECT *
        FROM anomaly_attempts
        WHERE user_id = ? AND week_key = ? AND challenge_class = ?
        ORDER BY created_at ASC, id ASC
        """,
        (int(user_id), str(week_key), str(challenge_class)),
    ).fetchall()
    best = None
    for row in rows:
        data = dict(row)
        if is_better_attempt(data, best):
            best = data
    return best


def ranking_rows(db, *, week_key, challenge_class, limit=5, exclude_admin=True):
    ensure_schema(db)
    where = ["a.week_key = ?", "a.challenge_class = ?"]
    params = [str(week_key), str(challenge_class)]
    if exclude_admin:
        where.append("COALESCE(u.is_admin, 0) = 0")
        where.append("COALESCE(u.is_banned, 0) = 0")
        where.append("COALESCE(u.analytics_excluded, 0) = 0")
        where.append("LOWER(COALESCE(u.username, '')) NOT LIKE 'test%'")
    rows = db.execute(
        f"""
        SELECT a.*, u.username, u.display_name, ri.name AS robot_name, ri.composed_image_path, ri.updated_at AS robot_updated_at, ri.style_key
        FROM anomaly_attempts a
        JOIN users u ON u.id = a.user_id
        LEFT JOIN robot_instances ri ON ri.id = a.robot_instance_id
        WHERE {' AND '.join(where)}
          AND NOT EXISTS (
            SELECT 1
            FROM anomaly_attempts b
            WHERE b.week_key = a.week_key
              AND b.challenge_class = a.challenge_class
              AND b.user_id = a.user_id
              AND (
                CASE WHEN b.result = 'clear' THEN 1 ELSE 0 END > CASE WHEN a.result = 'clear' THEN 1 ELSE 0 END
                OR (
                  CASE WHEN b.result = 'clear' THEN 1 ELSE 0 END = CASE WHEN a.result = 'clear' THEN 1 ELSE 0 END
                  AND (
                    (a.result = 'clear' AND (b.turns < a.turns OR (b.turns = a.turns AND CAST(b.player_hp_remaining AS REAL) / MAX(1, b.player_hp_max) > CAST(a.player_hp_remaining AS REAL) / MAX(1, a.player_hp_max))))
                    OR (a.result != 'clear' AND (b.analysis_rate > a.analysis_rate OR (b.analysis_rate = a.analysis_rate AND CAST(b.player_hp_remaining AS REAL) / MAX(1, b.player_hp_max) > CAST(a.player_hp_remaining AS REAL) / MAX(1, a.player_hp_max))))
                  )
                )
              )
          )
        ORDER BY
          CASE WHEN a.result = 'clear' THEN 0 ELSE 1 END ASC,
          CASE WHEN a.result = 'clear' THEN a.turns ELSE 999 END ASC,
          CASE WHEN a.result = 'clear' THEN CAST(a.player_hp_remaining AS REAL) / MAX(1, a.player_hp_max) ELSE 0 END DESC,
          CASE WHEN a.result != 'clear' THEN a.analysis_rate ELSE 100 END DESC,
          CASE WHEN a.result != 'clear' THEN CAST(a.player_hp_remaining AS REAL) / MAX(1, a.player_hp_max) ELSE 0 END DESC,
          a.created_at ASC,
          a.id ASC
        LIMIT ?
        """,
        (*params, int(limit)),
    ).fetchall()
    return [dict(row) for row in rows]


def can_attempt_now(db, *, user_id, is_admin=False, now_ts=None):
    if is_admin:
        return {"allowed": True, "remaining": 0}
    ensure_schema(db)
    now_value = int(now_ts or time.time())
    row = db.execute(
        "SELECT created_at FROM anomaly_attempts WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (int(user_id),),
    ).fetchone()
    if not row:
        return {"allowed": True, "remaining": 0}
    remaining = max(0, int(ANOMALY_RETRY_CT_SECONDS) - (now_value - int(row["created_at"] or 0)))
    return {"allowed": remaining <= 0, "remaining": remaining}
