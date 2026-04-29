ADVANTAGE_ATTACK_MULTIPLIER = 1.12
DISADVANTAGE_ATTACK_MULTIPLIER = 0.92
NEUTRAL_ATTACK_MULTIPLIER = 1.00

TYPE_AFFINITY_ADVANTAGE = {
    "burst": "desperate",
    "desperate": "stable",
    "stable": "burst",
}

TYPE_ALIASES = {
    "desperation": "desperate",
    "desperate": "desperate",
    "burst": "burst",
    "stable": "stable",
}

TYPE_LABELS = {
    "stable": "安定",
    "burst": "爆発",
    "desperate": "背水",
    "desperation": "背水",
}


def normalize_battle_type(type_key):
    key = str(type_key or "").strip().lower()
    return TYPE_ALIASES.get(key)


def battle_type_label(type_key):
    normalized = normalize_battle_type(type_key)
    return TYPE_LABELS.get(normalized or str(type_key or "").strip().lower(), "不明")


def _message(attacker_type, defender_type, result):
    attacker_label = battle_type_label(attacker_type)
    defender_label = battle_type_label(defender_type)
    if result == "advantage":
        return f"型相性：有利。あなたの{attacker_label}型は、相手の{defender_label}型に強い！"
    if result == "disadvantage":
        return f"型相性：不利。相手の{defender_label}型は、あなたの{attacker_label}型に強い……"
    if result == "neutral":
        return "型相性：五分。型の相性差はありません。"
    return "型相性：不明。相手の型を解析できません。"


def get_type_affinity(attacker_type, defender_type):
    attacker = normalize_battle_type(attacker_type)
    defender = normalize_battle_type(defender_type)
    if not attacker or not defender:
        return {
            "result": "unknown",
            "attack_multiplier": NEUTRAL_ATTACK_MULTIPLIER,
            "defense_multiplier": NEUTRAL_ATTACK_MULTIPLIER,
            "label": "不明",
            "message": _message(attacker, defender, "unknown"),
            "attacker_type": attacker,
            "defender_type": defender,
            "attacker_label": battle_type_label(attacker),
            "defender_label": battle_type_label(defender),
        }
    if attacker == defender:
        result = "neutral"
        multiplier = NEUTRAL_ATTACK_MULTIPLIER
        label = "五分"
    elif TYPE_AFFINITY_ADVANTAGE.get(attacker) == defender:
        result = "advantage"
        multiplier = ADVANTAGE_ATTACK_MULTIPLIER
        label = "有利"
    elif TYPE_AFFINITY_ADVANTAGE.get(defender) == attacker:
        result = "disadvantage"
        multiplier = DISADVANTAGE_ATTACK_MULTIPLIER
        label = "不利"
    else:
        result = "unknown"
        multiplier = NEUTRAL_ATTACK_MULTIPLIER
        label = "不明"
    return {
        "result": result,
        "attack_multiplier": float(multiplier),
        "defense_multiplier": NEUTRAL_ATTACK_MULTIPLIER,
        "label": label,
        "message": _message(attacker, defender, result),
        "attacker_type": attacker,
        "defender_type": defender,
        "attacker_label": battle_type_label(attacker),
        "defender_label": battle_type_label(defender),
    }


def apply_affinity_damage(damage, affinity):
    value = int(damage or 0)
    if value <= 0:
        return value
    mult = float((affinity or {}).get("attack_multiplier") or NEUTRAL_ATTACK_MULTIPLIER)
    return max(1, int(round(value * mult)))
