ENEMY_SEED_STATS = {
    "scrap_mite": {"name_ja": "スクラップ・マイト", "image_path": "assets/placeholder_enemy.png", "tier": 1, "element": "NORMAL", "hp": 28, "atk": 7, "def": 6, "spd": 8, "acc": 9, "cri": 2, "faction": "aurix"},
    "spark_rat": {"name_ja": "スパーク・ラット", "image_path": "assets/placeholder_enemy.png", "tier": 1, "element": "THUNDER", "hp": 24, "atk": 8, "def": 5, "spd": 11, "acc": 12, "cri": 4, "faction": "ventra"},
    "iron_pawn": {"name_ja": "アイアン・ポーン", "image_path": "assets/placeholder_enemy.png", "tier": 2, "element": "STEEL", "hp": 40, "atk": 10, "def": 9, "spd": 8, "acc": 12, "cri": 3, "faction": "aurix"},
    "wind_hopper": {"name_ja": "ウィンド・ホッパー", "image_path": "assets/placeholder_enemy.png", "tier": 2, "element": "WIND", "hp": 34, "atk": 9, "def": 7, "spd": 13, "acc": 14, "cri": 5, "faction": "ventra"},
    "frost_guard": {"name_ja": "フロスト・ガード", "image_path": "assets/placeholder_enemy.png", "tier": 3, "element": "ICE", "hp": 55, "atk": 12, "def": 11, "spd": 9, "acc": 14, "cri": 4, "faction": "ignis"},
    "ore_behemoth": {"name_ja": "オア・ベヒモス", "image_path": "assets/placeholder_enemy.png", "tier": 3, "element": "ORE", "hp": 68, "atk": 13, "def": 13, "spd": 7, "acc": 13, "cri": 3, "faction": "neutral"},
    "boss_aurix_guardian": {"name_ja": "オリクス・ガーディアン", "image_path": "enemies/boss/boss_aurix_guardian.png", "tier": 1, "element": "STEEL", "hp": 88, "atk": 10, "def": 12, "spd": 11, "acc": 12, "cri": 4, "faction": "aurix", "is_boss": 1, "boss_area_key": "layer_1", "trait": "heavy"},
    "boss_ventra_sentinel": {"name_ja": "ヴェントラ・センチネル", "image_path": "enemies/boss/boss_ventra_sentinel.png", "tier": 2, "element": "WIND", "hp": 97, "atk": 13, "def": 10, "spd": 15, "acc": 20, "cri": 5, "faction": "ventra", "is_boss": 1, "boss_area_key": "layer_2", "trait": "fast"},
    "boss_ignis_reaver": {"name_ja": "イグニス・リーヴァー", "image_path": "enemies/boss/boss_ignis_reaver.png", "tier": 3, "element": "FIRE", "hp": 122, "atk": 19, "def": 13, "spd": 13, "acc": 14, "cri": 8, "faction": "ignis", "is_boss": 1, "boss_area_key": "layer_3", "trait": "berserk"},
}

COIN_REWARD_BY_TIER = {
    1: 2,
    2: 3,
    3: 4,
}

DROP_TYPE_WEIGHTS_BY_TIER = {
    1: {"coin_only": 60, "parts_1": 38, "parts_2": 2},
    2: {"coin_only": 50, "parts_1": 45, "parts_2": 5},
    3: {"coin_only": 40, "parts_1": 55, "parts_2": 5},
}

RARITY_WEIGHTS_BY_TIER = {
    1: {"N": 78, "R": 20, "SR": 2, "SSR": 0, "UR": 0},
    2: {"N": 55, "R": 35, "SR": 9, "SSR": 1, "UR": 0},
    3: {"N": 35, "R": 40, "SR": 20, "SSR": 4, "UR": 1},
}

PLUS_WEIGHTS_BY_TIER = {
    1: {0: 100},
    2: {0: 95, 1: 5},
    3: {0: 88, 1: 10, 2: 2},
}

FUSE_COST_BY_PLUS = {
    0: 1,
    1: 2,
    2: 3,
    3: 4,
    4: 6,
    5: 8,
    6: 10,
    7: 12,
    8: 15,
    9: 20,
}
