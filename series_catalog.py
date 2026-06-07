SERIES_DEFINITIONS = [
    {
        "series_key": "insect_kabuto",
        "display_name": "カブトシリーズ",
        "short_label": "カブト",
        "category": "insect",
        "frame_type": "insect",
        "role_label": "安定",
        "description": "守りを固めて押し切る昆虫研究系。",
        "max_rarity": "R",
        "can_evolve": 1,
        "default_active": 1,
    },
    {
        "series_key": "insect_kuwagata",
        "display_name": "クワガタシリーズ",
        "short_label": "クワガタ",
        "category": "insect",
        "frame_type": "insect",
        "role_label": "爆発",
        "description": "一撃の伸びを狙う高火力の昆虫研究系。",
        "max_rarity": "R",
        "can_evolve": 1,
        "default_active": 1,
    },
    {
        "series_key": "insect_batta",
        "display_name": "バッタシリーズ",
        "short_label": "バッタ",
        "category": "insect",
        "frame_type": "insect",
        "role_label": "速攻",
        "description": "先手と命中で差を作る昆虫研究系。",
        "max_rarity": "R",
        "can_evolve": 1,
        "default_active": 1,
    },
    {
        "series_key": "insect_scorpion",
        "display_name": "サソリシリーズ",
        "short_label": "サソリ",
        "category": "insect",
        "frame_type": "insect",
        "role_label": "不安定",
        "description": "会心と火力に振れ幅を持たせた危険な研究系。",
        "max_rarity": "R",
        "can_evolve": 1,
        "default_active": 1,
    },
    {
        "series_key": "insect_bee",
        "display_name": "ハチシリーズ",
        "short_label": "ハチ",
        "category": "insect",
        "frame_type": "insect",
        "role_label": "精密速攻",
        "description": "命中と速度で差を作る精密な昆虫研究系。",
        "max_rarity": "R",
        "can_evolve": 1,
        "default_active": 1,
    },
    {
        "series_key": "insect_ant",
        "display_name": "アリシリーズ",
        "short_label": "アリ",
        "category": "insect",
        "frame_type": "insect",
        "role_label": "バランス",
        "description": "無理なく底上げする量産研究系。",
        "max_rarity": "R",
        "can_evolve": 1,
        "default_active": 1,
    },
    {
        "series_key": "insect_butterfly",
        "display_name": "チョウシリーズ",
        "short_label": "チョウ",
        "category": "insect",
        "frame_type": "insect",
        "role_label": "特殊",
        "description": "命中と回転で差を作る特殊研究系。",
        "max_rarity": "R",
        "can_evolve": 1,
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

INSECT_PART_DISPLAY_NAME_OVERRIDES = {
    "head_kuwagata": "双顎ヘッド",
    "right_arm_kuwagata": "紅顎ブレード",
    "left_arm_kuwagata": "顎砲クラッシャー",
    "legs_kuwagata": "斬脚フレーム",
    "head_bee": "針蜂ヘッド",
    "right_arm_bee": "スティングランス",
    "left_arm_bee": "蜂紋シールド",
    "legs_bee": "空戦レッグ",
    "head_butterfly": "幻蝶ヘッド",
    "right_arm_butterfly": "幻翼ブレード",
    "left_arm_butterfly": "幻翼シールド",
    "legs_butterfly": "幻蝶レッグ",
    "head_batta": "跳躍ヘッド",
    "right_arm_batta": "跳撃ランス",
    "left_arm_batta": "翡翠シールド",
    "legs_batta": "跳脚フレーム",
    "head_kabuto": "剛角ヘッド",
    "right_arm_kabuto": "三連キャノン",
    "left_arm_kabuto": "甲殻シールド",
    "legs_kabuto": "重甲レッグ",
    "head_ant": "工兵ヘッド",
    "right_arm_ant": "重機キャノン",
    "left_arm_ant": "工兵シールド",
    "legs_ant": "六脚フレーム",
    "head_scorpion": "毒蠍ヘッド",
    "right_arm_scorpion": "毒爪クロー",
    "left_arm_scorpion": "蠍甲シールド",
    "legs_scorpion": "蠍脚フレーム",
}

SERIES_BONUS_DEFINITIONS = [
    {"series_key": "insect_kabuto", "pieces_required": 2, "stat_key": "def", "value": 0.02},
    {"series_key": "insect_kabuto", "pieces_required": 4, "stat_key": "hp", "value": 0.04},
    {"series_key": "insect_kabuto", "pieces_required": 4, "stat_key": "def", "value": 0.04},
    {"series_key": "insect_kabuto", "pieces_required": 4, "stat_key": "spd", "value": -0.02},
    {"series_key": "insect_kuwagata", "pieces_required": 2, "stat_key": "atk", "value": 0.02},
    {"series_key": "insect_kuwagata", "pieces_required": 4, "stat_key": "atk", "value": 0.05},
    {"series_key": "insect_kuwagata", "pieces_required": 4, "stat_key": "cri", "value": 0.04},
    {"series_key": "insect_kuwagata", "pieces_required": 4, "stat_key": "acc", "value": -0.02},
    {"series_key": "insect_batta", "pieces_required": 2, "stat_key": "spd", "value": 0.02},
    {"series_key": "insect_batta", "pieces_required": 4, "stat_key": "spd", "value": 0.06},
    {"series_key": "insect_batta", "pieces_required": 4, "stat_key": "hp", "value": -0.03},
    {"series_key": "insect_batta", "pieces_required": 4, "stat_key": "def", "value": -0.03},
    {"series_key": "insect_scorpion", "pieces_required": 2, "stat_key": "cri", "value": 0.02},
    {"series_key": "insect_scorpion", "pieces_required": 4, "stat_key": "atk", "value": 0.05},
    {"series_key": "insect_scorpion", "pieces_required": 4, "stat_key": "cri", "value": 0.05},
    {"series_key": "insect_scorpion", "pieces_required": 4, "stat_key": "acc", "value": -0.03},
    {"series_key": "insect_scorpion", "pieces_required": 4, "stat_key": "hp", "value": -0.03},
    {"series_key": "insect_bee", "pieces_required": 2, "stat_key": "acc", "value": 0.02},
    {"series_key": "insect_bee", "pieces_required": 4, "stat_key": "acc", "value": 0.04},
    {"series_key": "insect_bee", "pieces_required": 4, "stat_key": "spd", "value": 0.04},
    {"series_key": "insect_bee", "pieces_required": 4, "stat_key": "atk", "value": -0.01},
    {"series_key": "insect_ant", "pieces_required": 2, "stat_key": "hp", "value": 0.01},
    {"series_key": "insect_ant", "pieces_required": 2, "stat_key": "atk", "value": 0.01},
    {"series_key": "insect_ant", "pieces_required": 2, "stat_key": "def", "value": 0.01},
    {"series_key": "insect_ant", "pieces_required": 2, "stat_key": "spd", "value": 0.01},
    {"series_key": "insect_ant", "pieces_required": 2, "stat_key": "acc", "value": 0.01},
    {"series_key": "insect_ant", "pieces_required": 2, "stat_key": "cri", "value": 0.01},
    {"series_key": "insect_ant", "pieces_required": 4, "stat_key": "hp", "value": 0.02},
    {"series_key": "insect_ant", "pieces_required": 4, "stat_key": "atk", "value": 0.02},
    {"series_key": "insect_ant", "pieces_required": 4, "stat_key": "def", "value": 0.02},
    {"series_key": "insect_ant", "pieces_required": 4, "stat_key": "spd", "value": 0.02},
    {"series_key": "insect_ant", "pieces_required": 4, "stat_key": "acc", "value": 0.02},
    {"series_key": "insect_ant", "pieces_required": 4, "stat_key": "cri", "value": 0.02},
    {"series_key": "insect_butterfly", "pieces_required": 2, "stat_key": "acc", "value": 0.02},
    {"series_key": "insect_butterfly", "pieces_required": 4, "stat_key": "acc", "value": 0.04},
    {"series_key": "insect_butterfly", "pieces_required": 4, "stat_key": "cri", "value": 0.04},
    {"series_key": "insect_butterfly", "pieces_required": 4, "stat_key": "hp", "value": -0.02},
]

SERIES_WEIGHT_BIASES = {
    "insect_kabuto": {"hp": 0.08, "def": 0.08, "spd": -0.05, "cri": -0.05, "atk": -0.02},
    "insect_kuwagata": {"atk": 0.10, "cri": 0.08, "acc": -0.05, "def": -0.07, "hp": -0.03},
    "insect_batta": {"spd": 0.12, "hp": -0.08, "def": -0.08, "atk": -0.02},
    "insect_scorpion": {"atk": 0.09, "cri": 0.10, "acc": -0.08, "hp": -0.06, "def": -0.05},
    "insect_bee": {"acc": 0.10, "spd": 0.08, "atk": 0.02, "hp": -0.07, "def": -0.07},
    "insect_ant": {"hp": 0.02, "atk": 0.02, "def": 0.02, "spd": 0.02, "acc": 0.02, "cri": 0.02},
    "insect_butterfly": {"acc": 0.08, "cri": 0.08, "spd": 0.02, "hp": -0.05, "def": -0.06, "atk": -0.04},
}

SERIES_PART_DEFINITIONS = []
INSECT_R_PART_DEFINITIONS = []
PART_KEY_SERIES_ASSIGNMENTS = {}
INSECT_R_ASSET_PATH_OVERRIDES = {}
INSECT_R_PART_DISPLAY_NAME_OVERRIDES = {
    "head_r_kabuto": "豪角ヘッド",
    "right_arm_r_kabuto": "重甲キャノン",
    "left_arm_r_kabuto": "鋼殻シールド",
    "legs_r_kabuto": "剛脚レッグ",
    "head_r_kuwagata": "双牙ヘッド",
    "right_arm_r_kuwagata": "紅牙ブレード",
    "left_arm_r_kuwagata": "顎砕クラッシャー",
    "legs_r_kuwagata": "剛斬脚フレーム",
    "head_r_batta": "飛躍ヘッド",
    "right_arm_r_batta": "跳撃ランサー",
    "left_arm_r_batta": "翡翠ガード",
    "legs_r_batta": "疾跳フレーム",
    "head_r_scorpion": "鋭蠍ヘッド",
    "right_arm_r_scorpion": "猛毒クロー",
    "left_arm_r_scorpion": "蠍甲ガード",
    "legs_r_scorpion": "蠍尾レッグ",
    "head_r_bee": "雷蜂ヘッド",
    "right_arm_r_bee": "雷針ランス",
    "left_arm_r_bee": "蜂紋ガード",
    "legs_r_bee": "空襲レッグ",
    "head_r_ant": "重工兵ヘッド",
    "right_arm_r_ant": "重機バスター",
    "left_arm_r_ant": "重工シールド",
    "legs_r_ant": "重六脚フレーム",
    "head_r_butterfly": "幻彩ヘッド",
    "right_arm_r_butterfly": "幻彩ブレード",
    "left_arm_r_butterfly": "幻彩シールド",
    "legs_r_butterfly": "幻舞レッグ",
}
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
                "series_key": variant["series_key"],
                "series_label": next(
                    (
                        item["display_name"]
                        for item in SERIES_DEFINITIONS
                        if item["series_key"] == variant["series_key"]
                    ),
                    variant["name_ja"],
                ),
                "frame_type": "insect",
                "display_name_ja": INSECT_PART_DISPLAY_NAME_OVERRIDES.get(
                    key,
                    f"{variant['name_ja']}{slot['label_ja']}",
                ),
            }
        )
        PART_KEY_SERIES_ASSIGNMENTS[key] = variant["series_key"]
        r_key = f"{slot['key_prefix']}_r_{variant['asset_suffix']}"
        r_image_path = INSECT_R_ASSET_PATH_OVERRIDES.get(
            r_key,
            f"parts/{slot['image_dir']}/{r_key}.png",
        )
        INSECT_R_PART_DEFINITIONS.append(
            {
                "key": r_key,
                "source_key": key,
                "part_type": slot["part_type"],
                "image_path": r_image_path,
                "rarity": "R",
                "element": "NORMAL",
                "series": variant["series_key"],
                "series_key": variant["series_key"],
                "series_label": next(
                    (
                        item["display_name"]
                        for item in SERIES_DEFINITIONS
                        if item["series_key"] == variant["series_key"]
                    ),
                    variant["name_ja"],
                ),
                "frame_type": "insect",
                "display_name_ja": INSECT_R_PART_DISPLAY_NAME_OVERRIDES[r_key],
            }
        )
        PART_KEY_SERIES_ASSIGNMENTS[r_key] = variant["series_key"]

LEGACY_GENERIC_SERIES_KEYS = {"", "S1", "n1"}

SERIES_METADATA_BY_KEY = {
    str(item["series_key"]): dict(item)
    for item in SERIES_DEFINITIONS
}
