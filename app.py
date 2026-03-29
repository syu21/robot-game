import os
import random
import re
import shutil
import sqlite3
import traceback
import time
import csv
import io
import json
import uuid
import math
from importlib import import_module
from collections import Counter
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, Response, abort, flash, g, has_request_context, jsonify, redirect, render_template, request, session, url_for
from PIL import Image
from balance_config import (
    COIN_REWARD_BY_TIER,
    DROP_TYPE_WEIGHTS_BY_TIER,
    ENEMY_SEED_STATS,
    FUSE_COST_BY_PLUS,
    PLUS_WEIGHTS_BY_TIER,
    RARITY_WEIGHTS_BY_TIER,
)
from werkzeug.security import check_password_hash, generate_password_hash
from constants import (
    APP_VERSION,
    AUDIT_EVENT_TYPES,
    DEFEAT_LOGS,
    ELEMENTS,
    ELEMENT_LABEL_MAP,
    ENCOUNTER_LOGS,
    FACTION_EMBLEMS,
    FACTION_ICONS,
    FACTION_LABELS,
    FUSE_SUCCESS_TABLE,
    MID_LOGS_COMMON,
    MID_LOGS_FACTION,
    RARITIES,
    SET_BONUS_TABLE,
    LEGAL_BRAND_NAME,
    LEGAL_DISCLOSURE_POLICY,
    LEGAL_OPERATOR_NAME,
    SUPPORT_EMAIL,
    VICTORY_LOGS,
)
from services.personality_logs import generate_exploration_log, get_idle_line, get_streak_lines, pick_personality
from services.audit import audit_log
from services.archetype import compute_archetype
from services.lab import LAB_RACE_COURSES, LAB_RACE_ENTRY_TARGET, fill_npc_entries, simulate_race
from services.lab_race_service import (
    LAB_CASINO_BET_AMOUNTS,
    LAB_CASINO_COIN_CAP,
    LAB_CASINO_CONDITIONS,
    LAB_CASINO_COURSE,
    LAB_CASINO_DAILY_GRANT,
    LAB_CASINO_ENTRY_TARGET,
    LAB_CASINO_ROLE_LABELS,
    LAB_CASINO_STARTING_COINS,
    LAB_CASINO_WATCH_BONUS,
    build_casino_entries,
    payout_amount as lab_casino_payout_amount,
    simulate_casino_race,
)
from services.lab_race_engine import (
    build_course as build_lab_race_course,
    create_race as build_lab_race_bundle,
    default_course_key as lab_default_course_key,
    load_course as load_lab_race_course,
    visible_course_defs as visible_lab_course_defs,
)
from services.simulate_balance import resolve_attack, simulate_battle
from services.stats import (
    compute_part_stats,
    compute_robot_stats,
    generate_noisy_weights,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "game.db")
stripe = None
_stripe_api_module = None
_stripe_api_import_error = None

app = Flask(__name__)
DEV_MODE = (
    os.getenv("APP_ENV", "development") == "development"
    or os.getenv("FLASK_ENV") == "development"
    or os.getenv("FLASK_DEBUG") == "1"
)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
app.config["SESSION_COOKIE_SAMESITE"] = (os.getenv("SESSION_COOKIE_SAMESITE") or "Lax").strip() or "Lax"
app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv("SESSION_COOKIE_SECURE", "0").strip().lower() in {"1", "true", "yes", "on"}
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
if DEV_MODE and "SESSION_COOKIE_SECURE" not in os.environ:
    app.config["SESSION_COOKIE_SECURE"] = False

CANVAS_SIZE = 128
ALLOWED_EXT = {"png"}
ASSET_ROOT = os.path.join(BASE_DIR, "static", "robot_assets")
COMPOSED_ROOT = os.path.join(BASE_DIR, "static", "robot_composed")
STATIC_ROOT = os.path.join(BASE_DIR, "static")
AVATAR_UPLOAD_ROOT = os.path.join(STATIC_ROOT, "uploads", "avatars")
LAB_UPLOAD_ROOT = os.path.join(STATIC_ROOT, "user_lab_uploads")
LAB_UPLOAD_ORIGINAL_ROOT = os.path.join(LAB_UPLOAD_ROOT, "originals")
LAB_UPLOAD_THUMB_ROOT = os.path.join(LAB_UPLOAD_ROOT, "thumbs")
LAB_SCENE_SPRITE_ROOT = os.path.join(STATIC_ROOT, "lab_scene_sprites")
ROBOT_ICON_ROOT = os.path.join(STATIC_ROOT, "robot_icons")
DEFAULT_ROOT = os.path.join(STATIC_ROOT, "defaults")
DEFAULT_AVATAR_REL = "defaults/avatar_default.png"
DEFAULT_BADGE_REL = "defaults/robot_badge_default.png"
AVATAR_OUTPUT_SIZE = 48
BADGE_OUTPUT_SIZE = 32
MAX_BADGE_INNER_SIZE = 28
MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_LAB_UPLOAD_BYTES = 1 * 1024 * 1024
REQUIRE_ALPHA = os.getenv("REQUIRE_ALPHA", "1") == "1"
HOME_OK_MODE = os.getenv("HOME_OK_MODE", "0") == "1"
HOME_DEBUG_COMMENT = os.getenv("HOME_DEBUG_COMMENT", "1") == "1"
EXPLORE_MAX_TURNS = 8
MAX_PART_DROPS_NORMAL = 1
MAX_PART_DROPS_CHAIN = 2
MAX_PART_PLUS = int(os.getenv("MAX_PART_PLUS", "5"))
EVOLUTION_CORE_KEY = "evolution_core"
EVOLUTION_CORE_DROP_RATE = 0.02
EVOLUTION_CORE_PROGRESS_PER_WIN = max(1, int(os.getenv("EVOLUTION_CORE_PROGRESS_PER_WIN", "1")))
EVOLUTION_CORE_PROGRESS_TARGET = max(1, int(os.getenv("EVOLUTION_CORE_PROGRESS_TARGET", "100")))
EVOLUTION_PATH = {"N": "R", "R": "SR", "SR": "UR"}
FACTION_KEYS = ("ignis", "ventra", "aurix")
FACTION_UNLOCK_REQUIREMENTS = {
    "explore": {"event_type": AUDIT_EVENT_TYPES["EXPLORE_END"], "required": 20},
    "build": {"event_type": AUDIT_EVENT_TYPES["BUILD_CONFIRM"], "required": 5},
    "fuse": {"event_type": AUDIT_EVENT_TYPES["FUSE"], "required": 3},
}
FACTION_WAR_POINTS = {
    "explore_win": 1,
    "boss_defeat": 10,
    "build_confirm": 2,
    "fuse": 1,
}
FACTION_DOCTRINES = {
    "ignis": {
        "title": "突破主義",
        "summary": "高出力試験とボス突破を重視する陣営。",
        "focus": "攻撃 / 撃破",
        "world_hint": "ボス討伐や突破研究が盛り上がる週に存在感が出やすい。",
    },
    "ventra": {
        "title": "速度適応",
        "summary": "機動戦術と速度適応を重視する陣営。",
        "focus": "素早さ / 命中",
        "world_hint": "最速・命中系の研究や横道周回と相性がいい。",
    },
    "aurix": {
        "title": "安定運用",
        "summary": "防衛運用と安定収集を重視する陣営。",
        "focus": "耐久 / 継続",
        "world_hint": "長期周回や積み上げで差を作るときに強い。",
    },
}
COMM_WORLD_ROOM_KEY = "world_public"
COMM_WORLD_MAX_CHARS = 60
COMM_WORLD_COOLDOWN_SECONDS = 30
COMM_ROOM_MAX_CHARS = 120
COMM_ROOM_COOLDOWN_SECONDS = 15
COMM_WORLD_TIMELINE_LIMIT = 50
COMM_ROOM_TIMELINE_LIMIT = 100
COMM_PERSONAL_LOG_LIMIT = 30
COMM_AUTO_REFRESH_SECONDS = 18
HOME_COMM_PREVIEW_LIMIT = 12
COMM_ROOM_DEFS = (
    {
        "key": "global_room",
        "title": "全体会議室",
        "summary": "攻略や発見、雑談をみんなで話せる部屋。",
        "tone": "世界全体の流れを話せる部屋",
    },
    {
        "key": "beginner_room",
        "title": "初心者相談室",
        "summary": "困ったことや育成の相談を気軽に聞ける部屋。",
        "tone": "最初の壁を越えるための部屋",
    },
    {
        "key": "feedback_room",
        "title": "フィードバック",
        "summary": "気づいたことや要望、小さな違和感も気軽に送れる部屋。",
        "tone": "改善案や感想を集める部屋",
    },
)
COMM_ROOM_DEF_MAP = {item["key"]: item for item in COMM_ROOM_DEFS}
EXPLORE_COOLDOWN_SECONDS = int(os.getenv("EXPLORE_COOLDOWN_SECONDS", "40"))
NEWBIE_BOOST_ENABLED = os.getenv("NEWBIE_BOOST_ENABLED", "1") == "1"
NEWBIE_BOOST_WINDOW_HOURS = int(os.getenv("NEWBIE_BOOST_WINDOW_HOURS", "72"))
NEWBIE_EXPLORE_CT_SECONDS = int(os.getenv("NEWBIE_EXPLORE_CT_SECONDS", "20"))
HOME_UNLOCK_RECENT_SECONDS = int(os.getenv("HOME_UNLOCK_RECENT_SECONDS", "86400"))
STAGE_MODIFIERS_ENABLED = os.getenv("STAGE_MODIFIERS_ENABLED", "1") == "1"
BATTLE_RITUAL_OVERLAY_ENABLED = os.getenv("BATTLE_RITUAL_OVERLAY_ENABLED", "1") == "1"
UI_EFFECTS_ENABLED = os.getenv("UI_EFFECTS_ENABLED", "1") == "1"
PUBLIC_GAME_URL = (os.getenv("PUBLIC_GAME_URL") or "").strip()
STRIPE_SECRET_KEY = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
STRIPE_PUBLISHABLE_KEY = (os.getenv("STRIPE_PUBLISHABLE_KEY") or "").strip()
STRIPE_WEBHOOK_SECRET = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()
STRIPE_PRICE_ID_SUPPORT_PACK = (os.getenv("STRIPE_PRICE_ID_SUPPORT_PACK") or "").strip()
STRIPE_PRICE_ID_EXPLORE_BOOST = (os.getenv("STRIPE_PRICE_ID_EXPLORE_BOOST") or "").strip()
PORTAL_ONLINE_WINDOW_MINUTES = int(os.getenv("PORTAL_ONLINE_WINDOW_MINUTES", "5"))
PORTAL_ONLINE_TIMEOUT_SECONDS = float(os.getenv("PORTAL_ONLINE_TIMEOUT_SECONDS", "5"))
LAST_SEEN_TOUCH_INTERVAL_SECONDS = int(os.getenv("LAST_SEEN_TOUCH_INTERVAL_SECONDS", "60"))
USER_PRESENCE_ACTIVE_WINDOW_MINUTES = max(
    1,
    int(os.getenv("USER_PRESENCE_ACTIVE_WINDOW_MINUTES", str(PORTAL_ONLINE_WINDOW_MINUTES))),
)
USER_PRESENCE_WARM_WINDOW_MINUTES = max(
    USER_PRESENCE_ACTIVE_WINDOW_MINUTES + 1,
    int(os.getenv("USER_PRESENCE_WARM_WINDOW_MINUTES", "60")),
)
COMM_ROOM_ACTIVITY_WINDOW_MINUTES = max(
    5,
    int(os.getenv("COMM_ROOM_ACTIVITY_WINDOW_MINUTES", "20")),
)
SUPPORT_PACK_PRODUCT_KEY = "support_pack_001"
SUPPORT_PACK_DECOR_KEY = "supporter_emblem_001"
EXPLORE_BOOST_PRODUCT_KEY = "explore_boost_14d"
EXPLORE_BOOST_DURATION_DAYS = 14
EXPLORE_BOOST_CT_SECONDS = 20
PAYMENT_STATUS_CREATED = "created"
PAYMENT_STATUS_COMPLETED = "completed"
PAYMENT_STATUS_GRANTED = "granted"
PAYMENT_STATUS_FAILED = "failed"
PAYMENT_STATUS_EXPIRED = "expired"
BUILD_ARCHETYPE_PRIORITY = ("BERSERK", "BURST", "STABLE", "NONE")
BUILD_ARCHETYPE_LABELS = {
    "BERSERK": "背水型",
    "BURST": "爆発型",
    "STABLE": "安定型",
    "NONE": "なし",
}
ROBOT_STYLE_DEFINITIONS = {
    "stable": {"label_jp": "安定", "description_jp": "防御・命中寄り（長期戦向き）"},
    "desperate": {"label_jp": "背水", "description_jp": "低耐久寄り（速攻・リスク）"},
    "burst": {"label_jp": "爆発", "description_jp": "攻撃・会心寄り（一撃型）"},
}
ROBOT_STYLE_LABELS = {k: v["label_jp"] for k, v in ROBOT_STYLE_DEFINITIONS.items()}
ROBOT_STYLE_TIE_BREAK = ("stable", "burst", "desperate")
ROBOT_STYLE_WEIGHTS = {
    "stable": {"def": 0.35, "hp": 0.25, "acc": 0.20, "spd": 0.10, "atk": 0.05, "inv_cri": 0.05},
    "burst": {"atk": 0.35, "cri": 0.35, "acc": 0.10, "spd": 0.10, "inv_def": 0.10},
    "desperate": {"atk": 0.30, "spd": 0.25, "cri": 0.15, "acc": 0.10, "inv_hp": 0.20},
}
AREA_GROWTH_TENDENCY_DEFS = {
    "layer_1": {
        "key": "durable",
        "label": "基礎整備",
        "short_label": "耐久・防御寄り",
        "home_line": "育成傾向: 耐久・防御寄り",
        "map_line": "耐久・防御寄りの基礎育成",
        "weight_bias": {"hp": 0.10, "def": 0.08, "acc": 0.02},
    },
    "layer_2": {
        "key": "control",
        "label": "制圧育成",
        "short_label": "命中・防御寄り",
        "home_line": "育成傾向: 命中・防御寄り",
        "map_line": "命中を伸ばして崩れにくくなる",
        "weight_bias": {"acc": 0.08, "def": 0.06, "hp": 0.03},
    },
    "layer_2_mist": {
        "key": "precision",
        "label": "狙撃育成",
        "short_label": "命中寄り",
        "home_line": "育成傾向: 命中寄り",
        "map_line": "命中の伸びで狙撃型が生まれやすい",
        "weight_bias": {"acc": 0.12, "spd": 0.03},
    },
    "layer_2_rush": {
        "key": "fastest",
        "label": "速攻育成",
        "short_label": "素早さ・会心寄り",
        "home_line": "育成傾向: 素早さ・会心寄り",
        "map_line": "速攻と会心で展開を押し切る",
        "weight_bias": {"spd": 0.12, "atk": 0.05, "cri": 0.06},
    },
    "layer_3": {
        "key": "burst",
        "label": "突破育成",
        "short_label": "攻撃・耐久寄り",
        "home_line": "育成傾向: 攻撃・耐久寄り",
        "map_line": "攻撃と耐久の両立で突破型が育つ",
        "weight_bias": {"atk": 0.08, "hp": 0.06, "def": 0.03},
    },
    "layer_4_forge": {
        "key": "fortress",
        "label": "要塞育成",
        "short_label": "耐久・防御寄り",
        "home_line": "育成傾向: 耐久・防御が大きく伸びる",
        "map_line": "長期戦向け。耐久と防御を明確に伸ばせる",
        "weight_bias": {"hp": 0.20, "def": 0.18, "atk": 0.08, "acc": 0.03, "spd": -0.10, "cri": -0.08},
    },
    "layer_4_haze": {
        "key": "precision_master",
        "label": "霧界育成",
        "short_label": "命中・安定寄り",
        "home_line": "育成傾向: 命中・安定寄り",
        "map_line": "命中と安定で高速機を捉える型が育つ",
        "weight_bias": {"hp": 0.04, "def": 0.08, "atk": -0.04, "acc": 0.22, "spd": 0.12, "cri": -0.04},
    },
    "layer_4_burst": {
        "key": "detonate",
        "label": "暴走育成",
        "short_label": "攻撃・会心寄り",
        "home_line": "育成傾向: 攻撃・会心が大きく伸びる",
        "map_line": "背水と爆発の王道。速攻で抜ける型が育つ",
        "weight_bias": {"hp": -0.10, "def": -0.10, "atk": 0.20, "acc": 0.06, "spd": 0.08, "cri": 0.18},
    },
    "layer_4_final": {
        "key": "judgement",
        "label": "審判試験",
        "short_label": "型理解試験",
        "home_line": "育成傾向: 最終試験",
        "map_line": "3ボス突破後に挑む、第4層の卒業試験",
        "weight_bias": {"hp": 0.08, "atk": 0.08, "def": 0.08, "acc": 0.08, "spd": 0.04, "cri": 0.04},
    },
    "layer_5_labyrinth": {
        "key": "labyrinth",
        "label": "観測育成",
        "short_label": "耐久・命中・安定寄り",
        "home_line": "育成傾向: 耐久・命中・安定寄り",
        "map_line": "事故を減らし、安定して勝ち切る型を仕上げる",
        "weight_bias": {"hp": 0.12, "def": 0.12, "acc": 0.12, "spd": 0.04, "atk": 0.02, "cri": -0.06},
    },
    "layer_5_pinnacle": {
        "key": "pinnacle",
        "label": "競覇育成",
        "short_label": "攻撃・会心・速攻寄り",
        "home_line": "育成傾向: 攻撃・会心・速攻寄り",
        "map_line": "背水と爆発を磨き、記録を取りにいく",
        "weight_bias": {"atk": 0.14, "cri": 0.14, "spd": 0.08, "acc": 0.02, "hp": -0.06, "def": -0.08},
    },
    "layer_5_final": {
        "key": "omega",
        "label": "完成試験",
        "short_label": "思想完成試験",
        "home_line": "育成傾向: 第5層最終試験",
        "map_line": "ニクスとイグニッションを越えた先にある総決算",
        "weight_bias": {"hp": 0.06, "atk": 0.06, "def": 0.06, "acc": 0.06, "spd": 0.04, "cri": 0.04},
    },
}
ENEMY_TENDENCY_TAGS = {
    "def": "硬い装甲",
    "atk": "脆いが危険",
    "cri": "脆いが危険",
    "spd": "高速個体",
    "acc": "照準が鋭い",
}
ENEMY_TRAIT_DEFS = {
    "heavy": {"label": "重装", "desc": "被ダメージ軽減"},
    "fast": {"label": "高速", "desc": "回避しやすい"},
    "berserk": {"label": "狂戦", "desc": "耐久半分以下で攻撃上昇"},
    "unstable": {"label": "不安定", "desc": "攻撃時に反動"},
}
DEFAULT_NORMAL_ENEMY_TRAITS = {
    "enemy12": "fast",
    "enemy23": "fast",
    "enemy9": "berserk",
    "enemy14": "heavy",
    "enemy10": "berserk",
    "enemy16": "heavy",
    "enemy17": "heavy",
    "enemy25": "unstable",
    "enemy29": "heavy",
}
STAT_UI_LABELS = {
    "hp": "耐久",
    "atk": "攻撃",
    "def": "防御",
    "spd": "素早さ",
    "acc": "命中",
    "cri": "会心",
    "power": "総合",
}
STAT_ABBR_TO_KEY = {
    "HP": "hp",
    "ATK": "atk",
    "DEF": "def",
    "SPD": "spd",
    "ACC": "acc",
    "CRI": "cri",
}
PART_ELEMENT_TITLES_JA = {
    "normal": "無印",
    "fire": "焔",
    "water": "蒼潮",
    "thunder": "蒼雷",
    "wind": "烈風",
    "ice": "氷刃",
    "steel": "鋼鉄",
    "machine": "機巧",
    "ore": "鉱晶",
}
PART_TYPE_TITLES_JA = {
    "head": "頭冠",
    "right_arm": "右腕",
    "left_arm": "左腕",
    "legs": "脚部",
}
PART_TYPE_FILTER_LABELS_JA = {
    "HEAD": "頭",
    "RIGHT_ARM": "右腕",
    "LEFT_ARM": "左腕",
    "LEGS": "脚",
}
PART_RARITY_SUFFIX_JA = {
    "N": "",
    "R": "改",
    "SR": "真",
    "SSR": "極",
    "UR": "神",
}
GUIDE_SECTIONS = (
    {
        "key": "build",
        "title": "🔥① ロボの育て方",
        "items": (
            {
                "term": "性格",
                "body": "ロボの育ち方の傾向を、ひとことで表した言葉です。どんな戦い方をしやすいかの目安になります。",
            },
            {
                "term": "安定",
                "body": "防御や命中が高く、長く戦いやすいタイプです。ミスが少なく、じっくり戦いたい人向けです。",
            },
            {
                "term": "背水",
                "body": "耐久は低いが素早く攻めるタイプです。短期決戦やギリギリの勝負が好きな人向けです。",
            },
            {
                "term": "爆発",
                "body": "攻撃力や会心が高く、一撃で流れを変えるタイプです。運や火力で突破したい人向けです。",
            },
            {
                "term": "型",
                "body": "ロボ全体の能力バランスです。",
            },
            {
                "term": "狙撃型",
                "body": "命中が高い型です。",
            },
            {
                "term": "疾風型",
                "body": "素早さが高い型です。",
            },
            {
                "term": "鉄壁型",
                "body": "防御が高い型です。",
            },
        ),
    },
    {
        "key": "growth",
        "title": "⚙️② ロボを強くする",
        "items": (
            {
                "term": "パーツ強化",
                "body": "素材を使ってパーツの +値 を上げます。まずはここから始まります。",
            },
            {
                "term": "進化合成",
                "body": "同じ N パーツを R パーツに進化できます。第2層のボスを倒すと解放されます。",
            },
            {
                "term": "進化コア",
                "body": "進化に必要な素材です。探索や勝利数の達成で手に入ります。",
            },
            {
                "term": "育成傾向",
                "body": "探索場所によって伸びやすい能力が少し変わります。自分の作りたいロボに合わせて周回先を選べます。",
            },
        ),
    },
    {
        "key": "world",
        "title": "🌍③ 世界で競う",
        "items": (
            {
                "term": "世界ログ",
                "body": "世界の大きな出来事や、他のロボ使いの声が流れる公開ログです。",
            },
            {
                "term": "ランキング",
                "body": "勝利数・探索数・耐久・爆発など、いろいろな強さで競えます。",
            },
            {
                "term": "ロボ展示",
                "body": "他のプレイヤーのロボを見ることができます。強いロボの育て方のヒントになります。",
            },
            {
                "term": "陣営戦",
                "body": "所属ごとの進行競争です。探索したりボスを倒すとスコアが増えます。",
            },
        ),
    },
    {
        "key": "pride",
        "title": "🎖④ 見た目と誇り",
        "items": (
            {
                "term": "DECOR",
                "body": "ロボの見た目を変えられる装飾です。ボスを倒した証として残ります。",
            },
            {
                "term": "WEEK適合",
                "body": "今週の環境と相性がいいロボにつく目印です。ついていると活躍しやすくなります。",
            },
        ),
    },
)


def _payment_catalog():
    return {
        SUPPORT_PACK_PRODUCT_KEY: {
            "product_key": SUPPORT_PACK_PRODUCT_KEY,
            "display_name": "ロボらぼ支援パック",
            "description": "開発応援ありがとうございます。戦力差はつきません。",
            "price_id": STRIPE_PRICE_ID_SUPPORT_PACK,
            "grant_type": "decor",
            "grant_key": SUPPORT_PACK_DECOR_KEY,
            "grant_name": "支援者トロフィー",
            "image_path": "decor/aurix_trophy.png",
            "return_endpoint": "support",
        },
        EXPLORE_BOOST_PRODUCT_KEY: {
            "product_key": EXPLORE_BOOST_PRODUCT_KEY,
            "display_name": "出撃ブースト",
            "description": "2週間、出撃待機時間を短縮します。戦力差はつきません。",
            "price_id": STRIPE_PRICE_ID_EXPLORE_BOOST,
            "grant_type": "explore_boost",
            "boost_days": EXPLORE_BOOST_DURATION_DAYS,
            "grant_name": "出撃CT短縮（40秒 → 20秒）",
            "image_path": "images/ui/robonavi.png",
            "return_endpoint": "shop",
        },
    }


def _payment_product(product_key):
    return _payment_catalog().get(str(product_key or "").strip())


def _support_payment_catalog():
    return _payment_catalog()


def _support_payment_product(product_key=SUPPORT_PACK_PRODUCT_KEY):
    return _payment_product(product_key)
PART_OFFSET_CACHE = {}
PART_OFFSET_CACHE_VERSION = 0
COMPOSE_REV = 0
MISSING_ASSET_WARNED_GLOBAL = set()
LAB_WORLD_EVENT_TYPES = {
    "LAB_RACE_WIN",
    "LAB_RACE_UPSET",
    "LAB_RACE_POPULAR_ENTRY",
}
LAB_SUBMISSION_SORT_DEFS = (
    {"key": "new", "label": "新着"},
    {"key": "popular", "label": "人気"},
    {"key": "talk", "label": "話題"},
    {"key": "pick", "label": "おすすめ"},
)
LAB_SUBMISSION_SORT_OPTIONS = tuple(item["key"] for item in LAB_SUBMISSION_SORT_DEFS)
LAB_REPORT_REASON_DEFS = (
    ("inappropriate", "不適切"),
    ("copyright", "著作権懸念"),
    ("spam", "スパム"),
    ("other", "その他"),
)
LAB_CASINO_PRIZE_SEEDS = (
    {
        "prize_key": "lab_title_hot_streak",
        "name": "称号: ヒートストリーク",
        "description": "実験室プロフィールに飾る想定のレース予想称号。",
        "cost_lab_coin": 500,
        "prize_type": "title",
        "grant_key": "lab_title_hot_streak",
    },
    {
        "prize_key": "lab_frame_checker",
        "name": "観戦フレーム: チェッカー",
        "description": "観戦気分を盛り上げるエネミーレース限定フレーム。",
        "cost_lab_coin": 1200,
        "prize_type": "frame",
        "grant_key": "lab_frame_checker",
    },
    {
        "prize_key": "lab_badge_jackpot",
        "name": "プロフィールバッジ: JACKPOT",
        "description": "実験室での大当たり記念バッジ。",
        "cost_lab_coin": 1800,
        "prize_type": "badge",
        "grant_key": "lab_badge_jackpot",
    },
    {
        "prize_key": "lab_skin_flash",
        "name": "観戦演出スキン: フラッシュライン",
        "description": "レース観戦の加速演出をイメージした景品。",
        "cost_lab_coin": 2600,
        "prize_type": "effect",
        "grant_key": "lab_skin_flash",
    },
)
STYLE_ACHIEVEMENT_DEFS = (
    {
        "key": "stable_no_damage_wins",
        "title": "安定の守り手",
        "label": "安定",
        "desc": "無被弾勝利",
        "target": 10,
    },
    {
        "key": "burst_crit_finisher_kills",
        "title": "爆発の処刑人",
        "label": "爆発",
        "desc": "会心トドメ",
        "target": 20,
    },
    {
        "key": "desperate_low_hp_wins",
        "title": "背水の生還者",
        "label": "背水",
        "desc": "耐久20%未満勝利",
        "target": 10,
    },
)
STYLE_ACHIEVEMENT_EVENT_TYPE = "audit.achievement.progress"
STYLE_ACHIEVEMENT_JSON_KEY_MAP = {
    "stable_no_damage_wins": ("stable", "hitless_wins"),
    "burst_crit_finisher_kills": ("burst", "crit_finishes"),
    "desperate_low_hp_wins": ("desperate", "low_hp_wins"),
}
HOME_BUILD_CHAT_PATTERN = re.compile(r"が新ロボ『.+』を完成！")
ROBOT_TITLE_DEFS = (
    {"key": "title_boot", "name_ja": "起動", "desc_ja": "初組み立てを完了した相棒", "sort_order": 10},
    {"key": "title_deployed", "name_ja": "実戦配備", "desc_ja": "勝利数10を達成", "sort_order": 20, "metric": "wins_total", "threshold": 10},
    {"key": "title_first_boss", "name_ja": "初撃破", "desc_ja": "ボス初撃破を達成", "sort_order": 30, "metric": "boss_defeats_total", "threshold": 1},
)
SHOWCASE_SORT_DEFS = (
    {"key": "new", "label": "新着"},
    {"key": "week", "label": "今週"},
    {"key": "boss", "label": "ボス"},
    {"key": "like", "label": "いいね"},
    {"key": "fastest", "label": "最速"},
    {"key": "durable", "label": "耐久"},
    {"key": "precision", "label": "命中"},
    {"key": "burst", "label": "爆発"},
)
SHOWCASE_SORT_OPTIONS = tuple(item["key"] for item in SHOWCASE_SORT_DEFS)
RANKING_METRIC_DEFS = (
    {
        "key": "wins",
        "tab_label": "勝利数",
        "title": "勝利数ランキング",
        "metric_label": "勝利数",
        "description": "歴代の勝利数を表示します。",
        "is_weekly": False,
        "row_kind": "user",
    },
    {
        "key": "explores",
        "tab_label": "探索数",
        "title": "探索数ランキング",
        "metric_label": "探索回数",
        "description": "累積の出撃回数を表示します。",
        "is_weekly": False,
        "row_kind": "user",
    },
    {
        "key": "weekly_explores",
        "tab_label": "今週探索",
        "title": "今週探索数ランキング",
        "metric_label": "今週探索",
        "description": "今週どれだけ出撃したかを表示します。",
        "is_weekly": True,
        "row_kind": "user",
    },
    {
        "key": "weekly_bosses",
        "tab_label": "今週ボス",
        "title": "今週ボス撃破ランキング",
        "metric_label": "今週ボス撃破",
        "description": "今週のボス討伐数を表示します。",
        "is_weekly": True,
        "row_kind": "user",
    },
    {
        "key": "fastest",
        "tab_label": "最速",
        "title": "最速ロボランキング",
        "metric_label": "素早さ",
        "description": "各プレイヤーの代表機から、最も速いロボを表示します。",
        "is_weekly": False,
        "row_kind": "robot",
    },
    {
        "key": "durable",
        "tab_label": "耐久",
        "title": "耐久ロボランキング",
        "metric_label": "耐久指数",
        "description": "耐久と防御が高い代表ロボを表示します。",
        "is_weekly": False,
        "row_kind": "robot",
    },
    {
        "key": "precision",
        "tab_label": "命中",
        "title": "命中ロボランキング",
        "metric_label": "命中",
        "description": "命中が高い代表ロボを表示します。",
        "is_weekly": False,
        "row_kind": "robot",
    },
    {
        "key": "burst",
        "tab_label": "爆発",
        "title": "爆発ロボランキング",
        "metric_label": "爆発指数",
        "description": "攻撃と会心が高い代表ロボを表示します。",
        "is_weekly": False,
        "row_kind": "robot",
    },
)
RANKING_METRIC_DEF_BY_KEY = {row["key"]: row for row in RANKING_METRIC_DEFS}
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
EXPLORE_AREAS = [
    {"key": "layer_1", "label": "第一層: 風化した整備通路", "layer": 1},
    {"key": "layer_2", "label": "第二層: 放電ノイズ帯", "layer": 2},
    {"key": "layer_2_mist", "label": "第二層横道: 霧の谷", "layer": 2},
    {"key": "layer_2_rush", "label": "第二層横道: 火花回廊", "layer": 2},
    {"key": "layer_3", "label": "第三層: 旧防衛区画", "layer": 3},
    {"key": "layer_4_forge", "label": "第四層: 機構深部フォージ", "layer": 4},
    {"key": "layer_4_haze", "label": "第四層: 戦術試験ヘイズ", "layer": 4},
    {"key": "layer_4_burst", "label": "第四層: 暴走試験バースト", "layer": 4},
    {"key": "layer_4_final", "label": "第四層最終試験: 審判域ゼロ", "layer": 4},
    {"key": "layer_5_labyrinth", "label": "第五層: 観測圏ラビリンス", "layer": 5},
    {"key": "layer_5_pinnacle", "label": "第五層: 競覇圏ピナクル", "layer": 5},
    {"key": "layer_5_final", "label": "第五層最終試験: 完成域オメガ", "layer": 5},
]
MAX_UNLOCKABLE_LAYER = 5
RELEASE_FLAG_DEFS = (
    {
        "key": "lab",
        "label": "実験室",
        "summary": "実験室トップ、エネミーレース、投稿、展示を一般公開します。",
    },
    {
        "key": "layer4",
        "label": "第4層",
        "summary": "第4層3エリアと第4層最終試験を一般公開します。",
    },
    {
        "key": "layer5",
        "label": "第5層",
        "summary": "第5層2エリアと第5層最終試験を一般公開します。",
    },
)
RELEASE_FLAG_DEF_BY_KEY = {item["key"]: item for item in RELEASE_FLAG_DEFS}
PUBLIC_RELEASED_BASE_LAYER = 3
MAIN_ADMIN_USERNAME = "admin（管理人）"
MAIN_ADMIN_USERNAME_ALIASES = ("admin", MAIN_ADMIN_USERNAME)
MAIN_ADMIN_FIRE_LOADOUT = {
    "head": "head_r_fire",
    "r_arm": "right_arm_r_fire",
    "l_arm": "left_arm_r_fire",
    "legs": "legs_r_fire",
}
EXPLORE_AREA_LAYER_BY_KEY = {a["key"]: int(a.get("layer") or 1) for a in EXPLORE_AREAS}
HOME_PRIMARY_AREA_BY_LAYER = {
    1: "layer_1",
    2: "layer_2",
    3: "layer_3",
    4: "layer_4_forge",
    5: "layer_5_labyrinth",
}
LAYER_BOSS_KEY_BY_LAYER = {
    1: "boss_aurix_guardian",
    2: "boss_ventra_sentinel",
    3: "boss_ignis_reaver",
}
LAYER4_SUBAREA_KEYS = ("layer_4_forge", "layer_4_haze", "layer_4_burst")
LAYER4_FINAL_AREA_KEY = "layer_4_final"
LAYER5_SUBAREA_KEYS = ("layer_5_labyrinth", "layer_5_pinnacle")
LAYER5_FINAL_AREA_KEY = "layer_5_final"
SPECIAL_EXPLORE_AREA_KEYS = {LAYER4_FINAL_AREA_KEY, LAYER5_FINAL_AREA_KEY}
NPC_BOSS_ALLOWED_AREAS = ("layer_2", "layer_3")
NPC_BOSS_PICK_RATE = float(os.getenv("NPC_BOSS_PICK_RATE", "0.25"))
NPC_BOSS_ALERT_ID_OFFSET = 1_000_000
NPC_BOSS_IMAGE_BY_FACTION = {
    "ignis": "enemies/boss/npc_boss_ignis.png",
    "ventra": "enemies/boss/npc_boss_ventra.png",
    "aurix": "enemies/boss/npc_boss_aurix.png",
}
NPC_BOSS_NAME_BY_FACTION = {
    "ignis": "IGNIS侵食機",
    "ventra": "VENTRA模倣機",
    "aurix": "AURIX残響機",
}
STAGE_MODIFIERS_BY_AREA = {
    "layer_1": {
        "tendency": "標準",
        "player_mult": {"atk": 1.00, "def": 1.00, "acc": 1.00},
        "enemy_mult": {"atk": 1.00, "def": 1.00, "acc": 1.00, "hp": 1.00},
    },
    "layer_2": {
        "tendency": "攻撃向き",
        "player_mult": {"atk": 1.08, "def": 0.96, "acc": 1.00},
        "enemy_mult": {"atk": 1.00, "def": 1.00, "acc": 1.00, "hp": 1.00},
    },
    "layer_2_mist": {
        "tendency": "命中向き",
        "player_mult": {"atk": 0.96, "def": 1.00, "acc": 1.08},
        "enemy_mult": {"atk": 1.00, "def": 1.00, "acc": 1.05, "spd": 1.10, "cri": 1.00, "hp": 1.00},
    },
    "layer_2_rush": {
        "tendency": "攻撃向き",
        "player_mult": {"atk": 1.08, "def": 0.96, "acc": 1.00},
        "enemy_mult": {"atk": 1.15, "def": 1.00, "acc": 1.00, "spd": 1.00, "cri": 1.05, "hp": 1.00},
    },
    "layer_3": {
        "tendency": "防御向き",
        "player_mult": {"atk": 0.96, "def": 1.08, "acc": 1.00},
        "enemy_mult": {"atk": 1.00, "def": 1.00, "acc": 1.00, "hp": 1.00},
    },
    "layer_4_forge": {
        "tendency": "重装向き",
        "player_mult": {"atk": 0.96, "def": 1.08, "acc": 1.00},
        "enemy_mult": {"atk": 1.02, "def": 1.12, "acc": 1.00, "hp": 1.14},
    },
    "layer_4_haze": {
        "tendency": "命中向き",
        "player_mult": {"atk": 0.98, "def": 1.02, "acc": 1.10},
        "enemy_mult": {"atk": 1.04, "def": 1.00, "acc": 1.10, "spd": 1.12, "cri": 1.00, "hp": 1.00},
    },
    "layer_4_burst": {
        "tendency": "爆発向き",
        "player_mult": {"atk": 1.10, "def": 0.94, "acc": 1.02},
        "enemy_mult": {"atk": 1.14, "def": 0.98, "acc": 1.00, "spd": 1.04, "cri": 1.10, "hp": 0.98},
    },
    "layer_4_final": {
        "tendency": "複合試験",
        "player_mult": {"atk": 1.00, "def": 1.00, "acc": 1.00},
        "enemy_mult": {"atk": 1.08, "def": 1.08, "acc": 1.08, "spd": 1.05, "cri": 1.05, "hp": 1.08},
    },
    "layer_5_labyrinth": {
        "tendency": "観測向き",
        "player_mult": {"atk": 1.00, "def": 1.08, "acc": 1.08},
        "enemy_mult": {"atk": 1.10, "def": 1.10, "acc": 1.08, "spd": 1.10, "cri": 1.02, "hp": 1.12},
    },
    "layer_5_pinnacle": {
        "tendency": "覇走向き",
        "player_mult": {"atk": 1.10, "def": 0.95, "acc": 1.02},
        "enemy_mult": {"atk": 1.18, "def": 1.00, "acc": 1.04, "spd": 1.08, "cri": 1.14, "hp": 1.02},
    },
    "layer_5_final": {
        "tendency": "完成試験",
        "player_mult": {"atk": 1.02, "def": 1.02, "acc": 1.02},
        "enemy_mult": {"atk": 1.14, "def": 1.12, "acc": 1.10, "spd": 1.08, "cri": 1.08, "hp": 1.14},
    },
}
EXPLORE_AREA_TIERS = {
    "layer_1": (1,),
    "layer_2": (1, 2),
    "layer_2_mist": (1, 2),
    "layer_2_rush": (1, 2),
    "layer_3": (2, 3),
    "layer_4_forge": (4,),
    "layer_4_haze": (4,),
    "layer_4_burst": (4,),
    "layer_4_final": (4,),
    "layer_5_labyrinth": (5,),
    "layer_5_pinnacle": (5,),
    "layer_5_final": (5,),
}
EXPLORE_AREA_TIER_WEIGHTS = {
    "layer_1": {1: 1.0},
    "layer_2": {1: 0.25, 2: 0.75},
    "layer_2_mist": {2: 1.0},
    "layer_2_rush": {2: 0.85, 3: 0.15},
    "layer_3": {2: 0.20, 3: 0.80},
    "layer_4_forge": {4: 1.0},
    "layer_4_haze": {4: 1.0},
    "layer_4_burst": {4: 1.0},
    "layer_4_final": {4: 1.0},
    "layer_5_labyrinth": {5: 1.0},
    "layer_5_pinnacle": {5: 1.0},
    "layer_5_final": {5: 1.0},
}
EXPLORE_AREA_ENEMY_KEYS = {
    "layer_4_forge": ("fort_ironbulk", "fort_platehound", "fort_bastion_eye"),
    "layer_4_haze": ("haze_mirage_mite", "haze_fog_lancer", "haze_glint_drone"),
    "layer_4_burst": ("burst_coreling", "burst_shockfang", "burst_ruptgear"),
    "layer_5_labyrinth": ("lab_guardian_veil", "lab_bulwark_node", "lab_trace_hound", "lab_fault_keeper"),
    "layer_5_pinnacle": ("pin_flare_beast", "pin_rupture_eye", "pin_scorch_fang", "pin_crash_gear"),
}
EXPLORE_DROP_PROFILE_BY_AREA = {
    # Tier1: 基本系中心。例外は少量だけ混ぜる。
    "layer_1": {
        "rarity_weights": {"N": 1.0},
        "element_weights": {
            "NORMAL": 2.2,
            "MACHINE": 2.0,
            "STEEL": 1.8,
            "THUNDER": 1.2,
            "WIND": 1.1,
            "FIRE": 0.9,
            "ICE": 0.9,
            "ORE": 0.8,
            "WATER": 0.8,
        },
        "exception_bias": 0.10,
    },
    # Tier2標準: 属性/役割の試行を増やす。
    "layer_2": {
        "rarity_weights": {"N": 1.0},
        "element_weights": {
            "MACHINE": 1.4,
            "STEEL": 1.3,
            "THUNDER": 1.3,
            "WIND": 1.3,
            "FIRE": 1.2,
            "ICE": 1.1,
            "WATER": 1.1,
            "ORE": 1.1,
            "NORMAL": 1.0,
        },
        "exception_bias": 0.18,
    },
    # 横道mist: 命中/素早さ寄り構成を少し引きやすく。
    "layer_2_mist": {
        "rarity_weights": {"N": 1.0},
        "element_weights": {
            "WIND": 1.7,
            "WATER": 1.5,
            "THUNDER": 1.4,
            "ICE": 1.3,
            "MACHINE": 1.0,
            "STEEL": 0.9,
            "ORE": 0.9,
            "FIRE": 0.8,
            "NORMAL": 0.8,
        },
        "exception_bias": 0.20,
    },
    # 横道rush: 火力/会心寄り構成を少し引きやすく。
    "layer_2_rush": {
        "rarity_weights": {"N": 1.0},
        "element_weights": {
            "FIRE": 1.8,
            "THUNDER": 1.5,
            "ORE": 1.2,
            "STEEL": 1.1,
            "MACHINE": 1.0,
            "WIND": 0.9,
            "ICE": 0.9,
            "WATER": 0.8,
            "NORMAL": 0.8,
        },
        "exception_bias": 0.22,
    },
    # Tier3: rarityは既存tier重みを使う。進化コア解禁でR化導線を主役化。
    "layer_3": {
        "rarity_weights": None,
        "element_weights": {
            "FIRE": 1.3,
            "STEEL": 1.2,
            "ORE": 1.2,
            "THUNDER": 1.1,
            "ICE": 1.1,
            "WIND": 1.0,
            "WATER": 1.0,
            "MACHINE": 1.0,
            "NORMAL": 0.9,
        },
        "exception_bias": 0.25,
    },
    "layer_4_forge": {
        "rarity_weights": None,
        "element_weights": {
            "STEEL": 1.8,
            "ORE": 1.6,
            "MACHINE": 1.2,
            "ICE": 1.0,
            "THUNDER": 0.9,
            "FIRE": 0.8,
            "WIND": 0.8,
            "WATER": 0.8,
            "NORMAL": 0.7,
        },
        "exception_bias": 0.28,
    },
    "layer_4_haze": {
        "rarity_weights": None,
        "element_weights": {
            "WIND": 1.8,
            "MACHINE": 1.5,
            "WATER": 1.4,
            "THUNDER": 1.3,
            "ICE": 1.2,
            "STEEL": 0.9,
            "ORE": 0.9,
            "FIRE": 0.8,
            "NORMAL": 0.8,
        },
        "exception_bias": 0.26,
    },
    "layer_4_burst": {
        "rarity_weights": None,
        "element_weights": {
            "FIRE": 1.9,
            "THUNDER": 1.6,
            "ORE": 1.2,
            "MACHINE": 1.1,
            "STEEL": 1.0,
            "WIND": 0.9,
            "ICE": 0.9,
            "WATER": 0.8,
            "NORMAL": 0.8,
        },
        "exception_bias": 0.30,
    },
    "layer_4_final": {
        "rarity_weights": None,
        "element_weights": {
            "MACHINE": 1.6,
            "STEEL": 1.3,
            "ORE": 1.2,
            "FIRE": 1.1,
            "WIND": 1.1,
            "THUNDER": 1.1,
            "ICE": 1.0,
            "WATER": 1.0,
            "NORMAL": 0.9,
        },
        "exception_bias": 0.32,
    },
    "layer_5_labyrinth": {
        "rarity_weights": None,
        "element_weights": {
            "MACHINE": 1.7,
            "STEEL": 1.5,
            "WIND": 1.5,
            "WATER": 1.2,
            "ICE": 1.2,
            "THUNDER": 1.1,
            "ORE": 1.0,
            "FIRE": 0.8,
            "NORMAL": 0.8,
        },
        "exception_bias": 0.34,
    },
    "layer_5_pinnacle": {
        "rarity_weights": None,
        "element_weights": {
            "FIRE": 1.9,
            "THUNDER": 1.6,
            "ORE": 1.3,
            "MACHINE": 1.2,
            "STEEL": 1.0,
            "WIND": 0.9,
            "ICE": 0.8,
            "WATER": 0.8,
            "NORMAL": 0.8,
        },
        "exception_bias": 0.36,
    },
    "layer_5_final": {
        "rarity_weights": None,
        "element_weights": {
            "MACHINE": 1.7,
            "STEEL": 1.4,
            "FIRE": 1.2,
            "WIND": 1.2,
            "THUNDER": 1.2,
            "ORE": 1.1,
            "ICE": 1.0,
            "WATER": 1.0,
            "NORMAL": 0.9,
        },
        "exception_bias": 0.38,
    },
}
EVOLUTION_CORE_DROP_RATE_BY_AREA = {
    "layer_1": 0.0,
    "layer_2": 0.0,
    "layer_2_mist": 0.0,
    "layer_2_rush": 0.0,
    "layer_3": float(os.getenv("EVOLUTION_CORE_DROP_RATE_LAYER3", "0.012")),
    "layer_4_forge": float(os.getenv("EVOLUTION_CORE_DROP_RATE_LAYER4", "0.018")),
    "layer_4_haze": float(os.getenv("EVOLUTION_CORE_DROP_RATE_LAYER4", "0.018")),
    "layer_4_burst": float(os.getenv("EVOLUTION_CORE_DROP_RATE_LAYER4", "0.018")),
    "layer_4_final": 0.0,
    "layer_5_labyrinth": float(os.getenv("EVOLUTION_CORE_DROP_RATE_LAYER5", "0.024")),
    "layer_5_pinnacle": float(os.getenv("EVOLUTION_CORE_DROP_RATE_LAYER5", "0.024")),
    "layer_5_final": 0.0,
}
EXPLORE_AREA_UNLOCK_WINS = {
    "layer_1": 0,
    "layer_2": 5,
    "layer_2_mist": 8,
    "layer_2_rush": 10,
    "layer_3": 15,
}
L1_BOSS_MIN_EXPLORE = 40
L1_BOSS_MIN_WINS = 25
L1_BOSS_PITY_EXPLORE = 80
L1_BOSS_PITY_WINS = 50
L1_BOSS_PREMONITION_RATE = 0.12
L1_BOSS_PREMONITION_LINES = [
    "奥から重い振動が響く…",
    "警告音のようなノイズが混じる…",
]
AREA_BOSS_KEYS = (
    "layer_1",
    "layer_2",
    "layer_3",
    "layer_4_forge",
    "layer_4_haze",
    "layer_4_burst",
    "layer_4_final",
    "layer_5_labyrinth",
    "layer_5_pinnacle",
    "layer_5_final",
)
AREA_BOSS_ALERT_AREAS = (
    "layer_1",
    "layer_2",
    "layer_2_mist",
    "layer_2_rush",
    "layer_3",
    "layer_4_forge",
    "layer_4_haze",
    "layer_4_burst",
    "layer_4_final",
    "layer_5_labyrinth",
    "layer_5_pinnacle",
    "layer_5_final",
)
AREA_BOSS_SPAWN_RATES = {
    "layer_1": 0.005,
    "layer_2": 0.005,
    "layer_2_mist": 0.003,
    "layer_2_rush": 0.005,
    "layer_3": 0.005,
    "layer_4_forge": 0.005,
    "layer_4_haze": 0.005,
    "layer_4_burst": 0.005,
    "layer_4_final": 1.0,
    "layer_5_labyrinth": 0.005,
    "layer_5_pinnacle": 0.005,
    "layer_5_final": 1.0,
}
AREA_BOSS_PITY_MISSES = {
    # UIには出さず、第1〜3層のみ内部でソフト天井を使う。
    # 第4層以降は現行のレア感を維持する。
    "layer_1": 90,
    "layer_2": 120,
    "layer_3": 140,
    "layer_4_forge": 1_000_000,
    "layer_4_haze": 1_000_000,
    "layer_4_burst": 1_000_000,
    "layer_4_final": 1,
    "layer_5_labyrinth": 1_000_000,
    "layer_5_pinnacle": 1_000_000,
    "layer_5_final": 1,
}
AREA_BOSS_SOFT_PITY_STARTS = {
    "layer_1": 45,
    "layer_2": 70,
    "layer_3": 85,
}
AREA_BOSS_SOFT_PITY_MAX_RATES = {
    "layer_1": 0.035,
    "layer_2": 0.040,
    "layer_3": 0.045,
}
AREA_BOSS_ALERT_ATTEMPTS = int(os.getenv("AREA_BOSS_ALERT_ATTEMPTS", "3"))
AREA_BOSS_ALERT_MINUTES = int(os.getenv("AREA_BOSS_ALERT_MINUTES", "45"))
AREA_BOSS_LABELS = {
    "layer_1": "第一層",
    "layer_2": "第二層",
    "layer_2_mist": "第二層横道: 霧の谷",
    "layer_2_rush": "第二層横道: 火花回廊",
    "layer_3": "第三層",
    "layer_4": "第四層",
    "layer_4_forge": "第四層: 機構深部フォージ",
    "layer_4_haze": "第四層: 戦術試験ヘイズ",
    "layer_4_burst": "第四層: 暴走試験バースト",
    "layer_4_final": "第四層最終試験",
    "layer_5": "第五層",
    "layer_5_labyrinth": "第五層: 観測圏ラビリンス",
    "layer_5_pinnacle": "第五層: 競覇圏ピナクル",
    "layer_5_final": "第五層最終試験",
}
LAYER3_UNLOCK_LAYER2_SORTIES_REQUIRED = int(os.getenv("LAYER3_UNLOCK_LAYER2_SORTIES_REQUIRED", "40"))
LAYER2_FAMILY_AREA_KEYS = ("layer_2", "layer_2_mist", "layer_2_rush")
MINI_BOSS_AREA_KEYS = ("layer_2_mist", "layer_2_rush", "layer_3")
MINI_BOSS_SPAWN_RATE = float(os.getenv("MINI_BOSS_SPAWN_RATE", "0.10"))
MINI_BOSS_HP_MULT = float(os.getenv("MINI_BOSS_HP_MULT", "1.50"))
MINI_BOSS_ATK_MULT = float(os.getenv("MINI_BOSS_ATK_MULT", "1.20"))
LAYER_UNLOCK_ICON_BY_LAYER = {
    1: "⚙",
    2: "⚡",
    3: "🔥",
    4: "🧪",
    5: "👑",
}
AREA_BOSS_DECOR_REWARD_KEYS = {
    "layer_1": ["boss_emblem_aurix"],
    "layer_2": ["boss_emblem_ventra"],
    "layer_3": ["boss_emblem_ignis"],
    "layer_4_forge": ["fortress_badge_001"],
    "layer_4_haze": ["mist_scope_001"],
    "layer_4_burst": ["burst_reactor_001"],
    "layer_4_final": ["judge_halo_001"],
    "layer_5_labyrinth": ["nyx_array_crest_001"],
    "layer_5_pinnacle": ["ignition_crown_001"],
    "layer_5_final": ["omega_frame_halo_001"],
}
AREA_BOSS_TYPE_BY_KEY = {
    "boss_ignis_reaver": "TANK",
    "boss_ventra_sentinel": "EVADE",
    "boss_aurix_guardian": "GLASS_CANNON",
    "boss_4_forge_elguard": "TANK",
    "boss_4_haze_mirage": "EVADE",
    "boss_4_burst_volterio": "GLASS_CANNON",
    "boss_4_final_ark_zero": "TACTICAL",
    "boss_5_labyrinth_nyx_array": "EVADE",
    "boss_5_pinnacle_ignition_king": "GLASS_CANNON",
    "boss_5_final_omega_frame": "TACTICAL",
}
AREA_BOSS_TYPE_PROFILES = {
    "TANK": {
        "label_ja": "硬い",
        "recommend_build": "爆発型",
        "icon": "🛡",
        "mult": {"hp": 1.25, "def": 1.25, "atk": 0.95, "acc": 1.00},
    },
    "EVADE": {
        "label_ja": "回避",
        "recommend_build": "安定型",
        "icon": "💨",
        "mult": {"hp": 1.05, "def": 1.00, "atk": 1.00, "acc": 1.25},
    },
    "GLASS_CANNON": {
        "label_ja": "高火力",
        "recommend_build": "背水型",
        "icon": "🔥",
        "mult": {"hp": 0.95, "def": 0.95, "atk": 1.25, "acc": 1.00},
    },
    "TACTICAL": {
        "label_ja": "複合",
        "recommend_build": "バランス型",
        "icon": "🧠",
        "mult": {"hp": 1.10, "def": 1.08, "atk": 1.08, "acc": 1.08},
    },
}
BOSS_TYPE_RECOMMENDED_BUILD = {
    "TANK": {"build": "BURST", "label_ja": "爆発型", "text": "おすすめ：爆発型（上振れで突破）"},
    "EVADE": {"build": "STABLE", "label_ja": "安定型", "text": "おすすめ：安定型（当てる）"},
    "GLASS_CANNON": {"build": "BERSERK", "label_ja": "背水型", "text": "おすすめ：背水型（削られて火力UP）"},
    "TACTICAL": {"build": "STABLE", "label_ja": "バランス型", "text": "おすすめ：バランス型（型理解で突破）"},
}
DECOR_PLACEHOLDER_REL = "assets/placeholder_enemy.png"
BOSS_DECOR_WARNING_EMITTED = False
EXPLORE_AREA_MAP_INFO = {
    "layer_1": {
        "desc": [
            "旧整備通路。最も安定した探索ルート。",
            "推奨: 基本ステ確認と初期ドロップ回収。",
            "注意: 低tier中心で稼ぎは控えめ。",
        ],
        "recommended_archetype": "自由",
    },
    "layer_2": {
        "desc": [
            "放電ノイズ帯。tier1/2が混在する中間層。",
            "推奨: 命中と耐久をバランスよく確保。",
            "注意: 連続被弾でペースを崩しやすい。",
        ],
        "recommended_archetype": "sniper",
    },
    "layer_2_mist": {
        "desc": [
            "霧の谷。命中差で体感難易度が変動する横道。",
            "推奨: ACC重視の編成で命中を安定化。",
            "注意: 高ACC敵の引きで長期化しやすい。",
        ],
        "recommended_archetype": "sniper",
    },
    "layer_2_rush": {
        "desc": [
            "短期決戦になりやすいルート。",
            "クリティカルで展開が動く。",
            "攻めの機体が向く。",
        ],
        "recommended_archetype": "swift",
    },
    "layer_3": {
        "desc": [
            "旧防衛区画。高tier混在の終盤ルート。",
            "推奨: 耐久と火力の両立で短期決着を狙う。",
            "注意: タイムアウト負けの管理が重要。",
        ],
        "recommended_archetype": "fortress",
    },
    "layer_4_forge": {
        "desc": [
            "重装機が多い。長く戦える機体向き。",
            "推奨: 耐久・防御寄りの型で押し切る。",
            "注意: 短期火力だけでは抜けきりにくい。",
        ],
        "recommended_archetype": "fortress",
    },
    "layer_4_haze": {
        "desc": [
            "霧機が多い。命中と安定が重要。",
            "推奨: ACC重視の安定構成で崩れを防ぐ。",
            "注意: MISSが続くと一気にテンポを失う。",
        ],
        "recommended_archetype": "sniper",
    },
    "layer_4_burst": {
        "desc": [
            "暴走機が多い。速攻と爆発力が活きる。",
            "推奨: 背水・爆発寄りで短期決着を狙う。",
            "注意: もたつくと事故が連鎖しやすい。",
        ],
        "recommended_archetype": "swift",
    },
    "layer_4_final": {
        "desc": [
            "3領域の試験を越えた機体だけが挑める審判域。",
            "推奨: 単一特化よりも、型理解のある構成。",
            "注意: 3ボス撃破後にのみ挑戦可能。",
        ],
        "recommended_archetype": "自由",
    },
    "layer_5_labyrinth": {
        "desc": [
            "観測と防衛が混ざる深部。事故らない機体が強い。",
            "推奨: 耐久・命中・バランス型で安定勝利を狙う。",
            "注意: MISSと長期戦の両方を咎められる。",
        ],
        "recommended_archetype": "sniper",
    },
    "layer_5_pinnacle": {
        "desc": [
            "記録を奪い合う競覇圏。速攻と爆発力が評価される。",
            "推奨: 背水・爆発・速攻寄りで最速突破を狙う。",
            "注意: 上振れは強いが、崩れると一気に脆い。",
        ],
        "recommended_archetype": "swift",
    },
    "layer_5_final": {
        "desc": [
            "観測と競覇を越えた先の完成域。",
            "推奨: 耐久も火力も命中も捨て切らない思想完成型。",
            "注意: ニクスとイグニッション撃破後にのみ挑戦可能。",
        ],
        "recommended_archetype": "自由",
    },
}
ENEMY_IMPORT_MAX_BYTES = 1_000_000
PERSONALITY_LABELS = {
    "silent": "寡黙",
    "cheerful": "陽気",
    "analyst": "分析型",
    "charger": "突撃型",
    "showoff": "目立ちたがり",
    "veteran": "熟練",
    "supportive": "支援型",
    "cold": "冷徹",
    "legend": "伝説級",
    "clumsy": "不器用",
}
WORLD_MODE_LEGACY_MAP = {
    "storm": "暴走",
    "surge": "活性",
    "calm": "安定",
}
WORLD_MODES = {
    "暴走": {"enemy_spawn_bonus": 0.35, "drop_bonus": 0.12},
    "活性": {"enemy_spawn_bonus": 0.25, "drop_bonus": 0.18},
    "安定": {"enemy_spawn_bonus": 0.10, "drop_bonus": 0.00},
    "静穏": {"enemy_spawn_bonus": 0.12, "drop_bonus": 0.08},
}
RESEARCH_UNLOCK_ORDER = ("HEAD", "RIGHT_ARM", "LEFT_ARM", "LEGS")
JST = timezone(timedelta(hours=9))
RESEARCH_PART_TYPE_LABELS_JA = {
    "HEAD": "HEADパーツ",
    "RIGHT_ARM": "右腕パーツ",
    "LEFT_ARM": "左腕パーツ",
    "LEGS": "脚部パーツ",
}


def now_str():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def count_online_users(db, window_minutes=PORTAL_ONLINE_WINDOW_MINUTES, now_ts=None):
    now = _now_ts() if now_ts is None else int(now_ts)
    window_sec = max(60, int(window_minutes) * 60)
    cutoff = int(now - window_sec)
    row = db.execute(
        """
        SELECT COUNT(*) AS c
        FROM users
        WHERE COALESCE(last_seen_at, 0) >= ?
        """,
        (cutoff,),
    ).fetchone()
    return int((row["c"] if row else 0) or 0)


def count_active_users(db, window_minutes=PORTAL_ONLINE_WINDOW_MINUTES, now_ts=None):
    """Compatibility helper: active users within recent window."""
    return count_online_users(db=db, window_minutes=window_minutes, now_ts=now_ts)


def _user_presence_snapshot(last_seen_at, *, now_ts=None):
    now = _now_ts() if now_ts is None else int(now_ts)
    seen_ts = int(last_seen_at or 0)
    active_window_seconds = max(60, int(USER_PRESENCE_ACTIVE_WINDOW_MINUTES) * 60)
    warm_window_seconds = max(
        active_window_seconds + 60,
        int(USER_PRESENCE_WARM_WINDOW_MINUTES) * 60,
    )
    if seen_ts > 0:
        age_seconds = max(0, int(now) - int(seen_ts))
        if age_seconds <= active_window_seconds:
            label = f"最近{int(USER_PRESENCE_ACTIVE_WINDOW_MINUTES)}分で活動中"
            return {
                "state": "active",
                "label": label,
                "title": f"{label}のロボ使い",
            }
        if age_seconds <= warm_window_seconds:
            return {
                "state": "warm",
                "label": "少し前まで動いていた",
                "title": "少し前まで基地で動いていたロボ使い",
            }
    return {
        "state": "idle",
        "label": "探索待機中",
        "title": "いまは静かに待機中のロボ使い",
    }


def _active_users_summary_line(active_count, *, window_minutes=USER_PRESENCE_ACTIVE_WINDOW_MINUTES):
    return f"最近{int(window_minutes)}分で{int(active_count)}人が活動中"


def _room_activity_summary_line(participant_count, *, window_minutes=COMM_ROOM_ACTIVITY_WINDOW_MINUTES):
    return f"最近{int(window_minutes)}分で{int(participant_count)}人が発言"


def _chat_recent_participant_count(db, room_keys=None, *, window_minutes=COMM_ROOM_ACTIVITY_WINDOW_MINUTES, now_ts=None):
    now_value = _now_ts() if now_ts is None else int(now_ts)
    cutoff_text = time.strftime(
        "%Y-%m-%d %H:%M:%S",
        time.localtime(int(now_value) - max(60, int(window_minutes) * 60)),
    )
    normalized_keys = []
    for raw_key in (room_keys or (COMM_WORLD_ROOM_KEY,)):
        key = _chat_normalize_room_key(raw_key) or COMM_WORLD_ROOM_KEY
        if key not in normalized_keys:
            normalized_keys.append(key)
    placeholders = ", ".join("?" for _ in normalized_keys)
    row = db.execute(
        f"""
        SELECT COUNT(DISTINCT user_id) AS c
        FROM chat_messages
        WHERE COALESCE(room_key, ?) IN ({placeholders})
          AND deleted_at IS NULL
          AND user_id IS NOT NULL
          AND UPPER(COALESCE(username, '')) != 'SYSTEM'
          AND created_at >= ?
        """,
        (COMM_WORLD_ROOM_KEY, *normalized_keys, cutoff_text),
    ).fetchone()
    return int((row["c"] if row else 0) or 0)


def _chat_room_recent_participant_count(db, room_key, *, window_minutes=COMM_ROOM_ACTIVITY_WINDOW_MINUTES, now_ts=None):
    return _chat_recent_participant_count(
        db,
        [room_key],
        window_minutes=window_minutes,
        now_ts=now_ts,
    )


def _portal_online_endpoint():
    endpoint = (os.getenv("POCHI_PORTAL_ENDPOINT") or "").strip()
    if not endpoint:
        return ""
    normalized = endpoint.rstrip("/")
    if normalized.endswith("/api/portal/online-count"):
        return normalized
    return f"{normalized}/api/portal/online-count"


def _portal_online_config():
    game_key = (os.getenv("POCHI_PORTAL_GAME_KEY") or "").strip()
    api_key = (os.getenv("POCHI_PORTAL_API_KEY") or "").strip()
    endpoint = _portal_online_endpoint()
    if not game_key or not api_key or not endpoint:
        return {"ok": False, "reason": "missing_config"}
    return {"ok": True, "game_key": game_key, "api_key": api_key, "endpoint": endpoint}


def _portal_online_send_value(online_count, endpoint, game_key, api_key):
    query = urlencode(
        {
            "game_key": game_key,
            "api_key": api_key,
            "online_count": int(online_count),
        }
    )
    url = f"{endpoint}/?{query}"
    req = Request(url, method="GET")
    with urlopen(req, timeout=float(PORTAL_ONLINE_TIMEOUT_SECONDS)) as resp:
        status = int(getattr(resp, "status", 0) or resp.getcode() or 0)
    if status < 200 or status >= 300:
        return {"ok": False, "reason": "http_error", "status": status, "url": url, "online_count": int(online_count)}
    return {"ok": True, "status": status, "url": url, "online_count": int(online_count)}


def _enqueue_portal_online_retry(db, online_count, window_minutes, reason, now_ts=None, response_status=None):
    now = _now_ts() if now_ts is None else int(now_ts)
    cur = db.execute(
        """
        INSERT INTO portal_online_delivery_queue
        (online_count, window_minutes, status, attempt_count, created_at, last_error, response_status)
        VALUES (?, ?, 'pending', 0, ?, ?, ?)
        """,
        (
            int(online_count),
            max(1, int(window_minutes or PORTAL_ONLINE_WINDOW_MINUTES)),
            now,
            (str(reason or "")[:240] or "unknown"),
            (int(response_status) if response_status is not None else None),
        ),
    )
    db.commit()
    queue_id = int(cur.lastrowid or 0)
    app.logger.warning(
        "portal.online_count_queued queue_id=%s online_count=%s reason=%s status=%s",
        queue_id,
        int(online_count),
        str(reason or "unknown"),
        response_status if response_status is not None else "-",
    )
    return queue_id


def flush_portal_online_retry_queue(db=None, limit=12, now_ts=None):
    config = _portal_online_config()
    if not config["ok"]:
        app.logger.warning("portal.online_queue_flush_skip missing_config")
        return {"ok": False, "reason": "missing_config", "processed": 0, "sent": 0, "failed": 0}
    if db is None:
        db = get_db()
    rows = db.execute(
        """
        SELECT id, online_count, window_minutes, attempt_count
        FROM portal_online_delivery_queue
        WHERE status = 'pending'
        ORDER BY created_at ASC, id ASC
        LIMIT ?
        """,
        (max(1, int(limit or 1)),),
    ).fetchall()
    if not rows:
        return {"ok": True, "processed": 0, "sent": 0, "failed": 0}
    now = _now_ts() if now_ts is None else int(now_ts)
    sent = 0
    failed = 0
    for row in rows:
        queue_id = int(row["id"])
        try:
            result = _portal_online_send_value(
                online_count=int(row["online_count"] or 0),
                endpoint=config["endpoint"],
                game_key=config["game_key"],
                api_key=config["api_key"],
            )
        except Exception:
            failed += 1
            db.execute(
                """
                UPDATE portal_online_delivery_queue
                SET attempt_count = attempt_count + 1,
                    last_attempt_at = ?,
                    last_error = ?,
                    response_status = NULL
                WHERE id = ?
                """,
                (now, "exception", queue_id),
            )
            db.commit()
            app.logger.exception("portal.online_queue_flush_failed queue_id=%s", queue_id)
            break
        if result["ok"]:
            sent += 1
            db.execute(
                """
                UPDATE portal_online_delivery_queue
                SET status = 'sent',
                    attempt_count = attempt_count + 1,
                    last_attempt_at = ?,
                    delivered_at = ?,
                    last_error = NULL,
                    response_status = ?
                WHERE id = ?
                """,
                (now, now, int(result["status"]), queue_id),
            )
            db.commit()
            app.logger.info(
                "portal.online_queue_flush_sent queue_id=%s online_count=%s status=%s",
                queue_id,
                int(row["online_count"] or 0),
                int(result["status"]),
            )
            continue
        failed += 1
        db.execute(
            """
            UPDATE portal_online_delivery_queue
            SET attempt_count = attempt_count + 1,
                last_attempt_at = ?,
                last_error = ?,
                response_status = ?
            WHERE id = ?
            """,
            (now, str(result.get("reason") or "http_error")[:240], int(result.get("status") or 0) or None, queue_id),
        )
        db.commit()
        app.logger.warning(
            "portal.online_queue_flush_non_2xx queue_id=%s status=%s online_count=%s",
            queue_id,
            result.get("status"),
            int(row["online_count"] or 0),
        )
        break
    return {"ok": failed == 0, "processed": sent + failed, "sent": sent, "failed": failed}


def send_portal_online_count(db=None, now_ts=None, window_minutes=PORTAL_ONLINE_WINDOW_MINUTES, flush_limit=12):
    config = _portal_online_config()
    if not config["ok"]:
        app.logger.warning("portal.online_count_skip missing_config")
        return {"ok": False, "reason": "missing_config"}
    flush_result = {"ok": True, "processed": 0, "sent": 0, "failed": 0}
    if db is None:
        db = get_db()
    try:
        flush_result = flush_portal_online_retry_queue(db=db, limit=flush_limit, now_ts=now_ts)
    except Exception:
        app.logger.exception("portal.online_queue_flush_wrapper_failed")
        flush_result = {"ok": False, "reason": "exception", "processed": 0, "sent": 0, "failed": 1}
    try:
        online_count = count_online_users(db, window_minutes=window_minutes, now_ts=now_ts)
        result = _portal_online_send_value(
            online_count=online_count,
            endpoint=config["endpoint"],
            game_key=config["game_key"],
            api_key=config["api_key"],
        )
        if not result["ok"]:
            queue_id = _enqueue_portal_online_retry(
                db,
                online_count=online_count,
                window_minutes=window_minutes,
                reason=result.get("reason") or "http_error",
                now_ts=now_ts,
                response_status=result.get("status"),
            )
            app.logger.warning("portal.online_count_send_non_2xx status=%s queue_id=%s", result.get("status"), queue_id)
            return {
                "ok": False,
                "reason": result.get("reason") or "http_error",
                "status": result.get("status"),
                "online_count": int(online_count),
                "queued": True,
                "queue_id": queue_id,
                "flush_result": flush_result,
            }
        return {
            "ok": True,
            "status": int(result["status"]),
            "online_count": int(online_count),
            "queued": False,
            "flush_result": flush_result,
        }
    except Exception:
        online_count = count_online_users(db, window_minutes=window_minutes, now_ts=now_ts)
        queue_id = _enqueue_portal_online_retry(
            db,
            online_count=online_count,
            window_minutes=window_minutes,
            reason="exception",
            now_ts=now_ts,
        )
        app.logger.exception("portal.online_count_send_failed")
        return {
            "ok": False,
            "reason": "exception",
            "online_count": int(online_count),
            "queued": True,
            "queue_id": queue_id,
            "flush_result": flush_result,
        }
    finally:
        pass


def create_db_backup(now_dt=None):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = (now_dt or datetime.now(JST)).strftime("%Y%m%d-%H%M%S")
    backup_name = f"game-{stamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(backup_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    stat = os.stat(backup_path)
    return {
        "name": backup_name,
        "path": backup_path,
        "size": int(stat.st_size),
        "updated_at": datetime.fromtimestamp(int(stat.st_mtime), JST).strftime("%Y-%m-%d %H:%M:%S"),
    }


def list_db_backups():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    files = []
    for name in sorted(os.listdir(BACKUP_DIR), reverse=True):
        path = os.path.join(BACKUP_DIR, name)
        if not os.path.isfile(path):
            continue
        stat = os.stat(path)
        files.append(
            {
                "name": name,
                "path": path,
                "size": int(stat.st_size),
                "updated_at": datetime.fromtimestamp(int(stat.st_mtime), JST).strftime("%Y-%m-%d %H:%M:%S"),
                "mtime": int(stat.st_mtime),
            }
        )
    return files


def prune_db_backups(keep_latest=7):
    keep_latest = max(1, int(keep_latest or 1))
    files = list_db_backups()
    pruned = []
    for item in files[keep_latest:]:
        try:
            os.remove(item["path"])
            pruned.append(item)
        except FileNotFoundError:
            continue
    return pruned


def _is_maintenance_mode():
    return os.getenv("MAINTENANCE_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}


def _jst_day_key_to_bounds(day_key):
    day_dt = datetime.strptime(day_key, "%Y-%m-%d").replace(tzinfo=JST)
    start_ts = int(day_dt.timestamp())
    end_ts = int((day_dt + timedelta(days=1)).timestamp())
    return start_ts, end_ts


def _collect_daily_metrics(db, day_key):
    start_ts, end_ts = _jst_day_key_to_bounds(day_key)
    dau_count = db.execute(
        """
        SELECT COUNT(DISTINCT user_id) AS c
        FROM world_events_log
        WHERE user_id IS NOT NULL
          AND created_at >= ? AND created_at < ?
        """,
        (start_ts, end_ts),
    ).fetchone()["c"]
    new_users = db.execute(
        "SELECT COUNT(*) AS c FROM users WHERE created_at >= ? AND created_at < ?",
        (start_ts, end_ts),
    ).fetchone()["c"]
    explore_count = db.execute(
        "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ? AND created_at >= ? AND created_at < ?",
        (AUDIT_EVENT_TYPES["EXPLORE_END"], start_ts, end_ts),
    ).fetchone()["c"]
    boss_encounters = db.execute(
        "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ? AND created_at >= ? AND created_at < ?",
        (AUDIT_EVENT_TYPES["BOSS_ENCOUNTER"], start_ts, end_ts),
    ).fetchone()["c"]
    boss_defeats = db.execute(
        "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ? AND created_at >= ? AND created_at < ?",
        (AUDIT_EVENT_TYPES["BOSS_DEFEAT"], start_ts, end_ts),
    ).fetchone()["c"]
    fuse_count = db.execute(
        "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ? AND created_at >= ? AND created_at < ?",
        (AUDIT_EVENT_TYPES["FUSE"], start_ts, end_ts),
    ).fetchone()["c"]
    row = {
        "day_key": day_key,
        "dau_count": int(dau_count or 0),
        "new_users": int(new_users or 0),
        "explore_count": int(explore_count or 0),
        "boss_encounters": int(boss_encounters or 0),
        "boss_defeats": int(boss_defeats or 0),
        "fuse_count": int(fuse_count or 0),
    }
    db.execute(
        """
        INSERT INTO daily_metrics
        (day_key, dau_count, new_users, explore_count, boss_encounters, boss_defeats, fuse_count)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(day_key) DO UPDATE SET
            dau_count = excluded.dau_count,
            new_users = excluded.new_users,
            explore_count = excluded.explore_count,
            boss_encounters = excluded.boss_encounters,
            boss_defeats = excluded.boss_defeats,
            fuse_count = excluded.fuse_count
        """,
        (
            row["day_key"],
            row["dau_count"],
            row["new_users"],
            row["explore_count"],
            row["boss_encounters"],
            row["boss_defeats"],
            row["fuse_count"],
        ),
    )
    return row


def _collect_recent_daily_metrics(db, days=7):
    rows = []
    today = datetime.now(JST).date()
    for i in range(max(1, int(days))):
        day_key = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        rows.append(_collect_daily_metrics(db, day_key))
    rows.sort(key=lambda x: x["day_key"], reverse=True)
    return rows


def _roll_evolution_core_drop(rng=None, drop_rate=None):
    """Single gateway for evolution-core drop RNG.
    Keep current behavior (flat probability), and allow pity extension later.
    """
    rng = rng or random
    rate = float(EVOLUTION_CORE_DROP_RATE if drop_rate is None else drop_rate)
    rate = _clamp(rate, 0.0, 1.0)
    return bool(rng.random() < rate)


def _evolution_core_drop_rate_for_area(area_key):
    key = str(area_key or "").strip()
    if key in EVOLUTION_CORE_DROP_RATE_BY_AREA:
        return float(EVOLUTION_CORE_DROP_RATE_BY_AREA[key])
    return float(EVOLUTION_CORE_DROP_RATE)


def _pick_drop_part_master(db, *, rarity=None, area_key=None):
    profile = EXPLORE_DROP_PROFILE_BY_AREA.get(str(area_key or "").strip(), {})
    rarity_weights = profile.get("rarity_weights") or {}
    effective_rarity = (rarity or "").upper().strip()
    if not effective_rarity and rarity_weights:
        keys = list(rarity_weights.keys())
        weights = [float(rarity_weights[k]) for k in keys]
        effective_rarity = str(random.choices(keys, weights=weights, k=1)[0])
    if not effective_rarity:
        effective_rarity = "N"

    if effective_rarity == "R":
        rows = db.execute(
            """
            SELECT * FROM robot_parts
            WHERE is_active = 1
              AND UPPER(COALESCE(rarity, '')) = 'R'
              AND is_unlocked = 1
            """,
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT * FROM robot_parts
            WHERE is_active = 1
              AND UPPER(COALESCE(rarity, '')) = UPPER(?)
            """,
            (effective_rarity,),
        ).fetchall()
    if not rows:
        return None

    element_weights = profile.get("element_weights") or {}
    bias = float(profile.get("exception_bias") or 0.0)
    weighted_rows = []
    weighted_values = []
    for row in rows:
        element_key = str(row["element"] or "NORMAL").strip().upper()
        base = float(element_weights.get(element_key, 1.0))
        w = max(0.01, base + bias)
        weighted_rows.append(row)
        weighted_values.append(w)
    return random.choices(weighted_rows, weights=weighted_values, k=1)[0]


def _core_drop_observability(db, sample_size=500, days=14, user_day_limit=200):
    sample_size = max(50, min(5000, int(sample_size or 500)))
    days = max(1, min(90, int(days or 14)))
    user_day_limit = max(20, min(1000, int(user_day_limit or 200)))

    explore_rows = db.execute(
        """
        SELECT id, payload_json
        FROM world_events_log
        WHERE event_type = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (AUDIT_EVENT_TYPES["EXPLORE_END"], sample_size),
    ).fetchall()

    explores = len(explore_rows)
    wins = 0
    battles_total = 0
    core_total = 0
    core_hit_explores = 0
    for row in explore_rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        rewards = payload.get("rewards") if isinstance(payload.get("rewards"), dict) else {}
        if bool(result.get("win")):
            wins += 1
        battles_total += int(result.get("battle_count") or 1)
        cores = int(rewards.get("cores") or 0)
        if cores > 0:
            core_hit_explores += 1
            core_total += cores

    avg_battles_per_explore = (float(battles_total) / float(explores)) if explores else 0.0
    core_per_explore = (float(core_total) / float(explores)) if explores else 0.0
    core_hit_rate_explore = (float(core_hit_explores) / float(explores)) if explores else 0.0
    core_per_battle_trial = (float(core_total) / float(battles_total)) if battles_total else 0.0
    expected_hit_per_explore = (
        1.0 - math.pow(1.0 - float(EVOLUTION_CORE_DROP_RATE), avg_battles_per_explore)
        if avg_battles_per_explore > 0
        else 0.0
    )

    since_ts = int(time.time()) - days * 86400
    user_day_rows = db.execute(
        """
        SELECT
            date(datetime(wel.created_at, 'unixepoch', 'localtime')) AS day_key,
            wel.user_id,
            u.username,
            SUM(COALESCE(CAST(json_extract(wel.payload_json, '$.quantity') AS INTEGER), 0)) AS core_qty
        FROM world_events_log wel
        LEFT JOIN users u ON u.id = wel.user_id
        WHERE wel.event_type = ?
          AND wel.user_id IS NOT NULL
          AND wel.created_at >= ?
        GROUP BY day_key, wel.user_id, u.username
        ORDER BY day_key DESC, core_qty DESC, wel.user_id ASC
        LIMIT ?
        """,
        (AUDIT_EVENT_TYPES["CORE_DROP"], since_ts, user_day_limit),
    ).fetchall()
    user_day = []
    for row in user_day_rows:
        user_day.append(
            {
                "day_key": row["day_key"],
                "user_id": int(row["user_id"]),
                "username": row["username"] or f"user#{int(row['user_id'])}",
                "core_qty": int(row["core_qty"] or 0),
            }
        )

    return {
        "configured_drop_rate": float(EVOLUTION_CORE_DROP_RATE),
        "sample_size": int(sample_size),
        "explores": int(explores),
        "wins": int(wins),
        "battles_total": int(battles_total),
        "core_total": int(core_total),
        "core_hit_explores": int(core_hit_explores),
        "avg_battles_per_explore": float(avg_battles_per_explore),
        "core_per_explore": float(core_per_explore),
        "core_hit_rate_explore": float(core_hit_rate_explore),
        "core_per_battle_trial": float(core_per_battle_trial),
        "expected_hit_per_explore": float(expected_hit_per_explore),
        "days": int(days),
        "user_day": user_day,
    }


def _world_week_key(ts=None):
    dt = datetime.now(JST) if ts is None else datetime.fromtimestamp(ts, JST)
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _world_week_bounds(week_key):
    year_s, week_s = week_key.split("-W")
    year = int(year_s)
    week = int(week_s)
    start = datetime.fromisocalendar(year, week, 1).replace(tzinfo=JST)
    end = start + timedelta(days=7)
    return start, end


def _jst_day_bounds(ts=None):
    dt = datetime.now(JST) if ts is None else datetime.fromtimestamp(ts, JST)
    start = datetime(dt.year, dt.month, dt.day, tzinfo=JST)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def _world_event_log(db, event_type, payload):
    db.execute(
        """
        INSERT INTO world_events_log (created_at, event_type, payload_json)
        VALUES (?, ?, ?)
        """,
        (int(time.time()), event_type, json.dumps(payload, ensure_ascii=False)),
    )


def _now_ts():
    if has_request_context():
        cached = getattr(g, "_now_ts", None)
        if cached is None:
            cached = int(time.time())
            g._now_ts = cached
        return int(cached)
    return int(time.time())


def _research_part_type_for_stage(stage):
    idx = int(stage) - 1
    if 0 <= idx < len(RESEARCH_UNLOCK_ORDER):
        return RESEARCH_UNLOCK_ORDER[idx]
    return None


def _ensure_world_research_rows(db):
    now_ts = int(time.time())
    for element, _ in ELEMENTS:
        db.execute(
            """
            INSERT INTO world_research_progress (element, progress, unlocked_stage, updated_at)
            VALUES (?, 0, 0, ?)
            ON CONFLICT(element) DO NOTHING
            """,
            (element, now_ts),
        )


def _research_winning_element(db, week_key):
    order = {element: idx for idx, (element, _) in enumerate(ELEMENTS)}
    scores = []
    for element, _ in ELEMENTS:
        kills = _world_counter_get(db, week_key, f"kills_{element}")
        builds = _world_counter_get(db, week_key, f"builds_{element}")
        scores.append((element, int(kills) + int(builds), int(kills), int(builds)))
    best = max(scores, key=lambda x: (x[1], x[2], x[3], -order.get(x[0], 999)))
    if best[1] <= 0:
        return None
    return best[0]


def _advance_world_research(db, current_week_key):
    advance_seen = db.execute(
        """
        SELECT 1
        FROM world_events_log
        WHERE event_type = 'RESEARCH_ADVANCE'
          AND payload_json LIKE ?
        LIMIT 1
        """,
        (f'%"week_key": "{current_week_key}"%',),
    ).fetchone()
    if advance_seen:
        return {
            "week_key": current_week_key,
            "skipped": True,
            "reason": "already_advanced",
        }

    _ensure_world_research_rows(db)
    prev_start = _world_week_bounds(current_week_key)[0] - timedelta(days=7)
    prev_week_key = _world_week_key(prev_start.timestamp())
    winner = _research_winning_element(db, prev_week_key)
    if not winner:
        result = {
            "week_key": current_week_key,
            "source_week_key": prev_week_key,
            "winner_element": None,
            "progress_added": 0,
            "unlocked": False,
            "skipped": False,
        }
        _world_event_log(db, "RESEARCH_ADVANCE", result)
        return result

    now_ts = int(time.time())
    row = db.execute(
        "SELECT progress, unlocked_stage FROM world_research_progress WHERE element = ?",
        (winner,),
    ).fetchone()
    prev_progress = int(row["progress"] or 0) if row else 0
    prev_stage = int(row["unlocked_stage"] or 0) if row else 0
    new_progress = prev_progress + 50
    new_stage = prev_stage
    unlocked_part_type = None
    unlocked_count = 0

    if new_progress >= 100 and prev_stage < len(RESEARCH_UNLOCK_ORDER):
        new_stage = prev_stage + 1
        new_progress = 0
        unlocked_part_type = _research_part_type_for_stage(new_stage)
        if unlocked_part_type:
            unlocked_count = db.execute(
                """
                UPDATE robot_parts
                SET is_unlocked = 1
                WHERE UPPER(COALESCE(rarity, '')) = 'R'
                  AND UPPER(COALESCE(element, '')) = ?
                  AND part_type = ?
                  AND is_unlocked = 0
                """,
                (winner, unlocked_part_type),
            ).rowcount
        unlock_payload = {
            "week_key": current_week_key,
            "source_week_key": prev_week_key,
            "element": winner,
            "stage": new_stage,
            "part_type": unlocked_part_type,
            "updated_parts": int(unlocked_count),
        }
        _world_event_log(db, "RESEARCH_UNLOCK", unlock_payload)
        db.execute(
            """
            INSERT INTO world_research_unlocks (created_at, week_key, element, stage, part_type, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                now_ts,
                current_week_key,
                winner,
                new_stage,
                unlocked_part_type or "",
                json.dumps(unlock_payload, ensure_ascii=False),
            ),
        )

    db.execute(
        """
        INSERT INTO world_research_progress (element, progress, unlocked_stage, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(element) DO UPDATE SET
            progress = excluded.progress,
            unlocked_stage = excluded.unlocked_stage,
            updated_at = excluded.updated_at
        """,
        (winner, int(new_progress), int(new_stage), now_ts),
    )
    result = {
        "week_key": current_week_key,
        "winner_element": winner,
        "progress_added": 50,
        "source_week_key": prev_week_key,
        "stage_before": prev_stage,
        "stage_after": new_stage,
        "progress_before": prev_progress,
        "progress_after": new_progress,
        "unlocked": bool(unlocked_part_type),
        "part_type": unlocked_part_type,
    }
    _world_event_log(db, "RESEARCH_ADVANCE", result)
    return result


def _load_user_area_streaks(db, user_id):
    rows = db.execute(
        """
        SELECT area_key, win_streak
        FROM user_area_streaks
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchall()
    return {r["area_key"]: int(r["win_streak"] or 0) for r in rows}


def _update_user_area_streak(db, user_id, area_key, won, updated_at):
    row = db.execute(
        "SELECT win_streak FROM user_area_streaks WHERE user_id = ? AND area_key = ?",
        (user_id, area_key),
    ).fetchone()
    prev_streak = int(row["win_streak"] or 0) if row else 0
    new_streak = (prev_streak + 1) if bool(won) else 0
    db.execute(
        """
        INSERT INTO user_area_streaks (user_id, area_key, win_streak, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, area_key) DO UPDATE
        SET win_streak = excluded.win_streak,
            updated_at = excluded.updated_at
        """,
        (user_id, area_key, int(new_streak), int(updated_at)),
    )
    db.execute(
        """
        UPDATE user_area_streaks
        SET win_streak = 0,
            updated_at = ?
        WHERE user_id = ? AND area_key != ? AND win_streak != 0
        """,
        (int(updated_at), user_id, area_key),
    )
    return int(new_streak)


def _area_layer(area_key):
    return int(EXPLORE_AREA_LAYER_BY_KEY.get(area_key, 1))


def _stat_mult_applied(base_value, multiplier):
    base = int(base_value or 0)
    mult = float(multiplier or 1.0)
    return max(1, int(round(base * mult)))


def _pct_text(multiplier):
    delta = int(round((float(multiplier or 1.0) - 1.0) * 100))
    if delta == 0:
        return None
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta}%"


def _stage_modifier_for_area(area_key, is_admin=False):
    if not STAGE_MODIFIERS_ENABLED or bool(is_admin):
        return None
    raw = STAGE_MODIFIERS_BY_AREA.get(area_key)
    if not raw:
        return None
    player_raw = raw.get("player_mult") or {}
    enemy_raw = raw.get("enemy_mult") or {}
    player_mult = {
        "atk": float(player_raw.get("atk", 1.0)),
        "def": float(player_raw.get("def", 1.0)),
        "acc": float(player_raw.get("acc", 1.0)),
    }
    enemy_mult = {
        "atk": float(enemy_raw.get("atk", 1.0)),
        "def": float(enemy_raw.get("def", 1.0)),
        "acc": float(enemy_raw.get("acc", 1.0)),
        "spd": float(enemy_raw.get("spd", 1.0)),
        "cri": float(enemy_raw.get("cri", 1.0)),
        "hp": float(enemy_raw.get("hp", 1.0)),
    }
    return {
        "area_key": area_key,
        "tendency": (raw.get("tendency") or "標準"),
        "player_mult": player_mult,
        "enemy_mult": enemy_mult,
    }


def _stage_modifier_summary_line(stage_modifier):
    if not stage_modifier:
        return None
    pm = stage_modifier["player_mult"]
    parts = []
    atk = _pct_text(pm.get("atk", 1.0))
    deff = _pct_text(pm.get("def", 1.0))
    acc = _pct_text(pm.get("acc", 1.0))
    if atk:
        parts.append(f"{_stat_label('atk')}{atk}")
    if deff:
        parts.append(f"{_stat_label('def')}{deff}")
    if acc:
        parts.append(f"{_stat_label('acc')}{acc}")
    if not parts:
        return f"傾向：{stage_modifier['tendency']}（補正なし）"
    return f"傾向：{stage_modifier['tendency']}（{'/'.join(parts)}）"


def _user_max_unlocked_layer(user_row):
    if not user_row:
        return 1
    current = int(user_row["max_unlocked_layer"] or 1) if "max_unlocked_layer" in user_row.keys() else 1
    if "layer2_unlocked" in user_row.keys() and int(user_row["layer2_unlocked"] or 0) == 1:
        current = max(current, 2)
    return max(1, min(MAX_UNLOCKABLE_LAYER, current))


def _seed_release_flags(db):
    for item in RELEASE_FLAG_DEFS:
        db.execute(
            """
            INSERT INTO release_flags (key, is_public, updated_at)
            VALUES (?, 0, 0)
            ON CONFLICT(key) DO NOTHING
            """,
            (item["key"],),
        )


def _release_flag_is_public(db, feature_key):
    key = str(feature_key or "").strip().lower()
    if not key:
        return True
    row = db.execute("SELECT is_public FROM release_flags WHERE key = ? LIMIT 1", (key,)).fetchone()
    return bool(row and int(row["is_public"] or 0) == 1)


def _release_gate_testing_bypass_enabled():
    return bool(app.config.get("TESTING")) and bool(app.config.get("BYPASS_RELEASE_GATES_IN_TESTS", True))


def _viewer_is_admin_for_release(db, *, user_row=None, user_id=None, is_admin=None):
    if is_admin is not None:
        return bool(is_admin)
    if user_row is not None and "is_admin" in user_row.keys():
        return bool(int(user_row["is_admin"] or 0) == 1)
    uid = int(user_id or 0)
    if uid <= 0 or not db:
        return False
    row = db.execute("SELECT is_admin FROM users WHERE id = ?", (uid,)).fetchone()
    return bool(row and int(row["is_admin"] or 0) == 1)


def _release_open_for_viewer(db, feature_key, *, user_row=None, user_id=None, is_admin=None):
    key = str(feature_key or "").strip().lower()
    if not key:
        return True
    if _release_gate_testing_bypass_enabled():
        return True
    if _viewer_is_admin_for_release(db, user_row=user_row, user_id=user_id, is_admin=is_admin):
        return True
    return _release_flag_is_public(db, key)


def _release_feature_for_area(area_key):
    key = str(area_key or "").strip()
    if key in {*LAYER4_SUBAREA_KEYS, LAYER4_FINAL_AREA_KEY}:
        return "layer4"
    if key in {*LAYER5_SUBAREA_KEYS, LAYER5_FINAL_AREA_KEY}:
        return "layer5"
    return None


def _area_visible_for_viewer(db, area_key, *, user_row=None, user_id=None, is_admin=None):
    return _release_open_for_viewer(
        db,
        _release_feature_for_area(area_key),
        user_row=user_row,
        user_id=user_id,
        is_admin=is_admin,
    )


def _release_layer_cap_for_viewer(db, *, user_row=None, user_id=None, is_admin=None):
    if _release_gate_testing_bypass_enabled():
        return MAX_UNLOCKABLE_LAYER
    if _viewer_is_admin_for_release(db, user_row=user_row, user_id=user_id, is_admin=is_admin):
        return MAX_UNLOCKABLE_LAYER
    if _release_flag_is_public(db, "layer5"):
        return MAX_UNLOCKABLE_LAYER
    if _release_flag_is_public(db, "layer4"):
        return 4
    return PUBLIC_RELEASED_BASE_LAYER


def _visible_user_max_unlocked_layer(user_row, db=None):
    actual = _user_max_unlocked_layer(user_row)
    if not db or not user_row:
        return actual
    return max(1, min(actual, _release_layer_cap_for_viewer(db, user_row=user_row)))


def _event_release_feature(event_type, payload):
    text = str(event_type or "").strip()
    if text.startswith("audit.lab.") or text in {"LAB_RACE_WIN", "LAB_RACE_UPSET", "LAB_RACE_POPULAR_ENTRY"}:
        return "lab"
    unlocked_layer = int((payload or {}).get("unlocked_layer") or 0)
    if unlocked_layer >= 5:
        return "layer5"
    if unlocked_layer >= 4:
        return "layer4"
    area_key = str((payload or {}).get("area_key") or "").strip()
    return _release_feature_for_area(area_key)


def _event_visible_for_viewer(db, event_type, payload, *, user_row=None, user_id=None, is_admin=None):
    return _release_open_for_viewer(
        db,
        _event_release_feature(event_type, payload),
        user_row=user_row,
        user_id=user_id,
        is_admin=is_admin,
    )


def _release_gate_redirect(db, feature_key, *, user_row=None, user_id=None, is_admin=None, next_endpoint="home"):
    if _release_open_for_viewer(db, feature_key, user_row=user_row, user_id=user_id, is_admin=is_admin):
        return None
    flash("まだ公開準備中です。公開まで少し待ってください。", "notice")
    return redirect(url_for(next_endpoint))


def _release_flag_rows(db):
    _seed_release_flags(db)
    rows = {
        row["key"]: row
        for row in db.execute("SELECT key, is_public, updated_at FROM release_flags").fetchall()
    }
    items = []
    for item in RELEASE_FLAG_DEFS:
        row = rows.get(item["key"])
        items.append(
            {
                "key": item["key"],
                "label": item["label"],
                "summary": item["summary"],
                "is_public": bool(row and int(row["is_public"] or 0) == 1),
                "updated_at": int(row["updated_at"] or 0) if row else 0,
                "updated_text": (_format_jst_ts(row["updated_at"]) if row and int(row["updated_at"] or 0) > 0 else "未変更"),
            }
        )
    return items


def _layer4_trial_bosses_cleared(db, user_id):
    uid = int(user_id or 0)
    if uid <= 0:
        return False
    return all(_has_fixed_boss_defeat_in_area(db, uid, area_key) for area_key in LAYER4_SUBAREA_KEYS)


def _layer5_trial_bosses_cleared(db, user_id):
    uid = int(user_id or 0)
    if uid <= 0:
        return False
    return all(_has_fixed_boss_defeat_in_area(db, uid, area_key) for area_key in LAYER5_SUBAREA_KEYS)


def _special_area_unlock_reason(area_key):
    key = str(area_key or "").strip()
    if key == LAYER4_FINAL_AREA_KEY:
        return "第4層3ボス撃破で解放"
    if key == LAYER5_FINAL_AREA_KEY:
        return "第5層2ボス撃破で解放"
    layer = _area_layer(key)
    if layer <= 1:
        return "未解放"
    return f"第{layer - 1}層ボス撃破で解放"


def _is_special_area_unlocked(db, user_id, area_key):
    if db and _is_main_admin_user_id(db, user_id):
        return True
    key = str(area_key or "").strip()
    if key == LAYER4_FINAL_AREA_KEY:
        return _layer4_trial_bosses_cleared(db, user_id)
    if key == LAYER5_FINAL_AREA_KEY:
        return _layer5_trial_bosses_cleared(db, user_id)
    return True


def _is_area_unlocked(user_row, area_key, db=None):
    if db and not _area_visible_for_viewer(db, area_key, user_row=user_row):
        return False
    visible_max = _visible_user_max_unlocked_layer(user_row, db=db)
    if _area_layer(area_key) > visible_max:
        return False
    key = str(area_key or "").strip()
    if key not in SPECIAL_EXPLORE_AREA_KEYS:
        return True
    if not db or not user_row or "id" not in user_row.keys():
        return False
    return _is_special_area_unlocked(db, int(user_row["id"]), key)


def _saved_explore_area_key(user_row, available_areas=None, db=None):
    if not user_row or "last_explore_area_key" not in user_row.keys():
        return None
    area_key = str(user_row["last_explore_area_key"] or "").strip()
    if not area_key or area_key not in EXPLORE_AREA_LAYER_BY_KEY:
        return None
    if not _is_area_unlocked(user_row, area_key, db=db):
        return None
    if available_areas is not None:
        available_keys = {str(area.get("key") or "").strip() for area in available_areas}
        if area_key not in available_keys:
            return None
    return area_key


def _default_explore_area_key(user_row, available_areas, db=None):
    saved = _saved_explore_area_key(user_row, available_areas, db=db)
    if saved:
        return saved
    if not available_areas:
        return None
    return str(available_areas[0].get("key") or "").strip() or None


def _locked_layer_lines(user_row, db=None):
    max_layer = _visible_user_max_unlocked_layer(user_row, db=db)
    release_cap = _release_layer_cap_for_viewer(db, user_row=user_row) if db and user_row else MAX_UNLOCKABLE_LAYER
    lines = []
    for layer in range(max_layer + 1, min(MAX_UNLOCKABLE_LAYER, release_cap) + 1):
        lines.append(f"🔒 第{layer}層（第{layer - 1}層ボス撃破で解放）")
    if (
        release_cap >= 4
        and max_layer >= 4
        and (not db or not user_row or "id" not in user_row.keys() or not _is_special_area_unlocked(db, int(user_row["id"]), LAYER4_FINAL_AREA_KEY))
    ):
        lines.append("🔒 第4層最終試験（Forge / Haze / Burst の3ボス撃破で解放）")
    if (
        release_cap >= 5
        and max_layer >= 5
        and (not db or not user_row or "id" not in user_row.keys() or not _is_special_area_unlocked(db, int(user_row["id"]), LAYER5_FINAL_AREA_KEY))
    ):
        lines.append("🔒 第5層最終試験（Labyrinth / Pinnacle の2ボス撃破で解放）")
    return lines


def _build_map_nodes(user_row, area_streaks=None, db=None):
    nodes = []
    max_layer = _visible_user_max_unlocked_layer(user_row, db=db)
    streaks = area_streaks or {}
    is_admin = bool(user_row and "is_admin" in user_row.keys() and int(user_row["is_admin"] or 0) == 1)
    for area in EXPLORE_AREAS:
        key = area["key"]
        layer = _area_layer(key)
        if layer > max_layer or (db and not _is_area_unlocked(user_row, key, db=db)):
            continue
        info = EXPLORE_AREA_MAP_INFO.get(
            key,
            {
                "desc": [
                    "詳細情報は未登録です。",
                    "推奨: 出撃機体の長所を活かす構成。",
                    "注意: 事前にステータスを確認してください。",
                ],
                "recommended_archetype": "自由",
            },
        )
        stage_modifier = _stage_modifier_for_area(key, is_admin=is_admin)
        tendency = _area_growth_tendency(key)
        tendency_line = str(tendency.get("map_line") or _stage_modifier_summary_line(stage_modifier) or "")
        archetype_label = str(info.get("recommended_archetype") or "自由")
        if archetype_label in {"sniper", "swift", "fortress"}:
            archetype_label = {
                "sniper": "狙撃型",
                "swift": "疾風型",
                "fortress": "鉄壁型",
            }.get(archetype_label, archetype_label)
        nodes.append(
            {
                "key": key,
                "label": area["label"],
                "layer": layer,
                "description_lines": info["desc"][:3],
                "tendency_line": tendency_line,
                "recommended_archetype": archetype_label,
                "win_streak": int(streaks.get(key, 0)),
            }
        )
    return nodes


def _battle_log_mode_for_user(user_row):
    mode = ""
    if user_row and "battle_log_mode" in user_row.keys():
        mode = (user_row["battle_log_mode"] or "").strip().lower()
    return "expanded" if mode == "expanded" else "collapsed"


def _layer1_boss_spawn_check(explore_meter, win_meter, rng=None):
    explore = int(explore_meter or 0)
    wins = int(win_meter or 0)
    if explore < L1_BOSS_MIN_EXPLORE or wins < L1_BOSS_MIN_WINS:
        return False, 0.0
    if explore >= L1_BOSS_PITY_EXPLORE or wins >= L1_BOSS_PITY_WINS:
        return True, 1.0
    prog_e = _clamp((explore - L1_BOSS_MIN_EXPLORE) / (L1_BOSS_PITY_EXPLORE - L1_BOSS_MIN_EXPLORE), 0.0, 1.0)
    prog_w = _clamp((wins - L1_BOSS_MIN_WINS) / (L1_BOSS_PITY_WINS - L1_BOSS_MIN_WINS), 0.0, 1.0)
    prog = max(prog_e, prog_w)
    p = 0.10 + 0.80 * prog
    roller = rng or random
    return bool(roller.random() < p), float(p)


def _build_layer1_boss_enemy(db):
    tier1 = db.execute(
        """
        SELECT AVG(hp) AS avg_hp, AVG(atk) AS avg_atk, AVG(def) AS avg_def, AVG(spd) AS avg_spd, AVG(acc) AS avg_acc, AVG(cri) AS avg_cri
        FROM enemies
        WHERE is_active = 1 AND tier = 1
        """
    ).fetchone()
    avg_hp = float(tier1["avg_hp"] or 22.0)
    avg_atk = float(tier1["avg_atk"] or 8.0)
    avg_def = float(tier1["avg_def"] or 8.0)
    avg_spd = float(tier1["avg_spd"] or 8.0)
    avg_acc = float(tier1["avg_acc"] or 8.0)
    avg_cri = float(tier1["avg_cri"] or 6.0)
    return {
        "id": -1001,
        "key": "boss_layer1_guardian",
        "name_ja": "試作型ガーディアン",
        "image_path": "assets/placeholder_enemy.png",
        "tier": 1,
        "element": "NORMAL",
        "faction": "neutral",
        "hp": max(1, int(round(avg_hp * 2.5))),
        "atk": max(1, int(round(avg_atk * 1.20))),
        "def": max(1, int(round(avg_def * 1.60))),
        "spd": max(1, int(round(avg_spd * 0.70))),
        "acc": max(1, int(round(avg_acc * 1.05))),
        "cri": max(1, int(round(avg_cri))),
        "_is_layer1_boss": True,
        "_crit_multiplier": 1.2,
    }


def _boss_area_label(area_key):
    return AREA_BOSS_LABELS.get(area_key, area_key)


def _area_supports_boss_alert(area_key):
    return area_key in AREA_BOSS_ALERT_AREAS


def _boss_area_key_for_route(area_key):
    layer = _area_layer(area_key)
    if layer in (1, 2, 3):
        return f"layer_{layer}"
    return area_key


def _boss_reward_area_key(area_key):
    key = str(area_key or "").strip()
    if not key:
        return ""
    if key in AREA_BOSS_DECOR_REWARD_KEYS:
        return key
    return _boss_area_key_for_route(key)


def _is_npc_boss_alert_id(enemy_id):
    try:
        value = int(enemy_id)
    except Exception:
        return False
    return value <= -int(NPC_BOSS_ALERT_ID_OFFSET)


def _encode_npc_boss_alert_id(template_id):
    return -int(NPC_BOSS_ALERT_ID_OFFSET) - int(template_id)


def _decode_npc_boss_alert_id(enemy_id):
    if not _is_npc_boss_alert_id(enemy_id):
        return None
    return abs(int(enemy_id)) - int(NPC_BOSS_ALERT_ID_OFFSET)


def _resolve_npc_faction(raw_faction):
    key = _normalize_faction_key(raw_faction)
    return key if key in NPC_BOSS_IMAGE_BY_FACTION else "aurix"


def _npc_boss_special_line(faction_key):
    faction = _resolve_npc_faction(faction_key)
    if faction == "ignis":
        return "未知の戦闘データをもつ侵食機"
    if faction == "ventra":
        return "他機体由来の模倣戦闘体"
    return "残響データを再構成した模倣機"


def _build_npc_boss_enemy_payload(template_row):
    if not template_row:
        return None
    row = dict(template_row)
    faction_key = _resolve_npc_faction(row.get("source_faction"))
    image_path = row.get("image_path") or NPC_BOSS_IMAGE_BY_FACTION.get(faction_key) or "assets/placeholder_enemy.png"
    tier = 2 if str(row.get("boss_area_key") or "layer_2") == "layer_2" else 3
    return {
        "id": None,
        "key": row.get("enemy_key"),
        "name_ja": row.get("enemy_name_ja") or "侵食機",
        "image_path": image_path,
        "tier": int(tier),
        "element": "NORMAL",
        "hp": int(row.get("hp") or 1),
        "atk": int(row.get("atk") or 1),
        "def": int(row.get("def") or 0),
        "spd": int(row.get("spd") or 1),
        "acc": int(row.get("acc") or 1),
        "cri": int(row.get("cri") or 1),
        "faction": faction_key,
        "trait": None,
        "is_boss": 1,
        "boss_area_key": row.get("boss_area_key"),
        "_boss_kind": "npc",
        "_npc_boss_template_id": int(row.get("id") or 0),
        "_source_robot_instance_id": int(row.get("source_robot_instance_id") or 0),
        "_source_user_id": int(row.get("source_user_id") or 0),
        "_source_faction": faction_key,
        "_special_line": _npc_boss_special_line(faction_key),
        "_alert_enemy_id": _encode_npc_boss_alert_id(int(row.get("id") or 0)),
    }


def pick_npc_boss_for_area(db, area_key):
    area = str(area_key or "").strip()
    if area not in NPC_BOSS_ALLOWED_AREAS:
        return None
    rows = db.execute(
        """
        SELECT *
        FROM npc_boss_templates
        WHERE is_active = 1
          AND boss_area_key = ?
        ORDER BY updated_at DESC, id DESC
        """,
        (area,),
    ).fetchall()
    if not rows:
        return None
    weights = [max(0.01, float(r["spawn_weight"] or 1.0)) for r in rows]
    picked = random.choices(rows, weights=weights, k=1)[0]
    return _build_npc_boss_enemy_payload(picked)


def create_npc_boss_from_active_robot(user_id, defeated_boss_area_key):
    area_key = str(defeated_boss_area_key or "").strip()
    if area_key not in NPC_BOSS_ALLOWED_AREAS:
        return None
    db = get_db()
    user_state = db.execute("SELECT active_robot_id, faction FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if not user_state or not user_state["active_robot_id"]:
        return None
    active = db.execute(
        "SELECT id, name FROM robot_instances WHERE id = ? AND user_id = ? AND status = 'active' LIMIT 1",
        (int(user_state["active_robot_id"]), int(user_id)),
    ).fetchone()
    if not active:
        return None
    active = dict(active)
    stats_payload = _compute_robot_stats_for_instance(db, int(active["id"]))
    if not stats_payload:
        return None
    stats = stats_payload.get("stats") or {}
    player_hp = max(1, int(stats.get("hp") or 1))
    player_atk = max(1, int(stats.get("atk") or 1))
    player_def = max(0, int(stats.get("def") or 0))
    player_spd = max(1, int(stats.get("spd") or 1))
    player_acc = max(1, int(stats.get("acc") or 1))
    player_cri = max(1, int(stats.get("cri") or 1))
    source_faction = _resolve_npc_faction(user_state["faction"] if "faction" in user_state.keys() else None)
    enemy_key = f"npc_boss_r{int(active['id'])}_{area_key}"
    enemy_name = NPC_BOSS_NAME_BY_FACTION.get(source_faction, "侵食機")
    image_path = NPC_BOSS_IMAGE_BY_FACTION.get(source_faction, "assets/placeholder_enemy.png")
    now_ts = int(time.time())
    existing = db.execute(
        "SELECT id FROM npc_boss_templates WHERE source_robot_instance_id = ? AND boss_area_key = ? LIMIT 1",
        (int(active["id"]), area_key),
    ).fetchone()
    if existing:
        db.execute(
            """
            UPDATE npc_boss_templates
            SET source_user_id = ?,
                source_faction = ?,
                source_robot_name = ?,
                enemy_key = ?,
                enemy_name_ja = ?,
                image_path = ?,
                hp = ?,
                atk = ?,
                def = ?,
                spd = ?,
                acc = ?,
                cri = ?,
                spawn_weight = 1.0,
                is_active = 1,
                updated_at = ?
            WHERE id = ?
            """,
            (
                int(user_id),
                source_faction,
                str(active.get("name") or ""),
                enemy_key,
                enemy_name,
                image_path,
                int(round(player_hp * 1.35)),
                max(1, int(round(player_atk * 0.90))),
                max(0, int(round(player_def * 0.90))),
                player_spd,
                player_acc,
                player_cri,
                now_ts,
                int(existing["id"]),
            ),
        )
        template_id = int(existing["id"])
    else:
        cur = db.execute(
            """
            INSERT INTO npc_boss_templates
            (source_user_id, source_robot_instance_id, source_faction, source_robot_name, boss_area_key, enemy_key, enemy_name_ja, image_path, hp, atk, def, spd, acc, cri, spawn_weight, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1.0, 1, ?, ?)
            """,
            (
                int(user_id),
                int(active["id"]),
                source_faction,
                str(active.get("name") or ""),
                area_key,
                enemy_key,
                enemy_name,
                image_path,
                int(round(player_hp * 1.35)),
                max(1, int(round(player_atk * 0.90))),
                max(0, int(round(player_def * 0.90))),
                player_spd,
                player_acc,
                player_cri,
                now_ts,
                now_ts,
            ),
        )
        template_id = int(cur.lastrowid)
    return db.execute("SELECT * FROM npc_boss_templates WHERE id = ?", (template_id,)).fetchone()


def _layer_label(layer_no):
    n = int(layer_no or 1)
    return AREA_BOSS_LABELS.get(f"layer_{n}", f"第{n}層")


def _boss_battle_bg_path(enemy_row, is_area_boss):
    if not is_area_boss or not enemy_row:
        return None
    faction = ((enemy_row["faction"] if "faction" in enemy_row.keys() else "") or "").strip().lower()
    faction_map = {
        "aurix": "backgrounds/boss/aurix.png",
        "ventra": "backgrounds/boss/ventra.png",
        "ignis": "backgrounds/boss/ignis.png",
    }
    if faction in faction_map:
        return faction_map[faction]
    key = ((enemy_row["key"] if "key" in enemy_row.keys() else "") or "").strip().lower()
    for token in ("aurix", "ventra", "ignis"):
        if token in key:
            return f"backgrounds/boss/{token}.png"
    return None


def _boss_type_code(enemy_row):
    if not enemy_row:
        return None
    key = ((enemy_row.get("key") if isinstance(enemy_row, dict) else enemy_row["key"]) or "").strip().lower()
    return AREA_BOSS_TYPE_BY_KEY.get(key)


def _boss_type_meta(enemy_row):
    code = _boss_type_code(enemy_row)
    if not code:
        return None
    profile = AREA_BOSS_TYPE_PROFILES.get(code, {})
    return {
        "code": code,
        "label_ja": profile.get("label_ja", code),
        "recommend_build": profile.get("recommend_build", "自由"),
        "icon": profile.get("icon", ""),
    }


def _boss_recommendation_for_type(boss_type):
    return BOSS_TYPE_RECOMMENDED_BUILD.get((boss_type or "").upper())


def _apply_boss_type_modifiers(enemy_row):
    enemy = dict(enemy_row or {})
    meta = _boss_type_meta(enemy)
    if not meta:
        return enemy
    profile = AREA_BOSS_TYPE_PROFILES.get(meta["code"], {})
    mult = profile.get("mult", {})
    for stat in ("hp", "atk", "def", "acc"):
        base = int(enemy.get(stat) or 0)
        factor = float(mult.get(stat, 1.0))
        enemy[stat] = max(1, int(round(base * factor)))
    enemy["_boss_type"] = meta["code"]
    enemy["_boss_type_label"] = meta["label_ja"]
    enemy["_boss_type_recommend"] = meta["recommend_build"]
    enemy["_boss_type_icon"] = meta["icon"]
    return enemy


def _arch_key_for_hit(archetype):
    if isinstance(archetype, dict):
        return (archetype.get("key") or "none").lower()
    if isinstance(archetype, str):
        return archetype.lower()
    return "none"


def _hit_debug(att_acc, def_acc, attacker_archetype):
    att_key = _arch_key_for_hit(attacker_archetype)
    hit_bonus = 0.03 if att_key == "sniper" else 0.0
    hit_chance = _clamp(0.75 + (int(att_acc) - int(def_acc)) * 0.01 + hit_bonus, 0.60, 0.95)
    return {
        "hit_chance": float(hit_chance),
        "att_acc": int(att_acc),
        "def_acc": int(def_acc),
        "hit_bonus": float(hit_bonus),
    }


def _resolve_attack_logged(
    att_atk,
    att_acc,
    att_cri,
    def_def,
    def_acc,
    *,
    rng,
    attacker_archetype=None,
    defender_archetype=None,
    attacker_is_first_striker=False,
    crit_multiplier=1.5,
    force_hit=False,
    damage_noise_range=None,
):
    fallback = _hit_debug(att_acc, def_acc, attacker_archetype)
    result = resolve_attack(
        att_atk,
        att_acc,
        att_cri,
        def_def,
        def_acc,
        rng=rng,
        attacker_archetype=attacker_archetype,
        defender_archetype=defender_archetype,
        attacker_is_first_striker=attacker_is_first_striker,
        crit_multiplier=crit_multiplier,
        force_hit=force_hit,
        return_detail=True,
        damage_noise_range=damage_noise_range,
    )
    if isinstance(result, tuple) and len(result) >= 3 and isinstance(result[2], dict):
        damage, critical, detail = result[0], result[1], dict(result[2])
        detail.setdefault("hit_chance", fallback["hit_chance"])
        detail.setdefault("att_acc", fallback["att_acc"])
        detail.setdefault("def_acc", fallback["def_acc"])
        detail.setdefault("hit_bonus", fallback["hit_bonus"])
        detail.setdefault("hit_forced", bool(force_hit))
        detail.setdefault("miss", int(damage) <= 0)
        return int(damage), bool(critical), detail
    if isinstance(result, tuple) and len(result) >= 2:
        damage, critical = result[0], result[1]
    else:
        damage, critical = 0, False
    detail = {
        **fallback,
        "hit_forced": bool(force_hit),
        "miss": int(damage) <= 0,
    }
    return int(damage), bool(critical), detail


def _is_stable_element_build(parts):
    if not parts or len(parts) != 4:
        return False
    elems = [((p.get("element") if isinstance(p, dict) else None) or "").upper() for p in parts]
    if any(not e for e in elems):
        return False
    return len(set(elems)) == 1


def _build_type_from_parts(parts):
    return "STABLE" if _is_stable_element_build(parts) else "BURST"


def _stat_label(stat_key):
    key = str(stat_key or "").strip()
    lowered = key.lower()
    if lowered in STAT_UI_LABELS:
        return STAT_UI_LABELS[lowered]
    mapped = STAT_ABBR_TO_KEY.get(key.upper())
    if mapped:
        return STAT_UI_LABELS.get(mapped, key)
    return key


def _humanize_stat_text(text):
    out = str(text or "")
    for abbr, key in STAT_ABBR_TO_KEY.items():
        out = out.replace(abbr, STAT_UI_LABELS.get(key, abbr))
    return out


def _normalize_part_type_key(part_type):
    key = str(part_type or "").strip().lower()
    if key in PART_TYPE_TITLES_JA:
        return key
    if key == "rightarm":
        return "right_arm"
    if key == "leftarm":
        return "left_arm"
    return ""


def _guess_part_type_from_key(part_key):
    key = str(part_key or "").strip().lower()
    if key.startswith("right_arm_"):
        return "right_arm"
    if key.startswith("left_arm_"):
        return "left_arm"
    if key.startswith("head_"):
        return "head"
    if key.startswith("legs_"):
        return "legs"
    return ""


def generate_part_display_name_ja(part_key, rarity=None, element=None, part_type=None):
    key = str(part_key or "").strip()
    if not key:
        return ""
    tokens = [tok for tok in key.lower().split("_") if tok]
    part_type_norm = _normalize_part_type_key(part_type) or _guess_part_type_from_key(key)
    rarity_norm = str(rarity or "").strip().upper()
    element_norm = str(element or "").strip().lower()
    if not rarity_norm:
        for tok in tokens:
            tok_up = tok.upper()
            if tok_up in PART_RARITY_SUFFIX_JA:
                rarity_norm = tok_up
                break
    if not element_norm:
        for tok in tokens:
            if tok in PART_ELEMENT_TITLES_JA:
                element_norm = tok
                break
    if not part_type_norm or element_norm not in PART_ELEMENT_TITLES_JA:
        return key
    suffix = PART_RARITY_SUFFIX_JA.get(rarity_norm, "")
    return f"{PART_ELEMENT_TITLES_JA[element_norm]}{PART_TYPE_TITLES_JA[part_type_norm]}{suffix}"


def _part_display_name_ja(part_row_or_key, rarity=None, element=None, part_type=None):
    if isinstance(part_row_or_key, (sqlite3.Row, dict)):
        row = part_row_or_key
        key = str(row["key"]) if "key" in row.keys() and row["key"] else ""
        explicit = (
            str(row["display_name_ja"]).strip()
            if "display_name_ja" in row.keys() and row["display_name_ja"]
            else ""
        )
        if explicit:
            return explicit
        generated = generate_part_display_name_ja(
            key,
            rarity=(row["rarity"] if "rarity" in row.keys() else rarity),
            element=(row["element"] if "element" in row.keys() else element),
            part_type=(row["part_type"] if "part_type" in row.keys() else part_type),
        )
        if generated:
            return generated
        legacy = str(row["name"]).strip() if "name" in row.keys() and row["name"] else ""
        return legacy or key
    key = str(part_row_or_key or "").strip()
    generated = generate_part_display_name_ja(
        key,
        rarity=rarity,
        element=element,
        part_type=part_type,
    )
    return generated or key


PART_STAT_KEYS = ("hp", "atk", "def", "spd", "acc", "cri")
PART_IMAGE_PATH_ALIASES = {
    "parts/head/head_normal.png": "parts/head/head_n_normal.png",
    "parts/right_arm/right_arm_normal.png": "parts/right_arm/right_arm_n_normal.png",
    "parts/left_arm/left_arm_normal.png": "parts/left_arm/left_arm_n_normal.png",
    "parts/legs/legs_normal.png": "parts/legs/legs_n_normal.png",
}


def _normalize_part_type_filter(raw_value):
    key = _norm_part_type(str(raw_value or "").strip().upper())
    return key if key in PART_TYPE_FILTER_LABELS_JA else ""


def _part_type_ui_label(part_type):
    norm = _normalize_part_type_filter(part_type)
    if norm:
        return PART_TYPE_FILTER_LABELS_JA[norm]
    return str(part_type or "パーツ")


def _part_type_filter_rows(selected_part_type, endpoint, *, extra_params=None):
    params = {
        str(key): value
        for key, value in (extra_params or {}).items()
        if value not in (None, "")
    }
    rows = []
    for key, label in (("", "すべて"), *PART_TYPE_FILTER_LABELS_JA.items()):
        next_params = dict(params)
        next_params.pop("page", None)
        if key:
            next_params["part_type"] = key
        else:
            next_params.pop("part_type", None)
        rows.append(
            {
                "key": key,
                "label": label,
                "is_active": selected_part_type == key,
                "url": url_for(endpoint, **next_params),
            }
        )
    return rows


def _part_total_value(stat_map):
    stats = stat_map or {}
    return sum(int(stats.get(key) or 0) for key in PART_STAT_KEYS)


def _delta_text(delta_value):
    delta = int(delta_value or 0)
    if delta > 0:
        return f"+{delta}"
    if delta < 0:
        return str(delta)
    return "±0"


def _part_stat_rows(stats, compare_stats=None, *, focus_limit=2):
    stat_map = stats or {}
    compare_map = compare_stats or {}
    focus_keys = {
        row["key"] for row in _robot_focus_stat_rows(stat_map, limit=max(1, int(focus_limit or 2)))
    }
    rows = []
    for key in PART_STAT_KEYS:
        value = int(stat_map.get(key) or 0)
        after_value = None
        delta = None
        delta_text = None
        delta_class = ""
        if compare_stats is not None:
            after_value = int(compare_map.get(key) or 0)
            delta = int(after_value - value)
            delta_text = _delta_text(delta)
            if delta > 0:
                delta_class = "up"
            elif delta < 0:
                delta_class = "down"
            else:
                delta_class = "flat"
        rows.append(
            {
                "key": key,
                "label": _stat_label(key),
                "value": value,
                "after_value": after_value,
                "delta": delta,
                "delta_text": delta_text,
                "delta_class": delta_class,
                "is_focus": key in focus_keys,
            }
        )
    return rows


def _part_image_candidates(image_path):
    raw = str(image_path or "").strip().replace("\\", "/").lstrip("/")
    if not raw:
        return []
    aliased = PART_IMAGE_PATH_ALIASES.get(raw)
    rels = []
    if aliased and aliased != raw:
        rels.append(f"robot_assets/{aliased}")
    rels.append(f"robot_assets/{raw}")
    seen = set()
    out = []
    for rel in rels:
        if rel not in seen:
            seen.add(rel)
            out.append(rel)
    return out


def _part_card_payload(part_row, *, compare_row=None, can_discard=None):
    item = dict(part_row)
    status_key = str(item.get("status") or "inventory").strip().lower()
    stats = compute_part_stats(item)
    item["display_name"] = _part_display_name_ja(item)
    item["part_type_label"] = _part_type_ui_label(item.get("part_type"))
    item["rarity_label"] = str(item.get("rarity") or "N").upper()
    item["status_key"] = status_key
    item["is_equipped"] = status_key == "equipped"
    item["is_inventory"] = status_key == "inventory"
    item["is_overflow"] = status_key == "overflow"
    item["can_discard"] = (status_key == "inventory") if can_discard is None else bool(can_discard)
    if item["is_equipped"]:
        item["status_label"] = "装備中"
    elif item["is_overflow"]:
        item["status_label"] = "保管中"
    else:
        item["status_label"] = "所持中"
    if item["is_inventory"]:
        item["material_hint"] = "強化素材に使える"
    elif item["is_overflow"]:
        item["material_hint"] = "所持枠がいっぱいのため保管中"
    else:
        item["material_hint"] = "今は素材に使えない"
    item["image_url"] = url_for("static", filename=_part_image_rel(item), v=APP_VERSION)
    item["stats"] = stats
    item["total_value"] = int(_part_total_value(stats))
    item["focus_rows"] = _robot_focus_stat_rows(stats, limit=2)
    item["focus_line"] = " / ".join(row["label"] for row in item["focus_rows"])
    item["extreme_title"] = _extract_part_extreme_title(item)
    compare_stats = None
    if compare_row:
        compare_item = dict(compare_row)
        compare_stats = compute_part_stats(compare_item)
        item["compare_display_name"] = _part_display_name_ja(compare_item)
        item["compare_image_url"] = url_for("static", filename=_part_image_rel(compare_item), v=APP_VERSION)
        item["compare_stats"] = compare_stats
        item["compare_total_value"] = int(_part_total_value(compare_stats))
        item["compare_total_delta"] = int(item["compare_total_value"] - item["total_value"])
        item["compare_total_delta_text"] = _delta_text(item["compare_total_delta"])
    item["stat_rows"] = _part_stat_rows(stats, compare_stats)
    return item


def _backfill_part_display_names(db):
    rows = db.execute(
        """
        SELECT id, key, rarity, element, part_type
        FROM robot_parts
        WHERE COALESCE(TRIM(display_name_ja), '') = ''
        """
    ).fetchall()
    updated = 0
    for row in rows:
        name = generate_part_display_name_ja(
            row["key"],
            rarity=row["rarity"],
            element=row["element"],
            part_type=row["part_type"],
        )
        if not name:
            continue
        db.execute(
            "UPDATE robot_parts SET display_name_ja = ? WHERE id = ?",
            (name, int(row["id"])),
        )
        updated += 1
    if updated > 0:
        app.logger.info("robot_parts display_name_ja backfill updated=%s", updated)
    return updated


def refresh_part_offset_cache(db):
    global PART_OFFSET_CACHE, PART_OFFSET_CACHE_VERSION, COMPOSE_REV
    rows = db.execute("SELECT key, offset_x, offset_y FROM robot_parts").fetchall()
    PART_OFFSET_CACHE = {
        str(row["key"]): {
            "offset_x": int(row["offset_x"] or 0),
            "offset_y": int(row["offset_y"] or 0),
        }
        for row in rows
    }
    PART_OFFSET_CACHE_VERSION = int(time.time())
    COMPOSE_REV = max(int(COMPOSE_REV or 0), int(PART_OFFSET_CACHE_VERSION))
    app.logger.info(
        "part_offset_cache refreshed count=%s version=%s",
        len(PART_OFFSET_CACHE),
        PART_OFFSET_CACHE_VERSION,
    )
    return len(PART_OFFSET_CACHE)


def _invalidate_composed_images_for_offset_change(db):
    global COMPOSE_REV
    # Offset change must force re-compose from robot_parts DB offsets.
    db.execute("UPDATE robot_builds SET composed_image_path = NULL")
    db.execute("UPDATE robot_instances SET composed_image_path = NULL, icon_32_path = NULL")
    COMPOSE_REV = int(time.time())


def _normalize_style_key(style_key):
    key = str(style_key or "").strip().lower()
    if key in ROBOT_STYLE_DEFINITIONS:
        return key
    return "stable"


def _default_style_stats():
    return {
        "stable": {"hitless_wins": 0},
        "burst": {"crit_finishes": 0},
        "desperate": {"low_hp_wins": 0},
    }


def _decode_style_stats_json(raw_json):
    stats = _default_style_stats()
    try:
        payload = json.loads(raw_json or "{}")
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        return stats
    for style_key in ("stable", "burst", "desperate"):
        section = payload.get(style_key)
        if isinstance(section, dict):
            for metric_key in stats[style_key].keys():
                stats[style_key][metric_key] = int(section.get(metric_key) or 0)
    return stats


def _encode_style_stats_json(stats):
    safe = _default_style_stats()
    source = stats or {}
    for style_key in safe.keys():
        section = source.get(style_key) if isinstance(source, dict) else None
        if isinstance(section, dict):
            for metric_key in safe[style_key].keys():
                safe[style_key][metric_key] = int(section.get(metric_key) or 0)
    return json.dumps(safe, ensure_ascii=False, separators=(",", ":"))


def _style_achievements_progress(robot_row):
    raw_json = None
    if robot_row is not None:
        if isinstance(robot_row, dict):
            raw_json = robot_row.get("style_stats_json")
        elif hasattr(robot_row, "keys") and "style_stats_json" in robot_row.keys():
            raw_json = robot_row["style_stats_json"]
    style_stats = _decode_style_stats_json(raw_json)
    progress = []
    for item in STYLE_ACHIEVEMENT_DEFS:
        style_key, metric_key = STYLE_ACHIEVEMENT_JSON_KEY_MAP[item["key"]]
        value = int(style_stats.get(style_key, {}).get(metric_key, 0))
        target = int(item["target"])
        progress.append(
            {
                "key": item["key"],
                "title": item["title"],
                "style_label": item["label"],
                "desc": item["desc"],
                "value": value,
                "target": target,
                "done": value >= target,
            }
        )
    return progress


def _is_no_damage_victory(damage_taken_total):
    return float(damage_taken_total or 0.0) <= 0.0


def _home_dedupe_rows(rows, text_key):
    deduped = []
    seen_ids = set()
    seen_fallback = set()
    for row in rows or []:
        row_id = row["id"] if "id" in row.keys() else None
        text = str(row[text_key]) if text_key in row.keys() else ""
        created_at = str(row["created_at"]) if "created_at" in row.keys() else ""
        row_type = str(row["row_type"]) if "row_type" in row.keys() else "generic"
        user_id = int(row["user_id"] or 0) if "user_id" in row.keys() and row["user_id"] is not None else 0
        username = (str(row["username"]) if "username" in row.keys() and row["username"] is not None else "")
        extra = (str(row["dedupe_extra"]) if "dedupe_extra" in row.keys() and row["dedupe_extra"] is not None else "")
        fallback = (row_type, user_id, username, text, extra, created_at[:19])
        if fallback in seen_fallback:
            continue
        if row_id is not None:
            row_id = int(row_id)
            if row_id in seen_ids:
                continue
            seen_ids.add(row_id)
        seen_fallback.add(fallback)
        deduped.append(row)
    return deduped


def _chat_created_at_ts(created_at_text):
    text = str(created_at_text or "").strip()
    if not text:
        return 0
    try:
        return int(time.mktime(time.strptime(text[:19], "%Y-%m-%d %H:%M:%S")))
    except (OverflowError, TypeError, ValueError):
        return 0


def _chat_normalize_room_key(raw_value, *, allow_world=True):
    key = str(raw_value or "").strip()
    if allow_world and key == COMM_WORLD_ROOM_KEY:
        return key
    if key in COMM_ROOM_DEF_MAP:
        return key
    return ""


def _chat_room_settings(room_key):
    key = _chat_normalize_room_key(room_key)
    if key == COMM_WORLD_ROOM_KEY:
        return {
            "key": COMM_WORLD_ROOM_KEY,
            "title": "世界ログ",
            "summary": "世界の動きや、他のロボ使いの声がここに流れます。",
            "max_chars": COMM_WORLD_MAX_CHARS,
            "cooldown_seconds": COMM_WORLD_COOLDOWN_SECONDS,
            "timeline_limit": COMM_WORLD_TIMELINE_LIMIT,
        }
    room_def = COMM_ROOM_DEF_MAP.get(key)
    if room_def:
        return {
            "key": room_def["key"],
            "title": room_def["title"],
            "summary": room_def["summary"],
            "tone": room_def["tone"],
            "max_chars": COMM_ROOM_MAX_CHARS,
            "cooldown_seconds": COMM_ROOM_COOLDOWN_SECONDS,
            "timeline_limit": COMM_ROOM_TIMELINE_LIMIT,
        }
    return None


def _relative_redirect_target(raw_value, fallback):
    text = str(raw_value or "").strip()
    if text.startswith("/") and not text.startswith("//"):
        return text
    return fallback


def _insert_chat_message(db, *, user_id, username, message, room_key=COMM_WORLD_ROOM_KEY, created_at_text=None):
    room_value = _chat_normalize_room_key(room_key) or COMM_WORLD_ROOM_KEY
    username_value = (str(username or "").strip() or "unknown")[:80]
    message_value = str(message or "").strip()
    created_text = str(created_at_text or now_str()).strip() or now_str()
    cur = db.execute(
        """
        INSERT INTO chat_messages (user_id, username, room_key, message, created_at, deleted_at)
        VALUES (?, ?, ?, ?, ?, NULL)
        """,
        (
            (int(user_id) if user_id is not None else None),
            username_value,
            room_value,
            message_value,
            created_text,
        ),
    )
    return int(cur.lastrowid or 0)


def _chat_room_rows(db, room_key, *, limit):
    room_value = _chat_normalize_room_key(room_key) or COMM_WORLD_ROOM_KEY
    return db.execute(
        """
        SELECT id, user_id, username, room_key, message, created_at
        FROM chat_messages
        WHERE COALESCE(room_key, ?) = ?
          AND deleted_at IS NULL
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (COMM_WORLD_ROOM_KEY, room_value, int(limit)),
    ).fetchall()


def _chat_room_cooldown_remaining(db, *, user_id, room_key, cooldown_seconds, now_ts=None):
    room_value = _chat_normalize_room_key(room_key) or COMM_WORLD_ROOM_KEY
    row = db.execute(
        """
        SELECT created_at
        FROM chat_messages
        WHERE user_id = ?
          AND COALESCE(room_key, ?) = ?
          AND deleted_at IS NULL
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (int(user_id), COMM_WORLD_ROOM_KEY, room_value),
    ).fetchone()
    if not row:
        return 0
    last_ts = _chat_created_at_ts(row["created_at"])
    if last_ts <= 0:
        return 0
    now_value = time.time() if now_ts is None else float(now_ts)
    remaining = float(cooldown_seconds) - max(0.0, now_value - float(last_ts))
    if remaining <= 0:
        return 0
    return int(math.ceil(remaining))


def _chat_post_redirect(default_endpoint, *, room_key=None):
    fallback = url_for(default_endpoint, room=room_key) if room_key else url_for(default_endpoint)
    return _relative_redirect_target(request.form.get("next"), fallback)


def _submit_chat_message(db, *, user_id, username, room_key, surface):
    settings = _chat_room_settings(room_key)
    if not settings:
        abort(404)
    redirect_target = _chat_post_redirect(
        "comms_world" if settings["key"] == COMM_WORLD_ROOM_KEY else "comms_rooms",
        room_key=(settings["key"] if settings["key"] != COMM_WORLD_ROOM_KEY else None),
    )
    text = str(request.form.get("message") or "").strip()
    if not text:
        session["message"] = "投稿内容を入力してください。"
        return redirect(redirect_target)
    if len(text) > int(settings["max_chars"]):
        session["message"] = f"{int(settings['max_chars'])}文字以内で入力してください。"
        return redirect(redirect_target)
    remaining = _chat_room_cooldown_remaining(
        db,
        user_id=user_id,
        room_key=settings["key"],
        cooldown_seconds=int(settings["cooldown_seconds"]),
    )
    if remaining > 0:
        session["message"] = f"連投はあと{int(remaining)}秒待ってください。"
        return redirect(redirect_target)
    message_id = _insert_chat_message(
        db,
        user_id=int(user_id),
        username=username,
        message=text,
        room_key=settings["key"],
    )
    audit_log(
        db,
        AUDIT_EVENT_TYPES["CHAT_POST"],
        user_id=int(user_id),
        request_id=getattr(g, "request_id", None),
        action_key="chat_post",
        entity_type="chat_message",
        entity_id=int(message_id),
        payload={
            "room_key": settings["key"],
            "surface": surface,
            "message_length": len(text),
            "preview": text[:60],
        },
        ip=request.remote_addr,
    )
    db.commit()
    return redirect(redirect_target)


def _home_chat_messages(db, limit=50):
    fetch_limit = max(int(limit) * 4, int(limit))
    rows = db.execute(
        """
        SELECT id, user_id, username, room_key, message, created_at, 'chat' AS row_type, '' AS dedupe_extra
        FROM chat_messages
        WHERE COALESCE(room_key, ?) = ?
          AND deleted_at IS NULL
        ORDER BY id DESC
        LIMIT ?
        """,
        (COMM_WORLD_ROOM_KEY, COMM_WORLD_ROOM_KEY, int(fetch_limit)),
    ).fetchall()
    filtered = []
    for row in rows:
        username = (row["username"] or "").strip().upper()
        message = (row["message"] or "").strip()
        if username == "SYSTEM" and HOME_BUILD_CHAT_PATTERN.search(message):
            continue
        filtered.append(row)
    return list(reversed(_home_dedupe_rows(filtered, "message")[: int(limit)]))


def _home_post_messages(db, limit=20):
    rows = db.execute(
        """
        SELECT id, user_id, username, title, body, created_at, 'post' AS row_type, COALESCE(title, '') AS dedupe_extra
        FROM posts
        ORDER BY id DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    return list(reversed(_home_dedupe_rows(rows, "body")))


def _home_humanize_log_message(row):
    username = str(row.get("username") or "").strip()
    message = str(row.get("message") or "").strip()
    if not message:
        return "更新がありました。"
    if username.upper() == "SYSTEM":
        # 例: 【BOSS撃破】alice が 第一層 の『...』を討伐！...
        m = re.search(r"【BOSS撃破】\s*([^ ]+)\s+が\s+([^ ]+)", message)
        if m:
            actor = m.group(1)
            area = m.group(2)
            return f"{actor} が{area}ボスを撃破！"
        if "進化コア" in message:
            m = re.search(r"([^ ]+)\s+が", message)
            if m:
                return f"{m.group(1)} が進化コアを入手！"
            return "進化コアを入手！"
        if "入手" in message:
            m = re.search(r"([^ ]+)\s+が", message)
            if m:
                return f"{m.group(1)} がパーツを入手！"
            return "パーツを入手！"
    return f"{username}: {message}" if username else message


def _apply_style_achievement_progress_once(
    db,
    *,
    user_id,
    robot_id,
    battle_id,
    stable_no_damage_inc,
    burst_crit_finisher_inc,
    desperate_low_hp_inc,
    request_ip=None,
):
    battle_key = str(battle_id or "").strip()
    robot_id_val = int(robot_id or 0)
    if not battle_key or robot_id_val <= 0:
        return False
    increments = {
        "stable_no_damage_wins": int(stable_no_damage_inc or 0),
        "burst_crit_finisher_kills": int(burst_crit_finisher_inc or 0),
        "desperate_low_hp_wins": int(desperate_low_hp_inc or 0),
    }
    if all(v <= 0 for v in increments.values()):
        return False
    already = db.execute(
        """
        SELECT 1
        FROM world_events_log
        WHERE event_type = ?
          AND user_id = ?
          AND request_id = ?
        LIMIT 1
        """,
        (STYLE_ACHIEVEMENT_EVENT_TYPE, int(user_id), battle_key),
    ).fetchone()
    if already:
        return False
    row = db.execute(
        "SELECT style_stats_json FROM robot_instances WHERE id = ? AND user_id = ?",
        (robot_id_val, int(user_id)),
    ).fetchone()
    if not row:
        return False
    style_stats = _decode_style_stats_json(row["style_stats_json"])
    for key, inc in increments.items():
        if inc <= 0:
            continue
        style_key, metric_key = STYLE_ACHIEVEMENT_JSON_KEY_MAP[key]
        style_stats[style_key][metric_key] = int(style_stats[style_key].get(metric_key, 0)) + int(inc)
    db.execute(
        "UPDATE robot_instances SET style_stats_json = ? WHERE id = ?",
        (_encode_style_stats_json(style_stats), robot_id_val),
    )
    audit_log(
        db,
        STYLE_ACHIEVEMENT_EVENT_TYPE,
        user_id=int(user_id),
        request_id=battle_key,
        action_key="explore",
        entity_type="robot_instance",
        entity_id=robot_id_val,
        payload={"battle_id": battle_key, "robot_instance_id": robot_id_val, "increments": increments},
        ip=request_ip,
    )
    return True


def _ensure_robot_title_master_rows(db):
    for row in ROBOT_TITLE_DEFS:
        db.execute(
            """
            INSERT INTO robot_titles (key, name_ja, desc_ja, sort_order, is_active)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(key) DO UPDATE SET
                name_ja = excluded.name_ja,
                desc_ja = excluded.desc_ja,
                sort_order = excluded.sort_order,
                is_active = 1
            """,
            (row["key"], row["name_ja"], row["desc_ja"], int(row["sort_order"])),
        )


def _update_robot_history(
    db,
    *,
    robot_id,
    week_key,
    won,
    is_boss_encounter,
    is_boss_defeat,
    weekly_fit_win,
):
    now = int(time.time())
    db.execute(
        """
        INSERT INTO robot_history
        (robot_id, battles_total, wins_total, losses_total, boss_encounters_total, boss_defeats_total, wins_this_week, wins_this_week_key, updated_at)
        VALUES (?, 0, 0, 0, 0, 0, 0, ?, ?)
        ON CONFLICT(robot_id) DO NOTHING
        """,
        (int(robot_id), str(week_key or ""), now),
    )
    week_key_text = str(week_key or "")
    weekly_fit_inc = 1 if weekly_fit_win else 0
    db.execute(
        """
        UPDATE robot_history
        SET battles_total = battles_total + 1,
            wins_total = wins_total + ?,
            losses_total = losses_total + ?,
            boss_encounters_total = boss_encounters_total + ?,
            boss_defeats_total = boss_defeats_total + ?,
            wins_this_week = CASE
                WHEN COALESCE(wins_this_week_key, '') != ? THEN ?
                ELSE wins_this_week + ?
            END,
            wins_this_week_key = ?,
            updated_at = ?
        WHERE robot_id = ?
        """,
        (
            1 if won else 0,
            0 if won else 1,
            1 if is_boss_encounter else 0,
            1 if is_boss_defeat else 0,
            week_key_text,
            weekly_fit_inc,
            weekly_fit_inc,
            week_key_text,
            now,
            int(robot_id),
        ),
    )


def _apply_robot_history_update_once(
    db,
    *,
    user_id,
    battle_id,
    robot_id,
    week_key,
    won,
    is_boss_encounter,
    is_boss_defeat,
    weekly_fit_win,
    request_ip=None,
):
    battle_key = str(battle_id or "").strip()
    if not battle_key:
        return False
    already = db.execute(
        """
        SELECT 1
        FROM world_events_log
        WHERE event_type = 'audit.robot.history.progress'
          AND user_id = ?
          AND request_id = ?
        LIMIT 1
        """,
        (int(user_id), battle_key),
    ).fetchone()
    if already:
        return False
    _update_robot_history(
        db,
        robot_id=int(robot_id),
        week_key=str(week_key or ""),
        won=bool(won),
        is_boss_encounter=bool(is_boss_encounter),
        is_boss_defeat=bool(is_boss_defeat),
        weekly_fit_win=bool(weekly_fit_win),
    )
    audit_log(
        db,
        "audit.robot.history.progress",
        user_id=int(user_id),
        request_id=battle_key,
        action_key="explore",
        entity_type="robot_instance",
        entity_id=int(robot_id),
        payload={
            "battle_id": battle_key,
            "week_key": str(week_key or ""),
            "won": bool(won),
            "is_boss_encounter": bool(is_boss_encounter),
            "is_boss_defeat": bool(is_boss_defeat),
            "weekly_fit_win": bool(weekly_fit_win),
        },
        ip=request_ip,
    )
    return True


def _sync_robot_title_unlocks(db, *, robot_id):
    _ensure_robot_title_master_rows(db)
    history = db.execute(
        """
        SELECT battles_total, wins_total, losses_total, boss_encounters_total, boss_defeats_total, wins_this_week
        FROM robot_history
        WHERE robot_id = ?
        """,
        (int(robot_id),),
    ).fetchone()
    if not history:
        return
    metric_values = {
        "battles_total": int(history["battles_total"] or 0),
        "wins_total": int(history["wins_total"] or 0),
        "losses_total": int(history["losses_total"] or 0),
        "boss_encounters_total": int(history["boss_encounters_total"] or 0),
        "boss_defeats_total": int(history["boss_defeats_total"] or 0),
        "wins_this_week": int(history["wins_this_week"] or 0),
    }
    now = int(time.time())
    for row in ROBOT_TITLE_DEFS:
        metric = row.get("metric")
        if not metric:
            continue
        metric = row["metric"]
        if int(metric_values.get(metric, 0)) < int(row["threshold"]):
            continue
        _grant_robot_title_by_key(db, robot_id=int(robot_id), title_key=row["key"], unlocked_at=now)


def _grant_robot_title_by_key(db, *, robot_id, title_key, unlocked_at=None):
    title_row = db.execute(
        "SELECT id FROM robot_titles WHERE key = ? AND is_active = 1",
        (str(title_key),),
    ).fetchone()
    if not title_row:
        return False
    db.execute(
        """
        INSERT INTO robot_title_unlocks (robot_id, title_id, unlocked_at)
        VALUES (?, ?, ?)
        ON CONFLICT(robot_id, title_id) DO NOTHING
        """,
        (int(robot_id), int(title_row["id"]), int(unlocked_at or time.time())),
    )
    return True


def _robot_primary_title(db, robot_id):
    row = db.execute(
        """
        SELECT rt.name_ja
        FROM robot_title_unlocks rtu
        JOIN robot_titles rt ON rt.id = rtu.title_id
        WHERE rtu.robot_id = ? AND rt.is_active = 1
        ORDER BY rt.sort_order ASC, rtu.unlocked_at ASC
        LIMIT 1
        """,
        (int(robot_id),),
    ).fetchone()
    return row["name_ja"] if row else "無銘"


def _record_robot_boss_achievement(db, *, robot_id, enemy_row, week_key):
    if not enemy_row:
        return
    enemy_key = enemy_row["key"] if "key" in enemy_row.keys() else None
    enemy_name = enemy_row["name_ja"] if "name_ja" in enemy_row.keys() else "層ボス"
    created_at = int(time.time())
    title = f"撃破証明: {enemy_name}"
    body = f"{week_key} に {enemy_name} を撃破"
    db.execute(
        """
        INSERT INTO robot_achievements
        (robot_id, type, title, body, enemy_key, enemy_name, week_key, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (int(robot_id), "boss_defeat", title, body, enemy_key, enemy_name, str(week_key or ""), created_at),
    )


def _robot_history_row(db, robot_id):
    row = db.execute(
        """
        SELECT robot_id, battles_total, wins_total, losses_total, boss_encounters_total, boss_defeats_total, wins_this_week, wins_this_week_key, updated_at
        FROM robot_history
        WHERE robot_id = ?
        """,
        (int(robot_id),),
    ).fetchone()
    if row:
        return row
    return {
        "robot_id": int(robot_id),
        "battles_total": 0,
        "wins_total": 0,
        "losses_total": 0,
        "boss_encounters_total": 0,
        "boss_defeats_total": 0,
        "wins_this_week": 0,
        "wins_this_week_key": "",
        "updated_at": 0,
    }


def _showcase_query_rows(db, *, user_id, sort_key, limit=80):
    order_by = {
        "new": "ri.updated_at DESC, ri.id DESC",
        "week": "COALESCE(rh.wins_this_week, 0) DESC, ri.updated_at DESC",
        "boss": "COALESCE(rh.boss_defeats_total, 0) DESC, ri.updated_at DESC",
        "like": "COALESCE(v.vote_count, 0) DESC, ri.updated_at DESC",
    }.get(sort_key, "ri.updated_at DESC, ri.id DESC")
    rows = db.execute(
        f"""
        SELECT
            ri.id,
            ri.user_id,
            ri.name,
            ri.composed_image_path,
            ri.updated_at,
            u.username,
            COALESCE(rh.wins_this_week, 0) AS wins_this_week,
            COALESCE(rh.boss_defeats_total, 0) AS boss_defeats_total,
            COALESCE(v.vote_count, 0) AS vote_count,
            CASE WHEN sv.user_id IS NULL THEN 0 ELSE 1 END AS liked_by_me,
            COALESCE(pt.primary_title, '無銘') AS primary_title
        FROM robot_instances ri
        JOIN users u ON u.id = ri.user_id
        LEFT JOIN robot_history rh ON rh.robot_id = ri.id
        LEFT JOIN (
            SELECT robot_id, COUNT(*) AS vote_count
            FROM showcase_votes
            WHERE vote_type = 'like'
            GROUP BY robot_id
        ) v ON v.robot_id = ri.id
        LEFT JOIN showcase_votes sv
           ON sv.robot_id = ri.id
           AND sv.user_id = ?
           AND sv.vote_type = 'like'
        LEFT JOIN (
            SELECT rtu.robot_id, MIN(rt.sort_order) AS min_sort
            FROM robot_title_unlocks rtu
            JOIN robot_titles rt ON rt.id = rtu.title_id AND rt.is_active = 1
            GROUP BY rtu.robot_id
        ) pt_sort ON pt_sort.robot_id = ri.id
        LEFT JOIN (
            SELECT rtu.robot_id, rt.sort_order, rt.name_ja AS primary_title
            FROM robot_title_unlocks rtu
            JOIN robot_titles rt ON rt.id = rtu.title_id AND rt.is_active = 1
        ) pt ON pt.robot_id = ri.id AND pt.sort_order = pt_sort.min_sort
        WHERE ri.status = 'active' AND COALESCE(ri.is_public, 1) = 1
        ORDER BY {order_by}
        LIMIT ?
        """,
        (int(user_id), int(limit)),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["image_url"] = _composed_image_url(item.get("composed_image_path"), item.get("updated_at"))
        stat_obj = _compute_robot_stats_for_instance(db, int(item["id"]))
        item["profile"] = _robot_profile_view(stat_obj)
        item["metric_fastest"] = _robot_metric_value("fastest", stat_obj["stats"] if stat_obj else None)
        item["metric_durable"] = _robot_metric_value("durable", stat_obj["stats"] if stat_obj else None)
        item["metric_precision"] = _robot_metric_value("precision", stat_obj["stats"] if stat_obj else None)
        item["metric_burst"] = _robot_metric_value("burst", stat_obj["stats"] if stat_obj else None)
        out.append(item)
    out = _decorate_user_rows(db, out, user_key="user_id")
    if sort_key in {"fastest", "durable", "precision", "burst"}:
        value_key = f"metric_{sort_key}"
        out.sort(
            key=lambda item: (
                -int(item.get(value_key) or 0),
                -int(item.get("vote_count") or 0),
                str(item.get("username") or ""),
                str(item.get("name") or ""),
            )
        )
    if len(out) > int(limit):
        out = out[: int(limit)]
    return out


def _ranking_rows_from_event_log(db, *, event_type, limit=50, start_ts=None, end_ts=None):
    where = ["event_type = ?", "user_id IS NOT NULL"]
    params = [str(event_type)]
    if start_ts is not None:
        where.append("created_at >= ?")
        params.append(int(start_ts))
    if end_ts is not None:
        where.append("created_at < ?")
        params.append(int(end_ts))
    rows = db.execute(
        f"""
        SELECT u.id, u.username, metrics.metric_value
        FROM (
            SELECT user_id, COUNT(*) AS metric_value
            FROM world_events_log
            WHERE {' AND '.join(where)}
            GROUP BY user_id
        ) metrics
        JOIN users u ON u.id = metrics.user_id
        ORDER BY metrics.metric_value DESC, u.username ASC
        LIMIT ?
        """,
        [*params, int(limit)],
    ).fetchall()
    return rows


def _ranking_rows(db, metric_key, limit=50, week_key=None):
    metric = RANKING_METRIC_DEF_BY_KEY.get(metric_key) or RANKING_METRIC_DEF_BY_KEY["wins"]
    wk = str(week_key or _world_week_key())
    if metric.get("row_kind") == "robot":
        return _robot_metric_rows(db, metric["key"], limit=limit)
    if metric["key"] == "wins":
        rows = db.execute(
            """
            SELECT id, username, wins AS metric_value
            FROM users
            ORDER BY wins DESC, username ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return rows, metric
    if metric["key"] == "explores":
        return (
            _ranking_rows_from_event_log(
                db,
                event_type=AUDIT_EVENT_TYPES["EXPLORE_END"],
                limit=limit,
            ),
            metric,
        )
    start_dt, end_dt = _world_week_bounds(wk)
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    if metric["key"] == "weekly_explores":
        return (
            _ranking_rows_from_event_log(
                db,
                event_type=AUDIT_EVENT_TYPES["EXPLORE_END"],
                limit=limit,
                start_ts=start_ts,
                end_ts=end_ts,
            ),
            metric,
        )
    if metric["key"] == "weekly_bosses":
        return (
            _ranking_rows_from_event_log(
                db,
                event_type=AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                limit=limit,
                start_ts=start_ts,
                end_ts=end_ts,
            ),
            metric,
        )
    return _ranking_rows(db, "wins", limit=limit, week_key=wk)


def _issue_explore_submission_id():
    submission_id = str(uuid.uuid4())
    # /home で探索フォームを描画するたびに新しい submission_id を発行し、session に保持する。
    # 同じフォームの POST 再送時は同じ submission_id が送られるため、battle_id を再利用できる。
    session["explore_submission_id"] = submission_id
    return submission_id


def _battle_id_for_explore_submission(submission_id):
    sid = str(submission_id or "").strip()
    if not sid:
        return str(uuid.uuid4())
    mapping = session.get("explore_battle_ids")
    if not isinstance(mapping, dict):
        mapping = {}
    existing = mapping.get(sid)
    if existing:
        return str(existing)
    battle_id = str(uuid.uuid4())
    mapping[sid] = battle_id
    if len(mapping) > 32:
        # session肥大化防止。新しい32件のみ保持。
        recent_items = list(mapping.items())[-32:]
        mapping = {k: v for k, v in recent_items}
    # battle_id は session["explore_battle_ids"] に保持。
    # 同一 submission_id の再送 POST では同じ battle_id を返す。
    session["explore_battle_ids"] = mapping
    return battle_id


def _robot_style_description(style_key):
    return (ROBOT_STYLE_DEFINITIONS.get(style_key) or {}).get("description_jp", "防御・命中寄り（長期戦向き）")


def _pick_robot_style_key(style_scores):
    best = ROBOT_STYLE_TIE_BREAK[0]
    best_score = float((style_scores or {}).get(best) or 0.0)
    for key in ROBOT_STYLE_TIE_BREAK[1:]:
        score = float((style_scores or {}).get(key) or 0.0)
        if score > best_score + 1e-12:
            best = key
            best_score = score
    return best


def _score_style_from_norm(norm, weights):
    score = 0.0
    for key, weight in (weights or {}).items():
        if key.startswith("inv_"):
            stat_key = key[4:]
            score += float(weight) * (1.0 - float(norm.get(stat_key, 0.0)))
        else:
            score += float(weight) * float(norm.get(key, 0.0))
    return score


def _style_scores_from_final_stats(stats):
    hp = float((stats or {}).get("hp") or 0.0)
    atk = float((stats or {}).get("atk") or 0.0)
    defe = float((stats or {}).get("def") or 0.0)
    spd = float((stats or {}).get("spd") or 0.0)
    acc = float((stats or {}).get("acc") or 0.0)
    cri = float((stats or {}).get("cri") or 0.0)
    total = hp + atk + defe + spd + acc + cri
    if total <= 0:
        return None
    hp_n = hp / total
    atk_n = atk / total
    def_n = defe / total
    spd_n = spd / total
    acc_n = acc / total
    cri_n = cri / total
    norm = {"hp": hp_n, "atk": atk_n, "def": def_n, "spd": spd_n, "acc": acc_n, "cri": cri_n}
    scores = {style_key: _score_style_from_norm(norm, weights) for style_key, weights in ROBOT_STYLE_WEIGHTS.items()}
    return {
        "scores": scores,
        "norm": norm,
    }


def _robot_style_from_final_stats(stats):
    payload = _style_scores_from_final_stats(stats)
    if not payload:
        return {
            "style_key": "stable",
            "style_label": ROBOT_STYLE_LABELS["stable"],
            "style_description": _robot_style_description("stable"),
            "reason": "ステータス不足",
            "style_scores": {"stable": 0.0, "desperate": 0.0, "burst": 0.0},
            "legacy_build_type": "STABLE",
        }
    scores = payload["scores"]
    best = _pick_robot_style_key(scores)
    norm = payload["norm"]
    if best == "stable":
        reason = f"{_stat_label('def')} {norm['def']*100:.1f}% / {_stat_label('hp')} {norm['hp']*100:.1f}% が高い"
        legacy = "STABLE"
    elif best == "burst":
        reason = f"{_stat_label('atk')} {norm['atk']*100:.1f}% / {_stat_label('cri')} {norm['cri']*100:.1f}% が高い"
        legacy = "BURST"
    else:
        reason = f"低{_stat_label('hp')}傾向 {(1.0-norm['hp'])*100:.1f}% / {_stat_label('spd')} {norm['spd']*100:.1f}% が高い"
        legacy = "BURST"
    return {
        "style_key": best,
        "style_label": ROBOT_STYLE_LABELS[best],
        "style_description": _robot_style_description(best),
        "reason": reason,
        "style_scores": scores,
        "legacy_build_type": legacy,
    }


def _robot_style_from_instance_key(style_key):
    key = _normalize_style_key(style_key)
    return {
        "style_key": key,
        "style_label": ROBOT_STYLE_LABELS[key],
        "style_description": _robot_style_description(key),
        "reason": "出撃機体の型",
        "style_scores": {"stable": 0.0, "desperate": 0.0, "burst": 0.0},
        "legacy_build_type": ("STABLE" if key == "stable" else "BURST"),
    }


def _area_growth_tendency(area_key):
    return AREA_GROWTH_TENDENCY_DEFS.get(str(area_key or "").strip(), {})


def _area_weight_bias(area_key):
    tendency = _area_growth_tendency(area_key)
    bias = tendency.get("weight_bias") or {}
    return {str(k): float(v) for k, v in bias.items()}


def _robot_focus_stat_rows(stats, limit=2):
    stat_map = stats or {}
    pairs = [
        {"key": key, "label": _stat_label(key), "value": int(stat_map.get(key) or 0)}
        for key in ("hp", "atk", "def", "spd", "acc", "cri")
    ]
    pairs.sort(key=lambda item: (-int(item["value"]), item["label"]))
    return pairs[: max(1, int(limit or 2))]


def _robot_profile_view(stat_obj):
    stats = (stat_obj or {}).get("stats") or {}
    archetype = (stat_obj or {}).get("archetype") or {"key": "none", "name_ja": "無印"}
    robot_style = (
        (stat_obj or {}).get("robot_style")
        if stat_obj and (stat_obj or {}).get("robot_style")
        else _robot_style_from_final_stats(stats)
    )
    focus_stats = _robot_focus_stat_rows(stats, limit=2)
    signature_label = (
        f"{archetype['name_ja']} / {robot_style['style_label']}"
        if archetype.get("name_ja") and archetype.get("name_ja") != "無印"
        else f"{robot_style['style_label']}寄り"
    )
    focus_line = " / ".join(f"{row['label']} {row['value']}" for row in focus_stats)
    return {
        "archetype_name": archetype.get("name_ja") or "無印",
        "archetype_key": archetype.get("key") or "none",
        "style_label": robot_style.get("style_label") or ROBOT_STYLE_LABELS["stable"],
        "style_key": robot_style.get("style_key") or "stable",
        "style_description": robot_style.get("style_description") or _robot_style_description("stable"),
        "signature_label": signature_label,
        "focus_stats": focus_stats,
        "focus_line": focus_line,
    }


def _robot_metric_value(metric_key, stats):
    data = stats or {}
    key = str(metric_key or "").strip().lower()
    if key == "fastest":
        return int(data.get("spd") or 0)
    if key == "durable":
        return int(data.get("hp") or 0) + int(data.get("def") or 0)
    if key == "precision":
        return int(data.get("acc") or 0)
    if key == "burst":
        return int(data.get("atk") or 0) + int(data.get("cri") or 0)
    return 0


def _robot_metric_rows(db, metric_key, limit=50):
    metric = RANKING_METRIC_DEF_BY_KEY.get(metric_key) or RANKING_METRIC_DEF_BY_KEY["wins"]
    rows = db.execute(
        """
        SELECT ri.id, ri.user_id, ri.name, ri.composed_image_path, ri.updated_at, u.username
        FROM robot_instances ri
        JOIN users u ON u.id = ri.user_id
        WHERE ri.status = 'active'
        ORDER BY ri.updated_at DESC, ri.id DESC
        """
    ).fetchall()
    best_by_user = {}
    for row in rows:
        stat_obj = _compute_robot_stats_for_instance(db, int(row["id"]))
        if not stat_obj:
            continue
        metric_value = _robot_metric_value(metric_key, stat_obj.get("stats"))
        profile = _robot_profile_view(stat_obj)
        item = {
            "id": int(row["user_id"]),
            "user_id": int(row["user_id"]),
            "username": row["username"],
            "robot_id": int(row["id"]),
            "robot_name": (row["name"] or "無名ロボ"),
            "metric_value": int(metric_value),
            "image_url": _composed_image_url(row["composed_image_path"], row["updated_at"]),
            "profile": profile,
        }
        existing = best_by_user.get(item["user_id"])
        if existing is None or (
            int(item["metric_value"]),
            str(item["robot_name"]),
            -int(item["robot_id"]),
        ) > (
            int(existing["metric_value"]),
            str(existing["robot_name"]),
            -int(existing["robot_id"]),
        ):
            best_by_user[item["user_id"]] = item
    out = list(best_by_user.values())
    out.sort(key=lambda item: (-int(item["metric_value"]), str(item["username"]), str(item["robot_name"])))
    return out[: int(limit)], metric


def _enemy_tendency_tag(enemy):
    data = enemy or {}
    hp = float(data.get("hp") or 0.0)
    atk = float(data.get("atk") or 0.0)
    defe = float(data.get("def") or 0.0)
    spd = float(data.get("spd") or 0.0)
    acc = float(data.get("acc") or 0.0)
    cri = float(data.get("cri") or 0.0)
    total = hp + atk + defe + spd + acc + cri
    if total <= 0:
        return None
    norm = {
        "def": defe / total,
        "atk": atk / total,
        "cri": cri / total,
        "spd": spd / total,
        "acc": acc / total,
    }
    order = ("def", "atk", "cri", "spd", "acc")
    axis = order[0]
    best = norm[axis]
    for key in order[1:]:
        if norm[key] > best + 1e-12:
            axis = key
            best = norm[key]
    return ENEMY_TENDENCY_TAGS.get(axis)


def _normalize_enemy_trait(trait):
    key = (trait or "").strip().lower()
    return key if key in ENEMY_TRAIT_DEFS else None


def _enemy_trait_label(trait):
    key = _normalize_enemy_trait(trait)
    if not key:
        return None
    return ENEMY_TRAIT_DEFS[key]["label"]


def _enemy_trait_desc(trait):
    key = _normalize_enemy_trait(trait)
    if not key:
        return None
    return ENEMY_TRAIT_DEFS[key]["desc"]


def _damage_noise_range_for_build_type(build_type):
    if build_type == "BURST":
        return (0.80, 1.25)
    return (0.95, 1.05)


def _player_crit_multiplier_for_build_type(base_crit_multiplier, build_type):
    return float(base_crit_multiplier) * 1.15 if build_type == "BURST" else float(base_crit_multiplier)


def _build_profile_battle_line(build_type, damage_noise_range, player_crit_multiplier, base_crit_multiplier):
    build_label = BUILD_ARCHETYPE_LABELS.get(build_type, BUILD_ARCHETYPE_LABELS["NONE"])
    low, high = damage_noise_range
    cri_note = f"x{(float(player_crit_multiplier) / float(base_crit_multiplier)):.2f}"
    if build_type == "BERSERK":
        return f"ビルド: {build_label} / 乱数レンジ: {low:.2f}-{high:.2f} / { _stat_label('cri') }倍率補正: {cri_note} / 背水: 最大{ _stat_label('hp') }-15%"
    return f"ビルド: {build_label} / 乱数レンジ: {low:.2f}-{high:.2f} / { _stat_label('cri') }倍率補正: {cri_note}"


def _normalize_combat_mode(raw_mode):
    mode = (raw_mode or "").strip().lower()
    return "berserk" if mode == "berserk" else "normal"


def _resolve_build_type(stats):
    style = _robot_style_from_final_stats(stats)
    return str(style.get("legacy_build_type") or "STABLE").upper()


def _berserk_attack_bonus(build_type, hp_current, hp_max):
    if build_type != "BERSERK":
        return 0.0
    hp_max_safe = max(1, int(hp_max))
    missing = max(0.0, 1.0 - (float(max(0, int(hp_current))) / float(hp_max_safe)))
    return min(0.30, missing * 0.60)


def _attack_note(action, damage, detail, debug=False):
    if action == "行動不能":
        return "→ 行動不能"
    if int(damage) > 0:
        return None
    hit_pct = int(round(float(detail.get("hit_chance", 0.0)) * 100))
    bonus_pct = int(round(float(detail.get("hit_bonus", 0.0)) * 100))
    acc = int(detail.get("att_acc", 0))
    eva = int(detail.get("def_acc", 0))
    if not debug:
        if detail.get("miss", False):
            if (eva - acc) >= 6:
                return "→ MISS（相手が速い）"
            return "→ MISS（命中不足）"
        return "→ 0ダメ（装甲が硬い）"
    if detail.get("miss", False):
        return f"→ MISS（命中率 {hit_pct}% / {_stat_label('acc')} {acc} vs EVA {eva} / 補正 {bonus_pct:+d}%）"
    return f"→ 0ダメ（防御で軽減 / {_stat_label('acc')} {acc} vs EVA {eva}）"


def _has_area_boss_candidates(db, area_key):
    if not _area_supports_boss_alert(area_key):
        return False
    boss_area_key = _boss_area_key_for_route(area_key)
    row = db.execute(
        """
        SELECT 1
        FROM enemies
        WHERE is_active = 1
          AND COALESCE(is_boss, 0) = 1
          AND boss_area_key = ?
        LIMIT 1
        """,
        (boss_area_key,),
    ).fetchone()
    if row:
        return True
    if boss_area_key in NPC_BOSS_ALLOWED_AREAS:
        npc_row = db.execute(
            "SELECT 1 FROM npc_boss_templates WHERE is_active = 1 AND boss_area_key = ? LIMIT 1",
            (boss_area_key,),
        ).fetchone()
        return bool(npc_row)
    return False


def _ensure_user_boss_progress_row(db, user_id, area_key):
    row = db.execute(
        """
        SELECT no_boss_streak
        FROM user_boss_progress
        WHERE user_id = ? AND area_key = ?
        """,
        (user_id, area_key),
    ).fetchone()
    if row:
        return int(row["no_boss_streak"] or 0)
    db.execute(
        """
        INSERT INTO user_boss_progress (user_id, area_key, no_boss_streak, active_boss_enemy_id, boss_attempts_left, boss_alert_expires_at, updated_at)
        VALUES (?, ?, 0, NULL, 0, NULL, ?)
        """,
        (user_id, area_key, int(time.time())),
    )
    return 0


def _get_boss_enemy_by_id(db, enemy_id):
    if enemy_id is None:
        return None
    if _is_npc_boss_alert_id(enemy_id):
        template_id = _decode_npc_boss_alert_id(enemy_id)
        if not template_id:
            return None
        row = db.execute(
            "SELECT * FROM npc_boss_templates WHERE id = ? AND is_active = 1 LIMIT 1",
            (int(template_id),),
        ).fetchone()
        return _build_npc_boss_enemy_payload(row)
    row = db.execute(
        """
        SELECT *
        FROM enemies
        WHERE id = ?
          AND is_active = 1
          AND COALESCE(is_boss, 0) = 1
        """,
        (int(enemy_id),),
    ).fetchone()
    if not row:
        return None
    payload = dict(row)
    payload["_boss_kind"] = "fixed"
    payload["_alert_enemy_id"] = int(row["id"])
    return payload


def _clear_boss_alert(db, user_id, area_key, now_ts=None):
    ts = int(time.time()) if now_ts is None else int(now_ts)
    db.execute(
        """
        UPDATE user_boss_progress
        SET active_boss_enemy_id = NULL,
            boss_attempts_left = 0,
            boss_alert_expires_at = NULL,
            updated_at = ?
        WHERE user_id = ? AND area_key = ?
        """,
        (ts, user_id, area_key),
    )


def _activate_boss_alert(db, user_id, area_key, enemy_id, now_ts=None, attempts=None, duration_minutes=None):
    ts = int(time.time()) if now_ts is None else int(now_ts)
    tries = int(AREA_BOSS_ALERT_ATTEMPTS if attempts is None else attempts)
    minutes = int(AREA_BOSS_ALERT_MINUTES if duration_minutes is None else duration_minutes)
    expires_at = ts + max(1, minutes) * 60
    db.execute(
        """
        INSERT INTO user_boss_progress
        (user_id, area_key, no_boss_streak, active_boss_enemy_id, boss_attempts_left, boss_alert_expires_at, updated_at)
        VALUES (?, ?, 0, ?, ?, ?, ?)
        ON CONFLICT(user_id, area_key) DO UPDATE
        SET active_boss_enemy_id = excluded.active_boss_enemy_id,
            boss_attempts_left = excluded.boss_attempts_left,
            boss_alert_expires_at = excluded.boss_alert_expires_at,
            updated_at = excluded.updated_at
        """,
        (user_id, area_key, int(enemy_id), max(0, tries), int(expires_at), ts),
    )
    return {
        "enemy_id": int(enemy_id),
        "attempts_left": max(0, tries),
        "expires_at": int(expires_at),
    }


def _get_active_boss_alert(db, user_id, area_key, now_ts=None):
    ts = int(time.time()) if now_ts is None else int(now_ts)
    row = db.execute(
        """
        SELECT active_boss_enemy_id, boss_attempts_left, boss_alert_expires_at
        FROM user_boss_progress
        WHERE user_id = ? AND area_key = ?
        """,
        (user_id, area_key),
    ).fetchone()
    if not row:
        return None
    enemy_id = row["active_boss_enemy_id"]
    attempts_left = int(row["boss_attempts_left"] or 0)
    expires_at = int(row["boss_alert_expires_at"] or 0)
    if not enemy_id or attempts_left <= 0 or expires_at <= ts:
        if enemy_id or attempts_left > 0 or expires_at > 0:
            _clear_boss_alert(db, user_id, area_key, now_ts=ts)
        return None
    enemy = _get_boss_enemy_by_id(db, enemy_id)
    if enemy is None:
        _clear_boss_alert(db, user_id, area_key, now_ts=ts)
        return None
    return {
        "enemy_id": int(enemy_id),
        "attempts_left": attempts_left,
        "expires_at": expires_at,
        "enemy": enemy,
    }


def _consume_boss_attempt(db, user_id, area_key, now_ts=None):
    ts = int(time.time()) if now_ts is None else int(now_ts)
    row = db.execute(
        """
        SELECT boss_attempts_left
        FROM user_boss_progress
        WHERE user_id = ? AND area_key = ?
        """,
        (user_id, area_key),
    ).fetchone()
    before = int(row["boss_attempts_left"] or 0) if row else 0
    after = max(0, before - 1)
    db.execute(
        """
        UPDATE user_boss_progress
        SET boss_attempts_left = ?,
            active_boss_enemy_id = CASE WHEN ? <= 0 THEN NULL ELSE active_boss_enemy_id END,
            boss_alert_expires_at = CASE WHEN ? <= 0 THEN NULL ELSE boss_alert_expires_at END,
            updated_at = ?
        WHERE user_id = ? AND area_key = ?
        """,
        (after, after, after, ts, user_id, area_key),
    )
    return {"before": before, "after": after}


def _area_boss_spawn_profile(area_key, streak_before):
    boss_progress_key = _boss_area_key_for_route(area_key)
    base_probability = float(AREA_BOSS_SPAWN_RATES.get(area_key, 0.1))
    pity_misses = int(
        AREA_BOSS_PITY_MISSES.get(
            boss_progress_key,
            AREA_BOSS_PITY_MISSES.get(area_key, 9),
        )
    )
    soft_start = int(
        AREA_BOSS_SOFT_PITY_STARTS.get(
            boss_progress_key,
            AREA_BOSS_SOFT_PITY_STARTS.get(area_key, pity_misses),
        )
    )
    soft_cap = float(
        AREA_BOSS_SOFT_PITY_MAX_RATES.get(
            boss_progress_key,
            AREA_BOSS_SOFT_PITY_MAX_RATES.get(area_key, base_probability),
        )
    )
    probability = float(base_probability)
    misses = max(0, int(streak_before))
    if soft_start < pity_misses and soft_cap > base_probability and misses >= soft_start:
        progress = _clamp((misses - soft_start + 1) / float(max(1, pity_misses - soft_start)), 0.0, 1.0)
        probability = float(base_probability + (soft_cap - base_probability) * progress)
    return {
        "probability": float(_clamp(probability, base_probability, 1.0)),
        "pity_misses": int(pity_misses),
        "soft_start": int(soft_start),
        "progress_key": boss_progress_key,
    }


def _area_boss_spawn_check(db, user_id, area_key, rng=None):
    if not _area_supports_boss_alert(area_key) or not _has_area_boss_candidates(db, area_key):
        return {"spawn": False, "probability": 0.0, "pity_forced": False, "streak_before": 0}
    roller = rng or random
    streak_before = _ensure_user_boss_progress_row(db, user_id, area_key)
    spawn_profile = _area_boss_spawn_profile(area_key, streak_before)
    pity_misses = int(spawn_profile["pity_misses"])
    spawn_p = float(spawn_profile["probability"])
    pity_forced = streak_before >= max(0, pity_misses - 1)
    spawned = pity_forced or (roller.random() < spawn_p)
    # streakはボス遭遇で0、通常探索（非ボス）で+1。報酬付与は撃破時のみ別処理で行う。
    next_streak = 0 if spawned else (streak_before + 1)
    db.execute(
        """
        INSERT INTO user_boss_progress (user_id, area_key, no_boss_streak, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, area_key) DO UPDATE
        SET no_boss_streak = excluded.no_boss_streak,
            updated_at = excluded.updated_at
        """,
        (user_id, area_key, int(next_streak), int(time.time())),
    )
    return {
        "spawn": bool(spawned),
        "probability": float(spawn_p),
        "pity_forced": bool(pity_forced),
        "streak_before": int(streak_before),
    }


def _pick_boss_enemy_for_area(db, area_key, weekly_env=None, rng=None):
    roller = rng or random
    boss_area_key = _boss_area_key_for_route(area_key)
    rows = db.execute(
        """
        SELECT *
        FROM enemies
        WHERE is_active = 1
          AND COALESCE(is_boss, 0) = 1
          AND boss_area_key = ?
        ORDER BY id ASC
        """,
        (boss_area_key,),
    ).fetchall()
    if not rows:
        return None
    if not weekly_env:
        return roller.choice(rows)
    env_element = (weekly_env.get("element") or "").upper()
    bonus = float(weekly_env.get("enemy_spawn_bonus") or 0.0)
    weights = []
    for row in rows:
        w = 1.0
        if (row["element"] or "").upper() == env_element:
            w += bonus
        weights.append(w)
    return roller.choices(rows, weights=weights, k=1)[0]


def _pick_layer_boss_enemy(db, area_key, weekly_env=None, rng=None):
    roller = rng or random
    layer = _area_layer(area_key)
    boss_key = LAYER_BOSS_KEY_BY_LAYER.get(layer)
    fixed_payload = None
    if boss_key:
        fixed_row = db.execute(
            """
            SELECT *
            FROM enemies
            WHERE is_active = 1
              AND COALESCE(is_boss, 0) = 1
              AND key = ?
            LIMIT 1
            """,
            (boss_key,),
        ).fetchone()
        if fixed_row:
            fixed_payload = dict(fixed_row)
            fixed_payload["_boss_kind"] = "fixed"
            fixed_payload["_alert_enemy_id"] = int(fixed_row["id"])
    if fixed_payload is None:
        fallback = _pick_boss_enemy_for_area(db, area_key, weekly_env=weekly_env, rng=roller)
        if fallback:
            fixed_payload = dict(fallback)
            fixed_payload["_boss_kind"] = "fixed"
            fixed_payload["_alert_enemy_id"] = int(fallback["id"])
    # Fixed boss is always the default. NPC is an additive variant for layer_2/3 only.
    if fixed_payload is not None:
        if (not app.config.get("TESTING")) and area_key in NPC_BOSS_ALLOWED_AREAS and roller.random() < float(NPC_BOSS_PICK_RATE):
            npc_payload = pick_npc_boss_for_area(db, area_key)
            if npc_payload:
                return npc_payload
        return fixed_payload
    npc_payload = pick_npc_boss_for_area(db, area_key)
    if npc_payload:
        return npc_payload
    return None


def _count_user_explore_end_in_areas(db, user_id, area_keys):
    keys = [str(k).strip() for k in (area_keys or ()) if str(k).strip()]
    if not keys:
        return 0
    placeholders = ",".join(["?"] * len(keys))
    row = db.execute(
        f"""
        SELECT COUNT(*) AS c
        FROM world_events_log
        WHERE user_id = ?
          AND event_type = ?
          AND COALESCE(json_extract(payload_json, '$.area_key'), '') IN ({placeholders})
        """,
        [int(user_id), AUDIT_EVENT_TYPES["EXPLORE_END"], *keys],
    ).fetchone()
    return int((row["c"] if row else 0) or 0)


def _maybe_unlock_next_layer(db, user_id, user_row, area_key, enemy_row):
    current_layer = _area_layer(area_key)
    max_layer = _user_max_unlocked_layer(user_row)
    if current_layer != max_layer or max_layer >= MAX_UNLOCKABLE_LAYER:
        return None
    enemy_key = ((enemy_row.get("key") if isinstance(enemy_row, dict) else enemy_row["key"]) or "").strip()
    expected_boss_key = None
    if area_key == LAYER4_FINAL_AREA_KEY:
        expected_boss_key = "boss_4_final_ark_zero"
    else:
        expected_boss_key = LAYER_BOSS_KEY_BY_LAYER.get(current_layer)
    if not expected_boss_key or enemy_key != expected_boss_key:
        return None
    if current_layer == 2:
        layer2_sorties = _count_user_explore_end_in_areas(db, user_id, LAYER2_FAMILY_AREA_KEYS)
        if area_key in LAYER2_FAMILY_AREA_KEYS:
            layer2_sorties += 1
        if layer2_sorties < int(LAYER3_UNLOCK_LAYER2_SORTIES_REQUIRED):
            return None
    unlocked_layer = max_layer + 1
    db.execute(
        "UPDATE users SET max_unlocked_layer = ?, layer2_unlocked = CASE WHEN ? >= 2 THEN 1 ELSE layer2_unlocked END WHERE id = ?",
        (int(unlocked_layer), int(unlocked_layer), user_id),
    )
    return int(unlocked_layer)


def _grant_boss_decor_reward(db, user_id, area_key):
    reward_area_key = _boss_reward_area_key(area_key)
    keys = AREA_BOSS_DECOR_REWARD_KEYS.get(reward_area_key, [])
    if not keys:
        return {
            "reward_missing": True,
            "missing_keys": [],
            "decor_asset_id": None,
            "decor_key": None,
            "decor_name": None,
            "decor_image_path": None,
            "granted": False,
        }
    placeholders = ",".join(["?"] * len(keys))
    rows = db.execute(
        f"""
        SELECT id, key, name_ja, image_path
        FROM robot_decor_assets
        WHERE is_active = 1 AND key IN ({placeholders})
        ORDER BY id ASC
        """,
        list(keys),
    ).fetchall()
    found_keys = {row["key"] for row in rows}
    missing_keys = [k for k in keys if k not in found_keys]
    if not rows:
        return {
            "reward_missing": True,
            "missing_keys": missing_keys,
            "decor_asset_id": None,
            "decor_key": None,
            "decor_name": None,
            "decor_image_path": None,
            "granted": False,
        }
    decor = random.choice(rows)
    now_ts = int(time.time())
    inserted = db.execute(
        """
        INSERT OR IGNORE INTO user_decor_inventory (user_id, decor_asset_id, acquired_at)
        VALUES (?, ?, ?)
        """,
        (user_id, int(decor["id"]), now_ts),
    ).rowcount > 0
    return {
        "reward_missing": False,
        "missing_keys": missing_keys,
        "decor_asset_id": int(decor["id"]),
        "decor_key": decor["key"],
        "decor_name": decor["name_ja"],
        "decor_image_path": decor["image_path"],
        "granted": bool(inserted),
    }


def _seed_default_decor_assets(db):
    now_ts = int(time.time())
    seeds = [
        ("boss_emblem_aurix", "オリクス紋章", "decor/aurix.png"),
        ("boss_emblem_ventra", "ヴェントラ紋章", "decor/ventra.png"),
        ("boss_emblem_ignis", "イグニス紋章", "decor/ignis.png"),
        ("fortress_badge_001", "要塞勲章", "decor/fortress_badge_001.png"),
        ("mist_scope_001", "霧界スコープ", "decor/mist_scope_001.png"),
        ("burst_reactor_001", "暴核リアクター", "decor/burst_reactor_001.png"),
        ("judge_halo_001", "審判ハロー", "decor/judge_halo_001.png"),
        ("nyx_array_crest_001", "観測群冠", "decor/nyx_array_crest_001.png"),
        ("ignition_crown_001", "覇走冠", "decor/ignition_crown_001.png"),
        ("omega_frame_halo_001", "終機輪", "decor/omega_frame_halo_001.png"),
        (SUPPORT_PACK_DECOR_KEY, "支援者トロフィー", "decor/aurix_trophy.png"),
    ]
    for key, name_ja, image_path in seeds:
        db.execute(
            """
            INSERT INTO robot_decor_assets (key, name_ja, image_path, is_active, created_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(key) DO UPDATE SET
                name_ja = excluded.name_ja,
                image_path = excluded.image_path
            """,
            (key, name_ja, (image_path or DECOR_PLACEHOLDER_REL), now_ts),
        )


def _seed_core_definitions(db):
    now_ts = int(time.time())
    db.execute(
        """
        INSERT INTO core_assets (core_key, name_ja, description, icon_path, is_active, created_at)
        VALUES (?, ?, ?, ?, 1, ?)
        ON CONFLICT(core_key) DO UPDATE SET
            name_ja = excluded.name_ja,
            description = excluded.description,
            icon_path = excluded.icon_path
        """,
        (
            EVOLUTION_CORE_KEY,
            "進化コア",
            "パーツを上位レアリティへ進化させる未知のコア",
            "images/cores/evolution_core.png",
            now_ts,
        ),
    )


def _seed_lab_casino_prizes(db):
    now_ts = int(time.time())
    for seed in LAB_CASINO_PRIZE_SEEDS:
        db.execute(
            """
            INSERT INTO lab_casino_prizes
            (prize_key, name, description, cost_lab_coin, prize_type, grant_key, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(prize_key) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                cost_lab_coin = excluded.cost_lab_coin,
                prize_type = excluded.prize_type,
                grant_key = excluded.grant_key,
                is_active = 1,
                updated_at = excluded.updated_at
            """,
            (
                seed["prize_key"],
                seed["name"],
                seed.get("description"),
                int(seed["cost_lab_coin"]),
                seed["prize_type"],
                seed.get("grant_key"),
                now_ts,
                now_ts,
            ),
        )


def _warn_missing_boss_decor_keys(db):
    global BOSS_DECOR_WARNING_EMITTED
    if BOSS_DECOR_WARNING_EMITTED:
        return
    configured = {}
    for area_key, keys in AREA_BOSS_DECOR_REWARD_KEYS.items():
        configured[area_key] = [k for k in keys if k]
    all_keys = sorted({k for keys in configured.values() for k in keys})
    if not all_keys:
        return
    placeholders = ",".join(["?"] * len(all_keys))
    rows = db.execute(
        f"SELECT key FROM robot_decor_assets WHERE key IN ({placeholders})",
        all_keys,
    ).fetchall()
    existing = {row["key"] for row in rows}
    missing_by_area = {}
    for area_key, keys in configured.items():
        missing = [k for k in keys if k not in existing]
        if missing:
            missing_by_area[area_key] = missing
    if missing_by_area:
        app.logger.warning("AREA_BOSS_DECOR_REWARD_KEYS missing in robot_decor_assets: %s", missing_by_area)
    BOSS_DECOR_WARNING_EMITTED = True


def _normalize_world_mode(raw_mode):
    mode = (raw_mode or "").strip()
    if mode in WORLD_MODES:
        return mode
    low = mode.lower()
    if low in WORLD_MODE_LEGACY_MAP:
        return WORLD_MODE_LEGACY_MAP[low]
    return "安定"


def _world_counter_inc(db, week_key, metric_key, delta=1):
    db.execute(
        """
        INSERT INTO world_weekly_counters (week_key, metric_key, value)
        VALUES (?, ?, ?)
        ON CONFLICT(week_key, metric_key) DO UPDATE SET value = value + excluded.value
        """,
        (week_key, metric_key, int(delta)),
    )


def _world_counter_get(db, week_key, metric_key):
    row = db.execute(
        "SELECT value FROM world_weekly_counters WHERE week_key = ? AND metric_key = ?",
        (week_key, metric_key),
    ).fetchone()
    return int(row["value"]) if row else 0


def _world_current_environment(db):
    row = _ensure_world_week_environment(db)
    if not row:
        return None
    data = dict(row)
    normalized = _normalize_world_mode(data.get("mode"))
    if normalized != data.get("mode"):
        db.execute(
            "UPDATE world_weekly_environment SET mode = ? WHERE id = ?",
            (normalized, data["id"]),
        )
        db.commit()
        data["mode"] = normalized
    return data


def _build_element_from_keys(db, head_key, r_arm_key, l_arm_key, legs_key):
    keys = [head_key, r_arm_key, l_arm_key, legs_key]
    rows = db.execute(
        "SELECT key, element FROM robot_parts WHERE key IN (?, ?, ?, ?)",
        keys,
    ).fetchall()
    elem_map = {r["key"]: (r["element"] or "NORMAL").upper() for r in rows}
    elems = [elem_map.get(k, "NORMAL") for k in keys]
    if len(set(elems)) == 1:
        return elems[0]
    return "MIXED"


def _world_recommendation(element, mode):
    key = f"{element}:{mode}"
    table = {
        "WIND:暴走": "命中重視で安定。連戦に備えてACC高め。",
        "FIRE:暴走": "短期決戦向け。ATK高めで押し切り推奨。",
        "WATER:活性": "速度重視で回転率を上げる週。",
        "THUNDER:活性": "クリティカル寄りの構成が刺さりやすい。",
        "NORMAL:安定": "初心者向け週。バランス型で試行回数を増やす。",
        "ICE:静穏": "防御寄りの研究週。敗北ペナルティが軽い。",
        "STEEL:静穏": "耐久検証に最適。防御ビルドの比較推奨。",
    }
    return table.get(key, f"{mode}週。{element}軸のビルド検証に向いています。")


def _world_effect_summary_lines(weekly_env):
    if not weekly_env:
        return []
    lines = []
    spawn_bonus = float(weekly_env.get("enemy_spawn_bonus") or 0.0)
    drop_bonus = float(weekly_env.get("drop_bonus") or 0.0)
    if spawn_bonus > 0:
        lines.append("NORMAL敵 出現率↑")
    if drop_bonus > 0:
        lines.append("ドロップ率↑")
    if not lines:
        lines.append("補正なし")
    return lines


def _element_to_faction(element):
    elem = (element or "").upper()
    if elem in {"THUNDER", "WIND"}:
        return "ventra"
    if elem in {"FIRE", "ICE"}:
        return "ignis"
    return "aurix"


def _build_battle_reward_front(*, reward_coin, reward_core, dropped_core_name, drop_items):
    drops = []
    part_rows = []
    if int(reward_core or 0) > 0:
        core_name = (dropped_core_name or "進化コア").strip() or "進化コア"
        drops.append(f"{core_name} ×{int(reward_core)}")
    drop_counter = Counter()
    part_row_map = {}
    for item in (drop_items or []):
        name = (item.get("part_display_name") or item.get("part_key") or "不明パーツ").strip()
        plus = int(item.get("plus") or 0)
        storage_suffix = "（保管）" if str(item.get("storage_status") or "").strip().lower() == "overflow" else ""
        label = f"{name} +{plus}{storage_suffix}"
        drop_counter[label] += 1
        row_key = (
            item.get("part_key") or name,
            plus,
            storage_suffix,
            item.get("image_url") or "",
            name,
        )
        if row_key not in part_row_map:
            part_row_map[row_key] = {
                "label": label,
                "image_url": item.get("image_url"),
                "count": 0,
            }
        part_row_map[row_key]["count"] += 1
    for label, count in drop_counter.items():
        if count > 1:
            drops.append(f"{label} ×{count}")
        else:
            drops.append(label)
    for row in part_row_map.values():
        part_rows.append(row)
    if not drops:
        drops.append("戦利品なし")
    return {
        "coin": int(reward_coin or 0),
        "drops": drops,
        "part_rows": part_rows,
    }


def _extract_part_extreme_title(part_instance):
    if not part_instance:
        return None
    weights = {
        "atk": float(part_instance.get("w_atk") or 0.0),
        "spd": float(part_instance.get("w_spd") or 0.0),
        "def": float(part_instance.get("w_def") or 0.0),
        "acc": float(part_instance.get("w_acc") or 0.0),
        "cri": float(part_instance.get("w_cri") or 0.0),
        "hp": float(part_instance.get("w_hp") or 0.0),
    }
    top_key = max(weights, key=weights.get)
    top_val = weights[top_key]
    if top_key == "atk" and top_val >= 0.45:
        return "破壊型"
    if top_key == "spd" and top_val >= 0.40:
        return "疾風型"
    if top_key == "def" and top_val >= 0.40:
        return "鉄壁型"
    if top_key == "acc" and top_val >= 0.42:
        return "狙撃型"
    if top_key == "cri" and top_val >= 0.32:
        return "豪運型"
    return None


def _maybe_post_research_title(db, user_id, username, part_instance):
    title = _extract_part_extreme_title(part_instance)
    if not title:
        return
    day_key = datetime.now(JST).strftime("%Y-%m-%d")
    once_key = f"title_posted:{user_id}:{day_key}"
    seen = db.execute(
        "SELECT 1 FROM world_events_log WHERE event_type = 'daily_title_posted' AND payload_json LIKE ? LIMIT 1",
        (f'%"{once_key}"%',),
    ).fetchone()
    if seen:
        return
    message = f"『{title}』パーツが発見された！ ({username})"
    db.execute(
        "INSERT INTO chat_messages (user_id, username, message, created_at) VALUES (?, ?, ?, ?)",
        (user_id, "SYSTEM", message, now_str()),
    )
    _world_event_log(
        db,
        "daily_title_posted",
        {"once_key": once_key, "user_id": user_id, "title": title},
    )


def _world_choose_next_environment(db, week_key, influence_ratio=0.30):
    elements = [code for code, _ in ELEMENTS]
    prev_start = _world_week_bounds(week_key)[0] - timedelta(days=7)
    prev_key = _world_week_key(prev_start.timestamp())

    kills_raw = {e: _world_counter_get(db, prev_key, f"kills_{e}") for e in elements}
    builds_raw = {e: _world_counter_get(db, prev_key, f"builds_{e}") for e in elements}
    kills_sum = sum(kills_raw.values())
    builds_sum = sum(builds_raw.values())

    kills_norm = {e: (kills_raw[e] / kills_sum) if kills_sum > 0 else 0.0 for e in elements}
    builds_norm = {e: (builds_raw[e] / builds_sum) if builds_sum > 0 else 0.0 for e in elements}
    influence = {e: kills_norm[e] * 0.6 + builds_norm[e] * 0.4 for e in elements}

    random_scores = {e: random.random() for e in elements}
    random_total = sum(random_scores.values()) or 1.0
    random_norm = {e: random_scores[e] / random_total for e in elements}
    final_weights = {
        e: ((1.0 - influence_ratio) * random_norm[e]) + (influence_ratio * influence[e])
        for e in elements
    }
    chosen = random.choices(elements, weights=[final_weights[e] for e in elements], k=1)[0]
    mode = random.choice(["暴走", "活性", "安定", "静穏"])
    config = WORLD_MODES[mode]

    kills_top = sorted(kills_raw.items(), key=lambda x: x[1], reverse=True)[:2]
    builds_top = sorted(builds_raw.items(), key=lambda x: x[1], reverse=True)[:1]
    kills_top_txt = ", ".join(f"{k}:{v}" for k, v in kills_top if v > 0) or "データなし"
    builds_top_txt = ", ".join(f"{k}:{v}" for k, v in builds_top if v > 0) or "データなし"
    reason = (
        f"ランダム70% + 影響30% / 前週撃破上位={kills_top_txt} / "
        f"前週組立上位={builds_top_txt} / 世界状態={mode}"
    )
    return {
        "element": chosen,
        "mode": mode,
        "enemy_spawn_bonus": config["enemy_spawn_bonus"],
        "drop_bonus": config["drop_bonus"],
        "influence_ratio": influence_ratio,
        "reason": reason,
        "random_seed": random.randint(1, 2_147_483_647),
        "payload": {
            "week_key": week_key,
            "kills_raw": kills_raw,
            "builds_raw": builds_raw,
            "final_weights": final_weights,
            "chosen_element": chosen,
            "mode": mode,
        },
    }


def _ensure_world_week_environment(db):
    current_key = _world_week_key()
    row = db.execute(
        "SELECT * FROM world_weekly_environment WHERE week_key = ?",
        (current_key,),
    ).fetchone()
    if row:
        return row
    env = _world_choose_next_environment(db, current_key, influence_ratio=0.30)
    start, end = _world_week_bounds(current_key)
    cur = db.execute(
        """
        INSERT OR IGNORE INTO world_weekly_environment
        (week_key, element, mode, enemy_spawn_bonus, drop_bonus, started_at, ends_at, random_seed, influence_ratio, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            current_key,
            env["element"],
            env["mode"],
            env["enemy_spawn_bonus"],
            env["drop_bonus"],
            int(start.timestamp()),
            int(end.timestamp()),
            env["random_seed"],
            env["influence_ratio"],
            env["reason"],
        ),
    )
    if cur.rowcount > 0:
        research_result = _advance_world_research(db, current_key)
        rollover_payload = dict(env["payload"])
        rollover_payload["research"] = research_result
        _world_event_log(db, "week_rollover", rollover_payload)
        msg = (
            f"今週の戦況: {env['mode']}（属性: {env['element']}）。"
            f" 理由: {env['reason']}"
        )
        db.execute(
            "INSERT INTO chat_messages (user_id, username, message, created_at) VALUES (?, ?, ?, ?)",
            (0, "SYSTEM", msg[:200], now_str()),
        )
        db.commit()
    return db.execute(
        "SELECT * FROM world_weekly_environment WHERE week_key = ?",
        (current_key,),
    ).fetchone()


def _world_weekly_trends(db, week_key, limit=3):
    rows = db.execute(
        """
        SELECT metric_key, value
        FROM world_weekly_counters
        WHERE week_key = ? AND metric_key LIKE 'builds_%'
        ORDER BY value DESC, metric_key ASC
        LIMIT ?
        """,
        (week_key, limit),
    ).fetchall()
    trends = []
    for r in rows:
        metric_key = r["metric_key"]
        element = metric_key.replace("builds_", "")
        trends.append({"element": element, "value": int(r["value"])})
    return trends


def _world_research_progress_rows(db):
    _ensure_world_research_rows(db)
    rows = db.execute(
        """
        SELECT element, progress, unlocked_stage, updated_at
        FROM world_research_progress
        ORDER BY element ASC
        """
    ).fetchall()
    items = []
    for r in rows:
        stage = int(r["unlocked_stage"] or 0)
        next_part = _research_part_type_for_stage(stage + 1) if stage < len(RESEARCH_UNLOCK_ORDER) else None
        items.append(
            {
                "element": r["element"],
                "progress": int(r["progress"] or 0),
                "unlocked_stage": stage,
                "next_part_type": next_part,
                "updated_at": int(r["updated_at"] or 0),
            }
        )
    return items


def _home_research_summary(db, current_week_key):
    row = db.execute(
        """
        SELECT id, payload_json
        FROM world_events_log
        WHERE event_type = 'RESEARCH_ADVANCE'
          AND payload_json LIKE ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (f'%"week_key": "{current_week_key}"%',),
    ).fetchone()
    winner_element = None
    if row and row["payload_json"]:
        try:
            payload = json.loads(row["payload_json"])
            winner_element = (payload.get("winner_element") or "").upper() or None
        except Exception:
            winner_element = None
    progress = 0
    unlocked_stage = 0
    if winner_element:
        p_row = db.execute(
            """
            SELECT progress, unlocked_stage
            FROM world_research_progress
            WHERE element = ?
            """,
            (winner_element,),
        ).fetchone()
        if p_row:
            progress = int(p_row["progress"] or 0)
            unlocked_stage = int(p_row["unlocked_stage"] or 0)
    next_part_type = _research_part_type_for_stage(unlocked_stage + 1) if unlocked_stage < len(RESEARCH_UNLOCK_ORDER) else None
    faction_key = _element_to_faction(winner_element) if winner_element else None
    icon_path = FACTION_EMBLEMS.get(faction_key) if faction_key else None
    return {
        "current_research_element": winner_element,
        "progress": progress,
        "unlocked_stage": unlocked_stage,
        "next_part_type": next_part_type,
        "icon_path": icon_path,
    }


def _home_research_unlock_banner(db, current_week_key):
    row = db.execute(
        """
        SELECT id, payload_json
        FROM world_events_log
        WHERE event_type = 'RESEARCH_UNLOCK'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except Exception:
        return None
    if payload.get("week_key") != current_week_key:
        return None
    if int(session.get("home_seen_research_unlock_id") or 0) >= int(row["id"]):
        return None
    session["home_seen_research_unlock_id"] = int(row["id"])
    part_type = str(payload.get("part_type") or "").strip().upper()
    part_label = RESEARCH_PART_TYPE_LABELS_JA.get(part_type)
    if part_label:
        line_1 = f"{part_label}の設計が解放されました！"
        line_2 = f"これから出撃で{part_label}が見つかるかもしれません。"
    else:
        line_1 = "新しいパーツ設計が解放されました！"
        line_2 = "これから出撃で見つかるかもしれません。"
    return {
        "line_1": line_1,
        "line_2": line_2,
        "part_type": part_type,
        "part_label": part_label,
    }


def ensure_schema(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_bases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            image_path TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_type TEXT NOT NULL,
            key TEXT UNIQUE NOT NULL,
            image_path TEXT NOT NULL,
            rarity TEXT,
            element TEXT,
            series TEXT,
            display_name_ja TEXT,
            offset_x INTEGER NOT NULL DEFAULT 0,
            offset_y INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            is_unlocked INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_builds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            base_key TEXT,
            head_key TEXT,
            r_arm_key TEXT,
            l_arm_key TEXT,
            legs_key TEXT,
            composed_image_path TEXT,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS base_bodies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sprite_path TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            sprite_path TEXT NOT NULL,
            attack INTEGER NOT NULL,
            defense INTEGER NOT NULL,
            speed INTEGER NOT NULL,
            hp INTEGER NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS robots_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            head TEXT NOT NULL,
            right_arm TEXT NOT NULL,
            left_arm TEXT NOT NULL,
            legs TEXT NOT NULL,
            name TEXT,
            rarity TEXT,
            type TEXT,
            flavor_text TEXT,
            attack INTEGER,
            defense INTEGER,
            rarity_bonus INTEGER
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_robots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            head TEXT NOT NULL,
            right_arm TEXT NOT NULL,
            left_arm TEXT NOT NULL,
            legs TEXT NOT NULL,
            obtained_at INTEGER NOT NULL,
            master_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS release_flags (
            key TEXT PRIMARY KEY,
            is_public INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    cols = {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}
    if "is_admin" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
    if "wins" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN wins INTEGER NOT NULL DEFAULT 0")
    if "click_power" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN click_power INTEGER NOT NULL DEFAULT 1")
    if "total_clicks" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN total_clicks INTEGER NOT NULL DEFAULT 0")
    if "robot_slot_limit" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN robot_slot_limit INTEGER NOT NULL DEFAULT 3")
    if "part_inventory_limit" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN part_inventory_limit INTEGER NOT NULL DEFAULT 60")
    if "avatar_path" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN avatar_path TEXT")
    if "active_robot_id" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN active_robot_id INTEGER")
    if "battle_log_mode" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN battle_log_mode TEXT NOT NULL DEFAULT 'collapsed'")
    if "boss_meter_explore_l1" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN boss_meter_explore_l1 INTEGER NOT NULL DEFAULT 0")
    if "boss_meter_win_l1" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN boss_meter_win_l1 INTEGER NOT NULL DEFAULT 0")
    if "layer2_unlocked" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN layer2_unlocked INTEGER NOT NULL DEFAULT 0")
    if "max_unlocked_layer" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN max_unlocked_layer INTEGER NOT NULL DEFAULT 1")
    if "home_axis_hint_seen" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN home_axis_hint_seen INTEGER NOT NULL DEFAULT 0")
    if "stable_no_damage_wins" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN stable_no_damage_wins INTEGER NOT NULL DEFAULT 0")
    if "burst_crit_finisher_kills" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN burst_crit_finisher_kills INTEGER NOT NULL DEFAULT 0")
    if "desperate_low_hp_wins" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN desperate_low_hp_wins INTEGER NOT NULL DEFAULT 0")
    if "faction" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN faction TEXT")
    if "last_seen_at" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN last_seen_at INTEGER NOT NULL DEFAULT 0")
    if "invite_code" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN invite_code TEXT")
    if "is_banned" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER NOT NULL DEFAULT 0")
    if "is_admin_protected" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN is_admin_protected INTEGER NOT NULL DEFAULT 0")
    if "banned_at" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN banned_at TEXT")
    if "banned_reason" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN banned_reason TEXT")
    if "banned_by_user_id" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN banned_by_user_id INTEGER")
    if "has_seen_intro_modal" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN has_seen_intro_modal INTEGER NOT NULL DEFAULT 0")
    if "intro_guide_closed_at" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN intro_guide_closed_at TEXT")
    if "last_explore_area_key" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN last_explore_area_key TEXT")
    if "explore_boost_until" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN explore_boost_until INTEGER NOT NULL DEFAULT 0")
    if "evolution_core_progress" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN evolution_core_progress INTEGER NOT NULL DEFAULT 0")
    if "home_beginner_mission_hidden" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN home_beginner_mission_hidden INTEGER NOT NULL DEFAULT 0")
    if "home_next_action_collapsed" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN home_next_action_collapsed INTEGER NOT NULL DEFAULT 0")
    if "lab_coin" not in cols:
        db.execute(f"ALTER TABLE users ADD COLUMN lab_coin INTEGER NOT NULL DEFAULT {LAB_CASINO_STARTING_COINS}")
    if "lab_coin_last_daily_at" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN lab_coin_last_daily_at TEXT")
    db.execute("UPDATE users SET is_admin = 0 WHERE is_admin IS NULL")
    db.execute("UPDATE users SET wins = 0 WHERE wins IS NULL")
    db.execute("UPDATE users SET click_power = 1 WHERE click_power IS NULL")
    db.execute("UPDATE users SET total_clicks = 0 WHERE total_clicks IS NULL")
    db.execute("UPDATE users SET robot_slot_limit = 3 WHERE robot_slot_limit IS NULL")
    db.execute("UPDATE users SET part_inventory_limit = 60 WHERE part_inventory_limit IS NULL")
    db.execute("UPDATE users SET battle_log_mode = 'collapsed' WHERE battle_log_mode IS NULL OR battle_log_mode = ''")
    db.execute("UPDATE users SET boss_meter_explore_l1 = 0 WHERE boss_meter_explore_l1 IS NULL")
    db.execute("UPDATE users SET boss_meter_win_l1 = 0 WHERE boss_meter_win_l1 IS NULL")
    db.execute("UPDATE users SET layer2_unlocked = 0 WHERE layer2_unlocked IS NULL")
    db.execute("UPDATE users SET max_unlocked_layer = 1 WHERE max_unlocked_layer IS NULL OR max_unlocked_layer < 1")
    db.execute(f"UPDATE users SET max_unlocked_layer = {MAX_UNLOCKABLE_LAYER} WHERE max_unlocked_layer > {MAX_UNLOCKABLE_LAYER}")
    db.execute("UPDATE users SET max_unlocked_layer = 2 WHERE layer2_unlocked = 1 AND max_unlocked_layer < 2")
    db.execute("UPDATE users SET layer2_unlocked = 1 WHERE max_unlocked_layer >= 2")
    db.execute("UPDATE users SET home_axis_hint_seen = 0 WHERE home_axis_hint_seen IS NULL")
    db.execute("UPDATE users SET stable_no_damage_wins = 0 WHERE stable_no_damage_wins IS NULL")
    db.execute("UPDATE users SET burst_crit_finisher_kills = 0 WHERE burst_crit_finisher_kills IS NULL")
    db.execute("UPDATE users SET desperate_low_hp_wins = 0 WHERE desperate_low_hp_wins IS NULL")
    db.execute(
        "UPDATE users SET faction = NULL WHERE faction IS NOT NULL AND LOWER(TRIM(faction)) NOT IN ('ignis','ventra','aurix')"
    )
    db.execute("UPDATE users SET last_seen_at = COALESCE(created_at, 0) WHERE last_seen_at IS NULL OR last_seen_at <= 0")
    db.execute("UPDATE users SET is_banned = 0 WHERE is_banned IS NULL")
    db.execute("UPDATE users SET is_admin_protected = 0 WHERE is_admin_protected IS NULL")
    db.execute("UPDATE users SET banned_at = NULL WHERE banned_at IS NOT NULL AND TRIM(banned_at) = ''")
    db.execute("UPDATE users SET banned_reason = NULL WHERE banned_reason IS NOT NULL AND TRIM(banned_reason) = ''")
    db.execute("UPDATE users SET has_seen_intro_modal = 0 WHERE has_seen_intro_modal IS NULL")
    db.execute("UPDATE users SET intro_guide_closed_at = NULL WHERE intro_guide_closed_at IS NOT NULL AND TRIM(intro_guide_closed_at) = ''")
    db.execute("UPDATE users SET last_explore_area_key = NULL WHERE last_explore_area_key IS NOT NULL AND TRIM(last_explore_area_key) = ''")
    db.execute("UPDATE users SET explore_boost_until = 0 WHERE explore_boost_until IS NULL")
    db.execute("UPDATE users SET evolution_core_progress = 0 WHERE evolution_core_progress IS NULL OR evolution_core_progress < 0")
    db.execute("UPDATE users SET home_beginner_mission_hidden = 0 WHERE home_beginner_mission_hidden IS NULL")
    db.execute("UPDATE users SET home_next_action_collapsed = 0 WHERE home_next_action_collapsed IS NULL")
    db.execute(f"UPDATE users SET lab_coin = {LAB_CASINO_STARTING_COINS} WHERE lab_coin IS NULL OR lab_coin < 0")
    db.execute(f"UPDATE users SET lab_coin = {LAB_CASINO_COIN_CAP} WHERE lab_coin > {LAB_CASINO_COIN_CAP}")
    db.execute("UPDATE users SET is_admin_protected = 1 WHERE is_admin = 1")
    user_rows = db.execute("SELECT id FROM users WHERE invite_code IS NULL OR TRIM(invite_code) = ''").fetchall()
    for user_row in user_rows:
        _ensure_user_invite_code(db, int(user_row["id"]))
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_invite_code ON users(invite_code)")
    rm_cols = {row["name"] for row in db.execute("PRAGMA table_info(robots_master)").fetchall()}
    if "name" not in rm_cols:
        db.execute("ALTER TABLE robots_master ADD COLUMN name TEXT")
    if "rarity" not in rm_cols:
        db.execute("ALTER TABLE robots_master ADD COLUMN rarity TEXT")
    if "type" not in rm_cols:
        db.execute("ALTER TABLE robots_master ADD COLUMN type TEXT")
    if "flavor_text" not in rm_cols:
        db.execute("ALTER TABLE robots_master ADD COLUMN flavor_text TEXT")
    if "attack" not in rm_cols:
        db.execute("ALTER TABLE robots_master ADD COLUMN attack INTEGER")
    if "defense" not in rm_cols:
        db.execute("ALTER TABLE robots_master ADD COLUMN defense INTEGER")
    if "rarity_bonus" not in rm_cols:
        db.execute("ALTER TABLE robots_master ADD COLUMN rarity_bonus INTEGER")
    db.execute("UPDATE robots_master SET name = head WHERE name IS NULL OR name = ''")
    db.execute("UPDATE robots_master SET rarity = 'N' WHERE rarity IS NULL OR rarity = ''")
    db.execute("UPDATE robots_master SET type = 'normal' WHERE type IS NULL OR type = ''")
    db.execute(
        "UPDATE robots_master SET flavor_text = '静かに起動する標準機。' WHERE flavor_text IS NULL OR flavor_text = ''"
    )
    db.execute("UPDATE robots_master SET attack = 1 WHERE attack IS NULL")
    db.execute("UPDATE robots_master SET defense = 1 WHERE defense IS NULL")
    db.execute("UPDATE robots_master SET rarity_bonus = 0 WHERE rarity_bonus IS NULL")
    ur_cols = {row["name"] for row in db.execute("PRAGMA table_info(user_robots)").fetchall()}
    if "master_id" not in ur_cols:
        db.execute("ALTER TABLE user_robots ADD COLUMN master_id INTEGER")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS login_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            created_at TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            room_key TEXT NOT NULL DEFAULT 'world_public',
            message TEXT,
            created_at TEXT,
            deleted_at TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            title TEXT,
            body TEXT,
            created_at TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_parts_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            part_type TEXT NOT NULL,
            part_key TEXT NOT NULL,
            obtained_at INTEGER NOT NULL,
            source TEXT,
            robot_instance_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_instances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            combat_mode TEXT NOT NULL DEFAULT 'normal',
            style_key TEXT NOT NULL DEFAULT 'stable',
            style_stats_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_instance_parts (
            robot_instance_id INTEGER PRIMARY KEY,
            head_key TEXT NOT NULL,
            r_arm_key TEXT NOT NULL,
            l_arm_key TEXT NOT NULL,
            legs_key TEXT NOT NULL,
            decor_asset_id INTEGER,
            FOREIGN KEY (robot_instance_id) REFERENCES robot_instances(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_decor_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            name_ja TEXT NOT NULL,
            image_path TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS part_instances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            part_type TEXT NOT NULL,
            rarity TEXT NOT NULL,
            element TEXT NOT NULL,
            series TEXT NOT NULL,
            plus INTEGER NOT NULL DEFAULT 0,
            w_hp REAL NOT NULL,
            w_atk REAL NOT NULL,
            w_def REAL NOT NULL,
            w_spd REAL NOT NULL,
            w_acc REAL NOT NULL,
            w_cri REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'inventory',
            created_at INTEGER NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (part_id) REFERENCES robot_parts(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_items (
            user_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            qty INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, item_key),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS enemies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            name_ja TEXT NOT NULL,
            image_path TEXT,
            tier INTEGER NOT NULL,
            element TEXT NOT NULL,
            hp INTEGER NOT NULL,
            atk INTEGER NOT NULL,
            def INTEGER NOT NULL,
            spd INTEGER NOT NULL,
            acc INTEGER NOT NULL,
            cri INTEGER NOT NULL,
            faction TEXT NOT NULL DEFAULT 'neutral',
            trait TEXT,
            is_boss INTEGER NOT NULL DEFAULT 0,
            boss_area_key TEXT,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    enemy_cols = {row["name"] for row in db.execute("PRAGMA table_info(enemies)").fetchall()}
    if "key" not in enemy_cols:
        db.execute("ALTER TABLE enemies ADD COLUMN key TEXT")
    if "name_ja" not in enemy_cols:
        db.execute("ALTER TABLE enemies ADD COLUMN name_ja TEXT")
    if "image_path" not in enemy_cols:
        db.execute("ALTER TABLE enemies ADD COLUMN image_path TEXT")
    if "tier" not in enemy_cols:
        db.execute("ALTER TABLE enemies ADD COLUMN tier INTEGER NOT NULL DEFAULT 1")
    if "element" not in enemy_cols:
        db.execute("ALTER TABLE enemies ADD COLUMN element TEXT NOT NULL DEFAULT 'NORMAL'")
    if "hp" not in enemy_cols:
        db.execute("ALTER TABLE enemies ADD COLUMN hp INTEGER NOT NULL DEFAULT 10")
    if "atk" not in enemy_cols:
        db.execute("ALTER TABLE enemies ADD COLUMN atk INTEGER NOT NULL DEFAULT 5")
    if "def" not in enemy_cols:
        db.execute("ALTER TABLE enemies ADD COLUMN def INTEGER NOT NULL DEFAULT 5")
    if "spd" not in enemy_cols:
        db.execute("ALTER TABLE enemies ADD COLUMN spd INTEGER NOT NULL DEFAULT 5")
    if "acc" not in enemy_cols:
        db.execute("ALTER TABLE enemies ADD COLUMN acc INTEGER NOT NULL DEFAULT 5")
    if "cri" not in enemy_cols:
        db.execute("ALTER TABLE enemies ADD COLUMN cri INTEGER NOT NULL DEFAULT 1")
    if "faction" not in enemy_cols:
        db.execute("ALTER TABLE enemies ADD COLUMN faction TEXT NOT NULL DEFAULT 'neutral'")
    if "trait" not in enemy_cols:
        db.execute("ALTER TABLE enemies ADD COLUMN trait TEXT")
    if "is_boss" not in enemy_cols:
        db.execute("ALTER TABLE enemies ADD COLUMN is_boss INTEGER NOT NULL DEFAULT 0")
    if "boss_area_key" not in enemy_cols:
        db.execute("ALTER TABLE enemies ADD COLUMN boss_area_key TEXT")
    if "is_active" not in enemy_cols:
        db.execute("ALTER TABLE enemies ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
    db.execute("UPDATE enemies SET faction = 'neutral' WHERE faction IS NULL OR faction = ''")
    db.execute("UPDATE enemies SET trait = NULL WHERE COALESCE(trait, '') NOT IN ('', 'heavy', 'fast', 'berserk', 'unstable')")
    db.execute("UPDATE enemies SET is_boss = 0 WHERE is_boss IS NULL")
    boss_area_placeholders = ",".join(["?"] * len(AREA_BOSS_KEYS))
    db.execute(
        f"UPDATE enemies SET boss_area_key = NULL WHERE boss_area_key IS NOT NULL AND boss_area_key NOT IN ({boss_area_placeholders})",
        list(AREA_BOSS_KEYS),
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            milestone_key TEXT UNIQUE NOT NULL,
            metric TEXT NOT NULL,
            threshold_value INTEGER NOT NULL,
            reward_head_key TEXT NOT NULL,
            reward_r_arm_key TEXT NOT NULL,
            reward_l_arm_key TEXT NOT NULL,
            reward_legs_key TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_milestone_claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            milestone_key TEXT NOT NULL,
            robot_instance_id INTEGER NOT NULL,
            claimed_at INTEGER NOT NULL,
            UNIQUE(user_id, milestone_key),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS qol_entitlements (
            user_id INTEGER PRIMARY KEY,
            slot_bonus INTEGER NOT NULL DEFAULT 0,
            showcase_slots INTEGER NOT NULL DEFAULT 1,
            active_slot_bonus INTEGER NOT NULL DEFAULT 0,
            decompose_speed_bonus INTEGER NOT NULL DEFAULT 0,
            cosmetic_flags TEXT NOT NULL DEFAULT '',
            updated_at INTEGER NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_showcase (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            slot_no INTEGER NOT NULL,
            robot_instance_id INTEGER,
            UNIQUE(user_id, slot_no),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS world_weekly_environment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT UNIQUE NOT NULL,
            element TEXT NOT NULL,
            mode TEXT NOT NULL,
            enemy_spawn_bonus REAL NOT NULL DEFAULT 0.0,
            drop_bonus REAL NOT NULL DEFAULT 0.0,
            started_at INTEGER NOT NULL,
            ends_at INTEGER NOT NULL,
            random_seed INTEGER,
            influence_ratio REAL NOT NULL DEFAULT 0.30,
            reason TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS world_weekly_counters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            metric_key TEXT NOT NULL,
            value INTEGER NOT NULL DEFAULT 0,
            UNIQUE(week_key, metric_key)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS world_faction_weekly_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            faction TEXT NOT NULL,
            points INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL,
            UNIQUE(week_key, faction)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS world_faction_weekly_result (
            week_key TEXT PRIMARY KEY,
            winner_faction TEXT NOT NULL,
            scores_json TEXT NOT NULL,
            computed_at INTEGER NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS world_events_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT,
            user_id INTEGER,
            request_id TEXT,
            ip_hash TEXT,
            action_key TEXT,
            entity_type TEXT,
            entity_id INTEGER,
            delta_coins INTEGER,
            delta_count INTEGER
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_user_id INTEGER NOT NULL,
            referred_user_id INTEGER NOT NULL,
            referral_code TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at INTEGER NOT NULL,
            qualified_at INTEGER,
            rewarded_at INTEGER,
            UNIQUE(referrer_user_id, referred_user_id),
            UNIQUE(referred_user_id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS world_research_progress (
            element TEXT PRIMARY KEY,
            progress INTEGER NOT NULL DEFAULT 0,
            unlocked_stage INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS world_research_unlocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at INTEGER NOT NULL,
            week_key TEXT NOT NULL,
            element TEXT NOT NULL,
            stage INTEGER NOT NULL,
            part_type TEXT NOT NULL,
            payload_json TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_boss_progress (
            user_id INTEGER NOT NULL,
            area_key TEXT NOT NULL,
            no_boss_streak INTEGER NOT NULL DEFAULT 0,
            active_boss_enemy_id INTEGER,
            boss_attempts_left INTEGER NOT NULL DEFAULT 0,
            boss_alert_expires_at INTEGER,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (user_id, area_key),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_decor_inventory (
            user_id INTEGER NOT NULL,
            decor_asset_id INTEGER NOT NULL,
            acquired_at INTEGER NOT NULL,
            UNIQUE(user_id, decor_asset_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (decor_asset_id) REFERENCES robot_decor_assets(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS payment_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_key TEXT NOT NULL,
            stripe_checkout_session_id TEXT UNIQUE,
            stripe_payment_intent_id TEXT,
            stripe_event_id TEXT UNIQUE,
            amount_jpy INTEGER,
            currency TEXT,
            status TEXT NOT NULL DEFAULT 'created',
            grant_type TEXT NOT NULL,
            boost_days INTEGER NOT NULL DEFAULT 0,
            starts_at INTEGER,
            ends_at INTEGER,
            granted_at INTEGER,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_history (
            robot_id INTEGER PRIMARY KEY,
            battles_total INTEGER NOT NULL DEFAULT 0,
            wins_total INTEGER NOT NULL DEFAULT 0,
            losses_total INTEGER NOT NULL DEFAULT 0,
            boss_encounters_total INTEGER NOT NULL DEFAULT 0,
            boss_defeats_total INTEGER NOT NULL DEFAULT 0,
            wins_this_week INTEGER NOT NULL DEFAULT 0,
            wins_this_week_key TEXT NOT NULL DEFAULT '',
            updated_at INTEGER NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_titles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            name_ja TEXT NOT NULL,
            desc_ja TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_title_unlocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            robot_id INTEGER NOT NULL,
            title_id INTEGER NOT NULL,
            unlocked_at INTEGER NOT NULL,
            UNIQUE(robot_id, title_id),
            FOREIGN KEY (robot_id) REFERENCES robot_instances(id),
            FOREIGN KEY (title_id) REFERENCES robot_titles(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            robot_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            enemy_key TEXT,
            enemy_name TEXT,
            week_key TEXT,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (robot_id) REFERENCES robot_instances(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS showcase_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            robot_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            vote_type TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            UNIQUE(robot_id, user_id, vote_type),
            FOREIGN KEY (robot_id) REFERENCES robot_instances(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_robot_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            comment TEXT NOT NULL,
            image_path TEXT NOT NULL,
            thumb_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            moderation_note TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            approved_at INTEGER,
            approved_by_user_id INTEGER,
            disabled_at INTEGER,
            disabled_by_user_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_submission_likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            UNIQUE(submission_id, user_id),
            FOREIGN KEY (submission_id) REFERENCES lab_robot_submissions(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_submission_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (submission_id) REFERENCES lab_robot_submissions(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_races (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL DEFAULT 'entry_open',
            course_key TEXT NOT NULL,
            course_payload_json TEXT,
            seed INTEGER NOT NULL,
            started_at INTEGER,
            finished_at INTEGER,
            created_at INTEGER NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_race_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id INTEGER NOT NULL,
            user_id INTEGER,
            source_type TEXT NOT NULL,
            robot_instance_id INTEGER,
            submission_id INTEGER,
            display_name TEXT NOT NULL,
            icon_path TEXT,
            hp INTEGER NOT NULL,
            atk INTEGER NOT NULL,
            def INTEGER NOT NULL,
            spd INTEGER NOT NULL,
            acc INTEGER NOT NULL,
            cri INTEGER NOT NULL,
            entry_order INTEGER NOT NULL,
            final_rank INTEGER,
            finish_time_ms INTEGER,
            dnf_reason TEXT,
            UNIQUE(race_id, entry_order),
            UNIQUE(race_id, user_id),
            FOREIGN KEY (race_id) REFERENCES lab_races(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (robot_instance_id) REFERENCES robot_instances(id),
            FOREIGN KEY (submission_id) REFERENCES lab_robot_submissions(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_race_frames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id INTEGER NOT NULL,
            frame_no INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            UNIQUE(race_id, frame_no),
            FOREIGN KEY (race_id) REFERENCES lab_races(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_race_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id INTEGER NOT NULL,
            entry_id INTEGER NOT NULL,
            user_id INTEGER,
            robot_label TEXT NOT NULL,
            final_rank INTEGER NOT NULL,
            finish_time_ms INTEGER,
            accident_count INTEGER NOT NULL DEFAULT 0,
            comeback_flag INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            UNIQUE(race_id, entry_id),
            FOREIGN KEY (race_id) REFERENCES lab_races(id),
            FOREIGN KEY (entry_id) REFERENCES lab_race_entries(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_casino_races (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_key TEXT NOT NULL,
            course_payload_json TEXT,
            status TEXT NOT NULL DEFAULT 'betting',
            seed INTEGER NOT NULL,
            started_at INTEGER,
            finished_at INTEGER,
            created_at INTEGER NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_casino_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id INTEGER NOT NULL,
            bot_key TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role_type TEXT NOT NULL,
            condition_key TEXT NOT NULL,
            icon_path TEXT,
            description TEXT,
            spd INTEGER NOT NULL,
            def INTEGER NOT NULL,
            acc INTEGER NOT NULL,
            cri INTEGER NOT NULL,
            luck INTEGER NOT NULL,
            odds REAL NOT NULL,
            lane_index INTEGER NOT NULL,
            entry_order INTEGER NOT NULL,
            final_rank INTEGER,
            finish_time_ms INTEGER,
            accident_count INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            UNIQUE(race_id, bot_key),
            UNIQUE(race_id, lane_index),
            UNIQUE(race_id, entry_order),
            FOREIGN KEY (race_id) REFERENCES lab_casino_races(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_casino_bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            race_id INTEGER NOT NULL,
            entry_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            payout_amount INTEGER NOT NULL DEFAULT 0,
            is_hit INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            resolved_at INTEGER,
            UNIQUE(user_id, race_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (race_id) REFERENCES lab_casino_races(id),
            FOREIGN KEY (entry_id) REFERENCES lab_casino_entries(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_casino_frames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id INTEGER NOT NULL,
            frame_no INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            UNIQUE(race_id, frame_no),
            FOREIGN KEY (race_id) REFERENCES lab_casino_races(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_casino_prizes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prize_key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            cost_lab_coin INTEGER NOT NULL,
            prize_type TEXT NOT NULL,
            grant_key TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_casino_prize_claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            prize_id INTEGER NOT NULL,
            cost_lab_coin INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (prize_id) REFERENCES lab_casino_prizes(id)
        )
        """
    )
    lab_race_cols = {row["name"] for row in db.execute("PRAGMA table_info(lab_races)").fetchall()}
    if "course_payload_json" not in lab_race_cols:
        db.execute("ALTER TABLE lab_races ADD COLUMN course_payload_json TEXT")
    lab_casino_race_cols = {row["name"] for row in db.execute("PRAGMA table_info(lab_casino_races)").fetchall()}
    if "course_payload_json" not in lab_casino_race_cols:
        db.execute("ALTER TABLE lab_casino_races ADD COLUMN course_payload_json TEXT")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_metrics (
            day_key TEXT PRIMARY KEY,
            dau_count INTEGER NOT NULL DEFAULT 0,
            new_users INTEGER NOT NULL DEFAULT 0,
            explore_count INTEGER NOT NULL DEFAULT 0,
            boss_encounters INTEGER NOT NULL DEFAULT 0,
            boss_defeats INTEGER NOT NULL DEFAULT 0,
            fuse_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS portal_online_delivery_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            online_count INTEGER NOT NULL,
            window_minutes INTEGER NOT NULL DEFAULT 5,
            status TEXT NOT NULL DEFAULT 'pending',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            last_attempt_at INTEGER,
            delivered_at INTEGER,
            last_error TEXT,
            response_status INTEGER
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_enemy_dex (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            enemy_key TEXT NOT NULL,
            first_seen_at INTEGER NOT NULL,
            first_defeated_at INTEGER,
            seen_count INTEGER NOT NULL DEFAULT 0,
            defeat_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, enemy_key),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS npc_boss_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_user_id INTEGER NOT NULL,
            source_robot_instance_id INTEGER NOT NULL,
            source_faction TEXT,
            source_robot_name TEXT,
            boss_area_key TEXT NOT NULL,
            enemy_key TEXT UNIQUE NOT NULL,
            enemy_name_ja TEXT NOT NULL,
            image_path TEXT,
            hp INTEGER NOT NULL,
            atk INTEGER NOT NULL,
            def INTEGER NOT NULL,
            spd INTEGER NOT NULL,
            acc INTEGER NOT NULL,
            cri INTEGER NOT NULL,
            spawn_weight REAL NOT NULL DEFAULT 1.0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    udi_cols = {row["name"] for row in db.execute("PRAGMA table_info(user_decor_inventory)").fetchall()}
    if "acquired_at" not in udi_cols:
        db.execute("ALTER TABLE user_decor_inventory ADD COLUMN acquired_at INTEGER")
        if "created_at" in udi_cols:
            db.execute("UPDATE user_decor_inventory SET acquired_at = created_at WHERE acquired_at IS NULL")
        db.execute("UPDATE user_decor_inventory SET acquired_at = ? WHERE acquired_at IS NULL", (int(time.time()),))
    po_cols = {row["name"] for row in db.execute("PRAGMA table_info(payment_orders)").fetchall()}
    if "user_id" not in po_cols:
        db.execute("ALTER TABLE payment_orders ADD COLUMN user_id INTEGER")
    if "product_key" not in po_cols:
        db.execute("ALTER TABLE payment_orders ADD COLUMN product_key TEXT")
    if "stripe_checkout_session_id" not in po_cols:
        db.execute("ALTER TABLE payment_orders ADD COLUMN stripe_checkout_session_id TEXT")
    if "stripe_payment_intent_id" not in po_cols:
        db.execute("ALTER TABLE payment_orders ADD COLUMN stripe_payment_intent_id TEXT")
    if "stripe_event_id" not in po_cols:
        db.execute("ALTER TABLE payment_orders ADD COLUMN stripe_event_id TEXT")
    if "amount_jpy" not in po_cols:
        db.execute("ALTER TABLE payment_orders ADD COLUMN amount_jpy INTEGER")
    if "currency" not in po_cols:
        db.execute("ALTER TABLE payment_orders ADD COLUMN currency TEXT")
    if "status" not in po_cols:
        db.execute("ALTER TABLE payment_orders ADD COLUMN status TEXT NOT NULL DEFAULT 'created'")
    if "grant_type" not in po_cols:
        db.execute("ALTER TABLE payment_orders ADD COLUMN grant_type TEXT NOT NULL DEFAULT 'decor'")
    if "boost_days" not in po_cols:
        db.execute("ALTER TABLE payment_orders ADD COLUMN boost_days INTEGER NOT NULL DEFAULT 0")
    if "starts_at" not in po_cols:
        db.execute("ALTER TABLE payment_orders ADD COLUMN starts_at INTEGER")
    if "ends_at" not in po_cols:
        db.execute("ALTER TABLE payment_orders ADD COLUMN ends_at INTEGER")
    if "granted_at" not in po_cols:
        db.execute("ALTER TABLE payment_orders ADD COLUMN granted_at INTEGER")
    if "created_at" not in po_cols:
        db.execute("ALTER TABLE payment_orders ADD COLUMN created_at INTEGER NOT NULL DEFAULT 0")
    if "updated_at" not in po_cols:
        db.execute("ALTER TABLE payment_orders ADD COLUMN updated_at INTEGER NOT NULL DEFAULT 0")
    db.execute("UPDATE payment_orders SET status = 'created' WHERE status IS NULL OR TRIM(status) = ''")
    db.execute("UPDATE payment_orders SET grant_type = 'decor' WHERE grant_type IS NULL OR TRIM(grant_type) = ''")
    db.execute("UPDATE payment_orders SET boost_days = 0 WHERE boost_days IS NULL")
    db.execute("UPDATE payment_orders SET created_at = 0 WHERE created_at IS NULL")
    db.execute("UPDATE payment_orders SET updated_at = created_at WHERE updated_at IS NULL OR updated_at = 0")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_area_streaks (
            user_id INTEGER NOT NULL,
            area_key TEXT NOT NULL,
            win_streak INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (user_id, area_key)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS fusion_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            mode TEXT NOT NULL,
            part_type TEXT,
            rarity TEXT,
            from_plus INTEGER,
            to_plus INTEGER,
            outcome TEXT,
            use_protect_core INTEGER NOT NULL DEFAULT 0,
            consumed_ids TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            message TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS core_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            core_key TEXT UNIQUE NOT NULL,
            name_ja TEXT NOT NULL,
            description TEXT,
            icon_path TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_core_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            core_asset_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT,
            UNIQUE(user_id, core_asset_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (core_asset_id) REFERENCES core_assets(id)
        )
        """
    )
    ri_cols = {row["name"] for row in db.execute("PRAGMA table_info(robot_instances)").fetchall()}
    if "composed_image_path" not in ri_cols:
        db.execute("ALTER TABLE robot_instances ADD COLUMN composed_image_path TEXT")
    if "personality" not in ri_cols:
        db.execute("ALTER TABLE robot_instances ADD COLUMN personality TEXT")
    if "icon_32_path" not in ri_cols:
        db.execute("ALTER TABLE robot_instances ADD COLUMN icon_32_path TEXT")
    if "combat_mode" not in ri_cols:
        db.execute("ALTER TABLE robot_instances ADD COLUMN combat_mode TEXT NOT NULL DEFAULT 'normal'")
    if "is_public" not in ri_cols:
        db.execute("ALTER TABLE robot_instances ADD COLUMN is_public INTEGER NOT NULL DEFAULT 1")
    if "style_key" not in ri_cols:
        db.execute("ALTER TABLE robot_instances ADD COLUMN style_key TEXT NOT NULL DEFAULT 'stable'")
    if "style_stats_json" not in ri_cols:
        db.execute("ALTER TABLE robot_instances ADD COLUMN style_stats_json TEXT NOT NULL DEFAULT '{}'")
    db.execute("UPDATE robot_instances SET combat_mode = 'normal' WHERE combat_mode IS NULL OR combat_mode = ''")
    db.execute("UPDATE robot_instances SET is_public = 1 WHERE is_public IS NULL")
    db.execute("UPDATE robot_instances SET style_key = 'stable' WHERE style_key IS NULL OR TRIM(style_key) = ''")
    db.execute("UPDATE robot_instances SET style_stats_json = '{}' WHERE style_stats_json IS NULL OR TRIM(style_stats_json) = ''")
    qe_cols = {row["name"] for row in db.execute("PRAGMA table_info(qol_entitlements)").fetchall()}
    if "showcase_slots" not in qe_cols:
        db.execute("ALTER TABLE qol_entitlements ADD COLUMN showcase_slots INTEGER NOT NULL DEFAULT 1")
    rb_cols = {row["name"] for row in db.execute("PRAGMA table_info(robot_builds)").fetchall()}
    if "base_body_id" in rb_cols and "base_key" not in rb_cols:
        _migrate_robot_builds(db)
        rb_cols = {row["name"] for row in db.execute("PRAGMA table_info(robot_builds)").fetchall()}
    if "base_key" not in rb_cols:
        db.execute("ALTER TABLE robot_builds ADD COLUMN base_key TEXT")
    if "head_key" not in rb_cols:
        db.execute("ALTER TABLE robot_builds ADD COLUMN head_key TEXT")
    if "r_arm_key" not in rb_cols:
        db.execute("ALTER TABLE robot_builds ADD COLUMN r_arm_key TEXT")
    if "l_arm_key" not in rb_cols:
        db.execute("ALTER TABLE robot_builds ADD COLUMN l_arm_key TEXT")
    if "legs_key" not in rb_cols:
        db.execute("ALTER TABLE robot_builds ADD COLUMN legs_key TEXT")
    if "composed_image_path" not in rb_cols:
        db.execute("ALTER TABLE robot_builds ADD COLUMN composed_image_path TEXT")
    if "head_offset_x" not in rb_cols:
        db.execute("ALTER TABLE robot_builds ADD COLUMN head_offset_x INTEGER NOT NULL DEFAULT 0")
    if "head_offset_y" not in rb_cols:
        db.execute("ALTER TABLE robot_builds ADD COLUMN head_offset_y INTEGER NOT NULL DEFAULT 0")
    if "r_arm_offset_x" not in rb_cols:
        db.execute("ALTER TABLE robot_builds ADD COLUMN r_arm_offset_x INTEGER NOT NULL DEFAULT 0")
    if "r_arm_offset_y" not in rb_cols:
        db.execute("ALTER TABLE robot_builds ADD COLUMN r_arm_offset_y INTEGER NOT NULL DEFAULT 0")
    if "l_arm_offset_x" not in rb_cols:
        db.execute("ALTER TABLE robot_builds ADD COLUMN l_arm_offset_x INTEGER NOT NULL DEFAULT 0")
    if "l_arm_offset_y" not in rb_cols:
        db.execute("ALTER TABLE robot_builds ADD COLUMN l_arm_offset_y INTEGER NOT NULL DEFAULT 0")
    if "legs_offset_x" not in rb_cols:
        db.execute("ALTER TABLE robot_builds ADD COLUMN legs_offset_x INTEGER NOT NULL DEFAULT 0")
    if "legs_offset_y" not in rb_cols:
        db.execute("ALTER TABLE robot_builds ADD COLUMN legs_offset_y INTEGER NOT NULL DEFAULT 0")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS robot_bases_key_uq ON robot_bases(key)")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS robot_parts_key_uq ON robot_parts(key)")
    bb_cols = {row["name"] for row in db.execute("PRAGMA table_info(base_bodies)").fetchall()}
    if "sprite_path" not in bb_cols:
        db.execute("ALTER TABLE base_bodies ADD COLUMN sprite_path TEXT")
    part_cols = {row["name"] for row in db.execute("PRAGMA table_info(parts)").fetchall()}
    if "attack" not in part_cols:
        db.execute("ALTER TABLE parts ADD COLUMN attack INTEGER")
    if "defense" not in part_cols:
        db.execute("ALTER TABLE parts ADD COLUMN defense INTEGER")
    if "speed" not in part_cols:
        db.execute("ALTER TABLE parts ADD COLUMN speed INTEGER")
    if "hp" not in part_cols:
        db.execute("ALTER TABLE parts ADD COLUMN hp INTEGER")
    if "sprite_path" not in part_cols:
        db.execute("ALTER TABLE parts ADD COLUMN sprite_path TEXT")
    if "type" not in part_cols:
        db.execute("ALTER TABLE parts ADD COLUMN type TEXT")
    if "name" not in part_cols:
        db.execute("ALTER TABLE parts ADD COLUMN name TEXT")
    db.execute("UPDATE base_bodies SET sprite_path = 'base_bodies/normal.png' WHERE sprite_path IS NULL OR sprite_path = ''")
    db.execute("UPDATE parts SET attack = 1 WHERE attack IS NULL")
    db.execute("UPDATE parts SET defense = 1 WHERE defense IS NULL")
    db.execute("UPDATE parts SET speed = 1 WHERE speed IS NULL")
    db.execute("UPDATE parts SET hp = 1 WHERE hp IS NULL")
    rp_cols = {row["name"] for row in db.execute("PRAGMA table_info(robot_parts)").fetchall()}
    if "rarity" not in rp_cols:
        db.execute("ALTER TABLE robot_parts ADD COLUMN rarity TEXT")
    if "offset_x" not in rp_cols:
        db.execute("ALTER TABLE robot_parts ADD COLUMN offset_x INTEGER NOT NULL DEFAULT 0")
    if "offset_y" not in rp_cols:
        db.execute("ALTER TABLE robot_parts ADD COLUMN offset_y INTEGER NOT NULL DEFAULT 0")
    if "is_active" not in rp_cols:
        db.execute("ALTER TABLE robot_parts ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
    if "is_unlocked" not in rp_cols:
        db.execute("ALTER TABLE robot_parts ADD COLUMN is_unlocked INTEGER NOT NULL DEFAULT 1")
    if "element" not in rp_cols:
        db.execute("ALTER TABLE robot_parts ADD COLUMN element TEXT")
    if "series" not in rp_cols:
        db.execute("ALTER TABLE robot_parts ADD COLUMN series TEXT")
    if "display_name_ja" not in rp_cols:
        db.execute("ALTER TABLE robot_parts ADD COLUMN display_name_ja TEXT")
    db.execute("UPDATE robot_parts SET rarity = 'N' WHERE rarity IS NULL OR rarity = ''")
    db.execute("UPDATE robot_parts SET element = 'NORMAL' WHERE element IS NULL OR element = ''")
    db.execute("UPDATE robot_parts SET series = 'S1' WHERE series IS NULL OR series = ''")
    db.execute("UPDATE robot_parts SET is_active = 1 WHERE is_active IS NULL")
    db.execute("UPDATE robot_parts SET is_unlocked = 1 WHERE is_unlocked IS NULL")
    db.execute("UPDATE robot_parts SET is_unlocked = 1 WHERE UPPER(COALESCE(rarity, '')) = 'N'")
    db.execute("UPDATE robot_parts SET is_unlocked = 0 WHERE UPPER(COALESCE(rarity, '')) = 'R'")
    _backfill_part_display_names(db)
    rip_cols = {row["name"] for row in db.execute("PRAGMA table_info(robot_instance_parts)").fetchall()}
    if "head_part_instance_id" not in rip_cols:
        db.execute("ALTER TABLE robot_instance_parts ADD COLUMN head_part_instance_id INTEGER")
    if "r_arm_part_instance_id" not in rip_cols:
        db.execute("ALTER TABLE robot_instance_parts ADD COLUMN r_arm_part_instance_id INTEGER")
    if "l_arm_part_instance_id" not in rip_cols:
        db.execute("ALTER TABLE robot_instance_parts ADD COLUMN l_arm_part_instance_id INTEGER")
    if "legs_part_instance_id" not in rip_cols:
        db.execute("ALTER TABLE robot_instance_parts ADD COLUMN legs_part_instance_id INTEGER")
    if "decor_asset_id" not in rip_cols:
        db.execute("ALTER TABLE robot_instance_parts ADD COLUMN decor_asset_id INTEGER")
    rda_cols = {row["name"] for row in db.execute("PRAGMA table_info(robot_decor_assets)").fetchall()}
    if "key" not in rda_cols:
        db.execute("ALTER TABLE robot_decor_assets ADD COLUMN key TEXT")
    if "name_ja" not in rda_cols:
        db.execute("ALTER TABLE robot_decor_assets ADD COLUMN name_ja TEXT")
    if "image_path" not in rda_cols:
        db.execute("ALTER TABLE robot_decor_assets ADD COLUMN image_path TEXT")
    if "is_active" not in rda_cols:
        db.execute("ALTER TABLE robot_decor_assets ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
    if "created_at" not in rda_cols:
        db.execute("ALTER TABLE robot_decor_assets ADD COLUMN created_at INTEGER NOT NULL DEFAULT 0")
    pi_cols = {row["name"] for row in db.execute("PRAGMA table_info(part_instances)").fetchall()}
    if "part_type" not in pi_cols:
        db.execute("ALTER TABLE part_instances ADD COLUMN part_type TEXT")
    if "updated_at" not in pi_cols:
        db.execute("ALTER TABLE part_instances ADD COLUMN updated_at TEXT")
    db.execute(
        """
        UPDATE part_instances
        SET part_type = (
            SELECT rp.part_type FROM robot_parts rp WHERE rp.id = part_instances.part_id
        )
        WHERE part_type IS NULL OR part_type = ''
        """
    )
    db.execute("UPDATE part_instances SET updated_at = datetime('now') WHERE updated_at IS NULL OR TRIM(updated_at) = ''")
    wwe_cols = {row["name"] for row in db.execute("PRAGMA table_info(world_weekly_environment)").fetchall()}
    if "influence_ratio" not in wwe_cols:
        db.execute("ALTER TABLE world_weekly_environment ADD COLUMN influence_ratio REAL NOT NULL DEFAULT 0.30")
    if "reason" not in wwe_cols:
        db.execute("ALTER TABLE world_weekly_environment ADD COLUMN reason TEXT")
    ubp_cols = {row["name"] for row in db.execute("PRAGMA table_info(user_boss_progress)").fetchall()}
    if "active_boss_enemy_id" not in ubp_cols:
        db.execute("ALTER TABLE user_boss_progress ADD COLUMN active_boss_enemy_id INTEGER")
    if "boss_attempts_left" not in ubp_cols:
        db.execute("ALTER TABLE user_boss_progress ADD COLUMN boss_attempts_left INTEGER NOT NULL DEFAULT 0")
    if "boss_alert_expires_at" not in ubp_cols:
        db.execute("ALTER TABLE user_boss_progress ADD COLUMN boss_alert_expires_at INTEGER")
    db.execute("UPDATE user_boss_progress SET boss_attempts_left = 0 WHERE boss_attempts_left IS NULL")
    db.execute("UPDATE world_weekly_environment SET mode = '暴走' WHERE LOWER(mode) = 'storm'")
    db.execute("UPDATE world_weekly_environment SET mode = '活性' WHERE LOWER(mode) = 'surge'")
    db.execute("UPDATE world_weekly_environment SET mode = '安定' WHERE LOWER(mode) = 'calm'")
    chat_cols = {row["name"] for row in db.execute("PRAGMA table_info(chat_messages)").fetchall()}
    if "room_key" not in chat_cols:
        db.execute("ALTER TABLE chat_messages ADD COLUMN room_key TEXT NOT NULL DEFAULT 'world_public'")
    if "deleted_at" not in chat_cols:
        db.execute("ALTER TABLE chat_messages ADD COLUMN deleted_at TEXT")
    db.execute("UPDATE chat_messages SET room_key = ? WHERE room_key IS NULL OR TRIM(room_key) = ''", (COMM_WORLD_ROOM_KEY,))
    wel_cols = {row["name"] for row in db.execute("PRAGMA table_info(world_events_log)").fetchall()}
    if "user_id" not in wel_cols:
        db.execute("ALTER TABLE world_events_log ADD COLUMN user_id INTEGER")
    if "request_id" not in wel_cols:
        db.execute("ALTER TABLE world_events_log ADD COLUMN request_id TEXT")
    if "ip_hash" not in wel_cols:
        db.execute("ALTER TABLE world_events_log ADD COLUMN ip_hash TEXT")
    if "action_key" not in wel_cols:
        db.execute("ALTER TABLE world_events_log ADD COLUMN action_key TEXT")
    if "entity_type" not in wel_cols:
        db.execute("ALTER TABLE world_events_log ADD COLUMN entity_type TEXT")
    if "entity_id" not in wel_cols:
        db.execute("ALTER TABLE world_events_log ADD COLUMN entity_id INTEGER")
    if "delta_coins" not in wel_cols:
        db.execute("ALTER TABLE world_events_log ADD COLUMN delta_coins INTEGER")
    if "delta_count" not in wel_cols:
        db.execute("ALTER TABLE world_events_log ADD COLUMN delta_count INTEGER")
    db.execute("CREATE INDEX IF NOT EXISTS idx_world_events_log_user_created ON world_events_log(user_id, created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_world_events_log_request ON world_events_log(request_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_world_events_log_event_type_created ON world_events_log(event_type, created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_room_created ON chat_messages(room_key, created_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_user_room_created ON chat_messages(user_id, room_key, created_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_users_faction ON users(faction)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_faction_scores_week_points ON world_faction_weekly_scores(week_key, points DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_faction_result_week ON world_faction_weekly_result(week_key)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_user_enemy_dex_user_seen ON user_enemy_dex(user_id, seen_count DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_robot_history_updated ON robot_history(updated_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_robot_achievements_robot_created ON robot_achievements(robot_id, created_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_robot_title_unlocks_robot ON robot_title_unlocks(robot_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_showcase_votes_robot_type ON showcase_votes(robot_id, vote_type)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_showcase_votes_user ON showcase_votes(user_id, vote_type)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_lab_submissions_status_created ON lab_robot_submissions(status, created_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_lab_submissions_user_created ON lab_robot_submissions(user_id, created_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_lab_submission_likes_submission ON lab_submission_likes(submission_id, created_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_lab_submission_reports_submission ON lab_submission_reports(submission_id, created_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_lab_races_status_created ON lab_races(status, created_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_lab_race_entries_race_order ON lab_race_entries(race_id, entry_order)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_lab_race_records_user_rank ON lab_race_records(user_id, final_rank, finish_time_ms)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_users_lab_coin ON users(lab_coin DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_lab_casino_races_status_created ON lab_casino_races(status, created_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_lab_casino_entries_race_lane ON lab_casino_entries(race_id, lane_index)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_lab_casino_bets_user_created ON lab_casino_bets(user_id, created_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_lab_casino_bets_race ON lab_casino_bets(race_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_lab_casino_frames_race_frame ON lab_casino_frames(race_id, frame_no)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_lab_casino_prizes_active_cost ON lab_casino_prizes(is_active, cost_lab_coin ASC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_lab_casino_claims_user_created ON lab_casino_prize_claims(user_id, created_at DESC)")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_portal_online_delivery_queue_status_created ON portal_online_delivery_queue(status, created_at)"
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_user_core_inventory_user_core ON user_core_inventory(user_id, core_asset_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_user_referrals_referrer_status ON user_referrals(referrer_user_id, status)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_user_referrals_referred_status ON user_referrals(referred_user_id, status)")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_npc_boss_templates_area_active ON npc_boss_templates(boss_area_key, is_active, spawn_weight DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_npc_boss_templates_source_robot ON npc_boss_templates(source_robot_instance_id)"
    )
    rh_cols = {row["name"] for row in db.execute("PRAGMA table_info(robot_history)").fetchall()}
    if "wins_this_week_key" not in rh_cols:
        db.execute("ALTER TABLE robot_history ADD COLUMN wins_this_week_key TEXT NOT NULL DEFAULT ''")
    _ensure_robot_title_master_rows(db)
    db.execute("CREATE INDEX IF NOT EXISTS idx_daily_metrics_day_key ON daily_metrics(day_key)")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_world_research_unlocks_week_created ON world_research_unlocks(week_key, created_at)"
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_enemies_boss_area_active ON enemies(is_boss, boss_area_key, is_active)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_user_decor_inventory_user_acquired ON user_decor_inventory(user_id, acquired_at)")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_orders_session_id ON payment_orders(stripe_checkout_session_id)")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_orders_event_id ON payment_orders(stripe_event_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_payment_orders_user_created ON payment_orders(user_id, created_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_payment_orders_status_created ON payment_orders(status, created_at DESC)")
    _seed_enemies(db)
    _apply_default_enemy_traits(db)
    _seed_default_decor_assets(db)
    _seed_core_definitions(db)
    _seed_release_flags(db)
    _warn_missing_boss_decor_keys(db)
    _seed_lab_casino_prizes(db)
    _ensure_world_research_rows(db)
    _ensure_world_week_environment(db)
    db.commit()


def _migrate_robot_builds(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_builds_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            base_key TEXT,
            head_key TEXT,
            r_arm_key TEXT,
            l_arm_key TEXT,
            legs_key TEXT,
            composed_image_path TEXT,
            head_offset_x INTEGER NOT NULL DEFAULT 0,
            head_offset_y INTEGER NOT NULL DEFAULT 0,
            r_arm_offset_x INTEGER NOT NULL DEFAULT 0,
            r_arm_offset_y INTEGER NOT NULL DEFAULT 0,
            l_arm_offset_x INTEGER NOT NULL DEFAULT 0,
            l_arm_offset_y INTEGER NOT NULL DEFAULT 0,
            legs_offset_x INTEGER NOT NULL DEFAULT 0,
            legs_offset_y INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    rows = db.execute(
        "SELECT id, user_id, base_body_id, head_part_id, right_arm_part_id, left_arm_part_id, legs_part_id, created_at FROM robot_builds"
    ).fetchall()
    base_map = {
        row["id"]: row["name"]
        for row in db.execute("SELECT id, name FROM base_bodies").fetchall()
    }
    part_map = {
        row["id"]: row["name"]
        for row in db.execute("SELECT id, name FROM parts").fetchall()
    }

    def to_key(name):
        if not name:
            return None
        name = name.strip()
        if name.startswith("HEAD-"):
            return f"head_{name.split('-')[-1]}"
        if name.startswith("R-ARM-"):
            return f"r_arm_{name.split('-')[-1]}"
        if name.startswith("L-ARM-"):
            return f"l_arm_{name.split('-')[-1]}"
        if name.startswith("LEGS-"):
            return f"legs_{name.split('-')[-1]}"
        return None

    for r in rows:
        base_key = base_map.get(r["base_body_id"])
        head_key = to_key(part_map.get(r["head_part_id"]))
        r_arm_key = to_key(part_map.get(r["right_arm_part_id"]))
        l_arm_key = to_key(part_map.get(r["left_arm_part_id"]))
        legs_key = to_key(part_map.get(r["legs_part_id"]))
        db.execute(
            """
            INSERT INTO robot_builds_new (id, user_id, base_key, head_key, r_arm_key, l_arm_key, legs_key, composed_image_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r["id"],
                r["user_id"],
                base_key,
                head_key,
                r_arm_key,
                l_arm_key,
                legs_key,
                None,
                r["created_at"],
            ),
        )
    db.execute("DROP TABLE robot_builds")
    db.execute("ALTER TABLE robot_builds_new RENAME TO robot_builds")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        ensure_schema(g.db)
        _ensure_dirs()
        _ensure_default_images()
        _check_static_health()
        _seed_robot_parts(g.db)
        _seed_robot_assets_v2(g.db)
        if _repair_legacy_starter_part_rows(g.db) > 0:
            g.db.commit()
        _seed_milestones(g.db)
        _ensure_main_admin_account_ready(g.db)
        if not PART_OFFSET_CACHE:
            refresh_part_offset_cache(g.db)
    return g.db


def _add_initial_robots(db, user_id):
    rows = db.execute(
        "SELECT id, head, right_arm, left_arm, legs FROM robots_master ORDER BY RANDOM() LIMIT 3"
    ).fetchall()
    if not rows:
        return
    now = int(time.time())
    for r in rows:
        db.execute(
            "INSERT INTO user_robots (user_id, head, right_arm, left_arm, legs, obtained_at, master_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, r["head"], r["right_arm"], r["left_arm"], r["legs"], now, r["id"]),
        )


def _starter_part_rows(db):
    out = {}
    for ptype in ("HEAD", "RIGHT_ARM", "LEFT_ARM", "LEGS"):
        row = db.execute(
            """
            SELECT *
            FROM robot_parts
            WHERE is_active = 1 AND part_type = ?
            ORDER BY CASE WHEN UPPER(COALESCE(rarity, 'N')) = 'N' THEN 0 ELSE 1 END, id ASC
            LIMIT 1
            """,
            (ptype,),
        ).fetchone()
        if not row:
            return None
        out[ptype] = row
    return out


def initialize_new_user(db, user_id, *, apply_admin_setup=True):
    user = db.execute(
        "SELECT id, username, is_admin, active_robot_id, max_unlocked_layer FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if not user:
        return {"ok": False, "created_robot": False, "created_inventory_set": False, "reason": "user_not_found"}

    db.execute(
        "UPDATE users SET max_unlocked_layer = CASE WHEN max_unlocked_layer IS NULL OR max_unlocked_layer < 1 THEN 1 ELSE max_unlocked_layer END WHERE id = ?",
        (user_id,),
    )

    starter_parts = _starter_part_rows(db)
    if not starter_parts:
        return {"ok": False, "created_robot": False, "created_inventory_set": False, "reason": "starter_parts_missing"}

    created_robot = False
    created_inventory_set = False
    active_robot_id = user["active_robot_id"]
    active_count = db.execute(
        "SELECT COUNT(*) AS c FROM robot_instances WHERE user_id = ? AND status != 'decomposed'",
        (user_id,),
    ).fetchone()["c"]

    if int(active_count or 0) == 0:
        robot_id = _create_robot_instance(
            db,
            user_id=user_id,
            robot_name="Starter Unit",
            head_key=starter_parts["HEAD"]["key"],
            r_arm_key=starter_parts["RIGHT_ARM"]["key"],
            l_arm_key=starter_parts["LEFT_ARM"]["key"],
            legs_key=starter_parts["LEGS"]["key"],
            status="active",
            combat_mode="normal",
        )
        equipped = {
            "head": _create_part_instance_from_master(db, user_id, starter_parts["HEAD"], plus=0),
            "r_arm": _create_part_instance_from_master(db, user_id, starter_parts["RIGHT_ARM"], plus=0),
            "l_arm": _create_part_instance_from_master(db, user_id, starter_parts["LEFT_ARM"], plus=0),
            "legs": _create_part_instance_from_master(db, user_id, starter_parts["LEGS"], plus=0),
        }
        _equip_part_instances_on_robot(db, robot_id, equipped)
        parts_row = db.execute("SELECT * FROM robot_instance_parts WHERE robot_instance_id = ?", (robot_id,)).fetchone()
        if parts_row:
            try:
                _compose_instance_image(db, {"id": robot_id}, parts_row)
            except Exception:
                # 初期化の本質は「行動可能な初期ロボ付与」。画像生成失敗ではロールバックしない。
                pass
        db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (robot_id, user_id))
        active_robot_id = robot_id
        created_robot = True
    elif not active_robot_id:
        first_active = db.execute(
            """
            SELECT id
            FROM robot_instances
            WHERE user_id = ? AND status = 'active'
            ORDER BY id ASC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        if first_active:
            db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (int(first_active["id"]), user_id))
            active_robot_id = int(first_active["id"])

    for ptype in ("HEAD", "RIGHT_ARM", "LEFT_ARM", "LEGS"):
        part_key = starter_parts[ptype]["key"]
        inv_count = db.execute(
            """
            SELECT COUNT(*) AS c
            FROM part_instances pi
            JOIN robot_parts rp ON rp.id = pi.part_id
            WHERE pi.user_id = ? AND pi.status = 'inventory' AND rp.key = ?
            """,
            (user_id, part_key),
        ).fetchone()["c"]
        if int(inv_count or 0) <= 0:
            _create_part_instance_from_master(db, user_id, starter_parts[ptype], plus=0)
            created_inventory_set = True

    result = {
        "ok": True,
        "created_robot": bool(created_robot),
        "created_inventory_set": bool(created_inventory_set),
        "active_robot_id": (int(active_robot_id) if active_robot_id else None),
    }
    if apply_admin_setup and _is_main_admin_user_row(user):
        admin_state = _apply_main_admin_account_state(db, int(user_id))
        result["main_admin_bootstrap"] = {
            "granted_parts": int(admin_state.get("granted_parts") or 0),
            "equipped_fire_loadout": bool(admin_state.get("equipped_fire_loadout")),
            "changed": bool(admin_state.get("changed")),
        }
    return result


def _seed_robot_parts(db):
    bb_count = db.execute("SELECT COUNT(*) AS c FROM base_bodies").fetchone()["c"]
    if bb_count == 0:
        db.executemany(
            "INSERT INTO base_bodies (name, sprite_path) VALUES (?, ?)",
            [
                ("normal", "base_bodies/normal.png"),
                ("angel", "base_bodies/angel.png"),
                ("devil", "base_bodies/devil.png"),
            ],
        )
    part_count = db.execute("SELECT COUNT(*) AS c FROM parts").fetchone()["c"]
    if part_count == 0:
        items = []
        for i in range(1, 11):
            items.append((f"HEAD-{i}", "HEAD", f"parts/head/{i}.png", 2, 1, 1, 3))
            items.append((f"R-ARM-{i}", "RIGHT_ARM", f"parts/right_arm/{i}.png", 2, 1, 1, 2))
            items.append((f"L-ARM-{i}", "LEFT_ARM", f"parts/left_arm/{i}.png", 2, 1, 1, 2))
            items.append((f"LEGS-{i}", "LEGS", f"parts/legs/{i}.png", 1, 2, 2, 3))
        db.executemany(
            "INSERT INTO parts (name, type, sprite_path, attack, defense, speed, hp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            items,
        )
        db.commit()


def _seed_robot_assets_v2(db):
    base_count = db.execute("SELECT COUNT(*) AS c FROM robot_bases").fetchone()["c"]
    if base_count == 0:
        db.executemany(
            "INSERT INTO robot_bases (key, image_path) VALUES (?, ?)",
            [
                ("normal", "base_bodies/normal.png"),
                ("angel", "base_bodies/angel.png"),
                ("devil", "base_bodies/devil.png"),
            ],
        )
    part_count = db.execute("SELECT COUNT(*) AS c FROM robot_parts").fetchone()["c"]
    if part_count == 0:
        now = int(time.time())
        items = []
        for i in range(1, 11):
            items.append(("HEAD", f"head_{i}", f"parts/head/{i}.png", "N", "NORMAL", "S1", 0, 0, now))
            items.append(("RIGHT_ARM", f"r_arm_{i}", f"parts/right_arm/{i}.png", "N", "NORMAL", "S1", 0, 0, now))
            items.append(("LEFT_ARM", f"l_arm_{i}", f"parts/left_arm/{i}.png", "N", "NORMAL", "S1", 0, 0, now))
            items.append(("LEGS", f"legs_{i}", f"parts/legs/{i}.png", "N", "NORMAL", "S1", 0, 0, now))
        db.executemany(
            "INSERT INTO robot_parts (part_type, key, image_path, rarity, element, series, offset_x, offset_y, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            items,
        )
        db.commit()
    if _backfill_part_display_names(db) > 0:
        db.commit()


def _repair_legacy_starter_part_rows(db):
    updates = [
        ("head_1", "parts/head/head_n_normal.png", "HEAD"),
        ("r_arm_1", "parts/right_arm/right_arm_n_normal.png", "RIGHT_ARM"),
        ("l_arm_1", "parts/left_arm/left_arm_n_normal.png", "LEFT_ARM"),
        ("legs_1", "parts/legs/legs_n_normal.png", "LEGS"),
    ]
    changed = 0
    for key, image_path, part_type in updates:
        row = db.execute(
            """
            SELECT id, image_path, rarity, element, series, part_type
            FROM robot_parts
            WHERE key = ?
            LIMIT 1
            """,
            (key,),
        ).fetchone()
        if not row:
            continue
        next_values = (
            image_path,
            "N",
            "NORMAL",
            "n1",
            part_type,
            1,
        )
        current_values = (
            row["image_path"],
            (row["rarity"] or "").upper(),
            (row["element"] or "").upper(),
            row["series"] or "",
            row["part_type"],
            1,
        )
        if current_values == next_values:
            continue
        db.execute(
            """
            UPDATE robot_parts
            SET image_path = ?, rarity = ?, element = ?, series = ?, part_type = ?, is_active = 1
            WHERE key = ?
            """,
            (image_path, "N", "NORMAL", "n1", part_type, key),
        )
        changed += 1
    return changed


def _seed_milestones(db):
    count = db.execute("SELECT COUNT(*) AS c FROM robot_milestones").fetchone()["c"]
    if count == 0:
        db.executemany(
            """
            INSERT INTO robot_milestones (
                milestone_key, metric, threshold_value, reward_head_key, reward_r_arm_key, reward_l_arm_key, reward_legs_key, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            [
                ("wins_3", "wins", 3, "head_1", "r_arm_1", "l_arm_1", "legs_1"),
                ("wins_10", "wins", 10, "head_2", "r_arm_2", "l_arm_2", "legs_2"),
            ],
        )
        db.commit()


def _ensure_qol_entitlement(db, user_id):
    row = db.execute("SELECT user_id FROM qol_entitlements WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        db.execute(
            """
            INSERT INTO qol_entitlements (user_id, slot_bonus, showcase_slots, active_slot_bonus, decompose_speed_bonus, cosmetic_flags, updated_at)
            VALUES (?, 0, 1, 0, 0, '', ?)
            """,
            (user_id, int(time.time())),
        )
        db.commit()


def _count_part_inventory(db, user_id):
    return int(
        db.execute(
            "SELECT COUNT(*) AS c FROM part_instances WHERE user_id = ? AND status = 'inventory'",
            (user_id,),
        ).fetchone()["c"]
        or 0
    )


def _count_part_overflow(db, user_id):
    return int(
        db.execute(
            "SELECT COUNT(*) AS c FROM part_instances WHERE user_id = ? AND status = 'overflow'",
            (user_id,),
        ).fetchone()["c"]
        or 0
    )


def _count_part_legacy_storage(db, user_id):
    return int(
        db.execute(
            "SELECT COUNT(*) AS c FROM user_parts_inventory WHERE user_id = ?",
            (user_id,),
        ).fetchone()["c"]
        or 0
    )


def _part_storage_snapshot(db, user_id):
    inventory_count = _count_part_inventory(db, user_id)
    overflow_count = _count_part_overflow(db, user_id)
    legacy_count = _count_part_legacy_storage(db, user_id)
    return {
        "inventory_count": int(inventory_count),
        "overflow_count": int(overflow_count),
        "legacy_count": int(legacy_count),
        "storage_count": int(overflow_count + legacy_count),
    }


def _inventory_space_remaining(db, user_id, user_row=None):
    if user_row is None:
        user_row = db.execute(
            "SELECT id, part_inventory_limit FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if not user_row:
        return 0
    limit = int(user_row["part_inventory_limit"] or 0)
    used = _count_part_inventory(db, user_id)
    return max(0, limit - used)


def _next_part_instance_status(db, user_id, user_row=None):
    return "inventory" if _inventory_space_remaining(db, user_id, user_row=user_row) > 0 else "overflow"


def _return_part_instance_to_pool(db, user_id, part_instance_id, user_row=None):
    next_status = _next_part_instance_status(db, user_id, user_row=user_row)
    db.execute(
        "UPDATE part_instances SET status = ?, updated_at = datetime('now') WHERE id = ? AND user_id = ?",
        (next_status, int(part_instance_id), int(user_id)),
    )
    return next_status


def _effective_limits(db, user):
    ent = db.execute("SELECT * FROM qol_entitlements WHERE user_id = ?", (user["id"],)).fetchone()
    slot_bonus = ent["slot_bonus"] if ent else 0
    showcase_slots = ent["showcase_slots"] if ent else 1
    return {
        "robot_slots": user["robot_slot_limit"] + slot_bonus,
        "part_inventory": user["part_inventory_limit"],
        "showcase_slots": showcase_slots,
    }


def _create_robot_instance(
    db,
    user_id,
    robot_name,
    head_key,
    r_arm_key,
    l_arm_key,
    legs_key,
    decor_asset_id=None,
    status="active",
    personality=None,
    combat_mode="normal",
):
    now = int(time.time())
    if not personality:
        personality = pick_personality()
    cur = db.execute(
        """
        INSERT INTO robot_instances (user_id, name, status, personality, combat_mode, style_key, style_stats_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'stable', '{}', ?, ?)
        """,
        (user_id, robot_name, status, personality, _normalize_combat_mode(combat_mode), now, now),
    )
    instance_id = cur.lastrowid
    db.execute(
        """
        INSERT INTO robot_instance_parts (robot_instance_id, head_key, r_arm_key, l_arm_key, legs_key, decor_asset_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (instance_id, head_key, r_arm_key, l_arm_key, legs_key, decor_asset_id),
    )
    return instance_id


def _add_part_drop(
    db,
    user_id,
    part_type=None,
    part_key=None,
    source="battle_drop",
    robot_instance_id=None,
    rarity=None,
    plus=0,
    as_instance=False,
    announce_username=None,
    area_key=None,
):
    rarity_code = (rarity or "").upper()
    if part_type is None or part_key is None:
        part = _pick_drop_part_master(db, rarity=rarity, area_key=area_key) if rarity else None
        if rarity_code == "R" and not part:
            return None
        if not part:
            part = db.execute(
                """
                SELECT * FROM robot_parts
                WHERE is_active = 1
                  AND (UPPER(COALESCE(rarity, '')) != 'R' OR is_unlocked = 1)
                ORDER BY RANDOM() LIMIT 1
                """
            ).fetchone()
        if not part:
            return None
        part_type = part["part_type"] if part_type is None else part_type
        part_key = part["key"] if part_key is None else part_key
    else:
        part = _get_part_by_key(db, part_key)

    create_as_instance = bool(as_instance or source == "battle_drop")
    if create_as_instance and part:
        storage_status = _next_part_instance_status(db, user_id)
        pi_id = _create_part_instance_from_master(
            db,
            user_id,
            part,
            plus=int(plus),
            area_key=area_key,
            status=storage_status,
        )
        tendency = _area_growth_tendency(area_key)
        if announce_username:
            pi_row = db.execute("SELECT * FROM part_instances WHERE id = ?", (pi_id,)).fetchone()
            if pi_row:
                _maybe_post_research_title(db, user_id, announce_username, dict(pi_row))
        return {
            "part_type": part["part_type"],
            "part_key": part["key"],
            "rarity": part["rarity"],
            "plus": int(plus),
            "part_instance_id": pi_id,
            "source": source,
            "storage_status": storage_status,
            "growth_tendency_key": (tendency.get("key") if tendency else None),
            "growth_tendency_label": (tendency.get("label") if tendency else None),
        }
    db.execute(
        """
        INSERT INTO user_parts_inventory (user_id, part_type, part_key, obtained_at, source, robot_instance_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, part_type, part_key, int(time.time()), source, robot_instance_id),
    )
    return {"part_type": part_type, "part_key": part_key, "source": source}


def _drop_audit_payload(area_key, battle_no, dropped_part):
    row = dropped_part or {}
    return {
        "area_key": area_key,
        "battle_no": battle_no,
        "drop_type": row.get("drop_type"),
        "part_type": row.get("part_type"),
        "part_key": row.get("part_key"),
        "rarity": row.get("rarity"),
        "plus": row.get("plus"),
        "storage_status": row.get("storage_status"),
        "growth_tendency_key": row.get("growth_tendency_key"),
        "growth_tendency_label": row.get("growth_tendency_label"),
    }


def _ensure_user_item_row(db, user_id, item_key):
    db.execute(
        """
        INSERT INTO user_items (user_id, item_key, qty)
        VALUES (?, ?, 0)
        ON CONFLICT(user_id, item_key) DO NOTHING
        """,
        (user_id, item_key),
    )


def _get_user_item_qty(db, user_id, item_key):
    _ensure_user_item_row(db, user_id, item_key)
    row = db.execute(
        "SELECT qty FROM user_items WHERE user_id = ? AND item_key = ?",
        (user_id, item_key),
    ).fetchone()
    return row["qty"] if row else 0


def _ensure_player_core_row(db, user_id, core_key):
    db.execute(
        """
        INSERT OR IGNORE INTO user_core_inventory (user_id, core_asset_id, quantity, updated_at)
        SELECT ?, ca.id, 0, datetime('now')
        FROM core_assets ca
        WHERE ca.core_key = ? AND ca.is_active = 1
        """,
        (int(user_id), str(core_key)),
    )


def _get_player_core_qty(db, user_id, core_key):
    _ensure_player_core_row(db, user_id, core_key)
    row = db.execute(
        """
        SELECT uci.quantity
        FROM user_core_inventory uci
        JOIN core_assets ca ON ca.id = uci.core_asset_id
        WHERE uci.user_id = ? AND ca.core_key = ?
        """,
        (int(user_id), str(core_key)),
    ).fetchone()
    return int(row["quantity"] or 0) if row else 0


def _grant_player_core(db, user_id, core_key, qty=1):
    grant_qty = max(0, int(qty or 0))
    if grant_qty <= 0:
        return 0
    _ensure_player_core_row(db, user_id, core_key)
    db.execute(
        """
        UPDATE user_core_inventory
        SET quantity = quantity + ?, updated_at = datetime('now')
        WHERE user_id = ?
          AND core_asset_id = (SELECT id FROM core_assets WHERE core_key = ? LIMIT 1)
        """,
        (grant_qty, int(user_id), str(core_key)),
    )
    return grant_qty


def _consume_player_core(db, user_id, core_key, qty=1):
    consume_qty = max(0, int(qty or 0))
    if consume_qty <= 0:
        return False
    current_qty = _get_player_core_qty(db, user_id, core_key)
    if current_qty < consume_qty:
        return False
    db.execute(
        """
        UPDATE user_core_inventory
        SET quantity = quantity - ?, updated_at = datetime('now')
        WHERE user_id = ?
          AND core_asset_id = (SELECT id FROM core_assets WHERE core_key = ? LIMIT 1)
        """,
        (consume_qty, int(user_id), str(core_key)),
    )
    return True


def _get_player_evolution_core_progress(db, user_id):
    row = db.execute(
        "SELECT evolution_core_progress FROM users WHERE id = ?",
        (int(user_id),),
    ).fetchone()
    if not row:
        return 0
    return max(0, int(row["evolution_core_progress"] or 0))


def _evolution_core_progress_status(progress, *, core_qty=0):
    current = max(0, int(progress or 0))
    target = max(1, int(EVOLUTION_CORE_PROGRESS_TARGET))
    if current >= target:
        current = current % target
    remain = max(0, int(target - current))
    if int(core_qty or 0) > 0:
        home_label = f"進化コア {int(core_qty)}個 / 次 {current}/{target}"
    else:
        home_label = f"あと{remain}勝で進化コア"
    return {
        "current": int(current),
        "target": int(target),
        "remaining_wins": int(remain),
        "progress_label": f"進化コア進捗 {int(current)}/{int(target)}",
        "remaining_label": f"あと{int(remain)}勝で進化コア",
        "home_label": home_label,
    }


def _advance_evolution_core_progress(
    db,
    user_id,
    battle_wins,
    *,
    request_id=None,
    action_key="explore",
    area_key=None,
    ip=None,
):
    wins = max(0, int(battle_wins or 0))
    target = max(1, int(EVOLUTION_CORE_PROGRESS_TARGET))
    progress_added = wins * int(EVOLUTION_CORE_PROGRESS_PER_WIN)
    before = _get_player_evolution_core_progress(db, user_id)
    if progress_added <= 0:
        return {
            "wins": wins,
            "progress_added": 0,
            "progress_before": before,
            "progress_after": before,
            "granted_core_qty": 0,
            "target": target,
        }

    total_after_add = int(before + progress_added)
    granted_core_qty = int(total_after_add // target)
    progress_after = int(total_after_add % target)
    db.execute(
        "UPDATE users SET evolution_core_progress = ? WHERE id = ?",
        (progress_after, int(user_id)),
    )
    audit_log(
        db,
        AUDIT_EVENT_TYPES["CORE_PROGRESS"],
        user_id=user_id,
        request_id=request_id,
        action_key=action_key,
        entity_type="core",
        entity_id=None,
        delta_count=int(progress_added),
        payload={
            "core_key": EVOLUTION_CORE_KEY,
            "battle_wins": int(wins),
            "progress_before": int(before),
            "progress_after": int(progress_after),
            "progress_added": int(progress_added),
            "target": int(target),
            "area_key": area_key,
            "granted_core_qty": int(granted_core_qty),
        },
        ip=ip,
    )
    if granted_core_qty > 0:
        granted_core_qty = int(_grant_player_core(db, user_id, EVOLUTION_CORE_KEY, qty=granted_core_qty))
        audit_log(
            db,
            AUDIT_EVENT_TYPES["CORE_GUARANTEE"],
            user_id=user_id,
            request_id=request_id,
            action_key=action_key,
            entity_type="core",
            entity_id=None,
            delta_count=int(granted_core_qty),
            payload={
                "core_key": EVOLUTION_CORE_KEY,
                "quantity": int(granted_core_qty),
                "battle_wins": int(wins),
                "progress_before": int(before),
                "progress_after_add": int(total_after_add),
                "progress_after_reset": int(progress_after),
                "target": int(target),
                "area_key": area_key,
            },
            ip=ip,
        )
        audit_log(
            db,
            AUDIT_EVENT_TYPES["CORE_DROP"],
            user_id=user_id,
            request_id=request_id,
            action_key=action_key,
            entity_type="core",
            entity_id=None,
            delta_count=int(granted_core_qty),
            payload={
                "core_key": EVOLUTION_CORE_KEY,
                "core_name": "進化コア",
                "quantity": int(granted_core_qty),
                "area_key": area_key,
                "source": "progress_guarantee",
                "battle_wins": int(wins),
                "target": int(target),
            },
            ip=ip,
        )
        audit_log(
            db,
            AUDIT_EVENT_TYPES["INVENTORY_DELTA"],
            user_id=user_id,
            request_id=request_id,
            action_key=action_key,
            entity_type="core",
            entity_id=None,
            delta_count=int(granted_core_qty),
            payload={
                "reason": "core_progress_guarantee",
                "core_key": EVOLUTION_CORE_KEY,
                "quantity": int(granted_core_qty),
                "area_key": area_key,
                "battle_wins": int(wins),
            },
            ip=ip,
        )
    return {
        "wins": int(wins),
        "progress_added": int(progress_added),
        "progress_before": int(before),
        "progress_after": int(progress_after),
        "granted_core_qty": int(granted_core_qty),
        "target": int(target),
    }


def _next_rarity_for_evolution(rarity_code):
    rarity = str(rarity_code or "").upper().strip()
    return EVOLUTION_PATH.get(rarity)


def _candidate_evolved_part_keys(base_part_key):
    key = str(base_part_key or "").strip().lower()
    if not key:
        return []
    candidates = []
    if "_n_" in key:
        candidates.append(key.replace("_n_", "_r_", 1))
    if key.endswith("_n"):
        candidates.append(f"{key[:-2]}_r")
    normal_fallback = {
        "head_normal": "head_r_normal",
        "right_arm_normal": "right_arm_r_normal",
        "left_arm_normal": "left_arm_r_normal",
        "legs_normal": "legs_r_normal",
        "head_n_normal": "head_r_normal",
        "right_arm_n_normal": "right_arm_r_normal",
        "left_arm_n_normal": "left_arm_r_normal",
        "legs_n_normal": "legs_r_normal",
    }
    if key in normal_fallback:
        candidates.append(normal_fallback[key])
    unique = []
    seen = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def resolve_evolved_part_key(base_part_key):
    db = get_db()
    for candidate in _candidate_evolved_part_keys(base_part_key):
        row = db.execute(
            """
            SELECT id
            FROM robot_parts
            WHERE key = ? AND is_active = 1 AND UPPER(COALESCE(rarity, '')) = 'R'
            LIMIT 1
            """,
            (candidate,),
        ).fetchone()
        if row:
            return candidate
    return None


def _norm_part_type(part_type):
    if part_type == "R_ARM":
        return "RIGHT_ARM"
    if part_type == "L_ARM":
        return "LEFT_ARM"
    return part_type


def _create_part_instance_from_master(db, user_id, part_row, plus=0, area_key=None, status="inventory"):
    ptype = _norm_part_type(part_row["part_type"])
    weights = generate_noisy_weights(ptype, bias=_area_weight_bias(area_key))
    rarity = (part_row["rarity"] or "N").upper()
    element = (part_row["element"] or "NORMAL").upper()
    series = part_row["series"] or "S1"
    status_key = str(status or "inventory").strip().lower()
    if status_key not in {"inventory", "equipped", "overflow"}:
        status_key = "inventory"
    cur = db.execute(
        """
        INSERT INTO part_instances
        (part_id, user_id, part_type, rarity, element, series, plus, w_hp, w_atk, w_def, w_spd, w_acc, w_cri, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            part_row["id"],
            user_id,
            ptype,
            rarity,
            element,
            series,
            plus,
            weights["w_hp"],
            weights["w_atk"],
            weights["w_def"],
            weights["w_spd"],
            weights["w_acc"],
            weights["w_cri"],
            status_key,
            int(time.time()),
        ),
    )
    return cur.lastrowid


def _take_or_materialize_part_instance(db, user_id, part_key):
    # Prefer existing individual parts first.
    row = db.execute(
        """
        SELECT pi.id
        FROM part_instances pi
        JOIN robot_parts rp ON rp.id = pi.part_id
        WHERE pi.user_id = ? AND pi.status = 'inventory' AND rp.key = ?
        ORDER BY pi.plus DESC, pi.id ASC
        LIMIT 1
        """,
        (user_id, part_key),
    ).fetchone()
    if row:
        return row["id"]

    # Lazy migration from old inventory row.
    inv = db.execute(
        """
        SELECT id FROM user_parts_inventory
        WHERE user_id = ? AND part_key = ?
        ORDER BY obtained_at ASC, id ASC
        LIMIT 1
        """,
        (user_id, part_key),
    ).fetchone()
    if not inv:
        return None
    part = _get_part_by_key(db, part_key)
    if not part:
        return None
    storage_status = _next_part_instance_status(db, user_id)
    pi_id = _create_part_instance_from_master(db, user_id, part, plus=0, status=storage_status)
    db.execute("DELETE FROM user_parts_inventory WHERE id = ?", (inv["id"],))
    return pi_id


def _equip_part_instances_on_robot(db, robot_instance_id, part_instance_ids):
    db.execute(
        """
        UPDATE robot_instance_parts
        SET head_part_instance_id = ?,
            r_arm_part_instance_id = ?,
            l_arm_part_instance_id = ?,
            legs_part_instance_id = ?
        WHERE robot_instance_id = ?
        """,
        (
            part_instance_ids["head"],
            part_instance_ids["r_arm"],
            part_instance_ids["l_arm"],
            part_instance_ids["legs"],
            robot_instance_id,
        ),
    )
    for pi_id in part_instance_ids.values():
        db.execute("UPDATE part_instances SET status = 'equipped' WHERE id = ?", (pi_id,))


def _ensure_robot_instance_part_instances(db, robot_instance_id):
    row = db.execute(
        """
        SELECT *
        FROM robot_instance_parts
        WHERE robot_instance_id = ?
        """,
        (robot_instance_id,),
    ).fetchone()
    if not row:
        return None
    mapping = {
        "head": row["head_part_instance_id"] if "head_part_instance_id" in row.keys() else None,
        "r_arm": row["r_arm_part_instance_id"] if "r_arm_part_instance_id" in row.keys() else None,
        "l_arm": row["l_arm_part_instance_id"] if "l_arm_part_instance_id" in row.keys() else None,
        "legs": row["legs_part_instance_id"] if "legs_part_instance_id" in row.keys() else None,
    }
    user_id = db.execute(
        "SELECT user_id FROM robot_instances WHERE id = ?",
        (robot_instance_id,),
    ).fetchone()["user_id"]
    changed = False
    key_map = {
        "head": row["head_key"],
        "r_arm": row["r_arm_key"],
        "l_arm": row["l_arm_key"],
        "legs": row["legs_key"],
    }
    for slot, key in key_map.items():
        if mapping[slot]:
            continue
        part = _get_part_by_key(db, key)
        if not part:
            continue
        mapping[slot] = _create_part_instance_from_master(db, user_id, part, plus=0)
        db.execute("UPDATE part_instances SET status = 'equipped' WHERE id = ?", (mapping[slot],))
        changed = True
    if changed:
        db.execute(
            """
            UPDATE robot_instance_parts
            SET head_part_instance_id = ?,
                r_arm_part_instance_id = ?,
                l_arm_part_instance_id = ?,
                legs_part_instance_id = ?
            WHERE robot_instance_id = ?
            """,
            (mapping["head"], mapping["r_arm"], mapping["l_arm"], mapping["legs"], robot_instance_id),
        )
    return mapping


def _compute_robot_stats_for_instance(db, robot_instance_id):
    mapping = _ensure_robot_instance_part_instances(db, robot_instance_id)
    if not mapping or not all(mapping.values()):
        return None
    rows = db.execute(
        f"""
        SELECT pi.*, rp.part_type, rp.key
        FROM part_instances pi
        JOIN robot_parts rp ON rp.id = pi.part_id
        WHERE pi.id IN ({",".join(["?"] * 4)})
        """,
        [mapping["head"], mapping["r_arm"], mapping["l_arm"], mapping["legs"]],
    ).fetchall()
    if len(rows) != 4:
        return None
    by_type = {_norm_part_type(r["part_type"]): dict(r) for r in rows}
    if not all(t in by_type for t in ("HEAD", "RIGHT_ARM", "LEFT_ARM", "LEGS")):
        return None
    ordered = [by_type["HEAD"], by_type["RIGHT_ARM"], by_type["LEFT_ARM"], by_type["LEGS"]]
    calc = compute_robot_stats(ordered)
    archetype = compute_archetype(ordered)
    computed_style = _robot_style_from_final_stats(calc["stats"])
    row = db.execute(
        "SELECT style_key FROM robot_instances WHERE id = ?",
        (int(robot_instance_id),),
    ).fetchone()
    stored_style_key = _normalize_style_key(row["style_key"] if row and "style_key" in row.keys() else None)
    if stored_style_key != computed_style["style_key"]:
        db.execute(
            "UPDATE robot_instances SET style_key = ? WHERE id = ?",
            (computed_style["style_key"], int(robot_instance_id)),
        )
        stored_style_key = computed_style["style_key"]
    robot_style = _robot_style_from_instance_key(stored_style_key)
    return {
        "stats": calc["stats"],
        "power": calc["power"],
        "set_bonus": calc["set_bonus"],
        "parts": ordered,
        "archetype": archetype,
        "robot_style": robot_style,
    }


def _robot_weekly_fit(db, robot_instance_id, weekly_element):
    if not weekly_element:
        return False
    row = db.execute(
        "SELECT head_key, r_arm_key, l_arm_key, legs_key FROM robot_instance_parts WHERE robot_instance_id = ?",
        (robot_instance_id,),
    ).fetchone()
    if not row:
        return False
    element = _build_element_from_keys(db, row["head_key"], row["r_arm_key"], row["l_arm_key"], row["legs_key"])
    return element == weekly_element


def _preview_part_payload_for_key(db, user_id, part_key):
    """Return an estimate payload for build preview without mutating inventory."""
    row = db.execute(
        """
        SELECT pi.*, rp.part_type, rp.key, rp.rarity AS master_rarity, rp.element AS master_element
        FROM part_instances pi
        JOIN robot_parts rp ON rp.id = pi.part_id
        WHERE pi.user_id = ? AND pi.status = 'inventory' AND rp.key = ?
        ORDER BY pi.plus DESC, pi.id ASC
        LIMIT 1
        """,
        (user_id, part_key),
    ).fetchone()
    if row:
        return dict(row)

    part = _get_part_by_key(db, part_key)
    if not part:
        return None
    weights = generate_noisy_weights(_norm_part_type(part["part_type"]), noise=0.0)
    return {
        "part_type": part["part_type"],
        "key": part["key"],
        "series": part["series"],
        "rarity": (part["rarity"] or "N").upper(),
        "element": (part["element"] or "NORMAL").upper(),
        "plus": 0,
        **weights,
    }


def _build_stat_comparison_rows(current_stats, candidate_stats):
    cur = dict(current_stats or {})
    cand = dict(candidate_stats or {})
    rows = []
    for key in ("hp", "atk", "def", "spd", "acc", "cri", "power"):
        label = _stat_label(key)
        current_val = float(cur.get(key) or 0.0)
        candidate_val = float(cand.get(key) or 0.0)
        delta = candidate_val - current_val
        if key != "power":
            current_show = int(round(current_val))
            candidate_show = int(round(candidate_val))
            delta_show = int(round(delta))
        else:
            current_show = round(current_val, 1)
            candidate_show = round(candidate_val, 1)
            delta_show = round(delta, 1)
        rows.append(
            {
                "key": key,
                "label": label,
                "current": current_show,
                "candidate": candidate_show,
                "delta": delta_show,
                "delta_text": (f"+{delta_show}" if delta_show > 0 else str(delta_show)),
            }
        )
    return rows


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _seed_enemies(db):
    for key, s in ENEMY_SEED_STATS.items():
        db.execute(
            """
            INSERT INTO enemies
            (key, name_ja, image_path, tier, element, hp, atk, def, spd, acc, cri, faction, trait, is_boss, boss_area_key, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(key) DO UPDATE SET
                name_ja = excluded.name_ja,
                image_path = excluded.image_path,
                tier = excluded.tier,
                element = excluded.element,
                hp = excluded.hp,
                atk = excluded.atk,
                def = excluded.def,
                spd = excluded.spd,
                acc = excluded.acc,
                cri = excluded.cri,
                faction = excluded.faction,
                trait = excluded.trait,
                is_boss = excluded.is_boss,
                boss_area_key = excluded.boss_area_key
            """,
            (
                key,
                s["name_ja"],
                s["image_path"],
                s["tier"],
                s["element"],
                s["hp"],
                s["atk"],
                s["def"],
                s["spd"],
                s["acc"],
                s["cri"],
                s.get("faction", "neutral"),
                s.get("trait"),
                int(s.get("is_boss", 0)),
                s.get("boss_area_key"),
            ),
        )


def _apply_default_enemy_traits(db):
    for enemy_key, trait in DEFAULT_NORMAL_ENEMY_TRAITS.items():
        db.execute(
            """
            UPDATE enemies
            SET trait = ?
            WHERE key = ?
              AND COALESCE(is_boss, 0) = 0
            """,
            (trait, enemy_key),
        )


def _weighted_pick(weight_map):
    keys = list(weight_map.keys())
    weights = [weight_map[k] for k in keys]
    return random.choices(keys, weights=weights, k=1)[0]


def _explore_part_drop_budget(total_fights):
    return MAX_PART_DROPS_CHAIN if int(total_fights or 0) > 1 else MAX_PART_DROPS_NORMAL


def _roll_battle_rewards(
    db,
    user_id,
    tier,
    weekly_env=None,
    enemy_element=None,
    announce_username=None,
    part_drop_budget=None,
    area_key=None,
):
    tier = int(tier or 1)
    coin = COIN_REWARD_BY_TIER.get(tier, 2)
    drop_type = _weighted_pick(DROP_TYPE_WEIGHTS_BY_TIER.get(tier, DROP_TYPE_WEIGHTS_BY_TIER[1]))
    promotion_triggered = False
    if (
        weekly_env
        and enemy_element
        and enemy_element.upper() == (weekly_env.get("element") or "").upper()
        and drop_type == "coin_only"
        and random.random() < float(weekly_env.get("drop_bonus") or 0.0)
    ):
        drop_type = "parts_1"
        promotion_triggered = True
        _world_event_log(
            db,
            "weekly_drop_promoted",
            {
                "week_key": _world_week_key(),
                "user_id": user_id,
                "enemy_element": enemy_element.upper(),
                "weekly_element": (weekly_env.get("element") or "").upper(),
                "drop_bonus": float(weekly_env.get("drop_bonus") or 0.0),
            },
        )
    dropped = []
    suppressed_by_budget = 0
    if drop_type != "coin_only":
        part_count = 1 if drop_type == "parts_1" else 2
        allowed_part_count = part_count
        if part_drop_budget is not None:
            allowed_part_count = max(0, min(part_count, int(part_drop_budget)))
            suppressed_by_budget = max(0, part_count - allowed_part_count)
        for _ in range(allowed_part_count):
            profile = EXPLORE_DROP_PROFILE_BY_AREA.get(str(area_key or "").strip(), {})
            rarity_weights = profile.get("rarity_weights")
            if rarity_weights:
                rarity = _weighted_pick(rarity_weights)
            else:
                rarity = _weighted_pick(RARITY_WEIGHTS_BY_TIER.get(tier, RARITY_WEIGHTS_BY_TIER[1]))
            plus = int(_weighted_pick(PLUS_WEIGHTS_BY_TIER.get(tier, PLUS_WEIGHTS_BY_TIER[1])))
            pd = _add_part_drop(
                db,
                user_id,
                source="battle_drop",
                rarity=rarity,
                plus=plus,
                as_instance=True,
                announce_username=announce_username,
                area_key=area_key,
            )
            if pd:
                dropped.append(pd)
    return {
        "coin": coin,
        "drop_type": drop_type,
        "dropped_parts": dropped,
        "promotion_triggered": promotion_triggered,
        "suppressed_part_drops": int(suppressed_by_budget),
    }


def _pick_enemy_from_rows(rows, area_key, weekly_env=None, rng=None):
    if not rows:
        return None
    roller = rng or random
    tier_weights = EXPLORE_AREA_TIER_WEIGHTS.get(area_key, {})
    rows_by_tier = {}
    for r in rows:
        t = int(r["tier"])
        rows_by_tier.setdefault(t, []).append(r)

    active_tiers = [t for t in tier_weights.keys() if rows_by_tier.get(t)]
    if active_tiers:
        picked_tier = roller.choices(
            active_tiers,
            weights=[float(tier_weights[t]) for t in active_tiers],
            k=1,
        )[0]
        candidates = rows_by_tier[picked_tier]
    else:
        candidates = rows

    use_mist_modifier = area_key == "layer_2_mist"
    use_rush_modifier = area_key == "layer_2_rush"
    tier_avg_acc = None
    tier_avg_cri = None
    if use_mist_modifier and candidates:
        tier_avg_acc = sum(int(r["acc"]) for r in candidates) / len(candidates)
    if use_rush_modifier and candidates:
        tier_avg_cri = sum(int(r["cri"]) for r in candidates) / len(candidates)

    if weekly_env or use_mist_modifier or use_rush_modifier:
        env_element = (weekly_env.get("element") or "").upper() if weekly_env else ""
        bonus = float(weekly_env.get("enemy_spawn_bonus") or 0.0) if weekly_env else 0.0
        weights = []
        for r in candidates:
            w = 1.0
            if weekly_env and (r["element"] or "").upper() == env_element:
                w += bonus
            if use_mist_modifier and tier_avg_acc is not None:
                mist_modifier = 1.0 + (int(r["acc"]) - float(tier_avg_acc)) * 0.02
                mist_modifier = _clamp(mist_modifier, 0.85, 1.15)
                w *= mist_modifier
            if use_rush_modifier and tier_avg_cri is not None:
                rush_modifier = 1.0 + (int(r["cri"]) - float(tier_avg_cri)) * 0.03
                rush_modifier = _clamp(rush_modifier, 0.85, 1.15)
                w *= rush_modifier
            weights.append(w)
        return roller.choices(candidates, weights=weights, k=1)[0]
    return roller.choice(candidates)


def _pick_enemy_for_area(db, area_key, weekly_env=None):
    tiers = EXPLORE_AREA_TIERS.get(area_key, (1,))
    placeholders = ",".join(["?"] * len(tiers))
    allowed_keys = tuple(EXPLORE_AREA_ENEMY_KEYS.get(str(area_key or "").strip(), ()))
    if allowed_keys:
        key_placeholders = ",".join(["?"] * len(allowed_keys))
        rows = db.execute(
            f"""
            SELECT * FROM enemies
            WHERE is_active = 1
              AND COALESCE(is_boss, 0) = 0
              AND tier IN ({placeholders})
              AND key IN ({key_placeholders})
            """,
            [*list(tiers), *list(allowed_keys)],
        ).fetchall()
    else:
        rows = db.execute(
            f"""
            SELECT * FROM enemies
            WHERE is_active = 1
              AND COALESCE(is_boss, 0) = 0
              AND tier IN ({placeholders})
            """,
            list(tiers),
        ).fetchall()
    if rows:
        return _pick_enemy_from_rows(rows, area_key, weekly_env=weekly_env, rng=random)
    return {
        "key": "training_drone",
        "name_ja": "訓練ドローン",
        "image_path": "enemies/_placeholder.png",
        "tier": int(tiers[0]) if tiers else 1,
        "element": "NORMAL",
        "faction": "neutral",
        "hp": 18,
        "atk": 8,
        "def": 6,
        "spd": 7,
        "acc": 8,
        "cri": 4,
    }


def _consume_part_by_key(db, user_id, part_key):
    row = db.execute(
        """
        SELECT id FROM user_parts_inventory
        WHERE user_id = ? AND part_key = ?
        ORDER BY obtained_at ASC, id ASC
        LIMIT 1
        """,
        (user_id, part_key),
    ).fetchone()
    if not row:
        return False
    db.execute("DELETE FROM user_parts_inventory WHERE id = ?", (row["id"],))
    return True


def _compose_instance_image(db, instance_row, parts_row):
    rel_path = f"robot_composed/instance_{instance_row['id']}.png"
    out_path = os.path.join(BASE_DIR, "static", rel_path)
    head = _get_part_by_key(db, parts_row["head_key"])
    r_arm = _get_part_by_key(db, parts_row["r_arm_key"])
    l_arm = _get_part_by_key(db, parts_row["l_arm_key"])
    legs = _get_part_by_key(db, parts_row["legs_key"])
    decor = _get_decor_asset_by_id(db, parts_row["decor_asset_id"] if "decor_asset_id" in parts_row.keys() else None)
    if not all([head, r_arm, l_arm, legs]):
        return None
    compose_robot(
        {"path": _asset_abs(head["image_path"]), "x": head["offset_x"], "y": head["offset_y"]},
        {"path": _asset_abs(r_arm["image_path"]), "x": r_arm["offset_x"], "y": r_arm["offset_y"]},
        {"path": _asset_abs(l_arm["image_path"]), "x": l_arm["offset_x"], "y": l_arm["offset_y"]},
        {"path": _asset_abs(legs["image_path"]), "x": legs["offset_x"], "y": legs["offset_y"]},
        out_path,
        _decor_layer_or_none(decor),
    )
    db.execute(
        "UPDATE robot_instances SET composed_image_path = ?, updated_at = ? WHERE id = ?",
        (rel_path, int(time.time()), instance_row["id"]),
    )
    db.commit()
    _ensure_robot_instance_badge(db, instance_row["id"], rel_path)
    return rel_path


def _reuse_or_compose_instance_image(db, instance_id, build_row, parts_row):
    instance_rel = f"robot_composed/instance_{instance_id}.png"
    instance_abs = os.path.join(BASE_DIR, "static", instance_rel)
    build_rel = None
    if build_row is not None and "composed_image_path" in build_row.keys():
        build_rel = build_row["composed_image_path"]
    if build_rel:
        build_abs = os.path.join(BASE_DIR, "static", build_rel)
        if os.path.exists(build_abs):
            os.makedirs(os.path.dirname(instance_abs), exist_ok=True)
            shutil.copyfile(build_abs, instance_abs)
            db.execute(
                "UPDATE robot_instances SET composed_image_path = ?, updated_at = ? WHERE id = ?",
                (instance_rel, int(time.time()), instance_id),
            )
            db.commit()
            _ensure_robot_instance_badge(db, instance_id, instance_rel)
            return instance_rel
    return _compose_instance_image(db, {"id": instance_id}, parts_row)


def _compose_instance_assets_no_commit(db, instance_id, parts_row):
    rel_path = f"robot_composed/instance_{instance_id}.png"
    out_path = os.path.join(BASE_DIR, "static", rel_path)
    head = _get_part_by_key(db, parts_row["head_key"])
    r_arm = _get_part_by_key(db, parts_row["r_arm_key"])
    l_arm = _get_part_by_key(db, parts_row["l_arm_key"])
    legs = _get_part_by_key(db, parts_row["legs_key"])
    decor = _get_decor_asset_by_id(db, parts_row.get("decor_asset_id"))
    if not all([head, r_arm, l_arm, legs]):
        raise ValueError("パーツ構成が不正です。")

    compose_robot(
        {"path": _asset_abs(head["image_path"]), "x": head["offset_x"], "y": head["offset_y"]},
        {"path": _asset_abs(r_arm["image_path"]), "x": r_arm["offset_x"], "y": r_arm["offset_y"]},
        {"path": _asset_abs(l_arm["image_path"]), "x": l_arm["offset_x"], "y": l_arm["offset_y"]},
        {"path": _asset_abs(legs["image_path"]), "x": legs["offset_x"], "y": legs["offset_y"]},
        out_path,
        _decor_layer_or_none(decor),
    )

    badge_rel = f"robot_icons/{instance_id}.png"
    badge_abs = _static_abs(badge_rel)
    if not _generate_robot_badge_from_composed(rel_path, badge_abs):
        default_abs = _static_abs(DEFAULT_BADGE_REL)
        os.makedirs(os.path.dirname(badge_abs), exist_ok=True)
        shutil.copyfile(default_abs, badge_abs)

    db.execute(
        "UPDATE robot_instances SET composed_image_path = ?, icon_32_path = ?, updated_at = ? WHERE id = ?",
        (rel_path, badge_rel, int(time.time()), instance_id),
    )
    return rel_path, badge_rel


def _ensure_showcase_slots(db, user_id, max_slots):
    existing = {
        row["slot_no"]
        for row in db.execute(
            "SELECT slot_no FROM user_showcase WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    }
    for slot_no in range(1, max_slots + 1):
        if slot_no not in existing:
            db.execute(
                "INSERT INTO user_showcase (user_id, slot_no, robot_instance_id) VALUES (?, ?, NULL)",
                (user_id, slot_no),
            )
    db.commit()


def _showcase_rows(db, user_id):
    rows = db.execute(
        """
        SELECT us.slot_no, us.robot_instance_id, ri.name, ri.status, ri.composed_image_path, ri.updated_at
        FROM user_showcase us
        LEFT JOIN robot_instances ri ON ri.id = us.robot_instance_id
        WHERE us.user_id = ?
        ORDER BY us.slot_no ASC
        """,
        (user_id,),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["image_url"] = _composed_image_url(item.get("composed_image_path"), item.get("updated_at"))
        out.append(item)
    return out


def _evaluate_milestones(db, user):
    milestones = db.execute(
        "SELECT * FROM robot_milestones WHERE active = 1 ORDER BY threshold_value ASC"
    ).fetchall()
    claims = {
        row["milestone_key"]
        for row in db.execute(
            "SELECT milestone_key FROM user_milestone_claims WHERE user_id = ?",
            (user["id"],),
        ).fetchall()
    }
    available = []
    for m in milestones:
        metric_value = user[m["metric"]] if m["metric"] in user.keys() else 0
        if metric_value >= m["threshold_value"] and m["milestone_key"] not in claims:
            available.append(m)
    return available


def _ensure_dirs():
    os.makedirs(ASSET_ROOT, exist_ok=True)
    os.makedirs(os.path.join(ASSET_ROOT, "base_bodies"), exist_ok=True)
    os.makedirs(os.path.join(ASSET_ROOT, "parts", "head"), exist_ok=True)
    os.makedirs(os.path.join(ASSET_ROOT, "parts", "right_arm"), exist_ok=True)
    os.makedirs(os.path.join(ASSET_ROOT, "parts", "left_arm"), exist_ok=True)
    os.makedirs(os.path.join(ASSET_ROOT, "parts", "legs"), exist_ok=True)
    os.makedirs(COMPOSED_ROOT, exist_ok=True)
    os.makedirs(os.path.join(STATIC_ROOT, "enemies"), exist_ok=True)
    os.makedirs(AVATAR_UPLOAD_ROOT, exist_ok=True)
    os.makedirs(LAB_UPLOAD_ORIGINAL_ROOT, exist_ok=True)
    os.makedirs(LAB_UPLOAD_THUMB_ROOT, exist_ok=True)
    os.makedirs(LAB_SCENE_SPRITE_ROOT, exist_ok=True)
    os.makedirs(ROBOT_ICON_ROOT, exist_ok=True)
    os.makedirs(DEFAULT_ROOT, exist_ok=True)


def _ensure_default_images():
    avatar_abs = os.path.join(STATIC_ROOT, DEFAULT_AVATAR_REL)
    badge_abs = os.path.join(STATIC_ROOT, DEFAULT_BADGE_REL)
    if not os.path.exists(avatar_abs):
        img = Image.new("RGBA", (AVATAR_OUTPUT_SIZE, AVATAR_OUTPUT_SIZE), (35, 40, 52, 255))
        inner = Image.new("RGBA", (36, 36), (88, 190, 180, 255))
        img.alpha_composite(inner, (6, 6))
        img.save(avatar_abs, format="PNG")
    if not os.path.exists(badge_abs):
        badge = Image.new("RGBA", (BADGE_OUTPUT_SIZE, BADGE_OUTPUT_SIZE), (0, 0, 0, 0))
        core = Image.new("RGBA", (24, 24), (230, 96, 56, 255))
        badge.alpha_composite(core, (4, 4))
        badge.save(badge_abs, format="PNG")
    enemy_placeholder = os.path.join(STATIC_ROOT, "enemies", "_placeholder.png")
    if not os.path.exists(enemy_placeholder):
        img = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
        body = Image.new("RGBA", (96, 96), (120, 124, 146, 255))
        img.alpha_composite(body, (16, 16))
        eye = Image.new("RGBA", (12, 12), (250, 224, 120, 255))
        img.alpha_composite(eye, (40, 44))
        img.alpha_composite(eye, (76, 44))
        img.save(enemy_placeholder, format="PNG")


def _check_static_health():
    required = [
        os.path.join(STATIC_ROOT, "style.css"),
        os.path.join(STATIC_ROOT, DEFAULT_AVATAR_REL),
        os.path.join(STATIC_ROOT, DEFAULT_BADGE_REL),
        os.path.join(STATIC_ROOT, "enemies", "_placeholder.png"),
    ]
    missing = [p for p in required if not os.path.exists(p)]
    if missing:
        _ensure_dirs()
        _ensure_default_images()


def _health_snapshot():
    db_ok = False
    db_error = ""
    pending_portal_queue = 0
    db = None
    try:
        db = sqlite3.connect(DB_PATH)
        db.execute("SELECT 1").fetchone()
        queue_exists = db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'portal_online_delivery_queue'"
        ).fetchone()
        if queue_exists:
            row = db.execute(
                "SELECT COUNT(*) FROM portal_online_delivery_queue WHERE status = 'pending'"
            ).fetchone()
            pending_portal_queue = int((row[0] if row else 0) or 0)
        db_ok = True
    except Exception as exc:
        db_error = str(exc)
    finally:
        try:
            db.close()
        except Exception:
            pass
    required = [
        os.path.join(STATIC_ROOT, "style.css"),
        os.path.join(STATIC_ROOT, DEFAULT_AVATAR_REL),
        os.path.join(STATIC_ROOT, DEFAULT_BADGE_REL),
    ]
    missing_static = [os.path.relpath(path, BASE_DIR) for path in required if not os.path.exists(path)]
    status_ok = db_ok and not missing_static
    return {
        "ok": status_ok,
        "db": {"ok": db_ok, "error": db_error},
        "static": {"ok": not missing_static, "missing": missing_static},
        "portal_queue_pending": int(pending_portal_queue),
        "app_version": APP_VERSION,
        "timestamp": now_str(),
    }


def _collect_missing_assets(db, limit=200):
    part_rows = db.execute(
        "SELECT key, image_path FROM robot_parts WHERE is_active = 1 ORDER BY key ASC"
    ).fetchall()
    enemy_rows = db.execute(
        "SELECT key, image_path FROM enemies WHERE COALESCE(is_active, 1) = 1 ORDER BY key ASC"
    ).fetchall()
    decor_rows = db.execute(
        "SELECT key, image_path FROM robot_decor_assets WHERE COALESCE(is_active, 1) = 1 ORDER BY key ASC"
    ).fetchall()

    out = []
    for row in part_rows:
        rel = f"robot_assets/{row['image_path']}" if row["image_path"] else ""
        if not rel or not os.path.exists(_static_abs(rel)):
            out.append({"type": "part", "key": row["key"], "path": rel or "(empty)"})
    for row in enemy_rows:
        rel = (row["image_path"] or "").strip()
        if not rel or not os.path.exists(_static_abs(rel)):
            out.append({"type": "enemy", "key": row["key"], "path": rel or "(empty)"})
    for row in decor_rows:
        rel = (row["image_path"] or "").strip()
        if not rel or not os.path.exists(_static_abs(rel)):
            out.append({"type": "decor", "key": row["key"], "path": rel or "(empty)"})
    return {
        "count": len(out),
        "rows": out[: max(0, int(limit))],
    }


def _clean_key(raw):
    key = re.sub(r"[^a-zA-Z0-9_-]", "", (raw or "").strip())
    return key.lower()


def _normalize_enemy_element(raw):
    return (raw or "NORMAL").strip().upper()


def _validate_enemy_image_path(raw):
    value = (raw or "").strip().replace("\\", "/")
    if not value:
        return None, None
    if value.startswith("/") or ".." in value.split("/"):
        return None, "image_path は static 配下の相対パスを指定してください（../禁止）。"
    return value, None


def _parse_enemy_csv_source(file_storage, csv_text):
    if file_storage and file_storage.filename:
        if not file_storage.filename.lower().endswith(".csv"):
            return None, "CSVファイル（.csv）のみアップロードできます。"
        raw = file_storage.read(ENEMY_IMPORT_MAX_BYTES + 1)
        file_storage.stream.seek(0)
        if len(raw) > ENEMY_IMPORT_MAX_BYTES:
            return None, f"CSVは最大 {ENEMY_IMPORT_MAX_BYTES // (1024 * 1024)}MB までです。"
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return None, "CSVはUTF-8で保存してください。"
        return text, None
    text = (csv_text or "").strip()
    if not text:
        return None, "CSV入力が空です。"
    if len(text.encode("utf-8")) > ENEMY_IMPORT_MAX_BYTES:
        return None, f"CSVは最大 {ENEMY_IMPORT_MAX_BYTES // (1024 * 1024)}MB までです。"
    return text, None


def _enemy_import_preview(db, csv_source_text):
    required = {"key", "name_ja", "tier", "element", "hp", "atk", "def", "spd", "acc", "cri"}
    reader = csv.DictReader(io.StringIO(csv_source_text))
    if not reader.fieldnames:
        return [{"action": "error", "line_no": 1, "errors": ["ヘッダー行がありません。"]}]
    headers = {h.strip() for h in reader.fieldnames if h}
    missing = required - headers
    if missing:
        return [{"action": "error", "line_no": 1, "errors": [f"必須ヘッダー不足: {', '.join(sorted(missing))}"]}]

    rows = []
    for i, row in enumerate(reader, start=2):
        errors = []
        key = (row.get("key") or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9_]+", key):
            errors.append("keyは [a-z0-9_]+ で入力してください。")
        name_ja = (row.get("name_ja") or "").strip()
        if not name_ja:
            errors.append("name_ja は必須です。")
        try:
            tier = int((row.get("tier") or "").strip())
        except ValueError:
            tier = -1
        if tier not in {1, 2, 3}:
            errors.append("tier は 1〜3 で入力してください。")
        element = (row.get("element") or "").strip()
        if not element:
            errors.append("element は必須です。")
        else:
            element = element.upper()

        stats = {}
        for k in ("hp", "atk", "def", "spd", "acc", "cri"):
            raw = (row.get(k) or "").strip()
            try:
                v = int(raw)
                if v < 0:
                    raise ValueError
                stats[k] = v
            except ValueError:
                errors.append(f"{k} は0以上の整数で入力してください。")

        is_active_raw = (row.get("is_active") or "").strip()
        if not is_active_raw:
            is_active = 1
        elif is_active_raw in {"0", "1"}:
            is_active = int(is_active_raw)
        else:
            is_active = -1
            errors.append("is_active は 0/1 で入力してください。")

        image_path, image_err = _validate_enemy_image_path(row.get("image_path") or "")
        if image_err:
            errors.append(image_err)
        faction = (row.get("faction") or "neutral").strip().lower() or "neutral"
        if faction not in FACTION_LABELS:
            errors.append("faction は aurix/ventra/ignis/neutral で入力してください。")
        is_boss_raw = (row.get("is_boss") or "").strip()
        if not is_boss_raw:
            is_boss = 0
        elif is_boss_raw in {"0", "1"}:
            is_boss = int(is_boss_raw)
        else:
            is_boss = -1
            errors.append("is_boss は 0/1 で入力してください。")
        boss_area_key = (row.get("boss_area_key") or "").strip()
        if boss_area_key:
            boss_area_key = boss_area_key.lower()
        else:
            boss_area_key = None
        if is_boss == 1 and boss_area_key not in AREA_BOSS_KEYS:
            errors.append("is_boss=1 の場合、boss_area_key は layer_1/layer_2/layer_3 が必須です。")
        if is_boss == 0:
            boss_area_key = None

        existing = db.execute("SELECT * FROM enemies WHERE key = ?", (key,)).fetchone() if key else None
        normalized = {
            "key": key,
            "name_ja": name_ja,
            "tier": tier,
            "element": element,
            "hp": stats.get("hp", 0),
            "atk": stats.get("atk", 0),
            "def": stats.get("def", 0),
            "spd": stats.get("spd", 0),
            "acc": stats.get("acc", 0),
            "cri": stats.get("cri", 0),
            "image_path": image_path,
            "faction": faction,
            "is_active": is_active,
            "is_boss": is_boss,
            "boss_area_key": boss_area_key,
        }

        if errors:
            rows.append({"action": "error", "line_no": i, "key": key, "data": normalized, "errors": errors, "changes": []})
            continue

        if existing is None:
            action = "create"
            changes = []
        else:
            changes = []
            for field in (
                "name_ja",
                "tier",
                "element",
                "hp",
                "atk",
                "def",
                "spd",
                "acc",
                "cri",
                "image_path",
                "faction",
                "is_active",
                "is_boss",
                "boss_area_key",
            ):
                if existing[field] != normalized[field]:
                    changes.append(f"{field}: {existing[field]} -> {normalized[field]}")
            action = "update" if changes else "skip"

        rows.append({"action": action, "line_no": i, "key": key, "data": normalized, "errors": [], "changes": changes})
    return rows


def _validate_png(file_storage):
    filename = (file_storage.filename or "").lower()
    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in ALLOWED_EXT:
        return False, "png形式のみ対応しています。", None
    try:
        file_storage.stream.seek(0)
        img = Image.open(file_storage.stream)
        if img.format != "PNG":
            return False, "PNG形式のみ対応しています。", None
        if img.size != (CANVAS_SIZE, CANVAS_SIZE):
            return False, f"画像サイズは {CANVAS_SIZE}x{CANVAS_SIZE} に統一してください。", None
        has_alpha = "A" in img.mode or "transparency" in img.info
        if not has_alpha:
            if REQUIRE_ALPHA:
                return False, "透過情報（alpha）が必要です。", None
            return True, None, "透過なしPNGです。合成表示が崩れる可能性があります。"
    except Exception:
        return False, "画像の読み込みに失敗しました。", None
    finally:
        file_storage.stream.seek(0)
    return True, None, None


def _validate_enemy_png(file_storage):
    filename = (file_storage.filename or "").lower()
    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    if ext != "png":
        return False, "敵画像はPNGのみ対応です。"
    try:
        file_storage.stream.seek(0)
        img = Image.open(file_storage.stream)
        if img.format != "PNG":
            return False, "敵画像はPNGのみ対応です。"
        if img.size != (CANVAS_SIZE, CANVAS_SIZE):
            return False, f"敵画像サイズは {CANVAS_SIZE}x{CANVAS_SIZE} 固定です。"
        has_alpha = "A" in img.mode or "transparency" in img.info
        if not has_alpha:
            return False, "敵画像は透過PNG（alpha必須）でアップロードしてください。"
    except Exception:
        return False, "敵画像の読み込みに失敗しました。"
    finally:
        file_storage.stream.seek(0)
    return True, None


def _validate_decor_png_soft(file_storage):
    filename = (file_storage.filename or "").lower()
    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    if ext != "png":
        return False, "装飾画像はPNGのみ対応です。", None
    warns = []
    try:
        file_storage.stream.seek(0)
        img = Image.open(file_storage.stream)
        if img.format != "PNG":
            return False, "装飾画像はPNGのみ対応です。", None
        if img.size != (CANVAS_SIZE, CANVAS_SIZE):
            warns.append(f"推奨サイズは {CANVAS_SIZE}x{CANVAS_SIZE} です。")
        has_alpha = "A" in img.mode or "transparency" in img.info
        if not has_alpha:
            warns.append("透過PNG推奨です（背景付きだと重なりが崩れる可能性があります）。")
    except Exception:
        return False, "装飾画像の読み込みに失敗しました。", None
    finally:
        file_storage.stream.seek(0)
    return True, None, warns


def _save_png(file_storage, rel_path):
    _ensure_dirs()
    abs_path = os.path.join(ASSET_ROOT, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    file_storage.stream.seek(0)
    img = Image.open(file_storage.stream).convert("RGBA")
    img.save(abs_path, format="PNG")
    file_storage.stream.seek(0)
    return abs_path


def _save_static_png(file_storage, rel_path):
    abs_path = _static_abs(rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    file_storage.stream.seek(0)
    img = Image.open(file_storage.stream).convert("RGBA")
    img.save(abs_path, format="PNG")
    file_storage.stream.seek(0)
    return abs_path


def _save_user_avatar(file_storage, user_id):
    raw = file_storage.read(MAX_AVATAR_BYTES + 1)
    file_storage.stream.seek(0)
    if len(raw) == 0:
        return False, "画像が選択されていません。", None
    if len(raw) > MAX_AVATAR_BYTES:
        return False, f"画像サイズは最大 {MAX_AVATAR_BYTES // (1024 * 1024)}MB です。", None
    try:
        img = Image.open(file_storage.stream).convert("RGBA")
    except Exception:
        file_storage.stream.seek(0)
        return False, "画像形式を読み込めませんでした。", None
    file_storage.stream.seek(0)
    side = min(img.width, img.height)
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    cropped = img.crop((left, top, left + side, top + side))
    avatar = cropped.resize((AVATAR_OUTPUT_SIZE, AVATAR_OUTPUT_SIZE), Image.NEAREST)
    rel_path = f"uploads/avatars/{user_id}.png"
    out_path = _static_abs(rel_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    avatar.save(out_path, format="PNG")
    return True, None, rel_path


def _lab_default_course_key():
    return lab_default_course_key(mode="standard")


def _lab_course_meta(course_key):
    key = str(course_key or "").strip().lower()
    if key == "scrapyard_dash":
        key = "scrapyard_sprint"
    return dict(LAB_RACE_COURSES.get(key) or LAB_RACE_COURSES[_lab_default_course_key()])


def _lab_course_payload_from_race(race, *, mode="standard"):
    if not race:
        return build_lab_race_course(0, mode=mode, course_key=lab_default_course_key(mode=mode))
    course_key = race.get("course_key") or race.get("race_key") or lab_default_course_key(mode=mode)
    return load_lab_race_course(
        race.get("course_payload_json"),
        seed=int(race.get("seed") or 0),
        mode=mode,
        course_key=course_key,
    )


def _lab_format_time_ms(value):
    if value is None:
        return "-"
    total_ms = max(0, int(value))
    seconds = total_ms / 1000.0
    return f"{seconds:.2f}秒"


def _lab_submission_status_label(status):
    return {
        "draft": "下書き",
        "pending": "審査待ち",
        "approved": "公開中",
        "rejected": "差し戻し",
        "disabled": "停止",
    }.get(str(status or "").strip().lower(), str(status or "-"))


def _lab_report_reason_label(reason):
    reason_key = str(reason or "").strip().lower()
    for key, label in LAB_REPORT_REASON_DEFS:
        if key == reason_key:
            return label
    return "その他"


def _lab_world_event_log(db, event_type, payload):
    db.execute(
        """
        INSERT INTO world_events_log (created_at, event_type, payload_json)
        VALUES (?, ?, ?)
        """,
        (
            int(time.time()),
            str(event_type),
            json.dumps(payload or {}, ensure_ascii=False),
        ),
    )


def _lab_validate_submission_image(file_storage):
    if not file_storage or not getattr(file_storage, "filename", ""):
        return False, "PNG画像を選択してください。", None
    filename = str(file_storage.filename or "")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext != "png":
        return False, "投稿画像はPNGのみ対応です。", None
    if str(file_storage.mimetype or "").lower() not in {"image/png", "image/x-png", ""}:
        return False, "投稿画像はPNGのみ対応です。", None
    raw = file_storage.read(MAX_LAB_UPLOAD_BYTES + 1)
    file_storage.stream.seek(0)
    if not raw:
        return False, "画像データを読み取れませんでした。", None
    if len(raw) > MAX_LAB_UPLOAD_BYTES:
        return False, f"画像サイズは最大 {MAX_LAB_UPLOAD_BYTES // (1024 * 1024)}MB です。", None
    try:
        img = Image.open(file_storage.stream)
        if img.format != "PNG":
            return False, "投稿画像はPNGのみ対応です。", None
        width, height = img.size
        if width != height or width < 96 or width > 512:
            return False, "画像は正方形で 96px 以上 512px 以下にしてください。", None
        rgba = img.convert("RGBA")
        alpha = rgba.getchannel("A")
        extrema = alpha.getextrema() or (255, 255)
        if int(extrema[0]) >= 255:
            return False, "透過付きPNGのみ投稿できます。背景を透過してください。", None
    except Exception:
        return False, "投稿画像の読み込みに失敗しました。", None
    finally:
        file_storage.stream.seek(0)
    return True, None, rgba


def _lab_save_submission_image(file_storage):
    ok, message, rgba = _lab_validate_submission_image(file_storage)
    if not ok:
        return False, message, None, None
    _ensure_dirs()
    token = uuid.uuid4().hex
    original_rel = f"user_lab_uploads/originals/{token}.png"
    thumb_rel = f"user_lab_uploads/thumbs/{token}.png"
    original_abs = _static_abs(original_rel)
    thumb_abs = _static_abs(thumb_rel)
    os.makedirs(os.path.dirname(original_abs), exist_ok=True)
    os.makedirs(os.path.dirname(thumb_abs), exist_ok=True)
    rgba.save(original_abs, format="PNG")
    thumb = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    resized = rgba.copy()
    resized.thumbnail((128, 128), Image.NEAREST)
    paste_x = (128 - resized.width) // 2
    paste_y = (128 - resized.height) // 2
    thumb.alpha_composite(resized, (paste_x, paste_y))
    thumb.save(thumb_abs, format="PNG")
    file_storage.stream.seek(0)
    return True, None, original_rel, thumb_rel


def _lab_recent_world_items(db, *, limit=6):
    rows = db.execute(
        f"""
        SELECT id, created_at, event_type, payload_json, user_id, action_key, entity_type, entity_id
        FROM world_events_log
        WHERE event_type IN ({",".join(["?"] * len(LAB_WORLD_EVENT_TYPES))})
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (*sorted(LAB_WORLD_EVENT_TYPES), int(limit)),
    ).fetchall()
    return [_feed_card_from_event(db, row) for row in rows]


def _lab_submission_recent_rows(db, user_id, *, limit=12):
    rows = db.execute(
        """
        SELECT *
        FROM lab_robot_submissions
        WHERE user_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (int(user_id), int(limit)),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["status_label"] = _lab_submission_status_label(item.get("status"))
        item["image_url"] = url_for("static", filename=item["thumb_path"]) if item.get("thumb_path") else None
        out.append(item)
    return out


def _lab_showcase_query_rows(db, *, viewer_user_id, sort_key="new", limit=48):
    current_sort = (sort_key or "new").strip().lower()
    if current_sort not in LAB_SUBMISSION_SORT_OPTIONS:
        current_sort = "new"
    order_by = {
        "new": "s.approved_at DESC, s.id DESC",
        "popular": "COALESCE(l.likes_count, 0) DESC, s.approved_at DESC, s.id DESC",
        "talk": "COALESCE(l.recent_likes, 0) DESC, COALESCE(l.likes_count, 0) DESC, s.approved_at DESC, s.id DESC",
        "pick": "CASE WHEN LOWER(COALESCE(s.moderation_note, '')) LIKE '%[pick]%' THEN 0 ELSE 1 END, s.approved_at DESC, s.id DESC",
    }[current_sort]
    recent_cutoff = int(time.time()) - 7 * 86400
    rows = db.execute(
        f"""
        SELECT
            s.*,
            u.username,
            COALESCE(l.likes_count, 0) AS likes_count,
            COALESCE(l.recent_likes, 0) AS recent_likes,
            COALESCE(r.report_count, 0) AS report_count,
            CASE WHEN my_like.id IS NULL THEN 0 ELSE 1 END AS liked_by_me
        FROM lab_robot_submissions s
        JOIN users u ON u.id = s.user_id
        LEFT JOIN (
            SELECT
                submission_id,
                COUNT(*) AS likes_count,
                SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS recent_likes
            FROM lab_submission_likes
            GROUP BY submission_id
        ) l ON l.submission_id = s.id
        LEFT JOIN (
            SELECT submission_id, COUNT(*) AS report_count
            FROM lab_submission_reports
            GROUP BY submission_id
        ) r ON r.submission_id = s.id
        LEFT JOIN lab_submission_likes my_like
          ON my_like.submission_id = s.id
         AND my_like.user_id = ?
        WHERE s.status = 'approved'
        ORDER BY {order_by}
        LIMIT ?
        """,
        (recent_cutoff, int(viewer_user_id), int(limit)),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["thumb_url"] = url_for("static", filename=item["thumb_path"]) if item.get("thumb_path") else None
        item["image_url"] = url_for("static", filename=item["image_path"]) if item.get("image_path") else None
        item["status_label"] = _lab_submission_status_label(item.get("status"))
        out.append(item)
    return _decorate_user_rows(db, out, user_key="user_id")


def _lab_submission_detail_row(db, submission_id, *, viewer_user_id=None, is_admin=False):
    row = db.execute(
        """
        SELECT
            s.*,
            u.username,
            COALESCE(l.likes_count, 0) AS likes_count,
            COALESCE(r.report_count, 0) AS report_count,
            CASE WHEN my_like.id IS NULL THEN 0 ELSE 1 END AS liked_by_me
        FROM lab_robot_submissions s
        JOIN users u ON u.id = s.user_id
        LEFT JOIN (
            SELECT submission_id, COUNT(*) AS likes_count
            FROM lab_submission_likes
            GROUP BY submission_id
        ) l ON l.submission_id = s.id
        LEFT JOIN (
            SELECT submission_id, COUNT(*) AS report_count
            FROM lab_submission_reports
            GROUP BY submission_id
        ) r ON r.submission_id = s.id
        LEFT JOIN lab_submission_likes my_like
          ON my_like.submission_id = s.id
         AND my_like.user_id = ?
        WHERE s.id = ?
        LIMIT 1
        """,
        (int(viewer_user_id or 0), int(submission_id)),
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    can_view = item["status"] == "approved" or bool(is_admin) or (viewer_user_id and int(item["user_id"]) == int(viewer_user_id))
    if not can_view:
        return None
    item["thumb_url"] = url_for("static", filename=item["thumb_path"]) if item.get("thumb_path") else None
    item["image_url"] = url_for("static", filename=item["image_path"]) if item.get("image_path") else None
    item["status_label"] = _lab_submission_status_label(item.get("status"))
    item = _decorate_user_rows(db, [item], user_key="user_id")[0]
    return item


def _lab_submission_pending_rows(db, *, status_filter="pending", limit=80):
    current_status = (status_filter or "pending").strip().lower()
    rows = db.execute(
        """
        SELECT
            s.*,
            u.username,
            COALESCE(r.report_count, 0) AS report_count,
            COALESCE(l.likes_count, 0) AS likes_count
        FROM lab_robot_submissions s
        JOIN users u ON u.id = s.user_id
        LEFT JOIN (
            SELECT submission_id, COUNT(*) AS report_count
            FROM lab_submission_reports
            GROUP BY submission_id
        ) r ON r.submission_id = s.id
        LEFT JOIN (
            SELECT submission_id, COUNT(*) AS likes_count
            FROM lab_submission_likes
            GROUP BY submission_id
        ) l ON l.submission_id = s.id
        WHERE s.status = ?
        ORDER BY s.created_at ASC, s.id ASC
        LIMIT ?
        """,
        (current_status, int(limit)),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["thumb_url"] = url_for("static", filename=item["thumb_path"]) if item.get("thumb_path") else None
        item["status_label"] = _lab_submission_status_label(item.get("status"))
        out.append(item)
    return _decorate_user_rows(db, out, user_key="user_id")


def _lab_user_robot_choices(db, user_id):
    rows = db.execute(
        """
        SELECT id, name, composed_image_path, icon_32_path, updated_at
        FROM robot_instances
        WHERE user_id = ? AND status = 'active'
        ORDER BY updated_at DESC, id DESC
        """,
        (int(user_id),),
    ).fetchall()
    out = []
    for row in rows:
        row = _refresh_robot_instance_render_assets(db, row, log_label="lab_user_robot_choices")
        if not row:
            continue
        stat_obj = _compute_robot_stats_for_instance(db, int(row["id"]))
        if not stat_obj:
            continue
        icon_rel = _safe_static_rel(row["icon_32_path"]) if row["icon_32_path"] else None
        thumb_rel = _safe_static_rel(row["composed_image_path"]) if row["composed_image_path"] else None
        out.append(
            {
                "id": int(row["id"]),
                "name": row["name"],
                "icon_url": url_for("static", filename=icon_rel or DEFAULT_BADGE_REL),
                "thumb_url": url_for("static", filename=thumb_rel) if thumb_rel else None,
                "stats": stat_obj["stats"],
                "power": stat_obj["power"],
            }
        )
    return out


def _lab_entry_snapshot_from_robot(db, user_id, robot_instance_id):
    robot = db.execute(
        """
        SELECT id, name, icon_32_path, composed_image_path, updated_at
        FROM robot_instances
        WHERE id = ? AND user_id = ? AND status = 'active'
        LIMIT 1
        """,
        (int(robot_instance_id), int(user_id)),
    ).fetchone()
    if not robot:
        return None
    robot = _refresh_robot_instance_render_assets(db, robot, log_label="lab_entry_snapshot")
    if not robot:
        return None
    stat_obj = _compute_robot_stats_for_instance(db, int(robot["id"]))
    if not stat_obj:
        return None
    icon_rel = _safe_static_rel(robot["icon_32_path"]) if robot["icon_32_path"] else None
    if not icon_rel and robot["composed_image_path"]:
        icon_rel = _ensure_robot_instance_badge(db, int(robot["id"]), robot["composed_image_path"])
    icon_rel = icon_rel or DEFAULT_BADGE_REL
    stats = stat_obj["stats"]
    return {
        "source_type": "robot_instance",
        "robot_instance_id": int(robot["id"]),
        "submission_id": None,
        "display_name": str(robot["name"] or f"Robot#{robot['id']}"),
        "icon_path": icon_rel,
        "hp": int(stats["hp"]),
        "atk": int(stats["atk"]),
        "def": int(stats["def"]),
        "spd": int(stats["spd"]),
        "acc": int(stats["acc"]),
        "cri": int(stats["cri"]),
    }


def _lab_latest_race(db):
    row = db.execute(
        """
        SELECT *
        FROM lab_races
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()
    return dict(row) if row else None


def _lab_fetch_race(db, race_id):
    row = db.execute("SELECT * FROM lab_races WHERE id = ? LIMIT 1", (int(race_id),)).fetchone()
    return dict(row) if row else None


def _lab_race_entries(db, race_id):
    rows = db.execute(
        """
        SELECT *
        FROM lab_race_entries
        WHERE race_id = ?
        ORDER BY entry_order ASC, id ASC
        """,
        (int(race_id),),
    ).fetchall()
    out = []
    robot_scene_cache = {}
    submission_scene_cache = {}
    for lane_index, row in enumerate(rows):
        item = dict(row)
        item["lane_index"] = int(lane_index)
        item["lane_no"] = int(lane_index) + 1
        item["owner_label"] = _feed_user_label(db, item["user_id"]) if item.get("user_id") else "LAB ENEMY"
        icon_rel = _safe_static_rel(item["icon_path"]) if item.get("icon_path") else None
        item["icon_url"] = url_for("static", filename=icon_rel or DEFAULT_BADGE_REL)
        track_rel = icon_rel
        scene_rel = icon_rel or DEFAULT_BADGE_REL
        scene_updated_at = item.get("updated_at")
        if item.get("source_type") == "robot_instance" and item.get("robot_instance_id"):
            robot_instance_id = int(item["robot_instance_id"])
            source_row = robot_scene_cache.get(robot_instance_id)
            if source_row is None:
                source_row = db.execute(
                    "SELECT composed_image_path, updated_at FROM robot_instances WHERE id = ? LIMIT 1",
                    (robot_instance_id,),
                ).fetchone()
                robot_scene_cache[robot_instance_id] = source_row
            if source_row and source_row["composed_image_path"]:
                source_rel = _safe_static_rel(source_row["composed_image_path"])
                scene_rel = source_rel or scene_rel
                if not track_rel:
                    track_rel = _lab_scene_sprite_rel(source_rel) or source_rel or track_rel
                scene_updated_at = source_row["updated_at"]
        elif item.get("source_type") == "submission" and item.get("submission_id"):
            submission_id = int(item["submission_id"])
            source_row = submission_scene_cache.get(submission_id)
            if source_row is None:
                source_row = db.execute(
                    "SELECT image_path, updated_at FROM lab_robot_submissions WHERE id = ? LIMIT 1",
                    (submission_id,),
                ).fetchone()
                submission_scene_cache[submission_id] = source_row
            if source_row and source_row["image_path"]:
                source_rel = _safe_static_rel(source_row["image_path"])
                scene_rel = source_rel or scene_rel
                if not track_rel:
                    track_rel = _lab_scene_sprite_rel(source_rel) or source_rel or track_rel
                scene_updated_at = source_row["updated_at"]
        scene_sprite_rel = _lab_scene_sprite_rel(scene_rel) or scene_rel or DEFAULT_BADGE_REL
        item["scene_url"] = _composed_image_url(scene_sprite_rel, scene_updated_at)
        item["track_icon_url"] = url_for("static", filename=track_rel or DEFAULT_BADGE_REL)
        out.append(item)
    return _decorate_user_rows(db, out, user_key="user_id")


def _lab_race_results(db, race_id):
    rows = db.execute(
        """
        SELECT
            e.*,
            r.accident_count,
            r.comeback_flag
        FROM lab_race_entries e
        LEFT JOIN lab_race_records r ON r.entry_id = e.id
        WHERE e.race_id = ?
        ORDER BY COALESCE(e.final_rank, 9999) ASC, e.entry_order ASC
        """,
        (int(race_id),),
    ).fetchall()
    out = []
    max_accidents = max((int(row["accident_count"] or 0) for row in rows), default=0)
    for row in rows:
        item = dict(row)
        item["owner_label"] = _feed_user_label(db, item["user_id"]) if item.get("user_id") else "LAB ENEMY"
        icon_rel = _safe_static_rel(item["icon_path"]) if item.get("icon_path") else None
        item["icon_url"] = url_for("static", filename=icon_rel or DEFAULT_BADGE_REL)
        item["finish_text"] = _lab_format_time_ms(item.get("finish_time_ms"))
        highlights = []
        if int(item.get("comeback_flag") or 0) == 1:
            highlights.append("大逆転")
        if int(item.get("accident_count") or 0) == int(max_accidents) and int(max_accidents) >= 3:
            highlights.append("転倒王")
        item["highlights"] = highlights
        out.append(item)
    return _decorate_user_rows(db, out, user_key="user_id")


def _lab_race_frames(db, race_id):
    rows = db.execute(
        """
        SELECT frame_no, payload_json
        FROM lab_race_frames
        WHERE race_id = ?
        ORDER BY frame_no ASC
        """,
        (int(race_id),),
    ).fetchall()
    out = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        payload["frame_no"] = int(row["frame_no"])
        out.append(payload)
    return out


def _lab_race_rankings(db, *, limit=20):
    wins_rows = db.execute(
        """
        SELECT user_id, COUNT(*) AS metric_value
        FROM lab_race_records
        WHERE user_id IS NOT NULL AND final_rank = 1
        GROUP BY user_id
        ORDER BY metric_value DESC, user_id ASC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    wins_rows = _decorate_user_rows(
        db,
        [
            {
                "id": int(row["user_id"]),
                "metric_value": int(row["metric_value"]),
                "username": _feed_user_label(db, row["user_id"]),
            }
            for row in wins_rows
        ],
        user_key="id",
    )
    fastest_rows = db.execute(
        """
        SELECT robot_label, user_id, MIN(finish_time_ms) AS metric_value
        FROM lab_race_records
        WHERE finish_time_ms IS NOT NULL AND user_id IS NOT NULL
        GROUP BY robot_label, user_id
        ORDER BY metric_value ASC, robot_label ASC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    fastest = _decorate_user_rows(
        db,
        [
            {
                "robot_label": row["robot_label"],
                "user_id": int(row["user_id"]),
                "username": _feed_user_label(db, row["user_id"]),
                "metric_value": int(row["metric_value"]),
            }
            for row in fastest_rows
        ],
        user_key="user_id",
    )
    accident_rows = db.execute(
        """
        SELECT user_id, SUM(accident_count) AS metric_value
        FROM lab_race_records
        WHERE user_id IS NOT NULL
        GROUP BY user_id
        ORDER BY metric_value DESC, user_id ASC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    accident_rows = _decorate_user_rows(
        db,
        [
            {
                "id": int(row["user_id"]),
                "metric_value": int(row["metric_value"] or 0),
                "username": _feed_user_label(db, row["user_id"]),
            }
            for row in accident_rows
        ],
        user_key="id",
    )
    comeback_rows = db.execute(
        """
        SELECT user_id, SUM(CASE WHEN comeback_flag = 1 THEN 1 ELSE 0 END) AS metric_value
        FROM lab_race_records
        WHERE user_id IS NOT NULL
        GROUP BY user_id
        HAVING metric_value > 0
        ORDER BY metric_value DESC, user_id ASC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    comeback_rows = _decorate_user_rows(
        db,
        [
            {
                "id": int(row["user_id"]),
                "metric_value": int(row["metric_value"]),
                "username": _feed_user_label(db, row["user_id"]),
            }
            for row in comeback_rows
        ],
        user_key="id",
    )
    return {
        "wins": wins_rows,
        "fastest": fastest,
        "accident": accident_rows,
        "comeback": comeback_rows,
    }


def _lab_create_race(db, *, course_key=None, seed=None):
    now_ts = int(time.time())
    race_seed = int(seed or random.randint(100_000, 999_999))
    course = build_lab_race_course(race_seed, mode="standard", course_key=course_key or _lab_default_course_key())
    cur = db.execute(
        """
        INSERT INTO lab_races (status, course_key, course_payload_json, seed, created_at)
        VALUES ('entry_open', ?, ?, ?, ?)
        """,
        (course["key"], json.dumps(course, ensure_ascii=False), race_seed, now_ts),
    )
    return int(cur.lastrowid)


def _lab_start_race(db, race_id, *, actor_user_id=None):
    race = _lab_fetch_race(db, race_id)
    if not race or race["status"] != "entry_open":
        return race
    entries = _lab_race_entries(db, race_id)
    if not entries:
        return race
    seed = int(race["seed"] or random.randint(100_000, 999_999))
    course = _lab_course_payload_from_race(race, mode="standard")
    filled = fill_npc_entries(entries, seed, target=LAB_RACE_ENTRY_TARGET)
    existing_orders = {int(item["entry_order"]) for item in entries}
    now_ts = int(time.time())
    for item in filled:
        if int(item["entry_order"]) in existing_orders:
            continue
        db.execute(
            """
            INSERT INTO lab_race_entries
            (
                race_id, user_id, source_type, robot_instance_id, submission_id,
                display_name, icon_path, hp, atk, def, spd, acc, cri, entry_order
            )
            VALUES (?, NULL, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(race_id),
                "npc",
                item["display_name"],
                item.get("icon_path") or DEFAULT_BADGE_REL,
                int(item["hp"]),
                int(item["atk"]),
                int(item["def"]),
                int(item["spd"]),
                int(item["acc"]),
                int(item["cri"]),
                int(item["entry_order"]),
            ),
        )
    full_rows = db.execute(
        """
        SELECT *
        FROM lab_race_entries
        WHERE race_id = ?
        ORDER BY entry_order ASC, id ASC
        """,
        (int(race_id),),
    ).fetchall()
    full_entries = [dict(item) for item in sorted(filled, key=lambda row: int(row["entry_order"]))]
    db.execute(
        "UPDATE lab_races SET status = 'running', started_at = ? WHERE id = ?",
        (now_ts, int(race_id)),
    )
    audit_log(
        db,
        AUDIT_EVENT_TYPES["LAB_RACE_START"],
        user_id=(int(actor_user_id) if actor_user_id else None),
        request_id=getattr(g, "request_id", None),
        action_key="lab_race_start",
        entity_type="lab_race",
        entity_id=int(race_id),
        payload={
            "race_id": int(race_id),
            "course_key": race["course_key"],
            "seed": seed,
            "entry_count": len(full_entries),
            "special_count": int(course.get("special_count") or 0),
            "features": [item["feature_key"] for item in course.get("selected_features", ())],
        },
        ip=request.remote_addr,
    )
    simulated = simulate_race(full_entries, seed, course)
    db.execute("DELETE FROM lab_race_frames WHERE race_id = ?", (int(race_id),))
    db.execute("DELETE FROM lab_race_records WHERE race_id = ?", (int(race_id),))
    entry_id_by_order = {int(row["entry_order"]): int(row["id"]) for row in full_rows}
    for frame in simulated["frames"]:
        db.execute(
            """
            INSERT INTO lab_race_frames (race_id, frame_no, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                int(race_id),
                int(frame["frame_no"]),
                json.dumps(frame, ensure_ascii=False),
                now_ts,
            ),
        )
    winner_payload = None
    upset_payload = None
    for record in simulated["results"]:
        entry_id = entry_id_by_order[int(record["entry_order"])]
        db.execute(
            """
            UPDATE lab_race_entries
            SET final_rank = ?, finish_time_ms = ?, dnf_reason = NULL
            WHERE id = ?
            """,
            (int(record["final_rank"]), int(record["finish_time_ms"]), int(entry_id)),
        )
        db.execute(
            """
            INSERT INTO lab_race_records
            (race_id, entry_id, user_id, robot_label, final_rank, finish_time_ms, accident_count, comeback_flag, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(race_id),
                int(entry_id),
                (int(record["user_id"]) if record.get("user_id") is not None else None),
                record["display_name"],
                int(record["final_rank"]),
                int(record["finish_time_ms"]),
                int(record["accident_count"]),
                (1 if record.get("comeback_flag") else 0),
                now_ts,
            ),
        )
        if int(record["final_rank"]) == 1:
            winner_payload = {
                "race_id": int(race_id),
                "course_key": race["course_key"],
                "robot_name": record["display_name"],
                "user_id": record.get("user_id"),
                "username": (_feed_user_label(db, record["user_id"]) if record.get("user_id") else "LAB ENEMY"),
                "finish_time_ms": int(record["finish_time_ms"]),
                "watch_url": f"/lab/race/watch/{int(race_id)}",
                "features": [item["feature_key"] for item in course.get("selected_features", ())],
            }
            if record.get("comeback_flag"):
                upset_payload = {
                    **winner_payload,
                    "worst_rank": int(record.get("worst_rank") or 0),
                }
    db.execute(
        "UPDATE lab_races SET status = 'finished', finished_at = ? WHERE id = ?",
        (now_ts, int(race_id)),
    )
    audit_log(
        db,
        AUDIT_EVENT_TYPES["LAB_RACE_FINISH"],
        user_id=(int(actor_user_id) if actor_user_id else None),
        request_id=getattr(g, "request_id", None),
        action_key="lab_race_finish",
        entity_type="lab_race",
        entity_id=int(race_id),
        payload={
            "race_id": int(race_id),
            "course_key": race["course_key"],
            "winner": winner_payload,
            "entry_count": len(full_entries),
        },
        ip=request.remote_addr,
    )
    if winner_payload:
        audit_log(
            db,
            AUDIT_EVENT_TYPES["LAB_RACE_RESULT"],
            user_id=(int(winner_payload["user_id"]) if winner_payload.get("user_id") else None),
            request_id=getattr(g, "request_id", None),
            action_key="lab_race_result",
            entity_type="lab_race",
            entity_id=int(race_id),
            payload=winner_payload,
            ip=request.remote_addr,
        )
        _lab_world_event_log(db, "LAB_RACE_WIN", winner_payload)
    if upset_payload:
        _lab_world_event_log(db, "LAB_RACE_UPSET", upset_payload)
    return _lab_fetch_race(db, race_id)


def _lab_casino_day_key():
    return datetime.now(JST).strftime("%Y-%m-%d")


def _lab_casino_wallet_row(db, user_id):
    row = db.execute(
        """
        SELECT id, username, COALESCE(lab_coin, ?) AS lab_coin, lab_coin_last_daily_at
        FROM users
        WHERE id = ?
        LIMIT 1
        """,
        (int(LAB_CASINO_STARTING_COINS), int(user_id)),
    ).fetchone()
    return dict(row) if row else None


def _lab_casino_adjust_coins(db, user_id, delta, *, cap=LAB_CASINO_COIN_CAP):
    wallet = _lab_casino_wallet_row(db, user_id)
    before = int(wallet["lab_coin"] or 0) if wallet else 0
    after = max(0, before + int(delta))
    if cap is not None:
        after = min(int(cap), after)
    db.execute("UPDATE users SET lab_coin = ? WHERE id = ?", (int(after), int(user_id)))
    return before, after


def _lab_casino_apply_daily_grant_if_needed(db, user_id):
    wallet = _lab_casino_wallet_row(db, user_id)
    if not wallet:
        return {"granted_amount": 0, "already_received": True, "lab_coin_before": 0, "lab_coin_after": 0, "day_key": None}
    day_key = _lab_casino_day_key()
    last_daily_at = str(wallet.get("lab_coin_last_daily_at") or "").strip()
    before_coin = int(wallet.get("lab_coin") or 0)
    if last_daily_at == day_key:
        return {
            "granted_amount": 0,
            "already_received": True,
            "lab_coin_before": before_coin,
            "lab_coin_after": before_coin,
            "day_key": day_key,
        }
    grant_amount = min(int(LAB_CASINO_DAILY_GRANT), max(0, int(LAB_CASINO_COIN_CAP) - before_coin))
    before, after = _lab_casino_adjust_coins(db, user_id, grant_amount)
    db.execute("UPDATE users SET lab_coin_last_daily_at = ? WHERE id = ?", (day_key, int(user_id)))
    audit_log(
        db,
        AUDIT_EVENT_TYPES["LAB_CASINO_DAILY_GRANT"],
        user_id=int(user_id),
        request_id=getattr(g, "request_id", None),
        action_key="lab_casino_daily_grant",
        entity_type="user",
        entity_id=int(user_id),
        delta_coins=int(grant_amount),
        payload={
            "day_key": day_key,
            "grant_amount": int(grant_amount),
            "lab_coin_before": int(before),
            "lab_coin_after": int(after),
            "cap": int(LAB_CASINO_COIN_CAP),
        },
        ip=request.remote_addr,
    )
    return {
        "granted_amount": int(grant_amount),
        "already_received": False,
        "lab_coin_before": int(before),
        "lab_coin_after": int(after),
        "day_key": day_key,
    }


def _lab_casino_latest_race(db, *, status=None):
    if status:
        row = db.execute(
            """
            SELECT *
            FROM lab_casino_races
            WHERE status = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (str(status),),
        ).fetchone()
    else:
        row = db.execute(
            """
            SELECT *
            FROM lab_casino_races
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
    return dict(row) if row else None


def _lab_casino_fetch_race(db, race_id):
    row = db.execute("SELECT * FROM lab_casino_races WHERE id = ? LIMIT 1", (int(race_id),)).fetchone()
    return dict(row) if row else None


def _lab_casino_create_race(db, *, seed=None):
    now_ts = int(time.time())
    race_seed = int(seed or random.randint(100_000, 999_999))
    bundle = build_lab_race_bundle(mode="casino", seed=race_seed, course_key="casino_scrapyard_cup", simulate=False)
    course = bundle["course"]
    cur = db.execute(
        """
        INSERT INTO lab_casino_races (race_key, course_payload_json, status, seed, created_at)
        VALUES (?, ?, 'betting', ?, ?)
        """,
        (course["key"], json.dumps(course, ensure_ascii=False), race_seed, now_ts),
    )
    race_id = int(cur.lastrowid)
    for entry in bundle["entries"]:
        db.execute(
            """
            INSERT INTO lab_casino_entries
            (
                race_id, bot_key, display_name, role_type, condition_key,
                icon_path, description, spd, def, acc, cri, luck, odds,
                lane_index, entry_order, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(race_id),
                entry["bot_key"],
                entry["display_name"],
                entry["role_type"],
                entry["condition_key"],
                entry.get("icon_path") or DEFAULT_BADGE_REL,
                entry.get("description"),
                int(entry["spd"]),
                int(entry["def"]),
                int(entry["acc"]),
                int(entry["cri"]),
                int(entry["luck"]),
                float(entry["odds"]),
                int(entry["lane_index"]),
                int(entry["entry_order"]),
                now_ts,
            ),
        )
    return _lab_casino_fetch_race(db, race_id)


def _lab_casino_ensure_open_race(db):
    race = _lab_casino_latest_race(db, status="betting")
    if race:
        return race
    return _lab_casino_create_race(db)


def _lab_casino_entries(db, race_id):
    rows = db.execute(
        """
        SELECT *
        FROM lab_casino_entries
        WHERE race_id = ?
        ORDER BY lane_index ASC, entry_order ASC
        """,
        (int(race_id),),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        icon_rel = _safe_static_rel(item.get("icon_path"), warn_key=f"lab_casino:{item.get('bot_key')}") or DEFAULT_BADGE_REL
        item["icon_url"] = url_for("static", filename=icon_rel)
        item["track_icon_url"] = item["icon_url"]
        item["owner_label"] = "LAB ENEMY"
        item["role_label"] = LAB_CASINO_ROLE_LABELS.get(str(item.get("role_type") or ""), "実験機")
        item["condition_label"] = LAB_CASINO_CONDITIONS.get(str(item.get("condition_key") or ""), {}).get(
            "label",
            str(item.get("condition_key") or "-"),
        )
        item["odds_text"] = f"{float(item.get('odds') or 0):.1f}倍"
        item["lane_no"] = int(item.get("lane_index") or 0) + 1
        item["finish_text"] = _lab_format_time_ms(item.get("finish_time_ms"))
        out.append(item)
    return out


def _lab_casino_frames(db, race_id):
    rows = db.execute(
        """
        SELECT frame_no, payload_json
        FROM lab_casino_frames
        WHERE race_id = ?
        ORDER BY frame_no ASC
        """,
        (int(race_id),),
    ).fetchall()
    out = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        payload["frame_no"] = int(row["frame_no"])
        out.append(payload)
    return out


def _lab_casino_results(db, race_id):
    rows = _lab_casino_entries(db, race_id)
    return sorted(rows, key=lambda item: (int(item.get("final_rank") or 9999), int(item.get("lane_index") or 0)))


def _lab_casino_user_bet(db, race_id, user_id):
    row = db.execute(
        """
        SELECT
            b.*,
            e.display_name,
            e.bot_key,
            e.icon_path,
            e.odds,
            e.final_rank
        FROM lab_casino_bets b
        JOIN lab_casino_entries e ON e.id = b.entry_id
        WHERE b.race_id = ? AND b.user_id = ?
        LIMIT 1
        """,
        (int(race_id), int(user_id)),
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    icon_rel = _safe_static_rel(item.get("icon_path")) or DEFAULT_BADGE_REL
    item["icon_url"] = url_for("static", filename=icon_rel)
    item["odds_text"] = f"{float(item.get('odds') or 0):.1f}倍"
    item["watch_bonus"] = int(LAB_CASINO_WATCH_BONUS)
    item["net_delta"] = int(item.get("payout_amount") or 0) + int(LAB_CASINO_WATCH_BONUS) - int(item.get("amount") or 0)
    return item


def _lab_casino_history_rows(db, user_id, *, limit=30):
    rows = db.execute(
        """
        SELECT
            b.*,
            r.status AS race_status,
            r.created_at AS race_created_at,
            e.display_name,
            e.bot_key,
            e.icon_path,
            e.odds,
            e.final_rank
        FROM lab_casino_bets b
        JOIN lab_casino_races r ON r.id = b.race_id
        JOIN lab_casino_entries e ON e.id = b.entry_id
        WHERE b.user_id = ?
        ORDER BY b.created_at DESC, b.id DESC
        LIMIT ?
        """,
        (int(user_id), int(limit)),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        icon_rel = _safe_static_rel(item.get("icon_path")) or DEFAULT_BADGE_REL
        item["icon_url"] = url_for("static", filename=icon_rel)
        item["odds_text"] = f"{float(item.get('odds') or 0):.1f}倍"
        item["created_text"] = _format_jst_ts(item.get("created_at"))
        item["resolved_text"] = _format_jst_ts(item.get("resolved_at"))
        item["race_url"] = url_for("lab_race_watch", race_id=int(item["race_id"]))
        item["result_url"] = url_for("lab_race_result", race_id=int(item["race_id"]))
        item["net_delta"] = int(item.get("payout_amount") or 0) + int(LAB_CASINO_WATCH_BONUS) - int(item.get("amount") or 0)
        out.append(item)
    return out


def _lab_casino_recent_big_hits(db, *, limit=6):
    since = int(time.time()) - 7 * 86400
    rows = db.execute(
        """
        SELECT
            b.user_id,
            b.race_id,
            b.amount,
            b.payout_amount,
            b.resolved_at,
            e.display_name,
            e.odds
        FROM lab_casino_bets b
        JOIN lab_casino_entries e ON e.id = b.entry_id
        WHERE b.is_hit = 1
          AND b.payout_amount > 0
          AND COALESCE(b.resolved_at, 0) >= ?
        ORDER BY b.payout_amount DESC, b.resolved_at DESC, b.id DESC
        LIMIT ?
        """,
        (since, int(limit)),
    ).fetchall()
    return [
        {
            "username": _feed_user_label(db, row["user_id"]),
            "race_id": int(row["race_id"]),
            "display_name": row["display_name"],
            "amount": int(row["amount"]),
            "payout_amount": int(row["payout_amount"]),
            "resolved_text": _format_jst_ts(row["resolved_at"]),
            "odds_text": f"{float(row['odds'] or 0):.1f}倍",
        }
        for row in rows
    ]


def _lab_casino_prize_rows(db, *, user_id):
    rows = db.execute(
        """
        SELECT
            p.*,
            CASE WHEN my_claim.id IS NULL THEN 0 ELSE 1 END AS claimed_by_me,
            COALESCE(claims.claim_count, 0) AS claim_count
        FROM lab_casino_prizes p
        LEFT JOIN (
            SELECT prize_id, COUNT(*) AS claim_count
            FROM lab_casino_prize_claims
            GROUP BY prize_id
        ) claims ON claims.prize_id = p.id
        LEFT JOIN lab_casino_prize_claims my_claim
          ON my_claim.prize_id = p.id
         AND my_claim.user_id = ?
        WHERE p.is_active = 1
        ORDER BY p.cost_lab_coin ASC, p.id ASC
        """,
        (int(user_id),),
    ).fetchall()
    return [dict(row) for row in rows]


def _lab_casino_resolve_race(db, race_id, *, actor_user_id=None):
    race = _lab_casino_fetch_race(db, race_id)
    if not race:
        return None
    if race["status"] == "finished":
        return race
    entries = _lab_casino_entries(db, race_id)
    if not entries:
        return race
    course = _lab_course_payload_from_race(race, mode="casino")
    now_ts = int(time.time())
    if race["status"] != "running":
        db.execute(
            "UPDATE lab_casino_races SET status = 'running', started_at = COALESCE(started_at, ?) WHERE id = ?",
            (now_ts, int(race_id)),
        )
        audit_log(
            db,
            AUDIT_EVENT_TYPES["LAB_CASINO_RACE_START"],
            user_id=(int(actor_user_id) if actor_user_id else None),
            request_id=getattr(g, "request_id", None),
            action_key="lab_casino_race_start",
            entity_type="lab_casino_race",
            entity_id=int(race_id),
            payload={
                "race_id": int(race_id),
                "race_key": race["race_key"],
                "seed": int(race["seed"]),
                "entry_count": len(entries),
                "special_count": int(course.get("special_count") or 0),
                "features": [item["feature_key"] for item in course.get("selected_features", ())],
            },
            ip=request.remote_addr,
        )
    simulated = simulate_casino_race(entries, int(race["seed"]), course)
    db.execute("DELETE FROM lab_casino_frames WHERE race_id = ?", (int(race_id),))
    result_by_order = {int(item["entry_order"]): item for item in simulated["results"]}
    for frame in simulated["frames"]:
        db.execute(
            """
            INSERT INTO lab_casino_frames (race_id, frame_no, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                int(race_id),
                int(frame["frame_no"]),
                json.dumps(frame, ensure_ascii=False),
                now_ts,
            ),
        )
    winner_entry_id = None
    winner_payload = None
    for entry in entries:
        result = result_by_order.get(int(entry["entry_order"]))
        if not result:
            continue
        db.execute(
            """
            UPDATE lab_casino_entries
            SET final_rank = ?, finish_time_ms = ?, accident_count = ?
            WHERE id = ?
            """,
            (
                int(result["final_rank"]),
                int(result["finish_time_ms"]),
                int(result["accident_count"]),
                int(entry["id"]),
            ),
        )
        if int(result["final_rank"]) == 1:
            winner_entry_id = int(entry["id"])
            winner_payload = {
                "race_id": int(race_id),
                "bot_key": result["bot_key"],
                "display_name": result["display_name"],
                "odds": float(result["odds"]),
                "finish_time_ms": int(result["finish_time_ms"]),
                "features": [item["feature_key"] for item in course.get("selected_features", ())],
            }
    bet_rows = db.execute(
        """
        SELECT
            b.*,
            e.bot_key,
            e.display_name,
            e.odds
        FROM lab_casino_bets b
        JOIN lab_casino_entries e ON e.id = b.entry_id
        WHERE b.race_id = ?
        ORDER BY b.id ASC
        """,
        (int(race_id),),
    ).fetchall()
    for bet in bet_rows:
        is_hit = int(bet["entry_id"]) == int(winner_entry_id or 0)
        payout = lab_casino_payout_amount(int(bet["amount"]), float(bet["odds"])) if is_hit else 0
        delta = int(payout) + int(LAB_CASINO_WATCH_BONUS)
        before_coin, after_coin = _lab_casino_adjust_coins(db, int(bet["user_id"]), delta)
        db.execute(
            """
            UPDATE lab_casino_bets
            SET payout_amount = ?, is_hit = ?, resolved_at = ?
            WHERE id = ?
            """,
            (int(payout), 1 if is_hit else 0, now_ts, int(bet["id"])),
        )
        audit_log(
            db,
            AUDIT_EVENT_TYPES["LAB_CASINO_BET_RESOLVE"],
            user_id=int(bet["user_id"]),
            request_id=getattr(g, "request_id", None),
            action_key="lab_casino_bet_resolve",
            entity_type="lab_casino_bet",
            entity_id=int(bet["id"]),
            delta_coins=int(delta),
            payload={
                "race_id": int(race_id),
                "entry_id": int(bet["entry_id"]),
                "bot_key": bet["bot_key"],
                "amount": int(bet["amount"]),
                "odds": float(bet["odds"]),
                "is_hit": bool(is_hit),
                "payout": int(payout),
                "watch_bonus": int(LAB_CASINO_WATCH_BONUS),
                "lab_coin_before": int(before_coin),
                "lab_coin_after": int(after_coin),
                "winner_entry_id": int(winner_entry_id or 0),
            },
            ip=request.remote_addr,
        )
    db.execute(
        "UPDATE lab_casino_races SET status = 'finished', finished_at = ? WHERE id = ?",
        (now_ts, int(race_id)),
    )
    audit_log(
        db,
        AUDIT_EVENT_TYPES["LAB_CASINO_RACE_FINISH"],
        user_id=(int(actor_user_id) if actor_user_id else None),
        request_id=getattr(g, "request_id", None),
        action_key="lab_casino_race_finish",
        entity_type="lab_casino_race",
        entity_id=int(race_id),
        payload={
            "race_id": int(race_id),
            "race_key": race["race_key"],
            "winner": winner_payload,
            "entry_count": len(entries),
            "special_count": int(course.get("special_count") or 0),
        },
        ip=request.remote_addr,
    )
    return _lab_casino_fetch_race(db, race_id)

def _asset_abs(rel_path):
    return os.path.join(ASSET_ROOT, rel_path)


def _static_abs(rel_path):
    return os.path.join(STATIC_ROOT, rel_path)


def _composed_image_url(rel_path, updated_at=None):
    if not rel_path:
        return None
    version = max(int(updated_at or 0), int(PART_OFFSET_CACHE_VERSION or 0), int(COMPOSE_REV or 0))
    if version > 0:
        return url_for("static", filename=rel_path, v=version)
    return url_for("static", filename=rel_path)


def _warn_missing_asset_once(asset_key, detail=None):
    key = str(asset_key or "").strip()
    if not key:
        return
    local_seen = set()
    if has_request_context():
        local_seen = getattr(g, "_missing_asset_warned", set())
        if key in local_seen:
            return
    if key in MISSING_ASSET_WARNED_GLOBAL:
        if has_request_context():
            local_seen.add(key)
            g._missing_asset_warned = local_seen
        return
    MISSING_ASSET_WARNED_GLOBAL.add(key)
    if has_request_context():
        local_seen.add(key)
        g._missing_asset_warned = local_seen
    if detail:
        app.logger.warning("asset.missing key=%s detail=%s", key, detail)
    else:
        app.logger.warning("asset.missing key=%s", key)


def _safe_static_rel(path_value, *, warn_key=None):
    if not path_value:
        return None
    rel = path_value.replace("\\", "/").lstrip("/")
    abs_path = _static_abs(rel)
    if os.path.exists(abs_path):
        return rel
    if warn_key:
        _warn_missing_asset_once(warn_key, detail=rel)
    return None


def _expand_image_bbox(bbox, width, height, pad=4):
    if not bbox:
        return None
    left = max(0, int(bbox[0]) - int(pad))
    top = max(0, int(bbox[1]) - int(pad))
    right = min(int(width), int(bbox[2]) + int(pad))
    bottom = min(int(height), int(bbox[3]) + int(pad))
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _remove_corner_matte(image):
    if image.width < 2 or image.height < 2:
        return image
    corners = [
        image.getpixel((0, 0)),
        image.getpixel((image.width - 1, 0)),
        image.getpixel((0, image.height - 1)),
        image.getpixel((image.width - 1, image.height - 1)),
    ]
    if any(int(pixel[3]) < 240 for pixel in corners):
        return image
    base = corners[0]
    if any(max(abs(int(pixel[idx]) - int(base[idx])) for idx in range(3)) > 18 for pixel in corners[1:]):
        return image
    updated = []
    changed = False
    for pixel in image.getdata():
        rgba = tuple(int(v) for v in pixel)
        if rgba[3] < 16:
            updated.append(rgba)
            continue
        dist = max(abs(rgba[idx] - int(base[idx])) for idx in range(3))
        if dist <= 10 and rgba[3] >= 240:
            updated.append((rgba[0], rgba[1], rgba[2], 0))
            changed = True
        elif dist <= 26 and rgba[3] >= 240:
            alpha = max(0, min(255, int(round(((dist - 10) / 16.0) * 255))))
            updated.append((rgba[0], rgba[1], rgba[2], alpha))
            changed = True
        else:
            updated.append(rgba)
    if not changed:
        return image
    matte_removed = Image.new("RGBA", image.size, (0, 0, 0, 0))
    matte_removed.putdata(updated)
    return matte_removed


def _lab_scene_sprite_rel(rel_path):
    safe_rel = _safe_static_rel(rel_path)
    if not safe_rel:
        return None
    src_abs = _static_abs(safe_rel)
    if not os.path.exists(src_abs):
        return safe_rel
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", safe_rel)
    if not safe_name.lower().endswith(".png"):
        safe_name += ".png"
    out_rel = f"lab_scene_sprites/{safe_name}"
    out_abs = _static_abs(out_rel)
    src_mtime = int(os.path.getmtime(src_abs) or 0)
    if os.path.exists(out_abs) and int(os.path.getmtime(out_abs) or 0) >= src_mtime:
        return out_rel
    try:
        image = Image.open(src_abs).convert("RGBA")
        alpha = image.getchannel("A")
        bbox = alpha.getbbox()
        if not bbox or bbox == (0, 0, image.width, image.height):
            image = _remove_corner_matte(image)
            alpha = image.getchannel("A")
            bbox = alpha.getbbox()
        expanded = _expand_image_bbox(bbox, image.width, image.height, pad=6)
        if expanded:
            image = image.crop(expanded)
        if image.width > CANVAS_SIZE or image.height > CANVAS_SIZE:
            scale = min(float(CANVAS_SIZE) / float(image.width), float(CANVAS_SIZE) / float(image.height))
            image = image.resize(
                (
                    max(1, int(round(float(image.width) * scale))),
                    max(1, int(round(float(image.height) * scale))),
                ),
                Image.NEAREST,
            )
        os.makedirs(os.path.dirname(out_abs), exist_ok=True)
        image.save(out_abs, format="PNG")
        if src_mtime > 0:
            os.utime(out_abs, (src_mtime, src_mtime))
        return out_rel
    except Exception:
        return safe_rel


def _enemy_image_rel(image_path):
    rel = _safe_static_rel(image_path, warn_key=("enemy:" + str(image_path or "").strip()) if image_path else None)
    if rel:
        return rel
    return "enemies/_placeholder.png"


def _part_image_rel(part_row):
    if not part_row:
        return "enemies/_placeholder.png"
    row_keys = part_row.keys() if hasattr(part_row, "keys") else []
    image_path = part_row["image_path"] if "image_path" in row_keys else None
    part_key = part_row["key"] if "key" in row_keys else image_path
    for rel_path in _part_image_candidates(image_path):
        rel = _safe_static_rel(rel_path)
        if rel:
            return rel
    if image_path:
        _warn_missing_asset_once("part:" + str(part_key), detail=f"robot_assets/{image_path}")
    return "enemies/_placeholder.png"


def _generate_robot_badge_from_composed(composed_rel_path, out_abs_path):
    composed_abs = _static_abs(composed_rel_path)
    if not os.path.exists(composed_abs):
        return False
    img = Image.open(composed_abs).convert("RGBA")
    alpha = img.getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        return False
    pad = 3
    left = max(0, bbox[0] - pad)
    top = max(0, bbox[1] - pad)
    right = min(img.width, bbox[2] + pad)
    bottom = min(img.height, bbox[3] + pad)
    cropped = img.crop((left, top, right, bottom))
    if cropped.width <= 0 or cropped.height <= 0:
        return False

    scale = min(MAX_BADGE_INNER_SIZE / cropped.width, MAX_BADGE_INNER_SIZE / cropped.height)
    resized_w = max(1, int(round(cropped.width * scale)))
    resized_h = max(1, int(round(cropped.height * scale)))
    resized = cropped.resize((resized_w, resized_h), Image.NEAREST)

    canvas = Image.new("RGBA", (BADGE_OUTPUT_SIZE, BADGE_OUTPUT_SIZE), (0, 0, 0, 0))
    paste_x = (BADGE_OUTPUT_SIZE - resized_w) // 2
    paste_y = (BADGE_OUTPUT_SIZE - resized_h) // 2
    canvas.paste(resized, (paste_x, paste_y), resized)
    os.makedirs(os.path.dirname(out_abs_path), exist_ok=True)
    canvas.save(out_abs_path, format="PNG")
    return True


def _ensure_robot_instance_badge(db, instance_id, composed_rel_path=None):
    if not composed_rel_path:
        row = db.execute(
            "SELECT composed_image_path FROM robot_instances WHERE id = ?",
            (instance_id,),
        ).fetchone()
        composed_rel_path = row["composed_image_path"] if row else None
    badge_rel = f"robot_icons/{instance_id}.png"
    badge_abs = _static_abs(badge_rel)
    ok = False
    if composed_rel_path:
        try:
            ok = _generate_robot_badge_from_composed(composed_rel_path, badge_abs)
        except Exception:
            ok = False
    if not ok:
        default_abs = _static_abs(DEFAULT_BADGE_REL)
        if os.path.exists(default_abs):
            os.makedirs(os.path.dirname(badge_abs), exist_ok=True)
            shutil.copyfile(default_abs, badge_abs)
    db.execute(
        "UPDATE robot_instances SET icon_32_path = ?, updated_at = ? WHERE id = ?",
        (badge_rel, int(time.time()), instance_id),
    )
    db.commit()
    return badge_rel


def _robot_render_revision():
    return max(int(PART_OFFSET_CACHE_VERSION or 0), int(COMPOSE_REV or 0))


def _refresh_robot_instance_render_assets(db, robot_row, *, log_label="robot_render"):
    if not robot_row:
        return None
    data = dict(robot_row)
    robot_id = int(data["id"])
    render_rev = _robot_render_revision()
    updated_at = int(data.get("updated_at") or 0)
    composed_rel = _safe_static_rel(data.get("composed_image_path")) if data.get("composed_image_path") else None
    icon_rel = _safe_static_rel(data.get("icon_32_path")) if data.get("icon_32_path") else None
    composed_missing = not composed_rel or not os.path.exists(_static_abs(composed_rel))
    icon_missing = not icon_rel or not os.path.exists(_static_abs(icon_rel))
    render_stale = updated_at < render_rev

    if composed_missing or render_stale:
        parts = db.execute(
            "SELECT * FROM robot_instance_parts WHERE robot_instance_id = ?",
            (robot_id,),
        ).fetchone()
        if parts:
            try:
                data["composed_image_path"] = _compose_instance_image(db, {"id": robot_id}, parts)
                latest = db.execute(
                    "SELECT composed_image_path, icon_32_path, updated_at FROM robot_instances WHERE id = ?",
                    (robot_id,),
                ).fetchone()
                if latest:
                    data["composed_image_path"] = latest["composed_image_path"]
                    data["icon_32_path"] = latest["icon_32_path"]
                    data["updated_at"] = int(latest["updated_at"] or 0)
                    composed_rel = _safe_static_rel(data.get("composed_image_path")) if data.get("composed_image_path") else None
                    icon_rel = _safe_static_rel(data.get("icon_32_path")) if data.get("icon_32_path") else None
                    icon_missing = not icon_rel or not os.path.exists(_static_abs(icon_rel))
            except Exception:
                app.logger.warning("%s compose skipped id=%s", log_label, robot_id, exc_info=True)
                data["composed_image_path"] = None

    if data.get("composed_image_path") and (icon_missing or render_stale):
        try:
            data["icon_32_path"] = _ensure_robot_instance_badge(db, robot_id, data.get("composed_image_path"))
            latest = db.execute(
                "SELECT icon_32_path, updated_at FROM robot_instances WHERE id = ?",
                (robot_id,),
            ).fetchone()
            if latest:
                data["icon_32_path"] = latest["icon_32_path"]
                data["updated_at"] = int(latest["updated_at"] or 0)
        except Exception:
            app.logger.warning("%s badge skipped id=%s", log_label, robot_id, exc_info=True)

    if has_request_context():
        data["image_url"] = _composed_image_url(data.get("composed_image_path"), data.get("updated_at"))
    else:
        data["image_url"] = None
    return data


def _user_avatar_rel(row):
    rel = _safe_static_rel(row["avatar_path"]) if row and "avatar_path" in row.keys() else None
    return rel or DEFAULT_AVATAR_REL


def _user_badge_rel(db, user_id):
    pick = db.execute(
        """
        SELECT ri.id, ri.icon_32_path, ri.composed_image_path
        FROM user_showcase us
        JOIN robot_instances ri ON ri.id = us.robot_instance_id
        WHERE us.user_id = ? AND ri.status = 'active'
        ORDER BY us.slot_no ASC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    if pick is None:
        pick = db.execute(
            """
            SELECT id, icon_32_path, composed_image_path
            FROM robot_instances
            WHERE user_id = ? AND status = 'active'
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    if pick is None:
        return DEFAULT_BADGE_REL
    icon_rel = _safe_static_rel(pick["icon_32_path"]) if pick["icon_32_path"] else None
    if icon_rel:
        return icon_rel
    if pick["composed_image_path"]:
        return _ensure_robot_instance_badge(db, pick["id"], pick["composed_image_path"])
    return DEFAULT_BADGE_REL


def _user_visuals(db, user_id, cache):
    if user_id in cache:
        return cache[user_id]
    user = db.execute(
        "SELECT id, avatar_path, last_seen_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    presence = _user_presence_snapshot(user["last_seen_at"] if user else 0)
    if not user:
        cache[user_id] = {
            "avatar": DEFAULT_AVATAR_REL,
            "badge": DEFAULT_BADGE_REL,
            "presence_state": presence["state"],
            "presence_label": presence["label"],
            "presence_title": presence["title"],
        }
    else:
        cache[user_id] = {
            "avatar": _user_avatar_rel(user),
            "badge": _user_badge_rel(db, user_id),
            "presence_state": presence["state"],
            "presence_label": presence["label"],
            "presence_title": presence["title"],
        }
    return cache[user_id]


def _decorate_user_rows(db, rows, user_key="user_id"):
    cache = {}
    decorated = []
    for row in rows:
        item = dict(row)
        user_id = item.get(user_key)
        if user_id:
            visuals = _user_visuals(db, user_id, cache)
            item["avatar_path"] = visuals["avatar"]
            item["badge_path"] = visuals["badge"]
            item["presence_state"] = visuals["presence_state"]
            item["presence_label"] = visuals["presence_label"]
            item["presence_title"] = visuals["presence_title"]
        else:
            presence = _user_presence_snapshot(0)
            item["avatar_path"] = DEFAULT_AVATAR_REL
            item["badge_path"] = DEFAULT_BADGE_REL
            item["presence_state"] = presence["state"]
            item["presence_label"] = presence["label"]
            item["presence_title"] = presence["title"]
        decorated.append(item)
    return decorated


def _get_part_by_key(db, key):
    return db.execute("SELECT * FROM robot_parts WHERE key = ?", (key,)).fetchone()


def _today_progress(db, user_id):
    start_ts, end_ts = _jst_day_bounds()
    explore_count = db.execute(
        """
        SELECT COUNT(*) AS c
        FROM world_events_log
        WHERE user_id = ?
          AND event_type = 'audit.explore.end'
          AND created_at >= ? AND created_at < ?
        """,
        (user_id, start_ts, end_ts),
    ).fetchone()["c"]
    win_count = db.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN CAST(json_extract(payload_json, '$.result.win') AS INTEGER) = 1 THEN 1 ELSE 0 END), 0) AS c
        FROM world_events_log
        WHERE user_id = ?
          AND event_type = 'audit.explore.end'
          AND created_at >= ? AND created_at < ?
        """,
        (user_id, start_ts, end_ts),
    ).fetchone()["c"]
    coins = db.execute(
        """
        SELECT COALESCE(SUM(COALESCE(delta_coins, CAST(json_extract(payload_json, '$.reward_coin') AS INTEGER), 0)), 0) AS c
        FROM world_events_log
        WHERE user_id = ?
          AND event_type = 'audit.coin.delta'
          AND (
                action_key = 'explore'
                OR CAST(json_extract(payload_json, '$.area_key') AS TEXT) IS NOT NULL
              )
          AND created_at >= ? AND created_at < ?
        """,
        (user_id, start_ts, end_ts),
    ).fetchone()["c"]
    return {
        "explore_count": int(explore_count or 0),
        "win_count": int(win_count or 0),
        "coin_total": int(coins or 0),
    }


def _home_boss_pity_status(db, user_id):
    rows = db.execute(
        """
        SELECT area_key, no_boss_streak
        FROM user_boss_progress
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchall()
    by_area = {row["area_key"]: int(row["no_boss_streak"] or 0) for row in rows}
    out = []
    for area_key in AREA_BOSS_KEYS:
        if area_key in SPECIAL_EXPLORE_AREA_KEYS:
            continue
        pity = int(AREA_BOSS_PITY_MISSES.get(area_key, 15))
        streak = int(by_area.get(area_key, 0))
        out.append(
            {
                "area_key": area_key,
                "area_label": _boss_area_label(area_key),
                "streak": streak,
                "pity": pity,
                "remain": max(0, pity - streak),
            }
        )
    return out


def _home_boss_alert_status(db, user_id, now_ts=None):
    ts = int(time.time()) if now_ts is None else int(now_ts)
    out = []
    for area_key in AREA_BOSS_ALERT_AREAS:
        alert = _get_active_boss_alert(db, user_id, area_key, now_ts=ts)
        if not alert:
            continue
        layer_no = _area_layer(area_key)
        remain_sec = max(0, int(alert["expires_at"]) - ts)
        enemy_meta = _boss_type_meta(alert.get("enemy"))
        rec = _boss_recommendation_for_type(enemy_meta["code"] if enemy_meta else None)
        out.append(
            {
                "area_key": area_key,
                "area_label": _boss_area_label(area_key),
                "layer_no": int(layer_no),
                "layer_label": _layer_label(layer_no),
                "enemy_name": alert["enemy"]["name_ja"] if alert.get("enemy") else "エリアボス",
                "attempts_left": int(alert["attempts_left"]),
                "attempts_max": int(AREA_BOSS_ALERT_ATTEMPTS),
                "expires_at": int(alert["expires_at"]),
                "remain_minutes": int(math.ceil(remain_sec / 60.0)),
                "boss_type": (enemy_meta["code"] if enemy_meta else None),
                "boss_type_label": (enemy_meta["label_ja"] if enemy_meta else None),
                "boss_type_recommend": (enemy_meta["recommend_build"] if enemy_meta else None),
                "boss_type_icon": (enemy_meta["icon"] if enemy_meta else ""),
                "recommended_build": (rec["build"] if rec else None),
                "recommended_text": (rec["text"] if rec else None),
            }
        )
    return out


def _boss_alert_recommendation_context(boss_alert_status):
    if not boss_alert_status:
        return {
            "boss_alert_active": False,
            "boss_type": None,
            "recommended_build": None,
            "recommended_text": None,
        }
    first = boss_alert_status[0]
    return {
        "boss_alert_active": True,
        "boss_type": first.get("boss_type"),
        "recommended_build": first.get("recommended_build"),
        "recommended_text": first.get("recommended_text"),
    }


def _has_any_active_boss_alert(db, user_id, now_ts=None):
    return len(_home_boss_alert_status(db, user_id, now_ts=now_ts)) > 0


def _home_fuse_ready(db, user_id):
    row = db.execute(
        """
        SELECT 1
        FROM part_instances
        WHERE user_id = ? AND status = 'inventory'
        GROUP BY part_type, rarity, plus
        HAVING COUNT(*) >= 3
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    return bool(row)


def _home_build_ready(db, user_id):
    rows = db.execute(
        """
        SELECT rp.part_type
        FROM part_instances pi
        JOIN robot_parts rp ON rp.id = pi.part_id
        WHERE pi.user_id = ? AND pi.status = 'inventory' AND rp.is_active = 1
        GROUP BY rp.part_type
        """,
        (int(user_id),),
    ).fetchall()
    owned_types = {str(r["part_type"] or "").upper() for r in rows}
    return {"HEAD", "RIGHT_ARM", "LEFT_ARM", "LEGS"}.issubset(owned_types)


def _home_recent_unlocked_layer(db, user_id, now_ts=None):
    ts = int(time.time()) if now_ts is None else int(now_ts)
    since = ts - max(60, int(HOME_UNLOCK_RECENT_SECONDS))
    row = db.execute(
        """
        SELECT CAST(json_extract(payload_json, '$.unlocked_layer') AS INTEGER) AS unlocked_layer
        FROM world_events_log
        WHERE user_id = ?
          AND event_type = ?
          AND created_at >= ?
          AND CAST(json_extract(payload_json, '$.unlocked_layer') AS INTEGER) IS NOT NULL
        ORDER BY id DESC
        LIMIT 1
        """,
        (user_id, AUDIT_EVENT_TYPES["BOSS_DEFEAT"], since),
    ).fetchone()
    if not row:
        return None
    v = int(row["unlocked_layer"] or 0)
    return v if 1 <= v <= MAX_UNLOCKABLE_LAYER else None


def _has_fixed_boss_defeat_in_area(db, user_id, area_key):
    row = db.execute(
        """
        SELECT 1
        FROM world_events_log
        WHERE user_id = ?
          AND event_type = ?
          AND COALESCE(json_extract(payload_json, '$.area_key'), '') = ?
          AND COALESCE(json_extract(payload_json, '$.boss_kind'), 'fixed') = 'fixed'
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(user_id), AUDIT_EVENT_TYPES["BOSS_DEFEAT"], str(area_key or "")),
    ).fetchone()
    return bool(row)


def _evolution_feature_unlocked(db, user=None, *, user_id=None, is_admin=None, max_unlocked_layer=None):
    if user is not None:
        if user_id is None:
            user_id = int(user["id"])
        if is_admin is None:
            is_admin = bool(int(user["is_admin"] or 0)) if "is_admin" in user.keys() else False
        if max_unlocked_layer is None:
            max_unlocked_layer = int(user["max_unlocked_layer"] or 1) if "max_unlocked_layer" in user.keys() else 1
    if user_id is None:
        return False
    if bool(is_admin):
        return True
    if int(max_unlocked_layer or 0) >= 3:
        return True
    return _has_fixed_boss_defeat_in_area(db, user_id, "layer_2")


def _normalize_faction_key(faction):
    v = str(faction or "").strip().lower()
    return v if v in FACTION_KEYS else None


def _new_invite_code():
    return uuid.uuid4().hex[:8].upper()


def _ensure_user_invite_code(db, user_id):
    uid = int(user_id)
    row = db.execute("SELECT invite_code FROM users WHERE id = ?", (uid,)).fetchone()
    if not row:
        return None
    current = (row["invite_code"] or "").strip() if "invite_code" in row.keys() else ""
    if current:
        return current
    for _ in range(12):
        code = _new_invite_code()
        try:
            db.execute("UPDATE users SET invite_code = ? WHERE id = ? AND (invite_code IS NULL OR invite_code = '')", (code, uid))
            return code
        except sqlite3.IntegrityError:
            continue
    return None


def _public_game_root_url():
    if PUBLIC_GAME_URL:
        return PUBLIC_GAME_URL.rstrip("/")
    if has_request_context():
        return request.url_root.rstrip("/")
    return "https://example.com"


def _invite_link_for_code(code):
    if not code:
        return ""
    return f"{_public_game_root_url()}{url_for('register')}?ref={code}"


def _payment_checkout_ready(product_key=SUPPORT_PACK_PRODUCT_KEY):
    product = _payment_product(product_key)
    return bool(STRIPE_SECRET_KEY and product and product["price_id"])


def _payment_webhook_ready():
    return bool(STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET)


def _load_stripe_api():
    global stripe, _stripe_api_module, _stripe_api_import_error
    if stripe is not None:
        return stripe
    if _stripe_api_module is not None:
        return _stripe_api_module
    if _stripe_api_import_error is not None:
        raise RuntimeError("Stripe SDK の読み込みに失敗しました。") from _stripe_api_import_error
    try:
        _stripe_api_module = import_module("stripe")
        return _stripe_api_module
    except ModuleNotFoundError as exc:
        _stripe_api_import_error = exc
        raise RuntimeError("Stripe SDK が未インストールです。") from exc
    except Exception as exc:
        _stripe_api_import_error = exc
        raise RuntimeError("Stripe SDK の初期化に失敗しました。") from exc


def _configure_stripe_api():
    stripe_api = _load_stripe_api()
    if not STRIPE_SECRET_KEY:
        raise RuntimeError("STRIPE_SECRET_KEY が未設定です。")
    stripe_api.api_key = STRIPE_SECRET_KEY
    return stripe_api


def _stripe_value(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _get_decor_asset_by_key(db, decor_key):
    key = str(decor_key or "").strip()
    if not key:
        return None
    return db.execute("SELECT * FROM robot_decor_assets WHERE key = ?", (key,)).fetchone()


def _user_has_decor_key(db, user_id, decor_key):
    decor = _get_decor_asset_by_key(db, decor_key)
    if not decor:
        return False
    row = db.execute(
        """
        SELECT 1
        FROM user_decor_inventory
        WHERE user_id = ? AND decor_asset_id = ?
        LIMIT 1
        """,
        (int(user_id), int(decor["id"])),
    ).fetchone()
    return bool(row)


def _grant_support_reward(db, user_id, product):
    grant_type = str((product or {}).get("grant_type") or "").strip().lower()
    if grant_type != "decor":
        return {"ok": False, "granted": False, "duplicate_reason": "unsupported_grant_type", "decor_asset": None}
    decor = _get_decor_asset_by_key(db, product.get("grant_key"))
    if not decor:
        return {"ok": False, "granted": False, "duplicate_reason": "missing_decor_asset", "decor_asset": None}
    inserted = db.execute(
        """
        INSERT OR IGNORE INTO user_decor_inventory (user_id, decor_asset_id, acquired_at)
        VALUES (?, ?, ?)
        """,
        (int(user_id), int(decor["id"]), _now_ts()),
    ).rowcount > 0
    return {
        "ok": True,
        "granted": bool(inserted),
        "duplicate_reason": (None if inserted else "already_owned_decor"),
        "decor_asset": decor,
    }


def _explore_boost_until_ts(user_row):
    if not user_row or "explore_boost_until" not in user_row.keys():
        return 0
    return int(user_row["explore_boost_until"] or 0)


def _is_paid_explore_boost_active(user_row, now_ts=None):
    until_ts = _explore_boost_until_ts(user_row)
    if until_ts <= 0:
        return False
    now = _now_ts() if now_ts is None else int(now_ts)
    return until_ts > now


def _explore_boost_status_for_user(user_row, now_ts=None):
    now = _now_ts() if now_ts is None else int(now_ts)
    until_ts = _explore_boost_until_ts(user_row)
    active = until_ts > now
    remain_seconds = max(0, until_ts - now) if until_ts > 0 else 0
    remain_days = int(math.ceil(remain_seconds / 86400.0)) if remain_seconds > 0 else 0
    return {
        "active": bool(active),
        "has_ever_purchased": bool(until_ts > 0),
        "ends_at": (until_ts if until_ts > 0 else None),
        "remain_seconds": int(remain_seconds),
        "remain_days": int(remain_days),
    }


def _grant_explore_boost_reward(db, user_id, product):
    boost_days = max(1, int((product or {}).get("boost_days") or EXPLORE_BOOST_DURATION_DAYS))
    user_row = db.execute(
        "SELECT id, explore_boost_until FROM users WHERE id = ?",
        (int(user_id),),
    ).fetchone()
    if not user_row:
        return {
            "ok": False,
            "granted": False,
            "duplicate_reason": "missing_user",
            "boost_days": boost_days,
            "starts_at": None,
            "ends_at": None,
        }
    existing_until = _explore_boost_until_ts(user_row)
    if existing_until > 0:
        return {
            "ok": True,
            "granted": False,
            "duplicate_reason": "already_purchased_boost",
            "boost_days": boost_days,
            "starts_at": None,
            "ends_at": existing_until,
        }
    starts_at = _now_ts()
    ends_at = starts_at + (boost_days * 86400)
    db.execute("UPDATE users SET explore_boost_until = ? WHERE id = ?", (ends_at, int(user_id)))
    return {
        "ok": True,
        "granted": True,
        "duplicate_reason": None,
        "boost_days": boost_days,
        "starts_at": starts_at,
        "ends_at": ends_at,
    }


def _grant_payment_reward(db, user_id, product):
    grant_type = str((product or {}).get("grant_type") or "").strip().lower()
    if grant_type == "decor":
        return _grant_support_reward(db, user_id, product)
    if grant_type == "explore_boost":
        return _grant_explore_boost_reward(db, user_id, product)
    return {"ok": False, "granted": False, "duplicate_reason": "unsupported_grant_type"}


def _payment_grant_audit_event_types(product):
    grant_type = str((product or {}).get("grant_type") or "").strip().lower()
    if grant_type == "explore_boost":
        return {
            "success": AUDIT_EVENT_TYPES["EXPLORE_BOOST_GRANT_SUCCESS"],
            "skip": AUDIT_EVENT_TYPES["EXPLORE_BOOST_GRANT_SKIP_DUPLICATE"],
            "failed": AUDIT_EVENT_TYPES["EXPLORE_BOOST_GRANT_FAILED"],
        }
    return {
        "success": AUDIT_EVENT_TYPES["PAYMENT_GRANT_SUCCESS"],
        "skip": AUDIT_EVENT_TYPES["PAYMENT_GRANT_SKIP_DUPLICATE"],
        "failed": AUDIT_EVENT_TYPES["PAYMENT_GRANT_FAILED"],
    }


def _payment_status_label(status):
    status_key = str(status or "").strip().lower()
    return {
        PAYMENT_STATUS_CREATED: "支払い待ち",
        PAYMENT_STATUS_COMPLETED: "支払い完了",
        PAYMENT_STATUS_GRANTED: "付与完了",
        PAYMENT_STATUS_FAILED: "失敗",
        PAYMENT_STATUS_EXPIRED: "期限切れ",
    }.get(status_key, status_key or "-")


def _payment_order_for_session(db, stripe_checkout_session_id):
    session_id = str(stripe_checkout_session_id or "").strip()
    if not session_id:
        return None
    return db.execute(
        "SELECT * FROM payment_orders WHERE stripe_checkout_session_id = ?",
        (session_id,),
    ).fetchone()


def _latest_payment_order_for_user_product(db, user_id, product_key):
    return db.execute(
        """
        SELECT *
        FROM payment_orders
        WHERE user_id = ? AND product_key = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(user_id), str(product_key or "")),
    ).fetchone()


def _payment_return_endpoint_for_product(product_key):
    product = _payment_product(product_key)
    return str((product or {}).get("return_endpoint") or "support")


def _payment_status_labels_map():
    return {
        PAYMENT_STATUS_CREATED: _payment_status_label(PAYMENT_STATUS_CREATED),
        PAYMENT_STATUS_COMPLETED: _payment_status_label(PAYMENT_STATUS_COMPLETED),
        PAYMENT_STATUS_GRANTED: _payment_status_label(PAYMENT_STATUS_GRANTED),
        PAYMENT_STATUS_FAILED: _payment_status_label(PAYMENT_STATUS_FAILED),
        PAYMENT_STATUS_EXPIRED: _payment_status_label(PAYMENT_STATUS_EXPIRED),
    }


def _create_checkout_session_for_product(db, *, user_id, product):
    stripe_api = _configure_stripe_api()
    success_query = (
        f"product_key={quote(str(product['product_key']), safe='')}"
        "&session_id={CHECKOUT_SESSION_ID}"
    )
    cancel_query = urlencode({"product_key": product["product_key"]})
    metadata = {
        "user_id": str(int(user_id)),
        "product_key": product["product_key"],
        "grant_type": product["grant_type"],
    }
    if product.get("boost_days"):
        metadata["boost_days"] = str(int(product["boost_days"]))
    checkout_session = stripe_api.checkout.Session.create(
        mode="payment",
        line_items=[{"price": product["price_id"], "quantity": 1}],
        success_url=f"{_public_game_root_url()}{url_for('payment_success')}?{success_query}",
        cancel_url=f"{_public_game_root_url()}{url_for('payment_cancel')}?{cancel_query}",
        client_reference_id=str(int(user_id)),
        metadata=metadata,
    )
    now_ts = _now_ts()
    session_id = str(_stripe_value(checkout_session, "id", "") or "").strip()
    payment_intent_id = str(_stripe_value(checkout_session, "payment_intent", "") or "").strip() or None
    amount_jpy = _stripe_value(checkout_session, "amount_total", None)
    try:
        amount_jpy = int(amount_jpy) if amount_jpy is not None else None
    except (TypeError, ValueError):
        amount_jpy = None
    currency = str(_stripe_value(checkout_session, "currency", "") or "").lower() or "jpy"
    db.execute(
        """
        INSERT INTO payment_orders (
            user_id,
            product_key,
            stripe_checkout_session_id,
            stripe_payment_intent_id,
            amount_jpy,
            currency,
            status,
            grant_type,
            boost_days,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(user_id),
            product["product_key"],
            session_id,
            payment_intent_id,
            amount_jpy,
            currency,
            PAYMENT_STATUS_CREATED,
            product["grant_type"],
            int(product.get("boost_days") or 0),
            now_ts,
            now_ts,
        ),
    )
    order_id = int(db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
    audit_log(
        db,
        AUDIT_EVENT_TYPES["PAYMENT_CHECKOUT_CREATE"],
        user_id=int(user_id),
        request_id=getattr(g, "request_id", None),
        action_key=product["product_key"],
        entity_type="payment_order",
        entity_id=order_id,
        payload={
            "product_key": product["product_key"],
            "stripe_checkout_session_id": session_id,
            "stripe_payment_intent_id": payment_intent_id,
            "stripe_event_id": None,
            "amount_jpy": amount_jpy,
            "currency": currency,
            "status": PAYMENT_STATUS_CREATED,
            "grant_type": product["grant_type"],
            "boost_days": int(product.get("boost_days") or 0),
        },
        ip=request.remote_addr,
    )
    checkout_url = str(_stripe_value(checkout_session, "url", "") or "").strip()
    return {
        "session_id": session_id,
        "checkout_url": checkout_url,
    }


def _update_payment_order(db, order_id, **fields):
    if not fields:
        return
    fields["updated_at"] = _now_ts()
    columns = list(fields.keys())
    assignments = ", ".join(f"{col} = ?" for col in columns)
    params = [fields[col] for col in columns]
    params.append(int(order_id))
    db.execute(f"UPDATE payment_orders SET {assignments} WHERE id = ?", params)


def _referral_counts_for_referrer(db, user_id):
    uid = int(user_id)
    rows = db.execute(
        """
        SELECT status, COUNT(*) AS c
        FROM user_referrals
        WHERE referrer_user_id = ?
        GROUP BY status
        """,
        (uid,),
    ).fetchall()
    pending = 0
    qualified = 0
    for row in rows:
        status = (row["status"] or "").strip().lower()
        count = int(row["c"] or 0)
        if status == "qualified":
            qualified += count
        elif status == "pending":
            pending += count
    return {"pending": pending, "qualified": qualified}


def _attach_referral_if_valid(db, *, referred_user_id, referral_code, request_ip=None):
    code = (referral_code or "").strip().upper()
    referred_id = int(referred_user_id)
    result = "invalid_code"
    payload = {
        "referrer_user_id": None,
        "referred_user_id": referred_id,
        "referral_code": code,
        "result": result,
    }
    if not code:
        return {"ok": False, "result": "no_ref"}
    referrer = db.execute("SELECT id FROM users WHERE invite_code = ? LIMIT 1", (code,)).fetchone()
    if not referrer:
        audit_log(
            db,
            AUDIT_EVENT_TYPES["REFERRAL_ATTACH"],
            user_id=referred_id,
            request_id=(getattr(g, "request_id", None) if g else None),
            action_key="register",
            entity_type="user",
            entity_id=referred_id,
            payload=payload,
            ip=request_ip,
        )
        return {"ok": False, "result": result}
    referrer_id = int(referrer["id"])
    if referrer_id == referred_id:
        result = "ignored_self"
    else:
        db.execute(
            """
            INSERT INTO user_referrals
            (referrer_user_id, referred_user_id, referral_code, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
            ON CONFLICT(referrer_user_id, referred_user_id) DO NOTHING
            """,
            (referrer_id, referred_id, code, int(time.time())),
        )
        result = "attached"
    payload.update({"referrer_user_id": referrer_id, "result": result})
    audit_log(
        db,
        AUDIT_EVENT_TYPES["REFERRAL_ATTACH"],
        user_id=referred_id,
        request_id=(getattr(g, "request_id", None) if g else None),
        action_key="register",
        entity_type="user",
        entity_id=referred_id,
        payload=payload,
        ip=request_ip,
    )
    return {"ok": result == "attached", "result": result, "referrer_user_id": referrer_id}


def evaluate_referral_qualification(db, user_id, request_ip=None):
    uid = int(user_id)
    pending = db.execute(
        """
        SELECT id, referrer_user_id
        FROM user_referrals
        WHERE referred_user_id = ? AND status = 'pending'
        ORDER BY id ASC
        """,
        (uid,),
    ).fetchall()
    if not pending:
        return {"updated": 0, "qualified": False}
    user_row = db.execute("SELECT created_at FROM users WHERE id = ?", (uid,)).fetchone()
    if not user_row:
        return {"updated": 0, "qualified": False}
    has_robot = bool(
        db.execute(
            "SELECT 1 FROM robot_instances WHERE user_id = ? AND status != 'decomposed' LIMIT 1",
            (uid,),
        ).fetchone()
    )
    explore_count = int(
        db.execute(
            "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
            (uid, AUDIT_EVENT_TYPES["EXPLORE_END"]),
        ).fetchone()["c"]
        or 0
    )
    second_day_login = int(time.time()) >= (int(user_row["created_at"] or 0) + 86400)
    if not (has_robot and explore_count >= 10 and second_day_login):
        return {"updated": 0, "qualified": False}
    now_ts = int(time.time())
    updated = 0
    for row in pending:
        db.execute(
            "UPDATE user_referrals SET status = 'qualified', qualified_at = ? WHERE id = ? AND status = 'pending'",
            (now_ts, int(row["id"])),
        )
        updated += 1
        audit_log(
            db,
            AUDIT_EVENT_TYPES["REFERRAL_QUALIFIED"],
            user_id=uid,
            request_id=(getattr(g, "request_id", None) if g else None),
            action_key="referral_qualify",
            entity_type="user_referral",
            entity_id=int(row["id"]),
            payload={
                "referrer_user_id": int(row["referrer_user_id"] or 0),
                "referred_user_id": uid,
                "conditions": {
                    "built_robot": has_robot,
                    "explore_count": explore_count,
                    "second_day_login": second_day_login,
                },
            },
            ip=request_ip,
        )
    return {"updated": updated, "qualified": updated > 0}


def build_share_text(event_type, payload):
    if event_type == "share.boss.defeat":
        boss_name = payload.get("enemy_name") or "未知のボス"
        area_name = payload.get("area_label") or payload.get("area_key") or "不明エリア"
        actor_name = payload.get("robot_name") or payload.get("username") or "パイロット"
        return f"ボス撃破！{actor_name} が {area_name} で {boss_name} を討伐。{payload.get('game_url') or _public_game_root_url()}"
    return payload.get("game_url") or _public_game_root_url()


def _faction_unlock_counts(db, user_id):
    out = {}
    for key, rule in FACTION_UNLOCK_REQUIREMENTS.items():
        row = db.execute(
            """
            SELECT COUNT(*) AS c
            FROM world_events_log
            WHERE user_id = ? AND event_type = ?
            """,
            (int(user_id), rule["event_type"]),
        ).fetchone()
        out[key] = int((row["c"] if row else 0) or 0)
    return out


def _faction_unlock_ready(counts):
    for key, rule in FACTION_UNLOCK_REQUIREMENTS.items():
        if int(counts.get(key, 0)) < int(rule["required"]):
            return False
    return True


def _faction_unlock_progress_line(counts):
    return (
        f"陣営選択まで: 探索 {int(counts.get('explore', 0))}/{FACTION_UNLOCK_REQUIREMENTS['explore']['required']}, "
        f"編成 {int(counts.get('build', 0))}/{FACTION_UNLOCK_REQUIREMENTS['build']['required']}, "
        f"強化 {int(counts.get('fuse', 0))}/{FACTION_UNLOCK_REQUIREMENTS['fuse']['required']}"
    )


def _faction_member_counts(db):
    rows = db.execute(
        """
        SELECT faction, COUNT(*) AS c
        FROM users
        WHERE faction IN ('ignis', 'ventra', 'aurix')
        GROUP BY faction
        """
    ).fetchall()
    counts = {k: 0 for k in FACTION_KEYS}
    for row in rows:
        fk = _normalize_faction_key(row["faction"])
        if fk:
            counts[fk] = int(row["c"] or 0)
    return counts


def _faction_recommended_key(counts):
    ranked = sorted([(int(counts.get(k, 0)), k) for k in FACTION_KEYS], key=lambda x: (x[0], x[1]))
    return ranked[0][1] if ranked else None


def _faction_week_result(db, week_key):
    row = db.execute(
        """
        SELECT week_key, winner_faction, scores_json, computed_at
        FROM world_faction_weekly_result
        WHERE week_key = ?
        """,
        (str(week_key),),
    ).fetchone()
    if not row:
        return None
    try:
        scores = json.loads(row["scores_json"] or "{}")
    except json.JSONDecodeError:
        scores = {}
    return {
        "week_key": row["week_key"],
        "winner_faction": _normalize_faction_key(row["winner_faction"]),
        "scores": {k: int(scores.get(k, 0) or 0) for k in FACTION_KEYS},
        "computed_at": int(row["computed_at"] or 0),
    }


def _faction_week_scores(db, week_key):
    rows = db.execute(
        """
        SELECT faction, points
        FROM world_faction_weekly_scores
        WHERE week_key = ?
        """,
        (str(week_key),),
    ).fetchall()
    out = {k: 0 for k in FACTION_KEYS}
    for row in rows:
        fk = _normalize_faction_key(row["faction"])
        if fk:
            out[fk] = int(row["points"] or 0)
    return out


def _faction_prev_week_key(week_key):
    start = _world_week_bounds(week_key)[0]
    prev_start = start - timedelta(days=7)
    return _world_week_key(prev_start.timestamp())


def _faction_effective_winner_for_week(db, current_week_key):
    prev_week_key = _faction_prev_week_key(current_week_key)
    prev = _faction_week_result(db, prev_week_key)
    if not prev:
        return None
    return _normalize_faction_key(prev.get("winner_faction"))


def _faction_war_recompute(db, week_key):
    wk = str(week_key or _world_week_key())
    start_dt, end_dt = _world_week_bounds(wk)
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    def _count_points(event_type, extra_where="", params=None):
        where = [
            "wel.event_type = ?",
            "wel.created_at >= ?",
            "wel.created_at < ?",
            "u.faction IN ('ignis','ventra','aurix')",
        ]
        qparams = [event_type, start_ts, end_ts]
        if extra_where:
            where.append(extra_where)
        if params:
            qparams.extend(params)
        rows = db.execute(
            f"""
            SELECT u.faction, COUNT(*) AS c
            FROM world_events_log wel
            JOIN users u ON u.id = wel.user_id
            WHERE {' AND '.join(where)}
            GROUP BY u.faction
            """,
            qparams,
        ).fetchall()
        out = {k: 0 for k in FACTION_KEYS}
        for row in rows:
            fk = _normalize_faction_key(row["faction"])
            if fk:
                out[fk] = int(row["c"] or 0)
        return out

    explore_wins = _count_points(
        AUDIT_EVENT_TYPES["EXPLORE_END"],
        "CAST(COALESCE(json_extract(wel.payload_json, '$.result.win'), 0) AS INTEGER) = 1",
    )
    boss_defeats = _count_points(AUDIT_EVENT_TYPES["BOSS_DEFEAT"])
    build_confirms = _count_points(AUDIT_EVENT_TYPES["BUILD_CONFIRM"])
    fuse_runs = _count_points(AUDIT_EVENT_TYPES["FUSE"])

    scores = {k: 0 for k in FACTION_KEYS}
    for fk in FACTION_KEYS:
        scores[fk] += int(explore_wins.get(fk, 0)) * int(FACTION_WAR_POINTS["explore_win"])
        scores[fk] += int(boss_defeats.get(fk, 0)) * int(FACTION_WAR_POINTS["boss_defeat"])
        scores[fk] += int(build_confirms.get(fk, 0)) * int(FACTION_WAR_POINTS["build_confirm"])
        scores[fk] += int(fuse_runs.get(fk, 0)) * int(FACTION_WAR_POINTS["fuse"])

    ranked = sorted([(scores[k], k) for k in FACTION_KEYS], key=lambda x: (-x[0], x[1]))
    winner = ranked[0][1] if ranked else "aurix"
    now_ts = int(time.time())
    for fk in FACTION_KEYS:
        db.execute(
            """
            INSERT INTO world_faction_weekly_scores (week_key, faction, points, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(week_key, faction) DO UPDATE SET
                points = excluded.points,
                updated_at = excluded.updated_at
            """,
            (wk, fk, int(scores[fk]), now_ts),
        )
    db.execute(
        """
        INSERT INTO world_faction_weekly_result (week_key, winner_faction, scores_json, computed_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(week_key) DO UPDATE SET
            winner_faction = excluded.winner_faction,
            scores_json = excluded.scores_json,
            computed_at = excluded.computed_at
        """,
        (wk, winner, json.dumps(scores, ensure_ascii=False), now_ts),
    )
    _world_event_log(
        db,
        "FACTION_WAR_RESULT",
        {"week_key": wk, "winner_faction": winner, "scores": scores},
    )
    return {"week_key": wk, "winner_faction": winner, "scores": scores, "computed_at": now_ts}


def _ensure_faction_war_auto_close(db, current_week_key=None):
    current_wk = str(current_week_key or _world_week_key())
    prev_wk = _faction_prev_week_key(current_wk)
    if not prev_wk:
        return None
    exists = db.execute(
        "SELECT 1 FROM world_faction_weekly_result WHERE week_key = ? LIMIT 1",
        (prev_wk,),
    ).fetchone()
    if exists:
        return None
    try:
        db.execute("BEGIN IMMEDIATE")
        exists_locked = db.execute(
            "SELECT 1 FROM world_faction_weekly_result WHERE week_key = ? LIMIT 1",
            (prev_wk,),
        ).fetchone()
        if exists_locked:
            db.rollback()
            return None
        result = _faction_war_recompute(db, prev_wk)
        db.commit()
        return result
    except Exception:
        db.rollback()
        return None


def _weekly_mvp_snapshot(db, week_key):
    wk = str(week_key or _world_week_key())
    start_dt, end_dt = _world_week_bounds(wk)
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    row = db.execute(
        """
        SELECT wel.user_id, COUNT(*) AS wins
        FROM world_events_log wel
        WHERE wel.event_type = ?
          AND wel.user_id IS NOT NULL
          AND wel.created_at >= ?
          AND wel.created_at < ?
          AND CAST(COALESCE(json_extract(wel.payload_json, '$.result.win'), 0) AS INTEGER) = 1
        GROUP BY wel.user_id
        ORDER BY wins DESC, wel.user_id ASC
        LIMIT 1
        """,
        (AUDIT_EVENT_TYPES["EXPLORE_END"], start_ts, end_ts),
    ).fetchone()
    if not row:
        return None
    user_row = db.execute("SELECT id, username, active_robot_id FROM users WHERE id = ?", (int(row["user_id"]),)).fetchone()
    if not user_row:
        return None
    robot = None
    if user_row["active_robot_id"]:
        robot = db.execute(
            """
            SELECT id, name, composed_image_path, updated_at
            FROM robot_instances
            WHERE id = ? AND user_id = ? AND status = 'active'
            """,
            (int(user_row["active_robot_id"]), int(user_row["id"])),
        ).fetchone()
    if not robot:
        robot = db.execute(
            """
            SELECT id, name, composed_image_path, updated_at
            FROM robot_instances
            WHERE user_id = ? AND status = 'active'
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (int(user_row["id"]),),
        ).fetchone()
    robot_dict = dict(robot) if robot else None
    image_url = None
    if robot_dict and robot_dict.get("composed_image_path"):
        image_url = _composed_image_url(robot_dict.get("composed_image_path"), robot_dict.get("updated_at"))
    visuals = _user_visuals(db, int(user_row["id"]), {})
    return {
        "user_id": int(user_row["id"]),
        "username": user_row["username"],
        "wins": int(row["wins"] or 0),
        "robot_id": int(robot_dict["id"]) if robot_dict else None,
        "robot_name": (robot_dict["name"] if robot_dict else None),
        "robot_image_url": image_url,
        "avatar_path": visuals["avatar"],
        "badge_path": visuals["badge"],
        "presence_state": visuals["presence_state"],
        "presence_label": visuals["presence_label"],
        "presence_title": visuals["presence_title"],
    }


def _explore_area_label(area_key):
    key = str(area_key or "").strip()
    for area in EXPLORE_AREAS:
        if area["key"] == key:
            return area["label"]
    return AREA_BOSS_LABELS.get(key, key or "-")


def _world_week_remaining_line(week_key=None, now_ts=None):
    current_week_key = str(week_key or _world_week_key())
    _, end_dt = _world_week_bounds(current_week_key)
    remain = max(0, int(end_dt.timestamp()) - int(now_ts or _now_ts()))
    days = remain // 86400
    hours = (remain % 86400) // 3600
    minutes = (remain % 3600) // 60
    if days > 0:
        return f"切替まであと{days}日{hours}時間"
    if hours > 0:
        return f"切替まであと{hours}時間{minutes}分"
    return f"切替まであと{minutes}分"


def _world_hot_area_rows(db, week_key, limit=4, *, user_row=None, user_id=None, is_admin=None):
    start_dt, end_dt = _world_week_bounds(str(week_key or _world_week_key()))
    rows = db.execute(
        """
        SELECT
            COALESCE(json_extract(payload_json, '$.area_key'), '') AS area_key,
            COUNT(*) AS c
        FROM world_events_log
        WHERE event_type = ?
          AND created_at >= ?
          AND created_at < ?
        GROUP BY area_key
        ORDER BY c DESC, area_key ASC
        LIMIT ?
        """,
        (
            AUDIT_EVENT_TYPES["EXPLORE_END"],
            int(start_dt.timestamp()),
            int(end_dt.timestamp()),
            int(limit),
        ),
    ).fetchall()
    out = []
    for row in rows:
        area_key = str(row["area_key"] or "").strip()
        if not area_key:
            continue
        if not _area_visible_for_viewer(db, area_key, user_row=user_row, user_id=user_id, is_admin=is_admin):
            continue
        out.append(
            {
                "area_key": area_key,
                "area_label": _explore_area_label(area_key),
                "count": int(row["c"] or 0),
            }
        )
    return out


def _faction_score_rows(score_map, member_counts=None, *, user_faction=None, weekly_faction_key=None):
    counts = member_counts or {}
    rows = []
    for key in FACTION_KEYS:
        doctrine = FACTION_DOCTRINES.get(key, {})
        rows.append(
            {
                "key": key,
                "label": FACTION_LABELS.get(key, key),
                "points": int((score_map or {}).get(key, 0) or 0),
                "member_count": int(counts.get(key, 0) or 0),
                "emblem_path": FACTION_EMBLEMS.get(key),
                "doctrine_title": doctrine.get("title", ""),
                "doctrine_summary": doctrine.get("summary", ""),
                "focus": doctrine.get("focus", ""),
                "world_hint": doctrine.get("world_hint", ""),
                "is_user_faction": bool(user_faction and key == user_faction),
                "is_weekly_tailwind": bool(weekly_faction_key and key == weekly_faction_key),
            }
        )
    rows.sort(key=lambda item: (-int(item["points"]), item["label"]))
    return rows


def _record_preview_rows(db, metric_key, *, week_key=None, limit=3):
    rows, metric = _ranking_rows(db, metric_key, limit=limit, week_key=week_key)
    row_kind = str(metric.get("row_kind") or "user")
    if row_kind == "robot":
        rows = _decorate_user_rows(db, rows, user_key="user_id")
    else:
        rows = _decorate_user_rows(db, rows, user_key="id")
    out = []
    for idx, row in enumerate(rows, start=1):
        if row_kind == "robot":
            out.append(
                {
                    "rank": idx,
                    "title": row["robot_name"],
                    "subtitle": row["username"],
                    "value": int(row["metric_value"] or 0),
                    "value_label": metric["metric_label"],
                    "robot_id": int(row["robot_id"]),
                    "user_id": int(row["user_id"]),
                    "avatar_path": row.get("avatar_path", DEFAULT_AVATAR_REL),
                    "badge_path": row.get("badge_path", DEFAULT_BADGE_REL),
                    "image_url": row.get("image_url"),
                    "profile": row.get("profile"),
                    "presence_state": row.get("presence_state", "idle"),
                    "presence_label": row.get("presence_label", "探索待機中"),
                    "presence_title": row.get("presence_title", "いまは静かに待機中のロボ使い"),
                }
            )
        else:
            out.append(
                {
                    "rank": idx,
                    "title": row["username"],
                    "subtitle": "",
                    "value": int(row["metric_value"] or 0),
                    "value_label": metric["metric_label"],
                    "robot_id": None,
                    "user_id": int(row["id"]),
                    "avatar_path": row.get("avatar_path", DEFAULT_AVATAR_REL),
                    "badge_path": row.get("badge_path", DEFAULT_BADGE_REL),
                    "presence_state": row.get("presence_state", "idle"),
                    "presence_label": row.get("presence_label", "探索待機中"),
                    "presence_title": row.get("presence_title", "いまは静かに待機中のロボ使い"),
                }
            )
    return {
        "metric": metric,
        "rows": out,
    }


def _first_boss_record_rows(db, *, user_row=None, user_id=None, is_admin=None):
    out = []
    cache = {}
    for area in EXPLORE_AREAS:
        area_key = area["key"]
        if not _area_visible_for_viewer(db, area_key, user_row=user_row, user_id=user_id, is_admin=is_admin):
            continue
        row = db.execute(
            """
            SELECT created_at, user_id, payload_json
            FROM world_events_log
            WHERE event_type = ?
              AND COALESCE(json_extract(payload_json, '$.area_key'), '') = ?
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (AUDIT_EVENT_TYPES["BOSS_DEFEAT"], area_key),
        ).fetchone()
        if not row:
            continue
        visuals = _user_visuals(db, int(row["user_id"]), cache) if row["user_id"] else {"avatar": DEFAULT_AVATAR_REL, "badge": DEFAULT_BADGE_REL}
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        out.append(
            {
                "title": f"{area['label']} 初撃破",
                "username": _feed_user_label(db, row["user_id"]),
                "detail": " / ".join(
                    part
                    for part in [
                        str(payload.get("enemy_name") or "").strip(),
                        str(payload.get("robot_name") or "").strip(),
                    ]
                    if part
                ),
                "time_jst": _format_jst_ts(row["created_at"]),
                "avatar_path": visuals["avatar"],
                "badge_path": visuals["badge"],
                "presence_state": visuals.get("presence_state", "idle"),
                "presence_label": visuals.get("presence_label", "探索待機中"),
                "presence_title": visuals.get("presence_title", "いまは静かに待機中のロボ使い"),
            }
        )
    return out


def _first_explore_record_rows(db, area_keys=None, *, user_row=None, user_id=None, is_admin=None):
    wanted = {str(k).strip() for k in (area_keys or ()) if str(k).strip()}
    if not wanted:
        return []
    out = []
    cache = {}
    for area in EXPLORE_AREAS:
        area_key = area["key"]
        if area_key not in wanted:
            continue
        if not _area_visible_for_viewer(db, area_key, user_row=user_row, user_id=user_id, is_admin=is_admin):
            continue
        row = db.execute(
            """
            SELECT created_at, user_id, payload_json
            FROM world_events_log
            WHERE event_type = ?
              AND COALESCE(json_extract(payload_json, '$.area_key'), '') = ?
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (AUDIT_EVENT_TYPES["EXPLORE_END"], area_key),
        ).fetchone()
        if not row:
            continue
        visuals = _user_visuals(db, int(row["user_id"]), cache) if row["user_id"] else {"avatar": DEFAULT_AVATAR_REL, "badge": DEFAULT_BADGE_REL}
        out.append(
            {
                "title": f"{area['label']} 初到達",
                "username": _feed_user_label(db, row["user_id"]),
                "detail": "",
                "time_jst": _format_jst_ts(row["created_at"]),
                "avatar_path": visuals["avatar"],
                "badge_path": visuals["badge"],
                "presence_state": visuals.get("presence_state", "idle"),
                "presence_label": visuals.get("presence_label", "探索待機中"),
                "presence_title": visuals.get("presence_title", "いまは静かに待機中のロボ使い"),
            }
        )
    return out


def _first_evolve_record_rows(db):
    part_types = ("HEAD", "RIGHT_ARM", "LEFT_ARM", "LEGS")
    out = []
    cache = {}
    for part_type in part_types:
        row = db.execute(
            """
            SELECT created_at, user_id, payload_json
            FROM world_events_log
            WHERE event_type = ?
              AND UPPER(COALESCE(json_extract(payload_json, '$.part_type'), '')) = ?
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (AUDIT_EVENT_TYPES["PART_EVOLVE"], part_type),
        ).fetchone()
        if not row:
            continue
        visuals = _user_visuals(db, int(row["user_id"]), cache) if row["user_id"] else {"avatar": DEFAULT_AVATAR_REL, "badge": DEFAULT_BADGE_REL}
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        part_label = PART_TYPE_TITLES_JA.get(_normalize_part_type_key(part_type), part_type)
        target_name = str(payload.get("target_part_name") or "").strip() or "Rパーツ"
        out.append(
            {
                "title": f"{part_label} 初R化",
                "username": _feed_user_label(db, row["user_id"]),
                "detail": target_name,
                "time_jst": _format_jst_ts(row["created_at"]),
                "avatar_path": visuals["avatar"],
                "badge_path": visuals["badge"],
                "presence_state": visuals.get("presence_state", "idle"),
                "presence_label": visuals.get("presence_label", "探索待機中"),
                "presence_title": visuals.get("presence_title", "いまは静かに待機中のロボ使い"),
            }
        )
    return out


def _record_showcase_highlights(db, user_id):
    highlights = []
    for sort_key, title in (("week", "今週の話題ロボ"), ("boss", "ボス常連"), ("like", "注目展示")):
        rows = _showcase_query_rows(db, user_id=int(user_id), sort_key=sort_key, limit=1)
        if not rows:
            continue
        row = rows[0]
        highlights.append(
            {
                "title": title,
                "robot_id": int(row["id"]),
                "robot_name": row["name"],
                "username": row["username"],
                "profile": row.get("profile"),
                "sort_key": sort_key,
                "image_url": row.get("image_url"),
                "avatar_path": row.get("avatar_path", DEFAULT_AVATAR_REL),
                "badge_path": row.get("badge_path", DEFAULT_BADGE_REL),
                "presence_state": row.get("presence_state", "idle"),
                "presence_label": row.get("presence_label", "探索待機中"),
                "presence_title": row.get("presence_title", "いまは静かに待機中のロボ使い"),
            }
        )
    return highlights


def _dex_upsert_enemy(db, *, user_id, enemy_key, is_defeat=False):
    if not enemy_key:
        return
    now_ts = int(time.time())
    db.execute(
        """
        INSERT INTO user_enemy_dex
        (user_id, enemy_key, first_seen_at, first_defeated_at, seen_count, defeat_count)
        VALUES (?, ?, ?, ?, 1, ?)
        ON CONFLICT(user_id, enemy_key) DO UPDATE SET
            seen_count = seen_count + 1,
            defeat_count = defeat_count + CASE WHEN ? = 1 THEN 1 ELSE 0 END,
            first_defeated_at = CASE
                WHEN ? = 1 AND first_defeated_at IS NULL THEN excluded.first_seen_at
                ELSE first_defeated_at
            END
        """,
        (
            int(user_id),
            str(enemy_key),
            now_ts,
            (now_ts if is_defeat else None),
            (1 if is_defeat else 0),
            (1 if is_defeat else 0),
            (1 if is_defeat else 0),
        ),
    )


def _home_next_action_card(
    db,
    user,
    boss_alert_status,
    max_unlocked_layer,
    new_layer_badge,
    unlocked_layer_recent,
    faction_status=None,
):
    robot_count = int(
        db.execute(
            "SELECT COUNT(*) AS c FROM robot_instances WHERE user_id = ? AND status != 'decomposed'",
            (user["id"],),
        ).fetchone()["c"]
        or 0
    )
    has_any_robot = robot_count > 0
    if not has_any_robot:
        return {
            "title": "Next Action",
            "desc": "まずは機体を1体完成させよう",
            "cta_label": "ロボを編成する",
            "cta_url": url_for("build"),
            "is_post": False,
            "area_key": None,
            "boss_enter": False,
        }
    if _get_active_robot(db, user["id"]) is None:
        return {
            "title": "Next Action",
            "desc": "出撃機体が未設定です",
            "cta_label": "ロボを編成する",
            "cta_url": url_for("build"),
            "is_post": False,
            "area_key": None,
            "boss_enter": False,
        }
    if boss_alert_status:
        alert = boss_alert_status[0]
        remain = "●" * max(1, int(alert.get("attempts_left") or 0))
        return {
            "title": "Next Action",
            "desc": "ボス警報が発令中",
            "cta_label": f"ボスに挑戦（残り{remain}）",
            "cta_url": url_for("explore"),
            "is_post": True,
            "area_key": alert["area_key"],
            "boss_enter": True,
        }
    unlocked_layer = int(new_layer_badge or 0) or int(unlocked_layer_recent or 0)
    if unlocked_layer:
        return {
            "title": "Next Action",
            "desc": "新しい層が開いた",
            "cta_label": f"NEW 第{unlocked_layer}層へ行く",
            "cta_url": url_for("map_view"),
            "is_post": False,
            "area_key": None,
            "boss_enter": False,
        }
    current_layer = max(1, min(MAX_UNLOCKABLE_LAYER, int(max_unlocked_layer or 1)))
    area_key = HOME_PRIMARY_AREA_BY_LAYER.get(current_layer, "layer_1")
    if current_layer == 1:
        if _home_fuse_ready(db, int(user["id"])):
            return {
                "title": "Next Action",
                "desc": "パーツを強化しよう",
                "cta_label": "パーツ強化へ",
                "cta_url": url_for("parts_strengthen", mode="select"),
                "is_post": False,
                "area_key": None,
                "boss_enter": False,
            }
        if _home_build_ready(db, int(user["id"])):
            return {
                "title": "Next Action",
                "desc": "自分だけのロボを組み立ててみよう",
                "cta_label": "ロボを編成する",
                "cta_url": url_for("build"),
                "is_post": False,
                "area_key": None,
                "boss_enter": False,
            }
        if robot_count >= 2:
            return {
                "title": "Next Action",
                "desc": "作ったロボを見てみよう",
                "cta_label": "ロボ一覧を見る",
                "cta_url": url_for("robots"),
                "is_post": False,
                "area_key": None,
                "boss_enter": False,
            }
        return {
            "title": "Next Action",
            "desc": "出撃してパーツを集めよう",
            "cta_label": "出撃",
            "cta_url": url_for("explore"),
            "is_post": True,
            "area_key": area_key,
            "boss_enter": False,
        }
    if (
        current_layer >= 4
        and _is_special_area_unlocked(db, int(user["id"]), LAYER4_FINAL_AREA_KEY)
        and not _has_fixed_boss_defeat_in_area(db, int(user["id"]), LAYER4_FINAL_AREA_KEY)
    ):
        return {
            "title": "Next Action",
            "desc": "第4層最終試験が解放中",
            "cta_label": "アーク=ゼロに挑む",
            "cta_url": url_for("explore"),
            "is_post": True,
            "area_key": LAYER4_FINAL_AREA_KEY,
            "boss_enter": False,
        }
    if (
        current_layer >= 5
        and _is_special_area_unlocked(db, int(user["id"]), LAYER5_FINAL_AREA_KEY)
        and not _has_fixed_boss_defeat_in_area(db, int(user["id"]), LAYER5_FINAL_AREA_KEY)
    ):
        return {
            "title": "Next Action",
            "desc": "第5層最終試験が解放中",
            "cta_label": "オメガフレームに挑む",
            "cta_url": url_for("explore"),
            "is_post": True,
            "area_key": LAYER5_FINAL_AREA_KEY,
            "boss_enter": False,
        }
    if current_layer < MAX_UNLOCKABLE_LAYER:
        return {
            "title": "Next Action",
            "desc": f"{_layer_label(current_layer)}の代表エリアへ",
            "cta_label": f"第{current_layer}層ボスを狙う",
            "cta_url": url_for("explore"),
            "is_post": True,
            "area_key": area_key,
            "boss_enter": False,
        }
    if _home_fuse_ready(db, int(user["id"])):
        return {
            "title": "Next Action",
            "desc": "同じパーツ3個で +1",
            "cta_label": "パーツ強化へ",
            "cta_url": url_for("parts_strengthen", mode="select"),
            "is_post": False,
            "area_key": None,
            "boss_enter": False,
        }
    return {
        "title": "Next Action",
        "desc": f"{_layer_label(current_layer)}を周回",
        "cta_label": "出撃",
        "cta_url": url_for("explore"),
        "is_post": True,
        "area_key": area_key,
        "boss_enter": False,
    }


def _recent_drop_items(db, user_id, limit=5):
    start_ts, _ = _jst_day_bounds()
    rows = db.execute(
        """
        SELECT id, created_at, payload_json
        FROM world_events_log
        WHERE user_id = ?
          AND event_type = 'audit.drop'
          AND created_at >= ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (user_id, start_ts, int(limit)),
    ).fetchall()
    if not rows:
        rows = db.execute(
            """
            SELECT id, created_at, payload_json
            FROM world_events_log
            WHERE user_id = ?
              AND event_type = 'audit.drop'
              AND created_at >= ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, int(time.time()) - 86400, int(limit)),
        ).fetchall()

    items = []
    for r in rows:
        try:
            payload = json.loads(r["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        part_key = payload.get("part_key")
        part_type = payload.get("part_type")
        rarity = payload.get("rarity")
        plus = int(payload.get("plus") or 0)
        part_row = _get_part_by_key(db, part_key) if part_key else None
        display_name = _part_display_name_ja(part_row) if part_row else (part_key or "-")
        items.append(
            {
                "part_type": part_type,
                "part_key": part_key,
                "part_display_name": display_name,
                "rarity": rarity,
                "plus": plus,
                "element": ((part_row["element"] if part_row else None) or "-"),
                "image_url": url_for("static", filename=_part_image_rel(part_row)),
                "link": url_for("parts", tab="instances"),
            }
        )
    return items


FEED_EVENT_TYPES = {
    "boss": {"audit.boss.defeat"},
    "evolve": {"audit.part.evolve"},
    "drop": {"audit.drop"},
    "fuse": {"audit.fuse"},
    "build": {"audit.build.confirm"},
    "lab": set(LAB_WORLD_EVENT_TYPES),
    "weekly": {"week_rollover", "admin_world_reroll", "admin_world_reset_counters", "weekly_drop_promoted", "daily_title_posted", "FACTION_WAR_RESULT", "RESEARCH_UNLOCK"},
}
FEED_WEEKLY_PUBLIC_EVENTS = {"week_rollover", "weekly_drop_promoted", "daily_title_posted", "FACTION_WAR_RESULT", "RESEARCH_UNLOCK"}
FEED_WEEKLY_ADMIN_EVENTS = {"admin_world_reroll", "admin_world_reset_counters"}
WORLD_LOG_SYSTEM_EVENT_TYPES = {
    AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
    "week_rollover",
    "FACTION_WAR_RESULT",
    "daily_title_posted",
    "RESEARCH_UNLOCK",
    *LAB_WORLD_EVENT_TYPES,
}
WORLD_LOG_RANKING_METRICS = (
    {
        "key": "weekly_explores",
        "event_type": AUDIT_EVENT_TYPES["EXPLORE_END"],
        "title": "探索ランキング速報",
        "text_label": "探索周回",
        "value_suffix": "回",
    },
    {
        "key": "weekly_bosses",
        "event_type": AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
        "title": "ボスランキング速報",
        "text_label": "ボス撃破",
        "value_suffix": "体",
    },
)
PERSONAL_LOG_EVENT_TYPES = (
    AUDIT_EVENT_TYPES["DROP"],
    AUDIT_EVENT_TYPES["FUSE"],
    AUDIT_EVENT_TYPES["BUILD_CONFIRM"],
    AUDIT_EVENT_TYPES["BOSS_ENCOUNTER"],
    AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
    AUDIT_EVENT_TYPES["EXPLORE_END"],
    AUDIT_EVENT_TYPES["PART_EVOLVE"],
    AUDIT_EVENT_TYPES["REFERRAL_QUALIFIED"],
    AUDIT_EVENT_TYPES["CORE_GUARANTEE"],
)


def _format_jst_ts(ts):
    if not ts:
        return "-"
    return datetime.fromtimestamp(int(ts), JST).strftime("%Y-%m-%d %H:%M")


def _parse_jst_day_filter(raw_value, *, end=False):
    text = str(raw_value or "").strip()
    if not text:
        return None
    try:
        base = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=JST)
    except ValueError:
        return None
    if end:
        base = base + timedelta(days=1)
    return int(base.timestamp())


def _feed_user_label(db, user_id):
    if user_id is None:
        return "SYSTEM"
    row = db.execute("SELECT username, is_admin FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if row and row["username"]:
        return _display_username(row["username"], is_admin=bool(int(row["is_admin"] or 0)))
    return f"User#{int(user_id)}"


def _part_image_url(part_row):
    return url_for("static", filename=_part_image_rel(part_row))


def _feed_enemy_row(db, row, payload):
    enemy_key = str(payload.get("enemy_key") or "").strip()
    if enemy_key:
        enemy = db.execute(
            "SELECT id, key, name_ja, image_path FROM enemies WHERE key = ?",
            (enemy_key,),
        ).fetchone()
        if enemy:
            return enemy
    entity_type = str((row["entity_type"] if "entity_type" in row.keys() else "") or "").strip().lower()
    entity_id = row["entity_id"] if "entity_id" in row.keys() else None
    if entity_type == "enemy" and entity_id:
        return db.execute(
            "SELECT id, key, name_ja, image_path FROM enemies WHERE id = ?",
            (int(entity_id),),
        ).fetchone()
    return None


def _feed_card_from_event(db, row):
    payload_raw = row["payload_json"] if "payload_json" in row.keys() else None
    try:
        payload = json.loads(payload_raw or "{}")
    except json.JSONDecodeError:
        payload = {}
    event_type = row["event_type"]
    card = {
        "id": int(row["id"]),
        "created_ts": int(row["created_at"] or 0),
        "event_type": event_type,
        "user_id": (int(row["user_id"]) if row["user_id"] is not None else None),
        "user_label": _feed_user_label(db, row["user_id"]) if "user_id" in row.keys() else "SYSTEM",
        "time_jst": _format_jst_ts(row["created_at"]),
        "text": event_type,
        "image_url": None,
        "link_url": None,
        "headline": "WORLD LOG",
        "accent": "default",
        "meta_lines": [],
    }
    if event_type == AUDIT_EVENT_TYPES["BOSS_DEFEAT"]:
        actor_label = card["user_label"]
        boss_name = str(payload.get("enemy_name") or "").strip() or "ボス"
        robot_name = str(payload.get("robot_name") or "").strip()
        area_label = str(payload.get("area_label") or "").strip()
        if not area_label and payload.get("area_key"):
            area_label = _boss_area_label(payload.get("area_key"))
        card["headline"] = "BOSS DEFEATED"
        card["accent"] = "boss"
        if robot_name:
            card["text"] = f"ボス撃破: {actor_label} の {robot_name} が {boss_name} を討伐"
            card["meta_lines"].append(f"機体: {robot_name}")
        else:
            card["text"] = f"ボス撃破: {actor_label} が {boss_name} を討伐"
        card["meta_lines"].append(f"対象: {boss_name}")
        if area_label:
            card["text"] += f"（{area_label}）"
            card["meta_lines"].append(f"戦域: {area_label}")
        enemy_row = _feed_enemy_row(db, row, payload)
        if enemy_row:
            card["image_url"] = url_for("static", filename=_enemy_image_rel(enemy_row["image_path"]))
    elif event_type == "LAB_RACE_WIN":
        username = str(payload.get("username") or "LAB ENEMY").strip() or "LAB ENEMY"
        robot_name = str(payload.get("robot_name") or "実験機").strip() or "実験機"
        card["headline"] = "LAB RACE"
        card["accent"] = "weekly"
        card["text"] = f"実験室レース優勝: {username} の 『{robot_name}』 が1着"
        card["meta_lines"] = [
            f"コース: {_lab_course_meta(payload.get('course_key')).get('label')}",
            f"完走: {_lab_format_time_ms(payload.get('finish_time_ms'))}",
        ]
        if payload.get("race_id"):
            card["link_url"] = url_for("lab_race_legacy_watch", race_id=int(payload["race_id"]))
    elif event_type == "LAB_RACE_UPSET":
        username = str(payload.get("username") or "LAB ENEMY").strip() or "LAB ENEMY"
        robot_name = str(payload.get("robot_name") or "実験機").strip() or "実験機"
        card["headline"] = "LAB UPSET"
        card["accent"] = "drop"
        card["text"] = f"大逆転: {username} の 『{robot_name}』 が実験室で1着"
        if payload.get("worst_rank"):
            card["meta_lines"] = [f"一時順位: {int(payload['worst_rank'])}位付近"]
        if payload.get("race_id"):
            card["link_url"] = url_for("lab_race_legacy_watch", race_id=int(payload["race_id"]))
    elif event_type == "LAB_RACE_POPULAR_ENTRY":
        title = str(payload.get("title") or "投稿ロボ").strip() or "投稿ロボ"
        username = str(payload.get("username") or "unknown").strip() or "unknown"
        likes_count = int(payload.get("likes_count") or 0)
        card["headline"] = "LAB SHOWCASE"
        card["accent"] = "build"
        card["text"] = f"投稿ロボ『{title}』が実験室で話題に浮上"
        card["meta_lines"] = [f"投稿者: {username}", f"いいね: {likes_count}"]
        if payload.get("submission_id"):
            card["link_url"] = url_for("lab_submission_detail", submission_id=int(payload["submission_id"]))
    elif event_type == AUDIT_EVENT_TYPES["PART_EVOLVE"]:
        actor_label = card["user_label"]
        target_part_key = str(payload.get("target_part_key") or "").strip()
        part_row = _get_part_by_key(db, target_part_key) if target_part_key else None
        target_name = str(payload.get("target_part_name") or "").strip()
        if not target_name and part_row:
            target_name = _part_display_name_ja(part_row)
        part_type = payload.get("part_type") or (part_row["part_type"] if part_row else "")
        part_type_label = PART_TYPE_TITLES_JA.get(_normalize_part_type_key(part_type), "パーツ")
        target_name = target_name or "Rパーツ"
        card["headline"] = "進化成功"
        card["accent"] = "evolve"
        card["text"] = f"進化成功: {actor_label} が {part_type_label}『{target_name}』をR化"
        card["meta_lines"] = [f"部位: {part_type_label}", f"対象: {target_name}"]
        if part_row:
            card["image_url"] = _part_image_url(part_row)
        card["link_url"] = url_for("evolve_parts")
    elif event_type == "audit.drop":
        card["headline"] = "パーツ入手"
        part_key = payload.get("part_key")
        part_type = payload.get("part_type") or "-"
        rarity = payload.get("rarity") or "-"
        plus = int(payload.get("plus") or 0)
        part_row = _get_part_by_key(db, part_key) if part_key else None
        display_name = _part_display_name_ja(part_row) if part_row else (part_key or "-")
        card["text"] = f"パーツを入手: {part_type} {rarity} {display_name} +{plus}"
        card["image_url"] = _part_image_url(part_row)
        card["link_url"] = url_for("parts", tab="instances")
    elif event_type == "audit.fuse":
        card["headline"] = "強化結果"
        outcome = payload.get("outcome") or "-"
        part_type = payload.get("part_type") or "-"
        rarity = payload.get("rarity") or "-"
        from_plus = payload.get("from_plus")
        to_plus = payload.get("to_plus")
        card["text"] = f"強化 {outcome}: {part_type} {rarity} +{from_plus}→+{to_plus}"
        created_id = payload.get("created_id")
        if created_id:
            pi = db.execute(
                """
                SELECT rp.*
                FROM part_instances pi
                JOIN robot_parts rp ON rp.id = pi.part_id
                WHERE pi.id = ?
                """,
                (int(created_id),),
            ).fetchone()
            card["image_url"] = _part_image_url(pi)
        card["link_url"] = url_for("parts_strengthen")
    elif event_type == "audit.build.confirm":
        card["headline"] = "ロボ完成"
        robot_name = payload.get("robot_name") or "新ロボ"
        card["text"] = f"ロボを完成: {robot_name}"
        rid = payload.get("robot_instance_id") or row["entity_id"]
        if rid:
            ri = db.execute(
                "SELECT composed_image_path, updated_at FROM robot_instances WHERE id = ?",
                (int(rid),),
            ).fetchone()
            if ri and ri["composed_image_path"]:
                card["image_url"] = _composed_image_url(ri["composed_image_path"], ri["updated_at"])
        card["link_url"] = url_for("robots")
    elif event_type == "week_rollover":
        card["headline"] = "週次更新"
        wk = payload.get("week_key") or "-"
        card["text"] = f"週次更新: {wk} が開始"
        if payload.get("chosen_element") or payload.get("mode"):
            elem = ELEMENT_LABEL_MAP.get(str(payload.get("chosen_element") or "").upper(), payload.get("chosen_element") or "-")
            mode = payload.get("mode") or "-"
            card["meta_lines"].append(f"今週属性: {elem}")
            card["meta_lines"].append(f"世界状態: {mode}")
        card["accent"] = "weekly"
    elif event_type == "FACTION_WAR_RESULT":
        winner = _normalize_faction_key(payload.get("winner_faction"))
        scores = payload.get("scores") or {}
        wk = payload.get("week_key") or "-"
        card["headline"] = "陣営戦決着"
        card["accent"] = "weekly"
        card["text"] = f"陣営戦決着: {wk} の勝者は {FACTION_LABELS.get(winner, winner or '未確定')}"
        card["meta_lines"] = [
            f"IGNIS {int(scores.get('ignis', 0) or 0)} / VENTRA {int(scores.get('ventra', 0) or 0)} / AURIX {int(scores.get('aurix', 0) or 0)}"
        ]
        card["link_url"] = url_for("world_view")
    elif event_type == "RESEARCH_UNLOCK":
        wk = payload.get("week_key") or "-"
        element = str(payload.get("element") or "").upper()
        part_type = str(payload.get("part_type") or "").strip().upper()
        element_label = ELEMENT_LABEL_MAP.get(element, element or "-")
        part_label = PART_TYPE_TITLES_JA.get(_normalize_part_type_key(part_type), RESEARCH_PART_TYPE_LABELS_JA.get(part_type, part_type or "パーツ"))
        card["headline"] = "研究解禁"
        card["accent"] = "weekly"
        card["text"] = f"研究解禁: {element_label} 系の {part_label} が解放（{wk}）"
        card["meta_lines"] = [f"属性: {element_label}", f"部位: {part_label}"]
        card["link_url"] = url_for("world_view")
    elif event_type == "admin_world_reroll":
        card["headline"] = "世界再抽選"
        wk = payload.get("week_key") or "-"
        card["text"] = f"世界状態が再抽選されました（{wk}）"
    elif event_type == "admin_world_reset_counters":
        card["headline"] = "週カウンタ再設定"
        wk = payload.get("week_key") or "-"
        card["text"] = f"週カウンタがリセットされました（{wk}）"
    elif event_type == "weekly_drop_promoted":
        card["headline"] = "週ボーナス"
        wk = payload.get("week_key") or "-"
        card["text"] = f"週ボーナス発動: ドロップ昇格（{wk}）"
    elif event_type == "daily_title_posted":
        card["headline"] = "本日の称号"
        title = payload.get("title") or "称号"
        card["text"] = f"本日の称号発見: {title}"
    return card


def _world_system_card_item(card, *, item_id=None, sort_ts=None, sort_id=None):
    base_id = int(item_id if item_id is not None else (card.get("id") or 0))
    created_ts = int(sort_ts if sort_ts is not None else (card.get("created_ts") or 0))
    order_id = int(sort_id if sort_id is not None else base_id)
    return {
        "timeline_type": "system",
        "id": base_id,
        "sort_ts": created_ts,
        "sort_id": order_id,
        "card": card,
    }


def _world_log_is_first_fixed_boss_defeat(db, row_id, area_key):
    key = str(area_key or "").strip()
    if not key:
        return False
    first_row = db.execute(
        """
        SELECT id
        FROM world_events_log
        WHERE event_type = ?
          AND COALESCE(json_extract(payload_json, '$.area_key'), '') = ?
          AND LOWER(COALESCE(json_extract(payload_json, '$.boss_kind'), 'fixed')) = 'fixed'
        ORDER BY created_at ASC, id ASC
        LIMIT 1
        """,
        (AUDIT_EVENT_TYPES["BOSS_DEFEAT"], key),
    ).fetchone()
    return bool(first_row and int(first_row["id"]) == int(row_id))


def _world_first_boss_card(db, row, payload):
    actor_label = _feed_user_label(db, row["user_id"])
    boss_name = str(payload.get("enemy_name") or "").strip() or "ボス"
    robot_name = str(payload.get("robot_name") or "").strip()
    area_label = str(payload.get("area_label") or "").strip()
    if not area_label and payload.get("area_key"):
        area_label = _boss_area_label(payload.get("area_key"))
    enemy_row = _feed_enemy_row(db, row, payload)
    text = f"ボス初討伐: {actor_label} が {boss_name} を初めて討伐"
    if area_label:
        text += f"（{area_label}）"
    meta_lines = [f"対象: {boss_name}"]
    if robot_name:
        meta_lines.append(f"機体: {robot_name}")
    if area_label:
        meta_lines.append(f"戦域: {area_label}")
    return {
        "id": int(row["id"]) * 10 + 1,
        "created_ts": int(row["created_at"] or 0),
        "event_type": "world.boss.first_defeat",
        "user_id": (int(row["user_id"]) if row["user_id"] is not None else None),
        "user_label": actor_label,
        "time_jst": _format_jst_ts(row["created_at"]),
        "text": text,
        "image_url": (
            url_for("static", filename=_enemy_image_rel(enemy_row["image_path"]))
            if enemy_row
            else None
        ),
        "link_url": url_for("world_view"),
        "headline": "BOSS FIRST",
        "accent": "boss",
        "meta_lines": meta_lines,
    }


def _world_layer_unlock_card(db, row, payload, unlocked_layer):
    actor_label = _feed_user_label(db, row["user_id"])
    boss_name = str(payload.get("enemy_name") or "").strip() or "ボス"
    area_label = str(payload.get("area_label") or "").strip()
    if not area_label and payload.get("area_key"):
        area_label = _boss_area_label(payload.get("area_key"))
    meta_lines = [f"解放先: 第{int(unlocked_layer)}層", f"契機: {boss_name}"]
    if area_label:
        meta_lines.append(f"戦域: {area_label}")
    return {
        "id": int(row["id"]) * 10 + 2,
        "created_ts": int(row["created_at"] or 0),
        "event_type": "world.layer.unlock",
        "user_id": (int(row["user_id"]) if row["user_id"] is not None else None),
        "user_label": actor_label,
        "time_jst": _format_jst_ts(row["created_at"]),
        "text": f"層解放: {actor_label} が第{int(unlocked_layer)}層へのルートを開いた",
        "image_url": None,
        "link_url": url_for("map_view"),
        "headline": "LAYER OPEN",
        "accent": "weekly",
        "meta_lines": meta_lines,
    }


def _latest_world_event_ts(db, *, event_type, user_id=None, start_ts=None, end_ts=None):
    where = ["event_type = ?"]
    params = [str(event_type)]
    if user_id is not None:
        where.append("user_id = ?")
        params.append(int(user_id))
    if start_ts is not None:
        where.append("created_at >= ?")
        params.append(int(start_ts))
    if end_ts is not None:
        where.append("created_at < ?")
        params.append(int(end_ts))
    row = db.execute(
        f"""
        SELECT MAX(created_at) AS latest_created_at
        FROM world_events_log
        WHERE {' AND '.join(where)}
        """,
        params,
    ).fetchone()
    return int((row["latest_created_at"] if row else 0) or 0)


def _world_ranking_timeline_items(db):
    week_key = _world_week_key()
    start_dt, end_dt = _world_week_bounds(week_key)
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    items = []
    for index, metric in enumerate(WORLD_LOG_RANKING_METRICS):
        rows = _ranking_rows_from_event_log(
            db,
            event_type=metric["event_type"],
            limit=3,
            start_ts=start_ts,
            end_ts=end_ts,
        )
        if not rows:
            continue
        leader = rows[0]
        latest_ts = _latest_world_event_ts(
            db,
            event_type=metric["event_type"],
            start_ts=start_ts,
            end_ts=end_ts,
        )
        card = {
            "id": 900000 + index,
            "created_ts": int(latest_ts),
            "event_type": f"world.ranking.{metric['key']}",
            "user_id": int(leader["id"]),
            "user_label": leader["username"],
            "time_jst": _format_jst_ts(latest_ts),
            "text": f"ランキング速報: {metric['text_label']}は {leader['username']} が {int(leader['metric_value'])}{metric['value_suffix']}で首位",
            "image_url": None,
            "link_url": url_for("ranking", metric=metric["key"]),
            "headline": metric["title"],
            "accent": "weekly",
            "meta_lines": [
                f"{rank}位 {row['username']} {int(row['metric_value'])}{metric['value_suffix']}"
                for rank, row in enumerate(rows[:3], start=1)
            ],
        }
        items.append(
            _world_system_card_item(
                card,
                item_id=card["id"],
                sort_ts=latest_ts,
                sort_id=card["id"],
            )
        )
    return items


def _world_system_timeline_items(db, *, limit=COMM_WORLD_TIMELINE_LIMIT, is_admin=False):
    event_types = tuple(sorted(WORLD_LOG_SYSTEM_EVENT_TYPES))
    fetch_limit = max(int(limit) * 12, 120)
    rows = db.execute(
        f"""
        SELECT id, created_at, event_type, payload_json, user_id, action_key, entity_type, entity_id
        FROM world_events_log
        WHERE event_type IN ({",".join(["?"] * len(event_types))})
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (*event_types, fetch_limit),
    ).fetchall()
    items = []
    for row in rows:
        event_type = str(row["event_type"] or "")
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        if not _event_visible_for_viewer(db, event_type, payload, is_admin=is_admin):
            continue
        created_ts = int(row["created_at"] or 0)
        row_id = int(row["id"])
        if event_type == AUDIT_EVENT_TYPES["BOSS_DEFEAT"]:
            boss_kind = str(payload.get("boss_kind") or "fixed").strip().lower()
            if boss_kind == "fixed" and _world_log_is_first_fixed_boss_defeat(db, row_id, payload.get("area_key")):
                boss_card = _world_first_boss_card(db, row, payload)
                items.append(
                    _world_system_card_item(
                        boss_card,
                        item_id=boss_card["id"],
                        sort_ts=created_ts,
                        sort_id=boss_card["id"],
                    )
                )
            unlocked_layer = int(payload.get("unlocked_layer") or 0)
            if unlocked_layer > 0:
                unlock_card = _world_layer_unlock_card(db, row, payload, unlocked_layer)
                items.append(
                    _world_system_card_item(
                        unlock_card,
                        item_id=unlock_card["id"],
                        sort_ts=created_ts,
                        sort_id=unlock_card["id"],
                    )
                )
            continue
        card = _feed_card_from_event(db, row)
        items.append(_world_system_card_item(card, item_id=row_id, sort_ts=created_ts, sort_id=row_id))
    items.extend(_world_ranking_timeline_items(db))
    items.sort(key=lambda item: (int(item.get("sort_ts") or 0), int(item.get("sort_id") or 0)), reverse=True)
    return items[: int(limit)]


def _world_user_message_items(db, limit=COMM_WORLD_TIMELINE_LIMIT):
    rows = _decorate_user_rows(db, _chat_room_rows(db, COMM_WORLD_ROOM_KEY, limit=limit))
    items = []
    for row in rows:
        username = str(row.get("username") or "").strip()
        if username.upper() == "SYSTEM":
            continue
        created_ts = _chat_created_at_ts(row.get("created_at"))
        items.append(
            {
                "timeline_type": "user",
                "id": int(row["id"]),
                "sort_ts": int(created_ts),
                "sort_id": int(row["id"]),
                "user_id": (int(row["user_id"]) if row.get("user_id") else None),
                "user_label": username or _feed_user_label(db, row.get("user_id")),
                "message": str(row.get("message") or "").strip(),
                "time_jst": (_format_jst_ts(created_ts) if created_ts else str(row.get("created_at") or "-")),
                "avatar_path": row.get("avatar_path") or DEFAULT_AVATAR_REL,
                "badge_path": row.get("badge_path") or DEFAULT_BADGE_REL,
                "presence_state": row.get("presence_state") or "idle",
                "presence_label": row.get("presence_label") or "探索待機中",
                "presence_title": row.get("presence_title") or "いまは静かに待機中のロボ使い",
            }
        )
    return items


def _world_legacy_system_message_items(db, limit=COMM_WORLD_TIMELINE_LIMIT):
    rows = _chat_room_rows(db, COMM_WORLD_ROOM_KEY, limit=limit * 2)
    items = []
    for row in rows:
        username = str(row["username"] or "").strip().upper()
        message = str(row["message"] or "").strip()
        if username != "SYSTEM" or not message:
            continue
        if HOME_BUILD_CHAT_PATTERN.search(message):
            continue
        if message.startswith("【BOSS撃破】"):
            continue
        if message.startswith("今週の戦況:"):
            continue
        if message.startswith("『") and "パーツが発見された！" in message:
            continue
        created_ts = _chat_created_at_ts(row["created_at"])
        items.append(
            {
                "timeline_type": "legacy_system",
                "id": int(row["id"]),
                "sort_ts": int(created_ts),
                "sort_id": int(row["id"]),
                "headline": "SYSTEM NOTE",
                "text": message,
                "time_jst": (_format_jst_ts(created_ts) if created_ts else str(row["created_at"] or "-")),
            }
        )
    return items[: int(limit)]


def _home_world_user_message_items(db, limit=HOME_COMM_PREVIEW_LIMIT):
    rows = _decorate_user_rows(db, _home_chat_messages(db, limit=limit))
    items = []
    for row in rows:
        username = str(row.get("username") or "").strip()
        if username.upper() == "SYSTEM":
            continue
        created_ts = _chat_created_at_ts(row.get("created_at"))
        items.append(
            {
                "timeline_type": "user",
                "id": int(row["id"]),
                "sort_ts": int(created_ts),
                "sort_id": int(row["id"]),
                "user_id": (int(row["user_id"]) if row.get("user_id") else None),
                "user_label": username or _feed_user_label(db, row.get("user_id")),
                "message": str(row.get("message") or "").strip(),
                "time_jst": (_format_jst_ts(created_ts) if created_ts else str(row.get("created_at") or "-")),
                "avatar_path": row.get("avatar_path") or DEFAULT_AVATAR_REL,
                "badge_path": row.get("badge_path") or DEFAULT_BADGE_REL,
                "presence_state": row.get("presence_state") or "idle",
                "presence_label": row.get("presence_label") or "探索待機中",
                "presence_title": row.get("presence_title") or "いまは静かに待機中のロボ使い",
            }
        )
    return items


def _home_world_timeline_items(db, *, limit=HOME_COMM_PREVIEW_LIMIT, is_admin=False):
    system_items = _world_system_timeline_items(db, limit=limit, is_admin=is_admin)
    items = system_items + _home_world_user_message_items(db, limit=limit)
    items.sort(key=lambda item: (int(item.get("sort_ts") or 0), int(item.get("sort_id") or 0)), reverse=True)
    return items[: int(limit)]


def _world_timeline_items(db, *, limit=COMM_WORLD_TIMELINE_LIMIT, is_admin=False):
    system_items = _world_system_timeline_items(db, limit=limit, is_admin=is_admin)
    items = system_items + _world_user_message_items(db, limit=limit)
    items.sort(key=lambda item: (int(item.get("sort_ts") or 0), int(item.get("sort_id") or 0)), reverse=True)
    return items[: int(limit)]


def _room_message_items(db, room_key, *, limit=COMM_ROOM_TIMELINE_LIMIT):
    room_value = _chat_normalize_room_key(room_key, allow_world=False)
    if not room_value:
        return []
    rows = _decorate_user_rows(db, _chat_room_rows(db, room_value, limit=limit))
    items = []
    for row in rows:
        created_ts = _chat_created_at_ts(row.get("created_at"))
        items.append(
            {
                "id": int(row["id"]),
                "user_id": (int(row["user_id"]) if row.get("user_id") else None),
                "user_label": str(row.get("username") or "").strip() or _feed_user_label(db, row.get("user_id")),
                "message": str(row.get("message") or "").strip(),
                "time_jst": (_format_jst_ts(created_ts) if created_ts else str(row.get("created_at") or "-")),
                "avatar_path": row.get("avatar_path") or DEFAULT_AVATAR_REL,
                "badge_path": row.get("badge_path") or DEFAULT_BADGE_REL,
                "presence_state": row.get("presence_state") or "idle",
                "presence_label": row.get("presence_label") or "探索待機中",
                "presence_title": row.get("presence_title") or "いまは静かに待機中のロボ使い",
            }
        )
    return items


def _personal_ranking_items(db, user_id):
    week_key = _world_week_key()
    start_dt, end_dt = _world_week_bounds(week_key)
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    total_users = int(db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] or 0)
    items = []
    for metric in WORLD_LOG_RANKING_METRICS:
        rows = _ranking_rows_from_event_log(
            db,
            event_type=metric["event_type"],
            limit=max(1, total_users),
            start_ts=start_ts,
            end_ts=end_ts,
        )
        found_rank = None
        found_value = 0
        for rank, row in enumerate(rows, start=1):
            if int(row["id"]) == int(user_id):
                found_rank = rank
                found_value = int(row["metric_value"])
                break
        if found_rank is None:
            continue
        latest_ts = _latest_world_event_ts(
            db,
            event_type=metric["event_type"],
            user_id=user_id,
            start_ts=start_ts,
            end_ts=end_ts,
        )
        items.append(
            {
                "title": "個人ランキング",
                "text": f"今週の{metric['text_label']}で {found_rank}位 に入りました。",
                "accent": "weekly",
                "time_jst": _format_jst_ts(latest_ts),
                "sort_ts": int(latest_ts),
                "sort_id": 950000 + len(items),
                "link_url": url_for("ranking", metric=metric["key"]),
                "meta_lines": [f"記録: {found_value}{metric['value_suffix']}", f"対象週: {week_key}"],
            }
        )
    return items


def _personal_log_items(db, user_id, *, limit=COMM_PERSONAL_LOG_LIMIT):
    event_types = PERSONAL_LOG_EVENT_TYPES
    rows = db.execute(
        f"""
        SELECT id, created_at, event_type, payload_json
        FROM world_events_log
        WHERE user_id = ?
          AND event_type IN ({",".join(["?"] * len(event_types))})
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (int(user_id), *event_types, int(limit) * 5),
    ).fetchall()
    items = []
    for row in rows:
        event_type = str(row["event_type"] or "")
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        created_ts = int(row["created_at"] or 0)
        base = {
            "time_jst": _format_jst_ts(created_ts),
            "sort_ts": created_ts,
            "sort_id": int(row["id"]),
            "link_url": None,
            "meta_lines": [],
            "accent": "default",
        }
        if event_type == AUDIT_EVENT_TYPES["DROP"]:
            part_key = str(payload.get("part_key") or "").strip()
            part_row = _get_part_by_key(db, part_key) if part_key else None
            part_name = _part_display_name_ja(part_row) if part_row else (part_key or "パーツ")
            part_type = payload.get("part_type") or (part_row["part_type"] if part_row else "")
            part_label = PART_TYPE_TITLES_JA.get(_normalize_part_type_key(part_type), "パーツ")
            rarity = str(payload.get("rarity") or "").strip() or "-"
            plus = int(payload.get("plus") or 0)
            item = dict(base)
            item.update(
                {
                    "title": "パーツ入手",
                    "text": f"{part_label}『{part_name}』を回収しました。",
                    "accent": "evolve",
                    "link_url": url_for("parts", tab="instances"),
                    "meta_lines": [f"レア度: {rarity}", f"強化値: +{plus}"],
                }
            )
            items.append(item)
        elif event_type == AUDIT_EVENT_TYPES["FUSE"]:
            part_type = payload.get("part_type") or ""
            part_label = PART_TYPE_TITLES_JA.get(_normalize_part_type_key(part_type), "パーツ")
            from_plus = int(payload.get("from_plus") or 0)
            to_plus = int(payload.get("to_plus") or from_plus)
            success = bool(payload.get("success", True))
            item = dict(base)
            item.update(
                {
                    "title": ("強化成功" if success else "強化記録"),
                    "text": (
                        f"{part_label}を +{from_plus} から +{to_plus} へ強化しました。"
                        if success
                        else f"{part_label}の強化を試しました。"
                    ),
                    "accent": "evolve",
                    "link_url": url_for("parts_strengthen"),
                }
            )
            items.append(item)
        elif event_type == AUDIT_EVENT_TYPES["BUILD_CONFIRM"]:
            robot_name = str(payload.get("robot_name") or "").strip() or "新ロボ"
            item = dict(base)
            item.update(
                {
                    "title": "ロボ完成",
                    "text": f"{robot_name} を完成させました。",
                    "accent": "weekly",
                    "link_url": url_for("robots"),
                }
            )
            items.append(item)
        elif event_type == AUDIT_EVENT_TYPES["BOSS_ENCOUNTER"]:
            boss_name = str(payload.get("enemy_name") or "").strip() or "ボス"
            area_label = str(payload.get("area_label") or "").strip()
            if not area_label and payload.get("area_key"):
                area_label = _boss_area_label(payload.get("area_key"))
            attempts_left = int(payload.get("alert_attempts_left") or 0)
            item = dict(base)
            item.update(
                {
                    "title": "ボス遭遇",
                    "text": (
                        f"{area_label}で {boss_name} を検知しました。"
                        if area_label
                        else f"{boss_name} を検知しました。"
                    ),
                    "accent": "boss",
                    "link_url": url_for("home"),
                }
            )
            if attempts_left > 0:
                item["meta_lines"].append(f"挑戦権: {attempts_left}回")
            items.append(item)
        elif event_type == AUDIT_EVENT_TYPES["BOSS_DEFEAT"]:
            boss_name = str(payload.get("enemy_name") or "").strip() or "ボス"
            area_label = str(payload.get("area_label") or "").strip()
            if not area_label and payload.get("area_key"):
                area_label = _boss_area_label(payload.get("area_key"))
            boss_item = dict(base)
            boss_item.update(
                {
                    "title": "ボス撃破",
                    "text": f"{boss_name} を討伐しました。",
                    "accent": "boss",
                    "link_url": url_for("world_view"),
                }
            )
            if area_label:
                boss_item["meta_lines"].append(f"戦域: {area_label}")
            items.append(boss_item)
            unlocked_layer = int(payload.get("unlocked_layer") or 0)
            if unlocked_layer > 0:
                unlock_item = dict(base)
                unlock_item.update(
                    {
                        "title": "層解放",
                        "text": f"第{unlocked_layer}層が解放されました。",
                        "accent": "weekly",
                        "link_url": url_for("map_view"),
                    }
                )
                items.append(unlock_item)
        elif event_type == AUDIT_EVENT_TYPES["EXPLORE_END"]:
            result = payload.get("result") or {}
            rewards = payload.get("rewards") or {}
            battles = payload.get("battles") or []
            boss = payload.get("boss") or {}
            area_label = _boss_area_label(payload.get("area_key"))
            last_enemy = (battles[-1].get("enemy") if battles else {}) or {}
            enemy_name = str(last_enemy.get("name_ja") or "").strip()
            is_win = bool(result.get("win"))
            is_timeout = bool(result.get("timeout"))
            is_boss = bool(result.get("is_area_boss")) or bool(boss.get("is_area_boss"))
            if is_boss and enemy_name:
                text = (
                    f"{area_label}で {enemy_name} を突破しました。"
                    if is_win
                    else f"{area_label}で {enemy_name} に押し返されました。"
                )
            elif is_win:
                text = f"{area_label} の探索を完了しました。"
            elif is_timeout:
                text = f"{area_label} の探索は時間切れで終了しました。"
            else:
                text = f"{area_label} の探索で撤退しました。"
            item = dict(base)
            item.update(
                {
                    "title": ("探索勝利" if is_win else "探索記録"),
                    "text": text,
                    "accent": ("boss" if is_boss else "default"),
                    "link_url": url_for("explore"),
                }
            )
            battle_count = int(result.get("battle_count") or len(battles) or 0)
            if battle_count > 0:
                item["meta_lines"].append(f"戦闘数: {battle_count}")
            reward_parts = len(rewards.get("drops") or [])
            reward_cores = int(rewards.get("cores") or 0)
            reward_coins = int(rewards.get("coins") or 0)
            reward_bits = []
            if reward_parts > 0:
                reward_bits.append(f"パーツ {reward_parts}件")
            if reward_cores > 0:
                reward_bits.append(f"進化コア {reward_cores}個")
            if reward_coins > 0:
                reward_bits.append(f"コイン {reward_coins}")
            if reward_bits:
                item["meta_lines"].append("報酬: " + " / ".join(reward_bits))
            items.append(item)
        elif event_type == AUDIT_EVENT_TYPES["PART_EVOLVE"]:
            target_part_key = str(payload.get("target_part_key") or "").strip()
            part_row = _get_part_by_key(db, target_part_key) if target_part_key else None
            target_name = str(payload.get("target_part_name") or "").strip()
            if not target_name and part_row:
                target_name = _part_display_name_ja(part_row)
            part_type = payload.get("part_type") or (part_row["part_type"] if part_row else "")
            part_label = PART_TYPE_TITLES_JA.get(_normalize_part_type_key(part_type), "パーツ")
            item = dict(base)
            item.update(
                {
                    "title": "進化成功",
                    "text": f"{part_label}『{target_name or 'Rパーツ'}』を進化させました。",
                    "accent": "evolve",
                    "link_url": url_for("evolve_parts"),
                    "meta_lines": [f"部位: {part_label}"],
                }
            )
            items.append(item)
        elif event_type == AUDIT_EVENT_TYPES["REFERRAL_QUALIFIED"]:
            item = dict(base)
            item.update(
                {
                    "title": "招待条件達成",
                    "text": "招待条件を達成し、紹介進行が更新されました。",
                    "accent": "weekly",
                    "link_url": url_for("home"),
                }
            )
            items.append(item)
        elif event_type == AUDIT_EVENT_TYPES["CORE_GUARANTEE"]:
            qty = int(payload.get("quantity") or 0)
            item = dict(base)
            item.update(
                {
                    "title": "進化コア保証到達",
                    "text": f"保証で進化コアを{max(1, qty)}個獲得しました。",
                    "accent": "weekly",
                    "link_url": url_for("evolve_parts"),
                }
            )
            target = int(payload.get("target") or EVOLUTION_CORE_PROGRESS_TARGET)
            progress_after_reset = int(payload.get("progress_after_reset") or 0)
            item["meta_lines"] = [f"保証ライン: {int(target)}勝", f"次の進捗: {int(progress_after_reset)}/{int(target)}"]
            items.append(item)
    items.extend(_personal_ranking_items(db, user_id))
    items.sort(key=lambda item: (int(item.get("sort_ts") or 0), int(item.get("sort_id") or 0)), reverse=True)
    return items[: int(limit)]


def _fetch_feed_cards(db, type_filter="", user_id_filter=None, limit=30, is_admin=False):
    feed_type = (type_filter or "").strip().lower()
    event_types = set()
    if feed_type in FEED_EVENT_TYPES:
        if feed_type == "weekly":
            event_types = set(FEED_WEEKLY_PUBLIC_EVENTS)
            if is_admin:
                event_types.update(FEED_WEEKLY_ADMIN_EVENTS)
        else:
            event_types = set(FEED_EVENT_TYPES[feed_type])
    else:
        event_types.update(FEED_EVENT_TYPES["boss"])
        event_types.update(FEED_EVENT_TYPES["evolve"])
        event_types.update(FEED_EVENT_TYPES["drop"])
        event_types.update(FEED_EVENT_TYPES["fuse"])
        event_types.update(FEED_EVENT_TYPES["build"])
        event_types.update(FEED_WEEKLY_PUBLIC_EVENTS)
        if is_admin:
            event_types.update(FEED_WEEKLY_ADMIN_EVENTS)
    where = ["event_type IN (" + ",".join(["?"] * len(event_types)) + ")"]
    params = list(event_types)
    where.append("event_type != 'balance.simulation'")
    if user_id_filter is not None:
        where.append("user_id = ?")
        params.append(int(user_id_filter))
    params.append(max(int(limit) * 4, int(limit)))
    rows = db.execute(
        f"""
        SELECT id, created_at, event_type, payload_json, user_id, action_key, entity_type, entity_id
        FROM world_events_log
        WHERE {' AND '.join(where)}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    cards = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        if not _event_visible_for_viewer(db, row["event_type"], payload, is_admin=is_admin):
            continue
        cards.append(_feed_card_from_event(db, row))
        if len(cards) >= int(limit):
            break
    return cards


def _get_decor_asset_by_id(db, decor_asset_id):
    if not decor_asset_id:
        return None
    return db.execute("SELECT * FROM robot_decor_assets WHERE id = ?", (decor_asset_id,)).fetchone()


def _decor_image_rel(image_path, decor_key=None):
    rel = (image_path or "").strip()
    if rel:
        hit = _safe_static_rel(rel, warn_key=("decor:" + (decor_key or rel)))
        if hit:
            return hit
    key = (decor_key or "").strip()
    if key:
        candidates = [f"decor/{key}.png"]
        if key.startswith("boss_emblem_"):
            candidates.append(f"decor/{key.replace('boss_emblem_', '', 1)}.png")
        for candidate in candidates:
            if os.path.exists(_static_abs(candidate)):
                return candidate
    return DECOR_PLACEHOLDER_REL


def _decor_layer_or_none(decor_row):
    if not decor_row:
        return None
    return {
        "path": _static_abs(_decor_image_rel(decor_row["image_path"], decor_row["key"] if "key" in decor_row.keys() else None)),
        "x": 0,
        "y": 0,
        "is_decor": True,
    }


def _is_admin_user(user_id):
    db = get_db()
    row = db.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,)).fetchone()
    return bool(row and row["is_admin"] == 1)


def _normalize_main_admin_username(username):
    text = str(username or "").strip()
    if not text:
        return ""
    if text == MAIN_ADMIN_USERNAME:
        return MAIN_ADMIN_USERNAME
    if text.lower() == "admin":
        return MAIN_ADMIN_USERNAME
    return text


def _is_main_admin_username(username):
    text = str(username or "").strip()
    if not text:
        return False
    return text == MAIN_ADMIN_USERNAME or text.lower() == "admin"


def _display_username(username, *, is_admin=False):
    text = str(username or "").strip()
    if not text:
        return ""
    if bool(is_admin) and _is_main_admin_username(text):
        return MAIN_ADMIN_USERNAME
    return text


def _is_main_admin_user_row(user_row):
    if not user_row or not hasattr(user_row, "keys"):
        return False
    username = user_row["username"] if "username" in user_row.keys() else None
    return _is_main_admin_username(username)


def _is_main_admin_user_id(db, user_id):
    row = db.execute("SELECT username, is_admin FROM users WHERE id = ?", (int(user_id),)).fetchone()
    return _is_main_admin_user_row(row)


def _find_user_for_login(db, username):
    text = str(username or "").strip()
    if not text:
        return None
    if _is_main_admin_username(text):
        return db.execute(
            """
            SELECT *
            FROM users
            WHERE username IN (?, ?)
            ORDER BY CASE WHEN username = ? THEN 0 ELSE 1 END, id ASC
            LIMIT 1
            """,
            (MAIN_ADMIN_USERNAME, "admin", MAIN_ADMIN_USERNAME),
        ).fetchone()
    return db.execute("SELECT * FROM users WHERE username = ?", (text,)).fetchone()


def _ensure_main_admin_fire_part_rows(db):
    now = int(time.time())
    rows = [
        ("HEAD", "head_r_fire", "parts/head/head_r_fire.png"),
        ("RIGHT_ARM", "right_arm_r_fire", "parts/right_arm/right_arm_r_fire.png"),
        ("LEFT_ARM", "left_arm_r_fire", "parts/left_arm/left_arm_r_fire.png"),
        ("LEGS", "legs_r_fire", "parts/legs/legs_r_fire.png"),
    ]
    changed = 0
    for part_type, key, image_path in rows:
        display_name = generate_part_display_name_ja(key, rarity="R", element="FIRE", part_type=part_type)
        existing = db.execute(
            """
            SELECT part_type, image_path, rarity, element, series, display_name_ja, is_active
            FROM robot_parts
            WHERE key = ?
            LIMIT 1
            """,
            (key,),
        ).fetchone()
        if existing:
            current = (
                str(existing["part_type"] or ""),
                str(existing["image_path"] or ""),
                str(existing["rarity"] or "").upper(),
                str(existing["element"] or "").upper(),
                str(existing["series"] or ""),
                str(existing["display_name_ja"] or ""),
                int(existing["is_active"] or 0),
            )
            target = (part_type, image_path, "R", "FIRE", "S1", display_name, 1)
            if current == target:
                continue
            db.execute(
                """
                UPDATE robot_parts
                SET part_type = ?,
                    image_path = ?,
                    rarity = 'R',
                    element = 'FIRE',
                    series = 'S1',
                    display_name_ja = ?,
                    is_active = 1
                WHERE key = ?
                """,
                (part_type, image_path, display_name, key),
            )
        else:
            db.execute(
                """
                INSERT INTO robot_parts
                (part_type, key, image_path, rarity, element, series, display_name_ja, offset_x, offset_y, is_active, is_unlocked, created_at)
                VALUES (?, ?, ?, 'R', 'FIRE', 'S1', ?, 0, 0, 1, 0, ?)
                """,
                (part_type, key, image_path, display_name, now),
            )
        changed += 1
    return changed


def _grant_all_robot_parts_to_user(db, user_id):
    owned_keys = {
        str(row["key"])
        for row in db.execute(
            """
            SELECT DISTINCT rp.key
            FROM part_instances pi
            JOIN robot_parts rp ON rp.id = pi.part_id
            WHERE pi.user_id = ?
            """,
            (int(user_id),),
        ).fetchall()
    }
    granted = 0
    rows = db.execute(
        """
        SELECT *
        FROM robot_parts
        WHERE is_active = 1
        ORDER BY id ASC
        """
    ).fetchall()
    for row in rows:
        key = str(row["key"] or "").strip()
        if not key or key in owned_keys:
            continue
        _create_part_instance_from_master(db, int(user_id), row, plus=0)
        owned_keys.add(key)
        granted += 1
    return granted


def _select_owned_part_instance_id(db, user_id, part_key):
    row = db.execute(
        """
        SELECT pi.id
        FROM part_instances pi
        JOIN robot_parts rp ON rp.id = pi.part_id
        WHERE pi.user_id = ? AND rp.key = ?
        ORDER BY CASE WHEN pi.status = 'inventory' THEN 0 ELSE 1 END, pi.plus DESC, pi.id ASC
        LIMIT 1
        """,
        (int(user_id), str(part_key)),
    ).fetchone()
    return int(row["id"]) if row else None


def _equip_main_admin_fire_loadout(db, user_id, robot_id):
    parts = db.execute(
        "SELECT * FROM robot_instance_parts WHERE robot_instance_id = ?",
        (int(robot_id),),
    ).fetchone()
    if not parts:
        return False
    desired_keys = {
        "head_key": MAIN_ADMIN_FIRE_LOADOUT["head"],
        "r_arm_key": MAIN_ADMIN_FIRE_LOADOUT["r_arm"],
        "l_arm_key": MAIN_ADMIN_FIRE_LOADOUT["l_arm"],
        "legs_key": MAIN_ADMIN_FIRE_LOADOUT["legs"],
    }
    current_keys = {
        "head_key": str(parts["head_key"] or "").strip(),
        "r_arm_key": str(parts["r_arm_key"] or "").strip(),
        "l_arm_key": str(parts["l_arm_key"] or "").strip(),
        "legs_key": str(parts["legs_key"] or "").strip(),
    }
    if current_keys == desired_keys:
        return False
    current_ids = [
        int(parts[col])
        for col in ("head_part_instance_id", "r_arm_part_instance_id", "l_arm_part_instance_id", "legs_part_instance_id")
        if col in parts.keys() and parts[col]
    ]
    if current_ids:
        user_row = db.execute("SELECT id, part_inventory_limit FROM users WHERE id = ?", (int(user_id),)).fetchone()
        for part_instance_id in current_ids:
            _return_part_instance_to_pool(db, int(user_id), int(part_instance_id), user_row=user_row)
    selected = {
        "head": _select_owned_part_instance_id(db, user_id, MAIN_ADMIN_FIRE_LOADOUT["head"]),
        "r_arm": _select_owned_part_instance_id(db, user_id, MAIN_ADMIN_FIRE_LOADOUT["r_arm"]),
        "l_arm": _select_owned_part_instance_id(db, user_id, MAIN_ADMIN_FIRE_LOADOUT["l_arm"]),
        "legs": _select_owned_part_instance_id(db, user_id, MAIN_ADMIN_FIRE_LOADOUT["legs"]),
    }
    if not all(selected.values()):
        return False
    db.execute(
        """
        UPDATE robot_instance_parts
        SET head_key = ?,
            r_arm_key = ?,
            l_arm_key = ?,
            legs_key = ?
        WHERE robot_instance_id = ?
        """,
        (
            desired_keys["head_key"],
            desired_keys["r_arm_key"],
            desired_keys["l_arm_key"],
            desired_keys["legs_key"],
            int(robot_id),
        ),
    )
    _equip_part_instances_on_robot(db, int(robot_id), selected)
    _compose_instance_assets_no_commit(
        db,
        int(robot_id),
        {
            "head_key": desired_keys["head_key"],
            "r_arm_key": desired_keys["r_arm_key"],
            "l_arm_key": desired_keys["l_arm_key"],
            "legs_key": desired_keys["legs_key"],
            "decor_asset_id": (parts["decor_asset_id"] if "decor_asset_id" in parts.keys() else None),
        },
    )
    return True


def _apply_main_admin_account_state(db, user_id):
    user = db.execute(
        """
        SELECT id, username, is_admin, is_admin_protected, layer2_unlocked, max_unlocked_layer, active_robot_id
        FROM users
        WHERE id = ?
        """,
        (int(user_id),),
    ).fetchone()
    if not _is_main_admin_user_row(user):
        return {"changed": False, "granted_parts": 0, "equipped_fire_loadout": False}

    changed = False
    granted_parts = 0
    equipped_fire_loadout = False
    normalized_username = _normalize_main_admin_username(user["username"])
    next_max_layer = max(int(user["max_unlocked_layer"] or 1), MAX_UNLOCKABLE_LAYER)
    if (
        str(user["username"] or "") != normalized_username
        or int(user["is_admin"] or 0) != 1
        or int(user["is_admin_protected"] or 0) != 1
        or int(user["layer2_unlocked"] or 0) != 1
        or int(user["max_unlocked_layer"] or 1) != next_max_layer
    ):
        db.execute(
            """
            UPDATE users
            SET username = ?,
                is_admin = 1,
                is_admin_protected = 1,
                layer2_unlocked = 1,
                max_unlocked_layer = ?
            WHERE id = ?
            """,
            (normalized_username, int(next_max_layer), int(user_id)),
        )
        changed = True

    active_robot = db.execute(
        """
        SELECT *
        FROM robot_instances
        WHERE user_id = ? AND status = 'active'
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (int(user_id),),
    ).fetchone()
    if active_robot is None:
        init_result = initialize_new_user(db, int(user_id), apply_admin_setup=False)
        changed = changed or bool(init_result.get("created_robot")) or bool(init_result.get("created_inventory_set"))
        active_robot = db.execute(
            """
            SELECT *
            FROM robot_instances
            WHERE user_id = ? AND status = 'active'
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (int(user_id),),
        ).fetchone()

    part_rows_changed = _ensure_main_admin_fire_part_rows(db)
    changed = changed or bool(part_rows_changed)
    granted_parts = _grant_all_robot_parts_to_user(db, int(user_id))
    changed = changed or (granted_parts > 0)

    if active_robot and (part_rows_changed or granted_parts > 0):
        equipped_fire_loadout = _equip_main_admin_fire_loadout(db, int(user_id), int(active_robot["id"]))
        changed = changed or bool(equipped_fire_loadout)
        db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (int(active_robot["id"]), int(user_id)))

    _ensure_qol_entitlement(db, int(user_id))
    return {
        "changed": bool(changed),
        "granted_parts": int(granted_parts),
        "equipped_fire_loadout": bool(equipped_fire_loadout),
    }


def _ensure_main_admin_account_ready(db):
    display_row = db.execute(
        "SELECT id, username, is_admin, is_admin_protected FROM users WHERE username = ? LIMIT 1",
        (MAIN_ADMIN_USERNAME,),
    ).fetchone()
    legacy_row = db.execute(
        "SELECT id, username, is_admin, is_admin_protected FROM users WHERE username = ? LIMIT 1",
        ("admin",),
    ).fetchone()
    target = display_row or legacy_row
    if not target:
        return None
    result = _apply_main_admin_account_state(db, int(target["id"]))
    if result.get("changed"):
        db.commit()
    return result


def _is_newbie_boost_active(user_row, now_ts=None):
    if not NEWBIE_BOOST_ENABLED or not user_row:
        return False
    created_at = int(user_row["created_at"] or 0) if "created_at" in user_row.keys() else 0
    if created_at <= 0:
        return False
    now = _now_ts() if now_ts is None else int(now_ts)
    return (now - created_at) < (NEWBIE_BOOST_WINDOW_HOURS * 3600)


def _explore_ct_seconds_for_user(user_row, now_ts=None):
    if user_row and int(user_row["is_admin"] or 0) == 1:
        return 0
    ct_candidates = [int(EXPLORE_COOLDOWN_SECONDS)]
    if _is_newbie_boost_active(user_row, now_ts=now_ts):
        ct_candidates.append(int(NEWBIE_EXPLORE_CT_SECONDS))
    if _is_paid_explore_boost_active(user_row, now_ts=now_ts):
        ct_candidates.append(int(EXPLORE_BOOST_CT_SECONDS))
    return min(ct_candidates)


def _remaining_cooldown_seconds(user_row, last_action_at, now_ts=None):
    if user_row and int(user_row["is_admin"] or 0) == 1:
        return 0
    now = _now_ts() if now_ts is None else int(now_ts)
    last_ts = int(last_action_at or 0)
    elapsed = max(0, now - last_ts)
    ct_seconds = int(_explore_ct_seconds_for_user(user_row, now_ts=now))
    return max(0, ct_seconds - elapsed)


def _explore_last_action_at(db, user_id):
    row = db.execute(
        "SELECT last_action_at FROM battle_state WHERE user_id = ? LIMIT 1",
        (int(user_id),),
    ).fetchone()
    return int((row["last_action_at"] if row else 0) or 0)


def _explore_remaining_seconds_for_user(db, user_row, user_id, now_ts=None):
    last_action_at = _explore_last_action_at(db, user_id)
    remain = _remaining_cooldown_seconds(user_row, last_action_at, now_ts=now_ts)
    return int(remain), int(last_action_at)


def _enforce_explore_cooldown_or_wait(db, user_row, user_id, now_ts=None):
    remain, _ = _explore_remaining_seconds_for_user(db, user_row, user_id, now_ts=now_ts)
    return int(remain)


def _touch_explore_cooldown(db, user_id, now_ts):
    now = int(now_ts)
    db.execute(
        """
        INSERT INTO battle_state (user_id, enemy_name, enemy_hp, last_action_at, active)
        VALUES (?, '', 0, ?, 0)
        ON CONFLICT(user_id) DO UPDATE SET
            enemy_name = '',
            enemy_hp = 0,
            last_action_at = excluded.last_action_at,
            active = 0
        """,
        (int(user_id), now),
    )


def _newbie_boost_hours_left(user_row, now_ts=None):
    if not _is_newbie_boost_active(user_row, now_ts=now_ts):
        return 0
    created_at = int(user_row["created_at"] or 0)
    now = _now_ts() if now_ts is None else int(now_ts)
    remain_sec = max(0, (NEWBIE_BOOST_WINDOW_HOURS * 3600) - (now - created_at))
    return int(math.ceil(remain_sec / 3600.0))


def _ensure_test_user(db):
    row = db.execute(
        "SELECT id, username, is_admin, is_admin_protected FROM users WHERE username = ?",
        ("test_user",),
    ).fetchone()
    if row:
        if int(row["is_admin"] or 0) != 1 or int(row["is_admin_protected"] or 0) != 1:
            db.execute("UPDATE users SET is_admin = 1, is_admin_protected = 1 WHERE id = ?", (row["id"],))
            db.commit()
        _ensure_qol_entitlement(db, row["id"])
        return db.execute("SELECT id, username, is_admin FROM users WHERE id = ?", (row["id"],)).fetchone()
    now = int(time.time())
    cur = db.execute(
        """
        INSERT INTO users (username, password_hash, coins, created_at, is_admin, is_admin_protected)
        VALUES (?, ?, ?, ?, 1, 1)
        """,
        ("test_user", generate_password_hash("test_user"), 0, now),
    )
    user_id = cur.lastrowid
    initialize_new_user(db, user_id)
    _ensure_qol_entitlement(db, user_id)
    db.commit()
    return db.execute("SELECT id, username, is_admin FROM users WHERE id = ?", (user_id,)).fetchone()


def _seed_test_robots_random(db, user_id, count):
    rows = db.execute(
        """
        SELECT id, key, part_type, rarity, element, series
        FROM robot_parts
        WHERE is_active = 1
        ORDER BY id ASC
        """
    ).fetchall()
    by_type = {"HEAD": [], "RIGHT_ARM": [], "LEFT_ARM": [], "LEGS": []}
    for r in rows:
        pt = _norm_part_type(r["part_type"])
        if pt in by_type:
            by_type[pt].append(r)
    if any(len(by_type[k]) == 0 for k in by_type):
        raise ValueError("有効なパーツが不足しています。")

    created_ids = []
    now = int(time.time())
    for i in range(int(count)):
        head = random.choice(by_type["HEAD"])
        r_arm = random.choice(by_type["RIGHT_ARM"])
        l_arm = random.choice(by_type["LEFT_ARM"])
        legs = random.choice(by_type["LEGS"])
        name = f"TestBot-{now}-{i+1:03d}"
        cur = db.execute(
            """
            INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
            VALUES (?, ?, 'active', ?, ?)
            """,
            (user_id, name, now, now),
        )
        robot_id = cur.lastrowid

        def roll_plus():
            x = random.random()
            if x < 0.84:
                return 0
            if x < 0.97:
                return 1
            return 2

        head_pi = _create_part_instance_from_master(db, user_id, head, plus=roll_plus())
        r_arm_pi = _create_part_instance_from_master(db, user_id, r_arm, plus=roll_plus())
        l_arm_pi = _create_part_instance_from_master(db, user_id, l_arm, plus=roll_plus())
        legs_pi = _create_part_instance_from_master(db, user_id, legs, plus=roll_plus())
        for pi_id in (head_pi, r_arm_pi, l_arm_pi, legs_pi):
            db.execute("UPDATE part_instances SET status = 'equipped' WHERE id = ?", (pi_id,))
        db.execute(
            """
            INSERT INTO robot_instance_parts
            (robot_instance_id, head_key, r_arm_key, l_arm_key, legs_key, head_part_instance_id, r_arm_part_instance_id, l_arm_part_instance_id, legs_part_instance_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (robot_id, head["key"], r_arm["key"], l_arm["key"], legs["key"], head_pi, r_arm_pi, l_arm_pi, legs_pi),
        )
        created_ids.append(robot_id)
    db.commit()

    powers = []
    for robot_id in created_ids:
        calc = _compute_robot_stats_for_instance(db, robot_id)
        if calc:
            powers.append(int(calc["power"]))
    if not powers:
        return {
            "created": len(created_ids),
            "power_min": None,
            "power_avg": None,
            "power_max": None,
            "top10": [],
        }
    powers_sorted = sorted(powers)
    return {
        "created": len(created_ids),
        "power_min": powers_sorted[0],
        "power_avg": sum(powers_sorted) / len(powers_sorted),
        "power_max": powers_sorted[-1],
        "top10": sorted(powers_sorted, reverse=True)[:10],
    }


def _part_purge_counts(db, part_key):
    if not part_key:
        return {
            "inventory": 0,
            "instances": 0,
            "builds": 0,
            "milestones": 0,
            "legacy_user_robots": 0,
        }
    return {
        "part_instances": db.execute(
            """
            SELECT COUNT(*) AS c
            FROM part_instances pi
            JOIN robot_parts rp ON rp.id = pi.part_id
            WHERE rp.key = ?
            """,
            (part_key,),
        ).fetchone()["c"],
        "inventory": db.execute(
            "SELECT COUNT(*) AS c FROM user_parts_inventory WHERE part_key = ?",
            (part_key,),
        ).fetchone()["c"],
        "instances": db.execute(
            """
            SELECT COUNT(*) AS c FROM robot_instance_parts
            WHERE head_key = ? OR r_arm_key = ? OR l_arm_key = ? OR legs_key = ?
            """,
            (part_key, part_key, part_key, part_key),
        ).fetchone()["c"],
        "builds": db.execute(
            """
            SELECT COUNT(*) AS c FROM robot_builds
            WHERE head_key = ? OR r_arm_key = ? OR l_arm_key = ? OR legs_key = ?
            """,
            (part_key, part_key, part_key, part_key),
        ).fetchone()["c"],
        "milestones": db.execute(
            """
            SELECT COUNT(*) AS c FROM robot_milestones
            WHERE reward_head_key = ? OR reward_r_arm_key = ? OR reward_l_arm_key = ? OR reward_legs_key = ?
            """,
            (part_key, part_key, part_key, part_key),
        ).fetchone()["c"],
        "legacy_user_robots": db.execute(
            """
            SELECT COUNT(*) AS c FROM user_robots
            WHERE head = ? OR right_arm = ? OR left_arm = ? OR legs = ?
            """,
            (part_key, part_key, part_key, part_key),
        ).fetchone()["c"],
    }


def _purge_part_with_dependencies(db, part):
    part_key = part["key"]
    db.execute("BEGIN IMMEDIATE")

    part_instances_deleted = db.execute(
        "DELETE FROM part_instances WHERE part_id = ?",
        (part["id"],),
    ).rowcount

    inv_deleted = db.execute(
        "DELETE FROM user_parts_inventory WHERE part_key = ?",
        (part_key,),
    ).rowcount

    instance_rows = db.execute(
        """
        SELECT ri.id, ri.composed_image_path, ri.icon_32_path
        FROM robot_instances ri
        JOIN robot_instance_parts rip ON rip.robot_instance_id = ri.id
        WHERE rip.head_key = ? OR rip.r_arm_key = ? OR rip.l_arm_key = ? OR rip.legs_key = ?
        """,
        (part_key, part_key, part_key, part_key),
    ).fetchall()
    instance_ids = [r["id"] for r in instance_rows]
    composed_paths = [r["composed_image_path"] for r in instance_rows if r["composed_image_path"]]
    icon_paths = [r["icon_32_path"] for r in instance_rows if r["icon_32_path"]]
    if instance_ids:
        placeholders = ",".join(["?"] * len(instance_ids))
        db.execute(
            f"UPDATE users SET active_robot_id = NULL WHERE active_robot_id IN ({placeholders})",
            instance_ids,
        )
        db.execute(
            f"DELETE FROM user_showcase WHERE robot_instance_id IN ({placeholders})",
            instance_ids,
        )
        db.execute(
            f"DELETE FROM user_milestone_claims WHERE robot_instance_id IN ({placeholders})",
            instance_ids,
        )
        db.execute(
            f"DELETE FROM robot_instance_parts WHERE robot_instance_id IN ({placeholders})",
            instance_ids,
        )
        db.execute(
            f"DELETE FROM robot_instances WHERE id IN ({placeholders})",
            instance_ids,
        )

    build_rows = db.execute(
        """
        SELECT id, composed_image_path FROM robot_builds
        WHERE head_key = ? OR r_arm_key = ? OR l_arm_key = ? OR legs_key = ?
        """,
        (part_key, part_key, part_key, part_key),
    ).fetchall()
    build_paths = [r["composed_image_path"] for r in build_rows if r["composed_image_path"]]
    build_deleted = db.execute(
        """
        DELETE FROM robot_builds
        WHERE head_key = ? OR r_arm_key = ? OR l_arm_key = ? OR legs_key = ?
        """,
        (part_key, part_key, part_key, part_key),
    ).rowcount

    milestone_deleted = db.execute(
        """
        DELETE FROM robot_milestones
        WHERE reward_head_key = ? OR reward_r_arm_key = ? OR reward_l_arm_key = ? OR reward_legs_key = ?
        """,
        (part_key, part_key, part_key, part_key),
    ).rowcount

    legacy_deleted = db.execute(
        """
        DELETE FROM user_robots
        WHERE head = ? OR right_arm = ? OR left_arm = ? OR legs = ?
        """,
        (part_key, part_key, part_key, part_key),
    ).rowcount

    part_image_path = part["image_path"]
    part_deleted = db.execute("DELETE FROM robot_parts WHERE id = ?", (part["id"],)).rowcount
    db.commit()

    # best-effort file cleanup
    for rel in composed_paths + icon_paths + build_paths:
        if not rel:
            continue
        abs_path = _static_abs(rel)
        if os.path.exists(abs_path):
            try:
                os.remove(abs_path)
            except OSError:
                pass
    if part_image_path:
        remain = db.execute("SELECT COUNT(*) AS c FROM robot_parts WHERE image_path = ?", (part_image_path,)).fetchone()["c"]
        if remain == 0:
            part_abs = _asset_abs(part_image_path)
            if os.path.exists(part_abs):
                try:
                    os.remove(part_abs)
                except OSError:
                    pass

    return {
        "part_instances": part_instances_deleted,
        "inventory": inv_deleted,
        "instances": len(instance_ids),
        "builds": build_deleted,
        "milestones": milestone_deleted,
        "legacy_user_robots": legacy_deleted,
        "part": part_deleted,
    }


def compose_robot(head_layer, r_arm_layer, l_arm_layer, legs_layer, out_path, decor_layer=None):
    _ensure_dirs()
    base = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    # Fixed composition order for Medarot-style 4-part rendering.
    layers = [legs_layer, head_layer, r_arm_layer, l_arm_layer]
    if decor_layer:
        layers.append(decor_layer)
    for layer in layers:
        image_path = layer["path"]
        if not image_path or not os.path.exists(image_path):
            _warn_missing_asset_once(f"compose:{image_path}", detail="compose_robot_layer")
            image_path = _static_abs("enemies/_placeholder.png")
        img = Image.open(image_path).convert("RGBA")
        canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
        if bool(layer.get("is_decor")):
            # DECOR is rendered as a small badge to avoid covering the robot body.
            badge_size = 28
            badge_margin = 6
            if img.size != (badge_size, badge_size):
                resample_lanczos = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)
                img = img.resize((badge_size, badge_size), resample_lanczos)
            decor_x = int(layer.get("x", 0)) + badge_margin
            decor_y = int(layer.get("y", 0)) + badge_margin
            canvas.paste(img, (decor_x, decor_y), img)
        else:
            if img.size != (CANVAS_SIZE, CANVAS_SIZE):
                raise ValueError("size mismatch")
            canvas.paste(img, (layer["x"], layer["y"]), img)
        base = Image.alpha_composite(base, canvas)
    base.save(out_path, format="PNG")
    return out_path


def _compose_build_image(db, build_id, head_key, r_arm_key, l_arm_key, legs_key, offsets=None):
    head = _get_part_by_key(db, head_key)
    r_arm = _get_part_by_key(db, r_arm_key)
    l_arm = _get_part_by_key(db, l_arm_key)
    legs = _get_part_by_key(db, legs_key)
    if not all([head, r_arm, l_arm, legs]):
        return None
    rel_path = f"robot_composed/build_{build_id}.png"
    out_path = os.path.join(BASE_DIR, "static", rel_path)
    offsets = offsets or {}
    compose_robot(
        {
            "path": _asset_abs(head["image_path"]),
            "x": head["offset_x"] + offsets.get("head_offset_x", 0),
            "y": head["offset_y"] + offsets.get("head_offset_y", 0),
        },
        {
            "path": _asset_abs(r_arm["image_path"]),
            "x": r_arm["offset_x"] + offsets.get("r_arm_offset_x", 0),
            "y": r_arm["offset_y"] + offsets.get("r_arm_offset_y", 0),
        },
        {
            "path": _asset_abs(l_arm["image_path"]),
            "x": l_arm["offset_x"] + offsets.get("l_arm_offset_x", 0),
            "y": l_arm["offset_y"] + offsets.get("l_arm_offset_y", 0),
        },
        {
            "path": _asset_abs(legs["image_path"]),
            "x": legs["offset_x"] + offsets.get("legs_offset_x", 0),
            "y": legs["offset_y"] + offsets.get("legs_offset_y", 0),
        },
        out_path,
        None,
    )
    db.execute(
        "UPDATE robot_builds SET composed_image_path = ? WHERE id = ?",
        (rel_path, build_id),
    )
    db.commit()
    return rel_path


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            if DEV_MODE:
                app.logger.debug(
                    "auth redirect path=%s cookies=%s session_keys=%s",
                    request.path,
                    dict(request.cookies),
                    list(session.keys()),
                )
            return redirect(url_for("login", next=request.path, reason="expired"))
        return fn(*args, **kwargs)

    return wrapper


@app.context_processor
def inject_user_display():
    user_id = session.get("user_id")
    if not user_id:
        return {"header_user_visual": None}
    db = get_db()
    user = db.execute("SELECT id, avatar_path FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return {"header_user_visual": None}
    return {
        "header_user_visual": {
            "avatar_path": _user_avatar_rel(user),
            "badge_path": _user_badge_rel(db, user_id),
        }
    }


@app.context_processor
def inject_safe_mode():
    return {"safe_mode": bool(session.get("safe_mode", False))}


def _ui_effects_enabled():
    override = session.get("ui_effects_enabled")
    if override is None:
        return bool(UI_EFFECTS_ENABLED)
    return bool(override)


@app.context_processor
def inject_ui_effects():
    return {"ui_effects_enabled": _ui_effects_enabled()}


@app.context_processor
def inject_app_meta():
    return {
        "app_version": APP_VERSION,
        "support_email": SUPPORT_EMAIL,
        "legal_operator_name": LEGAL_OPERATOR_NAME,
        "legal_brand_name": LEGAL_BRAND_NAME,
        "legal_disclosure_policy": LEGAL_DISCLOSURE_POLICY,
        "stat_ui_labels": STAT_UI_LABELS,
    }


@app.before_request
def apply_safe_mode():
    if "safe" in request.args:
        session["safe_mode"] = request.args.get("safe") == "1"


@app.before_request
def assign_request_id():
    g.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())


@app.before_request
def enforce_banned_user_logout():
    if request.endpoint == "static" or request.path.startswith("/static/"):
        return None
    user_id = session.get("user_id")
    if not user_id:
        return None
    db = get_db()
    row = db.execute(
        "SELECT id, username, is_admin, is_banned FROM users WHERE id = ?",
        (int(user_id),),
    ).fetchone()
    if not row:
        session.clear()
        return redirect(url_for("login", reason="expired"))
    username = _display_username(row["username"], is_admin=bool(int(row["is_admin"] or 0)))
    if username and session.get("username") != username:
        session["username"] = username
    if int(row["is_banned"] or 0) != 1:
        return None
    session.clear()
    flash("このアカウントは利用停止されています。", "error")
    return redirect(url_for("login"))


@app.before_request
def touch_user_last_seen():
    if request.endpoint == "static" or request.path.startswith("/static/"):
        return None
    user_id = session.get("user_id")
    if not user_id:
        return None
    now = _now_ts()
    try:
        db = get_db()
        row = db.execute("SELECT last_seen_at FROM users WHERE id = ?", (int(user_id),)).fetchone()
        last_seen_at = int((row["last_seen_at"] if row else 0) or 0)
        if now - last_seen_at < int(LAST_SEEN_TOUCH_INTERVAL_SECONDS):
            return None
        db.execute("UPDATE users SET last_seen_at = ? WHERE id = ?", (now, int(user_id)))
        db.commit()
    except Exception:
        app.logger.exception("user.last_seen_touch_failed user_id=%s", user_id)
    return None


@app.before_request
def enforce_release_gates():
    if request.endpoint == "static" or request.path.startswith("/static/"):
        return None
    if not request.path.startswith("/lab"):
        return None
    user_id = session.get("user_id")
    if not user_id:
        return None
    db = get_db()
    user = db.execute("SELECT id, is_admin FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if not user:
        return None
    return _release_gate_redirect(db, "lab", user_row=user)


@app.before_request
def auto_close_faction_war_weekly():
    if request.endpoint in {"static"}:
        return None
    try:
        db = get_db()
        _ensure_faction_war_auto_close(db, _world_week_key())
    except Exception:
        # Auto-close is best effort and must not block gameplay.
        app.logger.exception("faction_war.auto_close_failed")
    return None


@app.before_request
def block_maintenance_posts():
    if request.method != "POST":
        return None
    if not _is_maintenance_mode():
        return None
    blocked = {"explore", "parts_strengthen", "parts_fuse", "build", "build_confirm"}
    if request.endpoint not in blocked:
        return None
    db = get_db()
    user_id = session.get("user_id")
    audit_log(
        db,
        AUDIT_EVENT_TYPES["SYSTEM_MAINTENANCE_BLOCK"],
        user_id=user_id,
        request_id=getattr(g, "request_id", None),
        action_key=(request.endpoint or "unknown"),
        payload={"path": request.path, "method": request.method, "maintenance_mode": True},
        ip=request.remote_addr,
    )
    db.commit()
    return render_template("maintenance.html"), 503


@app.after_request
def add_security_headers(response):
    is_admin_path = request.path.startswith("/admin/")
    # Temporary: /build preview still relies on inline style/CSS variable updates.
    # Once build preview stops mutating styles directly, remove this exception and restore strict CSP.
    is_build_path = request.path.startswith("/build")
    script_src = "script-src 'self' 'unsafe-inline'; " if is_admin_path else "script-src 'self'; "
    style_src = "style-src 'self' 'unsafe-inline'; " if (is_admin_path or is_build_path) else "style-src 'self'; "
    csp = (
        "default-src 'self'; "
        + script_src
        + style_src
        + "img-src 'self' data:; "
        + "font-src 'self'; "
        + "connect-src 'self'; "
        + "object-src 'none'; "
        + "base-uri 'self'; "
        + "frame-ancestors 'self'"
    )
    response.headers["Content-Security-Policy"] = csp
    if is_build_path:
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


@app.errorhandler(404)
def handle_404(err):
    return render_template("404.html"), 404


@app.errorhandler(500)
def handle_500(err):
    return render_template("500.html"), 500


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("home"))
    return redirect(url_for("login"))


@app.route("/maintenance")
def maintenance():
    return render_template("maintenance.html"), 503


@app.route("/terms")
def terms():
    return render_template("terms.html", title="利用規約")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html", title="プライバシーポリシー")


@app.route("/commerce")
def commerce():
    return render_template("commerce.html", title="特定商取引法に基づく表記")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    sent = False
    if request.method == "POST":
        subject = (request.form.get("subject") or "").strip()
        body = (request.form.get("body") or "").strip()
        app.logger.info("contact.received subject=%s body_len=%s", subject[:80] or "-", len(body))
        sent = True
    return render_template("contact.html", title="お問い合わせ", sent=sent)


@app.route("/guide")
def guide():
    return render_template("guide.html", title="用語", sections=GUIDE_SECTIONS)


@app.route("/shop")
def shop():
    db = get_db()
    product = _payment_product(EXPLORE_BOOST_PRODUCT_KEY)
    user = None
    recent_order = None
    boost_status = None
    purchase_locked = False
    pending_order = False
    if session.get("user_id"):
        user = db.execute(
            "SELECT id, username, is_admin, created_at, explore_boost_until FROM users WHERE id = ?",
            (int(session["user_id"]),),
        ).fetchone()
        if user:
            recent_order = _latest_payment_order_for_user_product(db, int(user["id"]), EXPLORE_BOOST_PRODUCT_KEY)
            boost_status = _explore_boost_status_for_user(user)
            pending_order = bool(
                recent_order and str(recent_order["status"] or "") in {PAYMENT_STATUS_CREATED, PAYMENT_STATUS_COMPLETED}
            )
            purchase_locked = bool((boost_status and boost_status["has_ever_purchased"]) or pending_order)
    return render_template(
        "shop.html",
        title="ショップ",
        product=product,
        checkout_ready=_payment_checkout_ready(EXPLORE_BOOST_PRODUCT_KEY),
        recent_order=recent_order,
        payment_status_labels=_payment_status_labels_map(),
        boost_status=boost_status,
        purchase_locked=purchase_locked,
        pending_order=pending_order,
    )


@app.route("/support")
def support():
    db = get_db()
    product = _payment_product(SUPPORT_PACK_PRODUCT_KEY)
    user = None
    reward_owned = False
    recent_order = None
    decor_asset = _get_decor_asset_by_key(db, product.get("grant_key")) if product else None
    if session.get("user_id"):
        user = db.execute(
            "SELECT id, username FROM users WHERE id = ?",
            (int(session["user_id"]),),
        ).fetchone()
        if user and product:
            reward_owned = _user_has_decor_key(db, int(user["id"]), product["grant_key"])
            recent_order = _latest_payment_order_for_user_product(db, int(user["id"]), product["product_key"])
    return render_template(
        "support.html",
        title="支援",
        product=product,
        checkout_ready=_payment_checkout_ready(SUPPORT_PACK_PRODUCT_KEY),
        reward_owned=reward_owned,
        recent_order=recent_order,
        payment_status_labels=_payment_status_labels_map(),
        decor_asset=decor_asset,
    )


@app.route("/support/checkout", methods=["POST"])
@login_required
def support_checkout():
    db = get_db()
    user_id = int(session["user_id"])
    product = _payment_product(SUPPORT_PACK_PRODUCT_KEY)
    if not product or not product.get("price_id"):
        flash("支援導線はまだ準備中です。", "error")
        return redirect(url_for("support"))
    if not _payment_checkout_ready(SUPPORT_PACK_PRODUCT_KEY):
        flash("決済機能の準備が完了していません。", "error")
        return redirect(url_for("support"))
    if _user_has_decor_key(db, user_id, product["grant_key"]):
        flash("この支援特典はすでに受け取り済みです。", "notice")
        return redirect(url_for("support"))
    try:
        checkout_result = _create_checkout_session_for_product(db, user_id=user_id, product=product)
    except Exception:
        app.logger.exception("payment.checkout_create_failed user_id=%s product=%s", user_id, product["product_key"])
        flash("決済画面の準備に失敗しました。時間を置いてもう一度お試しください。", "error")
        return redirect(url_for("support"))
    db.commit()
    return redirect(
        checkout_result["checkout_url"]
        or url_for("payment_success", session_id=checkout_result["session_id"], product_key=product["product_key"]),
        code=303,
    )


@app.route("/shop/explore-boost/checkout", methods=["POST"])
@login_required
def shop_explore_boost_checkout():
    db = get_db()
    user = db.execute(
        "SELECT id, username, is_admin, created_at, explore_boost_until FROM users WHERE id = ?",
        (int(session["user_id"]),),
    ).fetchone()
    product = _payment_product(EXPLORE_BOOST_PRODUCT_KEY)
    if not user or not product or not product.get("price_id"):
        flash("出撃ブーストはまだ準備中です。", "error")
        return redirect(url_for("shop"))
    if int(user["is_admin"] or 0) == 1:
        flash("管理者アカウントでは出撃ブーストを購入できません。", "notice")
        return redirect(url_for("shop"))
    if not _payment_checkout_ready(EXPLORE_BOOST_PRODUCT_KEY):
        flash("決済機能の準備が完了していません。", "error")
        return redirect(url_for("shop"))
    boost_status = _explore_boost_status_for_user(user)
    if boost_status["has_ever_purchased"]:
        flash("出撃ブーストは1回限りの購入です。", "notice")
        return redirect(url_for("shop"))
    recent_order = _latest_payment_order_for_user_product(db, int(user["id"]), EXPLORE_BOOST_PRODUCT_KEY)
    if recent_order and str(recent_order["status"] or "") in {PAYMENT_STATUS_CREATED, PAYMENT_STATUS_COMPLETED}:
        flash("前回の支払いを確認中です。少し待ってから状態を確認してください。", "notice")
        return redirect(url_for("shop"))
    try:
        checkout_result = _create_checkout_session_for_product(db, user_id=int(user["id"]), product=product)
    except Exception:
        app.logger.exception("shop.explore_boost_checkout_failed user_id=%s", user["id"])
        flash("決済画面の準備に失敗しました。時間を置いてもう一度お試しください。", "error")
        return redirect(url_for("shop"))
    db.commit()
    return redirect(
        checkout_result["checkout_url"]
        or url_for("payment_success", session_id=checkout_result["session_id"], product_key=product["product_key"]),
        code=303,
    )


@app.route("/payment/success")
def payment_success():
    db = get_db()
    order = None
    session_id = (request.args.get("session_id") or "").strip()
    product_key = (request.args.get("product_key") or "").strip()
    if session_id and session.get("user_id"):
        order = db.execute(
            """
            SELECT po.*, u.username
            FROM payment_orders po
            JOIN users u ON u.id = po.user_id
            WHERE po.stripe_checkout_session_id = ? AND po.user_id = ?
            LIMIT 1
            """,
            (session_id, int(session["user_id"])),
        ).fetchone()
    resolved_product = _payment_product(order["product_key"] if order else product_key)
    return_endpoint = _payment_return_endpoint_for_product(order["product_key"] if order else product_key)
    return render_template(
        "payment_success.html",
        title="支払い確認中",
        order=order,
        session_id=session_id,
        product=resolved_product,
        return_url=url_for(return_endpoint),
        payment_status_label=_payment_status_label,
    )


@app.route("/payment/cancel")
def payment_cancel():
    product_key = (request.args.get("product_key") or "").strip()
    product = _payment_product(product_key)
    return_endpoint = _payment_return_endpoint_for_product(product_key)
    return render_template(
        "payment_cancel.html",
        title="購入を中断しました",
        product=product,
        return_url=url_for(return_endpoint),
    )


@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    if not _payment_webhook_ready():
        return jsonify({"ok": False, "error": "stripe_not_configured"}), 503
    stripe_api = _configure_stripe_api()
    payload_raw = request.get_data(cache=False, as_text=False)
    signature = request.headers.get("Stripe-Signature", "")
    signature_error_types = [ValueError]
    stripe_error_mod = getattr(stripe_api, "error", None)
    if stripe_error_mod and hasattr(stripe_error_mod, "SignatureVerificationError"):
        signature_error_types.append(stripe_error_mod.SignatureVerificationError)
    try:
        event = stripe_api.Webhook.construct_event(payload_raw, signature, STRIPE_WEBHOOK_SECRET)
    except tuple(signature_error_types):
        return jsonify({"ok": False, "error": "invalid_signature"}), 400

    db = get_db()
    event_type = str(_stripe_value(event, "type", "") or "").strip()
    event_id = str(_stripe_value(event, "id", "") or "").strip() or None
    data_container = _stripe_value(event, "data", {}) or {}
    session_obj = _stripe_value(data_container, "object", {}) or {}
    metadata = _stripe_value(session_obj, "metadata", {}) or {}
    stripe_checkout_session_id = str(_stripe_value(session_obj, "id", "") or "").strip() or None
    stripe_payment_intent_id = str(_stripe_value(session_obj, "payment_intent", "") or "").strip() or None
    amount_jpy = _stripe_value(session_obj, "amount_total", None)
    try:
        amount_jpy = int(amount_jpy) if amount_jpy is not None else None
    except (TypeError, ValueError):
        amount_jpy = None
    currency = str(_stripe_value(session_obj, "currency", "") or "").lower() or None
    user_id = int(metadata["user_id"]) if str(metadata.get("user_id") or "").isdigit() else None
    product_key = str(metadata.get("product_key") or "").strip() or None
    grant_type = str(metadata.get("grant_type") or "").strip() or None
    boost_days = int(metadata["boost_days"]) if str(metadata.get("boost_days") or "").isdigit() else 0
    product = _payment_product(product_key)
    grant_event_types = _payment_grant_audit_event_types(product)

    audit_log(
        db,
        AUDIT_EVENT_TYPES["PAYMENT_WEBHOOK_RECEIVED"],
        user_id=user_id,
        request_id=getattr(g, "request_id", None),
        action_key=product_key or event_type or "stripe_webhook",
        entity_type="payment_event",
        entity_id=None,
        payload={
            "product_key": product_key,
            "stripe_checkout_session_id": stripe_checkout_session_id,
            "stripe_payment_intent_id": stripe_payment_intent_id,
            "stripe_event_id": event_id,
            "amount_jpy": amount_jpy,
            "currency": currency,
            "status": event_type,
            "grant_type": grant_type,
            "boost_days": int(boost_days or 0),
        },
        ip=request.remote_addr,
    )

    order = _payment_order_for_session(db, stripe_checkout_session_id)
    if event_type == "checkout.session.expired":
        if order:
            _update_payment_order(
                db,
                int(order["id"]),
                stripe_payment_intent_id=stripe_payment_intent_id,
                stripe_event_id=event_id,
                amount_jpy=amount_jpy,
                currency=currency,
                status=PAYMENT_STATUS_EXPIRED,
            )
            db.commit()
        else:
            db.commit()
        return jsonify({"received": True})

    if event_type != "checkout.session.completed":
        db.commit()
        return jsonify({"received": True})

    if order and order["stripe_event_id"] and str(order["stripe_event_id"]) == str(event_id or ""):
        audit_log(
            db,
            grant_event_types["skip"],
            user_id=(int(order["user_id"]) if order["user_id"] is not None else user_id),
            request_id=getattr(g, "request_id", None),
            action_key=(order["product_key"] or product_key or "payment_duplicate"),
            entity_type="payment_order",
            entity_id=int(order["id"]),
            payload={
                "product_key": order["product_key"],
                "stripe_checkout_session_id": stripe_checkout_session_id,
                "stripe_payment_intent_id": stripe_payment_intent_id,
                "stripe_event_id": event_id,
                "amount_jpy": amount_jpy,
                "currency": currency,
                "status": str(order["status"] or ""),
                "duplicate_reason": "event_already_processed",
                "boost_days": int(order["boost_days"] or boost_days or 0),
                "starts_at": (int(order["starts_at"]) if order["starts_at"] else None),
                "ends_at": (int(order["ends_at"]) if order["ends_at"] else None),
            },
            ip=request.remote_addr,
        )
        db.commit()
        return jsonify({"received": True})

    if not product or not user_id or not stripe_checkout_session_id:
        if order:
            _update_payment_order(
                db,
                int(order["id"]),
                stripe_payment_intent_id=stripe_payment_intent_id,
                stripe_event_id=event_id,
                amount_jpy=amount_jpy,
                currency=currency,
                status=PAYMENT_STATUS_FAILED,
            )
        audit_log(
            db,
            grant_event_types["failed"],
            user_id=user_id,
            request_id=getattr(g, "request_id", None),
            action_key=product_key or "payment_invalid_metadata",
            entity_type="payment_order",
            entity_id=(int(order["id"]) if order else None),
            payload={
                "product_key": product_key,
                "stripe_checkout_session_id": stripe_checkout_session_id,
                "stripe_payment_intent_id": stripe_payment_intent_id,
                "stripe_event_id": event_id,
                "amount_jpy": amount_jpy,
                "currency": currency,
                "status": PAYMENT_STATUS_FAILED,
                "duplicate_reason": "invalid_metadata",
                "boost_days": int(boost_days or 0),
            },
            ip=request.remote_addr,
        )
        db.commit()
        return jsonify({"received": True})

    if order is None:
        now_ts = _now_ts()
        db.execute(
            """
            INSERT INTO payment_orders (
                user_id,
                product_key,
                stripe_checkout_session_id,
                stripe_payment_intent_id,
                stripe_event_id,
                amount_jpy,
                currency,
                status,
                grant_type,
                boost_days,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                product["product_key"],
                stripe_checkout_session_id,
                stripe_payment_intent_id,
                event_id,
                amount_jpy,
                currency,
                PAYMENT_STATUS_COMPLETED,
                product["grant_type"],
                int(product.get("boost_days") or 0),
                now_ts,
                now_ts,
            ),
        )
        order = _payment_order_for_session(db, stripe_checkout_session_id)
    else:
        if int(order["user_id"]) != user_id or str(order["product_key"]) != product["product_key"]:
            _update_payment_order(
                db,
                int(order["id"]),
                stripe_payment_intent_id=stripe_payment_intent_id,
                stripe_event_id=event_id,
                amount_jpy=amount_jpy,
                currency=currency,
                status=PAYMENT_STATUS_FAILED,
                boost_days=int(product.get("boost_days") or 0),
            )
            audit_log(
                db,
                grant_event_types["failed"],
                user_id=user_id,
                request_id=getattr(g, "request_id", None),
                action_key=product["product_key"],
                entity_type="payment_order",
                entity_id=int(order["id"]),
                payload={
                    "product_key": product["product_key"],
                    "stripe_checkout_session_id": stripe_checkout_session_id,
                    "stripe_payment_intent_id": stripe_payment_intent_id,
                    "stripe_event_id": event_id,
                    "amount_jpy": amount_jpy,
                    "currency": currency,
                    "status": PAYMENT_STATUS_FAILED,
                    "duplicate_reason": "order_mismatch",
                    "boost_days": int(product.get("boost_days") or 0),
                },
                ip=request.remote_addr,
            )
            db.commit()
            return jsonify({"received": True})
        if str(order["status"] or "") in {PAYMENT_STATUS_COMPLETED, PAYMENT_STATUS_GRANTED}:
            audit_log(
                db,
                grant_event_types["skip"],
                user_id=user_id,
                request_id=getattr(g, "request_id", None),
                action_key=product["product_key"],
                entity_type="payment_order",
                entity_id=int(order["id"]),
                payload={
                    "product_key": product["product_key"],
                    "stripe_checkout_session_id": stripe_checkout_session_id,
                    "stripe_payment_intent_id": stripe_payment_intent_id,
                    "stripe_event_id": event_id,
                    "amount_jpy": amount_jpy,
                    "currency": currency,
                    "status": str(order["status"] or ""),
                    "duplicate_reason": "session_already_completed",
                    "boost_days": int(order["boost_days"] or product.get("boost_days") or 0),
                    "starts_at": (int(order["starts_at"]) if order["starts_at"] else None),
                    "ends_at": (int(order["ends_at"]) if order["ends_at"] else None),
                },
                ip=request.remote_addr,
            )
            db.commit()
            return jsonify({"received": True})
        _update_payment_order(
            db,
            int(order["id"]),
            stripe_payment_intent_id=stripe_payment_intent_id,
            stripe_event_id=event_id,
            amount_jpy=amount_jpy,
            currency=currency,
            status=PAYMENT_STATUS_COMPLETED,
            boost_days=int(product.get("boost_days") or 0),
        )
        order = _payment_order_for_session(db, stripe_checkout_session_id)

    audit_log(
        db,
        AUDIT_EVENT_TYPES["PAYMENT_COMPLETED"],
        user_id=user_id,
        request_id=getattr(g, "request_id", None),
        action_key=product["product_key"],
        entity_type="payment_order",
        entity_id=(int(order["id"]) if order else None),
        payload={
            "product_key": product["product_key"],
            "stripe_checkout_session_id": stripe_checkout_session_id,
            "stripe_payment_intent_id": stripe_payment_intent_id,
            "stripe_event_id": event_id,
            "amount_jpy": amount_jpy,
            "currency": currency,
            "status": PAYMENT_STATUS_COMPLETED,
            "grant_type": product["grant_type"],
            "boost_days": int(product.get("boost_days") or 0),
        },
        ip=request.remote_addr,
    )

    grant_result = _grant_payment_reward(db, user_id, product)
    if not grant_result["ok"]:
        _update_payment_order(db, int(order["id"]), status=PAYMENT_STATUS_FAILED)
        audit_log(
            db,
            grant_event_types["failed"],
            user_id=user_id,
            request_id=getattr(g, "request_id", None),
            action_key=product["product_key"],
            entity_type="payment_order",
            entity_id=int(order["id"]),
            payload={
                "product_key": product["product_key"],
                "stripe_checkout_session_id": stripe_checkout_session_id,
                "stripe_payment_intent_id": stripe_payment_intent_id,
                "stripe_event_id": event_id,
                "amount_jpy": amount_jpy,
                "currency": currency,
                "status": PAYMENT_STATUS_FAILED,
                "duplicate_reason": grant_result["duplicate_reason"],
                "boost_days": int(grant_result.get("boost_days") or product.get("boost_days") or 0),
                "starts_at": grant_result.get("starts_at"),
                "ends_at": grant_result.get("ends_at"),
            },
            ip=request.remote_addr,
        )
        db.commit()
        return jsonify({"received": True})

    if grant_result["granted"]:
        _update_payment_order(
            db,
            int(order["id"]),
            status=PAYMENT_STATUS_GRANTED,
            granted_at=_now_ts(),
            boost_days=int(grant_result.get("boost_days") or product.get("boost_days") or 0),
            starts_at=grant_result.get("starts_at"),
            ends_at=grant_result.get("ends_at"),
        )
        audit_log(
            db,
            grant_event_types["success"],
            user_id=user_id,
            request_id=getattr(g, "request_id", None),
            action_key=product["product_key"],
            entity_type="payment_order",
            entity_id=int(order["id"]),
            payload={
                "product_key": product["product_key"],
                "stripe_checkout_session_id": stripe_checkout_session_id,
                "stripe_payment_intent_id": stripe_payment_intent_id,
                "stripe_event_id": event_id,
                "amount_jpy": amount_jpy,
                "currency": currency,
                "status": PAYMENT_STATUS_GRANTED,
                "grant_type": product["grant_type"],
                "grant_key": product.get("grant_key"),
                "boost_days": int(grant_result.get("boost_days") or product.get("boost_days") or 0),
                "starts_at": grant_result.get("starts_at"),
                "ends_at": grant_result.get("ends_at"),
            },
            ip=request.remote_addr,
        )
    else:
        _update_payment_order(
            db,
            int(order["id"]),
            boost_days=int(grant_result.get("boost_days") or product.get("boost_days") or 0),
            starts_at=grant_result.get("starts_at"),
            ends_at=grant_result.get("ends_at"),
        )
        audit_log(
            db,
            grant_event_types["skip"],
            user_id=user_id,
            request_id=getattr(g, "request_id", None),
            action_key=product["product_key"],
            entity_type="payment_order",
            entity_id=int(order["id"]),
            payload={
                "product_key": product["product_key"],
                "stripe_checkout_session_id": stripe_checkout_session_id,
                "stripe_payment_intent_id": stripe_payment_intent_id,
                "stripe_event_id": event_id,
                "amount_jpy": amount_jpy,
                "currency": currency,
                "status": PAYMENT_STATUS_COMPLETED,
                "duplicate_reason": grant_result["duplicate_reason"],
                "boost_days": int(grant_result.get("boost_days") or product.get("boost_days") or 0),
                "starts_at": grant_result.get("starts_at"),
                "ends_at": grant_result.get("ends_at"),
            },
            ip=request.remote_addr,
        )
    db.commit()
    return jsonify({"received": True})


@app.route("/sitemap.xml")
def sitemap_xml():
    root_url = _public_game_root_url().rstrip("/")
    urls = [
        f"{root_url}/",
        f"{root_url}/login",
        f"{root_url}/register",
        f"{root_url}/home",
        f"{root_url}/lab",
        f"{root_url}/lab/race",
        f"{root_url}/lab/upload",
        f"{root_url}/lab/showcase",
        f"{root_url}/guide",
        f"{root_url}/terms",
        f"{root_url}/privacy",
        f"{root_url}/commerce",
        f"{root_url}/support",
    ]
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc in urls:
        xml.append("  <url>")
        xml.append(f"    <loc>{loc}</loc>")
        xml.append("  </url>")
    xml.append("</urlset>")
    return Response("\n".join(xml), content_type="application/xml; charset=utf-8")


@app.route("/healthz")
def healthz():
    snapshot = _health_snapshot()
    return jsonify(snapshot), (200 if snapshot["ok"] else 503)


@app.route("/changelog")
def changelog():
    entries = [
        {
            "version": "0.1.14",
            "date": "2026/03/26",
            "title": "育成導線と表示整理を改善",
            "notes": [
                "探索場所ごとの育ち方の差を追加",
                "ロボの性格表示（安定 / 背水 / 爆発）を追加",
                "目的別ランキングと展示ソートを追加",
                "用語ページを追加",
                "ホームから前回の出撃先へすぐ出撃できるよう改善",
                "Layer2ボス報酬未付与の不具合を修正",
            ],
        },
        {"version": "0.1.13", "date": "2026-03-21", "title": "ヘッダー挙動と sitemap を調整", "notes": ["PC でのヘッダー自動非表示判定を修正", "公開用の /sitemap.xml を追加"]},
        {"version": "0.1.12", "date": "2026-03-21", "title": "公開運用の土台を強化", "notes": ["ポータル送信の再送キューと運用タイマー例を追加", "利用規約/プライバシー/問い合わせ/監視/バックアップ運用を整備", "初心者ホームの情報量を絞って初回導線を改善"]},
        {"version": "0.1.11", "date": "2026-03-21", "title": "モバイル表示と本番運用の調整", "notes": ["VPS 本番化と独自ドメイン公開に対応", "ホームのモバイル表示順とヘッダー挙動を改善"]},
        {"version": "0.1.10", "date": "2026-02-27", "title": "初回リリース", "notes": ["運用開始", "探索/組立/合成/監査の基本機能を提供"]},
    ]
    return render_template("changelog.html", title="更新履歴", entries=entries)


@app.route("/client-error/js", methods=["POST"])
def client_error_js():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {"raw": str(payload)}
    safe_payload = {
        "page_name": str(payload.get("page_name") or payload.get("pageName") or "")[:80],
        "pathname": str(payload.get("pathname") or "")[:300],
        "full_url": str(payload.get("full_url") or payload.get("url") or request.url)[:600],
        "message": str(payload.get("message") or "")[:800],
        "source": str(payload.get("source") or "")[:400],
        "line": int(payload.get("line") or 0),
        "column": int(payload.get("column") or 0),
        "stack": str(payload.get("stack") or "")[:2000],
        "url": str(payload.get("url") or request.path)[:500],
        "user_agent": str(payload.get("userAgent") or request.headers.get("User-Agent") or "")[:600],
        "kind": str(payload.get("kind") or "window.onerror")[:80],
        "step": str(payload.get("step") or "")[:160],
        "last_step": str(payload.get("last_step") or payload.get("lastStep") or "")[:160],
        "body_class": str(payload.get("body_class") or payload.get("bodyClass") or "")[:300],
        "body_id": str(payload.get("body_id") or payload.get("bodyId") or "")[:120],
        "page_template": str(payload.get("page_template") or payload.get("pageTemplate") or "")[:120],
        "ready_state": str(payload.get("ready_state") or payload.get("readyState") or "")[:40],
        "important_dom_state": payload.get("important_dom_state") if isinstance(payload.get("important_dom_state"), dict) else {},
        "loaded_scripts": payload.get("loaded_scripts") if isinstance(payload.get("loaded_scripts"), list) else [],
        "request_id": str(payload.get("requestId") or getattr(g, "request_id", ""))[:120],
        "user_id": int(session.get("user_id")) if session.get("user_id") else None,
    }
    log_msg = (
        "[client-js] page=%s kind=%s step=%s user=%s path=%s msg=%s "
        "src=%s:%s:%s last_step=%s body_class=%s body_id=%s template=%s ready=%s dom=%s scripts=%s"
    )
    log_args = (
        safe_payload["page_name"] or "-",
        safe_payload["kind"],
        safe_payload["step"] or "-",
        safe_payload["user_id"] if safe_payload["user_id"] is not None else "-",
        safe_payload["pathname"] or request.path,
        safe_payload["message"][:180],
        safe_payload["source"][:120],
        safe_payload["line"],
        safe_payload["column"],
        safe_payload["last_step"] or "-",
        safe_payload["body_class"][:140],
        safe_payload["body_id"][:80],
        safe_payload["page_template"][:80],
        safe_payload["ready_state"] or "-",
        json.dumps(safe_payload["important_dom_state"], ensure_ascii=False)[:240],
        ",".join(str(x) for x in safe_payload["loaded_scripts"][:10])[:260],
    )
    kind = safe_payload["kind"]
    error_kinds = {"window.onerror", "unhandledrejection", "caught_exception"}
    is_known_home_page_syntax_cache = (
        kind == "window.onerror"
        and "invalid or unexpected token" in (safe_payload["message"] or "").lower()
        and "home_page_v2.js" in (safe_payload["source"] or "").lower()
        and safe_payload["line"] == 163
        and safe_payload["column"] == 20
    )
    if kind == "overlay-scan":
        extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
        app.logger.warning(log_msg, *log_args)
        app.logger.warning(
            "[client-js-overlay] tag=%s id=%s class=%s rect=%s zIndex=%s backgroundColor=%s",
            str(extra.get("tag") or ""),
            str(extra.get("id") or ""),
            str(extra.get("className") or ""),
            json.dumps(extra.get("rect") or {}, ensure_ascii=False),
            str(extra.get("zIndex") or ""),
            str(extra.get("backgroundColor") or ""),
        )
    elif is_known_home_page_syntax_cache:
        app.logger.warning(
            "[client-js-known] page=%s kind=%s msg=%s src=%s:%s:%s (treat_as_cache_or_legacy)",
            safe_payload["page_name"] or "-",
            safe_payload["kind"],
            safe_payload["message"][:180],
            safe_payload["source"][:120],
            safe_payload["line"],
            safe_payload["column"],
        )
        if safe_payload["stack"]:
            app.logger.warning("[client-js-known-stack] %s", safe_payload["stack"][:1800])
    elif kind in error_kinds:
        app.logger.error(log_msg, *log_args)
        if safe_payload["stack"]:
            app.logger.error("[client-js-stack] %s", safe_payload["stack"][:1800])
    elif kind == "init_step":
        app.logger.info(log_msg, *log_args)
    else:
        app.logger.warning(log_msg, *log_args)
    return ("", 204)


def _login_user_session(db, user_row):
    session.clear()
    session["user_id"] = int(user_row["id"])
    session["username"] = _display_username(
        user_row["username"],
        is_admin=bool(int(user_row["is_admin"] or 0)) if "is_admin" in user_row.keys() else False,
    )
    session["battle_log"] = []
    db.execute("UPDATE users SET last_seen_at = ? WHERE id = ?", (int(time.time()), int(user_row["id"])))
    db.commit()


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    ref_code = (request.values.get("ref") or "").strip().upper()
    if request.method == "POST":
        username = _normalize_main_admin_username(request.form.get("username", "").strip())
        password = request.form.get("password", "").strip()
        password_confirm = request.form.get("password_confirm", "").strip()
        if not username or not password:
            error = "ユーザー名とパスワードを入力してください。"
        elif password_confirm and password_confirm != password:
            error = "確認用パスワードが一致しません。"
        else:
            db = get_db()
            try:
                is_admin = 1 if _is_main_admin_username(username) else 0
                cur = db.execute(
                    """
                    INSERT INTO users
                    (username, password_hash, coins, created_at, last_seen_at, is_admin, is_admin_protected)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        username,
                        generate_password_hash(password),
                        0,
                        int(time.time()),
                        int(time.time()),
                        is_admin,
                        is_admin,
                    ),
                )
                _ensure_user_invite_code(db, cur.lastrowid)
                _attach_referral_if_valid(
                    db,
                    referred_user_id=cur.lastrowid,
                    referral_code=ref_code,
                    request_ip=request.remote_addr,
                )
                initialize_new_user(db, cur.lastrowid)
                _ensure_qol_entitlement(db, cur.lastrowid)
                db.commit()
                user_row = db.execute("SELECT * FROM users WHERE id = ?", (int(cur.lastrowid),)).fetchone()
                if user_row:
                    _login_user_session(db, user_row)
                    session["just_registered"] = 1
                return redirect(url_for("home"))
            except sqlite3.IntegrityError:
                error = "そのユーザー名は既に使われています。"
    return render_template("register.html", error=error, ref_code=ref_code)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    reason = request.args.get("reason", "")
    next_path = request.args.get("next", "")
    message = None
    if reason == "expired":
        message = "セッションが期限切れです。もう一度ログインしてください。"
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        next_path = request.form.get("next", "").strip()
        db = get_db()
        user = _find_user_for_login(db, username)
        if user and check_password_hash(user["password_hash"], password):
            if int(user["is_banned"] or 0) == 1:
                error = "このアカウントは利用停止されています。"
                return render_template("login.html", error=error, message=message, next_path=next_path)
            if int(user["is_admin_protected"] or 0) == 1:
                error = "このアカウントは通常ログインできません。"
                return render_template("login.html", error=error, message=message, next_path=next_path)
            if _is_main_admin_username(username) and user["is_admin"] == 0:
                db.execute("UPDATE users SET is_admin = 1, is_admin_protected = 1 WHERE id = ?", (user["id"],))
                db.commit()
                user = db.execute("SELECT * FROM users WHERE id = ?", (int(user["id"]),)).fetchone()
            _login_user_session(db, user)
            if next_path and next_path.startswith("/") and not next_path.startswith("//"):
                return redirect(next_path)
            return redirect(url_for("home"))
        error = "ユーザー名かパスワードが違います。"
    return render_template("login.html", error=error, message=message, next_path=next_path)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    next_path = request.args.get("next", "").strip()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        next_path = request.form.get("next", "").strip()
        db = get_db()
        user = _find_user_for_login(db, username)
        if user and check_password_hash(user["password_hash"], password):
            if int(user["is_banned"] or 0) == 1:
                error = "このアカウントは利用停止されています。"
            elif int(user["is_admin"] or 0) != 1:
                error = "管理者権限が必要です。"
            else:
                _login_user_session(db, user)
                if next_path and next_path.startswith("/") and not next_path.startswith("//"):
                    return redirect(next_path)
                return redirect(url_for("admin"))
        else:
            error = "ユーザー名かパスワードが違います。"
    return render_template("admin_login.html", error=error, next_path=next_path)


@app.get("/debug/ui_effects_off")
def debug_ui_effects_off():
    session["ui_effects_enabled"] = False
    flash("UI演出をOFFにしました。")
    next_path = request.args.get("next", "").strip()
    if not next_path or not next_path.startswith("/"):
        next_path = request.referrer or url_for("home")
    return redirect(next_path)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/starter-pack/claim", methods=["POST"])
@login_required
def starter_pack_claim():
    db = get_db()
    result = initialize_new_user(db, session["user_id"])
    _ensure_qol_entitlement(db, session["user_id"])
    db.commit()
    if result.get("ok"):
        session["message"] = "スターターパックを受け取りました。"
    else:
        session["message"] = "スターターパックの付与に失敗しました。"
    return redirect(url_for("home"))


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    message = None
    if request.method == "POST":
        avatar_file = request.files.get("avatar")
        if not avatar_file:
            message = "画像ファイルを選択してください。"
        else:
            ok, err, rel_path = _save_user_avatar(avatar_file, user["id"])
            if not ok:
                message = err
            else:
                db.execute("UPDATE users SET avatar_path = ? WHERE id = ?", (rel_path, user["id"]))
                db.commit()
                message = "ユーザーアイコンを更新しました。"
                user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    return render_template(
        "settings.html",
        user=user,
        message=message,
        avatar_path=_user_avatar_rel(user),
        badge_path=_user_badge_rel(db, user["id"]),
    )


@app.route("/settings/battle_log_mode", methods=["POST"])
@login_required
def settings_battle_log_mode():
    db = get_db()
    mode = (request.form.get("mode") or "").strip().lower()
    if mode not in {"collapsed", "expanded"}:
        mode = "collapsed"
    db.execute("UPDATE users SET battle_log_mode = ? WHERE id = ?", (mode, session["user_id"]))
    db.commit()
    next_path = (request.form.get("next") or "").strip()
    if next_path and next_path.startswith("/"):
        return redirect(next_path)
    return redirect(url_for("home"))


@app.route("/home")
@login_required
def home():
    if HOME_OK_MODE:
        return "HOME OK"
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if user is None:
        if DEV_MODE:
            app.logger.debug(
                "home user missing path=%s cookies=%s session_keys=%s",
                request.path,
                dict(request.cookies),
                list(session.keys()),
            )
        session.clear()
        return redirect(url_for("login", next=request.path, reason="expired"))
    prev_invite_code = (user["invite_code"] or "").strip() if "invite_code" in user.keys() else ""
    _ensure_qol_entitlement(db, user["id"])
    invite_code = _ensure_user_invite_code(db, user["id"])
    referral_eval = evaluate_referral_qualification(db, user["id"], request_ip=request.remote_addr)
    if (not prev_invite_code and invite_code) or referral_eval.get("updated", 0) > 0:
        db.commit()
    show_axis_hint = int(user["home_axis_hint_seen"] or 0) == 0 if "home_axis_hint_seen" in user.keys() else True
    if show_axis_hint:
        db.execute("UPDATE users SET home_axis_hint_seen = 1 WHERE id = ?", (user["id"],))
        db.commit()
        user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    robot_count = db.execute(
        "SELECT COUNT(*) AS c FROM user_robots WHERE user_id = ?", (session["user_id"],)
    ).fetchone()["c"]
    instance_count = db.execute(
        "SELECT COUNT(*) AS c FROM robot_instances WHERE user_id = ? AND status != 'decomposed'",
        (user["id"],),
    ).fetchone()["c"]
    has_any_robot = int(instance_count or 0) > 0
    part_storage = _part_storage_snapshot(db, user["id"])
    part_inventory_count = int(part_storage["inventory_count"])
    part_storage_count = int(part_storage["storage_count"])
    limits = _effective_limits(db, user)
    _ensure_showcase_slots(db, user["id"], limits["showcase_slots"])
    showcase_rows = _showcase_rows(db, user["id"])
    for row in showcase_rows:
        if row["robot_instance_id"] and not row["composed_image_path"]:
            inst = {"id": row["robot_instance_id"]}
            parts = db.execute(
                "SELECT * FROM robot_instance_parts WHERE robot_instance_id = ?",
                (row["robot_instance_id"],),
            ).fetchone()
            if parts:
                _compose_instance_image(db, inst, parts)
    showcase_rows = _showcase_rows(db, user["id"])
    milestones = _evaluate_milestones(db, user)
    active_robot = _get_active_robot(db, user["id"])
    main_robot = active_robot if active_robot else _select_main_robot(db, user["id"])
    app.logger.info(
        "home.main_robot_render user_id=%s robot_id=%s image_url=%s composed_path=%s updated_at=%s active_robot_id=%s",
        user["id"],
        (main_robot.get("id") if main_robot else None),
        (main_robot.get("image_url") if main_robot else None),
        (main_robot.get("composed_image_path") if main_robot else None),
        (main_robot.get("updated_at") if main_robot else None),
        user["active_robot_id"],
    )
    main_robot_stats = _compute_robot_stats_for_instance(db, main_robot["id"]) if main_robot else None
    main_robot_style = _robot_style_from_instance_key(main_robot.get("style_key") if main_robot else None)
    main_robot_profile = _robot_profile_view(main_robot_stats)
    style_achievements = _style_achievements_progress(main_robot)
    idle_line = None
    if main_robot:
        idle_line = get_idle_line(main_robot["personality"], main_robot["name"])
    week_key = _world_week_key()
    weekly_env = _world_current_environment(db)
    weekly_recommendation = (
        _humanize_stat_text(_world_recommendation(weekly_env["element"], _normalize_world_mode(weekly_env["mode"])))
        if weekly_env
        else ""
    )
    weekly_env_effect_lines = _world_effect_summary_lines(weekly_env)
    weekly_kills_total = _world_counter_get(db, week_key, "kills_total")
    weekly_kills_attr = _world_counter_get(
        db,
        week_key,
        f"kills_{(weekly_env['element'] if weekly_env else 'NORMAL')}",
    )
    weekly_trends = _world_weekly_trends(db, week_key, limit=3)
    weekly_hot_areas = _world_hot_area_rows(db, week_key, limit=3, user_row=user)
    weekly_faction_key = _element_to_faction(weekly_env["element"]) if weekly_env else "aurix"
    user_faction = _normalize_faction_key(user["faction"] if "faction" in user.keys() else None)
    faction_unlock_counts = _faction_unlock_counts(db, user["id"])
    faction_can_choose = bool((not user_faction) and _faction_unlock_ready(faction_unlock_counts))
    faction_member_counts = _faction_member_counts(db)
    faction_recommended = _faction_recommended_key(faction_member_counts) if faction_can_choose else None
    faction_week_scores = _faction_week_scores(db, week_key)
    faction_score_rows = _faction_score_rows(
        faction_week_scores,
        faction_member_counts,
        user_faction=user_faction,
        weekly_faction_key=weekly_faction_key,
    )
    prev_week_key = _faction_prev_week_key(week_key)
    prev_faction_result = _faction_week_result(db, prev_week_key)
    if not prev_faction_result:
        _ensure_faction_war_auto_close(db, week_key)
        prev_faction_result = _faction_week_result(db, prev_week_key)
    faction_buff_winner = _faction_effective_winner_for_week(db, week_key)
    faction_buff_active = bool(user_faction and faction_buff_winner and user_faction == faction_buff_winner)
    weekly_mvp = _weekly_mvp_snapshot(db, week_key)
    faction_status = {
        "is_joined": bool(user_faction),
        "faction": user_faction,
        "counts": faction_unlock_counts,
        "can_choose": faction_can_choose,
    }
    research_summary = _home_research_summary(db, week_key)
    research_unlock_banner = _home_research_unlock_banner(db, week_key)
    main_robot_weekly_fit = (
        _robot_weekly_fit(db, main_robot["id"], weekly_env["element"])
        if main_robot and weekly_env
        else False
    )
    today_progress = _today_progress(db, user["id"])
    first_win_banner = None
    boss_pity_status = _home_boss_pity_status(db, user["id"])
    boss_alert_status = _home_boss_alert_status(db, user["id"])
    boss_alert_hint = _boss_alert_recommendation_context(boss_alert_status)
    recent_drop_items = _recent_drop_items(db, user["id"], limit=5)
    now = _now_ts()
    explore_ct_seconds = _explore_ct_seconds_for_user(user, now_ts=now)
    ct_remain, _ = _explore_remaining_seconds_for_user(db, user, user["id"], now_ts=now)
    ct_ready_at = int(now + max(0, int(ct_remain)))
    if int(user["is_admin"] or 0) == 1:
        ct_text = "出撃可能！"
        ct_button_text = "出撃する"
        ct_status_text = ""
    elif int(ct_remain) > 0:
        ct_text = f"出撃まであと{int(ct_remain)}秒！"
        ct_button_text = f"あと{int(ct_remain)}秒"
        ct_status_text = f"あと{int(ct_remain)}秒"
    else:
        ct_text = "出撃可能！"
        ct_button_text = "出撃する"
        ct_status_text = ""
    newbie_boost = None
    if user["is_admin"] != 1 and _is_newbie_boost_active(user, now_ts=now):
        newbie_boost = {
            "ct_seconds": int(explore_ct_seconds),
            "hours_left": _newbie_boost_hours_left(user, now_ts=now),
        }
    home_comm_initial_tab = "world"
    home_comm_initial_room_key = COMM_ROOM_DEFS[0]["key"]
    home_active_user_count = count_active_users(
        db,
        window_minutes=USER_PRESENCE_ACTIVE_WINDOW_MINUTES,
    )
    home_active_user_line = _active_users_summary_line(
        home_active_user_count,
        window_minutes=USER_PRESENCE_ACTIVE_WINDOW_MINUTES,
    )
    home_comm_world_settings = _chat_room_settings(COMM_WORLD_ROOM_KEY)
    home_comm_room_settings_by_key = {
        room["key"]: _chat_room_settings(room["key"])
        for room in COMM_ROOM_DEFS
    }
    home_comm_room_activity_counts_by_key = {
        room["key"]: _chat_room_recent_participant_count(
            db,
            room["key"],
            window_minutes=COMM_ROOM_ACTIVITY_WINDOW_MINUTES,
        )
        for room in COMM_ROOM_DEFS
    }
    home_comm_room_activity_lines_by_key = {
        room["key"]: _room_activity_summary_line(
            home_comm_room_activity_counts_by_key.get(room["key"], 0),
            window_minutes=COMM_ROOM_ACTIVITY_WINDOW_MINUTES,
        )
        for room in COMM_ROOM_DEFS
    }
    home_comm_world_items = _home_world_timeline_items(
        db,
        limit=HOME_COMM_PREVIEW_LIMIT,
        is_admin=bool(int(user["is_admin"] or 0) == 1),
    )
    home_comm_room_items_by_key = {
        room["key"]: _room_message_items(
            db,
            room["key"],
            limit=HOME_COMM_PREVIEW_LIMIT,
        )
        for room in COMM_ROOM_DEFS
    }
    home_comm_personal_items = _personal_log_items(
        db,
        int(user["id"]),
        limit=HOME_COMM_PREVIEW_LIMIT,
    )
    home_ranking_rows, home_ranking_metric = _ranking_rows(
        db,
        "weekly_explores",
        limit=5,
        week_key=week_key,
    )
    home_ranking_rows = _decorate_user_rows(db, home_ranking_rows, user_key="id")
    home_ranking_url = url_for("ranking", metric="weekly_explores")
    upgrade_cost = max(10, user["click_power"] * 10)
    message = session.pop("message", None)
    slot_display_used = min(instance_count, limits["robot_slots"])
    slot_overflow = max(0, instance_count - limits["robot_slots"])
    unlocked_explore_areas = [a for a in EXPLORE_AREAS if _is_area_unlocked(user, a["key"], db=db)]
    saved_explore_area_key = _saved_explore_area_key(user, unlocked_explore_areas, db=db)
    selected_explore_area_key = _default_explore_area_key(user, unlocked_explore_areas, db=db)
    home_return_explore_cta = None
    if has_any_robot and saved_explore_area_key:
        saved_area = next((a for a in unlocked_explore_areas if a["key"] == saved_explore_area_key), None)
        if saved_area:
            home_return_explore_cta = {
                "area_key": saved_area["key"],
                "area_label": saved_area["label"],
                "button_label": "前回の出撃先で出撃",
            }
    home_area_cards = []
    for area_row in unlocked_explore_areas:
        area_info = EXPLORE_AREA_MAP_INFO.get(area_row["key"]) or {}
        area_desc = area_info.get("desc") or []
        tendency = _area_growth_tendency(area_row["key"])
        line = str(tendency.get("home_line") or "")
        home_area_cards.append(
            {
                "key": area_row["key"],
                "label": area_row["label"],
                "desc_line": str(area_desc[0]) if len(area_desc) >= 1 else "",
                "recommend_line": str(area_desc[1]) if len(area_desc) >= 2 else "",
                "warning_line": str(area_desc[2]) if len(area_desc) >= 3 else "",
                "tendency_line": line,
            }
        )
    locked_layer_lines = _locked_layer_lines(user, db=db)
    max_unlocked_layer = _visible_user_max_unlocked_layer(user, db=db)
    new_layer_badge = session.pop("home_new_layer_badge", None)
    unlocked_layer_recent = _home_recent_unlocked_layer(db, user["id"], now_ts=now)
    release_cap = _release_layer_cap_for_viewer(db, user_row=user)
    if int(new_layer_badge or 0) > int(release_cap):
        new_layer_badge = None
    if int(unlocked_layer_recent or 0) > int(release_cap):
        unlocked_layer_recent = None
    next_action_card = _home_next_action_card(
        db,
        user,
        boss_alert_status,
        max_unlocked_layer,
        new_layer_badge,
        unlocked_layer_recent,
        faction_status=faction_status,
    )
    total_explores = int(
        db.execute(
            "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
            (int(user["id"]), AUDIT_EVENT_TYPES["EXPLORE_END"]),
        ).fetchone()["c"]
        or 0
    )
    layer1_boss_defeated = _has_fixed_boss_defeat_in_area(db, user["id"], "layer_1")
    beginner_mission_available = (user["is_admin"] != 1) and (not layer1_boss_defeated)
    beginner_mission_hidden = (
        int(user["home_beginner_mission_hidden"] or 0) == 1
        if "home_beginner_mission_hidden" in user.keys()
        else False
    )
    show_beginner_mission = bool(beginner_mission_available and (not beginner_mission_hidden))
    home_beginner_focus = bool((user["is_admin"] != 1) and (show_beginner_mission or total_explores < 3))
    home_next_action_collapsed = (
        int(user["home_next_action_collapsed"] or 0) == 1
        if "home_next_action_collapsed" in user.keys()
        else False
    )
    home_next_action_force_open = bool(home_next_action_collapsed and boss_alert_status)
    show_next_action_card = bool(next_action_card) and (not home_next_action_collapsed or home_next_action_force_open)
    show_home_visibility_controls = bool(
        (beginner_mission_available and beginner_mission_hidden)
        or (next_action_card and home_next_action_collapsed and not home_next_action_force_open)
    )
    home_summary_line = "パーツを集めて自分だけのロボを組み立て、ボスを倒して次の層へ進む探索ゲームです。"
    home_beginner_hint = "最初は「ロボ編成」か「出撃」だけ見ればOKです。"
    beginner_mission_text = "出撃してパーツを集めよう！\n強くなったらボスに挑戦だ！"
    beginner_mission_cta_label = "出撃する"
    beginner_mission_is_post = True
    beginner_mission_cta_url = url_for("explore")
    if not has_any_robot:
        beginner_mission_text = "まずはロボを1体完成させよう！\nパーツを選んで出撃準備だ！"
        beginner_mission_cta_label = "ロボを編成する"
        beginner_mission_is_post = False
        beginner_mission_cta_url = url_for("build")
    intro_modal_seen = int(user["has_seen_intro_modal"] or 0) == 1 if "has_seen_intro_modal" in user.keys() else False
    just_registered = bool(session.pop("just_registered", None))
    show_intro_modal = (not intro_modal_seen) and (just_registered or total_explores == 0)
    intro_npc_image = "images/ui/robonavi.png"
    explore_submission_id = _issue_explore_submission_id()
    referral_counts = _referral_counts_for_referrer(db, user["id"])
    invite_link = _invite_link_for_code(invite_code)
    evolution_core_qty = _get_player_core_qty(db, user["id"], EVOLUTION_CORE_KEY)
    evolution_core_progress = (
        int(user["evolution_core_progress"] or 0)
        if "evolution_core_progress" in user.keys()
        else 0
    )
    evolution_core_status = _evolution_core_progress_status(
        evolution_core_progress,
        core_qty=evolution_core_qty,
    )
    evolution_feature_unlocked = _evolution_feature_unlocked(db, user=user)
    debug_snapshot = {
        "user_id": user["id"] if user else None,
        "chat_messages": len(home_comm_world_items),
        "posts": 0,
        "showcase_rows": len(showcase_rows),
    }
    is_main_admin = _is_main_admin_user_row(user)
    show_lab_menu = _release_open_for_viewer(db, "lab", user_row=user)
    try:
        return render_template(
            "home.html",
            user=user,
            robot_count=robot_count,
            posts=[],
            upgrade_cost=upgrade_cost,
            message=message,
            combo=session.get("combo", 0),
            is_admin=user["is_admin"] == 1,
            is_main_admin=is_main_admin,
            limits=limits,
            instance_count=instance_count,
            has_any_robot=has_any_robot,
            part_count=part_inventory_count,
            part_inventory_count=part_inventory_count,
            part_storage_count=part_storage_count,
            milestones=milestones,
            showcase_rows=showcase_rows,
            main_robot=main_robot,
            main_robot_stats=main_robot_stats,
            main_robot_style=main_robot_style,
            main_robot_profile=main_robot_profile,
            style_achievements=style_achievements,
            idle_line=idle_line,
            ct_text=ct_text,
            ct_button_text=ct_button_text,
            ct_status_text=ct_status_text,
            ct_remain=int(ct_remain),
            ct_ready_at=int(ct_ready_at),
            personality_labels=PERSONALITY_LABELS,
            explore_areas=unlocked_explore_areas,
            home_return_explore_cta=home_return_explore_cta,
            selected_explore_area_key=selected_explore_area_key,
            home_area_cards=home_area_cards,
            stage_modifiers_enabled=STAGE_MODIFIERS_ENABLED,
            locked_layer_lines=locked_layer_lines,
            max_unlocked_layer=max_unlocked_layer,
            new_layer_badge=(int(new_layer_badge) if new_layer_badge else None),
            show_axis_hint=show_axis_hint,
            home_ranking_rows=home_ranking_rows,
            home_ranking_metric=home_ranking_metric,
            home_ranking_url=home_ranking_url,
            slot_display_used=slot_display_used,
            slot_overflow=slot_overflow,
            weekly_env=weekly_env,
            weekly_env_effect_lines=weekly_env_effect_lines,
            weekly_recommendation=weekly_recommendation,
            weekly_kills_total=weekly_kills_total,
            weekly_kills_attr=weekly_kills_attr,
            weekly_trends=weekly_trends,
            weekly_hot_areas=weekly_hot_areas,
            faction_emblems=FACTION_EMBLEMS,
            faction_labels=FACTION_LABELS,
            weekly_faction_key=weekly_faction_key,
            user_faction=user_faction,
            faction_status=faction_status,
            faction_unlock_progress_line=_faction_unlock_progress_line(faction_unlock_counts),
            faction_member_counts=faction_member_counts,
            faction_recommended=faction_recommended,
            faction_week_scores=faction_week_scores,
            faction_score_rows=faction_score_rows,
            prev_week_key=prev_week_key,
            prev_faction_result=prev_faction_result,
            faction_buff_winner=faction_buff_winner,
            faction_buff_active=faction_buff_active,
            weekly_mvp=weekly_mvp,
            research_summary=research_summary,
            research_unlock_banner=research_unlock_banner,
            first_win_banner=first_win_banner,
            total_explores=total_explores,
            home_beginner_focus=home_beginner_focus,
            home_summary_line=home_summary_line,
            home_beginner_hint=home_beginner_hint,
            beginner_mission_available=beginner_mission_available,
            show_beginner_mission=show_beginner_mission,
            beginner_mission_text=beginner_mission_text,
            beginner_mission_cta_label=beginner_mission_cta_label,
            beginner_mission_is_post=beginner_mission_is_post,
            beginner_mission_cta_url=beginner_mission_cta_url,
            show_next_action_card=show_next_action_card,
            home_next_action_collapsed=home_next_action_collapsed,
            home_next_action_force_open=home_next_action_force_open,
            show_home_visibility_controls=show_home_visibility_controls,
            show_intro_modal=show_intro_modal,
            intro_npc_image=intro_npc_image,
            main_robot_weekly_fit=main_robot_weekly_fit,
            today_progress=today_progress,
            boss_pity_status=boss_pity_status,
            boss_alert_status=boss_alert_status,
            boss_alert_active=boss_alert_hint["boss_alert_active"],
            boss_type=boss_alert_hint["boss_type"],
            recommended_build=boss_alert_hint["recommended_build"],
            recommended_text=boss_alert_hint["recommended_text"],
            show_lab_menu=show_lab_menu,
            recent_drop_items=recent_drop_items,
            newbie_boost=newbie_boost,
            debug_snapshot=debug_snapshot,
            debug_comment=HOME_DEBUG_COMMENT,
            explore_submission_id=explore_submission_id,
            invite_code=invite_code,
            invite_link=invite_link,
            referral_counts=referral_counts,
            has_evolution_core=(int(evolution_core_qty or 0) >= 1),
            evolution_core_status=evolution_core_status,
            show_evolution_actions=evolution_feature_unlocked,
            next_action_card=next_action_card,
            home_comm_room_defs=COMM_ROOM_DEFS,
            home_comm_initial_tab=home_comm_initial_tab,
            home_comm_initial_room_key=home_comm_initial_room_key,
            home_active_user_line=home_active_user_line,
            home_comm_world_settings=home_comm_world_settings,
            home_comm_room_settings_by_key=home_comm_room_settings_by_key,
            home_comm_room_activity_counts_by_key=home_comm_room_activity_counts_by_key,
            home_comm_room_activity_lines_by_key=home_comm_room_activity_lines_by_key,
            home_comm_world_items=home_comm_world_items,
            home_comm_room_items_by_key=home_comm_room_items_by_key,
            home_comm_personal_items=home_comm_personal_items,
        )
    except Exception as exc:
        app.logger.exception("home rendering failed")
        if app.debug:
            return render_template(
                "home_error.html",
                error_text=str(exc),
                traceback_text=traceback.format_exc(),
            ), 500
        return render_template(
            "home_error.html",
            error_text="ホーム画面の描画に失敗しました。",
            traceback_text="",
        ), 500


@app.route("/home/intro-modal/dismiss", methods=["POST"])
@login_required
def home_intro_modal_dismiss():
    dont_show_again = (request.form.get("dont_show_again") or "1").strip().lower()
    if dont_show_again in ("1", "true", "on", "yes"):
        db = get_db()
        db.execute(
            "UPDATE users SET has_seen_intro_modal = 1, intro_guide_closed_at = ? WHERE id = ?",
            (now_str(), int(session["user_id"])),
        )
        db.commit()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return ("", 204)
    return redirect(url_for("home"))


def _safe_home_next_redirect():
    next_path = (request.form.get("next") or "").strip()
    if next_path.startswith("/"):
        return redirect(next_path)
    return redirect(url_for("home"))


@app.route("/home/beginner-mission/hide", methods=["POST"])
@login_required
def home_beginner_mission_hide():
    db = get_db()
    db.execute(
        "UPDATE users SET home_beginner_mission_hidden = 1 WHERE id = ?",
        (int(session["user_id"]),),
    )
    db.commit()
    return _safe_home_next_redirect()


@app.route("/home/beginner-mission/show", methods=["POST"])
@login_required
def home_beginner_mission_show():
    db = get_db()
    db.execute(
        "UPDATE users SET home_beginner_mission_hidden = 0 WHERE id = ?",
        (int(session["user_id"]),),
    )
    db.commit()
    return _safe_home_next_redirect()


@app.route("/home/next-action/collapse", methods=["POST"])
@login_required
def home_next_action_collapse():
    db = get_db()
    db.execute(
        "UPDATE users SET home_next_action_collapsed = 1 WHERE id = ?",
        (int(session["user_id"]),),
    )
    db.commit()
    return _safe_home_next_redirect()


@app.route("/home/next-action/expand", methods=["POST"])
@login_required
def home_next_action_expand():
    db = get_db()
    db.execute(
        "UPDATE users SET home_next_action_collapsed = 0 WHERE id = ?",
        (int(session["user_id"]),),
    )
    db.commit()
    return _safe_home_next_redirect()


@app.route("/faction/choose", methods=["GET", "POST"])
@login_required
def faction_choose():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not user:
        session.clear()
        return redirect(url_for("login"))
    user_faction = _normalize_faction_key(user["faction"] if "faction" in user.keys() else None)
    counts = _faction_unlock_counts(db, user["id"])
    can_choose = bool((not user_faction) and _faction_unlock_ready(counts))
    member_counts = _faction_member_counts(db)
    recommended_faction = _faction_recommended_key(member_counts)
    current_week_key = _world_week_key()
    weekly_env = _world_current_environment(db)
    weekly_faction_key = _element_to_faction(weekly_env["element"]) if weekly_env else None
    faction_score_rows = _faction_score_rows(
        _faction_week_scores(db, current_week_key),
        member_counts,
        user_faction=user_faction,
        weekly_faction_key=weekly_faction_key,
    )

    if request.method == "POST":
        if user_faction:
            flash("すでに陣営所属済みです。", "notice")
            return redirect(url_for("faction_choose"))
        if not can_choose:
            return render_template(
                "faction_choose.html",
                user=user,
                user_faction=None,
                can_choose=False,
                unlock_counts=counts,
                unlock_progress_line=_faction_unlock_progress_line(counts),
                faction_labels=FACTION_LABELS,
                faction_emblems=FACTION_EMBLEMS,
                member_counts=member_counts,
                recommended_faction=recommended_faction,
                faction_score_rows=faction_score_rows,
                current_week_key=current_week_key,
            ), 403
        chosen = _normalize_faction_key(request.form.get("faction"))
        if not chosen:
            flash("陣営を選択してください。", "error")
            return redirect(url_for("faction_choose"))
        db.execute("UPDATE users SET faction = ? WHERE id = ?", (chosen, user["id"]))
        audit_log(
            db,
            AUDIT_EVENT_TYPES["FACTION_CHOOSE"],
            user_id=user["id"],
            request_id=(getattr(g, "request_id", None) if g else None),
            action_key="faction_choose",
            entity_type="user",
            entity_id=user["id"],
            payload={
                "chosen_faction": chosen,
                "counts_snapshot": counts,
            },
            ip=request.remote_addr,
        )
        db.execute(
            "INSERT INTO chat_messages (user_id, username, message, created_at) VALUES (?, ?, ?, ?)",
            (
                int(user["id"]),
                "SYSTEM",
                f"{session.get('username', 'unknown')} が {FACTION_LABELS.get(chosen, chosen)} に所属した。",
                now_str(),
            ),
        )
        db.commit()
        flash(f"{FACTION_LABELS.get(chosen, chosen)} に所属しました。", "notice")
        return redirect(url_for("home"))

    status_code = 200
    if (not user_faction) and (not can_choose):
        status_code = 403
    return render_template(
        "faction_choose.html",
        user=user,
        user_faction=user_faction,
        can_choose=can_choose,
        unlock_counts=counts,
        unlock_progress_line=_faction_unlock_progress_line(counts),
        faction_labels=FACTION_LABELS,
        faction_emblems=FACTION_EMBLEMS,
        member_counts=member_counts,
        recommended_faction=recommended_faction,
        faction_score_rows=faction_score_rows,
        current_week_key=current_week_key,
    ), status_code


@app.route("/progress")
@login_required
def progress_view():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not user:
        return redirect(url_for("login"))
    today_progress = _today_progress(db, int(user["id"]))
    return render_template("progress.html", today_progress=today_progress)


@app.route("/research")
@login_required
def research_view():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not user:
        return redirect(url_for("login"))
    week_key = _world_week_key()
    research_summary = _home_research_summary(db, week_key)
    weekly_trends = _world_weekly_trends(db, week_key, limit=8)
    return render_template(
        "research.html",
        research_summary=research_summary,
        weekly_trends=weekly_trends,
    )


@app.route("/world")
@login_required
def world_view():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not user:
        return redirect(url_for("login"))
    week_key = _world_week_key()
    weekly_env = _world_current_environment(db)
    weekly_env_effect_lines = _world_effect_summary_lines(weekly_env)
    weekly_recommendation = (
        _humanize_stat_text(_world_recommendation(weekly_env["element"], _normalize_world_mode(weekly_env["mode"])))
        if weekly_env
        else ""
    )
    weekly_trends = _world_weekly_trends(db, week_key, limit=5)
    weekly_hot_areas = _world_hot_area_rows(db, week_key, limit=5, user_row=user)
    weekly_remaining_line = _world_week_remaining_line(week_key)
    weekly_mvp = _weekly_mvp_snapshot(db, week_key)
    research_summary = _home_research_summary(db, week_key)
    member_counts = _faction_member_counts(db)
    user_faction = _normalize_faction_key(user["faction"] if "faction" in user.keys() else None)
    faction_unlock_counts = _faction_unlock_counts(db, user["id"])
    faction_can_choose = bool((not user_faction) and _faction_unlock_ready(faction_unlock_counts))
    faction_week_scores = _faction_week_scores(db, week_key)
    weekly_faction_key = _element_to_faction(weekly_env["element"]) if weekly_env else None
    faction_score_rows = _faction_score_rows(
        faction_week_scores,
        member_counts,
        user_faction=user_faction,
        weekly_faction_key=weekly_faction_key,
    )
    prev_week_key = _faction_prev_week_key(week_key)
    prev_faction_result = _faction_week_result(db, prev_week_key)
    if not prev_faction_result:
        _ensure_faction_war_auto_close(db, week_key)
        prev_faction_result = _faction_week_result(db, prev_week_key)
    faction_buff_winner = _faction_effective_winner_for_week(db, week_key)
    faction_buff_active = bool(user_faction and faction_buff_winner and user_faction == faction_buff_winner)
    return render_template(
        "world.html",
        week_key=week_key,
        weekly_env=weekly_env,
        weekly_env_effect_lines=weekly_env_effect_lines,
        weekly_recommendation=weekly_recommendation,
        weekly_trends=weekly_trends,
        weekly_hot_areas=weekly_hot_areas,
        weekly_remaining_line=weekly_remaining_line,
        weekly_mvp=weekly_mvp,
        research_summary=research_summary,
        faction_labels=FACTION_LABELS,
        faction_emblems=FACTION_EMBLEMS,
        faction_score_rows=faction_score_rows,
        prev_week_key=prev_week_key,
        prev_faction_result=prev_faction_result,
        user_faction=user_faction,
        faction_can_choose=faction_can_choose,
        faction_unlock_progress_line=_faction_unlock_progress_line(faction_unlock_counts),
        faction_buff_winner=faction_buff_winner,
        faction_buff_active=faction_buff_active,
        weekly_faction_key=weekly_faction_key,
        element_label_map=ELEMENT_LABEL_MAP,
    )


@app.route("/records")
@login_required
def records_view():
    db = get_db()
    user = db.execute("SELECT id, is_admin FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not user:
        return redirect(url_for("login"))
    week_key = _world_week_key()
    weekly_record_groups = (
        _record_preview_rows(db, "weekly_explores", week_key=week_key, limit=3),
        _record_preview_rows(db, "weekly_bosses", week_key=week_key, limit=3),
        _record_preview_rows(db, "fastest", limit=3),
        _record_preview_rows(db, "durable", limit=3),
        _record_preview_rows(db, "burst", limit=3),
    )
    return render_template(
        "records.html",
        first_layer4_records=_first_explore_record_rows(
            db,
            [*LAYER4_SUBAREA_KEYS, LAYER4_FINAL_AREA_KEY],
            user_row=user,
        ),
        first_layer5_records=_first_explore_record_rows(
            db,
            [*LAYER5_SUBAREA_KEYS, LAYER5_FINAL_AREA_KEY],
            user_row=user,
        ),
        first_boss_records=_first_boss_record_rows(db, user_row=user),
        first_evolve_records=_first_evolve_record_rows(db),
        weekly_record_groups=weekly_record_groups,
        showcase_highlights=_record_showcase_highlights(db, user["id"]),
        week_key=week_key,
    )


@app.route("/comms")
@login_required
def comms():
    db = get_db()
    user = db.execute("SELECT id FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not user:
        return redirect(url_for("login"))
    personal_items = _personal_log_items(db, int(user["id"]), limit=5)
    active_user_count = count_active_users(
        db,
        window_minutes=USER_PRESENCE_ACTIVE_WINDOW_MINUTES,
    )
    room_participant_count = _chat_recent_participant_count(
        db,
        [room["key"] for room in COMM_ROOM_DEFS],
        window_minutes=COMM_ROOM_ACTIVITY_WINDOW_MINUTES,
    )
    sections = [
        {
            "title": "世界ログ",
            "summary": "世界の動きや、他のロボ使いの声がここに流れます。",
            "status": "稼働中",
            "href": url_for("comms_world"),
            "meta": (
                f"直近 {COMM_WORLD_TIMELINE_LIMIT} 件 / "
                f"{COMM_AUTO_REFRESH_SECONDS} 秒ごと自動更新 / "
                f"{_active_users_summary_line(active_user_count, window_minutes=USER_PRESENCE_ACTIVE_WINDOW_MINUTES)}"
            ),
        },
        {
            "title": "会議室",
            "summary": "ロボ使いたちが集まって話せる場所です。",
            "status": "稼働中",
            "href": url_for("comms_rooms"),
            "meta": (
                "全体会議室 / 初心者相談室 / フィードバック / "
                f"{_room_activity_summary_line(room_participant_count, window_minutes=COMM_ROOM_ACTIVITY_WINDOW_MINUTES)}"
            ),
        },
        {
            "title": "陣営通信",
            "summary": "同じ陣営の仲間と話せる通信です。いまは準備中です。",
            "status": "準備中",
            "href": url_for("comms_faction"),
            "meta": "開放までのあいだは世界ログと会議室を利用",
        },
        {
            "title": "個人ログ",
            "summary": "あなたのロボの成長や出来事がここに残ります。",
            "status": "稼働中",
            "href": url_for("comms_personal"),
            "meta": f"直近 {len(personal_items)} 件を表示中",
        },
    ]
    return render_template("comms.html", sections=sections, message=session.pop("message", None))


@app.route("/comms/world", methods=["GET", "POST"])
@login_required
def comms_world():
    db = get_db()
    user = db.execute("SELECT id, is_admin FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not user:
        return redirect(url_for("login"))
    if request.method == "POST":
        return _submit_chat_message(
            db,
            user_id=int(user["id"]),
            username=session.get("username", "unknown"),
            room_key=COMM_WORLD_ROOM_KEY,
            surface="comms_world",
        )
    items = _world_timeline_items(
        db,
        limit=COMM_WORLD_TIMELINE_LIMIT,
        is_admin=bool(int(user["is_admin"] or 0) == 1),
    )
    active_user_count = count_active_users(
        db,
        window_minutes=USER_PRESENCE_ACTIVE_WINDOW_MINUTES,
    )
    return render_template(
        "comms_world.html",
        items=items,
        world_settings=_chat_room_settings(COMM_WORLD_ROOM_KEY),
        auto_refresh_seconds=COMM_AUTO_REFRESH_SECONDS,
        active_user_line=_active_users_summary_line(
            active_user_count,
            window_minutes=USER_PRESENCE_ACTIVE_WINDOW_MINUTES,
        ),
        message=session.pop("message", None),
    )


@app.route("/comms/rooms", methods=["GET", "POST"])
@login_required
def comms_rooms():
    db = get_db()
    user = db.execute("SELECT id FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not user:
        return redirect(url_for("login"))
    selected_room_key = _chat_normalize_room_key(request.values.get("room"), allow_world=False) or COMM_ROOM_DEFS[0]["key"]
    if request.method == "POST":
        selected_room_key = _chat_normalize_room_key(request.form.get("room_key"), allow_world=False) or selected_room_key
        return _submit_chat_message(
            db,
            user_id=int(user["id"]),
            username=session.get("username", "unknown"),
            room_key=selected_room_key,
            surface="comms_room",
        )
    room_activity_counts_by_key = {
        room["key"]: _chat_room_recent_participant_count(
            db,
            room["key"],
            window_minutes=COMM_ROOM_ACTIVITY_WINDOW_MINUTES,
        )
        for room in COMM_ROOM_DEFS
    }
    return render_template(
        "comms_rooms.html",
        room_defs=COMM_ROOM_DEFS,
        selected_room_key=selected_room_key,
        selected_room=COMM_ROOM_DEF_MAP[selected_room_key],
        room_items=_room_message_items(db, selected_room_key, limit=COMM_ROOM_TIMELINE_LIMIT),
        room_settings=_chat_room_settings(selected_room_key),
        auto_refresh_seconds=COMM_AUTO_REFRESH_SECONDS,
        room_activity_counts_by_key=room_activity_counts_by_key,
        room_activity_line=_room_activity_summary_line(
            room_activity_counts_by_key.get(selected_room_key, 0),
            window_minutes=COMM_ROOM_ACTIVITY_WINDOW_MINUTES,
        ),
        message=session.pop("message", None),
    )


@app.route("/comms/faction")
@login_required
def comms_faction():
    return render_template("comms_faction.html", message=session.pop("message", None))


@app.route("/comms/personal")
@login_required
def comms_personal():
    db = get_db()
    user = db.execute("SELECT id FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not user:
        return redirect(url_for("login"))
    return render_template(
        "comms_personal.html",
        items=_personal_log_items(db, int(user["id"]), limit=COMM_PERSONAL_LOG_LIMIT),
        message=session.pop("message", None),
    )


@app.route("/map")
@login_required
def map_view():
    db = get_db()
    user = db.execute(
        "SELECT id, wins, is_admin, layer2_unlocked, max_unlocked_layer FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()
    streaks = _load_user_area_streaks(db, user["id"]) if user else {}
    nodes = _build_map_nodes(user, area_streaks=streaks, db=db)
    locked_layers = _locked_layer_lines(user, db=db)
    return render_template(
        "map.html",
        nodes=nodes,
        locked_layers=locked_layers,
        stage_modifiers_enabled=STAGE_MODIFIERS_ENABLED,
        max_unlocked_layer=_visible_user_max_unlocked_layer(user, db=db),
        wins_total=int(user["wins"] if user else 0),
        message=session.pop("message", None),
    )


@app.route("/feed")
@login_required
def feed():
    db = get_db()
    user = db.execute("SELECT is_admin FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    is_admin_user = bool(user and int(user["is_admin"] or 0) == 1)
    type_filter = (request.args.get("type") or "").strip().lower()
    user_id_raw = (request.args.get("user_id") or "").strip()
    user_id_filter = int(user_id_raw) if user_id_raw.isdigit() else None
    if type_filter == "weekly" and not is_admin_user:
        type_filter = ""
    cards = _fetch_feed_cards(
        db,
        type_filter=type_filter,
        user_id_filter=user_id_filter,
        limit=30,
        is_admin=is_admin_user,
    )
    return render_template(
        "feed.html",
        cards=cards,
        selected_type=type_filter,
        selected_user_id=user_id_raw,
        is_admin=is_admin_user,
    )


@app.route("/click", methods=["POST"])
@login_required
def click():
    db = get_db()
    user_id = session["user_id"]
    user = db.execute("SELECT click_power FROM users WHERE id = ?", (user_id,)).fetchone()
    now = time.time()
    last = session.get("last_click_at", 0)
    combo = session.get("combo", 0)
    if now - last <= 1.2:
        combo += 1
    else:
        combo = 1
    session["combo"] = combo
    session["last_click_at"] = now
    db.execute(
        "UPDATE users SET coins = coins + ?, total_clicks = total_clicks + 1 WHERE id = ?",
        (user["click_power"], user_id),
    )
    audit_log(
        db,
        AUDIT_EVENT_TYPES["COIN_DELTA"],
        user_id=user_id,
        request_id=getattr(g, "request_id", None),
        action_key="click",
        delta_coins=int(user["click_power"]),
        payload={
            "source": "click",
            "click_power": int(user["click_power"]),
            "gain": int(user["click_power"]),
            "combo": int(combo),
        },
        ip=request.remote_addr,
    )
    db.commit()
    session["message"] = f"稼働報酬: +{user['click_power']} コイン / 連携 x{combo}"
    return redirect(url_for("home"))


@app.route("/upgrade", methods=["POST"])
@login_required
def upgrade():
    db = get_db()
    user_id = session["user_id"]
    user = db.execute(
        "SELECT coins, click_power FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    cost = max(10, user["click_power"] * 10)
    if user["coins"] < cost:
        session["message"] = "コインが足りません。"
        return redirect(url_for("home"))
    db.execute(
        "UPDATE users SET coins = coins - ?, click_power = click_power + 1 WHERE id = ?",
        (cost, user_id),
    )
    db.commit()
    session["message"] = "クリックパワーが上昇！"
    return redirect(url_for("home"))


@app.route("/chat", methods=["POST"])
@login_required
def chat():
    db = get_db()
    return _submit_chat_message(
        db,
        user_id=int(session["user_id"]),
        username=session.get("username", "unknown"),
        room_key=COMM_WORLD_ROOM_KEY,
        surface="home_social_log",
    )


@app.route("/post", methods=["POST"])
@login_required
def post():
    db = get_db()
    title = request.form.get("title", "").strip()[:60]
    body = request.form.get("body", "").strip()[:300]
    if not title or not body:
        session["message"] = "投稿はタイトルと本文が必要です。"
        return redirect(url_for("home"))
    db.execute(
        "INSERT INTO posts (user_id, username, title, body, created_at) VALUES (?, ?, ?, ?, ?)",
        (session["user_id"], session["username"], title, body, now_str()),
    )
    db.commit()
    return redirect(url_for("home"))


@app.route("/milestone/claim", methods=["POST"])
@login_required
def milestone_claim():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    _ensure_qol_entitlement(db, user["id"])
    milestone_key = request.form.get("milestone_key", "").strip()
    robot_name = request.form.get("robot_name", "").strip()
    if not milestone_key or not robot_name:
        session["message"] = "受取にはロボ名の入力が必要です。"
        return redirect(url_for("home"))
    m = db.execute(
        "SELECT * FROM robot_milestones WHERE milestone_key = ? AND active = 1",
        (milestone_key,),
    ).fetchone()
    if not m:
        session["message"] = "無効なマイルストーンです。"
        return redirect(url_for("home"))
    claimed = db.execute(
        "SELECT 1 FROM user_milestone_claims WHERE user_id = ? AND milestone_key = ?",
        (user["id"], milestone_key),
    ).fetchone()
    if claimed:
        session["message"] = "このマイルストーンは受取済みです。"
        return redirect(url_for("home"))
    metric_value = user[m["metric"]] if m["metric"] in user.keys() else 0
    if metric_value < m["threshold_value"]:
        session["message"] = "受取条件を満たしていません。"
        return redirect(url_for("home"))
    limits = _effective_limits(db, user)
    instance_count = db.execute(
        "SELECT COUNT(*) AS c FROM robot_instances WHERE user_id = ? AND status != 'decomposed'",
        (user["id"],),
    ).fetchone()["c"]
    if instance_count >= limits["robot_slots"]:
        session["message"] = "保存枠が上限です。分解して枠を空けてください。"
        return redirect(url_for("home"))
    instance_id = _create_robot_instance(
        db,
        user["id"],
        robot_name,
        m["reward_head_key"],
        m["reward_r_arm_key"],
        m["reward_l_arm_key"],
        m["reward_legs_key"],
    )
    db.execute(
        """
        INSERT INTO user_milestone_claims (user_id, milestone_key, robot_instance_id, claimed_at)
        VALUES (?, ?, ?, ?)
        """,
        (user["id"], milestone_key, instance_id, int(time.time())),
    )
    db.commit()
    session["message"] = "完成ロボを受け取りました。開発支援のQoL拡張で保存枠を増やせます。"
    return redirect(url_for("home"))


@app.route("/parts/discard", methods=["POST"])
@login_required
def parts_discard():
    db = get_db()
    instance_ids = request.form.getlist("instance_ids")
    valid_instance_ids = [pid for pid in instance_ids if pid.isdigit()]
    if valid_instance_ids:
        placeholders = ",".join(["?"] * len(valid_instance_ids))
        cur = db.execute(
            f"DELETE FROM part_instances WHERE user_id = ? AND status = 'inventory' AND id IN ({placeholders})",
            [session["user_id"], *valid_instance_ids],
        )
        db.commit()
        session["message"] = f"{cur.rowcount} 件の個体パーツを破棄しました。"
        return redirect(url_for("parts"))

    part_keys = [k.strip() for k in request.form.getlist("part_keys") if k.strip()]
    if part_keys:
        placeholders = ",".join(["?"] * len(part_keys))
        cur = db.execute(
            f"DELETE FROM user_parts_inventory WHERE user_id = ? AND part_key IN ({placeholders})",
            [session["user_id"], *part_keys],
        )
        db.commit()
        session["message"] = f"{cur.rowcount} 件の保管パーツを整理しました。"
        return redirect(url_for("parts"))

    part_ids = request.form.getlist("part_ids")
    single_id = request.form.get("part_id")
    if single_id:
        part_ids.append(single_id)
    confirm = request.form.get("confirm")
    if confirm != "yes":
        session["message"] = "破棄確認が必要です。"
        return redirect(url_for("parts"))
    valid_ids = [pid for pid in part_ids if pid.isdigit()]
    if not valid_ids:
        session["message"] = "破棄対象が選択されていません。"
        return redirect(url_for("parts"))
    placeholders = ",".join(["?"] * len(valid_ids))
    cur = db.execute(
        f"DELETE FROM user_parts_inventory WHERE user_id = ? AND id IN ({placeholders})",
        [session["user_id"], *valid_ids],
    )
    db.commit()
    session["message"] = f"{cur.rowcount} 件のパーツを破棄しました。"
    return redirect(url_for("parts"))


@app.route("/parts/restore", methods=["POST"])
@login_required
def parts_restore():
    db = get_db()
    user_id = int(session["user_id"])
    selected_part_type = _normalize_part_type_filter(request.form.get("part_type"))
    redirect_params = {"part_type": selected_part_type} if selected_part_type else {}
    overflow_instance_ids = [pid for pid in request.form.getlist("overflow_instance_ids") if pid.isdigit()]
    if not overflow_instance_ids:
        session["message"] = "所持へ戻す保管個体を選択してください。"
        return redirect(url_for("parts", **redirect_params))

    user_row = db.execute(
        "SELECT id, part_inventory_limit FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    remaining = _inventory_space_remaining(db, user_id, user_row=user_row)
    if remaining <= 0:
        session["message"] = "所持枠がいっぱいです。先に所持中パーツを整理してください。"
        return redirect(url_for("parts", **redirect_params))

    placeholders = ",".join(["?"] * len(overflow_instance_ids))
    rows = db.execute(
        f"""
        SELECT id
        FROM part_instances
        WHERE user_id = ? AND status = 'overflow' AND id IN ({placeholders})
        ORDER BY id ASC
        """,
        [user_id, *[int(pid) for pid in overflow_instance_ids]],
    ).fetchall()
    if not rows:
        session["message"] = "戻せる保管個体が見つかりませんでした。"
        return redirect(url_for("parts", **redirect_params))

    restored = 0
    for row in rows:
        if restored >= remaining:
            break
        cur = db.execute(
            "UPDATE part_instances SET status = 'inventory', updated_at = datetime('now') WHERE id = ? AND user_id = ? AND status = 'overflow'",
            (int(row["id"]), user_id),
        )
        restored += int(cur.rowcount or 0)
    db.commit()

    total_rows = len(rows)
    if restored <= 0:
        session["message"] = "所持枠が足りず、保管個体を戻せませんでした。"
    elif restored < total_rows:
        session["message"] = f"{restored} 件を所持へ戻しました。残り {total_rows - restored} 件は保管のままです。"
    else:
        session["message"] = f"{restored} 件を所持へ戻しました。"
    return redirect(url_for("parts", **redirect_params))


def _ensure_battle_state(db, user_id):
    state = db.execute("SELECT * FROM battle_state WHERE user_id = ?", (user_id,)).fetchone()
    if state is None or state["active"] == 0:
        enemy_name = random.choice(["MECHA-ALPHA", "MECHA-BETA", "MECHA-GAMMA", "MECHA-DELTA"])
        enemy_hp = 5
        last_action_at = 0
        if state is None:
            db.execute(
                "INSERT INTO battle_state (user_id, enemy_name, enemy_hp, last_action_at, active) VALUES (?, ?, ?, ?, ?)",
                (user_id, enemy_name, enemy_hp, last_action_at, 1),
            )
        else:
            db.execute(
                "UPDATE battle_state SET enemy_name = ?, enemy_hp = ?, last_action_at = ?, active = 1 WHERE user_id = ?",
                (enemy_name, enemy_hp, last_action_at, user_id),
            )
        db.commit()
        session["battle_log"] = [f"新しい敵 {enemy_name} が現れた！"]
        session["battle_log_entries"] = []
    return db.execute("SELECT * FROM battle_state WHERE user_id = ?", (user_id,)).fetchone()


def _select_main_robot(db, user_id):
    row = db.execute(
        """
            SELECT ri.id, ri.name, ri.personality, ri.composed_image_path, ri.icon_32_path, ri.updated_at, ri.style_key, ri.style_stats_json
            FROM user_showcase us
            JOIN robot_instances ri ON ri.id = us.robot_instance_id
            WHERE us.user_id = ? AND ri.status = 'active'
            ORDER BY us.slot_no ASC
            LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    if row:
        return _refresh_robot_instance_render_assets(db, row, log_label="select_main_robot")
    row = db.execute(
        """
        SELECT id, name, personality, composed_image_path, icon_32_path, updated_at, style_key, style_stats_json
        FROM robot_instances
        WHERE user_id = ? AND status = 'active'
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    if row:
        return _refresh_robot_instance_render_assets(db, row, log_label="select_main_robot")
    return None


def _get_active_robot(db, user_id):
    active_id_row = db.execute("SELECT active_robot_id FROM users WHERE id = ?", (user_id,)).fetchone()
    active_id = active_id_row["active_robot_id"] if active_id_row else None
    if active_id:
        row = db.execute(
            """
            SELECT ri.id, ri.name, ri.personality, ri.composed_image_path, ri.icon_32_path, ri.combat_mode, ri.updated_at, ri.style_key, ri.style_stats_json
            FROM robot_instances ri
            WHERE ri.id = ? AND ri.user_id = ? AND ri.status = 'active'
            """,
            (active_id, user_id),
        ).fetchone()
        if row:
            return _refresh_robot_instance_render_assets(db, row, log_label="get_active_robot")
    return None


def _select_battle_narrator(db, user_id):
    active_robot = _get_active_robot(db, user_id)
    if active_robot:
        return {
            "name": active_robot["name"],
            "personality": active_robot["personality"] or "silent",
        }
    main_robot = _select_main_robot(db, user_id)
    if main_robot:
        return {
            "name": main_robot["name"],
            "personality": main_robot["personality"] or "silent",
        }
    return {"name": "探索機", "personality": "analyst"}


def _add_robot_if_lucky(db, user_id):
    if random.random() < 0.5:
        rarity = _roll_rarity()
        base = _get_random_robot_by_rarity(db, rarity)
        if base is None:
            base = db.execute("SELECT * FROM robots_master ORDER BY RANDOM() LIMIT 1").fetchone()
        if base is None:
            return False, None
        db.execute(
            "INSERT INTO user_robots (user_id, head, right_arm, left_arm, legs, obtained_at, master_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                base["head"],
                base["right_arm"],
                base["left_arm"],
                base["legs"],
                int(time.time()),
                base["id"],
            ),
        )
        db.commit()
        return True, base
    return False, None


def _roll_rarity():
    r = random.random()
    if r < 0.60:
        return "N"
    if r < 0.90:
        return "R"
    if r < 0.99:
        return "SR"
    if r < 0.999:
        return "SSR"
    return "UR"


def _get_random_robot_by_rarity(db, rarity):
    return db.execute(
        "SELECT * FROM robots_master WHERE rarity = ? ORDER BY RANDOM() LIMIT 1", (rarity,)
    ).fetchone()


def _append_battle_entry(entry):
    entries = session.get("battle_log_entries", [])
    entries.append(entry)
    session["battle_log_entries"] = entries[-40:]
    session["battle_log"] = entry["lines"]


def _battle_log_entries():
    return session.get("battle_log_entries", [])


def _perform_battle_attack(db, user_id, user, state, now):
    if user["is_admin"] != 1 and now - state["last_action_at"] < 20:
        wait = 20 - (now - state["last_action_at"])
        return {"ok": False, "message": f"次の行動まであと {wait} 秒"}

    narrator = _select_battle_narrator(db, user_id)
    base_atk = 1 + max(0, user["click_power"] // 2)
    rand = random.randint(-1, 1)
    damage = max(1, base_atk - 1 + rand)
    new_hp = max(0, state["enemy_hp"] - damage)
    db.execute(
        "UPDATE battle_state SET enemy_hp = ?, last_action_at = ? WHERE user_id = ?",
        (new_hp, now, user_id),
    )
    drop_labels = []
    reward_coin = 0
    reward_exp = 0
    outcome = "lose"
    message = None
    if new_hp == 0:
        reward_coin = 1
        reward_exp = 2
        outcome = "win"
        db.execute(
            "UPDATE users SET coins = coins + 1, wins = wins + 1 WHERE id = ?",
            (user_id,),
        )
        part_drop = _add_part_drop(db, user_id, source="battle_drop")
        if part_drop:
            label_suffix = "（保管）" if str(part_drop.get("storage_status") or "").strip().lower() == "overflow" else ""
            drop_labels.append(f"{part_drop['part_type']} {part_drop['part_key']}{label_suffix}")
            if label_suffix:
                message = "所持がいっぱいだったため、戦利品は保管へ送りました。"
        got_robot, new_robot = _add_robot_if_lucky(db, user_id)
        if got_robot and new_robot is not None:
            session["new_robot"] = {
                "name": new_robot["name"],
                "rarity": new_robot["rarity"],
            }
            db.execute(
                "INSERT INTO chat_messages (user_id, username, message, created_at) VALUES (?, ?, ?, ?)",
                (
                    user_id,
                    "SYSTEM",
                    f"{session['username']} が {new_robot['rarity']} {new_robot['name']} を入手！",
                    now_str(),
                ),
            )
        db.execute(
            "UPDATE battle_state SET active = 0, enemy_name = '', enemy_hp = 0 WHERE user_id = ?",
            (user_id,),
        )
    lines = generate_exploration_log(
        narrator["name"],
        narrator["personality"],
        state["enemy_name"],
        outcome,
        reward_coin=reward_coin,
        reward_exp=reward_exp,
        dropped_parts=drop_labels,
    )
    db.commit()
    state_after = db.execute("SELECT * FROM battle_state WHERE user_id = ?", (user_id,)).fetchone()
    entry = {
        "timestamp": now_str(),
        "enemy_name": state["enemy_name"],
        "robot_name": narrator["name"],
        "personality": narrator["personality"],
        "lines": lines,
    }
    return {
        "ok": True,
        "message": message,
        "entry": entry,
        "state": state_after,
    }


@app.template_filter("dt")
def format_ts(ts):
    if not ts:
        return "-"
    if isinstance(ts, str):
        # Keep legacy string timestamps readable as-is (e.g. "2026-02-12 11:00:00").
        if "-" in ts and ":" in ts:
            return ts[:16]
        if ts.isdigit():
            ts = int(ts)
        else:
            return ts
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(int(ts)))


@app.route("/battle", methods=["GET", "POST"])
@login_required
def battle():
    db = get_db()
    user_id = session["user_id"]
    user = db.execute("SELECT is_admin, click_power, battle_log_mode FROM users WHERE id = ?", (user_id,)).fetchone()
    battle_log_mode = _battle_log_mode_for_user(user)
    requested_robot_id = request.args.get("robot_id", "").strip()
    if requested_robot_id.isdigit():
        target = db.execute(
            "SELECT id FROM robot_instances WHERE id = ? AND user_id = ? AND status = 'active'",
            (int(requested_robot_id), user_id),
        ).fetchone()
        if target:
            db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (int(requested_robot_id), user_id))
            db.commit()
    state = _ensure_battle_state(db, user_id)
    active_robot = _get_active_robot(db, user_id)
    no_active_robot = active_robot is None

    message = None
    if no_active_robot:
        message = "ロボが未登録です。編成して登録してください。"
    if request.method == "POST":
        action = request.form.get("action")
        now = _now_ts()
        if no_active_robot:
            message = "ロボが未登録です。/build で編成して完成登録してください。"
        elif action == "attack":
            result = _perform_battle_attack(db, user_id, user, state, now)
            if result["ok"]:
                _append_battle_entry(result["entry"])
                message = result["message"]
            else:
                message = result["message"]
        elif action == "defend":
            if user["is_admin"] != 1 and now - state["last_action_at"] < 20:
                wait = 20 - (now - state["last_action_at"])
                message = f"次の行動まであと {wait} 秒"
            else:
                db.execute(
                    "UPDATE battle_state SET last_action_at = ? WHERE user_id = ?",
                    (now, user_id),
                )
                db.commit()
                _append_battle_entry(
                    {
                        "timestamp": now_str(),
                        "enemy_name": state["enemy_name"],
                        "robot_name": "防御行動",
                        "personality": "-",
                        "lines": ["防御した！"],
                    }
                )
        elif action == "escape":
            if user["is_admin"] != 1 and now - state["last_action_at"] < 20:
                wait = 20 - (now - state["last_action_at"])
                message = f"次の行動まであと {wait} 秒"
            else:
                db.execute(
                    "UPDATE battle_state SET active = 0, enemy_name = '', enemy_hp = 0, last_action_at = ? WHERE user_id = ?",
                    (now, user_id),
                )
                db.commit()
                _append_battle_entry(
                    {
                        "timestamp": now_str(),
                        "enemy_name": state["enemy_name"],
                        "robot_name": "撤退行動",
                        "personality": "-",
                        "lines": ["逃走した… 戦闘終了"],
                    }
                )

        if action == "escape":
            return redirect(url_for("battle"))

    state = db.execute("SELECT * FROM battle_state WHERE user_id = ?", (user_id,)).fetchone()
    new_robot = session.pop("new_robot", None)
    return render_template(
        "battle.html",
        state=state,
        log=session.get("battle_log", []),
        log_entries=_battle_log_entries(),
        message=message,
        new_robot=new_robot,
        explore_mode=False,
        explore_area_key=None,
        explore_area_label=None,
        active_robot=active_robot,
        no_active_robot=no_active_robot,
        battle_log_mode=battle_log_mode,
        battle_ritual_overlay_enabled=BATTLE_RITUAL_OVERLAY_ENABLED,
    )


@app.route("/battle/attack_async", methods=["POST"])
@login_required
def battle_attack_async():
    db = get_db()
    user_id = session["user_id"]
    user = db.execute("SELECT is_admin, click_power FROM users WHERE id = ?", (user_id,)).fetchone()
    state = _ensure_battle_state(db, user_id)
    result = _perform_battle_attack(db, user_id, user, state, int(time.time()))
    state_after = db.execute("SELECT * FROM battle_state WHERE user_id = ?", (user_id,)).fetchone()
    if not result["ok"]:
        return jsonify(
            {
                "ok": False,
                "message": result["message"],
                "html_log": "",
                "html_status": render_template("partials/_battle_status.html", state=state_after),
            }
        )

    _append_battle_entry(result["entry"])
    return jsonify(
        {
            "ok": True,
            "message": result["message"],
            "html_log": render_template("partials/_battle_log_entry.html", entry=result["entry"]),
            "html_status": render_template("partials/_battle_status.html", state=result["state"]),
        }
    )


@app.route("/explore", methods=["POST"])
@login_required
def explore():
    db = get_db()
    user_id = session["user_id"]
    request_id = getattr(g, "request_id", None) or str(uuid.uuid4())
    area_key = (request.form.get("area_key") or "").strip()
    battle_debug = (request.args.get("debug") or "").strip() == "1"
    boss_enter_requested = (request.form.get("boss_enter") or "").strip().lower() in {"1", "true", "on", "yes"}
    area = next((a for a in EXPLORE_AREAS if a["key"] == area_key), None)
    if area is None:
        session["message"] = "探索先が不正です。"
        return redirect(url_for("home"))
    user = db.execute(
        """
        SELECT id, is_admin, click_power, wins, battle_log_mode,
               boss_meter_explore_l1, boss_meter_win_l1, layer2_unlocked, max_unlocked_layer, created_at,
               explore_boost_until,
               last_explore_area_key
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()
    user_is_main_admin = _is_main_admin_user_id(db, user_id)
    battle_log_mode = _battle_log_mode_for_user(user)
    if not _area_visible_for_viewer(db, area_key, user_row=user):
        session["message"] = "その探索先はまだ公開準備中です。"
        return redirect(url_for("home"))
    if not _is_area_unlocked(user, area_key, db=db):
        area_layer = _area_layer(area_key)
        if area_key in SPECIAL_EXPLORE_AREA_KEYS:
            session["message"] = f"その探索先は未解放です。{_special_area_unlock_reason(area_key)}"
        elif area_layer <= 1:
            session["message"] = "その探索先は未解放です。"
        else:
            session["message"] = f"その探索先は未解放です。第{area_layer - 1}層ボス撃破で解放"
        return redirect(url_for("home"))
    if str(user["last_explore_area_key"] or "").strip() != area_key:
        db.execute("UPDATE users SET last_explore_area_key = ? WHERE id = ?", (area_key, user_id))
        db.commit()
    if _get_active_robot(db, user_id) is None:
        session["message"] = "先にロボを編成しよう。/build で完成登録できます。"
        return redirect(url_for("build"))
    evolution_feature_unlocked = _evolution_feature_unlocked(db, user=user, user_id=user_id)

    now = _now_ts()
    ct_seconds = _explore_ct_seconds_for_user(user, now_ts=now)
    newbie_boost_active = _is_newbie_boost_active(user, now_ts=now)
    wait = _enforce_explore_cooldown_or_wait(db, user, user_id, now_ts=now)
    if wait > 0:
        return redirect(url_for("home"))
    audit_log(
        db,
        AUDIT_EVENT_TYPES["EXPLORE_START"],
        user_id=user_id,
        request_id=request_id,
        action_key="explore",
        payload={"area_key": area_key, "at": now, "newbie_boost": bool(newbie_boost_active), "ct_seconds": int(ct_seconds)},
        ip=request.remote_addr,
    )

    weekly_env = _world_current_environment(db)
    weekly_mode = _normalize_world_mode(weekly_env["mode"]) if weekly_env else "安定"
    active = _get_active_robot(db, user_id)
    robot_stats = _compute_robot_stats_for_instance(db, active["id"]) if active else None
    if not robot_stats:
        session["message"] = "アクティブロボの個体ステータスを取得できません。再編成後に探索してください。"
        return redirect(url_for("robots"))
    base_stats = robot_stats["stats"]
    player_atk_base = int(base_stats["atk"])
    player_def_base = int(base_stats["def"])
    player_spd = int(base_stats["spd"])
    player_acc_base = int(base_stats["acc"])
    player_cri = int(base_stats["cri"])
    player_max_hp_base = max(8, int(base_stats["hp"]))
    player_max_hp = player_max_hp_base
    stage_modifier = _stage_modifier_for_area(area_key, is_admin=(user["is_admin"] == 1))
    stage_modifier_line = f"ステージ補正: {_stage_modifier_summary_line(stage_modifier)}" if stage_modifier else None
    if stage_modifier:
        pm = stage_modifier["player_mult"]
        player_atk = _stat_mult_applied(player_atk_base, pm.get("atk", 1.0))
        player_def = _stat_mult_applied(player_def_base, pm.get("def", 1.0))
        player_acc = _stat_mult_applied(player_acc_base, pm.get("acc", 1.0))
    else:
        player_atk = player_atk_base
        player_def = player_def_base
        player_acc = player_acc_base
    player_archetype = (robot_stats.get("archetype") if robot_stats else None) or {"key": "none", "name_ja": "無印"}
    archetype_note = player_archetype.get("battle_note") if isinstance(player_archetype, dict) else None
    robot_style = (
        robot_stats.get("robot_style")
        if robot_stats and robot_stats.get("robot_style")
        else _robot_style_from_final_stats(base_stats)
    )
    combat_mode = _normalize_combat_mode(active["combat_mode"] if active and "combat_mode" in active.keys() else "normal")
    build_type = "BERSERK" if combat_mode == "berserk" else _build_type_from_parts(robot_stats.get("parts") or [])
    player_damage_noise_range = _damage_noise_range_for_build_type(build_type)
    max_turns = EXPLORE_MAX_TURNS
    all_turn_logs = []
    reward_coin = 0
    reward_exp = 0
    reward_core = 0
    core_reward_sources = set()
    core_dropped_this_explore = False
    bonus_line = None
    drop_labels = []
    new_robot = None
    timeout_any = False
    world_bonus_notes = []
    bonus_events = {}
    spawned_bonus_applied = False
    promoted_drop_applied = False
    battle_results = []
    explore_submission_id = (request.form.get("explore_submission_id") or "").strip()
    battle_id = _battle_id_for_explore_submission(explore_submission_id)
    damage_taken_total = 0
    crit_finisher_kills = 0
    consecutive_bonus_applied = False
    suppressed_part_drop_count = 0
    overflow_part_drop_count = 0
    total_fights = 1
    if weekly_mode == "暴走" and random.random() < 0.25:
        total_fights = 2
        world_bonus_notes.append("世界状態ボーナス発動: 連戦が発生")
    if weekly_mode == "静穏":
        world_bonus_notes.append("世界状態ボーナス発動: 敗北時の修理費は0")

    area_boss_active = False
    area_boss_spawn_p = 0.0
    area_boss_pity_forced = False
    area_boss_streak_before = 0
    area_boss_enemy = None
    area_boss_reward = None
    unlocked_layer = None
    boss_unlock_line = None
    area_boss_attempt_before = None
    area_boss_attempt_after = None
    area_boss_legacy_mode = False
    area_boss_kind = "fixed"
    area_boss_template_id = None
    npc_analysis_line = None
    layer1_boss_hint_line = None
    layer1_boss_spawn_p = 0.0
    active_alert = _get_active_boss_alert(db, user_id, area_key, now_ts=now) if _area_supports_boss_alert(area_key) else None
    last_enemy_tendency_tag = None
    last_enemy_trait_label = None
    last_enemy_trait_desc = None
    last_enemy_variant_label = None
    if boss_enter_requested and _area_supports_boss_alert(area_key):
        if user_is_main_admin and _has_area_boss_candidates(db, area_key):
            area_boss_active = True
            total_fights = 1
            area_boss_enemy = _pick_layer_boss_enemy(db, area_key, weekly_env=weekly_env, rng=random)
            if area_boss_enemy is None:
                session["message"] = "この探索先には挑戦可能なボスがいません。"
                db.commit()
                return redirect(url_for("home"))
            area_boss_kind = str(area_boss_enemy.get("_boss_kind") or "fixed")
            area_boss_template_id = (
                int(area_boss_enemy.get("_npc_boss_template_id") or 0) if area_boss_kind == "npc" else None
            )
            area_boss_enemy_meta = _boss_type_meta(area_boss_enemy)
            area_boss_spawn_p = 1.0
            area_boss_streak_before = _ensure_user_boss_progress_row(db, user_id, area_key)
            audit_log(
                db,
                AUDIT_EVENT_TYPES["BOSS_ATTEMPT"],
                user_id=user_id,
                request_id=request_id,
                action_key="explore",
                entity_type=("npc_boss_template" if area_boss_kind == "npc" else "enemy"),
                entity_id=(
                    int(area_boss_enemy.get("_npc_boss_template_id") or 0)
                    if area_boss_kind == "npc"
                    else (int(area_boss_enemy["id"]) if "id" in area_boss_enemy.keys() and area_boss_enemy["id"] else None)
                ),
                payload={
                    "user_id": user_id,
                    "area_key": area_key,
                    "enemy_key": area_boss_enemy["key"] if "key" in area_boss_enemy.keys() else None,
                    "boss_type": (area_boss_enemy_meta["code"] if area_boss_enemy_meta else None),
                    "boss_kind": area_boss_kind,
                    "npc_boss_template_id": area_boss_template_id,
                    "source_robot_instance_id": area_boss_enemy.get("_source_robot_instance_id"),
                    "source_user_id": area_boss_enemy.get("_source_user_id"),
                    "source_faction": area_boss_enemy.get("_source_faction"),
                    "attempts_before": None,
                    "attempts_after": None,
                    "admin_direct": True,
                },
                ip=request.remote_addr,
            )
        elif not active_alert:
            session["message"] = "有効なボス警報がありません。探索で警報を引き当ててください。"
            db.commit()
            return redirect(url_for("home"))
        else:
            area_boss_active = True
            total_fights = 1
            area_boss_enemy = active_alert["enemy"]
            area_boss_kind = str(area_boss_enemy.get("_boss_kind") or "fixed")
            area_boss_template_id = (
                int(area_boss_enemy.get("_npc_boss_template_id") or 0) if area_boss_kind == "npc" else None
            )
            area_boss_enemy_meta = _boss_type_meta(area_boss_enemy)
            area_boss_spawn_p = float(AREA_BOSS_SPAWN_RATES.get(area_key, 0.0))
            area_boss_streak_before = _ensure_user_boss_progress_row(db, user_id, area_key)
            consume = _consume_boss_attempt(db, user_id, area_key, now_ts=now)
            area_boss_attempt_before = int(consume["before"])
            area_boss_attempt_after = int(consume["after"])
            audit_log(
                db,
                AUDIT_EVENT_TYPES["BOSS_ATTEMPT"],
                user_id=user_id,
                request_id=request_id,
                action_key="explore",
                entity_type=("npc_boss_template" if area_boss_kind == "npc" else "enemy"),
                entity_id=(
                    int(area_boss_enemy.get("_npc_boss_template_id") or 0)
                    if area_boss_kind == "npc"
                    else (int(area_boss_enemy["id"]) if "id" in area_boss_enemy.keys() and area_boss_enemy["id"] else None)
                ),
                payload={
                    "user_id": user_id,
                    "area_key": area_key,
                    "enemy_key": area_boss_enemy["key"] if "key" in area_boss_enemy.keys() else None,
                    "boss_type": (area_boss_enemy_meta["code"] if area_boss_enemy_meta else None),
                    "boss_kind": area_boss_kind,
                    "npc_boss_template_id": area_boss_template_id,
                    "source_robot_instance_id": area_boss_enemy.get("_source_robot_instance_id"),
                    "source_user_id": area_boss_enemy.get("_source_user_id"),
                    "source_faction": area_boss_enemy.get("_source_faction"),
                    "attempts_before": area_boss_attempt_before,
                    "attempts_after": area_boss_attempt_after,
                    "expires_at": int(active_alert["expires_at"]),
                },
                ip=request.remote_addr,
            )
    elif _area_supports_boss_alert(area_key) and _has_area_boss_candidates(db, area_key):
        if not active_alert:
            boss_roll = _area_boss_spawn_check(db, user_id, area_key, rng=random)
            area_boss_spawn_p = float(boss_roll["probability"])
            area_boss_pity_forced = bool(boss_roll["pity_forced"])
            area_boss_streak_before = int(boss_roll["streak_before"])
            if bool(boss_roll["spawn"]):
                picked = _pick_layer_boss_enemy(db, area_key, weekly_env=weekly_env, rng=random)
                if picked is not None:
                    picked_kind = str(picked.get("_boss_kind") or "fixed")
                    picked_template_id = int(picked.get("_npc_boss_template_id") or 0) if picked_kind == "npc" else None
                    picked_meta = _boss_type_meta(picked)
                    alert_state = _activate_boss_alert(
                        db,
                        user_id=user_id,
                        area_key=area_key,
                        enemy_id=int(picked.get("_alert_enemy_id") or picked["id"]),
                        now_ts=now,
                    )
                    audit_log(
                        db,
                        AUDIT_EVENT_TYPES["BOSS_ENCOUNTER"],
                        user_id=user_id,
                        request_id=request_id,
                        action_key="explore",
                        entity_type=("npc_boss_template" if picked_kind == "npc" else "enemy"),
                        entity_id=(
                            picked_template_id
                            if picked_kind == "npc"
                            else (int(picked["id"]) if "id" in picked.keys() and picked["id"] else None)
                        ),
                        payload={
                            "user_id": user_id,
                            "area_key": area_key,
                            "enemy_key": picked["key"] if "key" in picked.keys() else None,
                            "is_boss": True,
                            "boss_kind": picked_kind,
                            "npc_boss_template_id": picked_template_id,
                            "source_robot_instance_id": picked.get("_source_robot_instance_id"),
                            "source_user_id": picked.get("_source_user_id"),
                            "source_faction": picked.get("_source_faction"),
                            "area_label": _boss_area_label(area_key),
                            "enemy_name": picked["name_ja"] if "name_ja" in picked.keys() else "エリアボス",
                            "boss_type": (picked_meta["code"] if picked_meta else None),
                            "spawn_probability": float(area_boss_spawn_p),
                            "pity_forced": bool(area_boss_pity_forced),
                            "streak_before": int(area_boss_streak_before),
                            "alert_attempts_left": int(alert_state["attempts_left"]),
                            "alert_expires_at": int(alert_state["expires_at"]),
                        },
                        ip=request.remote_addr,
                    )
                    db.commit()
                    session["message"] = (
                        f"【ボス警報】{_boss_area_label(area_key)}で{picked['name_ja']}を検知。"
                        f"挑戦権{AREA_BOSS_ALERT_ATTEMPTS}回（約{AREA_BOSS_ALERT_MINUTES}分）"
                    )
                    return redirect(url_for("home"))
    build_type = "BERSERK" if combat_mode == "berserk" else _build_type_from_parts(robot_stats.get("parts") or [])
    player_damage_noise_range = _damage_noise_range_for_build_type(build_type)
    if build_type == "BERSERK":
        player_max_hp = max(1, int(math.floor(player_max_hp_base * 0.85)))
    explore_drop_budget_max = _explore_part_drop_budget(total_fights)
    explore_drop_budget_left = int(explore_drop_budget_max)

    last_enemy = None
    player_hp = player_max_hp
    final_outcome = "lose"
    for battle_no in range(1, total_fights + 1):
        if area_boss_active and battle_no == 1 and area_boss_enemy is not None:
            enemy = area_boss_enemy
        else:
            enemy = _pick_enemy_for_area(db, area_key, weekly_env=weekly_env)
        enemy = dict(enemy) if not isinstance(enemy, dict) else dict(enemy)
        if area_boss_active and battle_no == 1 and str(enemy.get("_boss_kind") or area_boss_kind) == "fixed":
            enemy = _apply_boss_type_modifiers(enemy)
        elif (not app.config.get("TESTING")) and area_key in MINI_BOSS_AREA_KEYS and random.random() < float(MINI_BOSS_SPAWN_RATE):
            enemy["hp"] = max(1, int(round(int(enemy.get("hp") or 1) * float(MINI_BOSS_HP_MULT))))
            enemy["atk"] = max(1, int(round(int(enemy.get("atk") or 1) * float(MINI_BOSS_ATK_MULT))))
            enemy["_variant_label"] = "強化個体"
        last_enemy = enemy
        enemy_name = enemy["name_ja"]
        enemy_tendency_tag = None
        if not (area_boss_active and battle_no == 1):
            enemy_tendency_tag = _enemy_tendency_tag(enemy)
        enemy_tendency_line = f"敵の特徴：{enemy_tendency_tag}" if enemy_tendency_tag else None
        last_enemy_tendency_tag = enemy_tendency_tag
        enemy_trait_key = _normalize_enemy_trait(enemy.get("trait") if isinstance(enemy, dict) else None)
        enemy_trait_label = _enemy_trait_label(enemy_trait_key)
        enemy_trait_desc = _enemy_trait_desc(enemy_trait_key)
        enemy_trait_line = (
            f"特性：{enemy_trait_label}（{enemy_trait_desc}）"
            if enemy_trait_label and enemy_trait_desc
            else (f"特性：{enemy_trait_label}" if enemy_trait_label else None)
        )
        last_enemy_trait_label = enemy_trait_label
        last_enemy_trait_desc = enemy_trait_desc
        enemy_variant_label = (enemy.get("_variant_label") or "").strip() if isinstance(enemy, dict) else ""
        last_enemy_variant_label = enemy_variant_label or None
        enemy_variant_line = f"個体識別：{enemy_variant_label}" if enemy_variant_label else None
        enemy_faction = (enemy["faction"] if "faction" in enemy.keys() and enemy["faction"] else "neutral").lower()
        enemy_tier = int(enemy["tier"]) if "tier" in enemy.keys() and enemy["tier"] else 1
        encounter_pool = ENCOUNTER_LOGS.get(enemy_faction, ENCOUNTER_LOGS["neutral"]).get(enemy_tier, ENCOUNTER_LOGS["neutral"][1])
        encounter_line = random.choice(encounter_pool).format(enemy_name=enemy_name)
        mid_pool = MID_LOGS_COMMON + MID_LOGS_FACTION.get(enemy_faction, MID_LOGS_FACTION["neutral"])
        mid_line = random.choice(mid_pool) if random.random() < 0.5 else None
        enemy_atk = int(enemy["atk"])
        enemy_def = int(enemy["def"])
        enemy_spd = int(enemy["spd"])
        enemy_acc = int(enemy["acc"])
        enemy_cri = int(enemy["cri"])
        enemy_max_hp = max(1, int(enemy["hp"]))
        if stage_modifier:
            em = stage_modifier["enemy_mult"]
            enemy_atk = _stat_mult_applied(enemy_atk, em.get("atk", 1.0))
            enemy_def = _stat_mult_applied(enemy_def, em.get("def", 1.0))
            enemy_spd = _stat_mult_applied(enemy_spd, em.get("spd", 1.0))
            enemy_acc = _stat_mult_applied(enemy_acc, em.get("acc", 1.0))
            enemy_cri = _stat_mult_applied(enemy_cri, em.get("cri", 1.0))
            enemy_max_hp = _stat_mult_applied(enemy_max_hp, em.get("hp", 1.0))
        crit_multiplier = float(enemy["_crit_multiplier"]) if "_crit_multiplier" in enemy.keys() else 1.5
        player_crit_multiplier = _player_crit_multiplier_for_build_type(crit_multiplier, build_type)
        build_profile_line = _build_profile_battle_line(
            build_type,
            player_damage_noise_range,
            player_crit_multiplier,
            crit_multiplier,
        )
        boss_type_line = None
        if area_boss_active and battle_no == 1:
            boss_type_label = enemy.get("_boss_type_label")
            if boss_type_label:
                boss_type_line = f"ボス種別：{boss_type_label}"
        if area_boss_active and battle_no == 1 and area_boss_legacy_mode:
            audit_log(
                db,
                AUDIT_EVENT_TYPES["BOSS_ENCOUNTER"],
                user_id=user_id,
                request_id=request_id,
                action_key="explore",
                entity_type="enemy",
                entity_id=(int(enemy["id"]) if "id" in enemy.keys() and enemy["id"] else None),
                payload={
                    "user_id": user_id,
                    "area_key": area_key,
                    "enemy_key": enemy["key"] if "key" in enemy.keys() else None,
                    "is_boss": True,
                    "reward_decor_asset_id": None,
                    "reward_decor_key": None,
                    "reward_decor_name": None,
                    "area_label": _boss_area_label(area_key),
                    "enemy_name": enemy_name,
                    "boss_type": enemy.get("_boss_type"),
                    "spawn_probability": float(area_boss_spawn_p),
                    "pity_forced": bool(area_boss_pity_forced),
                    "streak_before": int(area_boss_streak_before),
                    "legacy_mode": bool(area_boss_legacy_mode),
                },
                ip=request.remote_addr,
            )
        enemy_hp = enemy_max_hp
        if weekly_env and (enemy.get("element") or "").upper() == (weekly_env.get("element") or "").upper():
            spawned_bonus_applied = True
        # 序盤救済Aは「通常のtier1戦のみ」で有効。
        # tier2以上とボス戦では絶対に発動させない。
        relief_miss_enabled = (not (area_boss_active and battle_no == 1)) and (enemy_tier == 1)
        battle_timeout = False
        battle_logs = []
        player_miss_streak = 0
        berserk_triggered = False
        for turn in range(1, max_turns + 1):
            enemy_before = enemy_hp
            player_before = player_hp
            player_damage = 0
            enemy_damage = 0
            critical = False
            player_action = "攻撃"
            enemy_action = "攻撃"
            player_attack_note = None
            enemy_attack_note = None
            player_relief_line = None
            player_berserk_line = None
            enemy_trait_trigger_line = None
            enemy_trait_triggers = []
            player_skill = random.choice(["スラッシュ", "バースト", "ドライブ"])

            player_first = player_spd >= enemy_spd
            if player_first:
                force_player_hit = relief_miss_enabled and (player_miss_streak >= 2)
                player_effective_atk = player_atk
                if build_type == "BERSERK":
                    berserk_bonus = _berserk_attack_bonus(build_type, player_hp, player_max_hp)
                    player_effective_atk = max(1, int(round(player_atk * (1.0 + berserk_bonus))))
                    player_berserk_line = f"背水発動 +{int(round(berserk_bonus * 100))}% {_stat_label('hp')}: {player_hp}/{player_max_hp}"
                player_damage, critical, player_attack_detail = _resolve_attack_logged(
                    player_effective_atk,
                    player_acc,
                    player_cri,
                    enemy_def,
                    enemy_acc,
                    rng=random,
                    attacker_archetype=player_archetype,
                    defender_archetype=None,
                    attacker_is_first_striker=True,
                    crit_multiplier=player_crit_multiplier,
                    force_hit=force_player_hit,
                    damage_noise_range=player_damage_noise_range,
                )
                player_attack_note = _attack_note(player_action, player_damage, player_attack_detail, debug=battle_debug)
                player_missed = bool(player_attack_detail.get("miss")) or player_damage <= 0
                if force_player_hit:
                    # 強制ヒット消化後は必ずstreakを切ってループ発動を防ぐ。
                    player_miss_streak = 0
                else:
                    player_miss_streak = (player_miss_streak + 1) if player_missed else 0
                if force_player_hit and not player_missed:
                    player_relief_line = "救済: 連続MISSのため命中補正"
                raw_player_damage = int(player_damage)
                if enemy_trait_key == "heavy" and raw_player_damage > 0:
                    reduced_damage = max(1, int(math.floor(raw_player_damage * 0.85)))
                    if reduced_damage < raw_player_damage:
                        player_damage = reduced_damage
                        enemy_trait_triggers.append("特徴発動: 重装で被ダメージ軽減")
                if (
                    enemy_trait_key == "fast"
                    and (not bool(player_attack_detail.get("miss")))
                    and player_damage > 0
                    and random.random() < 0.12
                ):
                    player_damage = 0
                    enemy_trait_triggers.append("特徴発動: 高速機動で回避")
                enemy_hp = max(0, enemy_hp - player_damage)
                if enemy_hp == 0 and critical:
                    crit_finisher_kills += 1
                if enemy_hp > 0:
                    enemy_effective_atk = enemy_atk
                    if enemy_trait_key == "berserk" and enemy_hp * 2 <= enemy_max_hp:
                        enemy_effective_atk = max(1, int(round(enemy_atk * 1.2)))
                        if not berserk_triggered:
                            enemy_trait_triggers.append("特徴発動: 狂戦で攻撃上昇")
                            berserk_triggered = True
                    enemy_damage, _, enemy_attack_detail = _resolve_attack_logged(
                        enemy_effective_atk,
                        enemy_acc,
                        enemy_cri,
                        player_def,
                        player_acc,
                        rng=random,
                        attacker_archetype=None,
                        defender_archetype=player_archetype,
                        attacker_is_first_striker=False,
                        crit_multiplier=crit_multiplier,
                        damage_noise_range=None,
                    )
                    enemy_attack_note = _attack_note(enemy_action, enemy_damage, enemy_attack_detail, debug=battle_debug)
                    player_hp = max(0, player_hp - enemy_damage)
                    damage_taken_total += max(0, int(enemy_damage))
                    if enemy_trait_key == "unstable" and enemy_hp > 0 and random.random() < 0.35:
                        recoil = min(enemy_hp, max(1, int(math.ceil(enemy_effective_atk * 0.12))))
                        enemy_hp = max(0, enemy_hp - recoil)
                        enemy_trait_triggers.append(f"特徴発動: 不安定反動で{recoil}ダメージ")
                else:
                    enemy_action = "行動不能"
                    enemy_attack_note = _attack_note(enemy_action, enemy_damage, {}, debug=battle_debug)
            else:
                enemy_effective_atk = enemy_atk
                if enemy_trait_key == "berserk" and enemy_hp * 2 <= enemy_max_hp:
                    enemy_effective_atk = max(1, int(round(enemy_atk * 1.2)))
                    if not berserk_triggered:
                        enemy_trait_triggers.append("特徴発動: 狂戦で攻撃上昇")
                        berserk_triggered = True
                enemy_damage, _, enemy_attack_detail = _resolve_attack_logged(
                    enemy_effective_atk,
                    enemy_acc,
                    enemy_cri,
                    player_def,
                    player_acc,
                    rng=random,
                    attacker_archetype=None,
                    defender_archetype=player_archetype,
                    attacker_is_first_striker=True,
                    crit_multiplier=crit_multiplier,
                    damage_noise_range=None,
                )
                enemy_attack_note = _attack_note(enemy_action, enemy_damage, enemy_attack_detail, debug=battle_debug)
                player_hp = max(0, player_hp - enemy_damage)
                damage_taken_total += max(0, int(enemy_damage))
                if enemy_trait_key == "unstable" and enemy_hp > 0 and random.random() < 0.35:
                    recoil = min(enemy_hp, max(1, int(math.ceil(enemy_effective_atk * 0.12))))
                    enemy_hp = max(0, enemy_hp - recoil)
                    enemy_trait_triggers.append(f"特徴発動: 不安定反動で{recoil}ダメージ")
                if player_hp > 0 and enemy_hp > 0:
                    force_player_hit = relief_miss_enabled and (player_miss_streak >= 2)
                    player_effective_atk = player_atk
                    if build_type == "BERSERK":
                        berserk_bonus = _berserk_attack_bonus(build_type, player_hp, player_max_hp)
                        player_effective_atk = max(1, int(round(player_atk * (1.0 + berserk_bonus))))
                        player_berserk_line = f"背水発動 +{int(round(berserk_bonus * 100))}% {_stat_label('hp')}: {player_hp}/{player_max_hp}"
                    player_damage, critical, player_attack_detail = _resolve_attack_logged(
                        player_effective_atk,
                        player_acc,
                        player_cri,
                        enemy_def,
                        enemy_acc,
                        rng=random,
                        attacker_archetype=player_archetype,
                        defender_archetype=None,
                        attacker_is_first_striker=False,
                        crit_multiplier=player_crit_multiplier,
                        force_hit=force_player_hit,
                        damage_noise_range=player_damage_noise_range,
                    )
                    player_attack_note = _attack_note(player_action, player_damage, player_attack_detail, debug=battle_debug)
                    player_missed = bool(player_attack_detail.get("miss")) or player_damage <= 0
                    if force_player_hit:
                        # 強制ヒット消化後は必ずstreakを切ってループ発動を防ぐ。
                        player_miss_streak = 0
                    else:
                        player_miss_streak = (player_miss_streak + 1) if player_missed else 0
                    if force_player_hit and not player_missed:
                        player_relief_line = "救済: 連続MISSのため命中補正"
                    raw_player_damage = int(player_damage)
                    if enemy_trait_key == "heavy" and raw_player_damage > 0:
                        reduced_damage = max(1, int(math.floor(raw_player_damage * 0.85)))
                        if reduced_damage < raw_player_damage:
                            player_damage = reduced_damage
                            enemy_trait_triggers.append("特徴発動: 重装で被ダメージ軽減")
                    if (
                        enemy_trait_key == "fast"
                        and (not bool(player_attack_detail.get("miss")))
                        and player_damage > 0
                        and random.random() < 0.12
                    ):
                        player_damage = 0
                        enemy_trait_triggers.append("特徴発動: 高速機動で回避")
                    enemy_hp = max(0, enemy_hp - player_damage)
                    if enemy_hp == 0 and critical:
                        crit_finisher_kills += 1
                elif enemy_hp <= 0:
                    player_action = "追撃不要"
                    player_attack_note = _attack_note(player_action, player_damage, {}, debug=battle_debug)
                else:
                    player_action = "行動不能"
                    player_attack_note = _attack_note(player_action, player_damage, {}, debug=battle_debug)

            if enemy_trait_triggers:
                enemy_trait_trigger_line = " / ".join(enemy_trait_triggers)

            battle_logs.append(
                {
                    "turn": turn,
                    "battle_no": battle_no,
                    "premonition_line": layer1_boss_hint_line if turn == 1 and battle_no == 1 and layer1_boss_hint_line else None,
                    "encounter_line": encounter_line if turn == 1 else None,
                    "enemy_tendency_line": enemy_tendency_line if turn == 1 and enemy_tendency_line else None,
                    "enemy_variant_line": enemy_variant_line if turn == 1 and enemy_variant_line else None,
                    "enemy_trait_line": enemy_trait_line if turn == 1 and enemy_trait_line else None,
                    "archetype_line": archetype_note if turn == 1 and archetype_note else None,
                    "build_profile_line": build_profile_line if turn == 1 and battle_no == 1 else None,
                    "stage_modifier_line": stage_modifier_line if turn == 1 and battle_no == 1 and stage_modifier_line else None,
                    "boss_type_line": boss_type_line if turn == 1 and battle_no == 1 else None,
                    "mid_line": mid_line if turn == 1 and mid_line else None,
                    "player_action": player_action,
                    "enemy_action": enemy_action,
                    "enemy_before": enemy_before,
                    "enemy_after": enemy_hp,
                    "player_before": player_before,
                    "player_after": player_hp,
                    "player_damage": player_damage,
                    "enemy_damage": enemy_damage,
                    "critical": critical,
                    "player_skill": player_skill,
                    "player_max": player_max_hp,
                    "enemy_max": enemy_max_hp,
                    "player_attack_note": player_attack_note,
                    "enemy_attack_note": enemy_attack_note,
                    "enemy_trait_trigger_line": enemy_trait_trigger_line,
                    "player_relief_line": player_relief_line,
                    "player_berserk_line": player_berserk_line,
                }
            )
            if enemy_hp == 0 or player_hp == 0:
                break
        if enemy_hp > 0 and player_hp > 0 and len(battle_logs) >= max_turns:
            battle_timeout = True
        timeout_any = timeout_any or battle_timeout
        all_turn_logs.extend(battle_logs)

        if enemy_hp == 0:
            if area_boss_active and battle_no == 1:
                rewards = {"coin": 0, "drop_type": "boss_reward", "dropped_parts": [], "promotion_triggered": False}
                if area_boss_kind == "npc":
                    area_boss_reward = {
                        "reward_missing": False,
                        "decor_asset_id": None,
                        "decor_key": None,
                        "decor_name": None,
                        "decor_image_path": None,
                        "granted": False,
                        "reward_type": "core" if evolution_feature_unlocked else "locked",
                    }
                    if evolution_feature_unlocked:
                        granted_core = _grant_player_core(db, user_id, EVOLUTION_CORE_KEY, qty=1)
                        if granted_core > 0:
                            core_dropped_this_explore = True
                            reward_core += int(granted_core)
                            core_reward_sources.add("npc_boss")
                            world_bonus_notes.append("✨ NPCボス撃破報酬: 進化コア ×1")
                            if battle_logs:
                                battle_logs[-1]["core_drop_line"] = "✨ NPCボス撃破報酬: 進化コア ×1"
                            audit_log(
                                db,
                                AUDIT_EVENT_TYPES["CORE_DROP"],
                                user_id=user_id,
                                request_id=request_id,
                                action_key="explore",
                                entity_type="core",
                                entity_id=None,
                                delta_count=int(granted_core),
                                payload={
                                    "core_key": EVOLUTION_CORE_KEY,
                                    "core_name": "進化コア",
                                    "quantity": int(granted_core),
                                    "area_key": area_key,
                                    "enemy_key": (enemy.get("key") if isinstance(enemy, dict) else None),
                                    "source": "npc_boss",
                                    "npc_boss_template_id": area_boss_template_id,
                                },
                                ip=request.remote_addr,
                            )
                else:
                    area_boss_reward = _grant_boss_decor_reward(
                        db,
                        user_id=user_id,
                        area_key=area_key,
                    )
                this_coin = 0
            else:
                rewards = _roll_battle_rewards(
                    db,
                    user_id,
                    int(enemy["tier"]) if "tier" in enemy.keys() else 1,
                    weekly_env=weekly_env,
                    enemy_element=(enemy["element"] if "element" in enemy.keys() else None),
                    announce_username=session.get("username"),
                    part_drop_budget=explore_drop_budget_left,
                    area_key=area_key,
                )
                this_coin = int(rewards["coin"])
                if weekly_mode == "活性":
                    this_coin += 1
            reward_coin += this_coin
            reward_exp += 2
            promoted_drop_applied = promoted_drop_applied or bool(rewards.get("promotion_triggered"))
            dropped_now = len(rewards.get("dropped_parts") or [])
            explore_drop_budget_left = max(0, int(explore_drop_budget_left) - int(dropped_now))
            suppressed_part_drop_count += int(rewards.get("suppressed_part_drops") or 0)
            week_key = _world_week_key()
            enemy_element = (enemy["element"] if "element" in enemy.keys() and enemy["element"] else "NORMAL").upper()
            _world_counter_inc(db, week_key, "kills_total", 1)
            _world_counter_inc(db, week_key, f"kills_{enemy_element}", 1)
            _world_counter_inc(db, week_key, "wins_total", 1)
            for p in rewards["dropped_parts"]:
                part_row_for_label = _get_part_by_key(db, p.get("part_key")) if p.get("part_key") else None
                part_display_name = _part_display_name_ja(part_row_for_label) if part_row_for_label else p.get("part_key")
                storage_suffix = "（保管）" if str(p.get("storage_status") or "").strip().lower() == "overflow" else ""
                if storage_suffix:
                    overflow_part_drop_count += 1
                drop_labels.append(f"{p['rarity']} {p['part_type']} {part_display_name} +{p['plus']}{storage_suffix}")
                audit_log(
                    db,
                    AUDIT_EVENT_TYPES["DROP"],
                    user_id=user_id,
                    request_id=request_id,
                    action_key="explore",
                    entity_type="part_instance",
                    entity_id=p.get("part_instance_id"),
                    delta_count=1,
                    payload=_drop_audit_payload(
                        area_key,
                        battle_no,
                        {
                            **dict(p),
                            "drop_type": rewards.get("drop_type"),
                        },
                    ),
                    ip=request.remote_addr,
                )
                audit_log(
                    db,
                    AUDIT_EVENT_TYPES["INVENTORY_DELTA"],
                    user_id=user_id,
                    request_id=request_id,
                    action_key="explore",
                    entity_type="part_instance",
                    entity_id=p.get("part_instance_id"),
                    delta_count=1,
                    payload={
                        "reason": "battle_drop",
                        "battle_no": battle_no,
                        "part_type": p.get("part_type"),
                        "part_key": p.get("part_key"),
                        "growth_tendency_key": p.get("growth_tendency_key"),
                    },
                    ip=request.remote_addr,
                )
            core_drop_rate = _evolution_core_drop_rate_for_area(area_key)
            if (
                not (area_boss_active and battle_no == 1)
                and evolution_feature_unlocked
                and (not core_dropped_this_explore)
                and core_drop_rate > 0.0
                and _roll_evolution_core_drop(rng=random, drop_rate=core_drop_rate)
            ):
                granted_core = _grant_player_core(db, user_id, EVOLUTION_CORE_KEY, qty=1)
                if granted_core > 0:
                    core_dropped_this_explore = True
                    reward_core += int(granted_core)
                    core_reward_sources.add("drop")
                    world_bonus_notes.append("✨ 進化コアを発見！")
                    if battle_logs:
                        battle_logs[-1]["core_drop_line"] = "✨ 進化コアを発見！"
                    audit_log(
                        db,
                        AUDIT_EVENT_TYPES["CORE_DROP"],
                        user_id=user_id,
                        request_id=request_id,
                        action_key="explore",
                        entity_type="core",
                        entity_id=None,
                        delta_count=int(granted_core),
                        payload={
                            "core_key": EVOLUTION_CORE_KEY,
                            "core_name": "進化コア",
                            "quantity": int(granted_core),
                            "area_key": area_key,
                            "enemy_key": (enemy.get("key") if isinstance(enemy, dict) else None),
                        },
                        ip=request.remote_addr,
                    )
                    audit_log(
                        db,
                        AUDIT_EVENT_TYPES["INVENTORY_DELTA"],
                        user_id=user_id,
                        request_id=request_id,
                        action_key="explore",
                        entity_type="core",
                        entity_id=None,
                        delta_count=int(granted_core),
                        payload={
                            "reason": "core_drop",
                            "core_key": EVOLUTION_CORE_KEY,
                            "quantity": int(granted_core),
                            "area_key": area_key,
                            "battle_no": battle_no,
                        },
                        ip=request.remote_addr,
                    )
            if area_boss_active and battle_no == 1:
                _clear_boss_alert(db, user_id, area_key, now_ts=now)
                unlocked_layer = _maybe_unlock_next_layer(db, user_id, user, area_key, enemy)
                if unlocked_layer:
                    boss_unlock_line = f"⚙ 第{int(unlocked_layer)}層 解放"
                    session["home_new_layer_badge"] = int(unlocked_layer)
                audit_log(
                    db,
                    AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                    user_id=user_id,
                    request_id=request_id,
                    action_key="explore",
                    entity_type=("npc_boss_template" if area_boss_kind == "npc" else "enemy"),
                    entity_id=(
                        area_boss_template_id
                        if area_boss_kind == "npc"
                        else (int(enemy["id"]) if "id" in enemy.keys() and enemy["id"] else None)
                    ),
                    payload={
                        "user_id": user_id,
                        "week_key": _world_week_key(),
                        "area_key": area_key,
                        "enemy_key": enemy["key"] if "key" in enemy.keys() else None,
                        "is_boss": True,
                        "boss_kind": area_boss_kind,
                        "robot_instance_id": (
                            int(active["id"])
                            if active and hasattr(active, "keys") and "id" in active.keys() and active["id"]
                            else None
                        ),
                        "robot_name": (
                            active["name"]
                            if active and hasattr(active, "keys") and "name" in active.keys() and active["name"]
                            else None
                        ),
                        "npc_boss_template_id": area_boss_template_id,
                        "source_robot_instance_id": enemy.get("_source_robot_instance_id"),
                        "source_user_id": enemy.get("_source_user_id"),
                        "source_faction": enemy.get("_source_faction"),
                        "reward_decor_asset_id": (area_boss_reward.get("decor_asset_id") if area_boss_reward else None),
                        "reward_decor_key": (area_boss_reward.get("decor_key") if area_boss_reward else None),
                        "reward_decor_name": (area_boss_reward.get("decor_name") if area_boss_reward else None),
                        "reward_missing": bool(area_boss_reward.get("reward_missing")) if area_boss_reward else True,
                        "area_label": _boss_area_label(area_key),
                        "enemy_name": enemy_name,
                        "boss_type": enemy.get("_boss_type"),
                        "reward": area_boss_reward,
                        "attempts_before": area_boss_attempt_before,
                        "attempts_after": area_boss_attempt_after,
                        "unlocked_layer": (int(unlocked_layer) if unlocked_layer else None),
                    },
                    ip=request.remote_addr,
                )
                if area_boss_kind == "fixed":
                    reward_label = (
                        f"装飾『{area_boss_reward['decor_name']}』を入手"
                        if area_boss_reward and area_boss_reward.get("granted")
                        else (
                            f"装飾『{area_boss_reward['decor_name']}』は既に所持"
                            if area_boss_reward and area_boss_reward.get("decor_name")
                            else "報酬なし"
                        )
                    )
                    db.execute(
                        "INSERT INTO chat_messages (user_id, username, message, created_at) VALUES (?, ?, ?, ?)",
                        (
                            user_id,
                            "SYSTEM",
                            f"【BOSS撃破】{session.get('username', 'unknown')} が {_boss_area_label(area_key)} の『{enemy_name}』を討伐！{reward_label}",
                            now_str(),
                        ),
                    )
                    if area_key in NPC_BOSS_ALLOWED_AREAS:
                        create_npc_boss_from_active_robot(user_id, area_key)
                else:
                    npc_analysis_line = f"解析完了: Robot #{int(enemy.get('_source_robot_instance_id') or 0)} の戦闘データ由来"
                    world_bonus_notes.append(npc_analysis_line)
            got_robot = False
            earned_robot = None
            if not (area_boss_active and battle_no == 1):
                got_robot, earned_robot = _add_robot_if_lucky(db, user_id)
                if got_robot and earned_robot is not None:
                    new_robot = {
                        "name": earned_robot["name"],
                        "rarity": earned_robot["rarity"],
                    }
                    db.execute(
                        "INSERT INTO chat_messages (user_id, username, message, created_at) VALUES (?, ?, ?, ?)",
                        (
                            user_id,
                            "SYSTEM",
                            f"{session['username']} が {earned_robot['rarity']} {earned_robot['name']} を入手！",
                            now_str(),
                        ),
                    )
            final_outcome = "win"
            battle_results.append(
                {
                    "battle_no": battle_no,
                    "win": True,
                    "turns": len(battle_logs),
                    "timeout": battle_timeout,
                    "enemy": {
                        "key": enemy["key"] if "key" in enemy.keys() else None,
                        "name_ja": enemy_name,
                        "tier": int(enemy["tier"]) if "tier" in enemy.keys() else None,
                        "element": (enemy["element"] if "element" in enemy.keys() else None),
                        "faction": enemy_faction,
                    },
                    "coin": this_coin,
                    "drops": rewards["dropped_parts"],
                }
            )
            if battle_no < total_fights:
                all_turn_logs.append(
                    {
                        "battle_no": battle_no + 1,
                        "turn": 0,
                        "separator_line": "【回収好機】さらに敵影。連戦に突入！",
                    }
                )
                if not consecutive_bonus_applied:
                    reward_coin += 1
                    world_bonus_notes.append("連戦ボーナス +1")
                    consecutive_bonus_applied = True
                    bonus_events["chain_bonus"] = 1
        else:
            final_outcome = "lose"
            battle_results.append(
                {
                    "battle_no": battle_no,
                    "win": False,
                    "turns": len(battle_logs),
                    "timeout": battle_timeout,
                    "enemy": {
                        "key": enemy["key"] if "key" in enemy.keys() else None,
                        "name_ja": enemy_name,
                        "tier": int(enemy["tier"]) if "tier" in enemy.keys() else None,
                        "element": (enemy["element"] if "element" in enemy.keys() else None),
                        "faction": enemy_faction,
                    },
                    "coin": 0,
                    "drops": [],
                }
            )
            break
        if player_hp <= 0:
            final_outcome = "lose"
            break

    if weekly_mode == "活性" and final_outcome == "win":
        world_bonus_notes.append("世界状態ボーナス発動: 勝利コイン+1")
    if spawned_bonus_applied:
        world_bonus_notes.append("世界状態ボーナス発動: 出現率ボーナス適用")
        if weekly_env and float(weekly_env.get("enemy_spawn_bonus") or 0.0) > 0:
            bonus_events["spawn_bonus_pct"] = round(float(weekly_env.get("enemy_spawn_bonus") or 0.0) * 100.0, 1)
    if weekly_env and float(weekly_env.get("drop_bonus") or 0.0) > 0:
        bonus_events["drop_bonus_pct"] = round(float(weekly_env.get("drop_bonus") or 0.0) * 100.0, 1)
    if promoted_drop_applied:
        world_bonus_notes.append("世界状態ボーナス発動: coin_only→parts昇格")
    if suppressed_part_drop_count > 0:
        world_bonus_notes.append("回収上限に到達: 追加パーツは持ち帰れなかった")
    parts_picked = max(0, int(explore_drop_budget_max) - int(explore_drop_budget_left))
    bonus_events["parts_pickup"] = {"picked": int(parts_picked), "max": int(explore_drop_budget_max)}
    world_bonus_notes.append(f"今回のパーツ回収: {int(parts_picked)}/{int(explore_drop_budget_max)}")
    if area_boss_reward and area_boss_reward.get("decor_name"):
        suffix = "入手" if area_boss_reward.get("granted") else "重複（既所持）"
        world_bonus_notes.append(f"エリアボス報酬: {area_boss_reward['decor_name']} ({suffix})")
    elif (
        area_boss_active
        and final_outcome == "win"
        and area_boss_kind == "npc"
        and area_boss_reward
        and area_boss_reward.get("reward_type") == "core"
    ):
        world_bonus_notes.append("NPCボス報酬: 進化コア ×1")
    elif area_boss_active and final_outcome == "win":
        world_bonus_notes.append("エリアボス報酬: なし")

    prev_row = db.execute(
        "SELECT win_streak FROM user_area_streaks WHERE user_id = ? AND area_key = ?",
        (user_id, area_key),
    ).fetchone()
    prev_streak = int(prev_row["win_streak"] or 0) if prev_row else 0

    win_streak = _update_user_area_streak(
        db,
        user_id=user_id,
        area_key=area_key,
        won=(final_outcome == "win"),
        updated_at=now,
    )
    if final_outcome == "win" and win_streak == 3:
        reward_coin += 1
        bonus_line = "連勝ボーナス：同地点3連勝 +1コイン"
        audit_log(
            db,
            AUDIT_EVENT_TYPES["STREAK_BONUS"],
            user_id=user_id,
            request_id=request_id,
            action_key="explore",
            payload={
                "user_id": user_id,
                "area_key": area_key,
                "win_streak": int(win_streak),
                "bonus_coin": 1,
            },
            ip=request.remote_addr,
        )

    faction_bonus_coin = 0
    winner_faction_for_week = _faction_effective_winner_for_week(db, _world_week_key())
    user_faction = _normalize_faction_key(user["faction"] if "faction" in user.keys() else None)
    if final_outcome == "win" and user_faction and winner_faction_for_week and user_faction == winner_faction_for_week:
        reward_coin += 1
        faction_bonus_coin = 1
        world_bonus_notes.append("陣営バフ発動: 勝利コイン+1")
        bonus_events["faction_bonus_coin"] = 1

    streak_lines = get_streak_lines(
        personality=(active["personality"] if active and "personality" in active.keys() else ""),
        robot_name=(active["name"] if active and "name" in active.keys() else "探索機"),
        win=(final_outcome == "win"),
        win_streak=win_streak,
        prev_streak=prev_streak,
    )
    streak_hint_line = streak_lines.get("streak_hint_line") if streak_lines else None
    bonus_line = (streak_lines.get("bonus_line", bonus_line) if streak_lines else bonus_line)
    streak_break_line = streak_lines.get("streak_break_line") if streak_lines else None

    for b in battle_results:
        enemy_info = b.get("enemy") or {}
        _dex_upsert_enemy(
            db,
            user_id=user_id,
            enemy_key=enemy_info.get("key"),
            is_defeat=bool(b.get("win")),
        )

    if evolution_feature_unlocked:
        evolution_core_progress_result = _advance_evolution_core_progress(
            db,
            user_id=user_id,
            battle_wins=sum(1 for b in battle_results if b.get("win")),
            request_id=request_id,
            action_key="explore",
            area_key=area_key,
            ip=request.remote_addr,
        )
        if int(evolution_core_progress_result.get("granted_core_qty") or 0) > 0:
            guaranteed_core_qty = int(evolution_core_progress_result["granted_core_qty"])
            reward_core += guaranteed_core_qty
            core_reward_sources.add("progress_guarantee")
            world_bonus_notes.append(f"進化コアゲージ満了: 進化コア ×{guaranteed_core_qty}")
    else:
        current_core_progress = _get_player_evolution_core_progress(db, user_id)
        evolution_core_progress_result = {
            "wins": sum(1 for b in battle_results if b.get("win")),
            "progress_added": 0,
            "progress_before": current_core_progress,
            "progress_after": current_core_progress,
            "granted_core_qty": 0,
            "target": int(EVOLUTION_CORE_PROGRESS_TARGET),
        }

    stable_no_damage_inc = 1 if (final_outcome == "win" and _is_no_damage_victory(damage_taken_total)) else 0
    desperate_low_hp_inc = 1 if (final_outcome == "win" and player_hp <= max(1, int(math.floor(player_max_hp * 0.2)))) else 0
    weekly_fit_win = bool(
        final_outcome == "win"
        and weekly_env
        and active
        and _robot_weekly_fit(db, int(active["id"]), weekly_env["element"])
    )
    current_week_key = str((weekly_env["week_key"] if weekly_env and "week_key" in weekly_env.keys() else "") or _world_week_key())
    if active:
        history_applied = _apply_robot_history_update_once(
            db,
            user_id=int(user_id),
            battle_id=battle_id,
            robot_id=int(active["id"]),
            week_key=current_week_key,
            won=(final_outcome == "win"),
            is_boss_encounter=bool(area_boss_active),
            is_boss_defeat=bool(area_boss_active and final_outcome == "win"),
            weekly_fit_win=weekly_fit_win,
            request_ip=request.remote_addr,
        )
        if history_applied:
            _sync_robot_title_unlocks(db, robot_id=int(active["id"]))
        if history_applied and area_boss_active and final_outcome == "win" and last_enemy is not None:
            _record_robot_boss_achievement(
                db,
                robot_id=int(active["id"]),
                enemy_row=last_enemy,
                week_key=_world_week_key(),
            )
    db.execute(
        """
        UPDATE users
        SET coins = coins + ?,
            wins = wins + ?
        WHERE id = ?
        """,
        (
            reward_coin,
            1 if final_outcome == "win" else 0,
            user_id,
        ),
    )
    _apply_style_achievement_progress_once(
        db,
        user_id=user_id,
        robot_id=(active["id"] if active else None),
        battle_id=battle_id,
        stable_no_damage_inc=stable_no_damage_inc,
        burst_crit_finisher_inc=int(crit_finisher_kills),
        desperate_low_hp_inc=desperate_low_hp_inc,
        request_ip=request.remote_addr,
    )
    audit_log(
        db,
        AUDIT_EVENT_TYPES["COIN_DELTA"],
        user_id=user_id,
        request_id=request_id,
        action_key="explore",
        delta_coins=int(reward_coin),
        payload={
            "area_key": area_key,
            "outcome": final_outcome,
            "reward_coin": int(reward_coin),
            "weekly_mode": weekly_mode,
            "faction_bonus_coin": int(faction_bonus_coin),
        },
        ip=request.remote_addr,
    )
    _touch_explore_cooldown(db, user_id, now)
    audit_log(
        db,
        AUDIT_EVENT_TYPES["EXPLORE_END"],
        user_id=user_id,
        request_id=request_id,
        action_key="explore",
        entity_type="enemy",
        entity_id=(int(last_enemy["id"]) if last_enemy and "id" in last_enemy.keys() and last_enemy["id"] else None),
        delta_coins=int(reward_coin),
        payload={
            "area_key": area_key,
            "week_key": _world_week_key(),
            "faction_war": {
                "user_faction": user_faction,
                "winner_faction": winner_faction_for_week,
                "faction_bonus_coin": int(faction_bonus_coin),
            },
            "weekly_element": weekly_env["element"] if weekly_env else None,
            "weekly_mode": weekly_mode,
            "enemy": {
                "key": (last_enemy["key"] if last_enemy and "key" in last_enemy.keys() else None),
                "tier": (int(last_enemy["tier"]) if last_enemy and "tier" in last_enemy.keys() else None),
                "element": (last_enemy["element"] if last_enemy and "element" in last_enemy.keys() else None),
                "faction": ((last_enemy["faction"] if last_enemy and "faction" in last_enemy.keys() else "neutral") or "neutral"),
            },
            "player": {
                "robot_instance_id": active["id"] if active else None,
                "power": robot_stats["power"] if robot_stats else None,
                "hp_max": player_max_hp,
                "atk": player_atk,
                "def": player_def,
                "spd": player_spd,
                "acc": player_acc,
                "cri": player_cri,
            },
            "stage_modifier": {
                "enabled": bool(STAGE_MODIFIERS_ENABLED),
                "summary_line": stage_modifier_line,
                "player_mult": (stage_modifier["player_mult"] if stage_modifier else None),
                "enemy_mult": (stage_modifier["enemy_mult"] if stage_modifier else None),
            },
            "result": {
                "win": final_outcome == "win",
                "turns": len(all_turn_logs),
                "timeout": timeout_any,
                "battle_count": total_fights,
                "is_area_boss": bool(area_boss_active),
                "battle_id": battle_id,
                "damage_taken_total": int(damage_taken_total),
            },
            "battles": battle_results,
            "rewards": {
                "coins": int(reward_coin),
                "cores": int(reward_core),
                "core_progress": {
                    "added": int(evolution_core_progress_result.get("progress_added") or 0),
                    "current": int(evolution_core_progress_result.get("progress_after") or 0),
                    "target": int(evolution_core_progress_result.get("target") or EVOLUTION_CORE_PROGRESS_TARGET),
                    "guaranteed_cores": int(evolution_core_progress_result.get("granted_core_qty") or 0),
                },
                "drops": [
                    {
                        "kind": "part_instance",
                        "id": p.get("part_instance_id"),
                        "count": 1,
                        "rarity": p.get("rarity"),
                        "plus": p.get("plus"),
                        "part_type": p.get("part_type"),
                        "part_key": p.get("part_key"),
                    }
                    for b in battle_results
                    for p in b.get("drops", [])
                ],
            },
            "boss": {
                "is_area_boss": bool(area_boss_active),
                "boss_kind": area_boss_kind,
                "npc_boss_template_id": area_boss_template_id,
                "legacy_mode": bool(area_boss_legacy_mode),
                "spawn_probability": float(area_boss_spawn_p),
                "pity_forced": bool(area_boss_pity_forced),
                "streak_before": int(area_boss_streak_before),
                "attempt_enter": bool(boss_enter_requested),
                "attempts_before": area_boss_attempt_before,
                "attempts_after": area_boss_attempt_after,
                "unlocked_layer": (int(unlocked_layer) if unlocked_layer else None),
                "reward": area_boss_reward,
            },
        },
        ip=request.remote_addr,
    )
    evaluate_referral_qualification(db, user_id, request_ip=request.remote_addr)
    db.commit()

    enemy_image_path = last_enemy["image_path"] if last_enemy and "image_path" in last_enemy.keys() else None
    drop_items = []
    for b in battle_results:
        for p in b.get("drops", []):
            part_key = p.get("part_key")
            part_row = _get_part_by_key(db, part_key) if part_key else None
            drop_items.append(
                {
                    "part_instance_id": p.get("part_instance_id"),
                    "part_type": p.get("part_type"),
                    "part_key": part_key,
                    "part_display_name": (_part_display_name_ja(part_row) if part_row else (part_key or "-")),
                    "rarity": p.get("rarity"),
                    "plus": p.get("plus"),
                    "element": (part_row["element"] if part_row else None),
                    "image_url": url_for("static", filename=_part_image_rel(part_row)),
                    "link": url_for("parts", tab="instances"),
                }
            )
    if all_turn_logs:
        all_turn_logs[-1]["result_line"] = random.choice(VICTORY_LOGS if final_outcome == "win" else DEFEAT_LOGS)
        if boss_unlock_line:
            all_turn_logs[-1]["result_line"] = boss_unlock_line
    if area_boss_active and final_outcome == "win" and last_enemy is not None:
        last_turn = int(all_turn_logs[-1]["turn"]) if all_turn_logs else 1
        last_battle_no = int(all_turn_logs[-1].get("battle_no") or 1) if all_turn_logs else 1
        all_turn_logs.append(
            {
                "turn": last_turn,
                "battle_no": last_battle_no,
                "premonition_line": None,
                "encounter_line": None,
                "archetype_line": None,
                "mid_line": None,
                "player_action": "記録",
                "enemy_action": "停止",
                "enemy_before": 0,
                "enemy_after": 0,
                "player_before": player_hp,
                "player_after": player_hp,
                "player_damage": 0,
                "enemy_damage": 0,
                "critical": False,
                "player_skill": "",
                "player_max": player_max_hp,
                "enemy_max": 0,
                "player_attack_note": None,
                "enemy_attack_note": None,
                "player_relief_line": None,
                "result_line": f"《討伐記録》{last_enemy['name_ja']}撃破！",
            }
        )
    reason_line = None
    if area_key == "layer_2_mist" and last_enemy is not None:
        enemy_acc_now = int(last_enemy["acc"]) if "acc" in last_enemy.keys() and last_enemy["acc"] is not None else None
        if enemy_acc_now is not None and (player_acc - enemy_acc_now) >= 3:
            reason_line = "勝因：命中が安定していた"
    if area_key == "layer_2_rush" and last_enemy is not None:
        enemy_cri_now = int(last_enemy["cri"]) if "cri" in last_enemy.keys() and last_enemy["cri"] is not None else None
        if enemy_cri_now is not None and (player_cri - enemy_cri_now) >= 2:
            reason_line = "勝因：一撃の決定力が活きた"
    dropped_core_name = None
    dropped_core_icon_url = url_for("static", filename="assets/placeholder_enemy.png")
    if reward_core > 0:
        core_row = db.execute(
            "SELECT name_ja, icon_path FROM core_assets WHERE core_key = ? LIMIT 1",
            (EVOLUTION_CORE_KEY,),
        ).fetchone()
        if core_row:
            dropped_core_name = core_row["name_ja"] or "進化コア"
            if core_row["icon_path"]:
                dropped_core_icon_url = url_for("static", filename=core_row["icon_path"])
        else:
            dropped_core_name = "進化コア"
    battle_core_qty = _get_player_core_qty(db, user_id, EVOLUTION_CORE_KEY)
    if core_reward_sources == {"drop"}:
        core_reward_headline = "✨ 進化コアを発見！ ✨"
        core_reward_subline = "パーツをレア化できる貴重なコアです"
        core_reward_row_label = "ドロップ"
    elif core_reward_sources == {"progress_guarantee"}:
        core_reward_headline = "✨ 進化コア保証達成！ ✨"
        core_reward_subline = "勝利ゲージが満了しました"
        core_reward_row_label = "保証"
    elif core_reward_sources == {"npc_boss"}:
        core_reward_headline = "✨ 進化コア獲得！ ✨"
        core_reward_subline = "NPCボス撃破報酬です"
        core_reward_row_label = "報酬"
    elif reward_core > 0:
        core_reward_headline = "✨ 進化コア獲得！ ✨"
        core_reward_subline = "直ドロップと保証がまとめて反映されました"
        core_reward_row_label = "獲得"
    else:
        core_reward_headline = ""
        core_reward_subline = ""
        core_reward_row_label = "ドロップ"
    battle_bg_path = _boss_battle_bg_path(last_enemy, bool(area_boss_active))
    explore_ct_remain = int(_enforce_explore_cooldown_or_wait(db, user, user_id, now_ts=now))
    explore_ct_is_admin = bool(int(user["is_admin"] or 0) == 1)
    if explore_ct_is_admin:
        explore_ct_button_label = "もう一度出撃"
        explore_ct_status_label = ""
    elif explore_ct_remain > 0:
        explore_ct_button_label = f"もう一度出撃（あと{explore_ct_remain}秒）"
        explore_ct_status_label = f"CT中: あと{explore_ct_remain}秒"
    else:
        explore_ct_button_label = "もう一度出撃"
        explore_ct_status_label = "出撃可能"

    summary = {
        "outcome": "勝利" if final_outcome == "win" else "敗北",
        "reward_coin": reward_coin,
        "reward_exp": reward_exp,
        "reward_core": reward_core,
        "highlight_core_drop": bool(reward_core > 0),
        "dropped_core_name": dropped_core_name,
        "dropped_core_icon_url": dropped_core_icon_url,
        "core_reward_headline": core_reward_headline,
        "core_reward_subline": core_reward_subline,
        "core_reward_row_label": core_reward_row_label,
        "dropped_parts": drop_labels,
        "storage_notice": (
            f"所持がいっぱいだったため、{int(overflow_part_drop_count)}件を保管へ送りました。"
            if overflow_part_drop_count > 0
            else None
        ),
        "player_final_hp": player_hp,
        "player_max_hp": player_max_hp,
        "enemy_name": (last_enemy["name_ja"] if last_enemy else "謎の敵"),
        "enemy_key": (last_enemy["key"] if last_enemy else None),
        "enemy_tier": int(last_enemy["tier"]) if last_enemy and "tier" in last_enemy.keys() else None,
        "enemy_image_url": url_for("static", filename=_enemy_image_rel(enemy_image_path)),
        "enemy_faction": ((last_enemy["faction"] if last_enemy and "faction" in last_enemy.keys() else "neutral") or "neutral").lower(),
        "enemy_faction_label": FACTION_LABELS.get(((last_enemy["faction"] if last_enemy and "faction" in last_enemy.keys() else "neutral") or "neutral").lower(), "旧文明"),
        "enemy_faction_icon": FACTION_ICONS.get(((last_enemy["faction"] if last_enemy and "faction" in last_enemy.keys() else "neutral") or "neutral").lower()),
        "boss_type": (last_enemy.get("_boss_type") if last_enemy else None),
        "boss_type_label": (last_enemy.get("_boss_type_label") if last_enemy else None),
        "boss_type_recommend": (last_enemy.get("_boss_type_recommend") if last_enemy else None),
        "boss_type_icon": (last_enemy.get("_boss_type_icon") if last_enemy else ""),
        "weekly_element": weekly_env["element"] if weekly_env else None,
        "weekly_mode": weekly_mode,
        "world_bonus_notes": world_bonus_notes,
        "bonus_events": bonus_events,
        "bonus_line": bonus_line,
        "streak_hint_line": streak_hint_line,
        "streak_break_line": streak_break_line,
        "timeout": timeout_any,
        "archetype_line": archetype_note,
        "player_style": robot_style,
        "reason_line": reason_line,
        "enemy_tendency_tag": (None if area_boss_active else last_enemy_tendency_tag),
        "enemy_variant_label": last_enemy_variant_label,
        "enemy_trait_label": last_enemy_trait_label,
        "enemy_trait_desc": last_enemy_trait_desc,
        "stage_modifier_line": stage_modifier_line,
        "stage_modifier": (
            {
                "tendency": stage_modifier.get("tendency"),
                "player_mult": stage_modifier.get("player_mult"),
                "enemy_mult": stage_modifier.get("enemy_mult"),
                "player_base": {"atk": player_atk_base, "def": player_def_base, "acc": player_acc_base},
                "player_effective": {"atk": player_atk, "def": player_def, "acc": player_acc},
            }
            if stage_modifier
            else None
        ),
        "drop_items": drop_items,
        "boss_unlock_line": boss_unlock_line,
        "unlocked_layer": (int(unlocked_layer) if unlocked_layer else None),
        "unlock_icon": (LAYER_UNLOCK_ICON_BY_LAYER.get(int(unlocked_layer)) if unlocked_layer else None),
        "unlock_banner_ms": (1700 + int(unlocked_layer) * 300) if unlocked_layer else None,
        "boss_reward": area_boss_reward,
        "is_area_boss": bool(area_boss_active),
        "boss_kind": area_boss_kind,
        "npc_boss_template_id": area_boss_template_id,
        "source_robot_instance_id": (last_enemy.get("_source_robot_instance_id") if last_enemy else None),
        "enemy_special_line": (last_enemy.get("_special_line") if isinstance(last_enemy, dict) else None),
        "npc_analysis_line": npc_analysis_line,
        "battle_bg_url": (url_for("static", filename=battle_bg_path) if battle_bg_path else None),
        "explore_ct_remain": int(explore_ct_remain),
        "explore_ct_is_admin": bool(explore_ct_is_admin),
        "explore_ct_button_label": explore_ct_button_label,
        "explore_ct_status_label": explore_ct_status_label,
    }
    summary["reward_front"] = _build_battle_reward_front(
        reward_coin=reward_coin,
        reward_core=reward_core,
        dropped_core_name=dropped_core_name,
        drop_items=drop_items,
    )
    if area_boss_reward and area_boss_reward.get("decor_name"):
        summary["boss_reward_display"] = {
            "name": area_boss_reward.get("decor_name"),
            "image_url": url_for(
                "static",
                filename=_decor_image_rel(area_boss_reward.get("decor_image_path"), area_boss_reward.get("decor_key")),
            ),
            "granted": bool(area_boss_reward.get("granted")),
        }
    else:
        summary["boss_reward_display"] = None
    if boss_unlock_line:
        summary["world_bonus_notes"] = summary.get("world_bonus_notes", []) + [boss_unlock_line]
    return render_template(
        "battle.html",
        state={"active": 0, "enemy_name": summary["enemy_name"], "enemy_hp": 0},
        log=[],
        log_entries=[],
        message=None,
        new_robot=new_robot,
        explore_mode=True,
        explore_area_key=area["key"],
        explore_area_label=area["label"],
        active_robot=_get_active_robot(db, user_id),
        no_active_robot=False,
        turn_logs=all_turn_logs,
        summary=summary,
        battle_log_mode=battle_log_mode,
        battle_ritual_overlay_enabled=BATTLE_RITUAL_OVERLAY_ENABLED,
    )


@app.route("/share/boss", methods=["POST"])
@login_required
def share_boss_defeat():
    db = get_db()
    user_id = int(session["user_id"])
    user = db.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
    enemy_key = (request.form.get("enemy_key") or "").strip()
    enemy_name = (request.form.get("enemy_name") or "未知のボス").strip()
    area_key = (request.form.get("area_key") or "").strip()
    area_label = (request.form.get("area_label") or _boss_area_label(area_key) or area_key or "不明エリア").strip()
    robot_id_raw = (request.form.get("robot_id") or "").strip()
    robot_name = (request.form.get("robot_name") or "").strip()
    robot_id = int(robot_id_raw) if robot_id_raw.isdigit() else None
    if robot_id:
        robot = db.execute(
            "SELECT id, name FROM robot_instances WHERE id = ? AND user_id = ?",
            (robot_id, user_id),
        ).fetchone()
        if robot:
            robot_name = (robot["name"] or robot_name).strip()
        else:
            robot_id = None
    payload = {
        "share_type": "boss_defeat",
        "enemy_key": enemy_key,
        "enemy_name": enemy_name,
        "area_key": area_key,
        "area_label": area_label,
        "robot_id": robot_id,
        "robot_name": robot_name,
        "user_id": user_id,
        "username": (user["username"] if user and user["username"] else session.get("username", "unknown")),
        "game_url": _public_game_root_url(),
    }
    share_text = build_share_text("share.boss.defeat", payload)
    audit_log(
        db,
        AUDIT_EVENT_TYPES["SHARE_CLICK"],
        user_id=user_id,
        request_id=getattr(g, "request_id", None),
        action_key="share",
        entity_type="enemy",
        entity_id=None,
        payload=payload,
        ip=request.remote_addr,
    )
    db.commit()
    intent_url = "https://x.com/intent/tweet?" + urlencode({"text": share_text})
    return redirect(intent_url)


@app.route("/robots")
@login_required
def robots():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    _ensure_qol_entitlement(db, user["id"])
    show_decomposed = request.args.get("show_decomposed", "0") == "1"
    where = "ri.user_id = ?"
    params = [session["user_id"]]
    if not show_decomposed:
        where += " AND ri.status != 'decomposed'"
    instances = db.execute(
        f"""
        SELECT ri.*, rip.head_key, rip.r_arm_key, rip.l_arm_key, rip.legs_key
        FROM robot_instances ri
        JOIN robot_instance_parts rip ON rip.robot_instance_id = ri.id
        WHERE {where}
        ORDER BY ri.updated_at DESC
        """,
        params,
    ).fetchall()
    instances = [dict(r) for r in instances]
    weekly_env = _world_current_environment(db)
    weekly_element = weekly_env["element"] if weekly_env else None
    for idx, inst in enumerate(instances):
        inst = _refresh_robot_instance_render_assets(db, inst, log_label="robots")
        if not inst:
            continue
        instances[idx] = inst
        raw_name = (inst.get("name") or "").strip()
        if not raw_name or re.fullmatch(r"Robot\s*#\d+", raw_name):
            inst["display_name"] = "無名ロボ"
        else:
            inst["display_name"] = raw_name
        stat_obj = _compute_robot_stats_for_instance(db, inst["id"])
        if stat_obj:
            inst["final_stats"] = stat_obj["stats"]
            inst["power"] = stat_obj["power"]
            inst["set_bonus"] = stat_obj["set_bonus"]
            inst["archetype"] = stat_obj.get("archetype")
            inst["robot_profile"] = _robot_profile_view(stat_obj)
        else:
            inst["final_stats"] = None
            inst["power"] = None
            inst["set_bonus"] = None
            inst["archetype"] = None
            inst["robot_profile"] = _robot_profile_view(None)
        inst["weekly_fit"] = _robot_weekly_fit(db, inst["id"], weekly_element) if weekly_element else False
    limits = _effective_limits(db, user)
    used_all = db.execute(
        "SELECT COUNT(*) AS c FROM robot_instances WHERE user_id = ? AND status != 'decomposed'",
        (session["user_id"],),
    ).fetchone()["c"]
    used_display = min(used_all, limits["robot_slots"])
    overflow = max(0, used_all - limits["robot_slots"])
    return render_template(
        "robots.html",
        instances=instances,
        limits=limits,
        active_robot_id=user["active_robot_id"],
        weekly_element=weekly_element,
        show_decomposed=show_decomposed,
        used_all=used_all,
        used_display=used_display,
        overflow=overflow,
    )


@app.route("/robots/<int:instance_id>")
@login_required
def robot_detail(instance_id):
    db = get_db()
    user_id = int(session["user_id"])
    row = db.execute(
        """
        SELECT
            ri.*,
            rip.head_key,
            rip.r_arm_key,
            rip.l_arm_key,
            rip.legs_key,
            rip.decor_asset_id,
            u.username AS owner_name
        FROM robot_instances ri
        JOIN robot_instance_parts rip ON rip.robot_instance_id = ri.id
        JOIN users u ON u.id = ri.user_id
        WHERE ri.id = ?
          AND ri.status = 'active'
          AND (ri.user_id = ? OR COALESCE(ri.is_public, 1) = 1)
        """,
        (int(instance_id), user_id),
    ).fetchone()
    if not row:
        abort(404)
    robot = dict(row)
    # Robot detail should always reflect latest part offsets/alignment.
    # Re-compose here to avoid stale composed_image_path from prior cache states.
    try:
        rel = _compose_instance_image(db, robot, robot)
        if rel:
            robot["composed_image_path"] = rel
            latest = db.execute("SELECT updated_at FROM robot_instances WHERE id = ?", (robot["id"],)).fetchone()
            robot["updated_at"] = int(latest["updated_at"] or 0) if latest else int(time.time())
    except Exception:
        app.logger.exception("robot_detail.compose_failed instance_id=%s", instance_id)
        if not robot.get("composed_image_path"):
            rel = _compose_instance_image(db, robot, robot)
            robot["composed_image_path"] = rel
            latest = db.execute("SELECT updated_at FROM robot_instances WHERE id = ?", (robot["id"],)).fetchone()
            robot["updated_at"] = int(latest["updated_at"] or 0) if latest else int(time.time())
    robot["image_url"] = _composed_image_url(robot.get("composed_image_path"), robot.get("updated_at"))
    stat_obj = _compute_robot_stats_for_instance(db, int(robot["id"]))
    robot["final_stats"] = stat_obj["stats"] if stat_obj else None
    robot["power"] = stat_obj["power"] if stat_obj else None
    robot["set_bonus"] = stat_obj["set_bonus"] if stat_obj else None
    robot["archetype"] = stat_obj.get("archetype") if stat_obj else None
    robot["robot_profile"] = _robot_profile_view(stat_obj)
    if robot.get("decor_asset_id"):
        decor_row = db.execute(
            "SELECT key, name_ja FROM robot_decor_assets WHERE id = ?",
            (int(robot["decor_asset_id"]),),
        ).fetchone()
        robot["decor_name"] = decor_row["name_ja"] if decor_row else None
    else:
        robot["decor_name"] = None

    part_rows = db.execute(
        """
        SELECT part_type, key, display_name_ja, rarity, element
        FROM robot_parts
        WHERE key IN (?, ?, ?, ?)
        """,
        (
            robot.get("head_key"),
            robot.get("r_arm_key"),
            robot.get("l_arm_key"),
            robot.get("legs_key"),
        ),
    ).fetchall()
    part_by_key = {str(r["key"]): dict(r) for r in part_rows}

    def _slot_line(label, key):
        row = part_by_key.get(str(key or ""))
        if row:
            name = _part_display_name_ja(row)
        else:
            name = str(key or "-")
        return {"slot_label": label, "part_name": name, "part_key": str(key or "-")}

    robot_composition = [
        _slot_line("頭部", robot.get("head_key")),
        _slot_line("右腕", robot.get("r_arm_key")),
        _slot_line("左腕", robot.get("l_arm_key")),
        _slot_line("脚部", robot.get("legs_key")),
        {"slot_label": "装飾", "part_name": (robot.get("decor_name") or "なし"), "part_key": None},
    ]
    weekly_env = _world_current_environment(db)
    weekly_element = weekly_env["element"] if weekly_env else None
    weekly_fit = _robot_weekly_fit(db, int(robot["id"]), weekly_element) if weekly_element else False
    history = _robot_history_row(db, int(robot["id"]))
    titles = db.execute(
        """
        SELECT rt.key, rt.name_ja, rt.desc_ja, rt.sort_order, rtu.unlocked_at
        FROM robot_title_unlocks rtu
        JOIN robot_titles rt ON rt.id = rtu.title_id
        WHERE rtu.robot_id = ? AND rt.is_active = 1
        ORDER BY rt.sort_order ASC, rtu.unlocked_at DESC
        """,
        (int(robot["id"]),),
    ).fetchall()
    achievements = db.execute(
        """
        SELECT id, type, title, body, enemy_key, enemy_name, week_key, created_at
        FROM robot_achievements
        WHERE robot_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 60
        """,
        (int(robot["id"]),),
    ).fetchall()
    return render_template(
        "robot_detail.html",
        robot=robot,
        robot_composition=robot_composition,
        history=history,
        titles=titles,
        achievements=achievements,
        weekly_env=weekly_env,
        weekly_fit=weekly_fit,
        primary_title=_robot_primary_title(db, int(robot["id"])),
        can_share=(int(robot["user_id"]) == user_id),
    )


@app.route("/robots/<int:instance_id>/activate", methods=["POST"])
@login_required
def robot_instance_activate(instance_id):
    db = get_db()
    target = db.execute(
        "SELECT id FROM robot_instances WHERE id = ? AND user_id = ? AND status = 'active'",
        (instance_id, session["user_id"]),
    ).fetchone()
    if not target:
        session["message"] = "出撃機体に設定できるロボが見つかりません。"
        return redirect(url_for("robots"))
    db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (instance_id, session["user_id"]))
    db.commit()
    session["message"] = f"出撃機体を #{instance_id} に設定しました。"
    return redirect(url_for("robots"))


@app.route("/robots/<int:instance_id>/share", methods=["POST"])
@login_required
def robot_share(instance_id):
    db = get_db()
    row = db.execute(
        """
        SELECT id, user_id, name
        FROM robot_instances
        WHERE id = ? AND user_id = ? AND status = 'active'
        """,
        (int(instance_id), int(session["user_id"])),
    ).fetchone()
    if not row:
        session["message"] = "共有対象のロボが見つかりません。"
        return redirect(url_for("robots"))
    primary_title = _robot_primary_title(db, int(row["id"]))
    detail_url = url_for("robot_detail", instance_id=int(row["id"]))
    msg = f"相棒共有：{row['name']}《{primary_title}》 {detail_url}"
    db.execute(
        "INSERT INTO chat_messages (user_id, username, message, created_at) VALUES (?, ?, ?, ?)",
        (int(session["user_id"]), session.get("username", "unknown"), msg[:200], now_str()),
    )
    audit_log(
        db,
        AUDIT_EVENT_TYPES["ROBOT_SHARE"],
        user_id=int(session["user_id"]),
        request_id=getattr(g, "request_id", None),
        action_key="robot_share",
        entity_type="robot_instance",
        entity_id=int(row["id"]),
        payload={
            "robot_instance_id": int(row["id"]),
            "primary_title": primary_title,
            "detail_url": detail_url,
        },
        ip=request.remote_addr,
    )
    db.commit()
    session["message"] = "全体チャットへ共有しました。"
    return redirect(url_for("robot_detail", instance_id=int(row["id"])))


@app.route("/robots/<int:instance_id>/toggle_public", methods=["POST"])
@login_required
def robot_toggle_public(instance_id):
    db = get_db()
    row = db.execute(
        "SELECT id, is_public FROM robot_instances WHERE id = ? AND user_id = ?",
        (int(instance_id), int(session["user_id"])),
    ).fetchone()
    if not row:
        abort(404)
    next_value = 0 if int(row["is_public"] or 0) == 1 else 1
    db.execute("UPDATE robot_instances SET is_public = ?, updated_at = ? WHERE id = ?", (next_value, int(time.time()), int(instance_id)))
    db.commit()
    session["message"] = ("展示を公開しました。" if next_value == 1 else "展示を非公開にしました。")
    return redirect(url_for("robot_detail", instance_id=int(instance_id)))


@app.route("/robot-instance/<int:instance_id>/decompose", methods=["POST"])
@login_required
def robot_instance_decompose(instance_id):
    db = get_db()
    row = db.execute(
        """
        SELECT ri.*, rip.head_key, rip.r_arm_key, rip.l_arm_key, rip.legs_key
        FROM robot_instances ri
        JOIN robot_instance_parts rip ON rip.robot_instance_id = ri.id
        WHERE ri.id = ? AND ri.user_id = ?
        """,
        (instance_id, session["user_id"]),
    ).fetchone()
    if not row or row["status"] == "decomposed":
        session["message"] = "分解対象が見つかりません。"
        return redirect(url_for("robots"))
    _ensure_robot_instance_part_instances(db, instance_id)
    rip = db.execute(
        "SELECT * FROM robot_instance_parts WHERE robot_instance_id = ?",
        (instance_id,),
    ).fetchone()
    restored = 0
    restored_ids = []
    user_row = db.execute("SELECT id, part_inventory_limit FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    for col in ("head_part_instance_id", "r_arm_part_instance_id", "l_arm_part_instance_id", "legs_part_instance_id"):
        if col in rip.keys() and rip[col]:
            _return_part_instance_to_pool(db, session["user_id"], rip[col], user_row=user_row)
            restored += 1
            restored_ids.append(int(rip[col]))
    if restored == 0:
        for ptype, pkey in [
            ("HEAD", row["head_key"]),
            ("RIGHT_ARM", row["r_arm_key"]),
            ("LEFT_ARM", row["l_arm_key"]),
            ("LEGS", row["legs_key"]),
        ]:
            _add_part_drop(
                db,
                session["user_id"],
                part_type=ptype,
                part_key=pkey,
                source="decompose",
                robot_instance_id=row["id"],
            )
            audit_log(
                db,
                AUDIT_EVENT_TYPES["INVENTORY_DELTA"],
                user_id=session["user_id"],
                request_id=getattr(g, "request_id", None),
                action_key="decompose",
                entity_type="part_key",
                entity_id=None,
                delta_count=1,
                payload={"reason": "decompose_fallback_drop", "part_type": ptype, "part_key": pkey, "robot_instance_id": row["id"]},
                ip=request.remote_addr,
            )
    db.execute(
        "UPDATE robot_instances SET status = 'decomposed', updated_at = ? WHERE id = ?",
        (int(time.time()), instance_id),
    )
    audit_log(
        db,
        AUDIT_EVENT_TYPES["ROBOT_DECOMPOSE"],
        user_id=session["user_id"],
        request_id=getattr(g, "request_id", None),
        action_key="decompose",
        entity_type="robot_instance",
        entity_id=instance_id,
        payload={
            "robot_instance_id": instance_id,
            "robot_name": row["name"],
            "restored_count": restored if restored else 4,
            "restored_part_instance_ids": restored_ids,
            "fallback_drop": restored == 0,
        },
        ip=request.remote_addr,
    )
    if restored_ids:
        for pid in restored_ids:
            audit_log(
                db,
                AUDIT_EVENT_TYPES["INVENTORY_DELTA"],
                user_id=session["user_id"],
                request_id=getattr(g, "request_id", None),
                action_key="decompose",
                entity_type="part_instance",
                entity_id=pid,
                delta_count=1,
                payload={"reason": "decompose_restore", "robot_instance_id": instance_id},
                ip=request.remote_addr,
            )
    db.commit()
    session["message"] = f"ロボ「{row['name']}」を分解し、パーツへ戻しました（名称は記録に保持）。"
    return redirect(url_for("robots"))


@app.route("/fusion", methods=["GET", "POST"])
@login_required
def fusion():
    db = get_db()
    user_id = session["user_id"]
    message = None

    if request.method == "POST":
        ids = request.form.getlist("robot_id")
        if len(ids) != 2:
            message = "2体選択してください。"
        else:
            r1 = db.execute(
                "SELECT * FROM user_robots WHERE id = ? AND user_id = ?", (ids[0], user_id)
            ).fetchone()
            r2 = db.execute(
                "SELECT * FROM user_robots WHERE id = ? AND user_id = ?", (ids[1], user_id)
            ).fetchone()
            if not r1 or not r2:
                message = "選択が無効です。"
            else:
                new_head = random.choice([r1["head"], r2["head"]])
                new_right = random.choice([r1["right_arm"], r2["right_arm"]])
                new_left = random.choice([r1["left_arm"], r2["left_arm"]])
                new_legs = random.choice([r1["legs"], r2["legs"]])
                db.execute("DELETE FROM user_robots WHERE id IN (?, ?)", (r1["id"], r2["id"]))
                db.execute(
                    "INSERT INTO user_robots (user_id, head, right_arm, left_arm, legs, obtained_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, new_head, new_right, new_left, new_legs, int(time.time())),
                )
                db.commit()
                message = "合成成功！ 新ロボを獲得。"

    robots = db.execute(
        "SELECT * FROM user_robots WHERE user_id = ? ORDER BY obtained_at DESC", (user_id,)
    ).fetchall()
    return render_template("fusion.html", robots=robots, message=message)


@app.route("/build", methods=["GET", "POST"])
@login_required
def build():
    db = get_db()
    user_id = session["user_id"]
    now = int(time.time())
    owned_rows = db.execute(
        """
        WITH inv AS (
            SELECT
                pi.id AS instance_id,
                pi.plus,
                pi.w_hp, pi.w_atk, pi.w_def, pi.w_spd, pi.w_acc, pi.w_cri,
                pi.rarity AS instance_rarity,
                pi.element AS instance_element,
                pi.series AS instance_series,
                rp.part_type, rp.key, rp.series, rp.image_path, rp.offset_x, rp.offset_y,
                rp.rarity, rp.element, rp.display_name_ja
            FROM part_instances pi
            JOIN robot_parts rp ON rp.id = pi.part_id
            WHERE pi.user_id = ? AND pi.status = 'inventory' AND rp.is_active = 1
        ),
        ranked AS (
            SELECT
                inv.*,
                COUNT(*) OVER (PARTITION BY inv.key, inv.plus) AS qty,
                ROW_NUMBER() OVER (PARTITION BY inv.key, inv.plus ORDER BY inv.instance_id ASC) AS rn
            FROM inv
        )
        SELECT *
        FROM ranked
        WHERE rn = 1
        ORDER BY
            part_type ASC,
            plus DESC,
            CASE UPPER(COALESCE(instance_rarity, rarity, 'N'))
                WHEN 'UR' THEN 5
                WHEN 'SSR' THEN 4
                WHEN 'SR' THEN 3
                WHEN 'R' THEN 2
                ELSE 1
            END DESC,
            COALESCE(instance_element, element, 'NORMAL') ASC,
            COALESCE(instance_series, series, '') ASC,
            instance_id ASC
        """,
        (user_id,),
    ).fetchall()
    part_groups = {"HEAD": [], "RIGHT_ARM": [], "LEFT_ARM": [], "LEGS": []}
    for row in owned_rows:
        item = dict(row)
        item["instance_id"] = int(item["instance_id"])
        item["display_name"] = _part_display_name_ja(item)
        item["display_name_with_plus"] = f"{item['display_name']} +{int(item.get('plus') or 0)}"
        item["display_image_url"] = url_for("static", filename=_part_image_rel(item), v=APP_VERSION)
        preview_payload = {
            "part_type": item.get("part_type"),
            "key": item.get("key"),
            "series": (item.get("instance_series") or item.get("series")),
            "rarity": (item.get("instance_rarity") or item.get("rarity") or "N"),
            "element": (item.get("instance_element") or item.get("element") or "NORMAL"),
            "plus": int(item.get("plus") or 0),
            "w_hp": item.get("w_hp"),
            "w_atk": item.get("w_atk"),
            "w_def": item.get("w_def"),
            "w_spd": item.get("w_spd"),
            "w_acc": item.get("w_acc"),
            "w_cri": item.get("w_cri"),
        }
        item["estimate_stats"] = compute_part_stats(preview_payload) if preview_payload else {
            "hp": 0,
            "atk": 0,
            "def": 0,
            "spd": 0,
            "acc": 0,
            "cri": 0,
        }
        item["estimate_element"] = (preview_payload.get("element") or "NORMAL").upper()
        card = _part_card_payload(item, can_discard=False)
        item["part_type_label"] = card["part_type_label"]
        item["stat_rows"] = card["stat_rows"]
        item["focus_rows"] = card["focus_rows"]
        item["focus_line"] = card["focus_line"]
        item["total_value"] = card["total_value"]
        item["extreme_title"] = card["extreme_title"]
        part_groups[row["part_type"]].append(item)

    slot_param_map = {
        "HEAD": "head_key",
        "RIGHT_ARM": "r_arm_key",
        "LEFT_ARM": "l_arm_key",
        "LEGS": "legs_key",
    }
    missing_part_types = [
        _part_type_ui_label(part_type)
        for part_type in slot_param_map.keys()
        if not part_groups[part_type]
    ]
    selected_slot_values = {}
    selected_parts = {}
    selected_payloads = []
    for part_type, param in slot_param_map.items():
        options = part_groups[part_type]
        picked_raw = (request.values.get(param) or "").strip()
        picked_id = int(picked_raw) if picked_raw.isdigit() else None
        option = next((o for o in options if int(o["instance_id"]) == picked_id), None) if picked_id is not None else None
        if option is None and options:
            option = options[0]
        selected_slot_values[param] = int(option["instance_id"]) if option else None
        selected_parts[part_type] = option
        if option:
            selected_payloads.append(
                {
                    "part_type": option.get("part_type"),
                    "key": option.get("key"),
                    "series": (option.get("instance_series") or option.get("series")),
                    "rarity": (option.get("instance_rarity") or option.get("rarity") or "N"),
                    "element": (option.get("instance_element") or option.get("element") or "NORMAL"),
                    "plus": int(option.get("plus") or 0),
                    "w_hp": option.get("w_hp"),
                    "w_atk": option.get("w_atk"),
                    "w_def": option.get("w_def"),
                    "w_spd": option.get("w_spd"),
                    "w_acc": option.get("w_acc"),
                    "w_cri": option.get("w_cri"),
                }
            )

    estimate = compute_robot_stats(selected_payloads) if len(selected_payloads) == 4 else None
    decor_assets = db.execute(
        """
        SELECT rda.id, rda.key, rda.name_ja, rda.image_path
        FROM user_decor_inventory udi
        JOIN robot_decor_assets rda ON rda.id = udi.decor_asset_id
        WHERE udi.user_id = ? AND rda.is_active = 1
        ORDER BY udi.acquired_at DESC, rda.id DESC
        """,
        (user_id,),
    ).fetchall()
    decor_assets = [
        {
            **dict(row),
            "display_image_path": _decor_image_rel(row["image_path"], row["key"]),
        }
        for row in decor_assets
    ]
    decor_id_raw = (request.values.get("decor_asset_id") or "").strip()
    selected_decor_id = int(decor_id_raw) if decor_id_raw.isdigit() else None
    if selected_decor_id and not any(int(d["id"]) == selected_decor_id for d in decor_assets):
        selected_decor_id = None
    selected_decor = next((d for d in decor_assets if int(d["id"]) == int(selected_decor_id)), None) if selected_decor_id else None
    candidate_build_style = _robot_style_from_final_stats(estimate["stats"]) if estimate else {
        "style_key": "stable",
        "style_label": ROBOT_STYLE_LABELS["stable"],
        "style_description": _robot_style_description("stable"),
        "reason": "判定対象パーツ不足",
        "style_scores": {"stable": 0.0, "desperate": 0.0, "burst": 0.0},
        "legacy_build_type": "STABLE",
    }
    active_robot = _get_active_robot(db, user_id)
    current_robot_stats_obj = _compute_robot_stats_for_instance(db, active_robot["id"]) if active_robot else None
    current_robot_stats = {
        "hp": int(current_robot_stats_obj["stats"]["hp"]) if current_robot_stats_obj else 0,
        "atk": int(current_robot_stats_obj["stats"]["atk"]) if current_robot_stats_obj else 0,
        "def": int(current_robot_stats_obj["stats"]["def"]) if current_robot_stats_obj else 0,
        "spd": int(current_robot_stats_obj["stats"]["spd"]) if current_robot_stats_obj else 0,
        "acc": int(current_robot_stats_obj["stats"]["acc"]) if current_robot_stats_obj else 0,
        "cri": int(current_robot_stats_obj["stats"]["cri"]) if current_robot_stats_obj else 0,
        "power": float(current_robot_stats_obj["power"]) if current_robot_stats_obj else 0.0,
    }
    candidate_robot_stats = {
        "hp": int(estimate["stats"]["hp"]) if estimate else 0,
        "atk": int(estimate["stats"]["atk"]) if estimate else 0,
        "def": int(estimate["stats"]["def"]) if estimate else 0,
        "spd": int(estimate["stats"]["spd"]) if estimate else 0,
        "acc": int(estimate["stats"]["acc"]) if estimate else 0,
        "cri": int(estimate["stats"]["cri"]) if estimate else 0,
        "power": float(estimate["power"]) if estimate else 0.0,
    }
    stat_comparison_rows = _build_stat_comparison_rows(current_robot_stats, candidate_robot_stats)
    current_build_style = (
        current_robot_stats_obj.get("robot_style")
        if current_robot_stats_obj and current_robot_stats_obj.get("robot_style")
        else {
            "style_key": "stable",
            "style_label": ROBOT_STYLE_LABELS["stable"],
            "style_description": _robot_style_description("stable"),
            "reason": "未設定",
            "style_scores": {"stable": 0.0, "desperate": 0.0, "burst": 0.0},
            "legacy_build_type": "STABLE",
        }
    )
    boss_alert_status = _home_boss_alert_status(db, user_id, now_ts=now)
    boss_alert_hint = _boss_alert_recommendation_context(boss_alert_status)

    return render_template(
        "build.html",
        part_groups=part_groups,
        missing_part_types=missing_part_types,
        selected_slot_values=selected_slot_values,
        selected_parts=selected_parts,
        estimate=estimate,
        decor_assets=decor_assets,
        selected_decor_id=selected_decor_id,
        candidate_build_style=candidate_build_style,
        current_build_style=current_build_style,
        current_robot_stats=current_robot_stats,
        stat_comparison_rows=stat_comparison_rows,
        boss_alert_active=boss_alert_hint["boss_alert_active"],
        boss_type=boss_alert_hint["boss_type"],
        recommended_build=boss_alert_hint["recommended_build"],
        recommended_text=boss_alert_hint["recommended_text"],
        set_bonus_table=SET_BONUS_TABLE,
        element_label_map=ELEMENT_LABEL_MAP,
    )


@app.route("/build/confirm", methods=["POST"])
@login_required
def build_confirm():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    robot_name = request.form.get("robot_name", "").strip()
    head_choice = (request.form.get("head_key") or "").strip()
    r_arm_choice = (request.form.get("r_arm_key") or "").strip()
    l_arm_choice = (request.form.get("l_arm_key") or "").strip()
    legs_choice = (request.form.get("legs_key") or "").strip()
    decor_asset_id_raw = (request.form.get("decor_asset_id") or "").strip()
    decor_asset_id = int(decor_asset_id_raw) if decor_asset_id_raw.isdigit() else None
    combat_mode = _normalize_combat_mode(request.form.get("combat_mode"))
    if not all([head_choice, r_arm_choice, l_arm_choice, legs_choice]):
        session["message"] = "全カテゴリから1つずつ選択してください。"
        return redirect(url_for("build"))
    slot_defs = {
        "head": {"expected_type": "HEAD", "choice": head_choice},
        "r_arm": {"expected_type": "RIGHT_ARM", "choice": r_arm_choice},
        "l_arm": {"expected_type": "LEFT_ARM", "choice": l_arm_choice},
        "legs": {"expected_type": "LEGS", "choice": legs_choice},
    }

    def _resolve_selected_part_instance(choice_raw, expected_type):
        choice = str(choice_raw or "").strip()
        if not choice:
            return None
        if choice.isdigit():
            row = db.execute(
                """
                SELECT pi.id, pi.status, rp.key, rp.part_type
                FROM part_instances pi
                JOIN robot_parts rp ON rp.id = pi.part_id
                WHERE pi.id = ? AND pi.user_id = ? AND pi.status = 'inventory' AND rp.is_active = 1
                """,
                (int(choice), user["id"]),
            ).fetchone()
            if not row:
                return None
            if _norm_part_type(row["part_type"]) != expected_type:
                return None
            return {"id": int(row["id"]), "key": row["key"], "part_type": _norm_part_type(row["part_type"])}
        # Backward-compatible key fallback.
        row = db.execute(
            """
            SELECT pi.id, pi.status, rp.key, rp.part_type
            FROM part_instances pi
            JOIN robot_parts rp ON rp.id = pi.part_id
            WHERE pi.user_id = ? AND pi.status = 'inventory' AND rp.key = ? AND rp.is_active = 1
            ORDER BY pi.plus DESC, pi.id ASC
            LIMIT 1
            """,
            (user["id"], choice),
        ).fetchone()
        if row and _norm_part_type(row["part_type"]) == expected_type:
            return {"id": int(row["id"]), "key": row["key"], "part_type": _norm_part_type(row["part_type"])}
        legacy_id = _take_or_materialize_part_instance(db, user["id"], choice)
        if not legacy_id:
            return None
        legacy_row = db.execute(
            """
            SELECT pi.id, pi.status, rp.key, rp.part_type
            FROM part_instances pi
            JOIN robot_parts rp ON rp.id = pi.part_id
            WHERE pi.id = ? AND pi.user_id = ? AND rp.is_active = 1
            """,
            (legacy_id, user["id"]),
        ).fetchone()
        if (
            not legacy_row
            or _norm_part_type(legacy_row["part_type"]) != expected_type
            or str(legacy_row["status"] or "inventory").strip().lower() != "inventory"
        ):
            return None
        return {"id": int(legacy_row["id"]), "key": legacy_row["key"], "part_type": _norm_part_type(legacy_row["part_type"])}

    resolved_slots = {}
    for slot_name, cfg in slot_defs.items():
        resolved = _resolve_selected_part_instance(cfg["choice"], cfg["expected_type"])
        if not resolved:
            session["message"] = "無効化されたパーツは組み立てに使用できません。"
            return redirect(url_for("build"))
        resolved_slots[slot_name] = resolved
    if len({resolved_slots["head"]["id"], resolved_slots["r_arm"]["id"], resolved_slots["l_arm"]["id"], resolved_slots["legs"]["id"]}) != 4:
        session["message"] = "同じ個体を複数部位へは設定できません。"
        return redirect(url_for("build"))

    head_key = resolved_slots["head"]["key"]
    r_arm_key = resolved_slots["r_arm"]["key"]
    l_arm_key = resolved_slots["l_arm"]["key"]
    legs_key = resolved_slots["legs"]["key"]
    if combat_mode == "berserk" and not _has_any_active_boss_alert(db, user["id"]):
        session["message"] = "背水モードはボス警報中のみ選択可能"
        return redirect(url_for("build"))
    if decor_asset_id is not None:
        decor = db.execute(
            """
            SELECT rda.id
            FROM robot_decor_assets rda
            JOIN user_decor_inventory udi ON udi.decor_asset_id = rda.id
            WHERE rda.id = ? AND rda.is_active = 1 AND udi.user_id = ?
            """,
            (decor_asset_id, user["id"]),
        ).fetchone()
        if not decor:
            session["message"] = "装飾が無効です。選び直してください。"
            return redirect(url_for("build"))
    if not robot_name:
        next_id_row = db.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM robot_instances"
        ).fetchone()
        robot_name = f"Robot #{next_id_row['next_id']}"
    limits = _effective_limits(db, user)
    active_count = db.execute(
        "SELECT COUNT(*) AS c FROM robot_instances WHERE user_id = ? AND status != 'decomposed'",
        (user["id"],),
    ).fetchone()["c"]
    if active_count >= limits["robot_slots"]:
        flash(
            f"保存枠がいっぱいです（{int(active_count)}/{int(limits['robot_slots'])}）。ロボを整理してください。",
            "error",
        )
        return redirect(url_for("build"))
    try:
        db.execute("BEGIN IMMEDIATE")
        selected = {
            "head": int(resolved_slots["head"]["id"]),
            "r_arm": int(resolved_slots["r_arm"]["id"]),
            "l_arm": int(resolved_slots["l_arm"]["id"]),
            "legs": int(resolved_slots["legs"]["id"]),
        }
        if not all(selected.values()):
            missing = [k for k, v in selected.items() if not v]
            raise ValueError(f"在庫不足: {', '.join(missing)}")

        instance_id = _create_robot_instance(
            db,
            user["id"],
            robot_name,
            head_key,
            r_arm_key,
            l_arm_key,
            legs_key,
            decor_asset_id=decor_asset_id,
            status="active",
            combat_mode=combat_mode,
        )
        _equip_part_instances_on_robot(db, instance_id, selected)
        parts = {
            "head_key": head_key,
            "r_arm_key": r_arm_key,
            "l_arm_key": l_arm_key,
            "legs_key": legs_key,
            "decor_asset_id": decor_asset_id,
        }
        _compose_instance_assets_no_commit(db, instance_id, parts)
        _ensure_robot_title_master_rows(db)
        _grant_robot_title_by_key(db, robot_id=int(instance_id), title_key="title_boot")
        db.execute("UPDATE users SET active_robot_id = ? WHERE id = ?", (instance_id, user["id"]))
        week_key = _world_week_key()
        build_element = _build_element_from_keys(db, head_key, r_arm_key, l_arm_key, legs_key)
        _world_counter_inc(db, week_key, f"builds_{build_element}", 1)
        consumed_ids = [selected["head"], selected["r_arm"], selected["l_arm"], selected["legs"]]
        audit_log(
            db,
            AUDIT_EVENT_TYPES["BUILD_CONFIRM"],
            user_id=user["id"],
            request_id=getattr(g, "request_id", None),
            action_key="build_confirm",
            entity_type="robot_instance",
            entity_id=instance_id,
            payload={
                "robot_instance_id": instance_id,
                "robot_name": robot_name,
                "head_key": head_key,
                "r_arm_key": r_arm_key,
                "l_arm_key": l_arm_key,
                "legs_key": legs_key,
                "decor_asset_id": decor_asset_id,
                "combat_mode": combat_mode,
                "consumed_part_instance_ids": consumed_ids,
            },
            ip=request.remote_addr,
        )
        for pid in consumed_ids:
            audit_log(
                db,
                AUDIT_EVENT_TYPES["INVENTORY_DELTA"],
                user_id=user["id"],
                request_id=getattr(g, "request_id", None),
                action_key="build_confirm",
                entity_type="part_instance",
                entity_id=pid,
                delta_count=-1,
                payload={"reason": "build_confirm_consume", "robot_instance_id": instance_id},
                ip=request.remote_addr,
            )
        evaluate_referral_qualification(db, user["id"], request_ip=request.remote_addr)
        db.commit()
    except Exception as exc:
        db.rollback()
        session["message"] = str(exc)
        return redirect(url_for("build"))
    session["message"] = "完成ロボを登録し、出撃機体に設定しました。"
    return redirect(url_for("robots"))


@app.route("/robots/<int:instance_id>/rename", methods=["POST"])
@login_required
def robot_instance_rename(instance_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    new_name = request.form.get("robot_name", "").strip()
    rename_cost = 500
    if not new_name:
        session["message"] = "新しいロボ名を入力してください。"
        return redirect(url_for("robots"))
    target = db.execute(
        "SELECT id, name FROM robot_instances WHERE id = ? AND user_id = ?",
        (instance_id, user["id"]),
    ).fetchone()
    if not target:
        session["message"] = "改名対象が見つかりません。"
        return redirect(url_for("robots"))
    if user["coins"] < rename_cost:
        session["message"] = f"コイン不足です（改名コスト {rename_cost}）。"
        return redirect(url_for("robots"))
    db.execute("UPDATE users SET coins = coins - ? WHERE id = ?", (rename_cost, user["id"]))
    db.execute(
        "UPDATE robot_instances SET name = ?, updated_at = ? WHERE id = ?",
        (new_name, int(time.time()), instance_id),
    )
    audit_log(
        db,
        AUDIT_EVENT_TYPES["ROBOT_RENAME"],
        user_id=user["id"],
        request_id=getattr(g, "request_id", None),
        action_key="rename",
        entity_type="robot_instance",
        entity_id=instance_id,
        delta_coins=-rename_cost,
        payload={
            "robot_instance_id": instance_id,
            "old_name": target["name"],
            "new_name": new_name,
            "coin_cost": rename_cost,
        },
        ip=request.remote_addr,
    )
    audit_log(
        db,
        AUDIT_EVENT_TYPES["COIN_DELTA"],
        user_id=user["id"],
        request_id=getattr(g, "request_id", None),
        action_key="rename",
        entity_type="robot_instance",
        entity_id=instance_id,
        delta_coins=-rename_cost,
        payload={"source": "rename", "coin_cost": rename_cost},
        ip=request.remote_addr,
    )
    db.commit()
    session["message"] = f"ロボ名を変更しました（-{rename_cost} コイン）。"
    return redirect(url_for("robots"))


@app.route("/showcase")
@login_required
def showcase():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    sort_key = (request.args.get("sort") or "new").strip().lower()
    if sort_key == "likes":
        sort_key = "like"
    if sort_key not in SHOWCASE_SORT_OPTIONS:
        sort_key = "new"
    _ensure_qol_entitlement(db, user["id"])
    limits = _effective_limits(db, user)
    _ensure_showcase_slots(db, user["id"], limits["showcase_slots"])
    rows = _showcase_rows(db, user["id"])
    robots = db.execute(
        "SELECT id, name, status, composed_image_path FROM robot_instances WHERE user_id = ? ORDER BY updated_at DESC",
        (user["id"],),
    ).fetchall()
    public_rows = _showcase_query_rows(
        db,
        user_id=int(user["id"]),
        sort_key=sort_key,
        limit=80,
    )
    return render_template(
        "showcase.html",
        rows=rows,
        robots=robots,
        limits=limits,
        public_rows=public_rows,
        sort_key=sort_key,
        sort_options=tuple(SHOWCASE_SORT_OPTIONS),
        sort_defs=SHOWCASE_SORT_DEFS,
    )


@app.route("/showcase/set", methods=["POST"])
@login_required
def showcase_set():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    _ensure_qol_entitlement(db, user["id"])
    limits = _effective_limits(db, user)
    _ensure_showcase_slots(db, user["id"], limits["showcase_slots"])
    try:
        slot_no = int(request.form.get("slot_no", "0"))
    except ValueError:
        slot_no = 0
    robot_instance_id = request.form.get("robot_instance_id")
    if slot_no < 1 or slot_no > limits["showcase_slots"]:
        session["message"] = "無効なロボ展示枠です。"
        return redirect(url_for("showcase"))
    if robot_instance_id:
        target = db.execute(
            "SELECT id FROM robot_instances WHERE id = ? AND user_id = ?",
            (robot_instance_id, user["id"]),
        ).fetchone()
        if not target:
            session["message"] = "設定対象のロボが見つかりません。"
            return redirect(url_for("showcase"))
        db.execute(
            "UPDATE user_showcase SET robot_instance_id = ? WHERE user_id = ? AND slot_no = ?",
            (robot_instance_id, user["id"], slot_no),
        )
    else:
        db.execute(
            "UPDATE user_showcase SET robot_instance_id = NULL WHERE user_id = ? AND slot_no = ?",
            (user["id"], slot_no),
        )
    db.commit()
    session["message"] = "ロボ展示を更新しました。"
    return redirect(url_for("showcase"))


@app.route("/showcase/buy_slot", methods=["POST"])
@login_required
def showcase_buy_slot():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    _ensure_qol_entitlement(db, user["id"])
    ent = db.execute("SELECT * FROM qol_entitlements WHERE user_id = ?", (user["id"],)).fetchone()
    current = ent["showcase_slots"]
    if current >= 3:
        session["message"] = "ロボ展示枠は最大です。"
        return redirect(url_for("showcase"))
    next_slot = current + 1
    price = 5_000 if next_slot == 2 else 15_000
    if user["coins"] < price:
        session["message"] = f"コイン不足です（必要 {price}）。"
        return redirect(url_for("showcase"))
    db.execute("UPDATE users SET coins = coins - ? WHERE id = ?", (price, user["id"]))
    db.execute(
        "UPDATE qol_entitlements SET showcase_slots = ?, updated_at = ? WHERE user_id = ?",
        (next_slot, int(time.time()), user["id"]),
    )
    _ensure_showcase_slots(db, user["id"], next_slot)
    audit_log(
        db,
        AUDIT_EVENT_TYPES["SHOWCASE_EXPAND"],
        user_id=user["id"],
        request_id=getattr(g, "request_id", None),
        action_key="showcase_expand",
        entity_type="user",
        entity_id=user["id"],
        delta_coins=-price,
        delta_count=1,
        payload={
            "from_slots": current,
            "to_slots": next_slot,
            "coin_cost": price,
        },
        ip=request.remote_addr,
    )
    audit_log(
        db,
        AUDIT_EVENT_TYPES["COIN_DELTA"],
        user_id=user["id"],
        request_id=getattr(g, "request_id", None),
        action_key="showcase_expand",
        delta_coins=-price,
        payload={"source": "showcase_expand", "coin_cost": price},
        ip=request.remote_addr,
    )
    db.commit()
    session["message"] = f"ロボ展示枠を拡張しました（-{price} コイン）。"
    return redirect(url_for("showcase"))


@app.route("/showcase/<int:robot_id>/like", methods=["POST"])
@login_required
def showcase_like(robot_id):
    db = get_db()
    row = db.execute(
        """
        SELECT id
        FROM robot_instances
        WHERE id = ? AND status = 'active' AND COALESCE(is_public, 1) = 1
        """,
        (int(robot_id),),
    ).fetchone()
    if not row:
        abort(404)
    existing = db.execute(
        """
        SELECT id
        FROM showcase_votes
        WHERE robot_id = ? AND user_id = ? AND vote_type = 'like'
        LIMIT 1
        """,
        (int(robot_id), int(session["user_id"])),
    ).fetchone()
    if existing:
        db.execute("DELETE FROM showcase_votes WHERE id = ?", (int(existing["id"]),))
        toggled_on = False
    else:
        db.execute(
            """
            INSERT INTO showcase_votes (robot_id, user_id, vote_type, created_at)
            VALUES (?, ?, 'like', ?)
            ON CONFLICT(robot_id, user_id, vote_type) DO NOTHING
            """,
            (int(robot_id), int(session["user_id"]), int(time.time())),
        )
        toggled_on = True
    audit_log(
        db,
        AUDIT_EVENT_TYPES["SHOWCASE_LIKE"],
        user_id=int(session["user_id"]),
        request_id=getattr(g, "request_id", None),
        action_key="showcase_like",
        entity_type="robot_instance",
        entity_id=int(robot_id),
        delta_count=(1 if toggled_on else -1),
        payload={"robot_id": int(robot_id), "vote_type": "like", "toggled_on": bool(toggled_on)},
        ip=request.remote_addr,
    )
    db.commit()
    sort_key = (request.form.get("sort") or request.args.get("sort") or "new").strip().lower()
    if sort_key == "likes":
        sort_key = "like"
    if sort_key not in SHOWCASE_SORT_OPTIONS:
        sort_key = "new"
    return redirect(url_for("showcase", sort=sort_key))


@app.route("/lab")
@login_required
def lab_home():
    db = get_db()
    user = db.execute("SELECT id, is_admin FROM users WHERE id = ?", (int(session["user_id"]),)).fetchone()
    latest_race = _lab_casino_latest_race(db, status="finished")
    latest_results = _lab_casino_results(db, latest_race["id"])[:3] if latest_race else []
    showcase_rows = _lab_showcase_query_rows(db, viewer_user_id=int(user["id"]), sort_key="popular", limit=4)
    world_items = _lab_recent_world_items(db, limit=6)
    counts = {
        "approved_submissions": int(
            db.execute("SELECT COUNT(*) AS c FROM lab_robot_submissions WHERE status = 'approved'").fetchone()["c"] or 0
        ),
        "pending_submissions": int(
            db.execute("SELECT COUNT(*) AS c FROM lab_robot_submissions WHERE status = 'pending'").fetchone()["c"] or 0
        ),
        "race_count": int(db.execute("SELECT COUNT(*) AS c FROM lab_casino_races").fetchone()["c"] or 0),
    }
    return render_template(
        "lab.html",
        latest_race=latest_race,
        latest_results=latest_results,
        showcase_rows=showcase_rows,
        world_items=world_items,
        counts=counts,
        is_admin=bool(int(user["is_admin"] or 0) == 1),
    )


@app.route("/lab/race/legacy")
@login_required
def lab_race_legacy():
    db = get_db()
    user = db.execute("SELECT id FROM users WHERE id = ?", (int(session["user_id"]),)).fetchone()
    latest_race = _lab_latest_race(db)
    latest_results = _lab_race_results(db, latest_race["id"]) if latest_race and latest_race["status"] == "finished" else []
    rankings = _lab_race_rankings(db, limit=5)
    return render_template(
        "lab_race.html",
        robot_choices=_lab_user_robot_choices(db, int(user["id"])),
        latest_race=latest_race,
        latest_results=latest_results[:LAB_RACE_ENTRY_TARGET],
        rankings=rankings,
        course_defs=visible_lab_course_defs(),
        default_course_key=_lab_default_course_key(),
    )


@app.route("/lab/race/entry", methods=["POST"])
@app.route("/lab/race/legacy/entry", methods=["POST"])
@login_required
def lab_race_entry():
    db = get_db()
    user_id = int(session["user_id"])
    robot_instance_id = request.form.get("robot_instance_id", type=int)
    course_key = (request.form.get("course_key") or _lab_default_course_key()).strip().lower()
    if not robot_instance_id:
        flash("参加するロボを選択してください。", "error")
        return redirect(url_for("lab_race_legacy"))
    snapshot = _lab_entry_snapshot_from_robot(db, user_id, robot_instance_id)
    if not snapshot:
        flash("参加対象のロボが見つからないか、能力計算に失敗しました。", "error")
        return redirect(url_for("lab_race_legacy"))
    race_id = _lab_create_race(db, course_key=course_key)
    db.execute(
        """
        INSERT INTO lab_race_entries
        (
            race_id, user_id, source_type, robot_instance_id, submission_id,
            display_name, icon_path, hp, atk, def, spd, acc, cri, entry_order
        )
        VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            int(race_id),
            user_id,
            snapshot["source_type"],
            int(snapshot["robot_instance_id"]),
            snapshot["display_name"],
            snapshot["icon_path"],
            int(snapshot["hp"]),
            int(snapshot["atk"]),
            int(snapshot["def"]),
            int(snapshot["spd"]),
            int(snapshot["acc"]),
            int(snapshot["cri"]),
        ),
    )
    audit_log(
        db,
        AUDIT_EVENT_TYPES["LAB_RACE_ENTRY"],
        user_id=user_id,
        request_id=getattr(g, "request_id", None),
        action_key="lab_race_entry",
        entity_type="lab_race",
        entity_id=int(race_id),
        payload={
            "race_id": int(race_id),
            "robot_instance_id": int(snapshot["robot_instance_id"]),
            "robot_name": snapshot["display_name"],
            "course_key": _lab_course_meta(course_key)["key"],
        },
        ip=request.remote_addr,
    )
    _lab_start_race(db, race_id, actor_user_id=user_id)
    db.commit()
    flash("観戦レースを開始しました。固定6レーンで、空き枠は LAB ENEMY が補完します。", "notice")
    return redirect(url_for("lab_race_legacy_watch", race_id=int(race_id)))


@app.route("/lab/race/legacy/watch/<int:race_id>")
@login_required
def lab_race_legacy_watch(race_id):
    db = get_db()
    race = _lab_fetch_race(db, race_id)
    if not race:
        abort(404)
    course = _lab_course_payload_from_race(race, mode="standard")
    frames = _lab_race_frames(db, race_id)
    watch_entries = _lab_race_entries(db, race_id)
    current_user_id = int(session.get("user_id") or 0)
    for item in watch_entries:
        item["is_user_entry"] = bool(int(item.get("user_id") or 0) == current_user_id)
    user_entry = next((item for item in watch_entries if item.get("is_user_entry")), None)
    lane_count = max(LAB_RACE_ENTRY_TARGET, len(watch_entries))
    results = _lab_race_results(db, race_id)
    return render_template(
        "lab_race_watch.html",
        race=race,
        course=course,
        frames=frames,
        watch_entries=watch_entries,
        user_entry=user_entry,
        lane_count=lane_count,
        results=results,
        watch_mode="standard",
        focus_chip_label="YOU",
        focus_title="あなたの出走ロボ",
        focus_line=(f"{user_entry['display_name']} / {user_entry['owner_label']}" if user_entry else None),
        support_line="この観戦レースでは本編ロボが1体参加し、残りは LAB ENEMY が補完します。",
        bet_row=None,
    )


@app.route("/lab/race/results/<int:race_id>")
@login_required
def lab_race_legacy_results_view(race_id):
    db = get_db()
    race = _lab_fetch_race(db, race_id)
    if not race:
        abort(404)
    return render_template(
        "lab_race_results.html",
        race=race,
        course=_lab_course_payload_from_race(race, mode="standard"),
        results=_lab_race_results(db, race_id),
    )


@app.route("/lab/race/rankings")
@login_required
def lab_race_legacy_rankings():
    db = get_db()
    rankings = _lab_race_rankings(db, limit=20)
    return render_template("lab_race_rankings.html", rankings=rankings)


@app.route("/lab/race")
@login_required
def lab_race():
    db = get_db()
    user_id = int(session["user_id"])
    daily_info = _lab_casino_apply_daily_grant_if_needed(db, user_id)
    race = _lab_casino_ensure_open_race(db)
    db.commit()
    user_bet = _lab_casino_user_bet(db, race["id"], user_id)
    if user_bet and race["status"] == "finished":
        return redirect(url_for("lab_race_watch", race_id=int(race["id"])))
    return render_template(
        "lab_casino_race.html",
        race=race,
        course=_lab_course_payload_from_race(race, mode="casino"),
        wallet=_lab_casino_wallet_row(db, user_id),
        daily_info=daily_info,
        entries=_lab_casino_entries(db, race["id"]),
        bet_amounts=LAB_CASINO_BET_AMOUNTS,
        user_bet=user_bet,
    )


@app.route("/lab/race/bet", methods=["POST"])
@login_required
def lab_race_place_bet():
    db = get_db()
    user_id = int(session["user_id"])
    _lab_casino_apply_daily_grant_if_needed(db, user_id)
    race_id = request.form.get("race_id", type=int)
    entry_id = request.form.get("entry_id", type=int)
    amount = request.form.get("amount", type=int)
    if amount not in LAB_CASINO_BET_AMOUNTS:
        flash("予想額は 10 / 50 / 100 から選んでください。", "error")
        db.commit()
        return redirect(url_for("lab_race"))
    race = _lab_casino_fetch_race(db, race_id)
    if not race or race["status"] != "betting":
        flash("このレースは締め切り済みです。次のレースへどうぞ。", "notice")
        db.commit()
        return redirect(url_for("lab_race"))
    if _lab_casino_user_bet(db, race_id, user_id):
        flash("このレースはすでに予想済みです。", "notice")
        db.commit()
        return redirect(url_for("lab_race_watch", race_id=int(race_id)))
    entry = db.execute(
        "SELECT * FROM lab_casino_entries WHERE id = ? AND race_id = ? LIMIT 1",
        (int(entry_id or 0), int(race_id)),
    ).fetchone()
    if not entry:
        flash("出走ロボが見つかりませんでした。", "error")
        db.commit()
        return redirect(url_for("lab_race"))
    wallet = _lab_casino_wallet_row(db, user_id)
    if not wallet or int(wallet["lab_coin"] or 0) < int(amount):
        flash("ラボコインが足りません。", "error")
        db.commit()
        return redirect(url_for("lab_race"))
    before_coin, after_coin = _lab_casino_adjust_coins(db, user_id, -int(amount), cap=None)
    now_ts = int(time.time())
    cur = db.execute(
        """
        INSERT INTO lab_casino_bets (user_id, race_id, entry_id, amount, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, int(race_id), int(entry_id), int(amount), now_ts),
    )
    bet_id = int(cur.lastrowid)
    audit_log(
        db,
        AUDIT_EVENT_TYPES["LAB_CASINO_BET_PLACE"],
        user_id=user_id,
        request_id=getattr(g, "request_id", None),
        action_key="lab_casino_bet_place",
        entity_type="lab_casino_bet",
        entity_id=bet_id,
        delta_coins=-int(amount),
        payload={
            "race_id": int(race_id),
            "entry_id": int(entry_id),
            "bot_key": entry["bot_key"],
            "amount": int(amount),
            "odds": float(entry["odds"]),
            "lab_coin_before": int(before_coin),
            "lab_coin_after": int(after_coin),
        },
        ip=request.remote_addr,
    )
    _lab_casino_resolve_race(db, race_id, actor_user_id=user_id)
    db.commit()
    flash(f"{entry['display_name']} に {int(amount)} ラボコインで予想しました。", "notice")
    return redirect(url_for("lab_race_watch", race_id=int(race_id)))


@app.route("/lab/race/watch/<int:race_id>")
@login_required
def lab_race_watch(race_id):
    db = get_db()
    user_id = int(session["user_id"])
    race = _lab_casino_fetch_race(db, race_id)
    if not race:
        abort(404)
    if race["status"] != "finished":
        race = _lab_casino_resolve_race(db, race_id, actor_user_id=user_id)
        db.commit()
    frames = _lab_casino_frames(db, race_id)
    watch_entries = _lab_casino_entries(db, race_id)
    bet_row = _lab_casino_user_bet(db, race_id, user_id)
    for item in watch_entries:
        item["is_user_entry"] = bool(bet_row and int(item["id"]) == int(bet_row["entry_id"]))
    focus_entry = next((item for item in watch_entries if item.get("is_user_entry")), None)
    course = _lab_course_payload_from_race(race, mode="casino")
    return render_template(
        "lab_race_watch.html",
        race=race,
        course=course,
        frames=frames,
        watch_entries=watch_entries,
        user_entry=focus_entry,
        lane_count=LAB_CASINO_ENTRY_TARGET,
        results=_lab_casino_results(db, race_id),
        watch_mode="enemy_race",
        focus_chip_label="予想",
        focus_title="あなたの予想",
        focus_line=(f"{bet_row['display_name']} / {bet_row['amount']} / 倍率 {bet_row['odds_text']}" if bet_row else None),
        support_line=(
            f"的中で払い戻し、外れても観戦ボーナス +{int(LAB_CASINO_WATCH_BONUS)}"
            if bet_row
            else "まずは1体選ぶと、ここがあなたの予想レーンになります。"
        ),
        bet_row=bet_row,
    )


@app.route("/lab/race/result/<int:race_id>")
@login_required
def lab_race_result(race_id):
    db = get_db()
    user_id = int(session["user_id"])
    race = _lab_casino_fetch_race(db, race_id)
    if not race:
        abort(404)
    if race["status"] != "finished":
        race = _lab_casino_resolve_race(db, race_id, actor_user_id=user_id)
        db.commit()
    return render_template(
        "lab_casino_result.html",
        race=race,
        course=_lab_course_payload_from_race(race, mode="casino"),
        wallet=_lab_casino_wallet_row(db, user_id),
        results=_lab_casino_results(db, race_id),
        bet_row=_lab_casino_user_bet(db, race_id, user_id),
        watch_bonus=int(LAB_CASINO_WATCH_BONUS),
    )


@app.route("/lab/race/prizes")
@login_required
def lab_race_prizes():
    db = get_db()
    user_id = int(session["user_id"])
    daily_info = _lab_casino_apply_daily_grant_if_needed(db, user_id)
    db.commit()
    claim_rows = db.execute(
        """
        SELECT c.created_at, p.name, p.prize_type
        FROM lab_casino_prize_claims c
        JOIN lab_casino_prizes p ON p.id = c.prize_id
        WHERE c.user_id = ?
        ORDER BY c.created_at DESC, c.id DESC
        LIMIT 8
        """,
        (user_id,),
    ).fetchall()
    return render_template(
        "lab_casino_prizes.html",
        wallet=_lab_casino_wallet_row(db, user_id),
        daily_info=daily_info,
        prizes=_lab_casino_prize_rows(db, user_id=user_id),
        claim_rows=[
            {"name": row["name"], "prize_type": row["prize_type"], "created_text": _format_jst_ts(row["created_at"])}
            for row in claim_rows
        ],
    )


@app.route("/lab/race/prizes/<int:prize_id>/claim", methods=["POST"])
@login_required
def lab_race_prize_claim(prize_id):
    db = get_db()
    user_id = int(session["user_id"])
    prize = db.execute(
        "SELECT * FROM lab_casino_prizes WHERE id = ? AND is_active = 1 LIMIT 1",
        (int(prize_id),),
    ).fetchone()
    if not prize:
        abort(404)
    existing = db.execute(
        """
        SELECT id
        FROM lab_casino_prize_claims
        WHERE user_id = ? AND prize_id = ?
        LIMIT 1
        """,
        (user_id, int(prize_id)),
    ).fetchone()
    if existing:
        flash("この景品はすでに交換済みです。", "notice")
        return redirect(url_for("lab_race_prizes"))
    wallet = _lab_casino_wallet_row(db, user_id)
    cost = int(prize["cost_lab_coin"])
    if not wallet or int(wallet["lab_coin"] or 0) < cost:
        flash("ラボコインが足りません。", "error")
        return redirect(url_for("lab_race_prizes"))
    before_coin, after_coin = _lab_casino_adjust_coins(db, user_id, -cost, cap=None)
    now_ts = int(time.time())
    cur = db.execute(
        """
        INSERT INTO lab_casino_prize_claims (user_id, prize_id, cost_lab_coin, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, int(prize_id), cost, now_ts),
    )
    audit_log(
        db,
        AUDIT_EVENT_TYPES["LAB_CASINO_PRIZE_CLAIM"],
        user_id=user_id,
        request_id=getattr(g, "request_id", None),
        action_key="lab_casino_prize_claim",
        entity_type="lab_casino_prize_claim",
        entity_id=int(cur.lastrowid),
        delta_coins=-cost,
        payload={
            "prize_id": int(prize_id),
            "prize_key": prize["prize_key"],
            "cost_lab_coin": cost,
            "lab_coin_before": int(before_coin),
            "lab_coin_after": int(after_coin),
        },
        ip=request.remote_addr,
    )
    db.commit()
    flash(f"{prize['name']} を交換しました。", "notice")
    return redirect(url_for("lab_race_prizes"))


@app.route("/lab/race/history")
@login_required
def lab_race_history():
    db = get_db()
    user_id = int(session["user_id"])
    daily_info = _lab_casino_apply_daily_grant_if_needed(db, user_id)
    db.commit()
    return render_template(
        "lab_casino_history.html",
        wallet=_lab_casino_wallet_row(db, user_id),
        daily_info=daily_info,
        rows=_lab_casino_history_rows(db, user_id),
    )


@app.route("/lab/casino")
@login_required
def lab_casino_home():
    return redirect(url_for("lab_race"))


@app.route("/lab/casino/race")
@login_required
def lab_casino_race():
    return redirect(url_for("lab_race"))


@app.route("/lab/casino/race/bet", methods=["POST"])
@login_required
def lab_casino_place_bet():
    return redirect(url_for("lab_race_place_bet"), code=307)


@app.route("/lab/casino/race/watch/<int:race_id>")
@login_required
def lab_casino_watch(race_id):
    return redirect(url_for("lab_race_watch", race_id=int(race_id)))


@app.route("/lab/casino/race/result/<int:race_id>")
@login_required
def lab_casino_result(race_id):
    return redirect(url_for("lab_race_result", race_id=int(race_id)))


@app.route("/lab/casino/prizes")
@login_required
def lab_casino_prizes():
    return redirect(url_for("lab_race_prizes"))


@app.route("/lab/casino/prizes/<int:prize_id>/claim", methods=["POST"])
@login_required
def lab_casino_prize_claim(prize_id):
    return redirect(url_for("lab_race_prize_claim", prize_id=int(prize_id)), code=307)


@app.route("/lab/casino/history")
@login_required
def lab_casino_history():
    return redirect(url_for("lab_race_history"))


@app.route("/lab/upload", methods=["GET", "POST"])
@login_required
def lab_upload():
    db = get_db()
    user_id = int(session["user_id"])
    message = None
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        comment = (request.form.get("comment") or "").strip()
        image = request.files.get("image")
        if not title:
            message = "タイトルを入力してください。"
        elif not comment:
            message = "一言コメントを入力してください。"
        else:
            ok, err, image_path, thumb_path = _lab_save_submission_image(image)
            if not ok:
                message = err
            else:
                now_ts = int(time.time())
                cur = db.execute(
                    """
                    INSERT INTO lab_robot_submissions
                    (user_id, title, comment, image_path, thumb_path, status, moderation_note, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'pending', NULL, ?, ?)
                    """,
                    (user_id, title[:80], comment[:200], image_path, thumb_path, now_ts, now_ts),
                )
                submission_id = int(cur.lastrowid)
                audit_log(
                    db,
                    AUDIT_EVENT_TYPES["LAB_SUBMISSION_CREATE"],
                    user_id=user_id,
                    request_id=getattr(g, "request_id", None),
                    action_key="lab_submission_create",
                    entity_type="lab_submission",
                    entity_id=submission_id,
                    payload={"submission_id": submission_id, "title": title[:80]},
                    ip=request.remote_addr,
                )
                db.commit()
                flash("投稿を受け付けました。公開は承認後です。", "notice")
                return redirect(url_for("lab_upload"))
    return render_template(
        "lab_upload.html",
        message=message,
        recent_rows=_lab_submission_recent_rows(db, user_id),
    )


@app.route("/lab/showcase")
@login_required
def lab_showcase():
    db = get_db()
    sort_key = (request.args.get("sort") or "new").strip().lower()
    if sort_key not in LAB_SUBMISSION_SORT_OPTIONS:
        sort_key = "new"
    return render_template(
        "lab_showcase.html",
        rows=_lab_showcase_query_rows(db, viewer_user_id=int(session["user_id"]), sort_key=sort_key, limit=48),
        sort_key=sort_key,
        sort_defs=LAB_SUBMISSION_SORT_DEFS,
    )


@app.route("/lab/showcase/<int:submission_id>")
@login_required
def lab_submission_detail(submission_id):
    db = get_db()
    is_admin = _is_admin_user(session["user_id"])
    row = _lab_submission_detail_row(
        db,
        submission_id,
        viewer_user_id=int(session["user_id"]),
        is_admin=is_admin,
    )
    if not row:
        abort(404)
    reports = []
    if is_admin:
        reports = db.execute(
            """
            SELECT user_id, reason, created_at
            FROM lab_submission_reports
            WHERE submission_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 20
            """,
            (int(submission_id),),
        ).fetchall()
    return render_template(
        "lab_submission_detail.html",
        row=row,
        report_reason_defs=LAB_REPORT_REASON_DEFS,
        admin_reports=[
            {
                "user_label": _feed_user_label(db, report["user_id"]),
                "reason_label": _lab_report_reason_label(report["reason"]),
                "created_at": _format_jst_ts(report["created_at"]),
            }
            for report in reports
        ],
        is_admin=is_admin,
    )


@app.route("/lab/showcase/<int:submission_id>/like", methods=["POST"])
@login_required
def lab_submission_like(submission_id):
    db = get_db()
    row = db.execute(
        "SELECT id, user_id, title, status FROM lab_robot_submissions WHERE id = ? LIMIT 1",
        (int(submission_id),),
    ).fetchone()
    if not row or row["status"] != "approved":
        abort(404)
    existing = db.execute(
        """
        SELECT id
        FROM lab_submission_likes
        WHERE submission_id = ? AND user_id = ?
        LIMIT 1
        """,
        (int(submission_id), int(session["user_id"])),
    ).fetchone()
    if existing:
        flash("この投稿には既にいいねしています。", "notice")
    else:
        db.execute(
            """
            INSERT INTO lab_submission_likes (submission_id, user_id, created_at)
            VALUES (?, ?, ?)
            """,
            (int(submission_id), int(session["user_id"]), int(time.time())),
        )
        audit_log(
            db,
            AUDIT_EVENT_TYPES["LAB_SUBMISSION_LIKE"],
            user_id=int(session["user_id"]),
            request_id=getattr(g, "request_id", None),
            action_key="lab_submission_like",
            entity_type="lab_submission",
            entity_id=int(submission_id),
            delta_count=1,
            payload={"submission_id": int(submission_id)},
            ip=request.remote_addr,
        )
        likes_count = int(
            db.execute(
                "SELECT COUNT(*) AS c FROM lab_submission_likes WHERE submission_id = ?",
                (int(submission_id),),
            ).fetchone()["c"]
            or 0
        )
        already_world_logged = db.execute(
            """
            SELECT 1
            FROM world_events_log
            WHERE event_type = 'LAB_RACE_POPULAR_ENTRY'
              AND CAST(COALESCE(json_extract(payload_json, '$.submission_id'), 0) AS INTEGER) = ?
            LIMIT 1
            """,
            (int(submission_id),),
        ).fetchone()
        if likes_count >= 3 and not already_world_logged:
            _lab_world_event_log(
                db,
                "LAB_RACE_POPULAR_ENTRY",
                {
                    "submission_id": int(submission_id),
                    "title": row["title"],
                    "username": _feed_user_label(db, row["user_id"]),
                    "likes_count": likes_count,
                },
            )
        db.commit()
        flash("いいねしました。", "notice")
    return redirect(url_for("lab_submission_detail", submission_id=int(submission_id)))


@app.route("/lab/showcase/<int:submission_id>/report", methods=["POST"])
@login_required
def lab_submission_report(submission_id):
    db = get_db()
    row = db.execute(
        "SELECT id, status FROM lab_robot_submissions WHERE id = ? LIMIT 1",
        (int(submission_id),),
    ).fetchone()
    if not row or row["status"] != "approved":
        abort(404)
    reason = (request.form.get("reason") or "").strip().lower()
    if reason not in {item[0] for item in LAB_REPORT_REASON_DEFS}:
        reason = "other"
    db.execute(
        """
        INSERT INTO lab_submission_reports (submission_id, user_id, reason, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (int(submission_id), int(session["user_id"]), reason, int(time.time())),
    )
    audit_log(
        db,
        AUDIT_EVENT_TYPES["LAB_SUBMISSION_REPORT"],
        user_id=int(session["user_id"]),
        request_id=getattr(g, "request_id", None),
        action_key="lab_submission_report",
        entity_type="lab_submission",
        entity_id=int(submission_id),
        payload={"submission_id": int(submission_id), "reason": reason},
        ip=request.remote_addr,
    )
    db.commit()
    flash("通報を受け付けました。確認後に対応します。", "notice")
    return redirect(url_for("lab_submission_detail", submission_id=int(submission_id)))


@app.route("/admin/lab")
@login_required
def admin_lab():
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    counts = {
        "pending": int(db.execute("SELECT COUNT(*) AS c FROM lab_robot_submissions WHERE status = 'pending'").fetchone()["c"] or 0),
        "approved": int(db.execute("SELECT COUNT(*) AS c FROM lab_robot_submissions WHERE status = 'approved'").fetchone()["c"] or 0),
        "disabled": int(db.execute("SELECT COUNT(*) AS c FROM lab_robot_submissions WHERE status = 'disabled'").fetchone()["c"] or 0),
        "races": int(db.execute("SELECT COUNT(*) AS c FROM lab_races").fetchone()["c"] or 0),
        "casino_races": int(db.execute("SELECT COUNT(*) AS c FROM lab_casino_races").fetchone()["c"] or 0),
    }
    latest_races = db.execute(
        """
        SELECT id, status, course_key, created_at, finished_at
        FROM lab_races
        ORDER BY id DESC
        LIMIT 10
        """
    ).fetchall()
    return render_template("admin_lab.html", counts=counts, latest_races=latest_races)


@app.route("/admin/lab/race")
@login_required
def admin_lab_race():
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    day_key = _lab_casino_day_key()
    day_start = int(datetime.strptime(day_key, "%Y-%m-%d").replace(tzinfo=JST).timestamp())
    day_end = int((datetime.strptime(day_key, "%Y-%m-%d").replace(tzinfo=JST) + timedelta(days=1)).timestamp())
    counts = {
        "betting": int(db.execute("SELECT COUNT(*) AS c FROM lab_casino_races WHERE status = 'betting'").fetchone()["c"] or 0),
        "finished": int(db.execute("SELECT COUNT(*) AS c FROM lab_casino_races WHERE status = 'finished'").fetchone()["c"] or 0),
        "bets": int(db.execute("SELECT COUNT(*) AS c FROM lab_casino_bets").fetchone()["c"] or 0),
        "claims": int(db.execute("SELECT COUNT(*) AS c FROM lab_casino_prize_claims").fetchone()["c"] or 0),
        "total_lab_coin": int(db.execute("SELECT COALESCE(SUM(lab_coin), 0) AS c FROM users").fetchone()["c"] or 0),
        "daily_grants_today": int(
            db.execute(
                """
                SELECT COUNT(*) AS c
                FROM world_events_log
                WHERE event_type = ?
                  AND created_at >= ?
                  AND created_at < ?
                """,
                (AUDIT_EVENT_TYPES["LAB_CASINO_DAILY_GRANT"], day_start, day_end),
            ).fetchone()["c"]
            or 0
        ),
    }
    latest_races = db.execute(
        """
        SELECT
            r.id,
            r.status,
            r.created_at,
            r.finished_at,
            COUNT(b.id) AS bet_count
        FROM lab_casino_races r
        LEFT JOIN lab_casino_bets b ON b.race_id = r.id
        GROUP BY r.id
        ORDER BY r.id DESC
        LIMIT 12
        """
    ).fetchall()
    recent_claims = db.execute(
        """
        SELECT c.created_at, c.cost_lab_coin, u.username, p.name, p.prize_key
        FROM lab_casino_prize_claims c
        JOIN users u ON u.id = c.user_id
        JOIN lab_casino_prizes p ON p.id = c.prize_id
        ORDER BY c.created_at DESC, c.id DESC
        LIMIT 12
        """
    ).fetchall()
    return render_template(
        "admin_lab_casino.html",
        counts=counts,
        latest_races=[
            {
                "id": int(row["id"]),
                "status": row["status"],
                "bet_count": int(row["bet_count"] or 0),
                "created_text": _format_jst_ts(row["created_at"]),
                "finished_text": _format_jst_ts(row["finished_at"]),
            }
            for row in latest_races
        ],
        recent_claims=[
            {
                "username": row["username"],
                "name": row["name"],
                "prize_key": row["prize_key"],
                "cost_lab_coin": int(row["cost_lab_coin"]),
                "created_text": _format_jst_ts(row["created_at"]),
            }
            for row in recent_claims
        ],
    )


@app.route("/admin/lab/casino")
@login_required
def admin_lab_casino():
    return redirect(url_for("admin_lab_race"))


@app.route("/admin/lab/submissions")
@login_required
def admin_lab_submissions():
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    status_filter = (request.args.get("status") or "pending").strip().lower()
    if status_filter not in {"pending", "approved", "rejected", "disabled"}:
        status_filter = "pending"
    return render_template(
        "admin_lab_submissions.html",
        rows=_lab_submission_pending_rows(db, status_filter=status_filter, limit=100),
        status_filter=status_filter,
        status_options=("pending", "approved", "rejected", "disabled"),
    )


def _admin_lab_submission_mutate(submission_id, *, action):
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    row = db.execute("SELECT * FROM lab_robot_submissions WHERE id = ? LIMIT 1", (int(submission_id),)).fetchone()
    if not row:
        abort(404)
    now_ts = int(time.time())
    note = (request.form.get("moderation_note") or "").strip()[:200]
    event_key = None
    if action == "approve":
        db.execute(
            """
            UPDATE lab_robot_submissions
            SET status = 'approved',
                moderation_note = ?,
                approved_at = ?,
                approved_by_user_id = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (note or None, now_ts, int(session["user_id"]), now_ts, int(submission_id)),
        )
        event_key = "LAB_SUBMISSION_APPROVE"
        flash("投稿を承認しました。", "notice")
    elif action == "reject":
        db.execute(
            """
            UPDATE lab_robot_submissions
            SET status = 'rejected',
                moderation_note = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (note or None, now_ts, int(submission_id)),
        )
        event_key = "LAB_SUBMISSION_REJECT"
        flash("投稿を差し戻しました。", "notice")
    elif action == "disable":
        db.execute(
            """
            UPDATE lab_robot_submissions
            SET status = 'disabled',
                moderation_note = ?,
                disabled_at = ?,
                disabled_by_user_id = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (note or None, now_ts, int(session["user_id"]), now_ts, int(submission_id)),
        )
        event_key = "LAB_SUBMISSION_DISABLE"
        flash("投稿を停止しました。", "notice")
    audit_log(
        db,
        AUDIT_EVENT_TYPES[event_key],
        user_id=int(session["user_id"]),
        request_id=getattr(g, "request_id", None),
        action_key=f"lab_submission_{action}",
        entity_type="lab_submission",
        entity_id=int(submission_id),
        payload={"submission_id": int(submission_id), "title": row["title"], "note": note or None},
        ip=request.remote_addr,
    )
    db.commit()
    return redirect(url_for("admin_lab_submissions", status=(request.args.get("status") or request.form.get("status") or "pending")))


@app.route("/admin/lab/submissions/<int:submission_id>/approve", methods=["POST"])
@login_required
def admin_lab_submission_approve(submission_id):
    return _admin_lab_submission_mutate(submission_id, action="approve")


@app.route("/admin/lab/submissions/<int:submission_id>/reject", methods=["POST"])
@login_required
def admin_lab_submission_reject(submission_id):
    return _admin_lab_submission_mutate(submission_id, action="reject")


@app.route("/admin/lab/submissions/<int:submission_id>/disable", methods=["POST"])
@login_required
def admin_lab_submission_disable(submission_id):
    return _admin_lab_submission_mutate(submission_id, action="disable")


@app.route("/ranking")
@login_required
def ranking():
    db = get_db()
    metric_key = (request.args.get("metric") or "wins").strip().lower()
    if metric_key not in RANKING_METRIC_DEF_BY_KEY:
        metric_key = "wins"
    week_key = _world_week_key()
    rows, metric = _ranking_rows(db, metric_key, limit=50, week_key=week_key)
    row_kind = str(metric.get("row_kind") or "user")
    if row_kind == "user":
        rows = _decorate_user_rows(db, rows, user_key="id")
    return render_template(
        "ranking.html",
        rows=rows,
        metric_key=metric_key,
        metric=metric,
        metric_defs=RANKING_METRIC_DEFS,
        week_key=week_key,
        row_kind=row_kind,
    )


@app.route("/dex/enemies")
@login_required
def enemy_dex():
    db = get_db()
    rows = db.execute(
        """
        SELECT d.enemy_key, d.first_seen_at, d.first_defeated_at, d.seen_count, d.defeat_count,
               e.name_ja, e.image_path, e.tier, e.element, e.faction, e.is_boss
        FROM user_enemy_dex d
        LEFT JOIN enemies e ON e.key = d.enemy_key
        WHERE d.user_id = ?
        ORDER BY d.seen_count DESC, d.enemy_key ASC
        """,
        (session["user_id"],),
    ).fetchall()
    cards = []
    for row in rows:
        name_ja = row["name_ja"] if int(row["defeat_count"] or 0) > 0 else "？？？"
        image_url = url_for("static", filename=_enemy_image_rel(row["image_path"]))
        cards.append(
            {
                "enemy_key": row["enemy_key"],
                "name_ja": name_ja,
                "seen_count": int(row["seen_count"] or 0),
                "defeat_count": int(row["defeat_count"] or 0),
                "is_boss": bool(int(row["is_boss"] or 0)),
                "image_url": image_url,
            }
        )
    return render_template("enemy_dex.html", cards=cards)


@app.route("/dex/enemies/<enemy_key>")
@login_required
def enemy_dex_detail(enemy_key):
    db = get_db()
    dex_row = db.execute(
        """
        SELECT enemy_key, first_seen_at, first_defeated_at, seen_count, defeat_count
        FROM user_enemy_dex
        WHERE user_id = ? AND enemy_key = ?
        """,
        (session["user_id"], enemy_key),
    ).fetchone()
    if not dex_row:
        return abort(404)
    enemy = db.execute("SELECT * FROM enemies WHERE key = ?", (enemy_key,)).fetchone()
    if not enemy:
        return abort(404)
    show_stats = int(dex_row["defeat_count"] or 0) > 0
    image_url = url_for("static", filename=_enemy_image_rel(enemy["image_path"]))
    return render_template(
        "enemy_dex_detail.html",
        enemy=enemy,
        dex=dex_row,
        show_stats=show_stats,
        image_url=image_url,
    )


@app.route("/parts")
@login_required
def parts():
    db = get_db()
    user_id = int(session["user_id"])
    user_row = db.execute(
        "SELECT id, is_admin, max_unlocked_layer, part_inventory_limit FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    selected_part_type = _normalize_part_type_filter(request.args.get("part_type"))
    page = max(1, int(request.args.get("page", "1")))
    per_page = 24
    offset = (page - 1) * per_page
    where_clauses = ["pi.user_id = ?", "pi.status IN ('inventory', 'equipped')"]
    params = [user_id]
    if selected_part_type:
        where_clauses.append("rp.part_type = ?")
        params.append(selected_part_type)
    where_sql = " AND ".join(where_clauses)

    rows = db.execute(
        """
        SELECT pi.*, rp.part_type, rp.key AS part_key, rp.image_path, rp.display_name_ja
        FROM part_instances pi
        JOIN robot_parts rp ON rp.id = pi.part_id
        WHERE """
        + where_sql
        + """
        ORDER BY
            CASE WHEN pi.status = 'equipped' THEN 0 ELSE 1 END ASC,
            CASE rp.part_type
                WHEN 'HEAD' THEN 1
                WHEN 'RIGHT_ARM' THEN 2
                WHEN 'LEFT_ARM' THEN 3
                WHEN 'LEGS' THEN 4
                ELSE 9
            END ASC,
            CASE UPPER(COALESCE(pi.rarity, 'N'))
                WHEN 'UR' THEN 5
                WHEN 'SSR' THEN 4
                WHEN 'SR' THEN 3
                WHEN 'R' THEN 2
                ELSE 1
            END DESC,
            pi.plus DESC,
            pi.id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, per_page, offset],
    ).fetchall()
    total = db.execute(
        """
        SELECT COUNT(*) AS c
        FROM part_instances pi
        JOIN robot_parts rp ON rp.id = pi.part_id
        WHERE """
        + where_sql,
        params,
    ).fetchone()["c"]
    summary = db.execute(
        """
        SELECT
            SUM(CASE WHEN pi.status = 'inventory' THEN 1 ELSE 0 END) AS inventory_count,
            SUM(CASE WHEN pi.status = 'equipped' THEN 1 ELSE 0 END) AS equipped_count
        FROM part_instances pi
        JOIN robot_parts rp ON rp.id = pi.part_id
        WHERE """
        + where_sql,
        params,
    ).fetchone()
    items = [_part_card_payload(r) for r in rows]
    protect_core = _get_user_item_qty(db, user_id, "protect_core")
    inventory_space_remaining = _inventory_space_remaining(db, user_id, user_row=user_row)
    overflow_rows = db.execute(
        """
        SELECT pi.*, rp.part_type, rp.key AS part_key, rp.image_path, rp.display_name_ja
        FROM part_instances pi
        JOIN robot_parts rp ON rp.id = pi.part_id
        WHERE pi.user_id = ? AND pi.status = 'overflow'
        """
        + (" AND rp.part_type = ?" if selected_part_type else "")
        + """
        ORDER BY
            CASE rp.part_type
                WHEN 'HEAD' THEN 1
                WHEN 'RIGHT_ARM' THEN 2
                WHEN 'LEFT_ARM' THEN 3
                WHEN 'LEGS' THEN 4
                ELSE 9
            END ASC,
            CASE UPPER(COALESCE(pi.rarity, 'N'))
                WHEN 'UR' THEN 5
                WHEN 'SSR' THEN 4
                WHEN 'SR' THEN 3
                WHEN 'R' THEN 2
                ELSE 1
            END DESC,
            pi.plus DESC,
            pi.id DESC
        """,
        ([user_id, selected_part_type] if selected_part_type else [user_id]),
    ).fetchall()
    overflow_items = [_part_card_payload(r, can_discard=False) for r in overflow_rows]
    overflow_total = len(overflow_items)
    legacy_where = ["upi.user_id = ?"]
    legacy_params = [user_id]
    if selected_part_type:
        legacy_where.append("upi.part_type = ?")
        legacy_params.append(selected_part_type)
    legacy_rows = db.execute(
        """
        SELECT upi.part_type, upi.part_key, COUNT(*) AS qty, rp.image_path, rp.rarity, rp.element, rp.display_name_ja
        FROM user_parts_inventory upi
        LEFT JOIN robot_parts rp ON rp.key = upi.part_key
        WHERE """
        + " AND ".join(legacy_where)
        + """
        GROUP BY upi.part_type, upi.part_key, rp.image_path
        ORDER BY upi.part_type, upi.part_key
        """,
        legacy_params,
    ).fetchall()
    legacy_items = []
    legacy_total = 0
    for r in legacy_rows:
        d = dict(r)
        d["display_name"] = _part_display_name_ja(
            d.get("part_key"),
            rarity=d.get("rarity"),
            element=d.get("element"),
            part_type=d.get("part_type"),
        )
        d["part_type_label"] = _part_type_ui_label(d.get("part_type"))
        legacy_total += int(d["qty"])
        d["image_url"] = url_for("static", filename=_part_image_rel(d), v=APP_VERSION)
        legacy_items.append(d)
    storage_total = int(overflow_total + legacy_total)
    list_params = {}
    if selected_part_type:
        list_params["part_type"] = selected_part_type
    prev_url = url_for("parts", page=page - 1, **list_params) if page > 1 else None
    next_url = url_for("parts", page=page + 1, **list_params) if total > page * per_page else None
    return render_template(
        "parts_instances.html",
        items=items,
        legacy_items=legacy_items,
        legacy_total=legacy_total,
        page=page,
        has_prev=bool(prev_url),
        has_next=bool(next_url),
        prev_url=prev_url,
        next_url=next_url,
        total=total,
        inventory_total=int(summary["inventory_count"] or 0),
        equipped_total=int(summary["equipped_count"] or 0),
        inventory_space_remaining=inventory_space_remaining,
        overflow_items=overflow_items,
        overflow_total=overflow_total,
        protect_core=protect_core,
        storage_total=storage_total,
        selected_part_type=selected_part_type,
        part_type_filters=_part_type_filter_rows(selected_part_type, "parts"),
        show_evolution_actions=_evolution_feature_unlocked(db, user=user_row, user_id=user_id),
    )


@app.route("/parts/evolve", methods=["GET", "POST"])
@login_required
def evolve_parts():
    db = get_db()
    user_id = int(session["user_id"])
    user = db.execute(
        "SELECT id, is_admin, max_unlocked_layer FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if not _evolution_feature_unlocked(db, user=user, user_id=user_id):
        flash("進化合成は第2層ボス撃破後に解放されます。", "error")
        return redirect(url_for("home"))
    request_id = getattr(g, "request_id", None)
    selected_mode = (request.args.get("mode") or "select").strip().lower()
    if selected_mode not in {"select", "result"}:
        selected_mode = "select"
    selected_part_type = _normalize_part_type_filter(request.values.get("part_type"))

    if request.method == "POST":
        part_instance_id_raw = (request.form.get("part_instance_id") or "").strip()
        redirect_params = {"mode": "select"}
        if selected_part_type:
            redirect_params["part_type"] = selected_part_type
        if not part_instance_id_raw.isdigit():
            flash("進化対象を選択してください。", "error")
            return redirect(url_for("evolve_parts", **redirect_params))
        part_instance_id = int(part_instance_id_raw)
        try:
            db.execute("BEGIN IMMEDIATE")
            source_row = db.execute(
                """
                SELECT
                    pi.id, pi.part_id, pi.rarity, pi.plus, pi.part_type, pi.element, pi.series, pi.status,
                    pi.w_hp, pi.w_atk, pi.w_def, pi.w_spd, pi.w_acc, pi.w_cri,
                    rp.key AS part_key, rp.display_name_ja, rp.image_path
                FROM part_instances pi
                JOIN robot_parts rp ON rp.id = pi.part_id
                WHERE pi.id = ? AND pi.user_id = ? AND pi.status IN ('inventory', 'equipped')
                """,
                (part_instance_id, user_id),
            ).fetchone()
            if not source_row:
                db.rollback()
                flash("進化対象が見つかりません。", "error")
                return redirect(url_for("evolve_parts", **redirect_params))
            source_rarity = str(source_row["rarity"] or "").upper().strip()
            if source_rarity != "N":
                db.rollback()
                flash("Nパーツのみ進化できます。", "error")
                return redirect(url_for("evolve_parts", **redirect_params))
            target_part_key = resolve_evolved_part_key(source_row["part_key"])
            if not target_part_key:
                db.rollback()
                flash("このパーツは進化できません。", "error")
                return redirect(url_for("evolve_parts", **redirect_params))
            target_part = db.execute(
                """
                SELECT id, key, part_type, rarity, element, series, image_path, display_name_ja
                FROM robot_parts
                WHERE key = ? AND is_active = 1
                LIMIT 1
                """,
                (target_part_key,),
            ).fetchone()
            if not target_part:
                db.rollback()
                flash("進化先パーツが未登録です。", "error")
                return redirect(url_for("evolve_parts", **redirect_params))
            if str(target_part["rarity"] or "").upper().strip() != "R":
                db.rollback()
                flash("進化先パーツのレアリティ設定が不正です。", "error")
                return redirect(url_for("evolve_parts", **redirect_params))
            if not _consume_player_core(db, user_id, EVOLUTION_CORE_KEY, qty=1):
                db.rollback()
                flash("進化コアが不足しています。", "error")
                return redirect(url_for("evolve_parts", **redirect_params))

            source_name = _part_display_name_ja(source_row)
            target_name = _part_display_name_ja(target_part)
            target_preview = dict(target_part)
            target_preview.update(
                {
                    "plus": int(source_row["plus"] or 0),
                    "w_hp": source_row["w_hp"],
                    "w_atk": source_row["w_atk"],
                    "w_def": source_row["w_def"],
                    "w_spd": source_row["w_spd"],
                    "w_acc": source_row["w_acc"],
                    "w_cri": source_row["w_cri"],
                    "rarity": "R",
                    "element": target_part["element"] or source_row["element"],
                    "series": target_part["series"] or source_row["series"],
                }
            )
            compare_payload = _part_card_payload(source_row, compare_row=target_preview)
            source_status = str(source_row["status"] or "inventory").strip().lower()
            if source_status == "equipped":
                db.execute(
                    """
                    UPDATE part_instances
                    SET
                        part_id = ?,
                        part_type = ?,
                        rarity = ?,
                        element = ?,
                        series = ?,
                        updated_at = datetime('now')
                    WHERE id = ? AND user_id = ? AND status = 'equipped'
                    """,
                    (
                        int(target_part["id"]),
                        target_part["part_type"],
                        "R",
                        target_part["element"] or source_row["element"],
                        target_part["series"] or source_row["series"],
                        int(part_instance_id),
                        int(user_id),
                    ),
                )
                created_id = int(part_instance_id)
            else:
                db.execute(
                    "DELETE FROM part_instances WHERE id = ? AND user_id = ? AND status = 'inventory'",
                    (part_instance_id, user_id),
                )
                created = db.execute(
                    """
                    INSERT INTO part_instances
                    (part_id, user_id, part_type, rarity, element, series, plus, w_hp, w_atk, w_def, w_spd, w_acc, w_cri, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'inventory', ?, datetime('now'))
                    """,
                    (
                        int(target_part["id"]),
                        user_id,
                        target_part["part_type"],
                        "R",
                        target_part["element"] or source_row["element"],
                        target_part["series"] or source_row["series"],
                        int(source_row["plus"] or 0),
                        source_row["w_hp"],
                        source_row["w_atk"],
                        source_row["w_def"],
                        source_row["w_spd"],
                        source_row["w_acc"],
                        source_row["w_cri"],
                        int(time.time()),
                    ),
                )
                created_id = int(created.lastrowid)
            audit_log(
                db,
                AUDIT_EVENT_TYPES["PART_EVOLVE"],
                user_id=user_id,
                request_id=request_id,
                action_key="evolve",
                entity_type="part_instance",
                entity_id=created_id,
                payload={
                    "source_part_instance_id": int(source_row["id"]),
                    "source_part_key": source_row["part_key"],
                    "source_part_name": source_name,
                    "source_plus": int(source_row["plus"] or 0),
                    "part_type": target_part["part_type"] or source_row["part_type"],
                    "target_part_key": target_part["key"],
                    "target_part_name": target_name,
                    "target_plus": int(source_row["plus"] or 0),
                    "core_key": EVOLUTION_CORE_KEY,
                    "core_consumed": 1,
                },
                ip=request.remote_addr,
            )
            db.commit()
            session["last_evolve_result"] = {
                "source_name": source_name,
                "target_name": target_name,
                "source_plus": int(source_row["plus"] or 0),
                "target_plus": int(source_row["plus"] or 0),
                "source_status": str(source_row["status"] or "inventory"),
                "source_image_url": (
                    url_for("static", filename=_part_image_rel(source_row))
                ),
                "target_image_url": (
                    url_for("static", filename=_part_image_rel(target_part))
                ),
                "part_type_label": compare_payload["part_type_label"],
                "source_total_value": compare_payload["total_value"],
                "target_total_value": compare_payload["compare_total_value"],
                "total_delta_text": compare_payload["compare_total_delta_text"],
                "stat_rows": compare_payload["stat_rows"],
            }
            flash("✨ 進化成功！", "notice")
            result_params = {"mode": "result"}
            if selected_part_type:
                result_params["part_type"] = selected_part_type
            return redirect(url_for("evolve_parts", **result_params))
        except Exception:
            db.rollback()
            app.logger.exception("evolve_parts.failed user_id=%s part_instance_id=%s", user_id, part_instance_id_raw)
            flash("進化処理に失敗しました。", "error")
            return redirect(url_for("evolve_parts", **redirect_params))

    last_evolve_result = session.pop("last_evolve_result", None) if selected_mode == "result" else None
    if selected_mode == "result" and not last_evolve_result:
        selected_mode = "select"
    core_qty = _get_player_core_qty(db, user_id, EVOLUTION_CORE_KEY)
    evolution_core_status = _evolution_core_progress_status(
        _get_player_evolution_core_progress(db, user_id),
        core_qty=core_qty,
    )
    where_clauses = [
        "pi.user_id = ?",
        "pi.status IN ('inventory', 'equipped')",
        "UPPER(COALESCE(pi.rarity, 'N')) = 'N'",
    ]
    params = [user_id]
    if selected_part_type:
        where_clauses.append("rp.part_type = ?")
        params.append(selected_part_type)
    rows = db.execute(
        """
        SELECT
            pi.id, pi.rarity, pi.plus, pi.part_type, pi.element, pi.series, pi.status,
            pi.w_hp, pi.w_atk, pi.w_def, pi.w_spd, pi.w_acc, pi.w_cri,
            rp.key AS part_key, rp.image_path, rp.display_name_ja
        FROM part_instances pi
        JOIN robot_parts rp ON rp.id = pi.part_id
        WHERE """
        + " AND ".join(where_clauses)
        + """
        ORDER BY CASE WHEN pi.status = 'equipped' THEN 0 ELSE 1 END ASC, pi.plus DESC, pi.id DESC
        """,
        params,
    ).fetchall()
    evolve_items = []
    for row in rows:
        item = dict(row)
        target_key = resolve_evolved_part_key(item.get("part_key"))
        if not target_key:
            continue
        target_part = db.execute(
            """
            SELECT id, key, display_name_ja, image_path, part_type, element, rarity, series
            FROM robot_parts
            WHERE key = ? AND is_active = 1
            LIMIT 1
            """,
            (target_key,),
        ).fetchone()
        if not target_part:
            continue
        target_preview = dict(target_part)
        target_preview.update(
            {
                "plus": int(item.get("plus") or 0),
                "w_hp": item.get("w_hp"),
                "w_atk": item.get("w_atk"),
                "w_def": item.get("w_def"),
                "w_spd": item.get("w_spd"),
                "w_acc": item.get("w_acc"),
                "w_cri": item.get("w_cri"),
                "rarity": "R",
                "element": target_part["element"] or item.get("element"),
                "series": target_part["series"] or item.get("series"),
            }
        )
        payload = _part_card_payload(item, compare_row=target_preview)
        payload["target_part_key"] = target_key
        payload["next_rarity"] = "R"
        evolve_items.append(payload)
    return render_template(
        "evolve.html",
        core_key=EVOLUTION_CORE_KEY,
        core_qty=core_qty,
        evolution_core_status=evolution_core_status,
        items=evolve_items,
        selected_part_type=selected_part_type,
        part_type_filters=_part_type_filter_rows(
            selected_part_type,
            "evolve_parts",
            extra_params={"mode": "select"},
        ),
        selected_mode=selected_mode,
        last_evolve_result=last_evolve_result,
    )


@app.route("/evolve", methods=["GET", "POST"])
@login_required
def evolve_parts_legacy():
    if request.method == "POST":
        return redirect(url_for("evolve_parts"), code=307)
    mode = (request.args.get("mode") or "").strip()
    return redirect(url_for("evolve_parts", mode=mode) if mode else url_for("evolve_parts"))


def _strengthen_parts_selected(db, user_id, base_id):
    try:
        base_id_int = int(base_id)
    except Exception:
        return {"ok": False, "message": "ベース個体を選択してください。"}

    base_row = db.execute(
        """
        SELECT
            pi.id, pi.part_id, pi.plus, pi.rarity, pi.element, pi.series, pi.status,
            pi.w_hp, pi.w_atk, pi.w_def, pi.w_spd, pi.w_acc, pi.w_cri,
            rp.part_type, rp.key AS part_key
        FROM part_instances pi
        JOIN robot_parts rp ON rp.id = pi.part_id
        WHERE pi.user_id = ? AND pi.status IN ('inventory', 'equipped') AND pi.id = ?
        """,
        (int(user_id), base_id_int),
    ).fetchone()
    if not base_row:
        return {"ok": False, "message": "ベース個体が見つかりません。"}
    if int(base_row["plus"] or 0) >= int(MAX_PART_PLUS):
        return {"ok": False, "message": f"この個体はすでに最大強化（+{MAX_PART_PLUS}）です。"}

    material_rows = db.execute(
        """
        SELECT
            pi.id, pi.part_id, pi.plus, pi.rarity, pi.element, pi.series,
            pi.w_hp, pi.w_atk, pi.w_def, pi.w_spd, pi.w_acc, pi.w_cri,
            rp.part_type, rp.key AS part_key
        FROM part_instances pi
        JOIN robot_parts rp ON rp.id = pi.part_id
        WHERE pi.user_id = ?
          AND pi.status = 'inventory'
          AND pi.id != ?
          AND rp.key = ?
          AND UPPER(COALESCE(pi.rarity, '')) = UPPER(COALESCE(?, ''))
        ORDER BY pi.plus ASC, pi.id ASC
        LIMIT 2
        """,
        (
            int(user_id),
            base_id_int,
            str(base_row["part_key"] or ""),
            str(base_row["rarity"] or ""),
        ),
    ).fetchall()
    if len(material_rows) != 2:
        return {"ok": False, "message": "同じパーツ（＋値違い可）の素材が2個不足しています。"}

    material_ids = [int(material_rows[0]["id"]), int(material_rows[1]["id"])]

    coin_cost = int(FUSE_COST_BY_PLUS.get(int(base_row["plus"] or 0), 20))
    user_row = db.execute("SELECT coins FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if not user_row or int(user_row["coins"] or 0) < coin_cost:
        return {"ok": False, "message": f"コイン不足です（必要: {coin_cost}）", "coin_cost": coin_cost}

    try:
        base_plus = int(base_row["plus"] or 0)
        material_pluses = [int(material_rows[0]["plus"] or 0), int(material_rows[1]["plus"] or 0)]
        mat_plus_sum = int(sum(material_pluses))
        bonus = 0
        inc = 1
        new_plus = min(int(MAX_PART_PLUS), base_plus + 1)
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE users SET coins = coins - ? WHERE id = ?", (coin_cost, int(user_id)))
        placeholders = ",".join(["?"] * len(material_ids))
        db.execute(
            f"DELETE FROM part_instances WHERE user_id = ? AND status = 'inventory' AND id IN ({placeholders})",
            [int(user_id)] + material_ids,
        )
        db.execute(
            """
            UPDATE part_instances
            SET plus = ?, updated_at = datetime('now')
            WHERE id = ? AND user_id = ?
            """,
            (
                int(new_plus),
                int(base_id_int),
                int(user_id),
            ),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        return {"ok": False, "message": f"強化に失敗しました: {exc}"}

    return {
        "ok": True,
        "outcome": "success",
        "part_type": base_row["part_type"],
        "rarity": base_row["rarity"],
        "part_key": base_row["part_key"],
        "base_plus": int(base_plus),
        "new_plus": int(new_plus),
        "material_pluses": material_pluses,
        "mat_plus_sum": int(mat_plus_sum),
        "bonus": int(bonus),
        "inc": int(inc),
        "consumed_ids": [int(x) for x in material_ids],
        "created_id": int(base_id_int),
        "updated_id": int(base_id_int),
        "coin_cost": coin_cost,
        "base_id": int(base_id_int),
        "base_status": str(base_row["status"] or "inventory"),
    }


@app.route("/parts/strengthen", methods=["GET", "POST"])
@app.route("/parts/fuse", methods=["GET", "POST"])
@login_required
def parts_strengthen():
    db = get_db()
    user_id = session["user_id"]
    request_id = None
    try:
        from flask import g as flask_g
        request_id = getattr(flask_g, "request_id", None)
    except Exception:
        request_id = None
    last_fuse_result = None
    selected_mode = (request.args.get("mode") or "select").strip().lower()
    if selected_mode not in {"select", "result"}:
        selected_mode = "select"
    filter_part_type = _normalize_part_type_filter(request.values.get("part_type"))
    filter_rarity = (request.values.get("rarity") or "").strip().upper()
    plus_raw = (request.values.get("plus") or "").strip()
    filter_plus = int(plus_raw) if plus_raw.isdigit() else None
    if request.method == "POST":
        result = {}
        mode = "select"
        redirect_plus = filter_plus
        base_id_raw = (request.form.get("base_id") or "").strip()
        if not base_id_raw.isdigit():
            flash("ベース個体を選択してください。", "error")
        else:
            try:
                result = _strengthen_parts_selected(
                    db,
                    user_id,
                    base_id=int(base_id_raw),
                )
            except Exception:
                app.logger.exception(
                    "parts_strengthen.failed user_id=%s mode=%s args=%s form=%s",
                    user_id,
                    mode,
                    dict(request.args),
                    dict(request.form),
                )
                flash("条件が不正です。URLを作り直してください。", "error")
                return redirect(url_for("parts_strengthen"))
        if result:
            if result.get("ok"):
                db.execute(
                    """
                    INSERT INTO fusion_audit_logs
                    (user_id, mode, part_type, rarity, from_plus, to_plus, outcome, use_protect_core, consumed_ids, created_at, message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        "select",
                        result.get("part_type"),
                        result.get("rarity"),
                        result.get("base_plus"),
                        result.get("new_plus"),
                        result.get("outcome"),
                        0,
                        json.dumps(result.get("consumed_ids", []), ensure_ascii=False),
                        int(time.time()),
                        "強化",
                    ),
                )
                db.commit()
            audit_log(
                db,
                AUDIT_EVENT_TYPES["FUSE"],
                user_id=user_id,
                request_id=request_id,
                action_key="fuse",
                entity_type="part_instance",
                entity_id=result.get("created_id"),
                delta_coins=-(int(result.get("coin_cost") or 0)) if result.get("coin_cost") is not None else None,
                payload={
                    "mode": "select",
                    "success": bool(result.get("ok")),
                    "base_part_instance_id": result.get("base_id"),
                    "outcome": result.get("outcome"),
                    "part_type": result.get("part_type"),
                    "rarity": result.get("rarity"),
                    "from_plus": result.get("base_plus"),
                    "to_plus": result.get("new_plus"),
                    "consumed_ids": result.get("consumed_ids", []),
                    "created_id": result.get("created_id"),
                    "coin_cost": result.get("coin_cost"),
                    "mat_plus_sum": result.get("mat_plus_sum"),
                    "bonus": result.get("bonus"),
                    "inc": result.get("inc"),
                },
                ip=request.remote_addr,
            )
            db.commit()
            session["last_fuse_result"] = {
                "mode": "select",
                "outcome": result.get("outcome"),
                "part_type": result.get("part_type"),
                "part_key": result.get("part_key"),
                "rarity": result.get("rarity"),
                "from_plus": result.get("base_plus"),
                "to_plus": result.get("new_plus"),
                "coin_cost": result.get("coin_cost"),
                "consumed_ids": result.get("consumed_ids", []),
                "created_id": result.get("created_id"),
                "base_id": result.get("base_id"),
                "mat_plus_sum": result.get("mat_plus_sum"),
                "bonus": result.get("bonus"),
                "inc": result.get("inc"),
                "material_pluses": result.get("material_pluses", []),
                "ok": bool(result.get("ok")),
            }
            mode_label = "強化"
            consumed_ids = ",".join([f"#{x}" for x in result.get("consumed_ids", [])])
            part_type = result.get("part_type") or "-"
            rarity = result.get("rarity") or "-"
            from_plus = result.get("base_plus")
            to_plus = result.get("new_plus")
            coin_cost = result.get("coin_cost")
            outcome = result.get("outcome")
            if result.get("ok"):
                status_label = "成功"
                plus_text = (
                    f"+{from_plus} → +{to_plus}"
                    if to_plus is not None and from_plus is not None
                    else (f"+{from_plus}" if from_plus is not None else "-")
                )
                detail = (
                    f"{mode_label}{status_label}：{part_type} / {rarity} / {plus_text} "
                    f"（上昇量 +1 / ベース #{result.get('base_id')} / 消費 {consumed_ids} / 更新 #{result.get('created_id')}） "
                    f"-{coin_cost if coin_cost is not None else 0}コイン"
                )
                flash(detail, "notice")
            else:
                flash(result["message"], "error")
        else:
            app.logger.warning(
                "parts_strengthen.invalid_selection user_id=%s mode=%s args=%s form=%s",
                user_id,
                "select",
                dict(request.args),
                dict(request.form),
            )
            flash("強化対象を選択してください。", "error")
            session.pop("last_fuse_result", None)
        return redirect(
            url_for(
                "parts_strengthen",
                part_type=((result.get("part_type") if isinstance(result, dict) else filter_part_type) or ""),
                rarity=((result.get("rarity") if isinstance(result, dict) else filter_rarity) or ""),
                plus=redirect_plus if redirect_plus is not None else "",
                mode="result",
            )
        )

    raw_last = session.pop("last_fuse_result", None) if selected_mode == "result" else None
    if selected_mode == "result" and not raw_last:
        selected_mode = "select"
    if raw_last:
        outcome_key = raw_last.get("outcome")
        outcome_label = {
            "great": "大成功",
            "success": "成功",
            "fail": "失敗",
        }.get(outcome_key, "不明")
        mode_label = "強化"
        last_fuse_result = dict(raw_last)
        last_fuse_result["outcome_label"] = outcome_label
        last_fuse_result["mode_label"] = mode_label
        created_id = raw_last.get("created_id")
        if created_id:
            created_row = db.execute(
                """
                SELECT
                    pi.id, pi.part_type, pi.rarity, pi.element, pi.series, pi.plus,
                    pi.w_hp, pi.w_atk, pi.w_def, pi.w_spd, pi.w_acc, pi.w_cri,
                    rp.key AS part_key, rp.image_path, rp.display_name_ja
                FROM part_instances pi
                JOIN robot_parts rp ON rp.id = pi.part_id
                WHERE pi.id = ? AND pi.user_id = ?
                """,
                (created_id, user_id),
            ).fetchone()
            if created_row:
                last_fuse_result["created_part"] = _part_card_payload(created_row)
        retry_params = {"mode": "select"}
        if filter_part_type:
            retry_params["part_type"] = filter_part_type
        if filter_rarity:
            retry_params["rarity"] = filter_rarity
        if filter_plus is not None:
            retry_params["plus"] = filter_plus
        last_fuse_result["retry_url"] = url_for("parts_strengthen", **retry_params)

    where_clauses = ["pi.user_id = ?", "pi.status IN ('inventory', 'equipped')"]
    params = [user_id]
    if filter_part_type in {"HEAD", "RIGHT_ARM", "LEFT_ARM", "LEGS"}:
        where_clauses.append("rp.part_type = ?")
        params.append(filter_part_type)
    if filter_rarity in RARITIES:
        where_clauses.append("pi.rarity = ?")
        params.append(filter_rarity)
    where_sql = " AND ".join(where_clauses)

    group_rows = db.execute(
        """
        SELECT
            rp.part_type,
            rp.key AS part_key,
            pi.rarity,
            COUNT(*) AS qty_total,
            SUM(CASE WHEN pi.status = 'inventory' THEN 1 ELSE 0 END) AS qty_inventory,
            GROUP_CONCAT(pi.id) AS ids,
            MIN(pi.element) AS element
        FROM part_instances pi
        JOIN robot_parts rp ON rp.id = pi.part_id
        WHERE """
        + where_sql
        + """
        GROUP BY rp.part_type, rp.key, pi.rarity
        HAVING COUNT(*) >= 3 AND SUM(CASE WHEN pi.status = 'inventory' THEN 1 ELSE 0 END) >= 2
        ORDER BY rp.part_type, rp.key, pi.rarity
        """,
        params,
    ).fetchall()
    plus_rows = db.execute(
        """
        SELECT DISTINCT plus
        FROM part_instances
        WHERE user_id = ? AND status = 'inventory'
        ORDER BY plus ASC
        """,
        (user_id,),
    ).fetchall()
    plus_options = [int(r["plus"]) for r in plus_rows]
    rarity_rows = db.execute(
        """
        SELECT DISTINCT rarity
        FROM part_instances
        WHERE user_id = ? AND status = 'inventory'
        ORDER BY rarity ASC
        """,
        (user_id,),
    ).fetchall()
    rarity_options = [str(r["rarity"]).upper() for r in rarity_rows if r["rarity"]]
    if not rarity_options:
        rarity_options = list(RARITIES)
    part_type_rows = db.execute(
        """
        SELECT DISTINCT rp.part_type
        FROM part_instances pi
        JOIN robot_parts rp ON rp.id = pi.part_id
        WHERE pi.user_id = ? AND pi.status = 'inventory'
        ORDER BY rp.part_type ASC
        """,
        (user_id,),
    ).fetchall()
    part_type_options = [str(r["part_type"]) for r in part_type_rows if r["part_type"]]
    if not part_type_options:
        part_type_options = ["HEAD", "RIGHT_ARM", "LEFT_ARM", "LEGS"]
    stat_labels = {k: _stat_label(k) for k in ("hp", "atk", "def", "spd", "acc", "cri")}
    base_candidates = []
    for group_row in group_rows:
        ids_csv = group_row["ids"] or ""
        sample_rows = db.execute(
            """
            SELECT
                pi.id,
                pi.part_id,
                pi.rarity,
                pi.element,
                pi.series,
                pi.plus,
                pi.status,
                pi.w_hp, pi.w_atk, pi.w_def, pi.w_spd, pi.w_acc, pi.w_cri,
                rp.part_type,
                rp.key AS part_key,
                rp.image_path,
                rp.display_name_ja
            FROM part_instances pi
            JOIN robot_parts rp ON rp.id = pi.part_id
            WHERE pi.user_id = ?
              AND pi.status IN ('inventory', 'equipped')
              AND rp.part_type = ?
              AND rp.key = ?
              AND pi.rarity = ?
            ORDER BY CASE WHEN pi.status = 'equipped' THEN 0 ELSE 1 END ASC, pi.plus DESC, pi.id ASC
            LIMIT 50
            """,
            (user_id, group_row["part_type"], group_row["part_key"], group_row["rarity"]),
        ).fetchall()
        if not sample_rows:
            continue
        inventory_count = sum(1 for r in sample_rows if (r["status"] or "") == "inventory")
        base_rows = sample_rows
        if filter_plus is not None:
            base_rows = [r for r in sample_rows if int(r["plus"] or 0) == int(filter_plus)]
        if not base_rows:
            continue
        eligible_base_rows = []
        for row in base_rows:
            row_status = (row["status"] or "").strip().lower()
            if row_status == "equipped" and inventory_count >= 2:
                eligible_base_rows.append(row)
            elif row_status == "inventory" and inventory_count >= 3:
                eligible_base_rows.append(row)
        if not eligible_base_rows:
            continue
        stat_ranges = {}
        for s in ("hp", "atk", "def", "spd", "acc", "cri"):
            cur_vals = []
            next_vals = []
            for row in eligible_base_rows:
                current = compute_part_stats(dict(row))
                next_row = dict(row)
                next_row["plus"] = int(next_row["plus"]) + 1
                nxt = compute_part_stats(next_row)
                cur_vals.append(int(current[s]))
                next_vals.append(int(nxt[s]))
            if cur_vals and next_vals:
                cmin = min(cur_vals)
                cmax = max(cur_vals)
                nmin = min(next_vals)
                nmax = max(next_vals)
                stat_ranges[s] = {
                    "label": stat_labels[s],
                    "current_min": cmin,
                    "current_max": cmax,
                    "next_min": nmin,
                    "next_max": nmax,
                    "delta_min": nmin - cmin,
                    "delta_max": nmax - cmax,
                }
        group_display_name = _part_display_name_ja(sample_rows[0]) if sample_rows else (group_row["part_type"] or "-")
        instance_options = []
        for row in eligible_base_rows:
            row_status = (row["status"] or "inventory").strip().lower()
            instance_options.append(
                {
                    "id": int(row["id"]),
                    "label": f"#{int(row['id'])} {group_display_name} +{int(row['plus'] or 0)}" + (" [装備中]" if row_status == "equipped" else ""),
                    "plus": int(row["plus"] or 0),
                    "status": row_status,
                }
            )
        plus_values = [int(row["plus"] or 0) for row in sample_rows]
        plus_min = min(plus_values) if plus_values else 0
        plus_max = max(plus_values) if plus_values else 0
        for row in eligible_base_rows:
            row_dict = dict(row)
            row_status = (row_dict.get("status") or "inventory").strip().lower()
            materials = [
                dict(candidate)
                for candidate in sample_rows
                if int(candidate["id"]) != int(row_dict["id"])
                and str(candidate["status"] or "").strip().lower() == "inventory"
            ]
            materials.sort(key=lambda item: (int(item.get("plus") or 0), int(item.get("id") or 0)))
            materials = materials[:2]
            if len(materials) != 2:
                continue
            next_row = dict(row_dict)
            next_row["plus"] = min(int(MAX_PART_PLUS), int(next_row.get("plus") or 0) + 1)
            candidate_item = _part_card_payload(row_dict, compare_row=next_row)
            candidate_item["group_display_name"] = group_display_name
            candidate_item["part_key"] = group_row["part_key"]
            candidate_item["qty_total"] = int(group_row["qty_total"] or 0)
            candidate_item["qty_inventory"] = int(group_row["qty_inventory"] or 0)
            candidate_item["plus_min"] = plus_min
            candidate_item["plus_max"] = plus_max
            candidate_item["cost"] = int(FUSE_COST_BY_PLUS.get(int(row_dict.get("plus") or 0), 20))
            candidate_item["material_cards"] = [_part_card_payload(material, can_discard=False) for material in materials]
            candidate_item["material_ids"] = [int(material["id"]) for material in materials]
            candidate_item["material_plus_text"] = " / ".join(
                f"+{int(material.get('plus') or 0)}" for material in materials
            )
            candidate_item["material_notice"] = (
                "装備中ベースのまま強化できます。素材は所持中から2個使います。"
                if row_status == "equipped"
                else "素材は所持中から2個使います。"
            )
            candidate_item["expected_plus_text"] = (
                f"+{int(row_dict.get('plus') or 0)} → +{int(next_row.get('plus') or 0)}"
            )
            candidate_item["stack_key"] = f"{group_row['part_key']}|{group_row['rarity']}|{int(row_dict['id'])}"
            base_candidates.append(candidate_item)
    base_candidates.sort(
        key=lambda item: (
            0 if item.get("is_equipped") else 1,
            ["HEAD", "RIGHT_ARM", "LEFT_ARM", "LEGS"].index(item.get("part_type")) if item.get("part_type") in {"HEAD", "RIGHT_ARM", "LEFT_ARM", "LEGS"} else 9,
            -int(item.get("total_value") or 0),
            -int(item.get("plus") or 0),
            int(item.get("id") or 0),
        )
    )
    protect_core = _get_user_item_qty(db, user_id, "protect_core")
    return render_template(
        "parts_fuse.html",
        base_candidates=base_candidates,
        protect_core=protect_core,
        rarity_options=rarity_options,
        part_type_options=part_type_options,
        selected_part_type=filter_part_type,
        selected_rarity=filter_rarity,
        selected_plus=filter_plus,
        part_type_filters=_part_type_filter_rows(
            filter_part_type,
            "parts_strengthen",
            extra_params={
                "mode": "select",
                "rarity": filter_rarity or "",
                "plus": filter_plus if filter_plus is not None else "",
            },
        ),
        selected_mode=selected_mode,
        plus_options=plus_options,
        element_labels=ELEMENT_LABEL_MAP,
        last_fuse_result=last_fuse_result,
    )


@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin():
    db = get_db()
    user = db.execute("SELECT is_admin FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if user["is_admin"] != 1:
        return redirect(url_for("home"))
    message = None
    if request.method == "POST":
        action = request.form.get("action", "grant_robots")
        if action == "grant_core":
            try:
                qty = max(1, int(request.form.get("qty", "5")))
            except ValueError:
                qty = 5
            _ensure_user_item_row(db, session["user_id"], "protect_core")
            db.execute(
                "UPDATE user_items SET qty = qty + ? WHERE user_id = ? AND item_key = 'protect_core'",
                (qty, session["user_id"]),
            )
            db.commit()
            message = f"保護コアを {qty} 個付与しました。"
        else:
            rows = db.execute(
                """
                SELECT id, head, right_arm, left_arm, legs
                FROM robots_master
                WHERE id NOT IN (
                    SELECT master_id FROM user_robots WHERE user_id = ? AND master_id IS NOT NULL
                )
                """,
                (session["user_id"],),
            ).fetchall()
            now = int(time.time())
            for r in rows:
                db.execute(
                    "INSERT INTO user_robots (user_id, head, right_arm, left_arm, legs, obtained_at, master_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (session["user_id"], r["head"], r["right_arm"], r["left_arm"], r["legs"], now, r["id"]),
                )
            db.commit()
            message = f"未所持ロボ {len(rows)} 体を付与しました。"
    referral_rows = db.execute(
        """
        SELECT status, COUNT(*) AS c
        FROM user_referrals
        GROUP BY status
        """
    ).fetchall()
    referral_counts = {"pending": 0, "qualified": 0, "rewarded": 0}
    for row in referral_rows:
        key = (row["status"] or "").strip().lower()
        if key in referral_counts:
            referral_counts[key] = int(row["c"] or 0)
    missing_assets = _collect_missing_assets(db, limit=120)
    return render_template("admin.html", message=message, referral_counts=referral_counts, missing_assets=missing_assets)


@app.route("/admin/release", methods=["GET", "POST"])
@login_required
def admin_release():
    db = get_db()
    user = db.execute("SELECT id, is_admin FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not user or int(user["is_admin"] or 0) != 1:
        return redirect(url_for("home"))
    _seed_release_flags(db)
    if request.method == "POST":
        feature_key = str(request.form.get("feature_key") or "").strip().lower()
        state = str(request.form.get("state") or "").strip().lower()
        if feature_key not in RELEASE_FLAG_DEF_BY_KEY or state not in {"public", "private"}:
            flash("公開設定の変更内容が不正です。", "error")
            return redirect(url_for("admin_release"))
        target_public = state == "public"
        changes = {feature_key: target_public}
        if feature_key == "layer5" and target_public:
            changes["layer4"] = True
        if feature_key == "layer4" and not target_public:
            changes["layer5"] = False
        now_ts = int(time.time())
        before_rows = {
            row["key"]: bool(int(row["is_public"] or 0) == 1)
            for row in db.execute("SELECT key, is_public FROM release_flags").fetchall()
        }
        applied_keys = []
        for key, is_public in changes.items():
            db.execute(
                """
                INSERT INTO release_flags (key, is_public, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    is_public = excluded.is_public,
                    updated_at = excluded.updated_at
                """,
                (key, 1 if is_public else 0, now_ts),
            )
            applied_keys.append({"key": key, "is_public": bool(is_public)})
        audit_log(
            db,
            AUDIT_EVENT_TYPES["ADMIN_RELEASE_TOGGLE"],
            user_id=int(user["id"]),
            request_id=getattr(g, "request_id", None),
            action_key="admin_release_toggle",
            entity_type="release_flag",
            entity_id=None,
            payload={
                "feature_key": feature_key,
                "state": state,
                "applied": applied_keys,
                "before": before_rows,
            },
            ip=request.remote_addr,
        )
        db.commit()
        changed_labels = " / ".join(RELEASE_FLAG_DEF_BY_KEY[item["key"]]["label"] for item in applied_keys)
        if target_public:
            flash(f"{changed_labels} を一般公開しました。", "notice")
        else:
            flash(f"{changed_labels} を管理者限定に戻しました。", "notice")
        return redirect(url_for("admin_release"))
    return render_template("admin_release.html", release_rows=_release_flag_rows(db))


def _admin_user_delete_summary(db, target_user_id):
    robot_count = int(
        db.execute(
            "SELECT COUNT(*) AS c FROM robot_instances WHERE user_id = ?",
            (target_user_id,),
        ).fetchone()["c"]
        or 0
    )
    part_count = int(
        db.execute(
            "SELECT COUNT(*) AS c FROM part_instances WHERE user_id = ?",
            (target_user_id,),
        ).fetchone()["c"]
        or 0
    )
    audit_count = int(
        db.execute(
            "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ?",
            (target_user_id,),
        ).fetchone()["c"]
        or 0
    )
    referral_count = int(
        db.execute(
            """
            SELECT COUNT(*) AS c
            FROM user_referrals
            WHERE referrer_user_id = ? OR referred_user_id = ?
            """,
            (target_user_id, target_user_id),
        ).fetchone()["c"]
        or 0
    )
    payment_count = int(
        db.execute(
            "SELECT COUNT(*) AS c FROM payment_orders WHERE user_id = ?",
            (target_user_id,),
        ).fetchone()["c"]
        or 0
    )
    return {
        "robot_count": robot_count,
        "part_count": part_count,
        "audit_count": audit_count,
        "referral_count": referral_count,
        "payment_count": payment_count,
    }


def _admin_delete_user_hard(db, target_user_id):
    existing_tables = {
        row["name"]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }

    def _safe_delete(table_name, where_sql, params):
        if table_name in existing_tables:
            db.execute(f"DELETE FROM {table_name} WHERE {where_sql}", params)

    robot_ids = [
        int(r["id"])
        for r in db.execute(
            "SELECT id FROM robot_instances WHERE user_id = ?",
            (target_user_id,),
        ).fetchall()
    ]
    if "users" in existing_tables:
        # Break soft references before hard delete so older DBs with extra refs do not fail mid-delete.
        db.execute("UPDATE users SET active_robot_id = NULL WHERE id = ?", (target_user_id,))
        if "banned_by_user_id" in {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}:
            db.execute("UPDATE users SET banned_by_user_id = NULL WHERE banned_by_user_id = ?", (target_user_id,))
    if robot_ids:
        marks = ",".join("?" for _ in robot_ids)
        if "users" in existing_tables:
            db.execute(f"UPDATE users SET active_robot_id = NULL WHERE active_robot_id IN ({marks})", robot_ids)
        _safe_delete("robot_instance_parts", f"robot_instance_id IN ({marks})", robot_ids)
        _safe_delete("robot_history", f"robot_id IN ({marks})", robot_ids)
        _safe_delete("robot_title_unlocks", f"robot_id IN ({marks})", robot_ids)
        _safe_delete("robot_achievements", f"robot_id IN ({marks})", robot_ids)
        _safe_delete("showcase_votes", f"robot_id IN ({marks})", robot_ids)
        _safe_delete("user_showcase", f"robot_instance_id IN ({marks})", robot_ids)
        _safe_delete("npc_boss_templates", f"source_robot_instance_id IN ({marks})", robot_ids)
        _safe_delete("lab_race_entries", f"robot_instance_id IN ({marks})", robot_ids)

    _safe_delete("battle_state", "user_id = ?", (target_user_id,))
    _safe_delete("chat_messages", "user_id = ?", (target_user_id,))
    _safe_delete("fusion_audit_logs", "user_id = ?", (target_user_id,))
    _safe_delete("lab_submission_likes", "user_id = ?", (target_user_id,))
    _safe_delete("lab_submission_reports", "user_id = ?", (target_user_id,))
    _safe_delete("lab_race_entries", "user_id = ?", (target_user_id,))
    _safe_delete("lab_race_records", "user_id = ?", (target_user_id,))
    _safe_delete("lab_robot_submissions", "user_id = ?", (target_user_id,))
    _safe_delete("login_logs", "user_id = ?", (target_user_id,))
    _safe_delete("part_instances", "user_id = ?", (target_user_id,))
    _safe_delete("payment_orders", "user_id = ?", (target_user_id,))
    _safe_delete("posts", "user_id = ?", (target_user_id,))
    _safe_delete("qol_entitlements", "user_id = ?", (target_user_id,))
    _safe_delete("robot_builds", "user_id = ?", (target_user_id,))
    _safe_delete("robot_instances", "user_id = ?", (target_user_id,))
    _safe_delete("showcase_votes", "user_id = ?", (target_user_id,))
    _safe_delete("user_area_streaks", "user_id = ?", (target_user_id,))
    _safe_delete("user_boss_progress", "user_id = ?", (target_user_id,))
    _safe_delete("user_core_inventory", "user_id = ?", (target_user_id,))
    _safe_delete("user_decor_inventory", "user_id = ?", (target_user_id,))
    _safe_delete("user_enemy_dex", "user_id = ?", (target_user_id,))
    _safe_delete("user_items", "user_id = ?", (target_user_id,))
    _safe_delete("user_milestone_claims", "user_id = ?", (target_user_id,))
    _safe_delete("user_parts_inventory", "user_id = ?", (target_user_id,))
    _safe_delete("user_referrals", "referrer_user_id = ? OR referred_user_id = ?", (target_user_id, target_user_id))
    _safe_delete("user_robots", "user_id = ?", (target_user_id,))
    _safe_delete("user_showcase", "user_id = ?", (target_user_id,))
    _safe_delete("world_events_log", "user_id = ?", (target_user_id,))
    _safe_delete("npc_boss_templates", "source_user_id = ?", (target_user_id,))
    _safe_delete("users", "id = ?", (target_user_id,))


def _admin_rename_user_account(db, target_user_id, new_username):
    existing_tables = {
        row["name"]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    db.execute("UPDATE users SET username = ? WHERE id = ?", (new_username, target_user_id))
    for table_name in ("chat_messages", "posts", "login_logs"):
        if table_name in existing_tables:
            db.execute(
                f"UPDATE {table_name} SET username = ? WHERE user_id = ?",
                (new_username, target_user_id),
            )


@app.route("/admin/users", methods=["GET", "POST"])
@login_required
def admin_users():
    db = get_db()
    admin_user_id = int(session["user_id"])
    if not _is_admin_user(admin_user_id):
        return abort(403)
    message = None
    if request.method == "POST":
        action = (request.form.get("action") or "").strip().lower()
        target_user_id_raw = (request.form.get("target_user_id") or "").strip()
        reason = (request.form.get("reason") or "").strip()
        if not target_user_id_raw.isdigit():
            flash("対象ユーザーが不正です。", "error")
            return redirect(url_for("admin_users"))
        target_user_id = int(target_user_id_raw)
        target = db.execute("SELECT * FROM users WHERE id = ?", (target_user_id,)).fetchone()
        if not target:
            flash("対象ユーザーが見つかりません。", "error")
            return redirect(url_for("admin_users"))
        now_ts = int(time.time())
        if action == "ban":
            if target_user_id == admin_user_id:
                flash("自分自身をBANできません。", "error")
                return redirect(url_for("admin_users"))
            ban_reason = reason or "管理者操作"
            db.execute(
                """
                UPDATE users
                SET is_banned = 1,
                    banned_at = ?,
                    banned_reason = ?,
                    banned_by_user_id = ?
                WHERE id = ?
                """,
                (now_str(), ban_reason, admin_user_id, target_user_id),
            )
            audit_log(
                db,
                AUDIT_EVENT_TYPES["ADMIN_USER_BAN"],
                user_id=admin_user_id,
                request_id=getattr(g, "request_id", None),
                action_key="admin_user_ban",
                entity_type="user",
                entity_id=target_user_id,
                payload={"reason": ban_reason},
                ip=request.remote_addr,
            )
            db.commit()
            message = f"ユーザー #{target_user_id} をBANしました。"
        elif action == "unban":
            db.execute(
                """
                UPDATE users
                SET is_banned = 0,
                    banned_at = NULL,
                    banned_reason = NULL,
                    banned_by_user_id = NULL
                WHERE id = ?
                """,
                (target_user_id,),
            )
            audit_log(
                db,
                AUDIT_EVENT_TYPES["ADMIN_USER_UNBAN"],
                user_id=admin_user_id,
                request_id=getattr(g, "request_id", None),
                action_key="admin_user_unban",
                entity_type="user",
                entity_id=target_user_id,
                payload={},
                ip=request.remote_addr,
            )
            db.commit()
            message = f"ユーザー #{target_user_id} のBANを解除しました。"
        elif action == "protect_login":
            db.execute(
                "UPDATE users SET is_admin_protected = 1 WHERE id = ?",
                (target_user_id,),
            )
            audit_log(
                db,
                AUDIT_EVENT_TYPES["ADMIN_USER_PROTECT_LOGIN"],
                user_id=admin_user_id,
                request_id=getattr(g, "request_id", None),
                action_key="admin_user_protect_login",
                entity_type="user",
                entity_id=target_user_id,
                payload={},
                ip=request.remote_addr,
            )
            db.commit()
            message = f"ユーザー #{target_user_id} を通常ログイン保護ONにしました。"
        elif action == "unprotect_login":
            if target_user_id == admin_user_id:
                flash("自分自身の通常ログイン保護OFFはできません。", "error")
                return redirect(url_for("admin_users"))
            db.execute(
                "UPDATE users SET is_admin_protected = 0 WHERE id = ?",
                (target_user_id,),
            )
            audit_log(
                db,
                AUDIT_EVENT_TYPES["ADMIN_USER_UNPROTECT_LOGIN"],
                user_id=admin_user_id,
                request_id=getattr(g, "request_id", None),
                action_key="admin_user_unprotect_login",
                entity_type="user",
                entity_id=target_user_id,
                payload={},
                ip=request.remote_addr,
            )
            db.commit()
            message = f"ユーザー #{target_user_id} の通常ログイン保護をOFFにしました。"
        elif action == "rename":
            old_username = str(target["username"] or "").strip()
            new_username = (request.form.get("new_username") or "").strip()
            if not new_username:
                flash("新しいユーザー名を入力してください。", "error")
                return redirect(url_for("admin_users"))
            if _is_main_admin_username(old_username):
                flash("メイン管理者アカウントのユーザー名は変更できません。", "error")
                return redirect(url_for("admin_users"))
            if _is_main_admin_username(new_username):
                flash(f"{MAIN_ADMIN_USERNAME} はユーザー名に設定できません。", "error")
                return redirect(url_for("admin_users"))
            if new_username == old_username:
                message = f"ユーザー #{target_user_id} のユーザー名は変更済みです。"
            else:
                existing = db.execute(
                    "SELECT id FROM users WHERE username = ? AND id != ?",
                    (new_username, target_user_id),
                ).fetchone()
                if existing:
                    flash("そのユーザー名は既に使われています。", "error")
                    return redirect(url_for("admin_users"))
                _admin_rename_user_account(db, target_user_id, new_username)
                audit_log(
                    db,
                    AUDIT_EVENT_TYPES.get("ADMIN_USER_RENAME", "audit.admin.user.rename"),
                    user_id=admin_user_id,
                    request_id=getattr(g, "request_id", None),
                    action_key="admin_user_rename",
                    entity_type="user",
                    entity_id=target_user_id,
                    payload={"old_username": old_username, "new_username": new_username},
                    ip=request.remote_addr,
                )
                db.commit()
                if target_user_id == admin_user_id:
                    session["username"] = _display_username(new_username, is_admin=True)
                message = f"ユーザー #{target_user_id} のユーザー名を『{old_username}』から『{new_username}』へ変更しました。"
        elif action == "delete":
            return redirect(url_for("admin_user_delete_confirm", target_user_id=target_user_id))
        else:
            flash("不正な操作です。", "error")
            return redirect(url_for("admin_users"))

    rows_raw = db.execute(
        """
        SELECT id, username, is_admin, is_banned, is_admin_protected, created_at, banned_at, banned_reason, banned_by_user_id
        FROM users
        ORDER BY id ASC
        """
    ).fetchall()
    rows = []
    for row in rows_raw:
        item = dict(row)
        item["display_username"] = _display_username(item.get("username"), is_admin=bool(int(item.get("is_admin") or 0)))
        item["is_main_admin"] = _is_main_admin_username(item.get("username"))
        rows.append(item)
    return render_template("admin_users.html", rows=rows, message=message, self_user_id=admin_user_id)


@app.route("/admin/payments")
@login_required
def admin_payments():
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)

    user_id_raw = (request.args.get("user_id") or "").strip()
    username = (request.args.get("username") or "").strip()
    product_key = (request.args.get("product_key") or "").strip()
    status = (request.args.get("status") or "").strip()
    stripe_checkout_session_id = (request.args.get("stripe_checkout_session_id") or "").strip()
    stripe_event_id = (request.args.get("stripe_event_id") or "").strip()
    created_at = (request.args.get("created_at") or "").strip()
    granted_at = (request.args.get("granted_at") or "").strip()

    where = []
    params = []
    if user_id_raw.isdigit():
        where.append("po.user_id = ?")
        params.append(int(user_id_raw))
    if username:
        where.append("u.username LIKE ?")
        params.append(f"%{username}%")
    if product_key:
        where.append("po.product_key = ?")
        params.append(product_key)
    if status:
        where.append("po.status = ?")
        params.append(status)
    if stripe_checkout_session_id:
        where.append("po.stripe_checkout_session_id = ?")
        params.append(stripe_checkout_session_id)
    if stripe_event_id:
        where.append("po.stripe_event_id = ?")
        params.append(stripe_event_id)
    created_from = _parse_jst_day_filter(created_at)
    created_to = _parse_jst_day_filter(created_at, end=True)
    if created_from is not None and created_to is not None:
        where.append("po.created_at >= ? AND po.created_at < ?")
        params.extend([created_from, created_to])
    granted_from = _parse_jst_day_filter(granted_at)
    granted_to = _parse_jst_day_filter(granted_at, end=True)
    if granted_from is not None and granted_to is not None:
        where.append("po.granted_at IS NOT NULL AND po.granted_at >= ? AND po.granted_at < ?")
        params.extend([granted_from, granted_to])

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    rows = db.execute(
        f"""
        SELECT
            po.*,
            u.username
        FROM payment_orders po
        JOIN users u ON u.id = po.user_id
        {where_sql}
        ORDER BY po.id DESC
        LIMIT 200
        """,
        params,
    ).fetchall()
    return render_template(
        "admin_payments.html",
        rows=rows,
        filters={
            "user_id": user_id_raw,
            "username": username,
            "product_key": product_key,
            "status": status,
            "stripe_checkout_session_id": stripe_checkout_session_id,
            "stripe_event_id": stripe_event_id,
            "created_at": created_at,
            "granted_at": granted_at,
        },
        payment_status_label=_payment_status_label,
    )


@app.route("/admin/users/<int:target_user_id>/delete", methods=["GET", "POST"])
@login_required
def admin_user_delete_confirm(target_user_id):
    db = get_db()
    actor_admin_id = int(session["user_id"])
    if not _is_admin_user(actor_admin_id):
        return abort(403)
    target = db.execute(
        "SELECT id, username, is_admin, is_admin_protected FROM users WHERE id = ?",
        (target_user_id,),
    ).fetchone()
    if not target:
        flash("対象ユーザーが見つかりません。", "error")
        return redirect(url_for("admin_users"))
    if target_user_id == actor_admin_id:
        flash("自分自身は完全削除できません。", "error")
        return redirect(url_for("admin_users"))
    if _is_main_admin_username(target["username"]):
        flash("メイン管理者アカウントは完全削除できません。", "error")
        return redirect(url_for("admin_users"))
    summary = _admin_user_delete_summary(db, target_user_id)
    if request.method == "POST":
        confirm_token = (request.form.get("confirm_token") or "").strip()
        if confirm_token != "DELETE":
            flash("確認トークンが不正です。DELETE を入力してください。", "error")
            return redirect(url_for("admin_user_delete_confirm", target_user_id=target_user_id))
        deleted_username = str(target["username"] or "")
        try:
            _admin_delete_user_hard(db, target_user_id)
            audit_log(
                db,
                AUDIT_EVENT_TYPES.get("ADMIN_USER_DELETE", "audit.admin.user.delete"),
                user_id=actor_admin_id,
                request_id=getattr(g, "request_id", None),
                action_key="admin_user_delete",
                entity_type="user",
                entity_id=target_user_id,
                payload={
                    "deleted_user_id": target_user_id,
                    "deleted_username": deleted_username,
                    "actor_admin_id": actor_admin_id,
                    "summary": summary,
                },
                ip=request.remote_addr,
            )
            db.commit()
            flash(f"ユーザー #{target_user_id}（{deleted_username}）を完全削除しました。", "notice")
            return redirect(url_for("admin_users"))
        except Exception as exc:
            db.rollback()
            app.logger.exception("admin user hard delete failed target_user_id=%s", target_user_id)
            flash(f"ユーザー削除に失敗しました: {exc}", "error")
            return redirect(url_for("admin_user_delete_confirm", target_user_id=target_user_id))
    return render_template("admin_user_delete_confirm.html", target=target, summary=summary)


@app.route("/admin/metrics", methods=["GET", "POST"])
@login_required
def admin_metrics():
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    db = get_db()
    sample_size = request.args.get("sample", type=int, default=500)
    core_days = request.args.get("core_days", type=int, default=14)
    if request.method == "POST":
        _collect_recent_daily_metrics(db, days=7)
        db.commit()
    rows = db.execute(
        """
        SELECT day_key, dau_count, new_users, explore_count, boss_encounters, boss_defeats, fuse_count
        FROM daily_metrics
        ORDER BY day_key DESC
        LIMIT 7
        """
    ).fetchall()
    if len(rows) < 7:
        _collect_recent_daily_metrics(db, days=7)
        db.commit()
        rows = db.execute(
            """
            SELECT day_key, dau_count, new_users, explore_count, boss_encounters, boss_defeats, fuse_count
            FROM daily_metrics
            ORDER BY day_key DESC
            LIMIT 7
            """
        ).fetchall()
    core_obs = _core_drop_observability(db, sample_size=sample_size, days=core_days, user_day_limit=300)
    return render_template(
        "admin_metrics.html",
        rows=rows,
        core_obs=core_obs,
        selected_sample_size=int(sample_size or 500),
        selected_core_days=int(core_days or 14),
    )


@app.route("/admin/backup", methods=["GET", "POST"])
@login_required
def admin_backup():
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    message = None
    if request.method == "POST":
        backup = create_db_backup()
        message = f"バックアップ作成: {backup['name']}"
    files = [{k: item[k] for k in ("name", "size", "updated_at")} for item in list_db_backups()]
    return render_template("admin_backup.html", files=files, message=message)


@app.route("/admin/bases", methods=["GET", "POST"])
@login_required
def admin_bases():
    return redirect(url_for("admin_parts"))


@app.route("/admin/tools/seed_robots", methods=["GET", "POST"])
@login_required
def admin_seed_robots():
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    db = get_db()
    message = None
    result = None
    params = {"count": 50, "strategy": "random"}
    test_user = _ensure_test_user(db)
    if request.method == "POST":
        strategy = (request.form.get("strategy") or "random").strip()
        count_raw = (request.form.get("count") or "50").strip()
        try:
            count = int(count_raw)
        except ValueError:
            count = 50
        count = max(1, min(300, count))
        params = {"count": count, "strategy": strategy}
        if strategy != "random":
            message = "strategy は random のみ対応しています。"
        else:
            try:
                result = _seed_test_robots_random(db, int(test_user["id"]), count)
                message = f"test_user にロボを {result['created']} 体生成しました。"
            except ValueError as exc:
                message = str(exc)
    return render_template(
        "admin_seed_robots.html",
        message=message,
        result=result,
        params=params,
        test_user=test_user,
    )


def _load_simulation_players(db, sample_mode, robots_limit, power_min=None, power_percentile=None):
    where = []
    params = []
    if sample_mode == "active_only":
        where.append("status = 'active'")
    elif sample_mode == "test_user_only":
        row = db.execute("SELECT id FROM users WHERE username = ?", ("test_user",)).fetchone()
        if not row:
            return []
        where.append("user_id = ?")
        params.append(int(row["id"]))
    elif sample_mode.startswith("user_id:"):
        user_id = int(sample_mode.split(":", 1)[1])
        where.append("user_id = ?")
        params.append(user_id)
    sql = "SELECT id, user_id, status FROM robot_instances"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
    params.append(int(robots_limit))
    rows = db.execute(sql, params).fetchall()
    players = []
    for row in rows:
        calc = _compute_robot_stats_for_instance(db, row["id"])
        if not calc:
            continue
        players.append(
            {
                "robot_id": int(row["id"]),
                "user_id": int(row["user_id"]),
                "status": row["status"],
                "power": int(calc["power"]),
                "archetype": calc.get("archetype") or {"key": "none", "name_ja": "無印"},
                "stats": {
                    "hp": int(calc["stats"]["hp"]),
                    "atk": int(calc["stats"]["atk"]),
                    "def": int(calc["stats"]["def"]),
                    "spd": int(calc["stats"]["spd"]),
                    "acc": int(calc["stats"]["acc"]),
                    "cri": int(calc["stats"]["cri"]),
                },
            }
        )
    if power_min is not None:
        threshold = int(power_min)
        players = [r for r in players if int(r["power"]) >= threshold]
    elif power_percentile is not None:
        p = max(0, min(100, int(power_percentile)))
        if players:
            powers = sorted(int(r["power"]) for r in players)
            idx = max(0, min(len(powers) - 1, math.ceil(len(powers) * p / 100.0) - 1))
            threshold = powers[idx]
            players = [r for r in players if int(r["power"]) >= threshold]
    return players


def _load_simulation_enemies(db, area_key):
    tiers = EXPLORE_AREA_TIERS.get(area_key, ())
    if not tiers:
        return []
    placeholders = ",".join(["?"] * len(tiers))
    rows = db.execute(
        f"""
        SELECT key, name_ja, tier, element, hp, atk, def, spd, acc, cri
        FROM enemies
        WHERE is_active = 1
          AND COALESCE(is_boss, 0) = 0
          AND tier IN ({placeholders})
        ORDER BY id ASC
        """,
        list(tiers),
    ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "key": r["key"],
                "name_ja": r["name_ja"],
                "tier": int(r["tier"]),
                "element": (r["element"] if "element" in r.keys() else None),
                "hp": int(r["hp"]),
                "atk": int(r["atk"]),
                "def": int(r["def"]),
                "spd": int(r["spd"]),
                "acc": int(r["acc"]),
                "cri": int(r["cri"]),
            }
        )
    return out


def _run_balance_simulation(players, enemies, n, rng, area_key=None, enable_archetype=False):
    wins = 0
    total_turns = 0
    timeouts = 0
    enemy_rollup = {
        e["key"]: {"key": e["key"], "name_ja": e["name_ja"], "wins": 0, "battles": 0} for e in enemies
    }
    for _ in range(int(n)):
        player = players[rng.randrange(len(players))]
        if area_key:
            enemy = _pick_enemy_from_rows(enemies, area_key, weekly_env=None, rng=rng)
        else:
            enemy = enemies[rng.randrange(len(enemies))]
        result = simulate_battle(
            player["stats"],
            enemy,
            max_turns=EXPLORE_MAX_TURNS,
            rng=rng,
            player_archetype=player.get("archetype"),
            enemy_archetype=None,
            enable_archetype=bool(enable_archetype),
        )
        if result["win"]:
            wins += 1
            enemy_rollup[enemy["key"]]["wins"] += 1
        if result["timeout"]:
            timeouts += 1
        total_turns += int(result["turns"])
        enemy_rollup[enemy["key"]]["battles"] += 1

    enemy_rows = []
    for row in enemy_rollup.values():
        battles = int(row["battles"])
        if battles <= 0:
            continue
        wins_each = int(row["wins"])
        enemy_rows.append(
            {
                "key": row["key"],
                "name_ja": row["name_ja"],
                "wins": wins_each,
                "battles": battles,
                "win_rate": wins_each / battles,
            }
        )
    enemy_rows.sort(key=lambda x: (x["win_rate"], x["battles"], x["key"]), reverse=True)

    return {
        "win_rate": wins / n,
        "avg_turns": total_turns / n,
        "timeout_rate": timeouts / n,
        "wins": wins,
        "timeouts": timeouts,
        "enemy_rows": enemy_rows,
    }


def _archetype_distribution(players):
    total = len(players)
    counts = {}
    for p in players:
        a = p.get("archetype") or {}
        key = (a.get("key") if isinstance(a, dict) else None) or "none"
        counts[key] = counts.get(key, 0) + 1
    ratios = {}
    if total > 0:
        for k, c in sorted(counts.items(), key=lambda x: x[0]):
            ratios[k] = c / total
    return {"total": total, "counts": counts, "ratios": ratios}


@app.route("/admin/balance")
@login_required
def admin_balance():
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    db = get_db()

    area_key = (request.args.get("area_key") or "layer_1").strip()
    if area_key not in EXPLORE_AREA_TIERS:
        area_key = "layer_1"
    try:
        n = int(request.args.get("n", "1000"))
    except ValueError:
        n = 1000
    n = max(100, min(5000, n))

    sample_mode_ui = (request.args.get("sample_mode") or "all_robots").strip()
    sample_user_id_raw = (request.args.get("sample_user_id") or "").strip()
    sample_mode = "all_robots"
    if sample_mode_ui == "active_only":
        sample_mode = "active_only"
    elif sample_mode_ui == "test_user_only":
        sample_mode = "test_user_only"
    elif sample_mode_ui == "user_id":
        if sample_user_id_raw.isdigit():
            sample_mode = f"user_id:{int(sample_user_id_raw)}"
        else:
            sample_mode = "all_robots"

    seed_raw = (request.args.get("seed") or "").strip()
    seed = None
    if seed_raw:
        try:
            seed = int(seed_raw)
        except ValueError:
            seed = None

    power_min_raw = (request.args.get("power_min") or "").strip()
    power_percentile_raw = (request.args.get("power_percentile") or "").strip()
    power_min = None
    power_percentile = None
    if power_min_raw:
        try:
            power_min = int(power_min_raw)
        except ValueError:
            power_min = None
    if power_min is None and power_percentile_raw:
        try:
            power_percentile = int(power_percentile_raw)
        except ValueError:
            power_percentile = None
        if power_percentile is not None:
            power_percentile = max(0, min(100, power_percentile))
    enable_archetype = (request.args.get("enable_archetype") or "").strip() in {"1", "on", "true", "yes"}
    scenario = (request.args.get("scenario") or "").strip()

    run_requested = (request.args.get("run") or "").strip() == "1"
    message = None
    simulation_result = None
    top_rows = []
    bottom_rows = []
    players_count = 0
    enemies_count = 0
    archetype_distribution = None
    power_filter_payload = {"mode": "none"}
    if power_min is not None:
        power_filter_payload = {"mode": "power_min", "power_min": power_min}
    elif power_percentile is not None:
        power_filter_payload = {"mode": "percentile", "percentile": power_percentile}
    if run_requested:
        players = _load_simulation_players(
            db,
            sample_mode,
            robots_limit=200,
            power_min=power_min,
            power_percentile=power_percentile,
        )
        enemies = _load_simulation_enemies(db, area_key)
        players_count = len(players)
        enemies_count = len(enemies)
        archetype_distribution = _archetype_distribution(players)
        if players_count == 0:
            message = "シミュレーション対象ロボが0件です。sample_mode/powerフィルタを見直してください。"
        elif enemies_count == 0:
            message = "対象エリアの有効敵が0件です。敵マスタを確認してください。"
        else:
            rng = random.Random(seed) if seed is not None else random.Random()
            stats = _run_balance_simulation(
                players,
                enemies,
                n,
                rng,
                area_key=area_key,
                enable_archetype=enable_archetype,
            )
            top_rows = stats["enemy_rows"][:10]
            bottom_rows = sorted(
                stats["enemy_rows"],
                key=lambda x: (x["win_rate"], x["battles"], x["key"]),
            )[:10]
            simulation_result = {
                "win_rate": stats["win_rate"],
                "avg_turns": stats["avg_turns"],
                "timeout_rate": stats["timeout_rate"],
                "wins": stats["wins"],
                "timeouts": stats["timeouts"],
                "n": n,
            }
            _world_event_log(
                db,
                "balance.simulation",
                {
                    "scenario": scenario if scenario else None,
                    "area_key": area_key,
                    "N": n,
                    "sample_mode": sample_mode,
                    "seed": seed,
                    "enable_archetype": bool(enable_archetype),
                    "power_filter": power_filter_payload,
                    "archetype_distribution": archetype_distribution,
                    "win_rate": stats["win_rate"],
                    "avg_turns": stats["avg_turns"],
                    "timeout_rate": stats["timeout_rate"],
                    "enemy_stats": {"top": top_rows, "bottom": bottom_rows},
                },
            )
            db.commit()
            message = "シミュレーションを実行しました。"
    return render_template(
        "admin_balance.html",
        enemy_seed_stats=ENEMY_SEED_STATS,
        coin_reward_by_tier=COIN_REWARD_BY_TIER,
        drop_type_weights_by_tier=DROP_TYPE_WEIGHTS_BY_TIER,
        rarity_weights_by_tier=RARITY_WEIGHTS_BY_TIER,
        plus_weights_by_tier=PLUS_WEIGHTS_BY_TIER,
        fuse_cost_by_plus=FUSE_COST_BY_PLUS,
        explore_areas=EXPLORE_AREAS,
        params={
            "area_key": area_key,
            "n": n,
            "sample_mode": sample_mode_ui,
            "sample_user_id": sample_user_id_raw,
            "seed": seed_raw,
            "enable_archetype": "1" if enable_archetype else "",
            "scenario": scenario,
            "power_min": power_min_raw,
            "power_percentile": power_percentile_raw,
        },
        simulation_result=simulation_result,
        players_count=players_count,
        enemies_count=enemies_count,
        archetype_distribution=archetype_distribution,
        enemy_top_rows=top_rows,
        enemy_bottom_rows=bottom_rows,
        message=message,
    )


@app.route("/admin/world", methods=["GET", "POST"])
@login_required
def admin_world():
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    week_key = _world_week_key()
    message = None
    dry_preview = None
    if request.method == "POST":
        action = (request.form.get("action") or "").strip()
        if action == "dry_run":
            try:
                influence_ratio = float(request.form.get("influence_ratio", "0.30"))
            except ValueError:
                influence_ratio = 0.30
            influence_ratio = _clamp(influence_ratio, 0.0, 1.0)
            next_start = _world_week_bounds(week_key)[0] + timedelta(days=7)
            next_week_key = _world_week_key(next_start.timestamp())
            env = _world_choose_next_environment(db, next_week_key, influence_ratio=influence_ratio)
            dry_preview = {
                "week_key": next_week_key,
                "element": env["element"],
                "mode": env["mode"],
                "enemy_spawn_bonus": env["enemy_spawn_bonus"],
                "drop_bonus": env["drop_bonus"],
                "reason": env["reason"],
                "kills_top": sorted(env["payload"]["kills_raw"].items(), key=lambda x: x[1], reverse=True)[:3],
                "builds_top": sorted(env["payload"]["builds_raw"].items(), key=lambda x: x[1], reverse=True)[:3],
            }
            message = "次週予測（dry-run）を生成しました。"
        elif action == "reroll":
            try:
                influence_ratio = float(request.form.get("influence_ratio", "0.30"))
            except ValueError:
                influence_ratio = 0.30
            influence_ratio = _clamp(influence_ratio, 0.0, 1.0)
            env = _world_choose_next_environment(db, week_key, influence_ratio=influence_ratio)
            start, end = _world_week_bounds(week_key)
            db.execute(
                """
                INSERT INTO world_weekly_environment
                (week_key, element, mode, enemy_spawn_bonus, drop_bonus, started_at, ends_at, random_seed, influence_ratio, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(week_key) DO UPDATE SET
                    element = excluded.element,
                    mode = excluded.mode,
                    enemy_spawn_bonus = excluded.enemy_spawn_bonus,
                    drop_bonus = excluded.drop_bonus,
                    started_at = excluded.started_at,
                    ends_at = excluded.ends_at,
                    random_seed = excluded.random_seed,
                    influence_ratio = excluded.influence_ratio,
                    reason = excluded.reason
                """,
                (
                    week_key,
                    env["element"],
                    env["mode"],
                    env["enemy_spawn_bonus"],
                    env["drop_bonus"],
                    int(start.timestamp()),
                    int(end.timestamp()),
                    env["random_seed"],
                    env["influence_ratio"],
                    env["reason"],
                ),
            )
            _world_event_log(db, "admin_world_reroll", env["payload"])
            db.execute(
                "INSERT INTO chat_messages (user_id, username, message, created_at) VALUES (?, ?, ?, ?)",
                (0, "SYSTEM", f"管理者により今週の戦況が再抽選されました: {env['element']} / {env['mode']}", now_str()),
            )
            db.commit()
            message = "今週の環境を再抽選しました。"
        elif action == "reset_counters":
            deleted = db.execute(
                "DELETE FROM world_weekly_counters WHERE week_key = ?",
                (week_key,),
            ).rowcount
            _world_event_log(db, "admin_world_reset_counters", {"week_key": week_key, "deleted": deleted})
            db.commit()
            message = f"今週カウンタをリセットしました（{deleted}件）。"
        elif action == "research_add":
            element = (request.form.get("element") or "").strip().upper()
            try:
                add_value = int(request.form.get("progress_add", "50"))
            except ValueError:
                add_value = 50
            if element and add_value > 0:
                _ensure_world_research_rows(db)
                row = db.execute(
                    "SELECT progress, unlocked_stage FROM world_research_progress WHERE element = ?",
                    (element,),
                ).fetchone()
                if row:
                    new_progress = max(0, int(row["progress"] or 0) + add_value)
                    db.execute(
                        "UPDATE world_research_progress SET progress = ?, updated_at = ? WHERE element = ?",
                        (new_progress, int(time.time()), element),
                    )
                    db.commit()
                    message = f"研究ゲージを加算しました（{element} +{add_value}）。"
                else:
                    message = f"属性が見つかりません: {element}"
            else:
                message = "研究ゲージ加算の入力が不正です。"
        elif action == "research_reset":
            element = (request.form.get("element") or "").strip().upper()
            if element:
                db.execute(
                    "UPDATE world_research_progress SET progress = 0, unlocked_stage = 0, updated_at = ? WHERE element = ?",
                    (int(time.time()), element),
                )
                db.execute(
                    """
                    UPDATE robot_parts
                    SET is_unlocked = 0
                    WHERE UPPER(COALESCE(rarity, '')) = 'R'
                      AND UPPER(COALESCE(element, '')) = ?
                    """,
                    (element,),
                )
                db.commit()
                message = f"研究状態をリセットしました（{element}）。"
            else:
                message = "リセット対象の属性を指定してください。"
        elif action == "research_force_stage":
            element = (request.form.get("element") or "").strip().upper()
            try:
                stage = int(request.form.get("force_stage", "0"))
            except ValueError:
                stage = 0
            stage = max(0, min(len(RESEARCH_UNLOCK_ORDER), stage))
            if element:
                db.execute(
                    "UPDATE world_research_progress SET unlocked_stage = ?, progress = 0, updated_at = ? WHERE element = ?",
                    (stage, int(time.time()), element),
                )
                db.execute(
                    """
                    UPDATE robot_parts
                    SET is_unlocked = CASE
                        WHEN UPPER(COALESCE(rarity, '')) = 'R'
                             AND UPPER(COALESCE(element, '')) = ?
                             AND part_type IN (
                                 CASE WHEN ? >= 1 THEN 'HEAD' ELSE '' END,
                                 CASE WHEN ? >= 2 THEN 'RIGHT_ARM' ELSE '' END,
                                 CASE WHEN ? >= 3 THEN 'LEFT_ARM' ELSE '' END,
                                 CASE WHEN ? >= 4 THEN 'LEGS' ELSE '' END
                             )
                        THEN 1
                        WHEN UPPER(COALESCE(rarity, '')) = 'R'
                             AND UPPER(COALESCE(element, '')) = ?
                        THEN 0
                        ELSE is_unlocked
                    END
                    """,
                    (element, stage, stage, stage, stage, element),
                )
                db.commit()
                message = f"研究ステージを強制更新しました（{element}: stage={stage}）。"
            else:
                message = "強制進行の属性を指定してください。"
    env_row = _world_current_environment(db)
    research_rows = _world_research_progress_rows(db)
    counters = db.execute(
        """
        SELECT metric_key, value
        FROM world_weekly_counters
        WHERE week_key = ?
        ORDER BY metric_key ASC
        """,
        (week_key,),
    ).fetchall()
    return render_template(
        "admin_world.html",
        message=message,
        week_key=week_key,
        env_row=env_row,
        counters=counters,
        dry_preview=dry_preview,
        research_rows=research_rows,
        research_unlock_order=RESEARCH_UNLOCK_ORDER,
        faction_week_scores=_faction_week_scores(db, week_key),
        faction_week_result=_faction_week_result(db, week_key),
    )


@app.route("/admin/world/faction-war/recompute", methods=["GET"])
@login_required
def admin_world_faction_war_recompute():
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    week_key = (request.args.get("week_key") or "").strip() or _world_week_key()
    try:
        _world_week_bounds(week_key)
    except Exception:
        flash("week_key が不正です。例: 2026-W10", "error")
        return redirect(url_for("admin_world"))
    result = _faction_war_recompute(db, week_key)
    db.commit()
    flash(
        f"陣営戦を再集計しました（{result['week_key']} / 勝者: {FACTION_LABELS.get(result['winner_faction'], result['winner_faction'])}）。",
        "notice",
    )
    return redirect(url_for("admin_world"))


@app.route("/admin/audit")
@login_required
def admin_audit():
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    user_id_raw = (request.args.get("user_id") or "").strip()
    event_type = (request.args.get("event_type") or "").strip()
    request_id = (request.args.get("request_id") or "").strip()
    after_raw = (request.args.get("after") or "").strip()
    before_raw = (request.args.get("before") or "").strip()
    limit_raw = (request.args.get("limit") or "100").strip()
    try:
        limit = max(1, min(500, int(limit_raw)))
    except ValueError:
        limit = 100
    where = ["1=1"]
    params = []
    if user_id_raw.isdigit():
        where.append("user_id = ?")
        params.append(int(user_id_raw))
    if event_type:
        where.append("event_type = ?")
        params.append(event_type)
    if request_id:
        where.append("request_id = ?")
        params.append(request_id)
    if after_raw.isdigit():
        where.append("created_at >= ?")
        params.append(int(after_raw))
    if before_raw.isdigit():
        where.append("created_at <= ?")
        params.append(int(before_raw))
    rows = db.execute(
        f"""
        SELECT *
        FROM world_events_log
        WHERE {' AND '.join(where)}
        ORDER BY id DESC
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()
    return render_template(
        "admin_audit.html",
        rows=rows,
        selected_user_id=user_id_raw,
        selected_event_type=event_type,
        selected_request_id=request_id,
        selected_after=after_raw,
        selected_before=before_raw,
        selected_limit=limit,
    )


@app.route("/admin/npc-bosses", methods=["GET", "POST"])
@login_required
def admin_npc_bosses():
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    message = None
    if request.method == "POST":
        template_id = request.form.get("template_id", type=int)
        next_state = request.form.get("next_state", type=int)
        if template_id is not None and next_state in {0, 1}:
            db.execute(
                "UPDATE npc_boss_templates SET is_active = ?, updated_at = ? WHERE id = ?",
                (int(next_state), int(time.time()), int(template_id)),
            )
            db.commit()
            message = "NPCボステンプレの状態を更新しました。"
    rows = db.execute(
        """
        SELECT id, enemy_name_ja, source_user_id, source_robot_instance_id, boss_area_key, is_active, created_at
        FROM npc_boss_templates
        ORDER BY updated_at DESC, id DESC
        LIMIT 300
        """
    ).fetchall()
    return render_template("admin_npc_bosses.html", rows=rows, message=message)


@app.route("/admin/enemies")
@login_required
def admin_enemies():
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    q = (request.args.get("q") or "").strip()
    tier_raw = (request.args.get("tier") or "").strip()
    element = (request.args.get("element") or "").strip().upper()
    faction = (request.args.get("faction") or "").strip().lower()
    active_raw = (request.args.get("is_active") or "all").strip().lower()
    boss_raw = (request.args.get("is_boss") or "all").strip().lower()
    boss_area = (request.args.get("boss_area_key") or "").strip().lower()

    where = ["1=1"]
    params = []
    if q:
        where.append("(key LIKE ? OR name_ja LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like])
    if tier_raw in {"1", "2", "3", "4"}:
        where.append("tier = ?")
        params.append(int(tier_raw))
    if element:
        where.append("element = ?")
        params.append(element)
    if faction in FACTION_LABELS:
        where.append("faction = ?")
        params.append(faction)
    if active_raw in {"0", "1"}:
        where.append("is_active = ?")
        params.append(int(active_raw))
    if boss_raw in {"0", "1"}:
        where.append("COALESCE(is_boss, 0) = ?")
        params.append(int(boss_raw))
    if boss_area in AREA_BOSS_KEYS:
        where.append("boss_area_key = ?")
        params.append(boss_area)

    rows = db.execute(
        f"SELECT * FROM enemies WHERE {' AND '.join(where)} ORDER BY tier ASC, key ASC",
        params,
    ).fetchall()
    enemies = []
    for row in rows:
        d = dict(row)
        d["display_image_path"] = _enemy_image_rel(d.get("image_path"))
        enemies.append(d)
    return render_template(
        "admin_enemies.html",
        enemies=enemies,
        q=q,
        tier=tier_raw,
        selected_element=element,
        selected_faction=faction,
        selected_active=active_raw,
        selected_boss=boss_raw,
        selected_boss_area=boss_area,
        element_options=ELEMENTS,
        faction_options=FACTION_LABELS,
        boss_area_options=AREA_BOSS_KEYS,
    )


@app.route("/admin/enemies/import", methods=["GET", "POST"])
@login_required
def admin_enemies_import():
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    message = None
    csv_text = ""
    preview = []
    summary = None
    if request.method == "POST":
        action = request.form.get("action", "dry_run")
        csv_text = request.form.get("csv_text", "")
        csv_file = request.files.get("csv_file")
        source, err = _parse_enemy_csv_source(csv_file, csv_text)
        if err:
            message = err
        else:
            csv_text = source
            preview = _enemy_import_preview(db, source)
            counts = {"create": 0, "update": 0, "skip": 0, "error": 0}
            for row in preview:
                key = row.get("action")
                if key in counts:
                    counts[key] += 1
            summary = counts

            if action == "import":
                if counts["error"] > 0:
                    message = "エラー行があるためインポートできません。先に修正してください。"
                else:
                    try:
                        db.execute("BEGIN IMMEDIATE")
                        for row in preview:
                            if row["action"] == "skip":
                                continue
                            d = row["data"]
                            exists = db.execute("SELECT 1 FROM enemies WHERE key = ?", (d["key"],)).fetchone()
                            if exists:
                                db.execute(
                                    """
                                    UPDATE enemies
                                    SET name_ja = ?, tier = ?, element = ?, hp = ?, atk = ?, def = ?, spd = ?, acc = ?, cri = ?, image_path = ?, faction = ?, is_boss = ?, boss_area_key = ?, is_active = ?
                                    WHERE key = ?
                                    """,
                                    (
                                        d["name_ja"],
                                        d["tier"],
                                        d["element"],
                                        d["hp"],
                                        d["atk"],
                                        d["def"],
                                        d["spd"],
                                        d["acc"],
                                        d["cri"],
                                        d["image_path"],
                                        d["faction"],
                                        d["is_boss"],
                                        d["boss_area_key"],
                                        d["is_active"],
                                        d["key"],
                                    ),
                                )
                            else:
                                db.execute(
                                    """
                                    INSERT INTO enemies (key, name_ja, image_path, tier, element, hp, atk, def, spd, acc, cri, faction, is_boss, boss_area_key, is_active)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """,
                                    (
                                        d["key"],
                                        d["name_ja"],
                                        d["image_path"],
                                        d["tier"],
                                        d["element"],
                                        d["hp"],
                                        d["atk"],
                                        d["def"],
                                        d["spd"],
                                        d["acc"],
                                        d["cri"],
                                        d["faction"],
                                        d["is_boss"],
                                        d["boss_area_key"],
                                        d["is_active"],
                                    ),
                                )
                        db.commit()
                        message = (
                            f"インポート完了: 追加 {counts['create']} / 更新 {counts['update']} / "
                            f"スキップ {counts['skip']} / エラー {counts['error']}"
                        )
                    except Exception as exc:
                        db.rollback()
                        message = f"インポート失敗（ロールバック）: {exc}"
            else:
                message = (
                    f"検証結果: 追加 {counts['create']} / 更新 {counts['update']} / "
                    f"スキップ {counts['skip']} / エラー {counts['error']}"
                )

    return render_template(
        "admin_enemies_import.html",
        message=message,
        csv_text=csv_text,
        preview=preview,
        summary=summary,
    )


@app.route("/admin/enemies/new", methods=["GET", "POST"])
@login_required
def admin_enemy_new():
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    message = None
    if request.method == "POST":
        key = _clean_key(request.form.get("key"))
        name_ja = (request.form.get("name_ja") or "").strip()
        element = _normalize_enemy_element(request.form.get("element"))
        faction = (request.form.get("faction") or "neutral").strip().lower()
        is_boss = 1 if request.form.get("is_boss") == "1" else 0
        boss_area_key = (request.form.get("boss_area_key") or "").strip().lower() or None
        image = request.files.get("image")
        try:
            tier = int(request.form.get("tier", "1"))
            hp = int(request.form.get("hp", "1"))
            atk = int(request.form.get("atk", "1"))
            deff = int(request.form.get("def", "1"))
            spd = int(request.form.get("spd", "1"))
            acc = int(request.form.get("acc", "1"))
            cri = int(request.form.get("cri", "1"))
        except ValueError:
            tier = 0
            hp = atk = deff = spd = acc = cri = -1
        is_active = 1 if request.form.get("is_active") == "1" else 0
        valid_elements = {code for code, _ in ELEMENTS}
        if not key or not name_ja:
            message = "key と表示名は必須です。"
        elif tier not in {1, 2, 3, 4}:
            message = "tier は 1〜4 で入力してください。"
        elif element not in valid_elements:
            message = "属性が不正です。"
        elif faction not in FACTION_LABELS:
            message = "所属が不正です。"
        elif is_boss == 1 and boss_area_key not in AREA_BOSS_KEYS:
            message = "ボス敵は出現エリア（layer_1/layer_2/layer_3）を指定してください。"
        elif min(hp, atk, deff, spd, acc, cri) < 0:
            message = "ステータスは0以上の整数で入力してください。"
        elif db.execute("SELECT 1 FROM enemies WHERE key = ?", (key,)).fetchone():
            message = "同じ key が既に存在します。"
        else:
            if is_boss == 0:
                boss_area_key = None
            image_path = None
            if image and image.filename:
                ok, err = _validate_enemy_png(image)
                if not ok:
                    message = err
                else:
                    rel = f"enemies/{key}.png"
                    abs_path = _static_abs(rel)
                    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                    img = Image.open(image.stream).convert("RGBA")
                    img.save(abs_path, format="PNG")
                    image.stream.seek(0)
                    image_path = rel
            if message is None:
                db.execute(
                    """
                    INSERT INTO enemies (key, name_ja, image_path, tier, element, hp, atk, def, spd, acc, cri, faction, is_boss, boss_area_key, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (key, name_ja, image_path, tier, element, hp, atk, deff, spd, acc, cri, faction, is_boss, boss_area_key, is_active),
                )
                db.commit()
                session["message"] = "敵を作成しました。"
                return redirect(url_for("admin_enemies"))
    return render_template(
        "admin_enemy_form.html",
        mode="new",
        enemy=None,
        message=message,
        element_options=ELEMENTS,
        faction_options=FACTION_LABELS,
        boss_area_options=AREA_BOSS_KEYS,
    )


@app.route("/admin/enemies/<string:key>/edit", methods=["GET", "POST"])
@login_required
def admin_enemy_edit(key):
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    enemy = db.execute("SELECT * FROM enemies WHERE key = ?", (key,)).fetchone()
    if not enemy:
        return abort(404)
    message = None
    if request.method == "POST":
        name_ja = (request.form.get("name_ja") or "").strip()
        element = _normalize_enemy_element(request.form.get("element"))
        faction = (request.form.get("faction") or "neutral").strip().lower()
        is_boss = 1 if request.form.get("is_boss") == "1" else 0
        boss_area_key = (request.form.get("boss_area_key") or "").strip().lower() or None
        image = request.files.get("image")
        try:
            tier = int(request.form.get("tier", "1"))
            hp = int(request.form.get("hp", "1"))
            atk = int(request.form.get("atk", "1"))
            deff = int(request.form.get("def", "1"))
            spd = int(request.form.get("spd", "1"))
            acc = int(request.form.get("acc", "1"))
            cri = int(request.form.get("cri", "1"))
        except ValueError:
            tier = 0
            hp = atk = deff = spd = acc = cri = -1
        is_active = 1 if request.form.get("is_active") == "1" else 0
        valid_elements = {code for code, _ in ELEMENTS}
        if not name_ja:
            message = "表示名は必須です。"
        elif tier not in {1, 2, 3, 4}:
            message = "tier は 1〜4 で入力してください。"
        elif element not in valid_elements:
            message = "属性が不正です。"
        elif faction not in FACTION_LABELS:
            message = "所属が不正です。"
        elif is_boss == 1 and boss_area_key not in AREA_BOSS_KEYS:
            message = "ボス敵は出現エリア（layer_1/layer_2/layer_3）を指定してください。"
        elif min(hp, atk, deff, spd, acc, cri) < 0:
            message = "ステータスは0以上の整数で入力してください。"
        else:
            if is_boss == 0:
                boss_area_key = None
            image_path = enemy["image_path"]
            if image and image.filename:
                ok, err = _validate_enemy_png(image)
                if not ok:
                    message = err
                else:
                    rel = f"enemies/{enemy['key']}.png"
                    abs_path = _static_abs(rel)
                    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                    img = Image.open(image.stream).convert("RGBA")
                    img.save(abs_path, format="PNG")
                    image.stream.seek(0)
                    image_path = rel
            if message is None:
                db.execute(
                    """
                    UPDATE enemies
                    SET name_ja = ?, image_path = ?, tier = ?, element = ?,
                        hp = ?, atk = ?, def = ?, spd = ?, acc = ?, cri = ?, faction = ?, is_boss = ?, boss_area_key = ?, is_active = ?
                    WHERE key = ?
                    """,
                    (name_ja, image_path, tier, element, hp, atk, deff, spd, acc, cri, faction, is_boss, boss_area_key, is_active, enemy["key"]),
                )
                db.commit()
                session["message"] = "敵情報を更新しました。"
                return redirect(url_for("admin_enemy_edit", key=enemy["key"]))
    enemy_dict = dict(enemy)
    enemy_dict["display_image_path"] = _enemy_image_rel(enemy_dict.get("image_path"))
    return render_template(
        "admin_enemy_form.html",
        mode="edit",
        enemy=enemy_dict,
        message=message,
        element_options=ELEMENTS,
        faction_options=FACTION_LABELS,
        boss_area_options=AREA_BOSS_KEYS,
    )


@app.route("/admin/enemies/<string:key>/toggle_active", methods=["POST"])
@login_required
def admin_enemy_toggle_active(key):
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    row = db.execute("SELECT key, is_active FROM enemies WHERE key = ?", (key,)).fetchone()
    if not row:
        session["message"] = "対象の敵が見つかりません。"
        return redirect(url_for("admin_enemies"))
    next_state = 0 if int(row["is_active"]) == 1 else 1
    db.execute("UPDATE enemies SET is_active = ? WHERE key = ?", (next_state, key))
    db.commit()
    session["message"] = "敵の有効状態を更新しました。"
    return redirect(url_for("admin_enemies"))


@app.route("/admin/parts", methods=["GET", "POST"])
@login_required
def admin_parts():
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    element_codes = {code for code, _ in ELEMENTS}
    show_inactive = request.args.get("show_inactive", "0") == "1"
    edit_id_raw = (request.args.get("edit_id") or "").strip()
    edit_id = int(edit_id_raw) if edit_id_raw.isdigit() else None
    editing = None
    message = None
    if request.method == "POST":
        edit_part_id_raw = (request.form.get("edit_part_id") or "").strip()
        edit_part_id = int(edit_part_id_raw) if edit_part_id_raw.isdigit() else None
        part_type = (request.form.get("part_type") or "").upper()
        raw_key = _clean_key(request.form.get("key"))
        key = f"{part_type.lower()}_{raw_key}" if raw_key and not raw_key.startswith(part_type.lower() + "_") else raw_key
        rarity = (request.form.get("rarity") or "N").upper()
        element = (request.form.get("element") or "NORMAL").upper()
        series = (request.form.get("series") or "S1").strip() or "S1"
        display_name_ja = (request.form.get("display_name_ja") or "").strip()
        try:
            offset_x = int(request.form.get("offset_x", 0))
            offset_y = int(request.form.get("offset_y", 0))
        except ValueError:
            offset_x = 0
            offset_y = 0
        file = request.files.get("image")
        if part_type not in {"HEAD", "RIGHT_ARM", "LEFT_ARM", "LEGS"}:
            message = "パーツ種別を選択してください。"
        elif rarity not in RARITIES:
            message = "レアリティが不正です。"
        elif element not in element_codes:
            message = "属性が不正です。"
        elif not raw_key:
            message = "キーを指定してください。"
        elif not file:
            existing = None
            if edit_part_id is not None:
                existing = db.execute("SELECT * FROM robot_parts WHERE id = ?", (edit_part_id,)).fetchone()
            if existing is None:
                existing = db.execute("SELECT * FROM robot_parts WHERE key = ?", (key,)).fetchone()
            if existing:
                db.execute(
                    "UPDATE robot_parts SET part_type = ?, key = ?, rarity = ?, element = ?, series = ?, display_name_ja = ?, offset_x = ?, offset_y = ? WHERE id = ?",
                    (part_type, key, rarity, element, series, (display_name_ja or None), offset_x, offset_y, existing["id"]),
                )
                _invalidate_composed_images_for_offset_change(db)
                refresh_part_offset_cache(db)
                db.commit()
                message = "パーツ情報を更新しました。"
            else:
                message = "新規登録には画像が必要です。"
        else:
            ok, err, warn = _validate_png(file)
            if not ok:
                message = err
            else:
                folder = {
                    "HEAD": "parts/head",
                    "RIGHT_ARM": "parts/right_arm",
                    "LEFT_ARM": "parts/left_arm",
                    "LEGS": "parts/legs",
                }[part_type]
                rel_path = f"{folder}/{key}.png"
                _save_png(file, rel_path)
                if edit_part_id is not None:
                    db.execute(
                        "UPDATE robot_parts SET part_type = ?, key = ?, image_path = ?, rarity = ?, element = ?, series = ?, display_name_ja = ?, offset_x = ?, offset_y = ?, is_active = 1 WHERE id = ?",
                        (part_type, key, rel_path, rarity, element, series, (display_name_ja or None), offset_x, offset_y, edit_part_id),
                    )
                else:
                    db.execute(
                        "INSERT INTO robot_parts (part_type, key, image_path, rarity, element, series, display_name_ja, offset_x, offset_y, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?) ON CONFLICT(key) DO UPDATE SET part_type = excluded.part_type, image_path = excluded.image_path, rarity = excluded.rarity, element = excluded.element, series = excluded.series, display_name_ja = excluded.display_name_ja, offset_x = excluded.offset_x, offset_y = excluded.offset_y, is_active = 1",
                        (part_type, key, rel_path, rarity, element, series, (display_name_ja or None), offset_x, offset_y, int(time.time())),
                    )
                _invalidate_composed_images_for_offset_change(db)
                refresh_part_offset_cache(db)
                db.commit()
                message = "パーツを保存しました。"
                if warn:
                    message += f" 注意: {warn}"
    if show_inactive:
        rows = db.execute("SELECT * FROM robot_parts ORDER BY id DESC LIMIT 200").fetchall()
    else:
        rows = db.execute("SELECT * FROM robot_parts WHERE is_active = 1 ORDER BY id DESC LIMIT 200").fetchall()
    rows = [
        {
            **dict(r),
            "display_name_resolved": _part_display_name_ja(r),
            "display_name_is_fallback": (not bool((r["display_name_ja"] or "").strip())) if "display_name_ja" in r.keys() else True,
        }
        for r in rows
    ]
    if edit_id is not None:
        editing = db.execute("SELECT * FROM robot_parts WHERE id = ?", (edit_id,)).fetchone()

    return render_template(
        "admin_parts.html",
        rows=rows,
        message=message,
        show_inactive=show_inactive,
        editing=editing,
        rarity_options=RARITIES,
        element_options=ELEMENTS,
        element_labels=ELEMENT_LABEL_MAP,
    )


@app.route("/admin/parts/align", methods=["GET", "POST"])
@login_required
def admin_parts_align():
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)

    def _default_base_key(rows, part_type):
        candidates = [r for r in rows if r["part_type"] == part_type and int(r["is_active"] or 0) == 1]
        if not candidates:
            return ""
        keyed = next((r for r in candidates if str(r["key"]).endswith("_1")), None)
        return keyed["key"] if keyed else candidates[0]["key"]

    rows = db.execute(
        """
        SELECT id, key, part_type, image_path, offset_x, offset_y, is_active
        FROM robot_parts
        ORDER BY part_type ASC, key ASC
        """
    ).fetchall()
    row_by_key = {r["key"]: r for r in rows}
    row_by_id = {int(r["id"]): r for r in rows}

    selected_part_key = (request.values.get("target_part_key") or request.values.get("part_key") or "").strip()
    part_id_raw = (request.values.get("part_id") or "").strip()
    part_id = int(part_id_raw) if part_id_raw.isdigit() else None
    if not selected_part_key and part_id is not None and part_id in row_by_id:
        selected_part_key = row_by_id[part_id]["key"]
    if not selected_part_key:
        first_active = next((r for r in rows if int(r["is_active"] or 0) == 1), None)
        if first_active:
            selected_part_key = first_active["key"]
    selected_part = row_by_key.get(selected_part_key)

    base_head_key = (request.values.get("base_head") or request.values.get("base_head_key") or "").strip()
    base_r_arm_key = (request.values.get("base_right") or request.values.get("base_r_arm_key") or "").strip()
    base_l_arm_key = (request.values.get("base_left") or request.values.get("base_l_arm_key") or "").strip()
    base_legs_key = (request.values.get("base_legs") or request.values.get("base_legs_key") or "").strip()

    if not base_head_key:
        base_head_key = _default_base_key(rows, "HEAD")
    if not base_r_arm_key:
        base_r_arm_key = _default_base_key(rows, "RIGHT_ARM")
    if not base_l_arm_key:
        base_l_arm_key = _default_base_key(rows, "LEFT_ARM")
    if not base_legs_key:
        base_legs_key = _default_base_key(rows, "LEGS")

    if request.method == "POST":
        selected_part_key = (request.form.get("target_part_key") or request.form.get("part_key") or "").strip()
        base_head_key = (request.form.get("base_head") or request.form.get("base_head_key") or "").strip()
        base_r_arm_key = (request.form.get("base_right") or request.form.get("base_r_arm_key") or "").strip()
        base_l_arm_key = (request.form.get("base_left") or request.form.get("base_l_arm_key") or "").strip()
        base_legs_key = (request.form.get("base_legs") or request.form.get("base_legs_key") or "").strip()
        selected_part = row_by_key.get(selected_part_key)
        if not selected_part:
            flash("対象パーツを選択してください。", "error")
        else:
            try:
                new_x = int(request.form.get("offset_x", selected_part["offset_x"]))
                new_y = int(request.form.get("offset_y", selected_part["offset_y"]))
            except ValueError:
                new_x = int(selected_part["offset_x"] or 0)
                new_y = int(selected_part["offset_y"] or 0)
            db.execute(
                "UPDATE robot_parts SET offset_x = ?, offset_y = ? WHERE key = ?",
                (new_x, new_y, selected_part_key),
            )
            _invalidate_composed_images_for_offset_change(db)
            refresh_part_offset_cache(db)
            db.commit()
            flash(f"オフセットを更新しました（{selected_part_key}: x={new_x}, y={new_y}）。", "notice")
            return redirect(
                url_for(
                    "admin_parts_align",
                    target_part_key=selected_part_key,
                    base_head=base_head_key,
                    base_right=base_r_arm_key,
                    base_left=base_l_arm_key,
                    base_legs=base_legs_key,
                )
            )

    if selected_part:
        if selected_part["part_type"] == "HEAD":
            base_head_key = selected_part["key"]
        elif selected_part["part_type"] == "RIGHT_ARM":
            base_r_arm_key = selected_part["key"]
        elif selected_part["part_type"] == "LEFT_ARM":
            base_l_arm_key = selected_part["key"]
        elif selected_part["part_type"] == "LEGS":
            base_legs_key = selected_part["key"]

    preview_parts = {
        "HEAD": row_by_key.get(base_head_key),
        "RIGHT_ARM": row_by_key.get(base_r_arm_key),
        "LEFT_ARM": row_by_key.get(base_l_arm_key),
        "LEGS": row_by_key.get(base_legs_key),
    }
    preview_layers = {}
    for slot, row in preview_parts.items():
        if row and row["image_path"]:
            preview_layers[slot] = {
                "key": row["key"],
                "image_url": url_for("static", filename=f"robot_assets/{row['image_path']}"),
                "offset_x": int(row["offset_x"] or 0),
                "offset_y": int(row["offset_y"] or 0),
            }
        else:
            preview_layers[slot] = None

    options = {
        "HEAD": [r for r in rows if r["part_type"] == "HEAD"],
        "RIGHT_ARM": [r for r in rows if r["part_type"] == "RIGHT_ARM"],
        "LEFT_ARM": [r for r in rows if r["part_type"] == "LEFT_ARM"],
        "LEGS": [r for r in rows if r["part_type"] == "LEGS"],
    }
    part_meta = {}
    for r in rows:
        part_meta[r["key"]] = {
            "part_type": r["part_type"],
            "offset_x": int(r["offset_x"] or 0),
            "offset_y": int(r["offset_y"] or 0),
            "image_url": (url_for("static", filename=f"robot_assets/{r['image_path']}") if r["image_path"] else ""),
        }

    return render_template(
        "admin_parts_align.html",
        selected_part=selected_part,
        preview_layers=preview_layers,
        options=options,
        rows=rows,
        part_meta=part_meta,
        base_head_key=base_head_key,
        base_r_arm_key=base_r_arm_key,
        base_l_arm_key=base_l_arm_key,
        base_legs_key=base_legs_key,
    )


@app.route("/admin/parts/<int:part_id>/toggle_active", methods=["POST"])
@login_required
def admin_parts_toggle_active(part_id):
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    row = db.execute("SELECT id, is_active FROM robot_parts WHERE id = ?", (part_id,)).fetchone()
    if not row:
        session["message"] = "対象パーツが見つかりません。"
        return redirect(url_for("admin_parts"))
    next_state = 0 if row["is_active"] == 1 else 1
    db.execute("UPDATE robot_parts SET is_active = ? WHERE id = ?", (next_state, part_id))
    db.commit()
    session["message"] = "パーツ状態を更新しました。"
    return redirect(url_for("admin_parts", show_inactive=1))


@app.route("/admin/decor", methods=["GET", "POST"])
@login_required
def admin_decor():
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    message = None
    if request.method == "POST":
        key = _clean_key(request.form.get("key"))
        name_ja = (request.form.get("name_ja") or "").strip()
        file = request.files.get("image")
        existing = db.execute("SELECT id, image_path FROM robot_decor_assets WHERE key = ?", (key,)).fetchone() if key else None
        if not key:
            message = "keyを入力してください。"
        elif not name_ja:
            message = "表示名を入力してください。"
        elif not file or not file.filename:
            rel_path = existing["image_path"] if existing and existing["image_path"] else DECOR_PLACEHOLDER_REL
            db.execute(
                """
                INSERT INTO robot_decor_assets (key, name_ja, image_path, is_active, created_at)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(key) DO UPDATE SET name_ja = excluded.name_ja, image_path = excluded.image_path, is_active = 1
                """,
                (key, name_ja, rel_path, int(time.time())),
            )
            db.execute("UPDATE robot_instances SET composed_image_path = NULL")
            db.commit()
            message = "装飾アセットを保存しました。画像未指定のためプレースホルダを使用します。"
        else:
            ok, err, warns = _validate_decor_png_soft(file)
            if not ok:
                message = err
            else:
                rel_path = f"decor/{key}.png"
                _save_static_png(file, rel_path)
                db.execute(
                    """
                    INSERT INTO robot_decor_assets (key, name_ja, image_path, is_active, created_at)
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(key) DO UPDATE SET name_ja = excluded.name_ja, image_path = excluded.image_path, is_active = 1
                    """,
                    (key, name_ja, rel_path, int(time.time())),
                )
                db.execute("UPDATE robot_instances SET composed_image_path = NULL")
                db.commit()
                message = "装飾アセットを保存しました。"
                if warns:
                    message += " " + " / ".join(warns)
    rows = db.execute(
        "SELECT * FROM robot_decor_assets ORDER BY id DESC LIMIT 300"
    ).fetchall()
    rows = [{**dict(r), "display_image_path": _decor_image_rel(r["image_path"], r["key"])} for r in rows]
    return render_template("admin_decor.html", rows=rows, message=message)


@app.route("/admin/decor/<int:decor_id>/toggle_active", methods=["POST"])
@login_required
def admin_decor_toggle_active(decor_id):
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    row = db.execute("SELECT id, is_active FROM robot_decor_assets WHERE id = ?", (decor_id,)).fetchone()
    if not row:
        session["message"] = "対象装飾が見つかりません。"
        return redirect(url_for("admin_decor"))
    next_state = 0 if int(row["is_active"]) == 1 else 1
    db.execute("UPDATE robot_decor_assets SET is_active = ? WHERE id = ?", (next_state, decor_id))
    db.execute("UPDATE robot_instances SET composed_image_path = NULL")
    db.commit()
    session["message"] = "装飾の有効状態を更新しました。"
    return redirect(url_for("admin_decor"))


@app.route("/admin/parts/<int:part_id>/delete", methods=["POST"])
@login_required
def admin_parts_delete(part_id):
    db = get_db()
    if not _is_admin_user(session["user_id"]):
        return abort(403)

    if request.form.get("confirm_delete") != "1" or request.form.get("danger_word", "") != "DELETE":
        session["message"] = "完全削除にはチェックと DELETE 入力が必要です。"
        return redirect(url_for("admin_parts", show_inactive=1))

    part = db.execute("SELECT * FROM robot_parts WHERE id = ?", (part_id,)).fetchone()
    if not part:
        session["message"] = "対象パーツが見つかりません。"
        return redirect(url_for("admin_parts", show_inactive=1))

    key = part["key"]
    ref_counts = {
        "inventory": db.execute(
            "SELECT COUNT(*) AS c FROM user_parts_inventory WHERE part_key = ?",
            (key,),
        ).fetchone()["c"],
        "instances": db.execute(
            """
            SELECT COUNT(*) AS c FROM robot_instance_parts
            WHERE head_key = ? OR r_arm_key = ? OR l_arm_key = ? OR legs_key = ?
            """,
            (key, key, key, key),
        ).fetchone()["c"],
        "builds": db.execute(
            """
            SELECT COUNT(*) AS c FROM robot_builds
            WHERE head_key = ? OR r_arm_key = ? OR l_arm_key = ? OR legs_key = ?
            """,
            (key, key, key, key),
        ).fetchone()["c"],
        "milestones": db.execute(
            """
            SELECT COUNT(*) AS c FROM robot_milestones
            WHERE reward_head_key = ? OR reward_r_arm_key = ? OR reward_l_arm_key = ? OR reward_legs_key = ?
            """,
            (key, key, key, key),
        ).fetchone()["c"],
    }
    if any(v > 0 for v in ref_counts.values()):
        rows = db.execute("SELECT * FROM robot_parts ORDER BY id DESC LIMIT 200").fetchall()
        message = (
            "使用中のため削除不可です。"
            f" 在庫:{ref_counts['inventory']} / 所有ロボ:{ref_counts['instances']} /"
            f" 設計:{ref_counts['builds']} / 報酬:{ref_counts['milestones']}"
        )
        return render_template("admin_parts.html", rows=rows, message=message, show_inactive=True), 409

    image_path = part["image_path"]
    db.execute("DELETE FROM robot_parts WHERE id = ?", (part_id,))
    db.commit()

    # Shared path guard: remove file only when no remaining row references this path.
    remain = db.execute("SELECT COUNT(*) AS c FROM robot_parts WHERE image_path = ?", (image_path,)).fetchone()["c"]
    if remain == 0 and image_path:
        abs_path = _asset_abs(image_path)
        if os.path.exists(abs_path):
            try:
                os.remove(abs_path)
            except OSError:
                pass

    session["message"] = "パーツを完全削除しました。"
    return redirect(url_for("admin_parts", show_inactive=1))


@app.route("/admin/parts/<int:part_id>/purge_confirm", methods=["GET"])
@login_required
def admin_parts_purge_confirm(part_id):
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    db = get_db()
    part = db.execute("SELECT * FROM robot_parts WHERE id = ?", (part_id,)).fetchone()
    part_key = part["key"] if part else None
    counts = _part_purge_counts(db, part_key)
    return render_template(
        "admin_part_purge_confirm.html",
        part=part,
        part_id=part_id,
        counts=counts,
    )


@app.route("/admin/parts/<int:part_id>/purge", methods=["POST"])
@login_required
def admin_parts_purge(part_id):
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    db = get_db()
    typed_part_id = request.form.get("typed_part_id", "").strip()
    confirm_word = request.form.get("confirm_word", "").strip()
    acknowledged = request.form.get("acknowledged") == "1"

    if typed_part_id != str(part_id) or confirm_word != "I UNDERSTAND" or not acknowledged:
        session["message"] = "確認入力が一致しません。part_id 手入力と I UNDERSTAND が必要です。"
        return redirect(url_for("admin_parts_purge_confirm", part_id=part_id))

    part = db.execute("SELECT * FROM robot_parts WHERE id = ?", (part_id,)).fetchone()
    if not part:
        session["message"] = "対象パーツは既に存在しません。削除件数 0 件。"
        return redirect(url_for("admin_parts", show_inactive=1))

    try:
        result = _purge_part_with_dependencies(db, part)
        session["message"] = (
            "危険一括削除を実行しました。"
            f" 個体:{result['part_instances']} / 在庫:{result['inventory']} / 所有ロボ:{result['instances']} / 設計:{result['builds']} /"
            f" 報酬:{result['milestones']} / 旧所持:{result['legacy_user_robots']} / パーツ本体:{result['part']}"
        )
        return redirect(url_for("admin_parts", show_inactive=1))
    except Exception as exc:
        db.rollback()
        session["message"] = f"危険一括削除に失敗しました: {exc}"
        return redirect(url_for("admin_parts_purge_confirm", part_id=part_id))


@app.route("/admin/parts/<int:part_id>/purge_quick", methods=["POST"])
@login_required
def admin_parts_purge_quick(part_id):
    if not _is_admin_user(session["user_id"]):
        return abort(403)
    if not DEV_MODE:
        session["message"] = "開発環境のみ利用できます。"
        return redirect(url_for("admin_parts", show_inactive=1))
    db = get_db()
    part = db.execute("SELECT * FROM robot_parts WHERE id = ?", (part_id,)).fetchone()
    if not part:
        session["message"] = "対象パーツは既に存在しません。削除件数 0 件。"
        return redirect(url_for("admin_parts", show_inactive=1))
    try:
        result = _purge_part_with_dependencies(db, part)
        session["message"] = (
            "開発用クイック削除を実行しました。"
            f" 個体:{result['part_instances']} / 在庫:{result['inventory']} / 所有ロボ:{result['instances']} / 設計:{result['builds']} /"
            f" 報酬:{result['milestones']} / 旧所持:{result['legacy_user_robots']} / パーツ本体:{result['part']}"
        )
    except Exception as exc:
        db.rollback()
        session["message"] = f"開発用クイック削除に失敗しました: {exc}"
    return redirect(url_for("admin_parts", show_inactive=1))


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "5050")),
        debug=True,
    )
