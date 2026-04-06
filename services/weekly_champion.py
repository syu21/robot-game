import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone


JST = timezone(timedelta(hours=9))


def get_current_week_key(ts=None):
    dt = datetime.now(JST) if ts is None else datetime.fromtimestamp(ts, JST)
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def get_week_bounds(week_key):
    year_s, week_s = str(week_key or "").split("-W")
    year = int(year_s)
    week = int(week_s)
    start = datetime.fromisocalendar(year, week, 1).replace(tzinfo=JST)
    end = start + timedelta(days=7)
    return start, end


def get_weekly_champion_snapshot(db, week_key):
    row = db.execute(
        """
        SELECT *
        FROM weekly_champion_snapshots
        WHERE week_key = ?
        LIMIT 1
        """,
        (str(week_key),),
    ).fetchone()
    return dict(row) if row else None


def get_previous_weekly_champion_snapshot(db, week_key):
    row = db.execute(
        """
        SELECT *
        FROM weekly_champion_snapshots
        WHERE week_key < ?
        ORDER BY week_key DESC, id DESC
        LIMIT 1
        """,
        (str(week_key),),
    ).fetchone()
    return dict(row) if row else None


def select_weekly_champion_candidate(db, week_key):
    start_dt, end_dt = get_week_bounds(week_key)
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    row = db.execute(
        """
        WITH explore_counts AS (
            SELECT wel.user_id, COUNT(*) AS explore_count, MAX(wel.created_at) AS latest_explore_at
            FROM world_events_log wel
            WHERE wel.event_type = 'audit.explore.end'
              AND wel.user_id IS NOT NULL
              AND wel.created_at >= ?
              AND wel.created_at < ?
            GROUP BY wel.user_id
        ),
        boss_counts AS (
            SELECT wel.user_id, COUNT(*) AS boss_count, MAX(wel.created_at) AS latest_boss_at
            FROM world_events_log wel
            WHERE wel.event_type = 'audit.boss.defeat'
              AND wel.user_id IS NOT NULL
              AND wel.created_at >= ?
              AND wel.created_at < ?
            GROUP BY wel.user_id
        )
        SELECT
            u.id AS user_id,
            u.username,
            u.active_robot_id AS robot_instance_id,
            COALESCE(b.boss_count, 0) AS boss_count,
            COALESCE(e.explore_count, 0) AS explore_count,
            MAX(COALESCE(b.latest_boss_at, 0), COALESCE(e.latest_explore_at, 0)) AS latest_activity_at
        FROM users u
        JOIN robot_instances ri
          ON ri.id = u.active_robot_id
         AND ri.user_id = u.id
         AND ri.status = 'active'
        LEFT JOIN boss_counts b ON b.user_id = u.id
        LEFT JOIN explore_counts e ON e.user_id = u.id
        WHERE u.active_robot_id IS NOT NULL
          AND COALESCE(u.is_admin, 0) = 0
          AND COALESCE(u.is_banned, 0) = 0
          AND (COALESCE(b.boss_count, 0) > 0 OR COALESCE(e.explore_count, 0) > 0)
        ORDER BY
          COALESCE(b.boss_count, 0) DESC,
          COALESCE(e.explore_count, 0) DESC,
          MAX(COALESCE(b.latest_boss_at, 0), COALESCE(e.latest_explore_at, 0)) DESC,
          u.active_robot_id ASC
        LIMIT 1
        """,
        (start_ts, end_ts, start_ts, end_ts),
    ).fetchone()
    return dict(row) if row else None


def get_or_create_weekly_champion(db, *, week_key=None, payload_builder=None, now_ts=None):
    wk = str(week_key or get_current_week_key())
    existing = get_weekly_champion_snapshot(db, wk)
    if existing:
        return {"snapshot": existing, "created": False, "fallback": False}

    now_value = int(now_ts or time.time())
    candidate = select_weekly_champion_candidate(db, wk)
    snapshot_values = None
    fallback = False
    if candidate and payload_builder:
        payload = payload_builder(candidate)
        if payload:
            snapshot_values = {
                "week_key": wk,
                "robot_instance_id": int(candidate["robot_instance_id"]),
                "user_id": int(candidate["user_id"]),
                "robot_name": str(payload.get("robot_name") or candidate.get("robot_name") or "無名ロボ"),
                "owner_name": str(payload.get("owner_name") or candidate.get("username") or "unknown"),
                "reason_key": ("weekly_boss" if int(candidate.get("boss_count") or 0) > 0 else "weekly_explore"),
                "score_value": int(candidate.get("boss_count") or 0) * 1000 + int(candidate.get("explore_count") or 0),
                "payload_json": json.dumps(payload, ensure_ascii=False),
                "source_week_key": wk,
                "created_at": now_value,
            }
    if snapshot_values is None:
        prev = get_previous_weekly_champion_snapshot(db, wk)
        if prev:
            snapshot_values = {
                "week_key": wk,
                "robot_instance_id": int(prev["robot_instance_id"]),
                "user_id": int(prev["user_id"]),
                "robot_name": str(prev["robot_name"] or "無名ロボ"),
                "owner_name": str(prev["owner_name"] or "unknown"),
                "reason_key": "carry_over",
                "score_value": int(prev.get("score_value") or 0),
                "payload_json": str(prev.get("payload_json") or "{}"),
                "source_week_key": str(prev.get("week_key") or ""),
                "created_at": now_value,
            }
            fallback = True
    if snapshot_values is None:
        return {"snapshot": None, "created": False, "fallback": False}

    created = False
    try:
        db.execute(
            """
            INSERT INTO weekly_champion_snapshots (
                week_key, robot_instance_id, user_id, robot_name, owner_name,
                reason_key, score_value, payload_json, source_week_key, created_at,
                challenge_count, win_count, loss_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0)
            """,
            (
                snapshot_values["week_key"],
                snapshot_values["robot_instance_id"],
                snapshot_values["user_id"],
                snapshot_values["robot_name"],
                snapshot_values["owner_name"],
                snapshot_values["reason_key"],
                snapshot_values["score_value"],
                snapshot_values["payload_json"],
                snapshot_values["source_week_key"],
                snapshot_values["created_at"],
            ),
        )
        created = True
    except sqlite3.IntegrityError:
        created = False

    row = get_weekly_champion_snapshot(db, wk)
    row_fallback = bool(fallback or (row and str(row.get("reason_key") or "") == "carry_over"))
    return {"snapshot": row, "created": created, "fallback": row_fallback}


def get_weekly_champion_stats(db, snapshot_id):
    row = db.execute(
        """
        SELECT
            COUNT(*) AS challenge_count,
            COALESCE(SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END), 0) AS win_count,
            COALESCE(SUM(CASE WHEN result = 'lose' THEN 1 ELSE 0 END), 0) AS loss_count
        FROM weekly_champion_battles
        WHERE champion_snapshot_id = ?
        """,
        (int(snapshot_id),),
    ).fetchone()
    challenge_count = int((row["challenge_count"] if row else 0) or 0)
    challenger_win_count = int((row["win_count"] if row else 0) or 0)
    challenger_loss_count = int((row["loss_count"] if row else 0) or 0)
    champion_win_count = challenger_loss_count
    champion_win_rate = int(round((champion_win_count / challenge_count) * 100)) if challenge_count > 0 else 100
    return {
        "challenge_count": challenge_count,
        "challenger_win_count": challenger_win_count,
        "challenger_loss_count": challenger_loss_count,
        "champion_win_count": champion_win_count,
        "champion_win_rate": champion_win_rate,
        "defeat_count": challenger_win_count,
    }


def list_weekly_champion_battles(db, snapshot_id, *, limit=10):
    rows = db.execute(
        """
        SELECT *
        FROM weekly_champion_battles
        WHERE champion_snapshot_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (int(snapshot_id), int(limit)),
    ).fetchall()
    return [dict(row) for row in rows]
