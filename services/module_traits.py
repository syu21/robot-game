TRAIT_DEFS = {
    "opening_assault": {
        "label": "先制出力",
        "description": "1ターン目のみ攻撃が上昇",
        "uses": ["速攻", "爆発", "最速狙い"],
        "min": 3,
        "max": 7,
    },
    "emergency_guard": {
        "label": "緊急防壁",
        "description": "耐久50%以下の間、防御が上昇",
        "uses": ["耐久", "背水", "長期戦"],
        "min": 3,
        "max": 7,
    },
    "precision_retry": {
        "label": "照準再補正",
        "description": "MISS後の次の攻撃だけ命中が上昇",
        "uses": ["命中", "安定", "Haze攻略"],
        "min": 4,
        "max": 9,
    },
    "critical_drive": {
        "label": "臨界加速",
        "description": "会心後の次の攻撃だけ攻撃が上昇",
        "uses": ["会心", "爆発", "Pinnacle攻略"],
        "min": 3,
        "max": 6,
    },
    "boss_analysis": {
        "label": "対大型解析",
        "description": "ボス戦のみ命中と防御が上昇",
        "uses": ["ボス攻略", "安定", "初突破"],
        "min": 2,
        "max": 5,
    },
    "steady_operation": {
        "label": "安定稼働",
        "description": "攻撃以外の得意補正を安定して上乗せ",
        "uses": ["普段使い", "安定周回", "初心者"],
        "min": 2,
        "max": 5,
    },
}

POLICY_DEFS = {
    "stable": {
        "label": "安定研究",
        "description": "素材の能力を引き継ぎやすく、結果の振れ幅を抑えます。",
        "stability": "高い",
        "trait_rate": 0.20,
    },
    "output": {
        "label": "高出力研究",
        "description": "高い能力値を狙います。結果の偏りも大きくなります。",
        "stability": "低め",
        "trait_rate": 0.35,
    },
    "trait": {
        "label": "特性研究",
        "description": "作戦特性が付きやすくなります。能力値はやや不安定です。",
        "stability": "標準",
        "trait_rate": 0.75,
    },
}

STAT_LABELS = {
    "hp_bonus": "耐久",
    "atk_bonus": "攻撃",
    "def_bonus": "防御",
    "spd_bonus": "素早さ",
    "acc_bonus": "命中",
    "cri_bonus": "会心",
}


def normalize_policy(policy_key):
    key = str(policy_key or "stable").strip().lower()
    return key if key in POLICY_DEFS else "stable"


def trait_label(trait_key):
    return TRAIT_DEFS.get(str(trait_key or ""), {}).get("label", "")


def trait_description(trait_key, trait_value=0):
    info = TRAIT_DEFS.get(str(trait_key or ""))
    if not info:
        return ""
    value = int(trait_value or 0)
    suffix = f" +{value}" if value > 0 else ""
    return f"{info['description']}{suffix}"


def trait_uses(trait_key):
    return list(TRAIT_DEFS.get(str(trait_key or ""), {}).get("uses", []))


def trait_grade(value):
    value = int(value or 0)
    if value >= 7:
        return "A"
    if value >= 5:
        return "B"
    if value > 0:
        return "C"
    return None


def _module_value(module, key, default=0):
    if module is None:
        return default
    try:
        value = module.get(key, default)
    except AttributeError:
        value = module[key] if key in module.keys() else default
    return default if value is None else value


def module_bonus_dict(module):
    return {key: int(_module_value(module, key, 0) or 0) for key in STAT_LABELS}


def tendency_from_modules(modules):
    totals = {key: 0 for key in STAT_LABELS}
    for module in modules or []:
        for key in totals:
            totals[key] += int(_module_value(module, key, 0) or 0)
    if not totals:
        return {"label": "バランス", "top_keys": [], "totals": totals}
    top_value = max(totals.values())
    top_keys = [key for key, value in totals.items() if value == top_value and value > 0][:2]
    if not top_keys:
        return {"label": "バランス", "top_keys": [], "totals": totals}
    return {
        "label": "・".join(STAT_LABELS[key] for key in top_keys) + "寄り",
        "top_keys": top_keys,
        "totals": totals,
    }


def trait_candidates_for_modules(modules):
    tendency = tendency_from_modules(modules)
    top_keys = set(tendency["top_keys"])
    if {"atk_bonus", "cri_bonus"} & top_keys:
        return ["opening_assault", "critical_drive"]
    if {"def_bonus", "hp_bonus"} & top_keys:
        return ["emergency_guard", "steady_operation"]
    if "acc_bonus" in top_keys:
        return ["precision_retry", "boss_analysis"]
    return ["steady_operation", "boss_analysis"]


def synthesis_prediction(modules, policy_key="stable"):
    policy = POLICY_DEFS[normalize_policy(policy_key)]
    candidates = trait_candidates_for_modules(modules)
    tendency = tendency_from_modules(modules)
    return {
        "policy_key": normalize_policy(policy_key),
        "policy_label": policy["label"],
        "ability_tendency": tendency["label"],
        "trait_candidates": [
            {"key": key, "label": trait_label(key)}
            for key in candidates[:2]
        ],
        "stability_label": policy["stability"],
    }


def roll_trait(modules, policy_key="stable", rng=None):
    import random

    roller = rng or random
    policy_key = normalize_policy(policy_key)
    if float(roller.random()) >= float(POLICY_DEFS[policy_key]["trait_rate"]):
        return {"trait_key": None, "trait_value": 0, "trait_grade": None}
    candidates = trait_candidates_for_modules(modules)
    trait_key = roller.choice(candidates)
    if trait_key not in TRAIT_DEFS:
        trait_key = candidates[0]
    info = TRAIT_DEFS[trait_key]
    value = int(roller.randint(int(info["min"]), int(info["max"])))
    return {"trait_key": trait_key, "trait_value": value, "trait_grade": trait_grade(value)}


def module_usage_labels(module):
    trait_key = str(_module_value(module, "trait_key", "") or "")
    if trait_key:
        return trait_uses(trait_key)
    bonuses = module_bonus_dict(module)
    if bonuses["acc_bonus"] >= 6:
        return ["命中向け", "安定"]
    if bonuses["hp_bonus"] >= 8 or bonuses["def_bonus"] >= 6:
        return ["耐久向け", "長期戦"]
    if bonuses["atk_bonus"] >= 8 or bonuses["cri_bonus"] >= 6:
        return ["火力向け", "短期戦"]
    return ["普段使い"]


def module_area_fit(module, area_key):
    if not module:
        return {"label": "標準", "message": "モジュール未選択でも出撃できます。"}
    area_key = str(area_key or "")
    trait_key = str(_module_value(module, "trait_key", "") or "")
    bonuses = module_bonus_dict(module)
    good = False
    reason = "この出撃先でも基礎補正がそのまま役立ちます。"
    if area_key == "layer_4_forge":
        good = trait_key in {"emergency_guard", "steady_operation"} or bonuses["def_bonus"] >= 6 or bonuses["hp_bonus"] >= 8
        reason = "Forgeでは耐久・防御補助が扱いやすいです。"
    elif area_key == "layer_4_haze":
        good = trait_key in {"precision_retry", "boss_analysis"} or bonuses["acc_bonus"] >= 6
        reason = "Hazeでは命中補助が役立ちます。"
    elif area_key == "layer_4_burst":
        good = trait_key in {"opening_assault", "critical_drive"} or bonuses["atk_bonus"] >= 8 or bonuses["cri_bonus"] >= 6
        reason = "Burstでは攻撃・会心補助が活きます。"
    elif area_key == "layer_5_labyrinth":
        good = trait_key in {"steady_operation", "precision_retry", "emergency_guard"}
        reason = "Labyrinthでは安定・命中・耐久補助が扱いやすいです。"
    elif area_key == "layer_5_pinnacle":
        good = trait_key in {"opening_assault", "critical_drive"}
        reason = "Pinnacleでは短期決戦向けの補助が噛み合いやすいです。"
    elif area_key.endswith("_final"):
        return {"label": "標準", "message": "最終試験ではロボ本体の総合力が重要です。"}
    if good:
        return {"label": "良好", "message": reason}
    if area_key.startswith("layer_4") or area_key.startswith("layer_5"):
        return {"label": "挑戦的", "message": "勝ち筋を変えたい時に試す価値があります。"}
    return {"label": "標準", "message": reason}
