import os
import sqlite3
import time
from balance_config import ENEMY_SEED_STATS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "game.db")
EVOLUTION_CORE_KEY = "evolution_core"

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
            is_banned INTEGER NOT NULL DEFAULT 0,
            is_admin_protected INTEGER NOT NULL DEFAULT 0,
            banned_at TEXT,
            banned_reason TEXT,
            banned_by_user_id INTEGER,
            has_seen_intro_modal INTEGER NOT NULL DEFAULT 0,
            intro_guide_closed_at TEXT,
            last_explore_area_key TEXT,
            explore_boost_until INTEGER NOT NULL DEFAULT 0,
            evolution_core_progress INTEGER NOT NULL DEFAULT 0,
            home_beginner_mission_hidden INTEGER NOT NULL DEFAULT 0,
            home_next_action_collapsed INTEGER NOT NULL DEFAULT 0,
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
            display_name_ja TEXT,
            offset_x INTEGER NOT NULL DEFAULT 0,
            offset_y INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            is_unlocked INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL
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
            style_key TEXT NOT NULL DEFAULT 'stable',
            style_stats_json TEXT NOT NULL DEFAULT '{}',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
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
            status TEXT NOT NULL DEFAULT 'inventory',
            created_at INTEGER NOT NULL,
            FOREIGN KEY (part_id) REFERENCES robot_parts(id),
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
    udi_cols = {row[1] for row in cur.execute("PRAGMA table_info(user_decor_inventory)").fetchall()}
    if "acquired_at" not in udi_cols:
        cur.execute("ALTER TABLE user_decor_inventory ADD COLUMN acquired_at INTEGER")
        if "created_at" in udi_cols:
            cur.execute("UPDATE user_decor_inventory SET acquired_at = created_at WHERE acquired_at IS NULL")
        cur.execute("UPDATE user_decor_inventory SET acquired_at = ? WHERE acquired_at IS NULL", (int(time.time()),))
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

    users_cols = {row[1] for row in cur.execute("PRAGMA table_info(users)").fetchall()}
    if "avatar_path" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN avatar_path TEXT")
    if "active_robot_id" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN active_robot_id INTEGER")
    if "stable_no_damage_wins" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN stable_no_damage_wins INTEGER NOT NULL DEFAULT 0")
    if "burst_crit_finisher_kills" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN burst_crit_finisher_kills INTEGER NOT NULL DEFAULT 0")
    if "desperate_low_hp_wins" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN desperate_low_hp_wins INTEGER NOT NULL DEFAULT 0")
    if "faction" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN faction TEXT")
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
    if "home_beginner_mission_hidden" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN home_beginner_mission_hidden INTEGER NOT NULL DEFAULT 0")
    if "home_next_action_collapsed" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN home_next_action_collapsed INTEGER NOT NULL DEFAULT 0")
    cur.execute(
        "UPDATE users SET faction = NULL WHERE faction IS NOT NULL AND LOWER(TRIM(faction)) NOT IN ('ignis','ventra','aurix')"
    )
    cur.execute("UPDATE users SET is_banned = 0 WHERE is_banned IS NULL")
    cur.execute("UPDATE users SET is_admin_protected = 0 WHERE is_admin_protected IS NULL")
    cur.execute("UPDATE users SET banned_at = NULL WHERE banned_at IS NOT NULL AND TRIM(banned_at) = ''")
    cur.execute("UPDATE users SET banned_reason = NULL WHERE banned_reason IS NOT NULL AND TRIM(banned_reason) = ''")
    cur.execute("UPDATE users SET has_seen_intro_modal = 0 WHERE has_seen_intro_modal IS NULL")
    cur.execute("UPDATE users SET intro_guide_closed_at = NULL WHERE intro_guide_closed_at IS NOT NULL AND TRIM(intro_guide_closed_at) = ''")
    cur.execute("UPDATE users SET last_explore_area_key = NULL WHERE last_explore_area_key IS NOT NULL AND TRIM(last_explore_area_key) = ''")
    cur.execute("UPDATE users SET explore_boost_until = 0 WHERE explore_boost_until IS NULL")
    cur.execute("UPDATE users SET home_beginner_mission_hidden = 0 WHERE home_beginner_mission_hidden IS NULL")
    cur.execute("UPDATE users SET home_next_action_collapsed = 0 WHERE home_next_action_collapsed IS NULL")
    cur.execute("UPDATE users SET is_admin_protected = 1 WHERE is_admin = 1")
    ri_cols = {row[1] for row in cur.execute("PRAGMA table_info(robot_instances)").fetchall()}
    if "personality" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN personality TEXT")
    if "icon_32_path" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN icon_32_path TEXT")
    if "combat_mode" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN combat_mode TEXT NOT NULL DEFAULT 'normal'")
    if "is_public" not in ri_cols:
        cur.execute("ALTER TABLE robot_instances ADD COLUMN is_public INTEGER NOT NULL DEFAULT 1")
    cur.execute("UPDATE robot_instances SET combat_mode = 'normal' WHERE combat_mode IS NULL OR combat_mode = ''")
    cur.execute("UPDATE robot_instances SET is_public = 1 WHERE is_public IS NULL")
    rp_cols = {row[1] for row in cur.execute("PRAGMA table_info(robot_parts)").fetchall()}
    if "rarity" not in rp_cols:
        cur.execute("ALTER TABLE robot_parts ADD COLUMN rarity TEXT")
    if "is_active" not in rp_cols:
        cur.execute("ALTER TABLE robot_parts ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
    if "element" not in rp_cols:
        cur.execute("ALTER TABLE robot_parts ADD COLUMN element TEXT")
    if "series" not in rp_cols:
        cur.execute("ALTER TABLE robot_parts ADD COLUMN series TEXT")
    if "display_name_ja" not in rp_cols:
        cur.execute("ALTER TABLE robot_parts ADD COLUMN display_name_ja TEXT")
    cur.execute("UPDATE robot_parts SET rarity = 'N' WHERE rarity IS NULL OR rarity = ''")
    cur.execute("UPDATE robot_parts SET element = 'NORMAL' WHERE element IS NULL OR element = ''")
    cur.execute("UPDATE robot_parts SET series = 'S1' WHERE series IS NULL OR series = ''")
    cur.execute("UPDATE robot_parts SET is_active = 1 WHERE is_active IS NULL")
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
    cur.execute("UPDATE enemies SET boss_area_key = NULL WHERE boss_area_key NOT IN ('layer_1', 'layer_2', 'layer_3')")
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
    cur.execute("CREATE INDEX IF NOT EXISTS idx_world_events_log_user_created ON world_events_log(user_id, created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_world_events_log_request ON world_events_log(request_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_world_events_log_event_type_created ON world_events_log(event_type, created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_room_created ON chat_messages(room_key, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_user_room_created ON chat_messages(user_id, room_key, created_at DESC)")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_portal_online_delivery_queue_status_created ON portal_online_delivery_queue(status, created_at)"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_faction ON users(faction)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_scores_week_points ON world_faction_weekly_scores(week_key, points DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faction_result_week ON world_faction_weekly_result(week_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_enemy_dex_user_seen ON user_enemy_dex(user_id, seen_count DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_daily_metrics_day_key ON daily_metrics(day_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_enemies_boss_area_active ON enemies(is_boss, boss_area_key, is_active)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_decor_inventory_user_acquired ON user_decor_inventory(user_id, acquired_at)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_orders_session_id ON payment_orders(stripe_checkout_session_id)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_orders_event_id ON payment_orders(stripe_event_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_payment_orders_user_created ON payment_orders(user_id, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_payment_orders_status_created ON payment_orders(status, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_robot_history_updated ON robot_history(updated_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_robot_achievements_robot_created ON robot_achievements(robot_id, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_robot_title_unlocks_robot ON robot_title_unlocks(robot_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_showcase_votes_robot_type ON showcase_votes(robot_id, vote_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_showcase_votes_user ON showcase_votes(user_id, vote_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_core_inventory_user_core ON user_core_inventory(user_id, core_asset_id)")
    pi_cols = {row[1] for row in cur.execute("PRAGMA table_info(part_instances)").fetchall()}
    if "part_type" not in pi_cols:
        cur.execute("ALTER TABLE part_instances ADD COLUMN part_type TEXT")
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
        ("boss_emblem_ventra", "ヴェントラ紋章", "images/factions/ventra.png"),
        ("boss_emblem_ignis", "イグニス紋章", "images/factions/ignis.png"),
        ("supporter_emblem_001", "支援者トロフィー", "decor/aurix_trophy.png"),
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
    parts_count = cur.execute("SELECT COUNT(*) FROM robot_parts").fetchone()[0]
    if parts_count == 0:
        now = int(time.time())
        items = []
        for i in range(1, 11):
            items.append(("HEAD", f"head_{i}", f"parts/head/{i}.png", "N", "NORMAL", "S1", 0, 0, now))
            items.append(("RIGHT_ARM", f"r_arm_{i}", f"parts/right_arm/{i}.png", "N", "NORMAL", "S1", 0, 0, now))
            items.append(("LEFT_ARM", f"l_arm_{i}", f"parts/left_arm/{i}.png", "N", "NORMAL", "S1", 0, 0, now))
            items.append(("LEGS", f"legs_{i}", f"parts/legs/{i}.png", "N", "NORMAL", "S1", 0, 0, now))
        cur.executemany(
            "INSERT INTO robot_parts (part_type, key, image_path, rarity, element, series, offset_x, offset_y, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            items,
        )
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
