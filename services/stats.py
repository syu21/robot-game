import math
import random

from constants import (
    FUSE_SUCCESS_TABLE,
    PLUS_WEIGHT_BONUS_CAP_MULTIPLIER,
    PLUS_WEIGHT_BONUS_K,
    SET_BONUS_TABLE,
)

STATS = ("hp", "atk", "def", "spd", "acc", "cri")
FUSE_SUCCESS_RATE = {k: v[0] for k, v in FUSE_SUCCESS_TABLE.items()}

WEIGHT_TEMPLATES = {
    "HEAD": {"hp": 0.35, "def": 0.25, "acc": 0.15, "atk": 0.10, "spd": 0.10, "cri": 0.05},
    "RIGHT_ARM": {"atk": 0.40, "acc": 0.20, "cri": 0.20, "spd": 0.10, "def": 0.05, "hp": 0.05},
    "LEFT_ARM": {"acc": 0.30, "def": 0.20, "atk": 0.20, "spd": 0.15, "cri": 0.10, "hp": 0.05},
    "LEGS": {"spd": 0.35, "def": 0.20, "hp": 0.20, "acc": 0.15, "atk": 0.05, "cri": 0.05},
}

RARITY_POWER = {"N": 12, "R": 18, "SR": 26, "SSR": 36, "UR": 48}

def _norm_type(part_type):
    if part_type in ("R_ARM", "RIGHT_ARM"):
        return "RIGHT_ARM"
    if part_type in ("L_ARM", "LEFT_ARM"):
        return "LEFT_ARM"
    return part_type


def generate_weights(part_type, noise=0.08, min_floor=0.01, bias=None):
    part_type = _norm_type(part_type)
    base = dict(WEIGHT_TEMPLATES[part_type])
    bias_map = bias or {}
    for k, v in bias_map.items():
        stat_key = str(k or "").strip().lower()
        if stat_key in STATS:
            base[stat_key] = max(min_floor, float(base.get(stat_key, min_floor)) + float(v or 0.0))
    raw = {}
    for k in STATS:
        v = base.get(k, 0.01) + random.uniform(-noise, noise)
        raw[k] = max(min_floor, v)
    total = sum(raw.values())
    if total <= 0:
        return {f"w_{k}": 1.0 / len(STATS) for k in STATS}
    normalized = {f"w_{k}": raw[k] / total for k in STATS}
    # re-normalize to avoid fp drift
    norm_total = sum(normalized.values())
    return {k: v / norm_total for k, v in normalized.items()}


def generate_noisy_weights(part_type, noise=0.08, min_floor=0.01, bias=None):
    return generate_weights(part_type, noise=noise, min_floor=min_floor, bias=bias)


def plus_common(plus):
    return round(1 * (1.45**plus))


def plus_hp_common(plus):
    return round(2 * (1.35**plus))


def compute_part_stats(part_instance):
    rarity = (part_instance.get("rarity") or "N").upper()
    p_unique = RARITY_POWER.get(rarity, 12)
    plus = int(part_instance.get("plus") or 0)
    common = plus_common(plus)
    hp_common = plus_hp_common(plus)
    out = {}
    weights = {}
    for s in STATS:
        w = float(part_instance.get(f"w_{s}") or 0.0)
        weights[s] = max(0.0, w)
        unique_stat = round(p_unique * w)
        out[s] = unique_stat + (hp_common if s == "hp" else common)
    if plus > 0:
        w_sum = sum(weights.values())
        if w_sum > 0:
            for s in STATS:
                ratio = weights[s] / w_sum
                bonus = math.floor(plus * PLUS_WEIGHT_BONUS_K * ratio)
                bonus = min(bonus, plus * PLUS_WEIGHT_BONUS_CAP_MULTIPLIER)
                if bonus > 0:
                    out[s] += bonus
    return out


def apply_set_bonus(stats, parts):
    elements = [p.get("element") for p in parts if p]
    if len(elements) != 4:
        return dict(stats), None
    e0 = elements[0]
    if not e0 or any(e != e0 for e in elements):
        return dict(stats), None
    bonus = SET_BONUS_TABLE.get(e0.upper())
    if not bonus:
        return dict(stats), None
    s, rate = bonus
    out = dict(stats)
    boosted = int(math.ceil(out[s] * (1.0 + rate)))
    out[s] = max(out[s] + 1, boosted) if out[s] > 0 else boosted
    return out, e0.upper()


def _normalize_series_key(series_key):
    key = str(series_key or "").strip()
    return key


def count_series(parts, series_bonus_defs=None):
    valid_keys = set((series_bonus_defs or {}).keys())
    counts = {}
    for part in parts or ():
        if not part:
            continue
        key = _normalize_series_key(part.get("series"))
        if not key:
            continue
        if valid_keys and key not in valid_keys:
            continue
        counts[key] = int(counts.get(key, 0)) + 1
    return counts


def _series_bonus_scale(progress_layer, pieces_required):
    layer = max(1, min(5, int(progress_layer or 1)))
    pieces = int(pieces_required or 0)
    if pieces <= 0:
        return 0.0, ""
    if pieces == 2:
        if layer >= 3:
            return 1.0, "強"
        if layer >= 2:
            return 0.6, "弱"
        return 0.0, ""
    if pieces == 4:
        if layer >= 5:
            return 1.0, "最大"
        if layer >= 4:
            return 0.7, "解禁"
        return 0.0, ""
    if layer >= 5:
        return 1.0, "最大"
    return 0.0, ""


def apply_series_bonus(stats, parts, series_bonus_defs=None, progress_layer=5):
    out = dict(stats)
    defs = series_bonus_defs or {}
    counts = count_series(parts, defs)
    applied = []
    for series_key, part_count in counts.items():
        bonus_rows = list(defs.get(series_key) or [])
        for bonus in bonus_rows:
            pieces_required = int(bonus.get("pieces_required") or 0)
            if not pieces_required or part_count < pieces_required:
                continue
            stat_key = str(bonus.get("stat_key") or "").strip().lower()
            if stat_key not in STATS:
                continue
            value_type = str(bonus.get("value_type") or "percent").strip().lower()
            configured_value = float(bonus.get("value") or 0.0)
            before_value = int(out.get(stat_key) or 0)
            if value_type == "flat":
                stage_label = "固定"
                applied_value = configured_value
                after_value = max(1, before_value + int(round(applied_value)))
            else:
                value_type = "percent"
                scale, stage_label = _series_bonus_scale(progress_layer, pieces_required)
                if scale <= 0.0:
                    continue
                applied_value = configured_value * scale
                if before_value > 0 and applied_value < 0:
                    reduced_value = int(math.floor(before_value * (1.0 + applied_value)))
                    after_value = max(1, min(before_value - 1, reduced_value))
                else:
                    boosted_value = int(math.ceil(before_value * (1.0 + applied_value)))
                    after_value = max(before_value + 1, boosted_value) if before_value > 0 else boosted_value
            out[stat_key] = after_value
            applied.append(
                {
                    "series_key": series_key,
                    "pieces_required": pieces_required,
                    "count": int(part_count),
                    "stat_key": stat_key,
                    "value_type": value_type,
                    "configured_value": configured_value,
                    "applied_value": applied_value,
                    "stage_label": stage_label,
                    "before_value": before_value,
                    "after_value": after_value,
                    "delta_value": int(after_value - before_value),
                }
            )
    return out, counts, applied


def compute_power(stats):
    # Lightweight display metric.
    return round(
        stats["hp"] * 0.8
        + stats["atk"] * 1.4
        + stats["def"] * 1.1
        + stats["spd"] * 1.1
        + stats["acc"] * 0.9
        + stats["cri"] * 1.2,
        1,
    )


def compute_robot_stats(parts, *, series_bonus_defs=None, series_progress_layer=5, disable_set_bonus=False):
    total = {k: 0 for k in STATS}
    for p in parts:
        ps = compute_part_stats(p)
        for k in STATS:
            total[k] += ps[k]
    if disable_set_bonus:
        series_counts = count_series(parts, series_bonus_defs)
        return {
            "stats": total,
            "power": compute_power(total),
            "set_bonus": None,
            "series_counts": series_counts,
            "series_bonus": [],
            "set_bonus_enabled": False,
        }
    total_with_bonus, element = apply_set_bonus(total, parts)
    total_with_series, series_counts, series_bonus = apply_series_bonus(
        total_with_bonus,
        parts,
        series_bonus_defs=series_bonus_defs,
        progress_layer=series_progress_layer,
    )
    return {
        "stats": total_with_series,
        "power": compute_power(total_with_series),
        "set_bonus": element,
        "series_counts": series_counts,
        "series_bonus": series_bonus,
        "set_bonus_enabled": True,
    }


def fuse_success_rate(plus):
    return FUSE_SUCCESS_TABLE.get(int(plus), (5, 8))[0]


def roll_fuse_outcome(plus):
    rate = fuse_success_rate(plus)
    roll = random.randint(1, 100)
    if roll > rate:
        return "fail", 0
    # Great success chance inside success window.
    great_rate = FUSE_SUCCESS_TABLE.get(int(plus), (5, 8))[1]
    if random.random() < (great_rate / 100.0):
        return "great", 2
    return "success", 1
