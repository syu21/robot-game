import json
import random
import time
from datetime import datetime, timedelta, timezone


JST = timezone(timedelta(hours=9))

FACTION_KEYS = ("ignis", "ventra", "aurix")
FACTION_LABELS = {
    "aurix": "オリクス",
    "ventra": "ヴェントラ",
    "ignis": "イグニス",
}

FACTION_POINTS = {
    "explore_win": 1,
    "build": 2,
    "strengthen": 1,
    "evolve": 8,
    "boss_defeat": 20,
    "champ_defeat": 15,
    "champ_upset": 30,
}

FACTION_COUNTER_COLUMNS = {
    "explore_win_count",
    "boss_defeat_count",
    "build_count",
    "strengthen_count",
    "evolve_count",
    "champ_defeat_count",
    "upset_count",
}

BIG_LOG_EVENT_TYPES = {
    "boss_defeat",
    "evolve",
    "champ_defeat",
    "champ_upset",
    "weekly_result",
    "rank_change",
}


def get_current_week_key(now=None) -> str:
    if now is None:
        dt = datetime.now(JST)
    elif isinstance(now, datetime):
        dt = now.astimezone(JST) if now.tzinfo else now.replace(tzinfo=JST)
    else:
        dt = datetime.fromtimestamp(int(now), JST)
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_bounds(week_key: str):
    year_s, week_s = str(week_key).split("-W")
    start = datetime.fromisocalendar(int(year_s), int(week_s), 1).replace(tzinfo=JST)
    return start, start + timedelta(days=7)


def normalize_faction_key(faction):
    value = str(faction or "").strip().lower()
    return value if value in FACTION_KEYS else None


def _now_text():
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")


def _now_ts():
    return int(time.time())


def _row_get(row, key, default=None):
    if row is None:
        return default
    try:
        if key in row.keys():
            return row[key]
    except AttributeError:
        pass
    if isinstance(row, dict):
        return row.get(key, default)
    return default


def _display_username(conn, user_id):
    if not user_id:
        return "研究員"
    row = conn.execute("SELECT username, display_name FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if not row:
        return "研究員"
    return (_row_get(row, "display_name") or _row_get(row, "username") or "研究員")


def _user_faction(conn, user_id):
    if not user_id:
        return None
    row = conn.execute("SELECT faction FROM users WHERE id = ?", (int(user_id),)).fetchone()
    return normalize_faction_key(_row_get(row, "faction"))


def _default_log_message(conn, *, user_id, faction, event_type, points):
    name = _display_username(conn, user_id)
    faction_name = FACTION_LABELS.get(faction, faction)
    if event_type == "explore_win":
        return f"{faction_name} が出撃データを蓄積しました +{int(points)}"
    if event_type == "build":
        return f"{name} が新しい機体を登録。{faction_name} に +{int(points)}"
    if event_type == "strengthen":
        return f"{name} がパーツ強化に成功。{faction_name} に +{int(points)}"
    if event_type == "evolve":
        return f"{name} がパーツ進化に成功。{faction_name} の研究が進みました +{int(points)}"
    if event_type == "boss_defeat":
        return f"{name} がボス撃破！ {faction_name} に大きく貢献 +{int(points)}"
    if event_type == "champ_upset":
        return f"{name} が不利相性でチャンプ撃破！ {faction_name} に +{int(points)}"
    if event_type == "champ_defeat":
        return f"{name} がチャンプ撃破。{faction_name} に +{int(points)}"
    return f"{name} が{faction_name}に貢献 +{int(points)}"


def should_create_log(event_type, *, rng=None):
    if event_type == "explore_win":
        rand = rng or random
        return rand.random() < 0.2
    return True


def add_faction_points(
    conn,
    user_id: int,
    event_type: str,
    points: int,
    counters: dict | None = None,
    payload: dict | None = None,
    create_log: bool = True,
    week_key: str | None = None,
    message: str | None = None,
    create_audit: bool = True,
) -> dict:
    faction = _user_faction(conn, int(user_id))
    if not faction:
        return {"ok": False, "reason": "user_not_in_faction", "points": 0, "faction": None}

    wk = str(week_key or get_current_week_key())
    pts = int(points or 0)
    now_ts = _now_ts()
    now_text = _now_text()
    clean_counters = {k: int(v or 0) for k, v in (counters or {}).items() if k in FACTION_COUNTER_COLUMNS}
    payload_obj = dict(payload or {})
    payload_json = json.dumps(payload_obj, ensure_ascii=False) if payload_obj else None

    conn.execute(
        """
        INSERT INTO world_faction_weekly_scores (week_key, faction, points, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(week_key, faction) DO UPDATE SET
            points = points + excluded.points,
            updated_at = excluded.updated_at
        """,
        (wk, faction, pts, now_ts),
    )

    columns = [
        "week_key",
        "user_id",
        "faction",
        "points",
        "created_at",
        "updated_at",
    ] + sorted(clean_counters.keys())
    values = [wk, int(user_id), faction, pts, now_text, now_text] + [clean_counters[k] for k in sorted(clean_counters.keys())]
    placeholders = ",".join(["?"] * len(columns))
    update_parts = ["points = points + excluded.points", "faction = excluded.faction", "updated_at = excluded.updated_at"]
    update_parts.extend(f"{k} = {k} + excluded.{k}" for k in sorted(clean_counters.keys()))
    conn.execute(
        f"""
        INSERT INTO world_faction_user_weekly_contributions ({",".join(columns)})
        VALUES ({placeholders})
        ON CONFLICT(week_key, user_id) DO UPDATE SET
            {", ".join(update_parts)}
        """,
        values,
    )

    log_created = False
    if create_log:
        log_message = message or _default_log_message(conn, user_id=user_id, faction=faction, event_type=event_type, points=pts)
        conn.execute(
            """
            INSERT INTO world_faction_logs (
                week_key, faction, user_id, event_type, message, points_delta, payload_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (wk, faction, int(user_id), str(event_type), log_message, pts, payload_json, now_text),
        )
        log_created = True

    if create_audit:
        conn.execute(
            """
            INSERT INTO world_events_log (
                created_at, event_type, payload_json, user_id, action_key, entity_type, delta_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_ts,
                "audit.faction.points.add",
                json.dumps(
                    {
                        "week_key": wk,
                        "faction": faction,
                        "event_type": str(event_type),
                        "points": pts,
                        "counters": clean_counters,
                        "payload": payload_obj,
                        "log_created": log_created,
                    },
                    ensure_ascii=False,
                ),
                int(user_id),
                str(event_type),
                "faction",
                pts,
            ),
        )
    return {"ok": True, "week_key": wk, "faction": faction, "points": pts, "log_created": log_created}


def aggregate_faction_details(conn, week_key: str) -> dict:
    rows = conn.execute(
        """
        SELECT faction,
               COALESCE(SUM(points), 0) AS points,
               COALESCE(SUM(explore_win_count), 0) AS explore_win_count,
               COALESCE(SUM(boss_defeat_count), 0) AS boss_defeat_count,
               COALESCE(SUM(build_count), 0) AS build_count,
               COALESCE(SUM(strengthen_count), 0) AS strengthen_count,
               COALESCE(SUM(evolve_count), 0) AS evolve_count,
               COALESCE(SUM(champ_defeat_count), 0) AS champ_defeat_count,
               COALESCE(SUM(upset_count), 0) AS upset_count,
               COUNT(DISTINCT user_id) AS active_user_count
        FROM world_faction_user_weekly_contributions
        WHERE week_key = ?
          AND faction IN ('ignis', 'ventra', 'aurix')
        GROUP BY faction
        """,
        (str(week_key),),
    ).fetchall()
    out = {
        k: {
            "points": 0,
            "explore_win_count": 0,
            "boss_defeat_count": 0,
            "build_count": 0,
            "strengthen_count": 0,
            "evolve_count": 0,
            "champ_defeat_count": 0,
            "upset_count": 0,
            "active_user_count": 0,
        }
        for k in FACTION_KEYS
    }
    for row in rows:
        faction = normalize_faction_key(_row_get(row, "faction"))
        if not faction:
            continue
        for key in out[faction]:
            out[faction][key] = int(_row_get(row, key, 0) or 0)
    return out


def contribution_for_user(conn, *, week_key: str, user_id: int):
    row = conn.execute(
        """
        SELECT *
        FROM world_faction_user_weekly_contributions
        WHERE week_key = ? AND user_id = ?
        """,
        (str(week_key), int(user_id)),
    ).fetchone()
    if not row:
        return {
            "points": 0,
            "rank": None,
            "explore_win_count": 0,
            "boss_defeat_count": 0,
            "build_count": 0,
            "strengthen_count": 0,
            "evolve_count": 0,
            "champ_defeat_count": 0,
            "upset_count": 0,
        }
    faction = normalize_faction_key(_row_get(row, "faction"))
    rank = None
    if faction:
        ranked = conn.execute(
            """
            SELECT user_id
            FROM world_faction_user_weekly_contributions
            WHERE week_key = ? AND faction = ?
            ORDER BY points DESC, user_id ASC
            """,
            (str(week_key), faction),
        ).fetchall()
        for idx, r in enumerate(ranked, start=1):
            if int(_row_get(r, "user_id") or 0) == int(user_id):
                rank = idx
                break
    out = {k: int(_row_get(row, k, 0) or 0) for k in FACTION_COUNTER_COLUMNS}
    out.update({"points": int(_row_get(row, "points", 0) or 0), "rank": rank, "faction": faction})
    return out


def rank_factions(details: dict) -> list:
    rows = []
    for faction in FACTION_KEYS:
        item = dict(details.get(faction) or {})
        item["faction"] = faction
        item["label"] = FACTION_LABELS.get(faction, faction)
        rows.append(item)
    rows.sort(key=lambda x: (-int(x.get("points") or 0), x["label"]))
    for idx, item in enumerate(rows, start=1):
        item["rank"] = idx
    return rows


def winner_reason_for(details: dict, winner: str) -> str:
    data = details.get(winner) or {}
    drivers = [
        ("ボス撃破数", int(data.get("boss_defeat_count") or 0)),
        ("進化成功数", int(data.get("evolve_count") or 0)),
        ("チャンプ突破", int(data.get("champ_defeat_count") or 0)),
        ("出撃勝利数", int(data.get("explore_win_count") or 0)),
        ("整備回数", int(data.get("strengthen_count") or 0)),
    ]
    top = [label for label, value in sorted(drivers, key=lambda x: -x[1]) if value > 0][:2]
    if not top:
        return "日常行動の積み上げでリード"
    if len(top) == 1:
        return f"{top[0]}でリード"
    return f"{top[0]}と{top[1]}でリード"


def faction_style_label(data: dict) -> str:
    candidates = [
        ("突破力", int(data.get("boss_defeat_count") or 0) * 3 + int(data.get("champ_defeat_count") or 0) * 2),
        ("研究力", int(data.get("evolve_count") or 0) * 3 + int(data.get("build_count") or 0)),
        ("周回力", int(data.get("explore_win_count") or 0)),
        ("整備力", int(data.get("strengthen_count") or 0)),
    ]
    return sorted(candidates, key=lambda x: (-x[1], x[0]))[0][0]


def compute_weekly_highlights(conn, week_key: str, winner: str, scores: dict) -> dict:
    details = aggregate_faction_details(conn, week_key)
    ranked = rank_factions(details)
    by_faction = {}
    rank_by_key = {row["faction"]: int(row["rank"]) for row in ranked}
    for faction in FACTION_KEYS:
        data = dict(details.get(faction) or {})
        data["points"] = int(scores.get(faction, data.get("points", 0)) or 0)
        data["rank"] = int(rank_by_key.get(faction, 3))
        data["style"] = faction_style_label(data)
        by_faction[faction] = data
    return {
        "winner_reason": winner_reason_for(details, winner),
        "factions": by_faction,
    }


def compute_and_store_weekly_mvp(conn, week_key: str) -> dict:
    categories = {
        "overall": ("points", "points"),
        "explore": ("explore_win_count", "explore_win_count"),
        "boss": ("boss_defeat_count", "boss_defeat_count"),
        "evolve": ("evolve_count", "evolve_count"),
        "champ": ("champ_defeat_count", "champ_defeat_count"),
        "upset": ("upset_count", "upset_count"),
    }
    conn.execute("DELETE FROM world_faction_weekly_mvp WHERE week_key = ?", (str(week_key),))
    result = {}
    for category, (column, payload_key) in categories.items():
        rows = conn.execute(
            f"""
            SELECT week_key, user_id, faction, points, {column} AS metric_value
            FROM world_faction_user_weekly_contributions
            WHERE week_key = ?
              AND faction IN ('ignis', 'ventra', 'aurix')
              AND {column} > 0
            ORDER BY {column} DESC, points DESC, user_id ASC
            LIMIT 3
            """,
            (str(week_key),),
        ).fetchall()
        if not rows:
            continue
        best = rows[0]
        faction = normalize_faction_key(_row_get(best, "faction"))
        payload = {
            "user_id": int(_row_get(best, "user_id") or 0),
            "faction": faction,
            "points": int(_row_get(best, "points") or 0),
            payload_key: int(_row_get(best, "metric_value") or 0),
        }
        conn.execute(
            """
            INSERT OR REPLACE INTO world_faction_weekly_mvp (
                week_key, faction, user_id, category, points, payload_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(week_key),
                faction,
                int(payload["user_id"]),
                category,
                int(payload["points"]),
                json.dumps(payload, ensure_ascii=False),
                _now_text(),
            ),
        )
        result[category] = payload
    return result
