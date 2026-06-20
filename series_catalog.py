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

DINO_SERIES_VARIANTS = (
    {
        "series_key": "dino_tyranno",
        "asset_suffix": "dino_tyranno",
        "name_ja": "ティラノ",
        "display_name": "ティラノフレーム",
        "role_label": "攻撃・会心",
        "description": "攻撃と会心に優れた恐竜型フレーム。短期決着を狙う研究員向け。",
        "primary_stat": "atk",
        "secondary_stat": "cri",
    },
    {
        "series_key": "dino_raptor",
        "asset_suffix": "dino_raptor",
        "name_ja": "ラプトル",
        "display_name": "ラプトルシリーズ",
        "role_label": "速度・攻撃",
        "description": "素早さと会心に優れた軽量フレーム。先手を取って攻める型。",
        "primary_stat": "spd",
        "secondary_stat": "cri",
    },
    {
        "series_key": "dino_ptera",
        "asset_suffix": "dino_ptera",
        "name_ja": "プテラ",
        "display_name": "プテラシリーズ",
        "role_label": "命中・速度",
        "description": "素早さと命中に優れた飛行型フレーム。安定して先に動きたい研究員向け。",
        "primary_stat": "acc",
        "secondary_stat": "spd",
    },
    {
        "series_key": "dino_parasa",
        "asset_suffix": "dino_parasa",
        "name_ja": "パラサ",
        "display_name": "パラサウンドフレーム",
        "role_label": "命中・防御",
        "description": "命中に優れた共鳴型フレーム。ミスを減らして安定させる型。",
        "primary_stat": "acc",
        "secondary_stat": "def",
    },
    {
        "series_key": "dino_tricera",
        "asset_suffix": "dino_tricera",
        "name_ja": "トリケラ",
        "display_name": "トリケラシリーズ",
        "role_label": "防御・HP",
        "description": "防御に優れた重装フレーム。正面から受け止めて進む型。",
        "primary_stat": "def",
        "secondary_stat": "hp",
    },
    {
        "series_key": "dino_ankylo",
        "asset_suffix": "dino_ankylo",
        "name_ja": "アンキロ",
        "display_name": "アンキロシリーズ",
        "role_label": "HP・防御",
        "description": "耐久と防御に優れた重装フレーム。遅い代わりに粘り強い型。",
        "primary_stat": "hp",
        "secondary_stat": "def",
    },
    {
        "series_key": "dino_spino",
        "asset_suffix": "dino_spino",
        "name_ja": "スピノ",
        "display_name": "スピノシリーズ",
        "role_label": "攻撃・命中",
        "description": "攻撃と命中のバランスに優れた水圧型フレーム。安定して削る型。",
        "primary_stat": "atk",
        "secondary_stat": "acc",
    },
)

SERIES_DEFINITIONS.extend(
    {
        "series_key": variant["series_key"],
        "display_name": variant["display_name"],
        "short_label": variant["name_ja"],
        "category": "dinosaur",
        "frame_type": "normal",
        "role_label": variant["role_label"],
        "description": variant["description"],
        "max_rarity": "N",
        "can_evolve": 0,
        "default_active": 1,
    }
    for variant in DINO_SERIES_VARIANTS
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

for variant in DINO_SERIES_VARIANTS:
    SERIES_BONUS_DEFINITIONS.extend(
        (
            {
                "series_key": variant["series_key"],
                "pieces_required": 2,
                "stat_key": variant["primary_stat"],
                "value": 1,
                "value_type": "flat",
            },
            {
                "series_key": variant["series_key"],
                "pieces_required": 4,
                "stat_key": variant["primary_stat"],
                "value": 1,
                "value_type": "flat",
            },
            {
                "series_key": variant["series_key"],
                "pieces_required": 4,
                "stat_key": variant["secondary_stat"],
                "value": 1,
                "value_type": "flat",
            },
        )
    )

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

DINO_PART_STATS_BY_SERIES = {
    "dino_tyranno": {
        "HEAD": {"hp": 3, "atk": 3, "def": 2, "spd": 1, "acc": 1, "cri": 2},
        "RIGHT_ARM": {"hp": 1, "atk": 4, "def": 1, "spd": 1, "acc": 2, "cri": 3},
        "LEFT_ARM": {"hp": 3, "atk": 1, "def": 4, "spd": 1, "acc": 2, "cri": 1},
        "LEGS": {"hp": 2, "atk": 2, "def": 1, "spd": 4, "acc": 1, "cri": 2},
    },
    "dino_raptor": {
        "HEAD": {"hp": 2, "atk": 2, "def": 1, "spd": 4, "acc": 1, "cri": 2},
        "RIGHT_ARM": {"hp": 1, "atk": 3, "def": 1, "spd": 3, "acc": 1, "cri": 3},
        "LEFT_ARM": {"hp": 2, "atk": 1, "def": 3, "spd": 2, "acc": 3, "cri": 1},
        "LEGS": {"hp": 1, "atk": 2, "def": 1, "spd": 5, "acc": 2, "cri": 1},
    },
    "dino_ptera": {
        "HEAD": {"hp": 2, "atk": 1, "def": 1, "spd": 3, "acc": 4, "cri": 1},
        "RIGHT_ARM": {"hp": 1, "atk": 3, "def": 1, "spd": 4, "acc": 2, "cri": 1},
        "LEFT_ARM": {"hp": 1, "atk": 1, "def": 2, "spd": 3, "acc": 4, "cri": 1},
        "LEGS": {"hp": 1, "atk": 1, "def": 1, "spd": 5, "acc": 3, "cri": 1},
    },
    "dino_parasa": {
        "HEAD": {"hp": 2, "atk": 1, "def": 2, "spd": 1, "acc": 5, "cri": 1},
        "RIGHT_ARM": {"hp": 1, "atk": 3, "def": 1, "spd": 1, "acc": 5, "cri": 1},
        "LEFT_ARM": {"hp": 3, "atk": 1, "def": 3, "spd": 1, "acc": 3, "cri": 1},
        "LEGS": {"hp": 2, "atk": 1, "def": 2, "spd": 3, "acc": 3, "cri": 1},
    },
    "dino_tricera": {
        "HEAD": {"hp": 3, "atk": 1, "def": 4, "spd": 1, "acc": 2, "cri": 1},
        "RIGHT_ARM": {"hp": 2, "atk": 3, "def": 3, "spd": 1, "acc": 2, "cri": 1},
        "LEFT_ARM": {"hp": 3, "atk": 1, "def": 4, "spd": 1, "acc": 2, "cri": 1},
        "LEGS": {"hp": 3, "atk": 1, "def": 3, "spd": 2, "acc": 2, "cri": 1},
    },
    "dino_ankylo": {
        "HEAD": {"hp": 4, "atk": 1, "def": 4, "spd": 1, "acc": 1, "cri": 1},
        "RIGHT_ARM": {"hp": 3, "atk": 3, "def": 3, "spd": 1, "acc": 1, "cri": 1},
        "LEFT_ARM": {"hp": 4, "atk": 1, "def": 4, "spd": 1, "acc": 1, "cri": 1},
        "LEGS": {"hp": 4, "atk": 1, "def": 3, "spd": 2, "acc": 1, "cri": 1},
    },
    "dino_spino": {
        "HEAD": {"hp": 3, "atk": 3, "def": 2, "spd": 1, "acc": 2, "cri": 1},
        "RIGHT_ARM": {"hp": 1, "atk": 4, "def": 1, "spd": 2, "acc": 3, "cri": 1},
        "LEFT_ARM": {"hp": 3, "atk": 1, "def": 3, "spd": 1, "acc": 3, "cri": 1},
        "LEGS": {"hp": 3, "atk": 2, "def": 2, "spd": 3, "acc": 1, "cri": 1},
    },
}

DINO_PART_DISPLAY_NAMES_BY_KEY = {
    "head_n_dino_tyranno": "ティラノヘッドコア",
    "right_arm_n_dino_tyranno": "ティラノクラッシュクロー",
    "left_arm_n_dino_tyranno": "ティラノガードシールド",
    "legs_n_dino_tyranno": "ティラノパワーレッグ",
    "head_n_dino_raptor": "ラプトルヘッドコア",
    "right_arm_n_dino_raptor": "ラプトルスラッシュアーム",
    "left_arm_n_dino_raptor": "ラプトルラウンドシールド",
    "legs_n_dino_raptor": "ラプトルランナーレッグ",
    "head_n_dino_ptera": "プテラヘッドコア",
    "right_arm_n_dino_ptera": "プテラウィングブレード",
    "left_arm_n_dino_ptera": "プテラエアシールド",
    "legs_n_dino_ptera": "プテラライトレッグ",
    "head_n_dino_parasa": "パラサウンドヘッドコア",
    "right_arm_n_dino_parasa": "パラサウンドブレード",
    "left_arm_n_dino_parasa": "パラサウンドシールド",
    "legs_n_dino_parasa": "パラサウンドスタンド",
    "head_n_dino_tricera": "トリケラホーンコア",
    "right_arm_n_dino_tricera": "トリケラドリルアーム",
    "left_arm_n_dino_tricera": "トリケラバルクシールド",
    "legs_n_dino_tricera": "トリケラスタンプレッグ",
    "head_n_dino_ankylo": "アンキロアーマーコア",
    "right_arm_n_dino_ankylo": "アンキロメイスアーム",
    "left_arm_n_dino_ankylo": "アンキロスパイクシールド",
    "legs_n_dino_ankylo": "アンキロヘビーレッグ",
    "head_n_dino_spino": "スピノセイルコア",
    "right_arm_n_dino_spino": "スピノアクアブレード",
    "left_arm_n_dino_spino": "スピノリーフシールド",
    "legs_n_dino_spino": "スピノスプラッシュレッグ",
}

DINO_PART_DEFINITIONS = []
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

for variant in DINO_SERIES_VARIANTS:
    for slot in SERIES_PART_SLOT_DEFS:
        key = f"{slot['key_prefix']}_n_{variant['asset_suffix']}"
        part = {
            "key": key,
            "part_type": slot["part_type"],
            "image_path": f"parts/dinosaur/{key}.png",
            "rarity": "N",
            "element": "NORMAL",
            "series": variant["series_key"],
            "series_key": variant["series_key"],
            "series_label": variant["display_name"],
            "frame_type": "normal",
            "display_name_ja": DINO_PART_DISPLAY_NAMES_BY_KEY[key],
            "is_admin_only": 1,
            "stats": dict(DINO_PART_STATS_BY_SERIES[variant["series_key"]][slot["part_type"]]),
        }
        DINO_PART_DEFINITIONS.append(part)
        SERIES_PART_DEFINITIONS.append(part)
        PART_KEY_SERIES_ASSIGNMENTS[key] = variant["series_key"]

DINO_PART_KEYS = tuple(part["key"] for part in DINO_PART_DEFINITIONS)
DINO_PART_STAT_BY_KEY = {part["key"]: dict(part["stats"]) for part in DINO_PART_DEFINITIONS}

LEGACY_GENERIC_SERIES_KEYS = {"", "S1", "n1"}

SERIES_METADATA_BY_KEY = {
    str(item["series_key"]): dict(item)
    for item in SERIES_DEFINITIONS
}
