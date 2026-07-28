import hashlib
import json
import time
import uuid


def _ip_hash(ip):
    if not ip:
        return None
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:24]


def audit_log(
    db,
    event_type,
    user_id=None,
    request_id=None,
    action_key=None,
    entity_type=None,
    entity_id=None,
    delta_coins=None,
    delta_count=None,
    payload=None,
    ip=None,
):
    rid = request_id or str(uuid.uuid4())
    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    now_ts = int(time.time())
    ip_digest = _ip_hash(ip)
    try:
        db.execute(
            """
            INSERT INTO world_events_log
            (created_at, event_type, payload_json, user_id, request_id, ip_hash, action_key, entity_type, entity_id, delta_coins, delta_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_ts,
                event_type,
                payload_json,
                user_id,
                rid,
                ip_digest,
                action_key,
                entity_type,
                entity_id,
                delta_coins,
                delta_count,
            ),
        )
    except Exception:
        # Backward-compatible fallback when migration has not run yet.
        db.execute(
            """
            INSERT INTO world_events_log (created_at, event_type, payload_json)
            VALUES (?, ?, ?)
            """,
            (now_ts, event_type, payload_json),
        )
    if user_id:
        try:
            from services.daily_research import (
                DAILY_RESEARCH_REWARD_SOURCE_EVENTS,
                DAILY_RESEARCH_TASK_EVENTS,
                ensure_tomorrow_research_reward,
                get_day_key,
                update_daily_task_progress,
            )

            if event_type in DAILY_RESEARCH_TASK_EVENTS:
                result = update_daily_task_progress(db, int(user_id), event_type, payload=payload or {})
                if result and result.get("claimed"):
                    try:
                        from flask import has_request_context, session

                        if has_request_context():
                            session["message"] = "今日の研究テーマ達成。コインを受け取りました。"
                    except Exception:
                        pass
            if event_type in DAILY_RESEARCH_REWARD_SOURCE_EVENTS:
                ensure_tomorrow_research_reward(db, int(user_id), get_day_key(now_ts))
        except Exception:
            pass
        try:
            from services.solo_research import (
                EVENT_EXPLORE_END,
                RESEARCH_COLLECTION_EVENTS,
                RESEARCH_TASK_EVENTS,
                process_research_collection_event,
                update_personal_records_from_explore,
                update_research_tasks_for_event,
            )

            if event_type in RESEARCH_COLLECTION_EVENTS:
                collection_updates = process_research_collection_event(
                    db,
                    int(user_id),
                    event_type,
                    payload=payload or {},
                    request_id=rid,
                    entity_type=entity_type,
                    entity_id=entity_id,
                )
                if collection_updates:
                    try:
                        from flask import has_request_context, session

                        if has_request_context():
                            session["solo_collection_updates"] = collection_updates
                    except Exception:
                        pass
            if event_type in RESEARCH_TASK_EVENTS:
                updates = update_research_tasks_for_event(db, int(user_id), event_type, payload=payload or {})
                if updates:
                    try:
                        from flask import has_request_context, session

                        if has_request_context():
                            session["solo_research_updates"] = updates
                    except Exception:
                        pass
            if event_type == EVENT_EXPLORE_END:
                records = update_personal_records_from_explore(db, int(user_id), payload or {}, include_extended=True)
                if records:
                    try:
                        from flask import has_request_context, session

                        if has_request_context():
                            session["solo_record_updates"] = records
                    except Exception:
                        pass
        except Exception:
            pass
    return rid
