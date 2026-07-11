import random

from services.module_traits import normalize_policy, roll_trait


STAT_KEYS = ("hp", "atk", "def", "spd", "acc", "cri")
BONUS_KEYS = tuple(f"{stat}_bonus" for stat in STAT_KEYS)

RESULT_LABELS = {
    "normal": "研究成功",
    "great": "研究大成功",
    "anomaly": "異常反応",
}

FAMILY_LABELS = {
    "sniper": "精密",
    "heavy": "重装",
    "assault": "突撃",
    "stable": "安定",
    "berserk": "暴走",
    "analysis": "解析",
    "synthesized": "合成",
}

FAMILY_PAIR_NAMES = {
    "sniper_sniper": "精密照準モジュール",
    "heavy_heavy": "重装装甲モジュール",
    "assault_assault": "突撃加速モジュール",
    "stable_stable": "安定制御モジュール",
    "berserk_berserk": "暴走出力モジュール",
    "analysis_analysis": "戦況解析モジュール",
    "assault_sniper": "精密突撃モジュール",
    "berserk_sniper": "暴走照準モジュール",
    "heavy_stable": "重装安定モジュール",
    "assault_berserk": "暴走突撃モジュール",
    "analysis_sniper": "解析照準モジュール",
    "analysis_heavy": "解析装甲モジュール",
}


def _module_value(module, key, default=0):
    if module is None:
        return default
    try:
        value = module.get(key, default)
    except AttributeError:
        value = module[key] if key in module.keys() else default
    return default if value is None else value


def synthesis_score(bonuses):
    positive_sum = sum(max(0, int(value or 0)) for value in bonuses.values())
    negative_sum = sum(abs(min(0, int(value or 0))) for value in bonuses.values())
    return int(positive_sum - (negative_sum // 2))


def synthesis_grade(result_type, score):
    if result_type == "anomaly":
        return "anomaly"
    if int(score) >= 26:
        return "complete"
    if int(score) >= 18:
        return "refined"
    return "prototype"


def synthesis_family(parent_a, parent_b):
    return "_".join(
        [
            str(_module_value(parent_a, "family", "synthesized") or "synthesized").strip(),
            str(_module_value(parent_b, "family", "synthesized") or "synthesized").strip(),
        ]
    )


def generated_name_ja(family, result_type=None):
    name = FAMILY_PAIR_NAMES.get(str(family or "").strip())
    if not name:
        parts = [part for part in str(family or "").split("_") if part]
        if len(parts) >= 2:
            name = f"{FAMILY_LABELS.get(parts[0], parts[0])}{FAMILY_LABELS.get(parts[1], parts[1])}モジュール"
        else:
            name = "研究合成モジュール"
    if result_type == "anomaly":
        return f"異常・{name}"
    return name


def synthesize_research_module(parent_a, parent_b, rng=None, research_policy_key="stable"):
    roller = rng or random
    research_policy_key = normalize_policy(research_policy_key)
    roll = float(roller.random())
    if roll < 0.05:
        result_type = "anomaly"
        max_positive = 24
        min_negative = -14
    elif roll < 0.30:
        result_type = "great"
        max_positive = 18
        min_negative = -10
    else:
        result_type = "normal"
        max_positive = 14
        min_negative = -10

    bonuses = {}
    for stat_key in STAT_KEYS:
        key = f"{stat_key}_bonus"
        base = int(round((int(_module_value(parent_a, key, 0) or 0) + int(_module_value(parent_b, key, 0) or 0)) / 2))
        if research_policy_key == "stable":
            jitter_min, jitter_max = (-1, 1) if result_type == "normal" else (0, 3)
        elif research_policy_key == "output":
            jitter_min, jitter_max = (-3, 3) if result_type == "normal" else (-2, 4)
        elif research_policy_key == "trait":
            jitter_min, jitter_max = (-3, 2) if result_type == "normal" else (-2, 3)
        else:
            jitter_min, jitter_max = (-2, 2)
        if result_type == "normal":
            value = base + int(roller.randint(jitter_min, jitter_max))
        elif result_type == "great":
            value = base + int(roller.randint(jitter_min, jitter_max))
        else:
            value = base + int(roller.randint(-2, 2))
        bonuses[key] = max(min_negative, min(max_positive, value))

    if research_policy_key == "output":
        focus_key = max(BONUS_KEYS, key=lambda stat: int(bonuses.get(stat) or 0))
        bonuses[focus_key] = min(max_positive, int(bonuses[focus_key]) + int(roller.randint(3, 6)))
        for key in BONUS_KEYS:
            if key != focus_key and int(bonuses[key]) > 0 and roller.random() < 0.45:
                bonuses[key] = max(min_negative, int(bonuses[key]) - int(roller.randint(1, 3)))

    if research_policy_key == "trait":
        for key in BONUS_KEYS:
            if int(bonuses[key]) > 0 and roller.random() < 0.35:
                bonuses[key] = max(min_negative, int(bonuses[key]) - 1)

    if result_type == "great":
        plus_keys = [key for key, value in bonuses.items() if int(value) >= 0] or list(BONUS_KEYS)
        key = roller.choice(plus_keys)
        if key in STAT_KEYS:
            key = f"{key}_bonus"
        bonuses[key] = min(max_positive, int(bonuses[key]) + 2)

    if result_type == "anomaly":
        positive_count = int(roller.randint(1, 2))
        for stat_key in roller.sample(STAT_KEYS, positive_count):
            key = f"{stat_key}_bonus"
            bonuses[key] = min(max_positive, int(bonuses[key]) + int(roller.randint(6, 12)))

        negative_total = 0
        for stat_key in roller.sample(STAT_KEYS, 2):
            key = f"{stat_key}_bonus"
            penalty = int(roller.randint(4, 8))
            bonuses[key] = max(min_negative, min(-1, int(bonuses[key]) - penalty))
            negative_total += abs(min(0, int(bonuses[key])))
        if negative_total < 8:
            lowest_key = min(BONUS_KEYS, key=lambda stat: int(bonuses[stat]))
            bonuses[lowest_key] = max(min_negative, int(bonuses[lowest_key]) - (8 - negative_total))

    family = synthesis_family(parent_a, parent_b)
    score = synthesis_score(bonuses)
    trait = roll_trait([parent_a, parent_b], research_policy_key, rng=roller)
    return {
        "result_type": result_type,
        "result_label": RESULT_LABELS[result_type],
        "synthesis_grade": synthesis_grade(result_type, score),
        "synthesis_family": family,
        "generated_name_ja": generated_name_ja(family, result_type),
        "name_ja": generated_name_ja(family, result_type),
        "bonuses": bonuses,
        "trait": trait,
        "research_policy_key": research_policy_key,
        "synthesis_score": score,
        "generation": max(int(_module_value(parent_a, "generation", 0) or 0), int(_module_value(parent_b, "generation", 0) or 0)) + 1,
    }
