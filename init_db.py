import os
import random
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from balance_config import ENEMY_SEED_STATS
from series_catalog import (
    INSECT_PART_DISPLAY_NAME_OVERRIDES,
    INSECT_R_PART_DEFINITIONS,
    PART_KEY_SERIES_ASSIGNMENTS,
    SERIES_BONUS_DEFINITIONS,
    SERIES_DEFINITIONS,
    SERIES_PART_DEFINITIONS,
)
from services.robot_titles import ensure_robot_title_system
from services.tower import ensure_tower_schema

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "game.db")
EVOLUTION_CORE_KEY = "evolution_core"
LAB_CASINO_PRIZE_SEEDS = (
    ("lab_title_hot_streak", "称号: ヒートストリーク", "実験室プロフィールに飾る想定のカジノ称号。", 500, "title", "lab_title_hot_streak"),
    ("lab_frame_checker", "観戦フレーム: チェッカー", "観戦気分を盛り上げるカジノ限定フレーム。", 1200, "frame", "lab_frame_checker"),
    ("lab_badge_jackpot", "プロフィールバッジ: JACKPOT", "実験室での大当たり記念バッジ。", 1800, "badge", "lab_badge_jackpot"),
    ("lab_skin_flash", "観戦演出スキン: フラッシュライン", "レース観戦の加速演出をイメージした景品。", 2600, "effect", "lab_skin_flash"),
)
LAB_CASINO_PRIZE_EXCHANGE_ENABLED = False
JST = timezone(timedelta(hours=9))
MINI_ROBOT_PERSONALITY_KEYS = ("timid", "curious", "loyal", "sleepy", "wild", "playful")
MINI_ROBOT_GROWTH_TYPES = ("stable", "burst", "adaptive", "guard", "chaos")
MINI_ROBOT_TIME_BANDS = ("morning", "day", "evening", "night")
RESEARCH_MODULE_SEEDS = (
    (
        "sniper_prototype",
        "狙撃モジュール 試作型",
        "prototype",
        "sniper",
        -3,
        0,
        0,
        0,
        8,
        3,
        "命中を高め、霧や回避型の敵に対応しやすくする試作モジュール。",
    ),
    (
        "heavy_prototype",
        "重装モジュール 試作型",
        "prototype",
        "heavy",
        10,
        0,
        6,
        -5,
        0,
        0,
        "耐久と防御を高める代わりに、動きが重くなる試作モジュール。",
    ),
    (
        "assault_prototype",
        "強襲モジュール 試作型",
        "prototype",
        "assault",
        0,
        8,
        -4,
        4,
        0,
        0,
        "攻撃と素早さを高め、短期決戦に寄せる試作モジュール。",
    ),
    (
        "stable_prototype",
        "安定モジュール 試作型",
        "prototype",
        "stable",
        0,
        0,
        5,
        0,
        5,
        -3,
        "防御と命中を整え、事故を減らす試作モジュール。",
    ),
    (
        "berserk_prototype",
        "暴走モジュール 試作型",
        "prototype",
        "berserk",
        0,
        12,
        0,
        0,
        -8,
        6,
        "攻撃と会心を大きく伸ばす代わりに命中が落ちる試作モジュール。",
    ),
    (
        "analysis_prototype",
        "解析モジュール 試作型",
        "prototype",
        "analysis",
        0,
        -3,
        3,
        0,
        6,
        0,
        "命中と防御を補助し、堅実な観測戦に寄せる試作モジュール。",
    ),
    (
        "sniper_complete",
        "狙撃モジュール 完成型",
        "complete",
        "sniper",
        -5,
        0,
        0,
        0,
        12,
        5,
        "命中と会心を高め、回避型や霧の敵へ強く出る完成型モジュール。",
    ),
    (
        "heavy_complete",
        "重装モジュール 完成型",
        "complete",
        "heavy",
        15,
        0,
        9,
        -7,
        0,
        0,
        "耐久と防御を大きく高める完成型モジュール。",
    ),
    (
        "assault_complete",
        "強襲モジュール 完成型",
        "complete",
        "assault",
        0,
        12,
        -6,
        6,
        0,
        0,
        "攻撃と素早さを大きく高める完成型モジュール。",
    ),
    (
        "stable_complete",
        "安定モジュール 完成型",
        "complete",
        "stable",
        0,
        0,
        8,
        0,
        8,
        -5,
        "防御と命中を高め、事故を抑える完成型モジュール。",
    ),
    (
        "berserk_complete",
        "暴走モジュール 完成型",
        "complete",
        "berserk",
        0,
        18,
        0,
        0,
        -12,
        9,
        "攻撃と会心を最大級に伸ばす完成型モジュール。",
    ),
    (
        "analysis_complete",
        "解析モジュール 完成型",
        "complete",
        "analysis",
        0,
        -5,
        5,
        0,
        10,
        0,
        "命中と防御を補助し、観測戦を安定させる完成型モジュール。",
    ),
    (
        "synthesized_module",
        "研究合成モジュール",
        "synth",
        "synthesized",
        0,
        0,
        0,
        0,
        0,
        0,
        "研究合成によって生成された個体差を持つモジュール。",
    ),
)
MINI_ROBOT_EVOLUTION_SEEDS = {
    "cerberus": ("cerberus_guard", "cerberus_wild", "cerberus_shadow"),
    "phoenix": ("phoenix_flare", "phoenix_ember", "phoenix_aura"),
    "hydra": ("hydra_many", "hydra_mist", "hydra_orbit"),
    "sphinx": ("sphinx_riddle", "sphinx_guard", "sphinx_oracle"),
}
MINI_ROBOT_SPECIES_SEEDS = (
    {
        "species_key": "cerberus",
        "name_ja": "ケルベロス",
        "description": "三つの頭を持つ、元気いっぱいの番犬型ミニロボ。",
        "type_key": "guard",
        "image_normal": "mini_robots/cerberus/normal.png",
        "image_blink": "mini_robots/cerberus/blink.png",
        "image_happy": "mini_robots/cerberus/happy.png",
        "image_sleep": "mini_robots/cerberus/sleep.png",
        "is_active": 1,
    },
    {
        "species_key": "phoenix",
        "name_ja": "フェニックス",
        "description": "小さな火花をまとった、静かで神秘的なミニロボ。",
        "type_key": "heat",
        "image_normal": "mini_robots/phoenix/normal.png",
        "image_blink": "mini_robots/phoenix/blink.png",
        "image_happy": "mini_robots/phoenix/happy.png",
        "image_sleep": "mini_robots/phoenix/sleep.png",
        "is_active": 1,
    },
    {
        "species_key": "hydra",
        "name_ja": "ヒュドラ",
        "description": "複数の頭がそれぞれ違う反応をする、不思議なミニロボ。",
        "type_key": "multi",
        "image_normal": "mini_robots/hydra/normal.png",
        "image_blink": "mini_robots/hydra/blink.png",
        "image_happy": "mini_robots/hydra/happy.png",
        "image_sleep": "mini_robots/hydra/sleep.png",
        "is_active": 1,
    },
    {
        "species_key": "sphinx",
        "name_ja": "スフィンクス",
        "description": "静かに盤面を読む、知略型の神話ミニロボ。",
        "type_key": "wisdom",
        "image_normal": "mini_robots/sphinx/normal.png",
        "image_blink": "mini_robots/sphinx/blink.png",
        "image_happy": "mini_robots/sphinx/happy.png",
        "image_sleep": "mini_robots/sphinx/sleep.png",
        "is_active": 1,
    },
)
RELEASE_FLAG_KEYS = ("lab", "lab_mini", "layer4", "layer5", "market", "series_system", "insect_r_parts", "research_boost")
SUPPORT_PACK_FOUNDER_PRODUCT_KEY = "support_pack_founder"
SUPPORT_PACK_LAB_PRODUCT_KEY = "support_pack_lab"
LEGACY_SUPPORT_PACK_PRODUCT_KEY = "support_pack_001"
SUPPORTER_FOUNDER_TROPHY_KEY = "supporter_founder"
SUPPORTER_LAB_TROPHY_KEY = "supporter_lab"
SUPPORT_PACK_FOUNDER_DECOR_KEY = "founder_badge_silver"
SUPPORT_PACK_LAB_DECOR_KEY = "lab_badge_gold"
LEGACY_SUPPORT_PACK_DECOR_KEY = "shien_trophy"


def _upsert_series_rows(cur):
    now = int(time.time())
    for row in SERIES_DEFINITIONS:
        cur.execute(
            """
            INSERT INTO series_master (
                series_key,
                display_name,
                category,
                frame_type,
                role_label,
                description,
                max_rarity,
                can_evolve,
                is_active,
                released_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(series_key) DO UPDATE SET
                display_name = excluded.display_name,
                category = excluded.category,
                frame_type = excluded.frame_type,
                role_label = excluded.role_label,
                description = excluded.description,
                max_rarity = excluded.max_rarity,
                can_evolve = excluded.can_evolve,
                is_active = CASE
                    WHEN series_master.is_active = 1 THEN 1
                    ELSE excluded.is_active
                END,
                released_at = CASE
                    WHEN series_master.released_at IS NOT NULL THEN series_master.released_at
                    ELSE excluded.released_at
                END
            """,
            (
                row["series_key"],
                row["display_name"],
                row["category"],
                row.get("frame_type") or "normal",
                row["role_label"],
                row["description"],
                str(row.get("max_rarity") or "N").upper(),
                int(row.get("can_evolve", 0)),
                int(row.get("default_active", 0)),
                now if int(row.get("default_active", 0)) else None,
            ),
        )
    for bonus in SERIES_BONUS_DEFINITIONS:
        cur.execute(
            """
            INSERT INTO series_set_bonus (series_key, pieces_required, stat_key, value, value_type)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(series_key, pieces_required, stat_key) DO UPDATE SET
                value = excluded.value,
                value_type = excluded.value_type
            """,
            (
                bonus["series_key"],
                int(bonus["pieces_required"]),
                bonus["stat_key"],
                float(bonus["value"]),
                str(bonus.get("value_type") or "percent"),
            ),
            )


def _upsert_mini_robot_species(cur):
    for species in MINI_ROBOT_SPECIES_SEEDS:
        cur.execute(
            """
            INSERT INTO mini_robot_species
            (species_key, name_ja, description, type_key, image_normal, image_blink, image_happy, image_sleep, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(species_key) DO UPDATE SET
                name_ja = excluded.name_ja,
                description = excluded.description,
                type_key = excluded.type_key,
                image_normal = excluded.image_normal,
                image_blink = excluded.image_blink,
                image_happy = excluded.image_happy,
                image_sleep = excluded.image_sleep,
                is_active = excluded.is_active
            """,
            (
                species["species_key"],
                species["name_ja"],
                species["description"],
                species["type_key"],
                species["image_normal"],
                species["image_blink"],
                species["image_happy"],
                species["image_sleep"],
                int(species["is_active"]),
            ),
        )


def _mini_robot_pick_initial_traits(species_key, *, seed=None):
    rng = random.Random(seed) if seed is not None else random
    species = str(species_key or "cerberus")
    evolution_candidates = MINI_ROBOT_EVOLUTION_SEEDS.get(species) or (f"{species}_default",)
    return {
        "personality_key": rng.choice(MINI_ROBOT_PERSONALITY_KEYS),
        "growth_type": rng.choice(MINI_ROBOT_GROWTH_TYPES),
        "behavior_seed": rng.randint(1, 999999),
        "evolution_seed": rng.choice(evolution_candidates),
        "favorite_time_band": rng.choice(MINI_ROBOT_TIME_BANDS),
        "instinct": rng.randint(1, 3),
    }


def _mini_robot_day_key_from_ts(ts):
    return datetime.fromtimestamp(int(ts), JST).strftime("%Y-%m-%d")


def _backfill_mini_robot_internal_fields(cur):
    rows = cur.execute("SELECT * FROM user_mini_robots").fetchall()
    col_names = [item[0] for item in cur.description]
    for raw in rows:
        row = dict(zip(col_names, raw))
        row_id = int(row["id"])
        species_key = str(row.get("species_key") or "cerberus")
        traits = _mini_robot_pick_initial_traits(species_key, seed=f"mini-backfill:{row_id}:{species_key}")
        last_cared_at = int(row.get("last_cared_at") or 0)
        last_care_date = _mini_robot_day_key_from_ts(last_cared_at) if last_cared_at > 0 else None
        care_count = int(
            cur.execute(
                "SELECT COUNT(*) FROM mini_robot_logs WHERE mini_robot_id = ? AND event_type = 'care'",
                (row_id,),
            ).fetchone()[0]
            or 0
        )
        updates = {}
        for key in ("personality_key", "growth_type", "evolution_seed", "favorite_time_band"):
            if not str(row.get(key) or "").strip():
                updates[key] = traits[key]
        if int(row.get("behavior_seed") or 0) <= 0:
            updates["behavior_seed"] = traits["behavior_seed"]
        if int(row.get("instinct") or 0) <= 0:
            updates["instinct"] = traits["instinct"]
        if int(row.get("care_count") or 0) <= 0 and care_count > 0:
            updates["care_count"] = care_count
        if not str(row.get("last_care_date") or "").strip() and last_care_date:
            updates["last_care_date"] = last_care_date
        if not str(row.get("last_state_reason") or "").strip():
            updates["last_state_reason"] = "backfilled"
        if updates:
            assignments = ", ".join([f"{key} = ?" for key in updates])
            cur.execute(f"UPDATE user_mini_robots SET {assignments} WHERE id = ?", [*updates.values(), row_id])


def _apply_series_part_assignments(cur):
    now = int(time.time())
    for part in SERIES_PART_DEFINITIONS:
        cur.execute(
            """
            INSERT INTO robot_parts (
                part_type,
                key,
                image_path,
                rarity,
                element,
                series,
                frame_type,
                series_key,
                series_label,
                display_name_ja,
                offset_x,
                offset_y,
                is_active,
                is_unlocked,
                is_admin_only,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 1, 1, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                part_type = excluded.part_type,
                image_path = excluded.image_path,
                rarity = excluded.rarity,
                element = excluded.element,
                series = excluded.series,
                frame_type = excluded.frame_type,
                series_key = excluded.series_key,
                series_label = excluded.series_label,
                display_name_ja = excluded.display_name_ja,
                is_active = 1,
                is_admin_only = excluded.is_admin_only
            """,
            (
                part["part_type"],
                part["key"],
                part["image_path"],
                part["rarity"],
                part["element"],
                part["series"],
                part.get("frame_type") or "normal",
                part.get("series_key") or part.get("series"),
                part.get("series_label"),
                part["display_name_ja"],
                int(part.get("is_admin_only", 0)),
                now,
            ),
        )
    for part in INSECT_R_PART_DEFINITIONS:
        cur.execute(
            """
            INSERT INTO robot_parts (
                part_type,
                key,
                image_path,
                rarity,
                element,
                series,
                frame_type,
                series_key,
                series_label,
                display_name_ja,
                offset_x,
                offset_y,
                is_active,
                is_unlocked,
                is_admin_only,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 1, 1, 0, ?)
            ON CONFLICT(key) DO UPDATE SET
                part_type = excluded.part_type,
                image_path = excluded.image_path,
                rarity = excluded.rarity,
                element = excluded.element,
                series = excluded.series,
                frame_type = excluded.frame_type,
                series_key = excluded.series_key,
                series_label = excluded.series_label,
                display_name_ja = excluded.display_name_ja,
                is_active = 1,
                is_unlocked = 1,
                is_admin_only = 0
            """,
            (
                part["part_type"],
                part["key"],
                part["image_path"],
                part["rarity"],
                part["element"],
                part["series"],
                part.get("frame_type") or "insect",
                part.get("series_key") or part.get("series"),
                part.get("series_label"),
                part["display_name_ja"],
                now,
            ),
        )
        cur.execute(
            """
            UPDATE robot_parts
            SET offset_x = COALESCE((SELECT src.offset_x FROM robot_parts src WHERE src.key = ? LIMIT 1), offset_x),
                offset_y = COALESCE((SELECT src.offset_y FROM robot_parts src WHERE src.key = ? LIMIT 1), offset_y)
            WHERE key = ?
            """,
            (part["source_key"], part["source_key"], part["key"]),
        )
    for part_key, series_key in PART_KEY_SERIES_ASSIGNMENTS.items():
        cur.execute(
            """
            UPDATE robot_parts
            SET
                series = ?,
                frame_type = COALESCE((
                    SELECT sm.frame_type
                    FROM series_master sm
                    WHERE sm.series_key = ?
                    LIMIT 1
                ), frame_type, 'normal'),
                series_key = ?,
                series_label = (
                    SELECT display_name
                    FROM series_master
                    WHERE series_key = ?
                    LIMIT 1
                )
            WHERE key = ?
            """,
            (series_key, series_key, series_key, series_key, part_key),
        )
    cur.execute(
        """
        UPDATE robot_parts
        SET frame_type = 'normal'
        WHERE frame_type IS NULL OR TRIM(frame_type) = ''
        """
    )
    cur.execute("UPDATE robot_parts SET frame_type = 'dinosaur' WHERE COALESCE(series_key, series, '') LIKE 'dino_%'")
    cur.execute(
        """
        UPDATE robot_parts
        SET
            series_key = COALESCE(NULLIF(TRIM(series_key), ''), NULLIF(TRIM(series), '')),
            series_label = COALESCE(
                NULLIF(TRIM(series_label), ''),
                (
                    SELECT sm.display_name
                    FROM series_master sm
                    WHERE sm.series_key = COALESCE(NULLIF(TRIM(robot_parts.series_key), ''), NULLIF(TRIM(robot_parts.series), ''))
                    LIMIT 1
                )
            )
        WHERE frame_type = 'insect'
        """
    )
    cur.execute(
        """
        UPDATE part_instances
        SET series = (
            SELECT rp.series
            FROM robot_parts rp
            WHERE rp.id = part_instances.part_id
        )
        WHERE COALESCE(series, '') IN ('', 'S1')
           OR EXISTS (
                SELECT 1
                FROM robot_parts rp
                WHERE rp.id = part_instances.part_id
                  AND COALESCE(rp.series, '') != COALESCE(part_instances.series, '')
           )
        """
    )


def _sync_insect_part_display_names(cur):
    for part_key, display_name in INSECT_PART_DISPLAY_NAME_OVERRIDES.items():
        cur.execute(
            "UPDATE robot_parts SET display_name_ja = ? WHERE key = ?",
            (display_name, part_key),
        )


def _ensure_default_normal_robot_parts(cur):
    normal_count = cur.execute(
        """
        SELECT COUNT(*)
        FROM robot_parts
        WHERE COALESCE(frame_type, 'normal') = 'normal'
        """
    ).fetchone()[0]
    if normal_count > 0:
        return
    now = int(time.time())
    items = []
    for i in range(1, 11):
        items.append(("HEAD", f"head_{i}", f"parts/head/{i}.png", "N", "NORMAL", "S1", "normal", 0, 0, now))
        items.append(("RIGHT_ARM", f"r_arm_{i}", f"parts/right_arm/{i}.png", "N", "NORMAL", "S1", "normal", 0, 0, now))
        items.append(("LEFT_ARM", f"l_arm_{i}", f"parts/left_arm/{i}.png", "N", "NORMAL", "S1", "normal", 0, 0, now))
        items.append(("LEGS", f"legs_{i}", f"parts/legs/{i}.png", "N", "NORMAL", "S1", "normal", 0, 0, now))
    cur.executemany(
        """
        INSERT INTO robot_parts (
            part_type, key, image_path, rarity, element, series, frame_type, offset_x, offset_y, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            part_type = excluded.part_type,
            image_path = excluded.image_path,
            rarity = excluded.rarity,
            element = excluded.element,
            series = excluded.series,
            frame_type = excluded.frame_type,
            offset_x = excluded.offset_x,
            offset_y = excluded.offset_y,
            is_active = 1
        """,
        items,
    )


robots_seed = [
    ("Head:A", "RightArm:A", "LeftArm:A", "Legs:A", "ヘラクス", "SR", "バランス", "蒼い炎をまとった強化型。", 4, 3, 20),
    ("Head:B", "RightArm:B", "LeftArm:B", "Legs:B", "カシオペア", "R", "機動", "素早さに特化した軽量機。", 3, 2, 10),
    ("Head:C", "RightArm:C", "LeftArm:C", "Legs:C", "ノクス", "N", "標準", "静かな夜を走る。", 2, 2, 0),
    ("Head:D", "RightArm:D", "LeftArm:D", "Legs:D", "ヴァルカン", "R", "火力", "高熱コアを内蔵。", 4, 2, 10),
    ("Head:E", "RightArm:E", "LeftArm:E", "Legs:E", "ユーノ", "N", "標準", "整備性が高い量産機。", 2, 3, 0),
    ("Head:F", "RightArm:F", "LeftArm:F", "Legs:F", "オルテガ", "SR", "装甲", "厚い装甲で守る。", 3, 4, 20),
    ("Head:G", "RightArm:G", "LeftArm:G", "Legs:G", "フェンリル", "SSR", "獣型", "伝説の獣型機体。", 6, 4, 40),
    ("Head:H", "RightArm:H", "LeftArm:H", "Legs:H", "ミラージュ", "R", "幻影", "姿が揺らぐ特殊機。", 3, 2, 10),
    ("Head:I", "RightArm:I", "LeftArm:I", "Legs:I", "グリム", "N", "標準", "堅実な作業機。", 2, 2, 0),
    ("Head:J", "RightArm:J", "LeftArm:J", "Legs:J", "ラプター", "R", "高速", "空気を裂く速度。", 4, 2, 10),
    ("Head:K", "RightArm:K", "LeftArm:K", "Legs:K", "バルムンク", "SR", "斬撃", "大剣を振るう。", 5, 2, 20),
    ("Head:L", "RightArm:L", "LeftArm:L", "Legs:L", "スピカ", "N", "標準", "星の光を映す。", 2, 2, 0),
    ("Head:M", "RightArm:M", "LeftArm:M", "Legs:M", "アルマ", "N", "補助", "支援ユニット搭載。", 2, 3, 0),
    ("Head:N", "RightArm:N", "LeftArm:N", "Legs:N", "タウルス", "R", "重量", "重装で押し切る。", 3, 4, 10),
    ("Head:O", "RightArm:O", "LeftArm:O", "Legs:O", "セレス", "N", "標準", "夜明けの守護者。", 2, 2, 0),
    ("Head:P", "RightArm:P", "LeftArm:P", "Legs:P", "ガイア", "R", "耐久", "大地に根を張る。", 3, 4, 10),
    ("Head:Q", "RightArm:Q", "LeftArm:Q", "Legs:Q", "ネビュラ", "SR", "浮遊", "宙を漂う。", 4, 3, 20),
    ("Head:R", "RightArm:R", "LeftArm:R", "Legs:R", "ストーム", "R", "嵐", "雷撃ユニット搭載。", 4, 2, 10),
    ("Head:S", "RightArm:S", "LeftArm:S", "Legs:S", "ルミナ", "N", "光学", "光を操る。", 2, 2, 0),
    ("Head:T", "RightArm:T", "LeftArm:T", "Legs:T", "オーディン", "SSR", "神話", "神話級の機体。", 6, 5, 40),
    ("Head:U", "RightArm:U", "LeftArm:U", "Legs:U", "ノヴァ", "UR", "神威", "空間歪曲コア搭載。", 8, 6, 80),
]

part_element_titles_ja = {
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
part_type_titles_ja = {
    "head": "頭冠",
    "right_arm": "右腕",
    "left_arm": "左腕",
    "legs": "脚部",
}
part_rarity_suffix_ja = {
    "N": "",
    "R": "改",
    "SR": "真",
    "SSR": "極",
    "UR": "神",
}


def _normalize_part_type_key(part_type):
    key = str(part_type or "").strip().lower()
    if key in part_type_titles_ja:
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
            if tok_up in part_rarity_suffix_ja:
                rarity_norm = tok_up
                break
    if not element_norm:
        for tok in tokens:
            if tok in part_element_titles_ja:
                element_norm = tok
                break
    if not part_type_norm or element_norm not in part_element_titles_ja:
        return key
    suffix = part_rarity_suffix_ja.get(rarity_norm, "")
    return f"{part_element_titles_ja[element_norm]}{part_type_titles_ja[part_type_norm]}{suffix}"


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT,
            password_hash TEXT NOT NULL,
            invite_code TEXT UNIQUE,
            coins INTEGER NOT NULL DEFAULT 0,
            is_admin INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            click_power INTEGER NOT NULL DEFAULT 1,
            total_clicks INTEGER NOT NULL DEFAULT 0,
            robot_slot_limit INTEGER NOT NULL DEFAULT 3,
            part_inventory_limit INTEGER NOT NULL DEFAULT 60,
            avatar_path TEXT,
            active_robot_id INTEGER,
            active_research_module_instance_id INTEGER,
            battle_log_mode TEXT NOT NULL DEFAULT 'collapsed',
            boss_meter_explore_l1 INTEGER NOT NULL DEFAULT 0,
            boss_meter_win_l1 INTEGER NOT NULL DEFAULT 0,
            layer2_unlocked INTEGER NOT NULL DEFAULT 0,
            max_unlocked_layer INTEGER NOT NULL DEFAULT 1,
            home_axis_hint_seen INTEGER NOT NULL DEFAULT 0,
            stable_no_damage_wins INTEGER NOT NULL DEFAULT 0,
            burst_crit_finisher_kills INTEGER NOT NULL DEFAULT 0,
            desperate_low_hp_wins INTEGER NOT NULL DEFAULT 0,
            faction TEXT,
            faction_changed_at TEXT,
            is_banned INTEGER NOT NULL DEFAULT 0,
            is_admin_protected INTEGER NOT NULL DEFAULT 0,
            banned_at TEXT,
            banned_reason TEXT,
            banned_by_user_id INTEGER,
            has_seen_intro_modal INTEGER NOT NULL DEFAULT 0,
            intro_guide_closed_at TEXT,
            last_explore_area_key TEXT,
            explore_boost_until INTEGER NOT NULL DEFAULT 0,
            lab_small_boost_count INTEGER NOT NULL DEFAULT 0,
            lab_small_boost_until INTEGER NOT NULL DEFAULT 0,
            research_boost_charges INTEGER NOT NULL DEFAULT 0,
            research_boost_auto_use_enabled INTEGER NOT NULL DEFAULT 1,
            research_module_pity INTEGER NOT NULL DEFAULT 0,
            evolution_core_progress INTEGER NOT NULL DEFAULT 0,
            home_beginner_mission_hidden INTEGER NOT NULL DEFAULT 0,
            home_next_action_collapsed INTEGER NOT NULL DEFAULT 0,
            home_daily_research_collapsed INTEGER NOT NULL DEFAULT 0,
            tutorial_layer1_state TEXT NOT NULL DEFAULT 'new',
            tutorial_layer1_normal_win_count INTEGER NOT NULL DEFAULT 0,
            tutorial_layer1_boss_seen_at INTEGER,
            tutorial_layer1_boss_fail_count INTEGER NOT NULL DEFAULT 0,
            tutorial_layer1_boss_help_ready INTEGER NOT NULL DEFAULT 0,
            tutorial_layer1_forced_boss_ready INTEGER NOT NULL DEFAULT 0,
            tutorial_layer1_fuse_after_boss_fail_count INTEGER NOT NULL DEFAULT 0,
            tutorial_layer1_updated_at INTEGER NOT NULL DEFAULT 0,
            layer1_first_clear_reward_claimed INTEGER NOT NULL DEFAULT 0,
            layer1_first_clear_home_seen INTEGER NOT NULL DEFAULT 0,
            lab_coin INTEGER NOT NULL DEFAULT 0,
            lab_coin_last_daily_at TEXT,
            lab_coin_converted_at INTEGER NOT NULL DEFAULT 0,
            lab_level INTEGER NOT NULL DEFAULT 1,
            lab_exp INTEGER NOT NULL DEFAULT 0,
            lab_total_exp INTEGER NOT NULL DEFAULT 0,
            lab_rank_label TEXT NOT NULL DEFAULT '見習い研究員',
            lab_level_updated_at TEXT,
            market_refresh_count_today INTEGER NOT NULL DEFAULT 0,
            market_free_refresh_used_at TEXT,
            market_refresh_day_key TEXT,
            last_daily_research_modal_day TEXT,
            last_seen_at INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        )
        """
    )
    cur.execute(
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
            UNIQUE(referred_user_id),
            FOREIGN KEY (referrer_user_id) REFERENCES users(id),
            FOREIGN KEY (referred_user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS release_flags (
            key TEXT PRIMARY KEY,
            is_public INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS maintenance_state (
            id INTEGER PRIMARY KEY,
            mode TEXT NOT NULL DEFAULT 'off',
            updated_at INTEGER NOT NULL DEFAULT 0,
            updated_by_user_id INTEGER,
            FOREIGN KEY (updated_by_user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_presence (
            user_id INTEGER PRIMARY KEY,
            last_active_at TEXT NOT NULL,
            last_surface TEXT,
            last_action_key TEXT,
            last_path TEXT,
            last_room_key TEXT,
            last_robot_instance_id INTEGER,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    cur.execute(
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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_bases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            image_path TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_type TEXT NOT NULL,
            key TEXT UNIQUE NOT NULL,
            image_path TEXT NOT NULL,
            rarity TEXT,
            element TEXT,
            series TEXT,
            frame_type TEXT DEFAULT 'normal',
            series_key TEXT,
            series_label TEXT,
            display_name_ja TEXT,
            offset_x INTEGER NOT NULL DEFAULT 0,
            offset_y INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            is_unlocked INTEGER NOT NULL DEFAULT 1,
            is_admin_only INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS series_master (
            series_key TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            category TEXT NOT NULL,
            frame_type TEXT DEFAULT 'normal',
            role_label TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            max_rarity TEXT DEFAULT 'N',
            can_evolve INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 0,
            released_at INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS series_set_bonus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_key TEXT NOT NULL,
            pieces_required INTEGER NOT NULL,
            stat_key TEXT NOT NULL,
            value REAL NOT NULL,
            value_type TEXT NOT NULL DEFAULT 'percent',
            UNIQUE(series_key, pieces_required, stat_key),
            FOREIGN KEY (series_key) REFERENCES series_master(series_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS enemy_series_drops (
            enemy_id INTEGER NOT NULL,
            series_key TEXT NOT NULL,
            drop_weight INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (enemy_id, series_key),
            FOREIGN KEY (series_key) REFERENCES series_master(series_key)
        )
        """
    )
    cur.execute(
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
    cur.execute(
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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS research_modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_key TEXT UNIQUE NOT NULL,
            name_ja TEXT NOT NULL,
            rarity TEXT NOT NULL,
            family TEXT NOT NULL,
            hp_bonus INTEGER NOT NULL DEFAULT 0,
            atk_bonus INTEGER NOT NULL DEFAULT 0,
            def_bonus INTEGER NOT NULL DEFAULT 0,
            spd_bonus INTEGER NOT NULL DEFAULT 0,
            acc_bonus INTEGER NOT NULL DEFAULT 0,
            cri_bonus INTEGER NOT NULL DEFAULT 0,
            description TEXT,
            tier INTEGER NOT NULL DEFAULT 1,
            trade_policy TEXT NOT NULL DEFAULT 'tradable',
            source_type TEXT NOT NULL DEFAULT 'normal_drop',
            is_limited INTEGER NOT NULL DEFAULT 0,
            npc_sell_price INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_research_modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            module_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'inventory',
            is_locked INTEGER NOT NULL DEFAULT 0,
            sold_at TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (module_key) REFERENCES research_modules(module_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_research_module_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            module_key TEXT NOT NULL,
            first_obtained_at INTEGER NOT NULL,
            first_instance_id INTEGER,
            UNIQUE(user_id, module_key),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (module_key) REFERENCES research_modules(module_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_instances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            is_public INTEGER NOT NULL DEFAULT 1,
            composed_image_path TEXT,
            personality TEXT,
            icon_32_path TEXT,
            combat_mode TEXT NOT NULL DEFAULT 'normal',
            frame_type TEXT DEFAULT 'normal',
            is_mixed_frame INTEGER NOT NULL DEFAULT 0,
            build_frame_mode TEXT NOT NULL DEFAULT 'normal',
            style_key TEXT NOT NULL DEFAULT 'stable',
            style_stats_json TEXT NOT NULL DEFAULT '{}',
            style_scores_json TEXT,
            style_rank_json TEXT,
            style_current_key TEXT,
            style_next_key TEXT,
            style_updated_at TEXT,
            primary_title_key TEXT,
            style_title_key TEXT,
            honor_title_key TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            decomposed_at INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_instance_decors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            robot_instance_id INTEGER NOT NULL,
            decor_asset_id INTEGER NOT NULL,
            slot_index INTEGER NOT NULL,
            offset_x INTEGER NOT NULL DEFAULT 0,
            offset_y INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL DEFAULT 0,
            UNIQUE(robot_instance_id, slot_index),
            FOREIGN KEY (robot_instance_id) REFERENCES robot_instances(id),
            FOREIGN KEY (decor_asset_id) REFERENCES robot_decor_assets(id)
        )
        """
    )
    cur.execute(
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
    cur.execute(
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
            r_assist_points INTEGER NOT NULL DEFAULT 0,
            locked INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'inventory',
            created_at INTEGER NOT NULL,
            FOREIGN KEY (part_id) REFERENCES robot_parts(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS market_daily_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            day_key TEXT NOT NULL,
            slot_key TEXT NOT NULL,
            part_key TEXT NOT NULL,
            part_type TEXT NOT NULL,
            rarity TEXT NOT NULL,
            plus INTEGER NOT NULL DEFAULT 0,
            price INTEGER NOT NULL,
            seed INTEGER NOT NULL DEFAULT 0,
            is_sold INTEGER NOT NULL DEFAULT 0,
            sold_to_user_id INTEGER,
            sold_at INTEGER,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            UNIQUE(user_id, day_key, slot_key),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS market_purchase_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            listing_id INTEGER,
            part_instance_id INTEGER,
            part_key TEXT NOT NULL,
            price INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS market_sell_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            part_instance_id INTEGER,
            part_key TEXT NOT NULL,
            rarity TEXT NOT NULL,
            plus INTEGER NOT NULL DEFAULT 0,
            price INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS market_refresh_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            day_key TEXT NOT NULL,
            refresh_index INTEGER NOT NULL,
            cost INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
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
    cur.execute(
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
    cur.execute(
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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_core_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            core_asset_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT,
            UNIQUE(user_id, core_asset_id)
        )
        """
    )
    cur.execute(
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
    cur.execute(
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
    cur.execute(
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
    cur.execute(
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
    cur.execute(
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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS base_bodies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sprite_path TEXT NOT NULL
        )
        """
    )
    cur.execute(
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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_robots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            head TEXT NOT NULL,
            right_arm TEXT NOT NULL,
            left_arm TEXT NOT NULL,
            legs TEXT NOT NULL,
            obtained_at INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS battle_state (
            user_id INTEGER PRIMARY KEY,
            enemy_name TEXT NOT NULL,
            enemy_hp INTEGER NOT NULL,
            last_action_at INTEGER NOT NULL,
            active INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS login_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            created_at TEXT
        )
        """
    )

    cur.execute(
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
    cur.execute(
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
    ensure_tower_schema(conn)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS battle_result_cache (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            area_key TEXT NOT NULL,
            area_label TEXT,
            summary_json TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_battle_result_cache_user_created ON battle_result_cache(user_id, created_at)")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_research_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            day_key TEXT NOT NULL,
            task_key TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            target_event TEXT NOT NULL,
            target_count INTEGER NOT NULL DEFAULT 1,
            current_count INTEGER NOT NULL DEFAULT 0,
            reward_coins INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            completed_at TEXT,
            claimed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, day_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_research_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            source_day_key TEXT NOT NULL,
            claim_day_key TEXT NOT NULL,
            reward_coins INTEGER NOT NULL DEFAULT 0,
            core_progress_delta INTEGER NOT NULL DEFAULT 0,
            reason TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            claimed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, source_day_key)
        )
        """
    )
    cur.execute(
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
    cur.execute(
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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_typing_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            score INTEGER NOT NULL DEFAULT 0,
            max_combo INTEGER NOT NULL DEFAULT 0,
            typed_count INTEGER NOT NULL DEFAULT 0,
            miss_count INTEGER NOT NULL DEFAULT 0,
            defeated_count INTEGER NOT NULL DEFAULT 0,
            boss_reached INTEGER NOT NULL DEFAULT 0,
            boss_defeated INTEGER NOT NULL DEFAULT 0,
            remaining_boss_hp INTEGER,
            duration_ms INTEGER NOT NULL DEFAULT 30000,
            client_payload_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_lab_exp_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action_key TEXT NOT NULL,
            exp_delta INTEGER NOT NULL,
            lab_level_before INTEGER NOT NULL,
            lab_level_after INTEGER NOT NULL,
            lab_exp_before INTEGER NOT NULL,
            lab_exp_after INTEGER NOT NULL,
            lab_total_exp_after INTEGER NOT NULL,
            source_entity_type TEXT,
            source_entity_id INTEGER,
            payload_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS mini_robot_species (
            species_key TEXT PRIMARY KEY,
            name_ja TEXT NOT NULL,
            description TEXT,
            type_key TEXT,
            image_normal TEXT NOT NULL,
            image_blink TEXT NOT NULL,
            image_happy TEXT NOT NULL,
            image_sleep TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_mini_robots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            species_key TEXT NOT NULL,
            nickname TEXT NOT NULL,
            stage TEXT NOT NULL DEFAULT 'child',
            affection INTEGER NOT NULL DEFAULT 0,
            stability INTEGER NOT NULL DEFAULT 50,
            energy INTEGER NOT NULL DEFAULT 60,
            mood INTEGER NOT NULL DEFAULT 50,
            growth_exp INTEGER NOT NULL DEFAULT 0,
            current_state TEXT NOT NULL DEFAULT 'normal',
            last_cared_at INTEGER,
            personality_key TEXT DEFAULT NULL,
            growth_type TEXT DEFAULT NULL,
            behavior_seed INTEGER NOT NULL DEFAULT 0,
            evolution_seed TEXT DEFAULT NULL,
            trust INTEGER NOT NULL DEFAULT 0,
            curiosity INTEGER NOT NULL DEFAULT 0,
            instinct INTEGER NOT NULL DEFAULT 0,
            stress INTEGER NOT NULL DEFAULT 0,
            care_count INTEGER NOT NULL DEFAULT 0,
            consecutive_care_days INTEGER NOT NULL DEFAULT 0,
            last_care_date TEXT DEFAULT NULL,
            favorite_time_band TEXT DEFAULT NULL,
            last_state_reason TEXT DEFAULT NULL,
            created_at INTEGER NOT NULL,
            UNIQUE(user_id, species_key),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(species_key) REFERENCES mini_robot_species(species_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS mini_robot_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            mini_robot_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            message TEXT NOT NULL,
            payload_json TEXT,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(mini_robot_id) REFERENCES user_mini_robots(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_mini_robot_profiles (
            user_id INTEGER PRIMARY KEY,
            active_mini_robot_id INTEGER,
            updated_at INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(active_mini_robot_id) REFERENCES user_mini_robots(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS mini_tactics_teams (
            user_id INTEGER PRIMARY KEY,
            slot_1_mini_robot_id INTEGER,
            slot_1_x INTEGER NOT NULL DEFAULT 0,
            slot_1_y INTEGER NOT NULL DEFAULT 1,
            slot_1_ai_type TEXT,
            slot_1_weapon_type TEXT,
            slot_2_mini_robot_id INTEGER,
            slot_2_x INTEGER NOT NULL DEFAULT 0,
            slot_2_y INTEGER NOT NULL DEFAULT 2,
            slot_2_ai_type TEXT,
            slot_2_weapon_type TEXT,
            slot_3_mini_robot_id INTEGER,
            slot_3_x INTEGER NOT NULL DEFAULT 0,
            slot_3_y INTEGER NOT NULL DEFAULT 3,
            slot_3_ai_type TEXT,
            slot_3_weapon_type TEXT,
            updated_at INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(slot_1_mini_robot_id) REFERENCES user_mini_robots(id),
            FOREIGN KEY(slot_2_mini_robot_id) REFERENCES user_mini_robots(id),
            FOREIGN KEY(slot_3_mini_robot_id) REFERENCES user_mini_robots(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_enemy_dex (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            enemy_key TEXT NOT NULL,
            first_seen_at INTEGER NOT NULL,
            first_defeated_at INTEGER,
            seen_count INTEGER NOT NULL DEFAULT 0,
            defeat_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, enemy_key)
        )
        """
    )
    cur.execute(
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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS world_faction_weekly_result (
            week_key TEXT PRIMARY KEY,
            winner_faction TEXT NOT NULL,
            scores_json TEXT NOT NULL,
            computed_at INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS world_faction_user_weekly_contributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            faction TEXT NOT NULL,
            points INTEGER NOT NULL DEFAULT 0,
            explore_win_count INTEGER NOT NULL DEFAULT 0,
            boss_defeat_count INTEGER NOT NULL DEFAULT 0,
            build_count INTEGER NOT NULL DEFAULT 0,
            strengthen_count INTEGER NOT NULL DEFAULT 0,
            evolve_count INTEGER NOT NULL DEFAULT 0,
            champ_defeat_count INTEGER NOT NULL DEFAULT 0,
            upset_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(week_key, user_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS world_faction_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            faction TEXT NOT NULL,
            user_id INTEGER,
            event_type TEXT NOT NULL,
            message TEXT NOT NULL,
            points_delta INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS world_faction_weekly_mvp (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            faction TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            points INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(week_key, faction, category)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_weekly_awards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            faction_key TEXT NOT NULL,
            award_key TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            score INTEGER NOT NULL DEFAULT 0,
            rank INTEGER NOT NULL DEFAULT 1,
            reward_status TEXT NOT NULL DEFAULT 'none',
            created_at TEXT NOT NULL,
            updated_at TEXT,
            UNIQUE(week_key, faction_key, award_key, user_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_faction_badges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            faction_key TEXT NOT NULL,
            badge_key TEXT NOT NULL,
            badge_label TEXT NOT NULL,
            badge_kind TEXT NOT NULL,
            week_key TEXT,
            source_type TEXT,
            source_id INTEGER,
            granted_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, badge_key, week_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_faction_titles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            faction_key TEXT NOT NULL,
            title_key TEXT NOT NULL,
            title_label TEXT NOT NULL,
            title_description TEXT,
            week_key TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL,
            source_id INTEGER,
            is_equipped INTEGER NOT NULL DEFAULT 0,
            granted_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, title_key, week_key, source_type)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_title_grant_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL DEFAULT '',
            title_key TEXT NOT NULL,
            faction_key TEXT,
            granted_count INTEGER NOT NULL DEFAULT 0,
            source_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(week_key, title_key, faction_key, source_type)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_weekly_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL UNIQUE,
            event_key TEXT NOT NULL,
            event_name TEXT NOT NULL,
            description TEXT,
            effect_summary TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            starts_at TEXT,
            ends_at TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            finalized_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_weekly_event_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            event_key TEXT NOT NULL,
            action TEXT NOT NULL,
            admin_user_id INTEGER,
            payload_json TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_shop_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_key TEXT NOT NULL UNIQUE,
            item_name TEXT NOT NULL,
            description TEXT,
            item_type TEXT NOT NULL,
            faction_key TEXT,
            price_coins INTEGER NOT NULL DEFAULT 0,
            required_facility_level INTEGER NOT NULL DEFAULT 0,
            required_title_key TEXT,
            required_event_key TEXT,
            required_territory_count INTEGER NOT NULL DEFAULT 0,
            required_guardian_author INTEGER NOT NULL DEFAULT 0,
            grant_title_key TEXT,
            badge_label TEXT,
            image_path TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            is_limited INTEGER NOT NULL DEFAULT 0,
            starts_at TEXT,
            ends_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_faction_shop_purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            faction_key TEXT,
            price_paid_coins INTEGER NOT NULL DEFAULT 0,
            purchased_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, item_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_equipped_faction_shop_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            slot_key TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            equipped_at TEXT NOT NULL,
            updated_at TEXT,
            UNIQUE(user_id, slot_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_weekly_claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            week_key TEXT NOT NULL,
            faction_key TEXT NOT NULL,
            activity_score INTEGER NOT NULL DEFAULT 0,
            coin_reward INTEGER NOT NULL DEFAULT 0,
            badge_key TEXT,
            claimed_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, week_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_weekly_missions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            mission_key TEXT NOT NULL,
            mission_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            target_value INTEGER NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            is_finalized INTEGER NOT NULL DEFAULT 0,
            finalized_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            UNIQUE(week_key, mission_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_weekly_mission_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            mission_id INTEGER NOT NULL,
            faction_key TEXT NOT NULL,
            current_value INTEGER NOT NULL DEFAULT 0,
            target_value INTEGER NOT NULL DEFAULT 0,
            progress_percent INTEGER NOT NULL DEFAULT 0,
            is_completed INTEGER NOT NULL DEFAULT 0,
            completed_at TEXT,
            is_finalized INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            UNIQUE(week_key, mission_id, faction_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_weekly_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            faction_key TEXT NOT NULL,
            member_count INTEGER NOT NULL DEFAULT 0,
            explore_count INTEGER NOT NULL DEFAULT 0,
            boss_defeat_count INTEGER NOT NULL DEFAULT 0,
            evolve_count INTEGER NOT NULL DEFAULT 0,
            activity_score INTEGER NOT NULL DEFAULT 0,
            rank INTEGER,
            report_label TEXT,
            is_minority INTEGER NOT NULL DEFAULT 0,
            is_finalized INTEGER NOT NULL DEFAULT 0,
            finalized_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            UNIQUE(week_key, faction_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_guardians (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            faction_key TEXT NOT NULL,
            guardian_name TEXT NOT NULL,
            guardian_title TEXT,
            source_type TEXT NOT NULL DEFAULT 'submission',
            submission_id INTEGER,
            author_user_id INTEGER,
            author_faction_key TEXT,
            image_path TEXT,
            faith_profile_json TEXT,
            max_hp INTEGER NOT NULL DEFAULT 1000,
            current_hp INTEGER NOT NULL DEFAULT 1000,
            is_active INTEGER NOT NULL DEFAULT 1,
            is_finalized INTEGER NOT NULL DEFAULT 0,
            fallback_cross_faction INTEGER NOT NULL DEFAULT 0,
            selected_at TEXT,
            finalized_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(week_key, faction_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_guardian_attacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            attacker_faction_key TEXT NOT NULL,
            target_faction_key TEXT NOT NULL,
            guardian_id INTEGER NOT NULL,
            attacker_user_id INTEGER NOT NULL,
            source_event_type TEXT NOT NULL,
            source_event_id INTEGER,
            request_id TEXT,
            damage INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(source_event_type, source_event_id, attacker_user_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_guardian_duels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            duel_key TEXT NOT NULL,
            faction_a_key TEXT NOT NULL,
            faction_b_key TEXT NOT NULL,
            guardian_a_id INTEGER,
            guardian_b_id INTEGER,
            winner_faction_key TEXT,
            result_status TEXT NOT NULL DEFAULT 'pending',
            battle_log_json TEXT,
            summary_text TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            updated_at TEXT,
            UNIQUE(week_key, duel_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_facilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            faction_key TEXT NOT NULL UNIQUE,
            facility_key TEXT NOT NULL,
            facility_name TEXT NOT NULL,
            description TEXT,
            level INTEGER NOT NULL DEFAULT 1,
            current_exp INTEGER NOT NULL DEFAULT 0,
            next_level_exp INTEGER NOT NULL DEFAULT 100,
            total_exp INTEGER NOT NULL DEFAULT 0,
            visual_tier INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_facility_contributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            faction_key TEXT NOT NULL,
            user_id INTEGER NOT NULL DEFAULT 0,
            source_event_type TEXT NOT NULL,
            source_event_id INTEGER NOT NULL DEFAULT 0,
            material_amount INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(source_event_type, source_event_id, user_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_facility_level_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            faction_key TEXT NOT NULL,
            facility_key TEXT NOT NULL,
            old_level INTEGER NOT NULL,
            new_level INTEGER NOT NULL,
            total_exp INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_territory_areas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            area_key TEXT NOT NULL UNIQUE,
            area_name TEXT NOT NULL,
            description TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            base_faction_key TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_territory_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            area_key TEXT NOT NULL,
            controlling_faction_key TEXT,
            previous_faction_key TEXT,
            control_score INTEGER NOT NULL DEFAULT 0,
            control_reason TEXT,
            is_finalized INTEGER NOT NULL DEFAULT 0,
            finalized_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            UNIQUE(week_key, area_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_territory_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            area_key TEXT NOT NULL,
            faction_key TEXT NOT NULL,
            activity_score INTEGER NOT NULL DEFAULT 0,
            guardian_score INTEGER NOT NULL DEFAULT 0,
            representative_score INTEGER NOT NULL DEFAULT 0,
            guardian_duel_score INTEGER NOT NULL DEFAULT 0,
            facility_score INTEGER NOT NULL DEFAULT 0,
            total_score INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            UNIQUE(week_key, area_key, faction_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_strategy_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            faction_key TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            strategy_key TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            UNIQUE(week_key, user_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_weekly_strategies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            faction_key TEXT NOT NULL,
            strategy_key TEXT NOT NULL,
            vote_count INTEGER NOT NULL DEFAULT 0,
            is_finalized INTEGER NOT NULL DEFAULT 0,
            finalized_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            UNIQUE(week_key, faction_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_representatives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            faction_key TEXT NOT NULL,
            user_id INTEGER,
            robot_id INTEGER,
            robot_name TEXT,
            robot_image_path TEXT,
            selection_type TEXT NOT NULL DEFAULT 'manual',
            selection_reason TEXT,
            contribution_damage INTEGER NOT NULL DEFAULT 0,
            activity_score INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            UNIQUE(week_key, faction_key)
        )
        """
    )
    rep_cols = {row[1] for row in cur.execute("PRAGMA table_info(faction_representatives)").fetchall()}
    if "selection_reason" not in rep_cols:
        cur.execute("ALTER TABLE faction_representatives ADD COLUMN selection_reason TEXT")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS faction_representative_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            match_key TEXT NOT NULL,
            faction_a_key TEXT NOT NULL,
            faction_b_key TEXT NOT NULL,
            representative_a_id INTEGER,
            representative_b_id INTEGER,
            winner_faction_key TEXT,
            winner_user_id INTEGER,
            result_status TEXT NOT NULL DEFAULT 'pending',
            battle_log_json TEXT,
            summary_text TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            updated_at TEXT,
            UNIQUE(week_key, match_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS champ_defeat_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            champ_robot_id INTEGER NOT NULL,
            champ_user_id INTEGER,
            defeated_at TEXT NOT NULL,
            reward_core_granted INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, champ_robot_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS champ_daily_bonus_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            day_key TEXT NOT NULL,
            granted_at TEXT NOT NULL,
            UNIQUE(user_id, day_key)
        )
        """
    )
    cur.execute(
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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS layer4_warning_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            area_key TEXT NOT NULL,
            progress_count INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            UNIQUE(user_id, area_key),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_layer4_warning_progress_user_area ON layer4_warning_progress(user_id, area_key)"
    )
    cur.execute(
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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_trophies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            trophy_key TEXT NOT NULL,
            granted_at INTEGER NOT NULL,
            UNIQUE(user_id, trophy_key),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
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
    cur.execute(
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
    cur.execute(
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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_title_unlocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            robot_id INTEGER NOT NULL,
            title_id INTEGER NOT NULL,
            unlocked_at INTEGER NOT NULL,
            UNIQUE(robot_id, title_id)
        )
        """
    )
    cur.execute(
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
            created_at INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS showcase_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            robot_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            vote_type TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            UNIQUE(robot_id, user_id, vote_type)
        )
        """
    )
    cur.execute(
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
            reject_reason_key TEXT,
            tags_json TEXT,
            intended_style_key TEXT,
            chart_hp INTEGER NOT NULL DEFAULT 50,
            chart_atk INTEGER NOT NULL DEFAULT 50,
            chart_def INTEGER NOT NULL DEFAULT 50,
            chart_spd INTEGER NOT NULL DEFAULT 50,
            chart_acc INTEGER NOT NULL DEFAULT 50,
            chart_cri INTEGER NOT NULL DEFAULT 50,
            is_featured INTEGER NOT NULL DEFAULT 0,
            is_trending_boosted INTEGER NOT NULL DEFAULT 0,
            is_adoption_candidate INTEGER NOT NULL DEFAULT 0,
            adoption_stage TEXT NOT NULL DEFAULT 'none',
            adoption_type TEXT,
            credit_name TEXT,
            terms_version TEXT,
            terms_accepted_at INTEGER,
            terms_snapshot_text TEXT,
            ai_generation_declared TEXT,
            source_note TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            approved_at INTEGER,
            approved_by_user_id INTEGER,
            disabled_at INTEGER,
            disabled_by_user_id INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_submission_likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            UNIQUE(submission_id, user_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_submission_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            note TEXT,
            created_at INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_submission_adoptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL,
            source_user_id INTEGER NOT NULL,
            adoption_type TEXT,
            internal_asset_key TEXT,
            credit_name TEXT,
            implementation_note TEXT,
            status TEXT NOT NULL DEFAULT 'candidate',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    cur.execute(
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
    cur.execute(
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
            UNIQUE(race_id, user_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_race_frames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id INTEGER NOT NULL,
            frame_no INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            UNIQUE(race_id, frame_no)
        )
        """
    )
    cur.execute(
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
            UNIQUE(race_id, entry_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS mini_tactics_battles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seed INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'prototype',
            mode TEXT NOT NULL DEFAULT 'auto_watch',
            map_json TEXT NOT NULL,
            units_json TEXT NOT NULL,
            frames_json TEXT NOT NULL,
            board_state_json TEXT,
            action_log_json TEXT,
            current_turn_side TEXT,
            turn_number INTEGER NOT NULL DEFAULT 1,
            result TEXT,
            battle_type TEXT NOT NULL DEFAULT 'cpu',
            invite_token TEXT,
            host_user_id INTEGER,
            guest_user_id INTEGER,
            host_side TEXT,
            guest_side TEXT,
            current_turn_user_id INTEGER,
            online_status TEXT,
            last_action_at INTEGER,
            updated_at INTEGER,
            created_at INTEGER NOT NULL,
            created_by_user_id INTEGER NOT NULL
        )
        """
    )
    cur.execute(
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
    cur.execute(
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
            UNIQUE(race_id, entry_order)
        )
        """
    )
    cur.execute(
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
            UNIQUE(user_id, race_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_casino_frames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id INTEGER NOT NULL,
            frame_no INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            UNIQUE(race_id, frame_no)
        )
        """
    )
    cur.execute(
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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_casino_prize_claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            prize_id INTEGER NOT NULL,
            cost_lab_coin INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )
    lab_race_cols = {row[1] for row in cur.execute("PRAGMA table_info(lab_races)").fetchall()}
    if "course_payload_json" not in lab_race_cols:
        cur.execute("ALTER TABLE lab_races ADD COLUMN course_payload_json TEXT")
    lab_casino_race_cols = {row[1] for row in cur.execute("PRAGMA table_info(lab_casino_races)").fetchall()}
    if "course_payload_json" not in lab_casino_race_cols:
        cur.execute("ALTER TABLE lab_casino_races ADD COLUMN course_payload_json TEXT")
    udi_cols = {row[1] for row in cur.execute("PRAGMA table_info(user_decor_inventory)").fetchall()}
    if "acquired_at" not in udi_cols:
        cur.execute("ALTER TABLE user_decor_inventory ADD COLUMN acquired_at INTEGER")
        if "created_at" in udi_cols:
            cur.execute("UPDATE user_decor_inventory SET acquired_at = created_at WHERE acquired_at IS NULL")
        cur.execute("UPDATE user_decor_inventory SET acquired_at = ? WHERE acquired_at IS NULL", (int(time.time()),))
    trophy_cols = {row[1] for row in cur.execute("PRAGMA table_info(user_trophies)").fetchall()}
    if "granted_at" not in trophy_cols and trophy_cols:
        cur.execute("ALTER TABLE user_trophies ADD COLUMN granted_at INTEGER")
        cur.execute("UPDATE user_trophies SET granted_at = ? WHERE granted_at IS NULL", (int(time.time()),))
    po_cols = {row[1] for row in cur.execute("PRAGMA table_info(payment_orders)").fetchall()}
    if "user_id" not in po_cols:
        cur.execute("ALTER TABLE payment_orders ADD COLUMN user_id INTEGER")
    if "product_key" not in po_cols:
        cur.execute("ALTER TABLE payment_orders ADD COLUMN product_key TEXT")
    if "stripe_checkout_session_id" not in po_cols:
        cur.execute("ALTER TABLE payment_orders ADD COLUMN stripe_checkout_session_id TEXT")
    if "stripe_payment_intent_id" not in po_cols:
        cur.execute("ALTER TABLE payment_orders ADD COLUMN stripe_payment_intent_id TEXT")
    if "stripe_event_id" not in po_cols:
        cur.execute("ALTER TABLE payment_orders ADD COLUMN stripe_event_id TEXT")
    if "amount_jpy" not in po_cols:
        cur.execute("ALTER TABLE payment_orders ADD COLUMN amount_jpy INTEGER")
    if "currency" not in po_cols:
        cur.execute("ALTER TABLE payment_orders ADD COLUMN currency TEXT")
    if "status" not in po_cols:
        cur.execute("ALTER TABLE payment_orders ADD COLUMN status TEXT NOT NULL DEFAULT 'created'")
    if "grant_type" not in po_cols:
        cur.execute("ALTER TABLE payment_orders ADD COLUMN grant_type TEXT NOT NULL DEFAULT 'decor'")
    if "boost_days" not in po_cols:
        cur.execute("ALTER TABLE payment_orders ADD COLUMN boost_days INTEGER NOT NULL DEFAULT 0")
    if "starts_at" not in po_cols:
        cur.execute("ALTER TABLE payment_orders ADD COLUMN starts_at INTEGER")
    if "ends_at" not in po_cols:
        cur.execute("ALTER TABLE payment_orders ADD COLUMN ends_at INTEGER")
    if "granted_at" not in po_cols:
        cur.execute("ALTER TABLE payment_orders ADD COLUMN granted_at INTEGER")
    if "created_at" not in po_cols:
        cur.execute("ALTER TABLE payment_orders ADD COLUMN created_at INTEGER NOT NULL DEFAULT 0")
    if "updated_at" not in po_cols:
        cur.execute("ALTER TABLE payment_orders ADD COLUMN updated_at INTEGER NOT NULL DEFAULT 0")
    cur.execute("UPDATE payment_orders SET status = 'created' WHERE status IS NULL OR TRIM(status) = ''")
    cur.execute("UPDATE payment_orders SET grant_type = 'decor' WHERE grant_type IS NULL OR TRIM(grant_type) = ''")
    cur.execute("UPDATE payment_orders SET boost_days = 0 WHERE boost_days IS NULL")
    cur.execute("UPDATE payment_orders SET created_at = 0 WHERE created_at IS NULL")
    cur.execute("UPDATE payment_orders SET updated_at = created_at WHERE updated_at IS NULL OR updated_at = 0")
    cur.execute(
        """
        INSERT OR IGNORE INTO user_trophies (user_id, trophy_key, granted_at)
        SELECT
            po.user_id,
            ?,
            COALESCE(po.granted_at, po.updated_at, po.created_at, ?)
        FROM payment_orders po
        WHERE po.product_key IN (?, ?)
          AND po.user_id IS NOT NULL
          AND po.status IN ('completed', 'granted')
        """,
        (
            SUPPORTER_FOUNDER_TROPHY_KEY,
            int(time.time()),
            LEGACY_SUPPORT_PACK_PRODUCT_KEY,
            SUPPORT_PACK_FOUNDER_PRODUCT_KEY,
        ),
    )
    cur.execute(
        """
        INSERT OR IGNORE INTO user_trophies (user_id, trophy_key, granted_at)
        SELECT
            po.user_id,
            ?,
            COALESCE(po.granted_at, po.updated_at, po.created_at, ?)
        FROM payment_orders po
        WHERE po.product_key = ?
          AND po.user_id IS NOT NULL
          AND po.status IN ('completed', 'granted')
        """,
        (
            SUPPORTER_LAB_TROPHY_KEY,
            int(time.time()),
            SUPPORT_PACK_LAB_PRODUCT_KEY,
        ),
    )

    users_cols = {row[1] for row in cur.execute("PRAGMA table_info(users)").fetchall()}
    added_research_boost_charges = "research_boost_charges" not in users_cols
    if "avatar_path" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN avatar_path TEXT")
    if "active_robot_id" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN active_robot_id INTEGER")
    if "active_research_module_instance_id" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN active_research_module_instance_id INTEGER")
    if "stable_no_damage_wins" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN stable_no_damage_wins INTEGER NOT NULL DEFAULT 0")
    if "burst_crit_finisher_kills" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN burst_crit_finisher_kills INTEGER NOT NULL DEFAULT 0")
    if "desperate_low_hp_wins" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN desperate_low_hp_wins INTEGER NOT NULL DEFAULT 0")
    if "faction" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN faction TEXT")
    if "faction_changed_at" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN faction_changed_at TEXT")
    if "is_banned" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER NOT NULL DEFAULT 0")
    if "is_admin_protected" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN is_admin_protected INTEGER NOT NULL DEFAULT 0")
    if "banned_at" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN banned_at TEXT")
    if "banned_reason" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN banned_reason TEXT")
    if "banned_by_user_id" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN banned_by_user_id INTEGER")
    if "has_seen_intro_modal" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN has_seen_intro_modal INTEGER NOT NULL DEFAULT 0")
    if "intro_guide_closed_at" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN intro_guide_closed_at TEXT")
    if "last_explore_area_key" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN last_explore_area_key TEXT")
    if "explore_boost_until" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN explore_boost_until INTEGER NOT NULL DEFAULT 0")
    if "lab_small_boost_count" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN lab_small_boost_count INTEGER NOT NULL DEFAULT 0")
    if "lab_small_boost_until" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN lab_small_boost_until INTEGER NOT NULL DEFAULT 0")
    if added_research_boost_charges:
        cur.execute("ALTER TABLE users ADD COLUMN research_boost_charges INTEGER NOT NULL DEFAULT 0")
    if "research_boost_auto_use_enabled" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN research_boost_auto_use_enabled INTEGER NOT NULL DEFAULT 1")
    if "research_module_pity" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN research_module_pity INTEGER NOT NULL DEFAULT 0")
    if "home_beginner_mission_hidden" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN home_beginner_mission_hidden INTEGER NOT NULL DEFAULT 0")
    if "home_next_action_collapsed" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN home_next_action_collapsed INTEGER NOT NULL DEFAULT 0")
    if "home_daily_research_collapsed" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN home_daily_research_collapsed INTEGER NOT NULL DEFAULT 0")
    if "tutorial_layer1_state" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN tutorial_layer1_state TEXT NOT NULL DEFAULT 'new'")
    if "tutorial_layer1_normal_win_count" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN tutorial_layer1_normal_win_count INTEGER NOT NULL DEFAULT 0")
    if "tutorial_layer1_boss_seen_at" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN tutorial_layer1_boss_seen_at INTEGER")
    if "tutorial_layer1_boss_fail_count" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN tutorial_layer1_boss_fail_count INTEGER NOT NULL DEFAULT 0")
    if "tutorial_layer1_boss_help_ready" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN tutorial_layer1_boss_help_ready INTEGER NOT NULL DEFAULT 0")
    if "tutorial_layer1_forced_boss_ready" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN tutorial_layer1_forced_boss_ready INTEGER NOT NULL DEFAULT 0")
    if "tutorial_layer1_fuse_after_boss_fail_count" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN tutorial_layer1_fuse_after_boss_fail_count INTEGER NOT NULL DEFAULT 0")
    if "tutorial_layer1_updated_at" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN tutorial_layer1_updated_at INTEGER NOT NULL DEFAULT 0")
    if "layer1_first_clear_reward_claimed" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN layer1_first_clear_reward_claimed INTEGER NOT NULL DEFAULT 0")
    if "layer1_first_clear_home_seen" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN layer1_first_clear_home_seen INTEGER NOT NULL DEFAULT 0")
    added_lab_coin_converted_at = "lab_coin_converted_at" not in users_cols
    if "lab_coin" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN lab_coin INTEGER NOT NULL DEFAULT 0")
    if "lab_coin_last_daily_at" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN lab_coin_last_daily_at TEXT")
    if added_lab_coin_converted_at:
        cur.execute("ALTER TABLE users ADD COLUMN lab_coin_converted_at INTEGER NOT NULL DEFAULT 0")
    if "lab_level" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN lab_level INTEGER NOT NULL DEFAULT 1")
    if "lab_exp" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN lab_exp INTEGER NOT NULL DEFAULT 0")
    if "lab_total_exp" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN lab_total_exp INTEGER NOT NULL DEFAULT 0")
    if "lab_rank_label" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN lab_rank_label TEXT NOT NULL DEFAULT '見習い研究員'")
    if "lab_level_updated_at" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN lab_level_updated_at TEXT")
    if "market_refresh_count_today" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN market_refresh_count_today INTEGER NOT NULL DEFAULT 0")
    if "market_free_refresh_used_at" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN market_free_refresh_used_at TEXT")
    if "market_refresh_day_key" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN market_refresh_day_key TEXT")
    if "last_daily_research_modal_day" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN last_daily_research_modal_day TEXT")

    research_module_cols = {row[1] for row in cur.execute("PRAGMA table_info(research_modules)").fetchall()}
    research_module_trade_cols = {"tier", "trade_policy", "source_type", "is_limited", "npc_sell_price"}
    added_research_module_trade_cols = any(column not in research_module_cols for column in research_module_trade_cols)
    research_module_column_defs = {
        "module_key": "module_key TEXT",
        "name_ja": "name_ja TEXT",
        "rarity": "rarity TEXT NOT NULL DEFAULT 'prototype'",
        "family": "family TEXT NOT NULL DEFAULT 'stable'",
        "hp_bonus": "hp_bonus INTEGER NOT NULL DEFAULT 0",
        "atk_bonus": "atk_bonus INTEGER NOT NULL DEFAULT 0",
        "def_bonus": "def_bonus INTEGER NOT NULL DEFAULT 0",
        "spd_bonus": "spd_bonus INTEGER NOT NULL DEFAULT 0",
        "acc_bonus": "acc_bonus INTEGER NOT NULL DEFAULT 0",
        "cri_bonus": "cri_bonus INTEGER NOT NULL DEFAULT 0",
        "description": "description TEXT",
        "tier": "tier INTEGER NOT NULL DEFAULT 1",
        "trade_policy": "trade_policy TEXT NOT NULL DEFAULT 'tradable'",
        "source_type": "source_type TEXT NOT NULL DEFAULT 'normal_drop'",
        "is_limited": "is_limited INTEGER NOT NULL DEFAULT 0",
        "npc_sell_price": "npc_sell_price INTEGER NOT NULL DEFAULT 0",
        "is_active": "is_active INTEGER NOT NULL DEFAULT 1",
        "created_at": "created_at INTEGER NOT NULL DEFAULT 0",
    }
    for column_name, column_sql in research_module_column_defs.items():
        if column_name not in research_module_cols:
            cur.execute(f"ALTER TABLE research_modules ADD COLUMN {column_sql}")
    user_research_module_cols = {row[1] for row in cur.execute("PRAGMA table_info(user_research_modules)").fetchall()}
    user_research_module_column_defs = {
        "user_id": "user_id INTEGER",
        "module_key": "module_key TEXT",
        "status": "status TEXT NOT NULL DEFAULT 'inventory'",
        "is_locked": "is_locked INTEGER NOT NULL DEFAULT 0",
        "sold_at": "sold_at TEXT",
        "hp_bonus": "hp_bonus INTEGER",
        "atk_bonus": "atk_bonus INTEGER",
        "def_bonus": "def_bonus INTEGER",
        "spd_bonus": "spd_bonus INTEGER",
        "acc_bonus": "acc_bonus INTEGER",
        "cri_bonus": "cri_bonus INTEGER",
        "synthesis_grade": "synthesis_grade TEXT",
        "synthesis_family": "synthesis_family TEXT",
        "synthesis_result_type": "synthesis_result_type TEXT",
        "origin_module_a_id": "origin_module_a_id INTEGER",
        "origin_module_b_id": "origin_module_b_id INTEGER",
        "generation": "generation INTEGER NOT NULL DEFAULT 0",
        "synthesis_score": "synthesis_score INTEGER NOT NULL DEFAULT 0",
        "generated_name_ja": "generated_name_ja TEXT",
        "created_at": "created_at INTEGER NOT NULL DEFAULT 0",
        "updated_at": "updated_at INTEGER NOT NULL DEFAULT 0",
    }
    for column_name, column_sql in user_research_module_column_defs.items():
        if column_name not in user_research_module_cols:
            cur.execute(f"ALTER TABLE user_research_modules ADD COLUMN {column_sql}")
    now_ts = int(time.time())
    for seed in RESEARCH_MODULE_SEEDS:
        cur.execute(
            """
            INSERT OR IGNORE INTO research_modules (
                module_key, name_ja, rarity, family,
                hp_bonus, atk_bonus, def_bonus, spd_bonus, acc_bonus, cri_bonus,
                description, is_active, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (*seed, now_ts),
        )
    cur.execute("UPDATE research_modules SET is_active = 1 WHERE is_active IS NULL")
    has_seed_prices = cur.execute("SELECT 1 FROM research_modules WHERE npc_sell_price > 0 LIMIT 1").fetchone()
    if added_research_module_trade_cols or not has_seed_prices:
        cur.execute(
            """
            UPDATE research_modules
            SET tier = CASE WHEN rarity = 'complete' THEN 2 ELSE 1 END,
                trade_policy = 'tradable',
                source_type = CASE WHEN rarity = 'complete' THEN 'combine' ELSE 'normal_drop' END,
                is_limited = COALESCE(is_limited, 0),
                npc_sell_price = CASE WHEN rarity = 'complete' THEN 1500 ELSE 300 END
            WHERE rarity IN ('prototype', 'complete')
            """
        )
    cur.execute(
        """
        UPDATE research_modules
        SET rarity = 'synth',
            tier = 1,
            trade_policy = 'tradable',
            source_type = 'synthesis',
            is_limited = 0,
            npc_sell_price = 600
        WHERE module_key = 'synthesized_module'
        """
    )
    cur.execute("UPDATE users SET research_module_pity = 0 WHERE research_module_pity IS NULL OR research_module_pity < 0")
    cur.execute("UPDATE user_research_modules SET status = 'inventory' WHERE status IS NULL OR TRIM(status) = ''")
    cur.execute("UPDATE user_research_modules SET is_locked = 0 WHERE is_locked IS NULL")
    cur.execute("UPDATE user_research_modules SET created_at = ? WHERE created_at IS NULL OR created_at = 0", (now_ts,))
    cur.execute("UPDATE user_research_modules SET updated_at = created_at WHERE updated_at IS NULL OR updated_at = 0")
    cur.execute(
        """
        INSERT OR IGNORE INTO user_research_module_catalog (
            user_id, module_key, first_obtained_at, first_instance_id
        )
        SELECT user_id, module_key, MIN(created_at), MIN(id)
        FROM user_research_modules
        WHERE user_id IS NOT NULL
          AND module_key IS NOT NULL
          AND TRIM(module_key) != ''
        GROUP BY user_id, module_key
        """
    )
    for release_key in RELEASE_FLAG_KEYS:
        cur.execute(
            """
            INSERT INTO release_flags (key, is_public, updated_at)
            VALUES (?, 0, 0)
            ON CONFLICT(key) DO NOTHING
            """,
            (release_key,),
        )
    cur.execute(
        """
        INSERT INTO maintenance_state (id, mode, updated_at, updated_by_user_id)
        VALUES (1, 'off', 0, NULL)
        ON CONFLICT(id) DO NOTHING
        """
    )
    cur.execute(
        "UPDATE users SET faction = NULL WHERE faction IS NOT NULL AND LOWER(TRIM(faction)) NOT IN ('ignis','ventra','aurix')"
    )
    cur.execute(
        """
        UPDATE users
        SET tutorial_layer1_state = 'new'
        WHERE tutorial_layer1_state IS NULL
           OR tutorial_layer1_state NOT IN ('new','won_normal_once','saw_boss','boss_failed_once','cleared_layer1')
        """
    )
    cur.execute("UPDATE users SET tutorial_layer1_state = 'cleared_layer1' WHERE max_unlocked_layer >= 2")
    cur.execute("UPDATE users SET tutorial_layer1_normal_win_count = 0 WHERE tutorial_layer1_normal_win_count IS NULL OR tutorial_layer1_normal_win_count < 0")
    cur.execute("UPDATE users SET tutorial_layer1_boss_fail_count = 0 WHERE tutorial_layer1_boss_fail_count IS NULL OR tutorial_layer1_boss_fail_count < 0")
    cur.execute("UPDATE users SET tutorial_layer1_boss_help_ready = 0 WHERE tutorial_layer1_boss_help_ready IS NULL")
    cur.execute("UPDATE users SET tutorial_layer1_forced_boss_ready = 0 WHERE tutorial_layer1_forced_boss_ready IS NULL")
    cur.execute("UPDATE users SET tutorial_layer1_fuse_after_boss_fail_count = 0 WHERE tutorial_layer1_fuse_after_boss_fail_count IS NULL OR tutorial_layer1_fuse_after_boss_fail_count < 0")
    cur.execute("UPDATE users SET tutorial_layer1_updated_at = 0 WHERE tutorial_layer1_updated_at IS NULL")
    cur.execute("UPDATE users SET layer1_first_clear_reward_claimed = 0 WHERE layer1_first_clear_reward_claimed IS NULL")
    cur.execute("UPDATE users SET layer1_first_clear_home_seen = 0 WHERE layer1_first_clear_home_seen IS NULL")
    cur.execute("UPDATE users SET is_banned = 0 WHERE is_banned IS NULL")
    cur.execute("UPDATE users SET is_admin_protected = 0 WHERE is_admin_protected IS NULL")
    cur.execute("UPDATE users SET banned_at = NULL WHERE banned_at IS NOT NULL AND TRIM(banned_at) = ''")
    cur.execute("UPDATE users SET banned_reason = NULL WHERE banned_reason IS NOT NULL AND TRIM(banned_reason) = ''")
    cur.execute("UPDATE users SET has_seen_intro_modal = 0 WHERE has_seen_intro_modal IS NULL")
    cur.execute("UPDATE users SET intro_guide_closed_at = NULL WHERE intro_guide_closed_at IS NOT NULL AND TRIM(intro_guide_closed_at) = ''")
    cur.execute("UPDATE users SET last_explore_area_key = NULL WHERE last_explore_area_key IS NOT NULL AND TRIM(last_explore_area_key) = ''")
    cur.execute("UPDATE users SET explore_boost_until = 0 WHERE explore_boost_until IS NULL")
    cur.execute("UPDATE users SET lab_small_boost_count = 0 WHERE lab_small_boost_count IS NULL OR lab_small_boost_count < 0")
    cur.execute("UPDATE users SET lab_small_boost_count = 3 WHERE lab_small_boost_count > 3")
    cur.execute("UPDATE users SET lab_small_boost_until = 0 WHERE lab_small_boost_until IS NULL OR lab_small_boost_until < 0")
    if added_research_boost_charges:
        now_ts = int(time.time())
        cur.execute(
            """
            UPDATE users
            SET research_boost_charges = MIN(
                3,
                MAX(
                    COALESCE(research_boost_charges, 0),
                    COALESCE(lab_small_boost_count, 0),
                    CASE WHEN COALESCE(lab_small_boost_until, 0) > ? THEN 1 ELSE 0 END
                )
            )
            """,
            (now_ts,),
        )
    cur.execute("UPDATE users SET research_boost_charges = 0 WHERE research_boost_charges IS NULL OR research_boost_charges < 0")
    cur.execute("UPDATE users SET research_boost_charges = 3 WHERE research_boost_charges > 3")
    cur.execute("UPDATE users SET research_boost_auto_use_enabled = 1 WHERE research_boost_auto_use_enabled IS NULL")
    cur.execute("UPDATE users SET research_boost_auto_use_enabled = 0 WHERE research_boost_auto_use_enabled NOT IN (0, 1)")
    cur.execute("UPDATE users SET home_beginner_mission_hidden = 0 WHERE home_beginner_mission_hidden IS NULL")
    cur.execute("UPDATE users SET home_next_action_collapsed = 0 WHERE home_next_action_collapsed IS NULL")
    cur.execute("UPDATE users SET home_daily_research_collapsed = 0 WHERE home_daily_research_collapsed IS NULL")
    cur.execute(
        """
        UPDATE users
        SET
            coins = COALESCE(coins, 0) + MAX(COALESCE(lab_coin, 0), 0),
            lab_coin = 0,
            lab_coin_converted_at = ?
        WHERE COALESCE(lab_coin_converted_at, 0) = 0
          AND COALESCE(lab_coin, 0) > 0
        """,
        (int(time.time()),),
    )
    cur.execute("UPDATE users SET lab_coin = 0 WHERE lab_coin IS NULL OR lab_coin < 0")
    cur.execute("UPDATE users SET lab_level = 1 WHERE lab_level IS NULL OR lab_level < 1")
    cur.execute("UPDATE users SET lab_exp = 0 WHERE lab_exp IS NULL OR lab_exp < 0")
    cur.execute("UPDATE users SET lab_total_exp = 0 WHERE lab_total_exp IS NULL OR lab_total_exp < 0")
    cur.execute("UPDATE users SET lab_rank_label = '見習い研究員' WHERE lab_rank_label IS NULL OR TRIM(lab_rank_label) = ''")
    cur.execute("UPDATE users SET market_refresh_count_today = 0 WHERE market_refresh_count_today IS NULL OR market_refresh_count_today < 0")
    cur.execute("UPDATE users SET is_admin_protected = 1 WHERE is_admin = 1")
    ri_cols = {row[1] for row in cur.execute("PRAGMA table_info(robot_instances)").fetchall()}
    if "personality" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN personality TEXT")
    if "icon_32_path" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN icon_32_path TEXT")
    if "decomposed_at" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN decomposed_at INTEGER")
    if "combat_mode" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN combat_mode TEXT NOT NULL DEFAULT 'normal'")
    if "frame_type" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN frame_type TEXT DEFAULT 'normal'")
    if "is_mixed_frame" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN is_mixed_frame INTEGER NOT NULL DEFAULT 0")
    if "build_frame_mode" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN build_frame_mode TEXT NOT NULL DEFAULT 'normal'")
    if "is_public" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN is_public INTEGER NOT NULL DEFAULT 1")
    if "style_key" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN style_key TEXT NOT NULL DEFAULT 'stable'")
    if "style_stats_json" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN style_stats_json TEXT NOT NULL DEFAULT '{}'")
    if "style_scores_json" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN style_scores_json TEXT")
    if "style_rank_json" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN style_rank_json TEXT")
    if "style_current_key" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN style_current_key TEXT")
    if "style_next_key" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN style_next_key TEXT")
    if "style_updated_at" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN style_updated_at TEXT")
    if "primary_title_key" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN primary_title_key TEXT")
    if "style_title_key" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN style_title_key TEXT")
    if "honor_title_key" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN honor_title_key TEXT")
    cur.execute("UPDATE robot_instances SET combat_mode = 'normal' WHERE combat_mode IS NULL OR combat_mode = ''")
    cur.execute("UPDATE robot_instances SET frame_type = 'normal' WHERE frame_type IS NULL OR TRIM(frame_type) = ''")
    cur.execute("UPDATE robot_instances SET is_mixed_frame = 0 WHERE is_mixed_frame IS NULL")
    cur.execute("UPDATE robot_instances SET build_frame_mode = 'normal' WHERE build_frame_mode IS NULL OR TRIM(build_frame_mode) = ''")
    cur.execute("UPDATE robot_instances SET is_public = 1 WHERE is_public IS NULL")
    cur.execute("UPDATE robot_instances SET style_key = 'stable' WHERE style_key IS NULL OR TRIM(style_key) = ''")
    cur.execute("UPDATE robot_instances SET style_stats_json = '{}' WHERE style_stats_json IS NULL OR TRIM(style_stats_json) = ''")
    ensure_robot_title_system(cur)
    rp_cols = {row[1] for row in cur.execute("PRAGMA table_info(robot_parts)").fetchall()}
    if "rarity" not in rp_cols:
        cur.execute("ALTER TABLE robot_parts ADD COLUMN rarity TEXT")
    if "is_active" not in rp_cols:
        cur.execute("ALTER TABLE robot_parts ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
    if "element" not in rp_cols:
        cur.execute("ALTER TABLE robot_parts ADD COLUMN element TEXT")
    if "series" not in rp_cols:
        cur.execute("ALTER TABLE robot_parts ADD COLUMN series TEXT")
    if "frame_type" not in rp_cols:
        cur.execute("ALTER TABLE robot_parts ADD COLUMN frame_type TEXT DEFAULT 'normal'")
    if "series_key" not in rp_cols:
        cur.execute("ALTER TABLE robot_parts ADD COLUMN series_key TEXT")
    if "series_label" not in rp_cols:
        cur.execute("ALTER TABLE robot_parts ADD COLUMN series_label TEXT")
    if "display_name_ja" not in rp_cols:
        cur.execute("ALTER TABLE robot_parts ADD COLUMN display_name_ja TEXT")
    if "is_admin_only" not in rp_cols:
        cur.execute("ALTER TABLE robot_parts ADD COLUMN is_admin_only INTEGER NOT NULL DEFAULT 0")
    cur.execute("UPDATE robot_parts SET rarity = 'N' WHERE rarity IS NULL OR rarity = ''")
    cur.execute("UPDATE robot_parts SET element = 'NORMAL' WHERE element IS NULL OR element = ''")
    cur.execute("UPDATE robot_parts SET series = 'S1' WHERE series IS NULL OR series = ''")
    cur.execute("UPDATE robot_parts SET frame_type = 'normal' WHERE frame_type IS NULL OR TRIM(frame_type) = ''")
    cur.execute("UPDATE robot_parts SET is_active = 1 WHERE is_active IS NULL")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS series_master (
            series_key TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            category TEXT NOT NULL,
            frame_type TEXT DEFAULT 'normal',
            role_label TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            max_rarity TEXT DEFAULT 'N',
            can_evolve INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 0,
            released_at INTEGER
        )
        """
    )
    sm_cols = {row[1] for row in cur.execute("PRAGMA table_info(series_master)").fetchall()}
    if "frame_type" not in sm_cols:
        cur.execute("ALTER TABLE series_master ADD COLUMN frame_type TEXT DEFAULT 'normal'")
    if "max_rarity" not in sm_cols:
        cur.execute("ALTER TABLE series_master ADD COLUMN max_rarity TEXT DEFAULT 'N'")
    if "can_evolve" not in sm_cols:
        cur.execute("ALTER TABLE series_master ADD COLUMN can_evolve INTEGER NOT NULL DEFAULT 0")
    cur.execute("UPDATE series_master SET frame_type = 'normal' WHERE frame_type IS NULL OR TRIM(frame_type) = ''")
    cur.execute("UPDATE series_master SET max_rarity = 'N' WHERE max_rarity IS NULL OR TRIM(max_rarity) = ''")
    cur.execute("UPDATE series_master SET can_evolve = 0 WHERE can_evolve IS NULL")
    cur.execute("UPDATE series_master SET frame_type = 'insect', max_rarity = 'N', can_evolve = 0 WHERE series_key LIKE 'insect_%'")
    cur.execute("UPDATE series_master SET frame_type = 'dinosaur', max_rarity = 'N', can_evolve = 0 WHERE series_key LIKE 'dino_%'")
    cur.execute("UPDATE series_master SET frame_type = 'normal', max_rarity = 'R', can_evolve = 1 WHERE series_key NOT LIKE 'insect_%' AND series_key NOT LIKE 'dino_%'")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS series_set_bonus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_key TEXT NOT NULL,
            pieces_required INTEGER NOT NULL,
            stat_key TEXT NOT NULL,
            value REAL NOT NULL,
            value_type TEXT NOT NULL DEFAULT 'percent',
            UNIQUE(series_key, pieces_required, stat_key)
        )
        """
    )
    ssb_cols = {row[1] for row in cur.execute("PRAGMA table_info(series_set_bonus)").fetchall()}
    if "value_type" not in ssb_cols:
        cur.execute("ALTER TABLE series_set_bonus ADD COLUMN value_type TEXT NOT NULL DEFAULT 'percent'")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS enemy_series_drops (
            enemy_id INTEGER NOT NULL,
            series_key TEXT NOT NULL,
            drop_weight INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (enemy_id, series_key)
        )
        """
    )
    _ensure_default_normal_robot_parts(cur)
    _upsert_series_rows(cur)
    _upsert_mini_robot_species(cur)
    _apply_series_part_assignments(cur)
    _sync_insect_part_display_names(cur)
    rows_to_fill = cur.execute(
        """
        SELECT id, key, rarity, element, part_type
        FROM robot_parts
        WHERE COALESCE(TRIM(display_name_ja), '') = ''
        """
    ).fetchall()
    updated_display_name = 0
    for row in rows_to_fill:
        name = generate_part_display_name_ja(
            row[1],
            rarity=row[2],
            element=row[3],
            part_type=row[4],
        )
        if not name:
            continue
        cur.execute("UPDATE robot_parts SET display_name_ja = ? WHERE id = ?", (name, int(row[0])))
        updated_display_name += 1
    if updated_display_name > 0:
        print(f"robot_parts display_name_ja backfill updated={updated_display_name}")
    enemy_cols = {row[1] for row in cur.execute("PRAGMA table_info(enemies)").fetchall()}
    if "key" not in enemy_cols:
        cur.execute("ALTER TABLE enemies ADD COLUMN key TEXT")
    if "name_ja" not in enemy_cols:
        cur.execute("ALTER TABLE enemies ADD COLUMN name_ja TEXT")
    if "image_path" not in enemy_cols:
        cur.execute("ALTER TABLE enemies ADD COLUMN image_path TEXT")
    if "tier" not in enemy_cols:
        cur.execute("ALTER TABLE enemies ADD COLUMN tier INTEGER NOT NULL DEFAULT 1")
    if "element" not in enemy_cols:
        cur.execute("ALTER TABLE enemies ADD COLUMN element TEXT NOT NULL DEFAULT 'NORMAL'")
    if "hp" not in enemy_cols:
        cur.execute("ALTER TABLE enemies ADD COLUMN hp INTEGER NOT NULL DEFAULT 10")
    if "atk" not in enemy_cols:
        cur.execute("ALTER TABLE enemies ADD COLUMN atk INTEGER NOT NULL DEFAULT 5")
    if "def" not in enemy_cols:
        cur.execute("ALTER TABLE enemies ADD COLUMN def INTEGER NOT NULL DEFAULT 5")
    if "spd" not in enemy_cols:
        cur.execute("ALTER TABLE enemies ADD COLUMN spd INTEGER NOT NULL DEFAULT 5")
    if "acc" not in enemy_cols:
        cur.execute("ALTER TABLE enemies ADD COLUMN acc INTEGER NOT NULL DEFAULT 5")
    if "cri" not in enemy_cols:
        cur.execute("ALTER TABLE enemies ADD COLUMN cri INTEGER NOT NULL DEFAULT 1")
    if "faction" not in enemy_cols:
        cur.execute("ALTER TABLE enemies ADD COLUMN faction TEXT NOT NULL DEFAULT 'neutral'")
    if "trait" not in enemy_cols:
        cur.execute("ALTER TABLE enemies ADD COLUMN trait TEXT")
    if "is_boss" not in enemy_cols:
        cur.execute("ALTER TABLE enemies ADD COLUMN is_boss INTEGER NOT NULL DEFAULT 0")
    if "boss_area_key" not in enemy_cols:
        cur.execute("ALTER TABLE enemies ADD COLUMN boss_area_key TEXT")
    if "is_active" not in enemy_cols:
        cur.execute("ALTER TABLE enemies ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
    cur.execute("UPDATE enemies SET faction = 'neutral' WHERE faction IS NULL OR faction = ''")
    cur.execute("UPDATE enemies SET trait = NULL WHERE COALESCE(trait, '') NOT IN ('', 'heavy', 'fast', 'berserk', 'unstable')")
    cur.execute("UPDATE enemies SET is_boss = 0 WHERE is_boss IS NULL")
    cur.execute(
        """
        UPDATE enemies
        SET boss_area_key = NULL
        WHERE boss_area_key IS NOT NULL
          AND boss_area_key NOT IN (
                'layer_1', 'layer_2', 'layer_3',
                'layer_4_forge', 'layer_4_haze', 'layer_4_burst', 'layer_4_final',
                'layer_5_labyrinth', 'layer_5_pinnacle', 'layer_5_final'
          )
        """
    )
    ubp_cols = {row[1] for row in cur.execute("PRAGMA table_info(user_boss_progress)").fetchall()}
    if "active_boss_enemy_id" not in ubp_cols:
        cur.execute("ALTER TABLE user_boss_progress ADD COLUMN active_boss_enemy_id INTEGER")
    if "boss_attempts_left" not in ubp_cols:
        cur.execute("ALTER TABLE user_boss_progress ADD COLUMN boss_attempts_left INTEGER NOT NULL DEFAULT 0")
    if "boss_alert_expires_at" not in ubp_cols:
        cur.execute("ALTER TABLE user_boss_progress ADD COLUMN boss_alert_expires_at INTEGER")
    cur.execute("UPDATE user_boss_progress SET boss_attempts_left = 0 WHERE boss_attempts_left IS NULL")
    rip_cols = {row[1] for row in cur.execute("PRAGMA table_info(robot_instance_parts)").fetchall()}
    if "head_part_instance_id" not in rip_cols:
        cur.execute("ALTER TABLE robot_instance_parts ADD COLUMN head_part_instance_id INTEGER")
    if "r_arm_part_instance_id" not in rip_cols:
        cur.execute("ALTER TABLE robot_instance_parts ADD COLUMN r_arm_part_instance_id INTEGER")
    if "l_arm_part_instance_id" not in rip_cols:
        cur.execute("ALTER TABLE robot_instance_parts ADD COLUMN l_arm_part_instance_id INTEGER")
    if "legs_part_instance_id" not in rip_cols:
        cur.execute("ALTER TABLE robot_instance_parts ADD COLUMN legs_part_instance_id INTEGER")
    if "decor_asset_id" not in rip_cols:
        cur.execute("ALTER TABLE robot_instance_parts ADD COLUMN decor_asset_id INTEGER")
    for scale_col in ("head_scale_percent", "r_arm_scale_percent", "l_arm_scale_percent", "legs_scale_percent"):
        if scale_col not in rip_cols:
            cur.execute(f"ALTER TABLE robot_instance_parts ADD COLUMN {scale_col} INTEGER NOT NULL DEFAULT 100")
        cur.execute(f"UPDATE robot_instance_parts SET {scale_col} = 100 WHERE {scale_col} IS NULL")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_instance_decors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            robot_instance_id INTEGER NOT NULL,
            decor_asset_id INTEGER NOT NULL,
            slot_index INTEGER NOT NULL,
            offset_x INTEGER NOT NULL DEFAULT 0,
            offset_y INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL DEFAULT 0,
            UNIQUE(robot_instance_id, slot_index),
            FOREIGN KEY (robot_instance_id) REFERENCES robot_instances(id),
            FOREIGN KEY (decor_asset_id) REFERENCES robot_decor_assets(id)
        )
        """
    )
    rid_cols = {row[1] for row in cur.execute("PRAGMA table_info(robot_instance_decors)").fetchall()}
    if "offset_x" not in rid_cols:
        cur.execute("ALTER TABLE robot_instance_decors ADD COLUMN offset_x INTEGER NOT NULL DEFAULT 0")
    if "offset_y" not in rid_cols:
        cur.execute("ALTER TABLE robot_instance_decors ADD COLUMN offset_y INTEGER NOT NULL DEFAULT 0")
    if "created_at" not in rid_cols:
        cur.execute("ALTER TABLE robot_instance_decors ADD COLUMN created_at INTEGER NOT NULL DEFAULT 0")
    if "updated_at" not in rid_cols:
        cur.execute("ALTER TABLE robot_instance_decors ADD COLUMN updated_at INTEGER NOT NULL DEFAULT 0")
    cur.execute(
        """
        INSERT OR IGNORE INTO robot_instance_decors (
            robot_instance_id, decor_asset_id, slot_index, offset_x, offset_y, created_at, updated_at
        )
        SELECT robot_instance_id, decor_asset_id, 0, 0, 0, strftime('%s','now'), strftime('%s','now')
        FROM robot_instance_parts
        WHERE decor_asset_id IS NOT NULL
          AND EXISTS (SELECT 1 FROM robot_decor_assets rda WHERE rda.id = robot_instance_parts.decor_asset_id)
        """
    )
    rda_cols = {row[1] for row in cur.execute("PRAGMA table_info(robot_decor_assets)").fetchall()}
    if "key" not in rda_cols:
        cur.execute("ALTER TABLE robot_decor_assets ADD COLUMN key TEXT")
    if "name_ja" not in rda_cols:
        cur.execute("ALTER TABLE robot_decor_assets ADD COLUMN name_ja TEXT")
    if "image_path" not in rda_cols:
        cur.execute("ALTER TABLE robot_decor_assets ADD COLUMN image_path TEXT")
    if "is_active" not in rda_cols:
        cur.execute("ALTER TABLE robot_decor_assets ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
    if "created_at" not in rda_cols:
        cur.execute("ALTER TABLE robot_decor_assets ADD COLUMN created_at INTEGER NOT NULL DEFAULT 0")
    wel_cols = {row[1] for row in cur.execute("PRAGMA table_info(world_events_log)").fetchall()}
    chat_cols = {row[1] for row in cur.execute("PRAGMA table_info(chat_messages)").fetchall()}
    if "room_key" not in chat_cols:
        cur.execute("ALTER TABLE chat_messages ADD COLUMN room_key TEXT NOT NULL DEFAULT 'world_public'")
    if "deleted_at" not in chat_cols:
        cur.execute("ALTER TABLE chat_messages ADD COLUMN deleted_at TEXT")
    cur.execute("UPDATE chat_messages SET room_key = 'world_public' WHERE room_key IS NULL OR TRIM(room_key) = ''")
    if "user_id" not in wel_cols:
        cur.execute("ALTER TABLE world_events_log ADD COLUMN user_id INTEGER")
    if "request_id" not in wel_cols:
        cur.execute("ALTER TABLE world_events_log ADD COLUMN request_id TEXT")
    if "ip_hash" not in wel_cols:
        cur.execute("ALTER TABLE world_events_log ADD COLUMN ip_hash TEXT")
    if "action_key" not in wel_cols:
        cur.execute("ALTER TABLE world_events_log ADD COLUMN action_key TEXT")
    if "entity_type" not in wel_cols:
        cur.execute("ALTER TABLE world_events_log ADD COLUMN entity_type TEXT")
    if "entity_id" not in wel_cols:
        cur.execute("ALTER TABLE world_events_log ADD COLUMN entity_id INTEGER")
    if "delta_coins" not in wel_cols:
        cur.execute("ALTER TABLE world_events_log ADD COLUMN delta_coins INTEGER")
    if "delta_count" not in wel_cols:
        cur.execute("ALTER TABLE world_events_log ADD COLUMN delta_count INTEGER")
    mini_robot_cols = {row[1] for row in cur.execute("PRAGMA table_info(user_mini_robots)").fetchall()}
    mini_robot_column_defs = {
        "personality_key": "personality_key TEXT DEFAULT NULL",
        "growth_type": "growth_type TEXT DEFAULT NULL",
        "behavior_seed": "behavior_seed INTEGER NOT NULL DEFAULT 0",
        "evolution_seed": "evolution_seed TEXT DEFAULT NULL",
        "trust": "trust INTEGER NOT NULL DEFAULT 0",
        "curiosity": "curiosity INTEGER NOT NULL DEFAULT 0",
        "instinct": "instinct INTEGER NOT NULL DEFAULT 0",
        "stress": "stress INTEGER NOT NULL DEFAULT 0",
        "care_count": "care_count INTEGER NOT NULL DEFAULT 0",
        "consecutive_care_days": "consecutive_care_days INTEGER NOT NULL DEFAULT 0",
        "last_care_date": "last_care_date TEXT DEFAULT NULL",
        "favorite_time_band": "favorite_time_band TEXT DEFAULT NULL",
        "last_state_reason": "last_state_reason TEXT DEFAULT NULL",
    }
    for column_name, column_sql in mini_robot_column_defs.items():
        if column_name not in mini_robot_cols:
            cur.execute(f"ALTER TABLE user_mini_robots ADD COLUMN {column_sql}")
    mini_log_cols = {row[1] for row in cur.execute("PRAGMA table_info(mini_robot_logs)").fetchall()}
    if "payload_json" not in mini_log_cols:
        cur.execute("ALTER TABLE mini_robot_logs ADD COLUMN payload_json TEXT")
    mini_tactics_team_cols = {row[1] for row in cur.execute("PRAGMA table_info(mini_tactics_teams)").fetchall()}
    mini_tactics_team_column_defs = {
        "slot_1_x": "slot_1_x INTEGER NOT NULL DEFAULT 0",
        "slot_1_y": "slot_1_y INTEGER NOT NULL DEFAULT 1",
        "slot_1_ai_type": "slot_1_ai_type TEXT",
        "slot_1_weapon_type": "slot_1_weapon_type TEXT",
        "slot_2_x": "slot_2_x INTEGER NOT NULL DEFAULT 0",
        "slot_2_y": "slot_2_y INTEGER NOT NULL DEFAULT 2",
        "slot_2_ai_type": "slot_2_ai_type TEXT",
        "slot_2_weapon_type": "slot_2_weapon_type TEXT",
        "slot_3_x": "slot_3_x INTEGER NOT NULL DEFAULT 0",
        "slot_3_y": "slot_3_y INTEGER NOT NULL DEFAULT 3",
        "slot_3_ai_type": "slot_3_ai_type TEXT",
        "slot_3_weapon_type": "slot_3_weapon_type TEXT",
    }
    for column_name, column_sql in mini_tactics_team_column_defs.items():
        if column_name not in mini_tactics_team_cols:
            cur.execute(f"ALTER TABLE mini_tactics_teams ADD COLUMN {column_sql}")
    mini_tactics_battle_cols = {row[1] for row in cur.execute("PRAGMA table_info(mini_tactics_battles)").fetchall()}
    mini_tactics_battle_column_defs = {
        "mode": "mode TEXT NOT NULL DEFAULT 'auto_watch'",
        "board_state_json": "board_state_json TEXT",
        "action_log_json": "action_log_json TEXT",
        "current_turn_side": "current_turn_side TEXT",
        "turn_number": "turn_number INTEGER NOT NULL DEFAULT 1",
        "result": "result TEXT",
        "battle_type": "battle_type TEXT NOT NULL DEFAULT 'cpu'",
        "invite_token": "invite_token TEXT",
        "host_user_id": "host_user_id INTEGER",
        "guest_user_id": "guest_user_id INTEGER",
        "host_side": "host_side TEXT",
        "guest_side": "guest_side TEXT",
        "current_turn_user_id": "current_turn_user_id INTEGER",
        "online_status": "online_status TEXT",
        "last_action_at": "last_action_at INTEGER",
        "updated_at": "updated_at INTEGER",
    }
    for column_name, column_sql in mini_tactics_battle_column_defs.items():
        if column_name not in mini_tactics_battle_cols:
            cur.execute(f"ALTER TABLE mini_tactics_battles ADD COLUMN {column_sql}")
    _backfill_mini_robot_internal_fields(cur)
    now_ts = int(time.time())
    cur.execute(
        """
        INSERT OR IGNORE INTO user_mini_robot_profiles (user_id, active_mini_robot_id, updated_at)
        SELECT mr.user_id, MIN(mr.id), ?
        FROM user_mini_robots mr
        GROUP BY mr.user_id
        """,
        (now_ts,),
    )
    cur.execute(
        """
        INSERT OR IGNORE INTO mini_tactics_teams (user_id, slot_1_mini_robot_id, slot_2_mini_robot_id, slot_3_mini_robot_id, updated_at)
        SELECT mr.user_id, MIN(mr.id), NULL, NULL, ?
        FROM user_mini_robots mr
        GROUP BY mr.user_id
        """,
        (now_ts,),
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_world_events_log_user_created ON world_events_log(user_id, created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_world_events_log_request ON world_events_log(request_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_world_events_log_event_type_created ON world_events_log(event_type, created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_room_created ON chat_messages(room_key, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_user_room_created ON chat_messages(user_id, room_key, created_at DESC)")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_portal_online_delivery_queue_status_created ON portal_online_delivery_queue(status, created_at)"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_typing_runs_user_created ON lab_typing_runs(user_id, created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_typing_runs_score_created ON lab_typing_runs(score, created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_typing_runs_weekly ON lab_typing_runs(created_at, score)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_lab_exp_events_user_created ON user_lab_exp_events(user_id, created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_lab_exp_events_action_created ON user_lab_exp_events(action_key, created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_mini_robots_user_created ON user_mini_robots(user_id, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mini_robot_logs_robot_created ON mini_robot_logs(mini_robot_id, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mini_robot_logs_user_created ON mini_robot_logs(user_id, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_mini_robot_profiles_active ON user_mini_robot_profiles(active_mini_robot_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_presence_last_active_at ON user_presence(last_active_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_faction ON users(faction)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_scores_week_points ON world_faction_weekly_scores(week_key, points DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_result_week ON world_faction_weekly_result(week_key)")
    faction_result_cols = {row[1] for row in cur.execute("PRAGMA table_info(world_faction_weekly_result)").fetchall()}
    if "summary_text" not in faction_result_cols:
        cur.execute("ALTER TABLE world_faction_weekly_result ADD COLUMN summary_text TEXT")
    if "highlights_json" not in faction_result_cols:
        cur.execute("ALTER TABLE world_faction_weekly_result ADD COLUMN highlights_json TEXT")
    if "mvp_json" not in faction_result_cols:
        cur.execute("ALTER TABLE world_faction_weekly_result ADD COLUMN mvp_json TEXT")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_contrib_week_faction_points ON world_faction_user_weekly_contributions(week_key, faction, points DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_contrib_user_week ON world_faction_user_weekly_contributions(user_id, week_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_logs_week_faction_created ON world_faction_logs(week_key, faction, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_logs_week_event_created ON world_faction_logs(week_key, event_type, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_mvp_week_category ON world_faction_weekly_mvp(week_key, category)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_awards_week_faction ON faction_weekly_awards(week_key, faction_key, award_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_badges_user_week ON user_faction_badges(user_id, week_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_faction_titles_user_granted ON user_faction_titles(user_id, granted_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_faction_titles_week_faction ON user_faction_titles(week_key, faction_key, title_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_title_logs_week ON faction_title_grant_logs(week_key, title_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_weekly_events_status ON faction_weekly_events(week_key, status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_weekly_event_logs_week ON faction_weekly_event_logs(week_key, action)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_shop_items_active ON faction_shop_items(is_active, sort_order, item_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_shop_items_faction ON faction_shop_items(faction_key, is_active)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_shop_purchases_user ON user_faction_shop_purchases(user_id, purchased_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_equipped_faction_shop_items_user ON user_equipped_faction_shop_items(user_id, slot_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_claims_user_week ON faction_weekly_claims(user_id, week_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_missions_week_active ON faction_weekly_missions(week_key, is_active)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_mission_progress_week ON faction_weekly_mission_progress(week_key, faction_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_reports_week_rank ON faction_weekly_reports(week_key, rank, activity_score DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_guardians_week_faction ON faction_guardians(week_key, faction_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_guardians_submission ON faction_guardians(submission_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_guardian_attacks_week ON faction_guardian_attacks(week_key, attacker_faction_key, target_faction_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_guardian_attacks_event ON faction_guardian_attacks(source_event_type, source_event_id)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_faction_guardian_attacks_request_user ON faction_guardian_attacks(source_event_type, request_id, attacker_user_id) WHERE request_id IS NOT NULL")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_guardian_duels_week ON faction_guardian_duels(week_key, result_status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_facility_contrib_week_faction ON faction_facility_contributions(week_key, faction_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_facility_contrib_user_week ON faction_facility_contributions(user_id, week_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_facility_level_logs_faction_created ON faction_facility_level_logs(faction_key, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_territory_areas_active_order ON faction_territory_areas(is_active, sort_order)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_territory_states_week ON faction_territory_states(week_key, controlling_faction_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_territory_scores_week_area ON faction_territory_scores(week_key, area_key, total_score DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_strategy_votes_week_faction ON faction_strategy_votes(week_key, faction_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_weekly_strategies_week ON faction_weekly_strategies(week_key, faction_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_representatives_week ON faction_representatives(week_key, faction_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_representative_matches_week ON faction_representative_matches(week_key, result_status)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_champ_defeat_records_user_robot ON champ_defeat_records(user_id, champ_robot_id)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_champ_daily_bonus_records_user_day ON champ_daily_bonus_records(user_id, day_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_enemy_dex_user_seen ON user_enemy_dex(user_id, seen_count DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_daily_metrics_day_key ON daily_metrics(day_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_enemies_boss_area_active ON enemies(is_boss, boss_area_key, is_active)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_decor_inventory_user_acquired ON user_decor_inventory(user_id, acquired_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_trophies_user_granted ON user_trophies(user_id, granted_at DESC)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_orders_session_id ON payment_orders(stripe_checkout_session_id)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_orders_event_id ON payment_orders(stripe_event_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_payment_orders_user_created ON payment_orders(user_id, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_payment_orders_status_created ON payment_orders(status, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_robot_history_updated ON robot_history(updated_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_robot_achievements_robot_created ON robot_achievements(robot_id, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_robot_title_unlocks_robot ON robot_title_unlocks(robot_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_showcase_votes_robot_type ON showcase_votes(robot_id, vote_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_showcase_votes_user ON showcase_votes(user_id, vote_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_submissions_status_created ON lab_robot_submissions(status, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_submissions_user_created ON lab_robot_submissions(user_id, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_submissions_featured ON lab_robot_submissions(status, is_featured, approved_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_submissions_adoption ON lab_robot_submissions(status, is_adoption_candidate, adoption_stage, approved_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_submission_likes_submission ON lab_submission_likes(submission_id, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_submission_reports_submission ON lab_submission_reports(submission_id, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_submission_adoptions_submission ON lab_submission_adoptions(submission_id, updated_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_races_status_created ON lab_races(status, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_race_entries_race_order ON lab_race_entries(race_id, entry_order)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_race_records_user_rank ON lab_race_records(user_id, final_rank, finish_time_ms)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_lab_coin ON users(lab_coin DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_market_daily_listings_user_day ON market_daily_listings(user_id, day_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_market_daily_listings_day_slot ON market_daily_listings(day_key, slot_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_market_purchase_history_user_created ON market_purchase_history(user_id, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_market_sell_history_user_created ON market_sell_history(user_id, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_market_refresh_history_user_day ON market_refresh_history(user_id, day_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_casino_races_status_created ON lab_casino_races(status, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_casino_entries_race_lane ON lab_casino_entries(race_id, lane_index)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_casino_bets_user_created ON lab_casino_bets(user_id, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_casino_bets_race ON lab_casino_bets(race_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_casino_frames_race_frame ON lab_casino_frames(race_id, frame_no)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_casino_prizes_active_cost ON lab_casino_prizes(is_active, cost_lab_coin ASC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lab_casino_claims_user_created ON lab_casino_prize_claims(user_id, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_core_inventory_user_core ON user_core_inventory(user_id, core_asset_id)")
    pi_cols = {row[1] for row in cur.execute("PRAGMA table_info(part_instances)").fetchall()}
    if "status" not in pi_cols:
        cur.execute("ALTER TABLE part_instances ADD COLUMN status TEXT NOT NULL DEFAULT 'inventory'")
    if "part_type" not in pi_cols:
        cur.execute("ALTER TABLE part_instances ADD COLUMN part_type TEXT")
    if "updated_at" not in pi_cols:
        cur.execute("ALTER TABLE part_instances ADD COLUMN updated_at TEXT")
    if "r_assist_points" not in pi_cols:
        cur.execute("ALTER TABLE part_instances ADD COLUMN r_assist_points INTEGER NOT NULL DEFAULT 0")
    if "locked" not in pi_cols:
        cur.execute("ALTER TABLE part_instances ADD COLUMN locked INTEGER NOT NULL DEFAULT 0")
    cur.execute("UPDATE part_instances SET status = 'inventory' WHERE status IS NULL OR TRIM(status) = ''")
    cur.execute("UPDATE part_instances SET r_assist_points = 0 WHERE r_assist_points IS NULL OR r_assist_points < 0")
    cur.execute("UPDATE part_instances SET locked = 0 WHERE locked IS NULL OR locked NOT IN (0, 1)")
    cur.execute(
        """
        UPDATE part_instances
        SET part_type = (
            SELECT rp.part_type FROM robot_parts rp WHERE rp.id = part_instances.part_id
        )
        WHERE part_type IS NULL OR part_type = ''
        """
    )
    for key, s in ENEMY_SEED_STATS.items():
        cur.execute(
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
    decor_seed = [
        ("boss_emblem_aurix", "オリクス紋章", "images/factions/aurix.png"),
        ("layer1_clear_emblem_001", "第1層突破エンブレム", "decor/aurix_trophy.png"),
        ("boss_emblem_ventra", "ヴェントラ紋章", "images/factions/ventra.png"),
        ("boss_emblem_ignis", "イグニス紋章", "images/factions/ignis.png"),
        ("fortress_badge_001", "要塞勲章", "decor/fortress_badge_001.png"),
        ("mist_scope_001", "霧界スコープ", "decor/mist_scope_001.png"),
        ("burst_reactor_001", "暴核リアクター", "decor/burst_reactor_001.png"),
        ("judge_halo_001", "審判ハロー", "decor/judge_halo_001.png"),
        ("nyx_array_crest_001", "観測群冠", "decor/nyx_array_crest_001.png"),
        ("ignition_crown_001", "覇走冠", "decor/ignition_crown_001.png"),
        ("omega_frame_halo_001", "終機輪", "decor/omega_frame_halo_001.png"),
        (SUPPORT_PACK_FOUNDER_DECOR_KEY, "創設支援トロフィー", "decor/founder_badge_silver.png"),
        (SUPPORT_PACK_LAB_DECOR_KEY, "ラボ維持支援トロフィー", "decor/lab_badge_gold.png"),
        (LEGACY_SUPPORT_PACK_DECOR_KEY, "旧支援トロフィー", "decor/founder_badge_silver.png"),
    ]
    for key, name_ja, image_path in decor_seed:
        cur.execute(
            """
            INSERT INTO robot_decor_assets (key, name_ja, image_path, is_active, created_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(key) DO UPDATE SET
                name_ja = excluded.name_ja,
                image_path = excluded.image_path
            """,
            (key, name_ja, image_path, int(time.time())),
        )
    support_decor = cur.execute(
        "SELECT id FROM robot_decor_assets WHERE key = ? LIMIT 1",
        (SUPPORT_PACK_FOUNDER_DECOR_KEY,),
    ).fetchone()
    if support_decor:
        cur.execute(
            """
            INSERT OR IGNORE INTO user_decor_inventory (user_id, decor_asset_id, acquired_at)
            SELECT
                po.user_id,
                ?,
                COALESCE(po.granted_at, po.updated_at, po.created_at, ?)
            FROM payment_orders po
            WHERE po.product_key IN (?, ?)
              AND po.user_id IS NOT NULL
              AND po.status IN ('completed', 'granted')
            """,
            (
                int(support_decor[0]),
                int(time.time()),
                LEGACY_SUPPORT_PACK_PRODUCT_KEY,
                SUPPORT_PACK_FOUNDER_PRODUCT_KEY,
            ),
        )
    lab_decor = cur.execute(
        "SELECT id FROM robot_decor_assets WHERE key = ? LIMIT 1",
        (SUPPORT_PACK_LAB_DECOR_KEY,),
    ).fetchone()
    if lab_decor:
        cur.execute(
            """
            INSERT OR IGNORE INTO user_decor_inventory (user_id, decor_asset_id, acquired_at)
            SELECT
                po.user_id,
                ?,
                COALESCE(po.granted_at, po.updated_at, po.created_at, ?)
            FROM payment_orders po
            WHERE po.product_key = ?
              AND po.user_id IS NOT NULL
              AND po.status IN ('completed', 'granted')
            """,
            (int(lab_decor[0]), int(time.time()), SUPPORT_PACK_LAB_PRODUCT_KEY),
        )
    cur.execute(
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
            int(time.time()),
        ),
    )
    now_ts = int(time.time())
    lab_casino_prize_is_active = 1 if LAB_CASINO_PRIZE_EXCHANGE_ENABLED else 0
    for prize_key, name, description, cost_lab_coin, prize_type, grant_key in LAB_CASINO_PRIZE_SEEDS:
        cur.execute(
            """
            INSERT INTO lab_casino_prizes
            (prize_key, name, description, cost_lab_coin, prize_type, grant_key, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(prize_key) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                cost_lab_coin = excluded.cost_lab_coin,
                prize_type = excluded.prize_type,
                grant_key = excluded.grant_key,
                is_active = excluded.is_active,
                updated_at = excluded.updated_at
            """,
            (
                prize_key,
                name,
                description,
                int(cost_lab_coin),
                prize_type,
                grant_key,
                lab_casino_prize_is_active,
                now_ts,
                now_ts,
            ),
        )
    rh_cols = {row[1] for row in cur.execute("PRAGMA table_info(robot_history)").fetchall()}
    if "wins_this_week_key" not in rh_cols:
        cur.execute("ALTER TABLE robot_history ADD COLUMN wins_this_week_key TEXT NOT NULL DEFAULT ''")
    for key, name_ja, desc_ja, sort_order in [
        ("title_boot", "起動", "初組み立てを完了した相棒", 10),
        ("title_deployed", "実戦配備", "勝利数10を達成", 20),
        ("title_first_boss", "初撃破", "ボス初撃破を達成", 30),
    ]:
        cur.execute(
            """
            INSERT INTO robot_titles (key, name_ja, desc_ja, sort_order, is_active)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(key) DO UPDATE SET
                name_ja = excluded.name_ja,
                desc_ja = excluded.desc_ja,
                sort_order = excluded.sort_order,
                is_active = 1
            """,
            (key, name_ja, desc_ja, sort_order),
        )
    count = cur.execute("SELECT COUNT(*) FROM robots_master").fetchone()[0]
    if count == 0:
        cur.executemany(
            "INSERT INTO robots_master (head, right_arm, left_arm, legs, name, rarity, type, flavor_text, attack, defense, rarity_bonus) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            robots_seed,
        )
    base_count = cur.execute("SELECT COUNT(*) FROM robot_bases").fetchone()[0]
    if base_count == 0:
        cur.executemany(
            "INSERT INTO robot_bases (key, image_path) VALUES (?, ?)",
            [
                ("normal", "base_bodies/normal.png"),
                ("angel", "base_bodies/angel.png"),
                ("devil", "base_bodies/devil.png"),
            ],
        )
    _ensure_default_normal_robot_parts(cur)
    _upsert_series_rows(cur)
    _apply_series_part_assignments(cur)
    milestone_count = cur.execute("SELECT COUNT(*) FROM robot_milestones").fetchone()[0]
    if milestone_count == 0:
        cur.executemany(
            """
            INSERT INTO robot_milestones
            (milestone_key, metric, threshold_value, reward_head_key, reward_r_arm_key, reward_l_arm_key, reward_legs_key, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            [
                ("wins_3", "wins", 3, "head_1", "r_arm_1", "l_arm_1", "legs_1"),
                ("wins_10", "wins", 10, "head_2", "r_arm_2", "l_arm_2", "legs_2"),
            ],
        )
    bb_count = cur.execute("SELECT COUNT(*) FROM base_bodies").fetchone()[0]
    if bb_count == 0:
        cur.executemany(
            "INSERT INTO base_bodies (name, sprite_path) VALUES (?, ?)",
            [
                ("normal", "base_bodies/normal.png"),
                ("angel", "base_bodies/angel.png"),
                ("devil", "base_bodies/devil.png"),
            ],
        )
    part_count = cur.execute("SELECT COUNT(*) FROM parts").fetchone()[0]
    if part_count == 0:
        items = []
        for i in range(1, 11):
            items.append((f"HEAD-{i}", "HEAD", f"parts/head/{i}.png", 2, 1, 1, 3))
            items.append((f"R-ARM-{i}", "RIGHT_ARM", f"parts/right_arm/{i}.png", 2, 1, 1, 2))
            items.append((f"L-ARM-{i}", "LEFT_ARM", f"parts/left_arm/{i}.png", 2, 1, 1, 2))
            items.append((f"LEGS-{i}", "LEGS", f"parts/legs/{i}.png", 1, 2, 2, 3))
        cur.executemany(
            "INSERT INTO parts (name, type, sprite_path, attack, defense, speed, hp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            items,
        )

    conn.commit()
    conn.close()
    print("DB initialized at", DB_PATH)


if __name__ == "__main__":
    main()
