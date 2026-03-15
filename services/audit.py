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
    return rid
