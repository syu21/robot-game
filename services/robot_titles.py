import time


TITLE_MASTER_DEFS = (
    {
        "key": "style_stable",
        "name_ja": "安定型",
        "description": "耐久・防御・命中を中心に育った機体。",
        "category": "style",
        "rarity": 1,
        "icon_key": "shield",
        "color_key": "cyan",
        "unlock_scope": "robot",
        "sort_order": 300,
    },
    {
        "key": "style_burst",
        "name_ja": "爆発型",
        "description": "攻撃・会心を中心に育った機体。",
        "category": "style",
        "rarity": 1,
        "icon_key": "spark",
        "color_key": "purple",
        "unlock_scope": "robot",
        "sort_order": 310,
    },
    {
        "key": "style_berserk",
        "name_ja": "背水型",
        "description": "低耐久・高火力で逆転を狙う機体。",
        "category": "style",
        "rarity": 1,
        "icon_key": "core",
        "color_key": "red",
        "unlock_scope": "robot",
        "sort_order": 320,
    },
    {
        "key": "boss_hunter_01",
        "name_ja": "ボスハンター",
        "description": "ボス撃破累計3体を達成した機体。",
        "category": "battle",
        "rarity": 2,
        "icon_key": "boss",
        "color_key": "orange",
        "unlock_scope": "robot",
        "sort_order": 120,
    },
    {
        "key": "champion_breaker",
        "name_ja": "チャンプブレイカー",
        "description": "今週のチャンプ機体を撃破した機体。",
        "category": "battle",
        "rarity": 5,
        "icon_key": "crown_break",
        "color_key": "gold",
        "unlock_scope": "robot",
        "sort_order": 10,
    },
    {
        "key": "deep_layer_04",
        "name_ja": "審判越え",
        "description": "第4層の最終試験を突破した機体。",
        "category": "battle",
        "rarity": 4,
        "icon_key": "layer4",
        "color_key": "gold",
        "unlock_scope": "robot",
        "sort_order": 80,
    },
    {
        "key": "deep_layer_05",
        "name_ja": "完成域到達者",
        "description": "第5層の最終試験を突破した機体。",
        "category": "battle",
        "rarity": 5,
        "icon_key": "layer5",
        "color_key": "gold",
        "unlock_scope": "robot",
        "sort_order": 70,
    },
    {
        "key": "enhance_plus_5",
        "name_ja": "強化職人",
        "description": "いずれかの部位で+5強化を達成した機体。",
        "category": "growth",
        "rarity": 2,
        "icon_key": "plus",
        "color_key": "green",
        "unlock_scope": "robot",
        "sort_order": 180,
    },
    {
        "key": "evolve_first",
        "name_ja": "進化研究者",
        "description": "初めて進化パーツを組み込んだ機体。",
        "category": "growth",
        "rarity": 2,
        "icon_key": "evolve",
        "color_key": "mint",
        "unlock_scope": "robot",
        "sort_order": 170,
    },
    {
        "key": "evolve_full_set",
        "name_ja": "完成研究機",
        "description": "全4部位をR相当以上で構成した機体。",
        "category": "growth",
        "rarity": 3,
        "icon_key": "full_set",
        "color_key": "mint",
        "unlock_scope": "robot",
        "sort_order": 160,
    },
    {
        "key": "record_updater",
        "name_ja": "記録更新者",
        "description": "週間記録を更新した機体。",
        "category": "record",
        "rarity": 3,
        "icon_key": "record",
        "color_key": "purple",
        "unlock_scope": "robot",
        "sort_order": 40,
    },
    {
        "key": "mvp_weekly",
        "name_ja": "今週の顔",
        "description": "今週のMVPとして観測された機体。",
        "category": "record",
        "rarity": 4,
        "icon_key": "mvp",
        "color_key": "gold",
        "unlock_scope": "robot",
        "sort_order": 20,
    },
    {
        "key": "weekly_rank_top",
        "name_ja": "首位研究機",
        "description": "週間ランキング首位に立った機体。",
        "category": "record",
        "rarity": 4,
        "icon_key": "rank",
        "color_key": "purple",
        "unlock_scope": "robot",
        "sort_order": 30,
    },
    {
        "key": "supporter",
        "name_ja": "ラボ支援者",
        "description": "ラボ支援者の出撃機体。",
        "category": "support",
        "rarity": 1,
        "icon_key": "crown",
        "color_key": "crown_gold",
        "unlock_scope": "user",
        "sort_order": 500,
    },
    {
        "key": "supporter_plus",
        "name_ja": "ラボ支援者+",
        "description": "継続してラボを支えている研究員の印。",
        "category": "support",
        "rarity": 2,
        "icon_key": "crown_plus",
        "color_key": "crown_gold",
        "unlock_scope": "user",
        "sort_order": 510,
    },
    {
        "key": "supporter_star",
        "name_ja": "ラボ支援者★",
        "description": "常連支援者の印。",
        "category": "support",
        "rarity": 3,
        "icon_key": "crown_star",
        "color_key": "crown_gold",
        "unlock_scope": "user",
        "sort_order": 520,
    },
)

TITLE_MASTER_BY_KEY = {row["key"]: dict(row) for row in TITLE_MASTER_DEFS}
STYLE_TITLE_MAP = {
    "stable": "style_stable",
    "burst": "style_burst",
    "desperate": "style_berserk",
    "berserk": "style_berserk",
}
PRIMARY_TITLE_PRIORITY = {
    "champion_breaker": 10,
    "mvp_weekly": 20,
    "record_updater": 30,
    "weekly_rank_top": 35,
    "deep_layer_05": 40,
    "deep_layer_04": 50,
    "boss_hunter_01": 60,
    "evolve_full_set": 70,
    "enhance_plus_5": 80,
    "evolve_first": 90,
    "style_stable": 300,
    "style_burst": 300,
    "style_berserk": 300,
    "supporter": 500,
    "supporter_plus": 510,
    "supporter_star": 520,
}
TITLE_DECOR_MAP = {
    "champion_breaker": "ignition_crown_001",
    "style_stable": "judge_halo_001",
    "style_burst": "burst_reactor_001",
    "style_berserk": "ignition_crown_001",
}
RARITY_ORDER = {"N": 1, "R": 2, "SR": 3, "SSR": 4, "UR": 5}
_ENSURED_DB_KEYS = set()


def _db_cache_key(db):
    try:
        rows = db.execute("PRAGMA database_list").fetchall()
        parts = []
        for row in rows:
            try:
                parts.append(str(row["file"] or ""))
            except Exception:
                parts.append(str(row[2] or ""))
        return "|".join(parts) or str(id(db))
    except Exception:
        return str(id(db))


def _columns(db, table_name):
    rows = db.execute(f"PRAGMA table_info({table_name})").fetchall()
    cols = set()
    for row in rows:
        try:
            cols.add(str(row["name"]))
        except Exception:
            cols.add(str(row[1]))
    return cols


def ensure_robot_title_system(db):
    cache_key = _db_cache_key(db)
    if cache_key in _ENSURED_DB_KEYS:
        return
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS titles_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            name_ja TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL,
            rarity INTEGER NOT NULL DEFAULT 1,
            icon_key TEXT NOT NULL DEFAULT '',
            color_key TEXT NOT NULL DEFAULT '',
            unlock_scope TEXT NOT NULL DEFAULT 'robot',
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_title_grants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            robot_id INTEGER NOT NULL,
            title_key TEXT NOT NULL,
            source_event TEXT NOT NULL DEFAULT '',
            source_entity_type TEXT NOT NULL DEFAULT '',
            source_entity_id INTEGER,
            acquired_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            is_featured INTEGER NOT NULL DEFAULT 0,
            UNIQUE(robot_id, title_key)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_titles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title_key TEXT NOT NULL,
            acquired_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            is_equipped INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, title_key)
        )
        """
    )
    ri_cols = _columns(db, "robot_instances")
    has_robot_instances = bool(ri_cols)
    if has_robot_instances:
        if "primary_title_key" not in ri_cols:
            db.execute("ALTER TABLE robot_instances ADD COLUMN primary_title_key TEXT")
        if "style_title_key" not in ri_cols:
            db.execute("ALTER TABLE robot_instances ADD COLUMN style_title_key TEXT")
        if "honor_title_key" not in ri_cols:
            db.execute("ALTER TABLE robot_instances ADD COLUMN honor_title_key TEXT")
    db.execute("CREATE INDEX IF NOT EXISTS idx_titles_master_active_sort ON titles_master(is_active, sort_order)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_robot_title_grants_robot ON robot_title_grants(robot_id, acquired_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_robot_title_grants_title ON robot_title_grants(title_key)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_user_titles_user ON user_titles(user_id, acquired_at DESC)")
    seed_title_master(db)
    if has_robot_instances:
        _ENSURED_DB_KEYS.add(cache_key)


def seed_title_master(db):
    for row in TITLE_MASTER_DEFS:
        db.execute(
            """
            INSERT INTO titles_master
                (key, name_ja, description, category, rarity, icon_key, color_key,
                 unlock_scope, sort_order, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(key) DO UPDATE SET
                name_ja = excluded.name_ja,
                description = excluded.description,
                category = excluded.category,
                rarity = excluded.rarity,
                icon_key = excluded.icon_key,
                color_key = excluded.color_key,
                unlock_scope = excluded.unlock_scope,
                sort_order = excluded.sort_order,
                is_active = 1
            """,
            (
                row["key"],
                row["name_ja"],
                row["description"],
                row["category"],
                int(row["rarity"]),
                row["icon_key"],
                row["color_key"],
                row["unlock_scope"],
                int(row["sort_order"]),
            ),
        )


def _title_row(db, title_key):
    key = str(title_key or "").strip()
    if not key:
        return None
    ensure_robot_title_system(db)
    row = db.execute(
        """
        SELECT key, name_ja, description, category, rarity, icon_key, color_key,
               unlock_scope, sort_order, is_active
        FROM titles_master
        WHERE key = ? AND is_active = 1
        """,
        (key,),
    ).fetchone()
    if row:
        return dict(row)
    fallback = TITLE_MASTER_BY_KEY.get(key)
    return dict(fallback) if fallback else None


def title_view(db, title_key):
    row = _title_row(db, title_key)
    if not row:
        return None
    category = str(row.get("category") or "").strip() or "honor"
    color_key = str(row.get("color_key") or category).strip() or category
    return {
        "key": str(row.get("key") or ""),
        "label": str(row.get("name_ja") or row.get("key") or ""),
        "name_ja": str(row.get("name_ja") or row.get("key") or ""),
        "description": str(row.get("description") or ""),
        "category": category,
        "rarity": int(row.get("rarity") or 1),
        "icon_key": str(row.get("icon_key") or ""),
        "color_key": color_key,
        "class_name": f"is-{category} is-{color_key}",
    }


def _title_priority(title_key):
    key = str(title_key or "")
    if key in PRIMARY_TITLE_PRIORITY:
        return int(PRIMARY_TITLE_PRIORITY[key])
    row = TITLE_MASTER_BY_KEY.get(key) or {}
    return int(row.get("sort_order") or 9999)


def _grant_title_decor_if_available(db, *, robot_id, title_key):
    decor_key = TITLE_DECOR_MAP.get(str(title_key or ""))
    if not decor_key:
        return
    robot = db.execute("SELECT user_id FROM robot_instances WHERE id = ?", (int(robot_id),)).fetchone()
    if not robot:
        return
    decor = db.execute("SELECT id FROM robot_decor_assets WHERE key = ? AND is_active = 1", (decor_key,)).fetchone()
    if not decor:
        return
    db.execute(
        """
        INSERT OR IGNORE INTO user_decor_inventory (user_id, decor_asset_id, acquired_at)
        VALUES (?, ?, ?)
        """,
        (int(robot["user_id"]), int(decor["id"]), int(time.time())),
    )


def _granted_title_rows(db, robot_id):
    ensure_robot_title_system(db)
    return [
        dict(row)
        for row in db.execute(
            """
            SELECT rtg.robot_id, rtg.title_key, rtg.acquired_at, rtg.is_featured,
                   tm.name_ja, tm.description, tm.category, tm.rarity, tm.icon_key,
                   tm.color_key, tm.sort_order
            FROM robot_title_grants rtg
            JOIN titles_master tm ON tm.key = rtg.title_key AND tm.is_active = 1
            WHERE rtg.robot_id = ?
            ORDER BY rtg.is_featured DESC, tm.sort_order ASC, rtg.acquired_at DESC
            """,
            (int(robot_id),),
        ).fetchall()
    ]


def recompute_robot_titles(db, robot_id):
    ensure_robot_title_system(db)
    rid = int(robot_id or 0)
    if rid <= 0:
        return None
    rows = _granted_title_rows(db, rid)
    primary_key = ""
    style_key = ""
    honor_key = ""
    if rows:
        ordered = sorted(
            rows,
            key=lambda row: (
                _title_priority(row.get("title_key")),
                -int(row.get("rarity") or 1),
                -int(row.get("acquired_at") or 0),
                str(row.get("title_key") or ""),
            ),
        )
        primary_key = str(ordered[0].get("title_key") or "")
        style_rows = [row for row in rows if str(row.get("category") or "") == "style"]
        if style_rows:
            style_key = str(sorted(style_rows, key=lambda row: -int(row.get("acquired_at") or 0))[0].get("title_key") or "")
        honor_rows = [row for row in ordered if str(row.get("category") or "") not in {"style", "support"}]
        if honor_rows:
            honor_key = str(honor_rows[0].get("title_key") or "")
    db.execute("UPDATE robot_title_grants SET is_featured = 0 WHERE robot_id = ?", (rid,))
    if primary_key:
        db.execute(
            "UPDATE robot_title_grants SET is_featured = 1 WHERE robot_id = ? AND title_key = ?",
            (rid, primary_key),
        )
    db.execute(
        """
        UPDATE robot_instances
        SET primary_title_key = ?, style_title_key = ?, honor_title_key = ?
        WHERE id = ?
        """,
        (primary_key or None, style_key or None, honor_key or None, rid),
    )
    return primary_key or None


def grant_robot_title(
    db,
    robot_id,
    title_key,
    *,
    source_event="",
    source_entity_type="",
    source_entity_id=None,
    acquired_at=None,
):
    ensure_robot_title_system(db)
    rid = int(robot_id or 0)
    key = str(title_key or "").strip()
    if rid <= 0 or not key or not _title_row(db, key):
        return False
    robot = db.execute("SELECT id FROM robot_instances WHERE id = ?", (rid,)).fetchone()
    if not robot:
        return False
    cur = db.execute(
        """
        INSERT OR IGNORE INTO robot_title_grants
            (robot_id, title_key, source_event, source_entity_type, source_entity_id, acquired_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            rid,
            key,
            str(source_event or ""),
            str(source_entity_type or ""),
            int(source_entity_id) if source_entity_id is not None else None,
            int(acquired_at or time.time()),
        ),
    )
    inserted = int(getattr(cur, "rowcount", 0) or 0) > 0
    if inserted:
        _grant_title_decor_if_available(db, robot_id=rid, title_key=key)
    recompute_robot_titles(db, rid)
    return inserted


def sync_style_title_for_robot(db, robot_id, thought_key, *, source_event="style_detected"):
    key = STYLE_TITLE_MAP.get(str(thought_key or "").strip().lower())
    if not key:
        return False
    changed = grant_robot_title(db, robot_id, key, source_event=source_event)
    db.execute(
        "UPDATE robot_instances SET style_title_key = ? WHERE id = ?",
        (key, int(robot_id)),
    )
    return changed


def _robot_full_r_set(db, robot_id):
    row = db.execute(
        """
        SELECT head_key, r_arm_key, l_arm_key, legs_key
        FROM robot_instance_parts
        WHERE robot_instance_id = ?
        """,
        (int(robot_id),),
    ).fetchone()
    if not row:
        return False
    keys = [row["head_key"], row["r_arm_key"], row["l_arm_key"], row["legs_key"]]
    if not all(keys):
        return False
    part_rows = db.execute(
        f"""
        SELECT key, rarity
        FROM robot_parts
        WHERE key IN ({','.join(['?'] * len(keys))})
        """,
        keys,
    ).fetchall()
    rarity_by_key = {str(part["key"]): str(part["rarity"] or "N").upper() for part in part_rows}
    return all(RARITY_ORDER.get(rarity_by_key.get(str(key), "N"), 1) >= RARITY_ORDER["R"] for key in keys)


def sync_growth_titles_for_robot(db, robot_id, *, plus_value=None, evolved=False, source_entity_id=None):
    rid = int(robot_id or 0)
    if rid <= 0:
        return []
    granted = []
    if plus_value is not None and int(plus_value or 0) >= 5:
        if grant_robot_title(
            db,
            rid,
            "enhance_plus_5",
            source_event="fuse",
            source_entity_type="part_instance",
            source_entity_id=source_entity_id,
        ):
            granted.append("enhance_plus_5")
    if evolved:
        if grant_robot_title(
            db,
            rid,
            "evolve_first",
            source_event="part_evolve",
            source_entity_type="part_instance",
            source_entity_id=source_entity_id,
        ):
            granted.append("evolve_first")
        if _robot_full_r_set(db, rid) and grant_robot_title(
            db,
            rid,
            "evolve_full_set",
            source_event="part_evolve",
            source_entity_type="robot_instance",
            source_entity_id=rid,
        ):
            granted.append("evolve_full_set")
    return granted


def sync_progress_titles_for_robot(db, robot_id, *, area_key="", source_entity_id=None):
    rid = int(robot_id or 0)
    if rid <= 0:
        return []
    granted = []
    history = db.execute(
        "SELECT boss_defeats_total FROM robot_history WHERE robot_id = ?",
        (rid,),
    ).fetchone()
    if history and int(history["boss_defeats_total"] or 0) >= 3:
        if grant_robot_title(db, rid, "boss_hunter_01", source_event="boss_defeat"):
            granted.append("boss_hunter_01")
    area = str(area_key or "").strip().lower()
    if area.startswith("layer_5"):
        if grant_robot_title(
            db,
            rid,
            "deep_layer_05",
            source_event="boss_defeat",
            source_entity_type="enemy",
            source_entity_id=source_entity_id,
        ):
            granted.append("deep_layer_05")
    elif area.startswith("layer_4"):
        if grant_robot_title(
            db,
            rid,
            "deep_layer_04",
            source_event="boss_defeat",
            source_entity_type="enemy",
            source_entity_id=source_entity_id,
        ):
            granted.append("deep_layer_04")
    return granted


def robot_title_summary(db, robot_id, *, limit=8):
    rid = int(robot_id or 0)
    if rid <= 0:
        return {"primary": None, "style": None, "honor": None, "titles": []}
    ensure_robot_title_system(db)
    robot = db.execute(
        "SELECT primary_title_key, style_title_key, honor_title_key FROM robot_instances WHERE id = ?",
        (rid,),
    ).fetchone()
    if not robot:
        return {"primary": None, "style": None, "honor": None, "titles": []}
    if not robot["primary_title_key"]:
        recompute_robot_titles(db, rid)
        robot = db.execute(
            "SELECT primary_title_key, style_title_key, honor_title_key FROM robot_instances WHERE id = ?",
            (rid,),
        ).fetchone()
    rows = _granted_title_rows(db, rid)
    titles = []
    for row in rows[: max(1, int(limit or 8))]:
        view = title_view(db, row.get("title_key"))
        if view:
            view["acquired_at"] = int(row.get("acquired_at") or 0)
            view["is_featured"] = bool(row.get("is_featured"))
            titles.append(view)
    return {
        "primary": title_view(db, robot["primary_title_key"] if robot else None),
        "style": title_view(db, robot["style_title_key"] if robot else None),
        "honor": title_view(db, robot["honor_title_key"] if robot else None),
        "titles": titles,
    }


def robot_story_suffix(db, robot_id):
    summary = robot_title_summary(db, robot_id, limit=2)
    labels = []
    style = summary.get("style")
    primary = summary.get("primary")
    if style:
        labels.append(style["label"])
    if primary and primary.get("key") != (style or {}).get("key"):
        labels.append(primary["label"])
    if not labels:
        return ""
    return f"（{'・'.join(labels[:2])}）"
