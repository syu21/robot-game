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


def generate_weights(part_type, noise=0.08, min_floor=0.01):
    part_type = _norm_type(part_type)
    base = WEIGHT_TEMPLATES[part_type]
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


def generate_noisy_weights(part_type, noise=0.08, min_floor=0.01):
    return generate_weights(part_type, noise=noise, min_floor=min_floor)


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


def compute_robot_stats(parts):
    total = {k: 0 for k in STATS}
    for p in parts:
        ps = compute_part_stats(p)
        for k in STATS:
            total[k] += ps[k]
    total_with_bonus, element = apply_set_bonus(total, parts)
    return {
        "stats": total_with_bonus,
        "power": compute_power(total_with_bonus),
        "set_bonus": element,
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
