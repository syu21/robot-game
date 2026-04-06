BALANCE_FAMILY_ORDER = (
    "tank",
    "stable",
    "accuracy",
    "crit",
    "burst",
    "berserk",
    "balance",
)

BALANCE_FAMILY_LABELS = {
    "tank": "鉄壁型",
    "stable": "安定型",
    "accuracy": "命中型",
    "crit": "会心型",
    "burst": "爆発型",
    "berserk": "背水型",
    "balance": "バランス型",
}


BALANCE_TEMPLATES = {
    "tank": [
        {
            "key": "tank_pure",
            "family": "tank",
            "family_label": "鉄壁型",
            "label": "鉄壁型 / 純耐久",
            "build_type": "STABLE",
            "sim_archetype": "fortress",
            "stats": {"hp": 30, "atk": 9, "def": 17, "spd": 8, "acc": 10, "cri": 4},
            "notes": "純粋な受け性能で短期火力を止める。",
        },
        {
            "key": "tank_accuracy",
            "family": "tank",
            "family_label": "鉄壁型",
            "label": "鉄壁型 / 耐久命中",
            "build_type": "STABLE",
            "sim_archetype": "fortress",
            "stats": {"hp": 28, "atk": 10, "def": 15, "spd": 9, "acc": 13, "cri": 4},
            "notes": "受けながら取りこぼしを減らす。",
        },
        {
            "key": "tank_guard",
            "family": "tank",
            "family_label": "鉄壁型",
            "label": "鉄壁型 / 防御特化",
            "build_type": "STABLE",
            "sim_archetype": "fortress",
            "stats": {"hp": 26, "atk": 9, "def": 18, "spd": 8, "acc": 11, "cri": 5},
            "notes": "防御特化で爆発型を受け止める。",
        },
    ],
    "stable": [
        {
            "key": "stable_precision",
            "family": "stable",
            "family_label": "安定型",
            "label": "安定型 / 命中制御",
            "build_type": "STABLE",
            "stats": {"hp": 24, "atk": 12, "def": 13, "spd": 11, "acc": 14, "cri": 6},
            "notes": "事故が少なく、周回向き。",
        },
        {
            "key": "stable_midline",
            "family": "stable",
            "family_label": "安定型",
            "label": "安定型 / 中庸火力",
            "build_type": "STABLE",
            "stats": {"hp": 23, "atk": 13, "def": 12, "spd": 11, "acc": 13, "cri": 6},
            "notes": "穴が小さく、極端な事故が起きにくい。",
        },
        {
            "key": "stable_guard",
            "family": "stable",
            "family_label": "安定型",
            "label": "安定型 / 守備寄り",
            "build_type": "STABLE",
            "stats": {"hp": 25, "atk": 11, "def": 14, "spd": 10, "acc": 13, "cri": 5},
            "notes": "守備と命中を両立して長期戦に耐える。",
        },
    ],
    "accuracy": [
        {
            "key": "accuracy_pure",
            "family": "accuracy",
            "family_label": "命中型",
            "label": "命中型 / 狙撃純化",
            "build_type": "STABLE",
            "sim_archetype": "sniper",
            "stats": {"hp": 20, "atk": 13, "def": 10, "spd": 12, "acc": 17, "cri": 5},
            "notes": "命中差で高速・不安定を咎める。",
        },
        {
            "key": "accuracy_speed",
            "family": "accuracy",
            "family_label": "命中型",
            "label": "命中型 / 先手狙い",
            "build_type": "STABLE",
            "sim_archetype": "sniper",
            "stats": {"hp": 19, "atk": 12, "def": 9, "spd": 14, "acc": 17, "cri": 5},
            "notes": "先手と命中を両立した高速寄り。",
        },
        {
            "key": "accuracy_thread",
            "family": "accuracy",
            "family_label": "命中型",
            "label": "命中型 / 安定狙撃",
            "build_type": "STABLE",
            "sim_archetype": "sniper",
            "stats": {"hp": 21, "atk": 13, "def": 10, "spd": 11, "acc": 18, "cri": 4},
            "notes": "高命中を優先し、着実に削る。",
        },
    ],
    "crit": [
        {
            "key": "crit_spike",
            "family": "crit",
            "family_label": "会心型",
            "label": "会心型 / 上振れ狙い",
            "build_type": "STABLE",
            "stats": {"hp": 18, "atk": 13, "def": 8, "spd": 12, "acc": 11, "cri": 18},
            "notes": "上振れで勝ち筋を作る。",
        },
        {
            "key": "crit_midline",
            "family": "crit",
            "family_label": "会心型",
            "label": "会心型 / 中庸",
            "build_type": "STABLE",
            "stats": {"hp": 19, "atk": 12, "def": 9, "spd": 12, "acc": 12, "cri": 17},
            "notes": "会心を残しつつ少しだけ安定化。",
        },
        {
            "key": "crit_glass",
            "family": "crit",
            "family_label": "会心型",
            "label": "会心型 / ガラス火力",
            "build_type": "STABLE",
            "stats": {"hp": 17, "atk": 14, "def": 7, "spd": 13, "acc": 11, "cri": 19},
            "notes": "刺さると強いが受けには弱い。",
        },
    ],
    "burst": [
        {
            "key": "burst_alpha",
            "family": "burst",
            "family_label": "爆発型",
            "label": "爆発型 / 初動火力",
            "build_type": "BURST",
            "sim_archetype": "swift",
            "stats": {"hp": 18, "atk": 17, "def": 8, "spd": 13, "acc": 10, "cri": 12},
            "notes": "短期決戦で押し切る。",
        },
        {
            "key": "burst_risky",
            "family": "burst",
            "family_label": "爆発型",
            "label": "爆発型 / 荒い一撃",
            "build_type": "BURST",
            "sim_archetype": "swift",
            "stats": {"hp": 17, "atk": 18, "def": 7, "spd": 12, "acc": 9, "cri": 13},
            "notes": "火力は高いが命中と耐久は不安定。",
        },
        {
            "key": "burst_shortfight",
            "family": "burst",
            "family_label": "爆発型",
            "label": "爆発型 / 3ターン決着寄り",
            "build_type": "BURST",
            "sim_archetype": "swift",
            "stats": {"hp": 19, "atk": 16, "def": 8, "spd": 14, "acc": 10, "cri": 11},
            "notes": "先手から一気に流れを取りに行く。",
        },
    ],
    "berserk": [
        {
            "key": "berserk_glass",
            "family": "berserk",
            "family_label": "背水型",
            "label": "背水型 / 速攻博打",
            "build_type": "BERSERK",
            "sim_archetype": "swift",
            "stats": {"hp": 18, "atk": 16, "def": 8, "spd": 13, "acc": 10, "cri": 10},
            "notes": "削られてから強いが、安定性は低い。",
        },
        {
            "key": "berserk_midline",
            "family": "berserk",
            "family_label": "背水型",
            "label": "背水型 / 中庸背水",
            "build_type": "BERSERK",
            "sim_archetype": "swift",
            "stats": {"hp": 20, "atk": 15, "def": 9, "spd": 12, "acc": 11, "cri": 9},
            "notes": "背水火力と最低限の安定を両立する。",
        },
        {
            "key": "berserk_finisher",
            "family": "berserk",
            "family_label": "背水型",
            "label": "背水型 / 決着特化",
            "build_type": "BERSERK",
            "sim_archetype": "swift",
            "stats": {"hp": 17, "atk": 17, "def": 7, "spd": 14, "acc": 10, "cri": 10},
            "notes": "ギリギリから決着火力を狙う。",
        },
    ],
    "balance": [
        {
            "key": "balance_even",
            "family": "balance",
            "family_label": "バランス型",
            "label": "バランス型 / 均整",
            "build_type": "STABLE",
            "stats": {"hp": 23, "atk": 13, "def": 12, "spd": 12, "acc": 12, "cri": 8},
            "notes": "大きな穴がなく、初心者向け。",
        },
        {
            "key": "balance_hp",
            "family": "balance",
            "family_label": "バランス型",
            "label": "バランス型 / 耐久寄り",
            "build_type": "STABLE",
            "stats": {"hp": 24, "atk": 12, "def": 12, "spd": 11, "acc": 12, "cri": 8},
            "notes": "耐久を少し厚くした万能寄り。",
        },
        {
            "key": "balance_speed",
            "family": "balance",
            "family_label": "バランス型",
            "label": "バランス型 / 先手寄り",
            "build_type": "STABLE",
            "stats": {"hp": 22, "atk": 13, "def": 11, "spd": 13, "acc": 12, "cri": 8},
            "notes": "万能のまま先手率を少し上げる。",
        },
    ],
}


def get_balance_template_catalog():
    return {key: [dict(item) for item in items] for key, items in BALANCE_TEMPLATES.items()}


def get_balance_templates_for_family(family_key):
    return [dict(item) for item in BALANCE_TEMPLATES.get(str(family_key or "").strip().lower(), [])]


def flatten_balance_templates(template_catalog=None):
    catalog = template_catalog or BALANCE_TEMPLATES
    flattened = []
    for family_key in BALANCE_FAMILY_ORDER:
        for item in catalog.get(family_key, []):
            flattened.append(dict(item))
    return flattened
