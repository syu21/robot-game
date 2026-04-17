import copy
import json
from datetime import datetime, timezone


STYLE_DEFINITIONS = {
    "stable": {"label_jp": "安定", "description_jp": "防御・命中寄り（長期戦向き）"},
    "desperate": {"label_jp": "背水", "description_jp": "低耐久寄り（速攻・リスク）"},
    "burst": {"label_jp": "爆発", "description_jp": "攻撃・会心寄り（一撃型）"},
}
STYLE_LABELS = {key: value["label_jp"] for key, value in STYLE_DEFINITIONS.items()}
STYLE_KEYS = ("stable", "burst", "desperate")
STYLE_TIE_BREAK = ("stable", "burst", "desperate")
STYLE_WEIGHTS = {
    "stable": {"def": 0.35, "hp": 0.25, "acc": 0.20, "spd": 0.10, "atk": 0.05, "inv_cri": 0.05},
    "burst": {"atk": 0.35, "cri": 0.35, "acc": 0.10, "spd": 0.10, "inv_def": 0.10},
    "desperate": {"atk": 0.30, "spd": 0.25, "cri": 0.15, "acc": 0.10, "inv_hp": 0.20},
}
STYLE_PLAY_GUIDE = {
    "stable": {
        "battle_line": "耐久や命中を活かして、崩れにくく勝つ型",
        "support_line": "守りと命中で試合を安定させやすい思想です。",
    },
    "desperate": {
        "battle_line": "打たれ弱いぶん、先手や逆転で押し切る型",
        "support_line": "短期決着やギリギリの逆転を狙いやすい思想です。",
    },
    "burst": {
        "battle_line": "攻撃や会心で一気に勝負を決める型",
        "support_line": "高火力で流れをひっくり返しやすい思想です。",
    },
}

STYLE_RANK_LABELS = {
    1: "I",
    2: "II",
    3: "III",
    4: "IV",
    5: "MASTER",
}
STYLE_RANK_THRESHOLDS = (
    (150, 5),
    (70, 4),
    (30, 3),
    (10, 2),
    (0, 1),
)


def _float_stat(stats, key):
    try:
        return float((stats or {}).get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def style_score_payload_from_stats(stats):
    values = {
        "hp": _float_stat(stats, "hp"),
        "atk": _float_stat(stats, "atk"),
        "def": _float_stat(stats, "def"),
        "spd": _float_stat(stats, "spd"),
        "acc": _float_stat(stats, "acc"),
        "cri": _float_stat(stats, "cri"),
    }
    total = sum(values.values())
    if total <= 0:
        return None
    norm = {key: value / total for key, value in values.items()}
    return {
        "scores": compute_style_scores_from_norm(norm),
        "norm": norm,
    }


def compute_style_scores_from_norm(norm):
    normalized = norm or {}
    scores = {}
    for style_key, weights in STYLE_WEIGHTS.items():
        score = 0.0
        for key, weight in weights.items():
            if str(key).startswith("inv_"):
                stat_key = str(key)[4:]
                score += float(weight) * (1.0 - float(normalized.get(stat_key, 0.0)))
            else:
                score += float(weight) * float(normalized.get(key, 0.0))
        scores[style_key] = score
    return scores


def compute_style_scores(stats):
    payload = style_score_payload_from_stats(stats)
    if not payload:
        return {key: 0.0 for key in STYLE_KEYS}
    return payload["scores"]


def normalize_style_scores(raw_scores):
    raw = {key: max(0.0, float((raw_scores or {}).get(key) or 0.0)) for key in STYLE_KEYS}
    total = sum(raw.values())
    if total <= 0:
        return {key: 0 for key in STYLE_KEYS}
    exact = {key: (raw[key] / total) * 100.0 for key in STYLE_KEYS}
    base = {key: int(exact[key]) for key in STYLE_KEYS}
    remainder = 100 - sum(base.values())
    ranked_fraction = sorted(
        STYLE_KEYS,
        key=lambda key: (-(exact[key] - base[key]), STYLE_TIE_BREAK.index(key)),
    )
    for key in ranked_fraction[: max(0, remainder)]:
        base[key] += 1
    return base


def resolve_current_style(scores):
    values = scores or {}
    best = STYLE_TIE_BREAK[0]
    best_score = float(values.get(best) or 0.0)
    for key in STYLE_TIE_BREAK[1:]:
        score = float(values.get(key) or 0.0)
        if score > best_score + 1e-12:
            best = key
            best_score = score
    return best


def resolve_next_style(scores, current_key):
    current = str(current_key or "").strip().lower()
    values = scores or {}
    candidates = [key for key in STYLE_TIE_BREAK if key != current]
    if not candidates:
        return None
    best = candidates[0]
    best_score = float(values.get(best) or 0.0)
    for key in candidates[1:]:
        score = float(values.get(key) or 0.0)
        if score > best_score + 1e-12:
            best = key
            best_score = score
    return best


def build_style_snapshot(stats):
    payload = style_score_payload_from_stats(stats)
    if not payload:
        raw_scores = {key: 0.0 for key in STYLE_KEYS}
        normalized = {key: 0 for key in STYLE_KEYS}
        current_key = "stable"
    else:
        raw_scores = payload["scores"]
        normalized = normalize_style_scores(raw_scores)
        current_key = resolve_current_style(raw_scores)
    next_key = resolve_next_style(raw_scores, current_key)
    return {
        "raw_scores": {key: round(float(raw_scores.get(key) or 0.0), 6) for key in STYLE_KEYS},
        "scores": {key: int(normalized.get(key) or 0) for key in STYLE_KEYS},
        "current_key": current_key,
        "next_key": next_key,
    }


def style_rank_from_xp(xp):
    value = max(0, int(xp or 0))
    for threshold, rank in STYLE_RANK_THRESHOLDS:
        if value >= threshold:
            return rank
    return 1


def get_style_rank_label(rank):
    try:
        rank_value = int(rank or 1)
    except (TypeError, ValueError):
        rank_value = 1
    return STYLE_RANK_LABELS.get(max(1, min(5, rank_value)), "I")


def empty_style_rank_state():
    return {key: {"xp": 0, "rank": 1, "wins": 0} for key in STYLE_KEYS}


def decode_style_rank_state(raw):
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(raw or "{}")
        except (TypeError, json.JSONDecodeError):
            data = {}
    return ensure_style_rank_state(data)


def ensure_style_rank_state(raw):
    state = empty_style_rank_state()
    source = raw if isinstance(raw, dict) else {}
    for key in STYLE_KEYS:
        section = source.get(key) if isinstance(source, dict) else None
        if not isinstance(section, dict):
            continue
        xp = max(0, int(section.get("xp") or section.get("wins") or 0))
        wins = max(0, int(section.get("wins") or xp))
        rank = max(int(section.get("rank") or 1), style_rank_from_xp(xp))
        state[key] = {
            "xp": xp,
            "rank": max(1, min(5, rank)),
            "wins": wins,
        }
    return state


def encode_style_rank_state(state):
    safe = ensure_style_rank_state(state)
    return json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def award_style_xp_state(state, style_key, amount=1):
    key = str(style_key or "").strip().lower()
    if key not in STYLE_KEYS:
        key = "stable"
    qty = max(0, int(amount or 0))
    before = ensure_style_rank_state(state)
    after = copy.deepcopy(before)
    old_rank = int(after[key]["rank"])
    after[key]["xp"] = max(0, int(after[key].get("xp") or 0) + qty)
    after[key]["wins"] = max(0, int(after[key].get("wins") or 0) + qty)
    after[key]["rank"] = max(old_rank, style_rank_from_xp(after[key]["xp"]))
    new_rank = int(after[key]["rank"])
    return {
        "state": after,
        "style_key": key,
        "old_rank": old_rank,
        "new_rank": new_rank,
        "rank_up": bool(new_rank > old_rank),
        "xp": int(after[key]["xp"]),
        "wins": int(after[key]["wins"]),
        "amount": qty,
    }


def style_rank_view_rows(rank_state, current_key=None):
    state = ensure_style_rank_state(rank_state)
    current = str(current_key or "").strip().lower()
    return [
        {
            "key": key,
            "label": STYLE_LABELS[key],
            "xp": int(state[key]["xp"]),
            "wins": int(state[key]["wins"]),
            "rank": int(state[key]["rank"]),
            "rank_label": get_style_rank_label(state[key]["rank"]),
            "is_current": key == current,
        }
        for key in STYLE_KEYS
    ]


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
