import random


LAB_RACE_ENTRY_COUNT = 6
LAB_RACE_SEGMENT_COUNT = 10
LAB_RACE_GOAL = 100.0


LAB_RACE_COURSE_ALIASES = {
    "scrapyard_dash": "scrapyard_sprint",
}


LAB_RACE_COURSES = {
    "scrapyard_sprint": {
        "key": "scrapyard_sprint",
        "label": "スクラップスプリント",
        "summary": "通常路の中に数個だけ特殊障害物が混ざる、見やすさ優先の標準コース。",
        "hidden": 0,
        "normal_theme": "normal",
        "normal_badge": "RUN",
    },
    "gravity_lane": {
        "key": "gravity_lane",
        "label": "グラビティレーン",
        "summary": "磁気ノイズ寄りの配色で見せる、変則感のある標準コース。",
        "hidden": 0,
        "normal_theme": "noise",
        "normal_badge": "RUN",
    },
    "casino_scrapyard_cup": {
        "key": "casino_scrapyard_cup",
        "label": "スクラップ杯",
        "summary": "6体の中から1体を選んで、レースの行方を見届けよう。",
        "hidden": 1,
        "normal_theme": "normal",
        "normal_badge": "RUN",
    },
}


LAB_RACE_SPECIAL_COUNT_WEIGHTS = (
    (3, 0.60),
    (4, 0.25),
    (2, 0.10),
    (5, 0.05),
)


LAB_RACE_OBSTACLE_MASTER = (
    {
        "key": "boost_pad",
        "label": "コンベア加速帯",
        "short_label": "加速",
        "badge": "BOOST",
        "category": "boost",
        "theme": "boost",
        "color": "#f2b44c",
        "short_desc": "速度上昇",
        "effect_params": {"pace": 0.12, "chaos": 0.06, "dash_bias": 0.05},
        "weight": 1.0,
    },
    {
        "key": "oil_slick",
        "label": "オイル漏れ地帯",
        "short_label": "オイル",
        "badge": "OIL",
        "category": "slow",
        "theme": "oil",
        "color": "#26323f",
        "short_desc": "減速 + スリップ",
        "effect_params": {"pace": -0.03, "chaos": 0.18, "dash_bias": 0.0},
        "weight": 1.0,
    },
    {
        "key": "barrier_spin",
        "label": "回転アーム区画",
        "short_label": "アーム",
        "badge": "ARM",
        "category": "hazard",
        "theme": "hazard",
        "color": "#be5d48",
        "short_desc": "転倒判定",
        "effect_params": {"pace": -0.04, "chaos": 0.28, "dash_bias": 0.0},
        "weight": 1.0,
    },
    {
        "key": "warp_gate",
        "label": "ワープゲート",
        "short_label": "ワープ",
        "badge": "WARP",
        "category": "chaos",
        "theme": "jump",
        "color": "#55d3ea",
        "short_desc": "大きな位置変動",
        "effect_params": {"pace": 0.05, "chaos": 0.24, "dash_bias": 0.08},
        "weight": 0.8,
    },
    {
        "key": "slow_zone",
        "label": "スクラップ散乱地帯",
        "short_label": "スクラップ",
        "badge": "SCRAP",
        "category": "slow",
        "theme": "scrap",
        "color": "#b58f63",
        "short_desc": "小減速",
        "effect_params": {"pace": -0.04, "chaos": 0.12, "dash_bias": 0.0},
        "weight": 1.0,
    },
    {
        "key": "pitfall",
        "label": "落下ピット",
        "short_label": "ピット",
        "badge": "PIT",
        "category": "hazard",
        "theme": "core",
        "color": "#62a26a",
        "short_desc": "落下で大きく減速",
        "effect_params": {"pace": 0.02, "chaos": 0.30, "dash_bias": 0.02},
        "weight": 0.8,
    },
    {
        "key": "magnet_field",
        "label": "磁気乱流帯",
        "short_label": "磁気",
        "badge": "MAG",
        "category": "chaos",
        "theme": "noise",
        "color": "#6d8bff",
        "short_desc": "引き寄せ / 押し戻し",
        "effect_params": {"pace": -0.01, "chaos": 0.20, "dash_bias": 0.03},
        "weight": 0.7,
    },
    {
        "key": "shock_gate",
        "label": "ショックゲート",
        "short_label": "ショック",
        "badge": "SHOCK",
        "category": "hazard",
        "theme": "hazard",
        "color": "#f69b61",
        "short_desc": "一時停止",
        "effect_params": {"pace": -0.05, "chaos": 0.22, "dash_bias": 0.0},
        "weight": 0.7,
    },
    {
        "key": "jump_pad",
        "label": "ジャンプパッド",
        "short_label": "ジャンプ",
        "badge": "JUMP",
        "category": "boost",
        "theme": "jump",
        "color": "#5ee0dc",
        "short_desc": "成功時加速、失敗時減速",
        "effect_params": {"pace": 0.04, "chaos": 0.14, "dash_bias": 0.06},
        "weight": 0.8,
    },
    {
        "key": "safe_bay",
        "label": "安全整備帯",
        "short_label": "SAFE",
        "badge": "SAFE",
        "category": "safe",
        "theme": "bay",
        "color": "#8ea5bc",
        "short_desc": "立て直しやすい",
        "effect_params": {"pace": 0.05, "chaos": 0.02, "dash_bias": 0.0},
        "weight": 0.6,
    },
)

LAB_RACE_OBSTACLE_BY_KEY = {item["key"]: item for item in LAB_RACE_OBSTACLE_MASTER}

_CATEGORY_LIMITS = {
    "boost": 1,
    "hazard": 2,
    "chaos": 1,
    "safe": 1,
    "slow": 2,
}


def _weighted_choice(rng, weighted_items):
    total = sum(max(0.0, float(weight)) for _, weight in weighted_items)
    if total <= 0:
        return weighted_items[0][0]
    roll = rng.uniform(0.0, total)
    acc = 0.0
    for item, weight in weighted_items:
        acc += max(0.0, float(weight))
        if roll <= acc:
            return item
    return weighted_items[-1][0]


def _course_key(course_key):
    key = str(course_key or "").strip().lower()
    key = LAB_RACE_COURSE_ALIASES.get(key, key)
    if key in LAB_RACE_COURSES:
        return key
    return "scrapyard_sprint"


def course_meta(course_key=None, *, mode="standard"):
    if mode == "casino" and not course_key:
        return dict(LAB_RACE_COURSES["casino_scrapyard_cup"])
    return dict(LAB_RACE_COURSES[_course_key(course_key)])


def _special_positions_ok(indices):
    if any(indices[idx] + 1 == indices[idx + 1] and indices[idx + 1] + 1 == indices[idx + 2] for idx in range(len(indices) - 2)):
        return False
    middle_indices = {3, 4, 5, 6}
    if middle_indices.issubset(set(indices)):
        return False
    return True


def _choose_special_positions(rng, count):
    slots = list(range(1, LAB_RACE_SEGMENT_COUNT - 1))
    for _ in range(200):
        picked = sorted(rng.sample(slots, int(count)))
        if _special_positions_ok(picked):
            return picked
    return sorted(slots[: int(count)])


def _choose_special_features(rng, count):
    picked = []
    category_counts = {}
    for _ in range(200):
        candidates = []
        for item in LAB_RACE_OBSTACLE_MASTER:
            if item["key"] in {row["key"] for row in picked}:
                continue
            limit = _CATEGORY_LIMITS.get(item["category"], 99)
            if int(category_counts.get(item["category"], 0)) >= int(limit):
                continue
            candidates.append(item)
        if not candidates:
            break
        chosen = _weighted_choice(rng, [(item, item.get("weight", 1.0)) for item in candidates])
        picked.append(dict(chosen))
        category = chosen["category"]
        category_counts[category] = int(category_counts.get(category, 0)) + 1
        if len(picked) >= int(count):
            break
    if len(picked) < int(count):
        for item in LAB_RACE_OBSTACLE_MASTER:
            if item["key"] in {row["key"] for row in picked}:
                continue
            picked.append(dict(item))
            if len(picked) >= int(count):
                break
    return picked[: int(count)]


def build_course_layout(seed, *, course_key=None, mode="standard"):
    meta = course_meta(course_key, mode=mode)
    rng = random.Random(f"lab-race-course:{mode}:{meta['key']}:{int(seed)}")
    special_count = int(_weighted_choice(rng, LAB_RACE_SPECIAL_COUNT_WEIGHTS))
    special_positions = _choose_special_positions(rng, special_count)
    special_features = _choose_special_features(rng, special_count)
    rng.shuffle(special_features)
    feature_by_index = {
        index: dict(feature)
        for index, feature in zip(special_positions, special_features)
    }
    segment_size = LAB_RACE_GOAL / float(LAB_RACE_SEGMENT_COUNT)
    segments = []
    obstacles = []
    selected_features = []
    for index in range(LAB_RACE_SEGMENT_COUNT):
        start = round(index * segment_size, 2)
        end = round((index + 1) * segment_size, 2)
        mid = round(start + segment_size * 0.52, 2)
        if index == 0:
            segment = {
                "index": index,
                "kind": "start",
                "feature_key": "start",
                "label": "スタート整列区画",
                "short_label": "START",
                "badge": "START",
                "theme": "bay",
                "color": "#8ea5bc",
                "desc": "スタート直線",
                "effect_label": "足並みを揃える",
                "start": start,
                "end": end,
                "mid": mid,
            }
        elif index == LAB_RACE_SEGMENT_COUNT - 1:
            segment = {
                "index": index,
                "kind": "goal",
                "feature_key": "goal",
                "label": "ゴール前直線",
                "short_label": "GOAL",
                "badge": "GOAL",
                "theme": "goal",
                "color": "#7cb56c",
                "desc": "最後の決着区間",
                "effect_label": "最後の直線",
                "start": start,
                "end": end,
                "mid": mid,
            }
        elif index in feature_by_index:
            feature = dict(feature_by_index[index])
            segment = {
                "index": index,
                "kind": "special",
                "feature_key": feature["key"],
                "label": feature["label"],
                "short_label": feature["short_label"],
                "badge": feature["badge"],
                "theme": feature["theme"],
                "color": feature["color"],
                "desc": feature["short_desc"],
                "effect_label": feature["short_desc"],
                "category": feature["category"],
                "effect_params": dict(feature.get("effect_params") or {}),
                "start": start,
                "end": end,
                "mid": mid,
            }
            obstacles.append(
                {
                    "feature_key": feature["key"],
                    "type": feature["key"],
                    "label": feature["label"],
                    "category": feature["category"],
                    "theme": feature["theme"],
                    "badge": feature["badge"],
                    "color": feature["color"],
                    "progress": mid,
                    "segment_index": index,
                    "effect_params": dict(feature.get("effect_params") or {}),
                }
            )
            selected_features.append(
                {
                    "segment_index": index,
                    "feature_key": feature["key"],
                    "label": feature["label"],
                    "short_label": feature["short_label"],
                    "badge": feature["badge"],
                    "theme": feature["theme"],
                    "category": feature["category"],
                    "color": feature["color"],
                    "desc": feature["short_desc"],
                }
            )
        else:
            segment = {
                "index": index,
                "kind": "normal",
                "feature_key": "normal",
                "label": "通常路",
                "short_label": "STRAIGHT",
                "badge": meta.get("normal_badge") or "RUN",
                "theme": meta.get("normal_theme") or "normal",
                "color": "#7f8d98",
                "desc": "通常走行区間",
                "effect_label": "通常路",
                "start": start,
                "end": end,
                "mid": mid,
            }
        segments.append(segment)
    return {
        "key": meta["key"],
        "label": meta["label"],
        "summary": meta["summary"],
        "hidden": int(meta.get("hidden") or 0),
        "segment_size": float(segment_size),
        "segments": tuple(segments),
        "obstacles": tuple(obstacles),
        "selected_features": tuple(selected_features),
        "special_count": int(special_count),
    }
