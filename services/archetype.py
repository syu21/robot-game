ARCHETYPE_DEFS = {
    "none": {
        "key": "none",
        "name_ja": "無印",
        "bonuses": {},
        "battle_note": "称号: 無印",
    },
    "swift": {
        "key": "swift",
        "name_ja": "疾風型",
        "bonuses": {"first_strike_damage_mult": 1.10},
        "battle_note": "称号: 疾風型（先攻ダメージ+10%）",
    },
    "fortress": {
        "key": "fortress",
        "name_ja": "鉄壁型",
        "bonuses": {"incoming_damage_mult": 0.90},
        "battle_note": "称号: 鉄壁型（被ダメージ-10%）",
    },
    "sniper": {
        "key": "sniper",
        "name_ja": "狙撃型",
        "bonuses": {"hit_bonus": 0.03},
        "battle_note": "称号: 狙撃型（命中率+3%）",
    },
}


def _extract_weight_totals(part_instances_or_weights):
    keys = ("w_hp", "w_atk", "w_def", "w_spd", "w_acc", "w_cri")
    if isinstance(part_instances_or_weights, dict):
        if all(k in part_instances_or_weights for k in keys):
            return {k: float(part_instances_or_weights.get(k) or 0.0) for k in keys}
        return {k: float(part_instances_or_weights.get(k.replace("w_", ""), 0.0) or 0.0) for k in keys}
    totals = {k: 0.0 for k in keys}
    for item in part_instances_or_weights or []:
        for k in keys:
            totals[k] += float(item.get(k) or 0.0)
    return totals


def compute_archetype(part_instances_or_weights):
    totals = _extract_weight_totals(part_instances_or_weights)
    total_sum = sum(totals.values())
    if total_sum <= 0:
        return dict(ARCHETYPE_DEFS["none"])

    ratios = {k: (v / total_sum) for k, v in totals.items()}
    dominant = max(ratios, key=ratios.get)
    key = "none"
    if dominant == "w_spd":
        key = "swift"
    elif dominant == "w_def":
        key = "fortress"
    elif dominant == "w_acc":
        key = "sniper"

    out = dict(ARCHETYPE_DEFS[key])
    out["dominant_weight"] = dominant
    out["ratios"] = ratios
    return out
