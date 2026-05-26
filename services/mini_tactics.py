import json
import random
import time


BOARD_SIZE = 5
MAX_TURNS = 10
ALLY_START_POSITIONS = ((0, 1), (0, 2), (0, 3))
MINI_TACTICS_WALLS = ((2, 1), (2, 3))
WEAPON_SPECS = {
    "melee": {"range": 1, "label": "格闘"},
    "laser": {"range": 2, "label": "レーザー"},
    "missile": {"range": 2, "label": "ミサイル"},
}
MOVE_TYPE_LABELS = {
    "walk": "歩行",
    "flight": "飛行",
    "multi_leg": "多脚",
    "core": "コア",
}
SPECIES_MOVE_TYPES = {
    "cerberus": "walk",
    "phoenix": "flight",
    "hydra": "multi_leg",
    "dummy_a": "walk",
    "dummy_b": "walk",
    "dummy_c": "walk",
}
WEAPON_ROLES = {
    "melee": "assault",
    "laser": "shooting",
    "missile": "guard",
}
ROLE_LABELS = {
    "assault": "突撃",
    "shooting": "射撃",
    "guard": "守備",
    "core": "コア",
}
ROLE_ADVANTAGE = {
    "assault": "shooting",
    "shooting": "guard",
    "guard": "assault",
}
BOARD_V1_SIZE = 4
MANUAL_V1_ROLE_ADVANTAGE = {
    "assault": "sniper",
    "sniper": "guardian",
    "guardian": "assault",
}
MANUAL_V1_WEAPON_LABELS = {
    "melee": "格闘",
    "laser": "レーザー",
    "missile": "ミサイル",
}
MANUAL_V1_MOVE_LABELS = {
    "walker": "歩行",
    "flyer": "飛行",
}
MANUAL_V1_ROLE_LABELS = {
    "assault": "突撃",
    "sniper": "射撃",
    "guardian": "守備",
}
MANUAL_V1_TRAIT_LABELS = {
    "guard_dog": "番犬",
    "retreat_shot": "退き撃ち",
    "fortress": "要塞",
}
MANUAL_V1_ALLY_SPECS = (
    ("ally_cerberus", "ケルベロス", "cerberus", True, 0, 1, "walker", "assault", "melee", "guard_dog", "right"),
    ("ally_phoenix", "フェニックス", "phoenix", False, 0, 2, "flyer", "sniper", "laser", "retreat_shot", "right"),
    ("ally_hydra", "ヒュドラ", "hydra", False, 1, 3, "walker", "guardian", "missile", "fortress", "right"),
)
MANUAL_V1_ENEMY_SPECS = (
    ("enemy_dummy_a", "ダミーA", "dummy_a", True, 3, 1, "walker", "assault", "melee", "guard_dog", "left"),
    ("enemy_dummy_b", "ダミーB", "dummy_b", False, 3, 2, "walker", "sniper", "laser", "retreat_shot", "left"),
    ("enemy_dummy_c", "ダミーC", "dummy_c", False, 2, 0, "walker", "guardian", "missile", "fortress", "left"),
)
SPECIES_WEAPONS = {
    "cerberus": "melee",
    "phoenix": "laser",
    "hydra": "missile",
    "dummy_a": "melee",
    "dummy_b": "melee",
    "dummy_c": "melee",
}
SPECIES_SPD = {
    "cerberus": 4,
    "phoenix": 6,
    "hydra": 3,
    "dummy_a": 4,
    "dummy_b": 4,
    "dummy_c": 4,
}
RENTAL_ALLY_SPECS = (
    ("rental_cerberus", "ケルベロス", "cerberus", "assault", "melee", 18, 5, 2, 4, "mini_robots/cerberus/normal.png"),
    ("rental_phoenix", "フェニックス", "phoenix", "cautious", "laser", 14, 4, 1, 6, "mini_robots/phoenix/normal.png"),
    ("rental_hydra", "ヒュドラ", "hydra", "guardian", "missile", 20, 3, 3, 3, "mini_robots/hydra/normal.png"),
)


def build_initial_map():
    return {
        "width": BOARD_SIZE,
        "height": BOARD_SIZE,
        "tiles": [
            [
                {
                    "x": x,
                    "y": y,
                    "terrain": "wall" if (x, y) in MINI_TACTICS_WALLS else "floor",
                }
                for x in range(BOARD_SIZE)
            ]
            for y in range(BOARD_SIZE)
        ],
    }


def build_initial_units():
    return [
        {
            "unit_id": "ally_cerberus",
            "side": "ally",
            "name": "ケルベロス",
            "species_key": "cerberus",
            "x": 0,
            "y": 1,
            "hp": 18,
            "max_hp": 18,
            "atk": 5,
            "def": 2,
            "spd": 4,
            "defeated": False,
            "ai_type": "assault",
            "weapon_type": "melee",
            "weapon_label": "格闘",
            "attack_range": 1,
            "range": 1,
            "image_path": "mini_robots/cerberus/normal.png",
            "direction": "right",
        },
        {
            "unit_id": "ally_phoenix",
            "side": "ally",
            "name": "フェニックス",
            "species_key": "phoenix",
            "x": 0,
            "y": 2,
            "hp": 14,
            "max_hp": 14,
            "atk": 4,
            "def": 1,
            "spd": 6,
            "defeated": False,
            "ai_type": "cautious",
            "weapon_type": "laser",
            "weapon_label": "レーザー",
            "attack_range": 2,
            "range": 2,
            "image_path": "mini_robots/phoenix/normal.png",
            "direction": "right",
        },
        {
            "unit_id": "ally_hydra",
            "side": "ally",
            "name": "ヒュドラ",
            "species_key": "hydra",
            "x": 0,
            "y": 3,
            "hp": 20,
            "max_hp": 20,
            "atk": 3,
            "def": 3,
            "spd": 3,
            "defeated": False,
            "ai_type": "guardian",
            "weapon_type": "missile",
            "weapon_label": "ミサイル",
            "attack_range": 2,
            "range": 2,
            "image_path": "mini_robots/hydra/normal.png",
            "direction": "right",
        },
        {
            "unit_id": "enemy_dummy_a",
            "side": "enemy",
            "name": "ダミーA",
            "species_key": "dummy_a",
            "x": 4,
            "y": 1,
            "hp": 12,
            "max_hp": 12,
            "atk": 3,
            "def": 1,
            "spd": 4,
            "defeated": False,
            "ai_type": "assault",
            "weapon_type": "melee",
            "weapon_label": "格闘",
            "attack_range": 1,
            "range": 1,
            "image_path": "",
            "direction": "left",
        },
        {
            "unit_id": "enemy_dummy_b",
            "side": "enemy",
            "name": "ダミーB",
            "species_key": "dummy_b",
            "x": 4,
            "y": 2,
            "hp": 12,
            "max_hp": 12,
            "atk": 3,
            "def": 1,
            "spd": 4,
            "defeated": False,
            "ai_type": "assault",
            "weapon_type": "melee",
            "weapon_label": "格闘",
            "attack_range": 1,
            "range": 1,
            "image_path": "",
            "direction": "left",
        },
        {
            "unit_id": "enemy_dummy_c",
            "side": "enemy",
            "name": "ダミーC",
            "species_key": "dummy_c",
            "x": 4,
            "y": 3,
            "hp": 12,
            "max_hp": 12,
            "atk": 3,
            "def": 1,
            "spd": 4,
            "defeated": False,
            "ai_type":