import os

RARITIES = ("N", "R", "SR", "SSR", "UR")
APP_VERSION = "0.1.32"
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "pochirobo021@gmail.com").strip() or "pochirobo021@gmail.com"
LEGAL_OPERATOR_NAME = os.getenv("LEGAL_OPERATOR_NAME", "大谷周平").strip() or "大谷周平"
LEGAL_BRAND_NAME = os.getenv("LEGAL_BRAND_NAME", "KAS Development").strip() or "KAS Development"
LEGAL_DISCLOSURE_POLICY = (
    os.getenv("LEGAL_DISCLOSURE_POLICY", "所在地・電話番号は請求があった場合、遅滞なく開示いたします。").strip()
    or "所在地・電話番号は請求があった場合、遅滞なく開示いたします。"
)

ELEMENTS = (
    ("NORMAL", "無"),
    ("FIRE", "炎"),
    ("WATER", "水"),
    ("THUNDER", "雷"),
    ("WIND", "風"),
    ("ICE", "氷"),
    ("STEEL", "鋼"),
    ("MACHINE", "機械"),
    ("ORE", "鉱石"),
)

ELEMENT_LABEL_MAP = {code: label for code, label in ELEMENTS}

SET_BONUS_TABLE = {
    "NORMAL": ("hp", 0.05),
    "FIRE": ("atk", 0.05),
    "WATER": ("spd", 0.05),
    "THUNDER": ("cri", 0.05),
    "WIND": ("acc", 0.05),
    "ICE": ("def", 0.05),
    "STEEL": ("def", 0.05),
    "MACHINE": ("acc", 0.05),
    "ORE": ("cri", 0.05),
}

# plus -> (success_rate, great_success_rate)
# great success rate is evaluated only inside success window.
FUSE_SUCCESS_TABLE = {
    0: (90, 15),
    1: (80, 15),
    2: (70, 14),
    3: (60, 13),
    4: (50, 12),
    5: (40, 11),
    6: (30, 10),
    7: (20, 10),
    8: (12, 9),
    9: (7, 8),
}

PLUS_WEIGHT_BONUS_K = 6
PLUS_WEIGHT_BONUS_CAP_MULTIPLIER = 2

FACTION_LABELS = {
    "aurix": "オリクス",
    "ventra": "ヴェントラ",
    "ignis": "イグニス",
    "neutral": "旧文明",
}

FACTION_ICONS = {
    "aurix": None,
    "ventra": None,
    "ignis": None,
    "neutral": None,
}

FACTION_EMBLEMS = {
    "aurix": "images/factions/aurix.png",
    "ignis": "images/factions/ignis.png",
    "ventra": "images/factions/ventra.png",
}

ENCOUNTER_LOGS = {
    "aurix": {
        1: [
            "巡回中のオリクス機《{enemy_name}》が現れた。",
            "管理区域でオリクス機《{enemy_name}》と遭遇。",
        ],
        2: [
            "装甲を強化したオリクス機《{enemy_name}》が立ちはだかる。",
            "防衛プロトコル発動。オリクス機《{enemy_name}》が迎撃。",
        ],
        3: [
            "重装オリクス機《{enemy_name}》が起動。",
            "深層防衛機《{enemy_name}》…反応が強い。",
        ],
    },
    "ventra": {
        1: [
            "高速機《{enemy_name}》が接近。ヴェントラ所属だ。",
            "ヴェントラ機《{enemy_name}》が旋回している。",
        ],
        2: [
            "加速反応。ヴェントラ機《{enemy_name}》が突入。",
            "機動強化型《{enemy_name}》がロックオン。",
        ],
        3: [
            "強襲型ヴェントラ機《{enemy_name}》が現れた。",
            "索敵妨害を確認。《{enemy_name}》の動きが読めない。",
        ],
    },
    "ignis": {
        1: [
            "試験機《{enemy_name}》が起動。イグニス製だ。",
            "コアが光る。《{enemy_name}》が動き出した。",
        ],
        2: [
            "出力上昇。イグニス機《{enemy_name}》が暴れ出す。",
            "不安定な機体《{enemy_name}》が迫る。",
        ],
        3: [
            "高出力コア機《{enemy_name}》が覚醒。",
            "制御不能。《{enemy_name}》が突進してくる。",
        ],
    },
    "neutral": {
        1: [
            "所属不明機《{enemy_name}》が現れた。",
            "古い機体《{enemy_name}》が起動する。",
        ],
        2: [
            "旧文明機《{enemy_name}》が静かに構える。",
            "解析不能。《{enemy_name}》の反応が強い。",
        ],
        3: [
            "深層機《{enemy_name}》が目を覚ました。",
            "規格外のコア反応。《{enemy_name}》が覚醒。",
        ],
    },
}

MID_LOGS_COMMON = [
    "火花が散る。",
    "装甲がきしむ。",
    "駆動音が跳ねる。",
    "視界が揺れる。",
    "照準がぶれる。",
]

MID_LOGS_FACTION = {
    "aurix": ["防衛プロトコルが更新された。", "装甲板が閉じる。"],
    "ventra": ["加速音が近づく。", "軌道が読めない。"],
    "ignis": ["熱が上がる。", "不規則な振動…。"],
    "neutral": ["ノイズが増える。", "静かに圧が増す。"],
}

VICTORY_LOGS = [
    "戦闘終了。回収成功。",
    "停止を確認。パーツを回収した。",
]

DEFEAT_LOGS = [
    "撤退。次に備えよう。",
    "損傷が大きい。帰還する。",
]

AUDIT_EVENT_TYPES = {
    "HOME_VIEW": "audit.home.view",
    "EXPLORE_START": "audit.explore.start",
    "EXPLORE_END": "audit.explore.end",
    "COIN_DELTA": "audit.coin.delta",
    "STREAK_BONUS": "audit.streak.bonus",
    "DROP": "audit.drop",
    "INVENTORY_DELTA": "audit.inventory.delta",
    "FUSE": "audit.fuse",
    "BUILD_CONFIRM": "audit.build.confirm",
    "ROBOT_DECOMPOSE": "audit.robot.decompose",
    "ROBOT_RENAME": "audit.robot.rename",
    "SHOWCASE_EXPAND": "audit.showcase.expand",
    "SHOWCASE_LIKE": "audit.showcase.like",
    "ROBOT_SHARE": "audit.robot.share",
    "CHAT_POST": "audit.chat.post",
    "BOSS_ENCOUNTER": "audit.boss.encounter",
    "BOSS_ATTEMPT": "audit.boss.attempt",
    "BOSS_DEFEAT": "audit.boss.defeat",
    "CORE_DROP": "audit.core.drop",
    "PART_EVOLVE": "audit.part.evolve",
    "CORE_PROGRESS": "audit.core.progress",
    "CORE_GUARANTEE": "audit.core.guarantee",
    "PAYMENT_CHECKOUT_CREATE": "audit.payment.checkout.create",
    "PAYMENT_WEBHOOK_RECEIVED": "audit.payment.webhook.received",
    "PAYMENT_COMPLETED": "audit.payment.completed",
    "PAYMENT_GRANT_SUCCESS": "audit.payment.grant.success",
    "PAYMENT_GRANT_SKIP_DUPLICATE": "audit.payment.grant.skip_duplicate",
    "PAYMENT_GRANT_FAILED": "audit.payment.grant.failed",
    "TROPHY_GRANT_SUCCESS": "audit.trophy.grant.success",
    "TROPHY_GRANT_SKIP_DUPLICATE": "audit.trophy.grant.skip_duplicate",
    "TROPHY_GRANT_FAILED": "audit.trophy.grant.failed",
    "EXPLORE_BOOST_GRANT_SUCCESS": "audit.explore_boost.grant.success",
    "EXPLORE_BOOST_GRANT_SKIP_DUPLICATE": "audit.explore_boost.grant.skip_duplicate",
    "EXPLORE_BOOST_GRANT_FAILED": "audit.explore_boost.grant.failed",
    "SHARE_CLICK": "audit.share.click",
    "REFERRAL_ATTACH": "audit.referral.attach",
    "REFERRAL_QUALIFIED": "audit.referral.qualified",
    "FACTION_CHOOSE": "audit.faction.choose",
    "SYSTEM_MAINTENANCE_BLOCK": "audit.system.maintenance_block",
    "ADMIN_USER_BAN": "audit.admin.user.ban",
    "ADMIN_USER_UNBAN": "audit.admin.user.unban",
    "ADMIN_USER_PROTECT_LOGIN": "audit.admin.user.protect_login",
    "ADMIN_USER_UNPROTECT_LOGIN": "audit.admin.user.unprotect_login",
    "ADMIN_USER_RENAME": "audit.admin.user.rename",
    "ADMIN_USER_DELETE": "audit.admin.user.delete",
    "ADMIN_RELEASE_TOGGLE": "audit.admin.release.toggle",
    "LAB_SUBMISSION_CREATE": "audit.lab.submission.create",
    "LAB_SUBMISSION_APPROVE": "audit.lab.submission.approve",
    "LAB_SUBMISSION_REJECT": "audit.lab.submission.reject",
    "LAB_SUBMISSION_DISABLE": "audit.lab.submission.disable",
    "LAB_SUBMISSION_LIKE": "audit.lab.submission.like",
    "LAB_SUBMISSION_REPORT": "audit.lab.submission.report",
    "LAB_RACE_ENTRY": "audit.lab.race.entry",
    "LAB_RACE_START": "audit.lab.race.start",
    "LAB_RACE_FINISH": "audit.lab.race.finish",
    "LAB_RACE_RESULT": "audit.lab.race.result",
    "LAB_CASINO_DAILY_GRANT": "audit.lab.casino.daily_grant",
    "LAB_CASINO_BET_PLACE": "audit.lab.casino.bet.place",
    "LAB_CASINO_BET_RESOLVE": "audit.lab.casino.bet.resolve",
    "LAB_CASINO_RACE_START": "audit.lab.casino.race.start",
    "LAB_CASINO_RACE_FINISH": "audit.lab.casino.race.finish",
    "LAB_CASINO_PRIZE_CLAIM": "audit.lab.casino.prize.claim",
}
