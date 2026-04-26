SERIES_DEFINITIONS = [
    {
        "series_key": "insect_kabuto",
        "display_name": "カブトシリーズ",
        "category": "insect",
        "role_label": "安定",
        "description": "守りを固めて押し切る昆虫研究系。",
        "default_active": 1,
    },
    {
        "series_key": "insect_kuwagata",
        "display_name": "クワガタシリーズ",
        "category": "insect",
        "role_label": "爆発",
        "description": "一撃の伸びを狙う高火力の昆虫研究系。",
        "default_active": 1,
    },
    {
        "series_key": "insect_batta",
        "display_name": "バッタシリーズ",
        "category": "insect",
        "role_label": "速攻",
        "description": "先手と命中で差を作る昆虫研究系。",
        "default_active": 1,
    },
    {
        "series_key": "insect_scorpion",
        "display_name": "サソリシリーズ",
        "category": "insect",
        "role_label": "不安定",
        "description": "会心と火力に振れ幅を持たせた危険な研究系。",
        "default_active": 1,
    },
    {
        "series_key": "insect_bee",
        "display_name": "ハチシリーズ",
        "category": "insect",
        "role_label": "瞬発",
        "description": "短期決着を狙う機動型の昆虫研究系。",
        "default_active": 1,
    },
    {
        "series_key": "insect_ant",
        "display_name": "アリシリーズ",
        "category": "insect",
        "role_label": "バランス",
        "description": "無理なく底上げする量産研究系。",
        "default_active": 1,
    },
    {
        "series_key": "insect_butterfly",
        "display_name": "チョウシリーズ",
        "category": "insect",
        "role_label": "特殊",
        "description": "命中と回転で差を作る特殊研究系。",
        "default_active": 1,
    },
]

SERIES_VARIANTS = (
    {"series_key": "insect_kabuto", "asset_suffix": "kabuto", "name_ja": "カブト"},
    {"series_key": "insect_kuwagata", "asset_suffix": "kuwagata", "name_ja": "クワガタ"},
    {"series_key": "insect_batta", "asset_suffix": "batta", "name_ja": "バッタ"},
    {"series_key": "insect_scorpion", "asset_suffix": "scorpion", "name_ja": "サソリ"},
    {"series_key": "insect_bee", "asset_suffix": "bee", "name_ja": "ハチ"},
    {"series_key": "insect_ant", "asset_suffix": "ant", "name_ja": "アリ"},
    {"series_key": "insect_butterfly", "asset_suffix": "butterfly", "name_ja": "チョウ"},
)

SERIES_PART_SLOT_DEFS = (
    {"part_type": "HEAD", "key_prefix": "head", "image_dir": "head", "label_ja": "ヘッド"},
    {"part_type": "RIGHT_ARM", "key_prefix": "right_arm", "image_dir": "right_arm", "label_ja": "右腕"},
    {"part_type": "LEFT_ARM", "key_prefix": "left_arm", "image_dir": "left_arm", "label_ja": "左腕"},
    {"part_type": "LEGS", "key_prefix": "legs", "image_dir": "legs", "label_ja": "脚部"},
)

SERIES_BONUS_DEFINITIONS = [
    {"series_key": "insect_kabuto", "pieces_required": 2, "stat_key": "def", "value": 0.03},
    {"series_key": "insect_kabuto", "pieces_required": 4, "stat_key": "hp", "value": 0.05},
    {"series_key": "insect_kabuto", "pieces_required": 4, "stat_key": "def", "value": 0.05},
    {"series_key": "insect_kuwagata", "pieces_required": 2, "stat_key": "atk", "value": 0.03},
    {"series_key": "insect_kuwagata", "pieces_required": 4, "stat_key": "atk", "value": 0.05},
    {"series_key": "insect_kuwagata", "pieces_required": 4, "stat_key": "cri", "value": 0.05},
    {"series_key": "insect_batta", "pieces_required": 2, "stat_key": "spd", "value": 0.03},
    {"series_key": "insect_batta", "pieces_required": 4, "stat_key": "spd", "value": 0.05},
    {"series_key": "insect_batta", "pieces_required": 4, "stat_key": "acc", "value": 0.05},
    {"series_key": "insect_scorpion", "pieces_required": 2, "stat_key": "cri", "value": 0.03},
    {"series_key": "insect_scorpion", "pieces_required": 4, "stat_key": "atk", "value": 0.04},
    {"series_key": "insect_scorpion", "pieces_required": 4, "stat_key": "cri", "value": 0.06},
    {"series_key": "insect_bee", "pieces_required": 2, "stat_key": "acc", "value": 0.03},
    {"series_key": "insect_bee", "pieces_required": 4, "stat_key": "spd", "value": 0.04},
    {"series_key": "insect_bee", "pieces_required": 4, "stat_key": "atk", "value": 0.04},
    {"series_key": "insect_ant", "pieces_required": 2, "stat_key": "hp", "value": 0.02},
    {"series_key": "insect_ant", "pieces_required": 4, "stat_key": "atk", "value": 0.03},
    {"series_key": "insect_ant", "pieces_required": 4, "stat_key": "def", "value": 0.03},
    {"series_key": "insect_butterfly", "pieces_required": 2, "stat_key": "def", "value": 0.02},
    {"series_key": "insect_butterfly", "pieces_required": 4, "stat_key": "acc", "value": 0.04},
    {"series_key": "insect_butterfly", "pieces_required": 4, "stat_key": "spd", "value": 0.04},
]

SERIES_PART_DEFINITIONS = []
PART_KEY_SERIES_ASSIGNMENTS = {}
for variant in SERIES_VARIANTS:
    for slot in SERIES_PART_SLOT_DEFS:
        key = f"{slot['key_prefix']}_{variant['asset_suffix']}"
        SERIES_PART_DEFINITIONS.append(
            {
                "key": key,
                "part_type": slot["part_type"],
                "image_path": f"parts/{slot['image_dir']}/{key}.png",
                "rarity": "N",
                "element": "NORMAL",
                "series": variant["series_key"],
                "display_name_ja": f"{variant['name_ja']}{slot['label_ja']}",
            }
        )
        PART_KEY_SERIES_ASSIGNMENTS[key] = variant["series_key"]

LEGACY_GENERIC_SERIES_KEYS = {"", "S1", "n1"}

SERIES_METADATA_BY_KEY = {
    str(item["series_key"]): dict(item)
    for item in SERIES_DEFINITIONS
}
