import json
import math

from constants import AUDIT_EVENT_TYPES
from services.audit import audit_log


LAB_LEVEL_MILESTONES = {5, 10, 20, 30, 50, 100}

LAB_RANKS = (
    (1, "見習い研究員"),
    (3, "新米整備士"),
    (5, "実験補助員"),
    (8, "パーツ技師"),
    (10, "主任整備士"),
    (15, "機体研究員"),
    (20, "上級ラボ主任"),
    (30, "特任ロボ博士"),
    (50, "伝説の開発主任"),
    (75, "中央ラボ顧問"),
    (100, "ロボらぼ創設級"),
)


def get_required_lab_exp(level: int) -> int:
    level = max(1, int(level or 1))
    return max(1, int(math.floor(60 * (level ** 1.3))))


def get_lab_rank_label(level: int) -> str:
    level = max(1, int(level or 1))
    label = LAB_RANKS[0][1]
    for required_level, rank_label in LAB_RANKS:
        if level >= required_level:
            label = rank_label
        else:
            break
    return label


def lab_level_view(user_row) -> dict:
    level = max(1, int((user_row["lab_level"] if "lab_level" in user_row.keys() else 1) or 1))
    current_exp = max(0, int((user_row["lab_exp"] if "lab_exp" in user_row.keys() else 0) or 0))
    required_exp = get_required_lab_exp(level)
    rank_label = (
        str(user_row["lab_rank_label"] or "").strip()
        if "lab_rank_label" in user_row.keys()
        else ""
    ) or get_lab_rank_label(level)
    progress_ratio = min(1.0, max(0.0, current_exp / required_exp if required_exp > 0 else 0.0))
    return {
        "level": level,
        "current_exp": current_exp,
        "required_exp": required_exp,
        "exp_to_next": max(0, required_exp - current_exp),
        "rank_label": rank_label,
        "total_exp": max(0, int((user_row["lab_total_exp"] if "lab_total_exp" in user_row.keys() else 0) or 0)),
        "progress_ratio": progress_ratio,
        "progress_pct": int(round(progress_ratio * 100)),
    }


def _milestones_crossed(before: int, after: int) -> list[int]:
    return sorted(level for level in LAB_LEVEL_MILESTONES if int(before) < level <= int(after))


def grant_lab_exp(
    db,
    user_id: int,
    action_key: str,
    exp: int,
    source_entity_type: str | None = None,
    source_entity_id: int | None = None,
    payload: dict | None = None,
) -> dict:
    exp_delta = max(0, int(exp or 0))
    user = db.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if not user or exp_delta <= 0:
        return {
            "exp_delta": 0,
            "level_before": 1,
            "level_after": 1,
            "leveled_up": False,
            "rank_before": "見習い研究員",
            "rank_after": "見習い研究員",
            "current_exp": 0,
            "required_exp": get_required_lab_exp(1),
            "exp_to_next": get_required_lab_exp(1),
            "progress_ratio": 0.0,
            "milestone": False,
        }

    level_before = max(1, int((user["lab_level"] if "lab_level" in user.keys() else 1) or 1))
    lab_exp_before = max(0, int((user["lab_exp"] if "lab_exp" in user.keys() else 0) or 0))
    total_before = max(0, int((user["lab_total_exp"] if "lab_total_exp" in user.keys() else 0) or 0))
    rank_before = (
        str(user["lab_rank_label"] or "").strip()
        if "lab_rank_label" in user.keys()
        else ""
    ) or get_lab_rank_label(level_before)

    level_after = level_before
    lab_exp_after = lab_exp_before + exp_delta
    while lab_exp_after >= get_required_lab_exp(level_after):
        lab_exp_after -= get_required_lab_exp(level_after)
        level_after += 1

    rank_after = get_lab_rank_label(level_after)
    total_after = total_before + exp_delta
    required_after = get_required_lab_exp(level_after)
    leveled_up = level_after > level_before
    crossed = _milestones_crossed(level_before, level_after)
    milestone = bool(crossed)
    payload = dict(payload or {})

    db.execute(
        """
        UPDATE users
        SET lab_level = ?,
            lab_exp = ?,
            lab_total_exp = ?,
            lab_rank_label = ?,
            lab_level_updated_at = CASE WHEN ? THEN datetime('now') ELSE lab_level_updated_at END
        WHERE id = ?
        """,
        (level_after, lab_exp_after, total_after, rank_after, 1 if leveled_up else 0, int(user_id)),
    )
    db.execute(
        """
        INSERT INTO user_lab_exp_events
        (user_id, action_key, exp_delta, lab_level_before, lab_level_after,
         lab_exp_before, lab_exp_after, lab_total_exp_after,
         source_entity_type, source_entity_id, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(user_id),
            str(action_key or "unknown"),
            exp_delta,
            level_before,
            level_after,
            lab_exp_before,
            lab_exp_after,
            total_after,
            source_entity_type,
            source_entity_id,
            json.dumps(payload, ensure_ascii=False),
        ),
    )

    audit_payload = {
        "user_id": int(user_id),
        "action_key": str(action_key or "unknown"),
        "exp_delta": exp_delta,
        "lab_level_before": level_before,
        "lab_level_after": level_after,
        "lab_exp_before": lab_exp_before,
        "lab_exp_after": lab_exp_after,
        "lab_total_exp_after": total_after,
        "required_exp": required_after,
        "exp_to_next": max(0, required_after - lab_exp_after),
        "source_entity_type": source_entity_type,
        "source_entity_id": source_entity_id,
        **payload,
    }
    audit_log(
        db,
        AUDIT_EVENT_TYPES["LAB_LEVEL_EXP_GAIN"],
        user_id=int(user_id),
        action_key=str(action_key or "unknown"),
        entity_type=source_entity_type,
        entity_id=source_entity_id,
        delta_count=exp_delta,
        payload=audit_payload,
    )
    if leveled_up:
        level_payload = {
            "user_id": int(user_id),
            "level_before": level_before,
            "level_after": level_after,
            "rank_before": rank_before,
            "rank_after": rank_after,
            "milestone": milestone,
            "milestones": crossed,
        }
        audit_log(
            db,
            AUDIT_EVENT_TYPES["LAB_LEVEL_LEVEL_UP"],
            user_id=int(user_id),
            action_key="lab_level.level_up",
            entity_type="user",
            entity_id=int(user_id),
            payload=level_payload,
        )
        for milestone_level in crossed:
            audit_log(
                db,
                AUDIT_EVENT_TYPES["LAB_LEVEL_MILESTONE"],
                user_id=int(user_id),
                action_key="lab_level.milestone",
                entity_type="user",
                entity_id=int(user_id),
                payload={
                    **level_payload,
                    "milestone_level": milestone_level,
                    "message": f"研究室が Lv.{milestone_level} に到達。{get_lab_rank_label(milestone_level)}として記録庫に登録されました。",
                },
            )

    progress_ratio = min(1.0, max(0.0, lab_exp_after / required_after if required_after else 0.0))
    return {
        "exp_delta": exp_delta,
        "level_before": level_before,
        "level_after": level_after,
        "leveled_up": leveled_up,
        "rank_before": rank_before,
        "rank_after": rank_after,
        "current_exp": lab_exp_after,
        "required_exp": required_after,
        "exp_to_next": max(0, required_after - lab_exp_after),
        "progress_ratio": progress_ratio,
        "milestone": milestone,
        "milestones": crossed,
    }
