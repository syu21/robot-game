import math
import random

from balance_config import ENEMY_SEED_STATS
from services.lab_race_course import LAB_RACE_ENTRY_COUNT


LAB_CASINO_BET_AMOUNTS = (10, 50, 100)
LAB_CASINO_STARTING_COINS = 1000
LAB_CASINO_DAILY_GRANT = 500
LAB_CASINO_WATCH_BONUS = 20
LAB_CASINO_COIN_CAP = 5000
LAB_CASINO_ODDS_MIN = 1.8
LAB_CASINO_ODDS_MAX = 5.5


LAB_CASINO_ROLE_LABELS = {
    "speed": "速攻型",
    "tank": "堅実型",
    "chaos": "暴走型",
    "balanced": "バランス型",
    "heavy": "重量型",
    "miracle": "奇跡型",
}


LAB_CASINO_CONDITIONS = {
    "excellent": {"label": "絶好調", "stats": {"spd": 2, "def": 1, "acc": 1, "cri": 1, "luck": 2}, "score_bonus": 2.4},
    "good": {"label": "好調", "stats": {"spd": 1, "def": 1, "acc": 1, "cri": 0, "luck": 1}, "score_bonus": 1.2},
    "normal": {"label": "平常", "stats": {"spd": 0, "def": 0, "acc": 0, "cri": 0, "luck": 0}, "score_bonus": 0.0},
    "bad": {"label": "不調", "stats": {"spd": -1, "def": -1, "acc": -1, "cri": 0, "luck": -1}, "score_bonus": -1.6},
}


ROLE_RISK = {
    "speed": 0.09,
    "tank": -0.03,
    "chaos": 0.13,
    "balanced": 0.0,
    "heavy": -0.02,
    "miracle": 0.06,
}


ROLE_DASH = {
    "speed": 0.03,
    "tank": -0.01,
    "chaos": 0.05,
    "balanced": 0.0,
    "heavy": -0.01,
    "miracle": 0.06,
}


def _enemy_path(enemy_key, fallback):
    item = ENEMY_SEED_STATS.get(enemy_key) or {}
    return str(item.get("image_path") or fallback)


LAB_CASINO_BOT_DEFS = (
    {
        "bot_key": "blaze_mech",
        "display_name": "ブレイズメック",
        "role_type": "speed",
        "icon_path": _enemy_path("enemy5", "enemies/enemy5.png"),
        "blurb": "速いが事故りやすい、本命寄りの速攻型。",
        "base_stats": {"spd": 18, "def": 8, "acc": 9, "cri": 11, "luck": 8},
    },
    {
        "bot_key": "ice_guardian",
        "display_name": "アイスガーディアン",
        "role_type": "tank",
        "icon_path": _enemy_path("enemy29", "enemies/enemy29.png"),
        "blurb": "遅いが安定。堅くまとめる守備型。",
        "base_stats": {"spd": 9, "def": 17, "acc": 13, "cri": 7, "luck": 8},
    },
    {
        "bot_key": "scrap_mine",
        "display_name": "スクラップマイン",
        "role_type": "chaos",
        "icon_path": _enemy_path("enemy1", "enemies/enemy1.png"),
        "blurb": "暴走すると一発がある、荒れ枠。",
        "base_stats": {"spd": 13, "def": 10, "acc": 8, "cri": 15, "luck": 9},
    },
    {
        "bot_key": "bolt_runner",
        "display_name": "ボルトランナー",
        "role_type": "balanced",
        "icon_path": _enemy_path("enemy13", "enemies/enemy13.png"),
        "blurb": "大崩れしにくい、可もなく不可もない中庸型。",
        "base_stats": {"spd": 14, "def": 12, "acc": 12, "cri": 10, "luck": 10},
    },
    {
        "bot_key": "gravity_core",
        "display_name": "グラビティコア",
        "role_type": "heavy",
        "icon_path": _enemy_path("enemy30", "enemies/enemy30.png"),
        "blurb": "重くて鈍いが、転びにくい中穴。",
        "base_stats": {"spd": 10, "def": 16, "acc": 11, "cri": 8, "luck": 7},
    },
    {
        "bot_key": "mirage_gear",
        "display_name": "ミラージュギア",
        "role_type": "miracle",
        "icon_path": _enemy_path("enemy23", "enemies/enemy23.png"),
        "blurb": "ワープと奇跡頼みの大穴。",
        "base_stats": {"spd": 12, "def": 9, "acc": 11, "cri": 13, "luck": 15},
    },
)


def _weighted_choice(rng, options):
    total = sum(weight for _, weight in options)
    roll = rng.uniform(0.0, total)
    acc = 0.0
    for value, weight in options:
        acc += weight
        if roll <= acc:
            return value
    return options[-1][0]


def build_casino_entries(seed):
    entries = []
    score_map = {}
    for idx, bot in enumerate(LAB_CASINO_BOT_DEFS[:LAB_RACE_ENTRY_COUNT], start=1):
        rng = random.Random(f"lab-casino-entry:{int(seed)}:{bot['bot_key']}")
        condition_key = _weighted_choice(
            rng,
            (("excellent", 0.12), ("good", 0.28), ("normal", 0.42), ("bad", 0.18)),
        )
        condition = LAB_CASINO_CONDITIONS[condition_key]
        stats = {}
        for stat_key, base_value in bot["base_stats"].items():
            jitter = rng.randint(-2, 2)
            value = int(base_value) + jitter + int(condition["stats"].get(stat_key, 0))
            stats[stat_key] = max(5, min(20, value))
        score = (
            stats["spd"] * 1.28
            + stats["def"] * 0.92
            + stats["acc"] * 0.96
            + stats["cri"] * 0.76
            + stats["luck"] * 0.88
            + float(condition["score_bonus"])
            + ROLE_DASH[bot["role_type"]] * 6.0
            - ROLE_RISK[bot["role_type"]] * 2.4
            + rng.uniform(-1.0, 1.0)
        )
        score_map[bot["bot_key"]] = max(8.0, score)
        entries.append(
            {
                "entry_order": idx,
                "bot_key": bot["bot_key"],
                "display_name": bot["display_name"],
                "role_type": bot["role_type"],
                "role_label": LAB_CASINO_ROLE_LABELS[bot["role_type"]],
                "condition_key": condition_key,
                "condition_label": condition["label"],
                "description": bot["blurb"],
                "icon_path": bot["icon_path"],
                "lane_index": idx - 1,
                "spd": int(stats["spd"]),
                "def": int(stats["def"]),
                "acc": int(stats["acc"]),
                "cri": int(stats["cri"]),
                "luck": int(stats["luck"]),
            }
        )
    total_score = sum(score_map.values()) or 1.0
    for entry in entries:
        rng = random.Random(f"lab-casino-odds:{int(seed)}:{entry['bot_key']}")
        share = score_map[entry["bot_key"]] / total_score
        raw_odds = 0.86 / max(0.08, share)
        raw_odds += rng.uniform(-0.22, 0.28)
        odds = max(LAB_CASINO_ODDS_MIN, min(LAB_CASINO_ODDS_MAX, raw_odds))
        entry["odds"] = round(odds, 1)
    return entries


def payout_amount(amount, odds):
    try:
        return max(0, int(math.floor(float(amount) * float(odds))))
    except Exception:
        return 0
