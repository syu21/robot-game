import math
from collections import Counter

from constants import MODULE_PROTOCOL_DEFINITIONS


def protocol_definition(protocol_key):
    definition = MODULE_PROTOCOL_DEFINITIONS.get(str(protocol_key or ""))
    if not definition or not definition.get("is_active", True):
        return None
    return dict(definition)


def available_protocols(loadout_summary):
    modules = list((loadout_summary or {}).get("modules") or [])[:3]
    brand_counts = Counter(str(module.get("brand_key") or "nova") for module in modules)
    hybrid_three = len(modules) == 3 and len(brand_counts) == 3
    result = []
    for key, definition in MODULE_PROTOCOL_DEFINITIONS.items():
        item = dict(definition)
        if not item.get("is_active", True):
            continue
        brand_key = str(item.get("brand_key") or "")
        required = int(item.get("required_brand_count") or 0)
        unlocked = int(brand_counts.get(brand_key, 0)) >= required
        if key == "adaptive_shift" and hybrid_three:
            unlocked = True
        item["protocol_key"] = key
        item["is_unlocked"] = bool(unlocked)
        item["brand_count"] = int(brand_counts.get(brand_key, 0))
        if unlocked:
            item["lock_reason"] = ""
        elif key == "adaptive_shift":
            item["lock_reason"] = "NOVA 2個以上、または3ブランド混成で解放"
        else:
            item["lock_reason"] = f"あと{max(0, required - int(brand_counts.get(brand_key, 0)))}個で解放"
        result.append(item)
    return result


def is_protocol_available(loadout_summary, protocol_key):
    key = str(protocol_key or "").strip()
    return any(item["protocol_key"] == key and item.get("is_unlocked") for item in available_protocols(loadout_summary))


def init_protocol_state(protocol_key, loadout_summary):
    definition = protocol_definition(protocol_key)
    if not definition:
        return None
    return {
        "protocol_key": definition["protocol_key"],
        "protocol_name": definition["name_ja"],
        "definition": definition,
        "activation_count": 0,
        "activation_turns": [],
        "events": [],
        "pending_critical_bonus": False,
        "critical_bonus_from_chain": False,
        "pending_guaranteed_hit": False,
        "limit_break_active": False,
        "selected_adaptation": None,
        "adaptive_bonus": {},
        "temporary_bonus": {},
        "temporary_bonus_until_turn": 0,
        "recent_player_results": [],
        "totals": {
            "damage_reduced": 0,
            "healing_amount": 0,
            "bonus_damage": 0,
            "recoil_damage": 0,
            "guaranteed_hit": 0,
            "critical_bonus": 0,
        },
        "brand_counts": dict((loadout_summary or {}).get("brand_counts") or {}),
        "os_name": (loadout_summary or {}).get("os_name") or "NO MODULE OS",
    }


def _event(state, turn, text, *, effect_type="", effect_value=0, **extra):
    state["activation_count"] = int(state.get("activation_count") or 0) + 1
    state.setdefault("activation_turns", []).append(int(turn))
    item = {
        "turn": int(turn),
        "text": text,
        "effect_type": effect_type,
        "effect_value": effect_value,
    }
    item.update(extra)
    state.setdefault("events", []).append(item)
    return text


def _pick_adaptation(enemy_stats):
    stats = {
        "atk": int((enemy_stats or {}).get("atk") or 0),
        "def": int((enemy_stats or {}).get("def") or 0),
        "spd": int((enemy_stats or {}).get("spd") or 0),
        "acc": int((enemy_stats or {}).get("acc") or 0),
    }
    top = max(stats.values()) if stats else 0
    top_keys = [key for key, value in stats.items() if value == top]
    if len(top_keys) != 1:
        return "hp", {"hp": 8}, "耐久構成"
    key = top_keys[0]
    if key == "atk":
        return "def", {"def_pct": 0.10}, "防御構成"
    if key == "def":
        return "atk", {"atk_pct": 0.10}, "攻撃構成"
    if key == "spd":
        return "acc", {"acc": 10}, "命中構成"
    return "spd", {"spd_pct": 0.10}, "高速構成"


def battle_start(state, enemy_stats):
    if not state:
        return []
    key = state["protocol_key"]
    if key == "fortress_guard":
        return [_event(state, 1, "要塞防御が展開され、被害を軽減した", effect_type="damage_reduction_window", effect_value=15)]
    if key == "opening_acceleration":
        return [_event(state, 1, "開幕加速により演算速度が上昇した", effect_type="speed_pct", effect_value=20)]
    if key == "target_analysis":
        return [_event(state, 1, "標的解析により敵機動データを取得した", effect_type="accuracy", effect_value=10)]
    if key == "adaptive_shift":
        selected, bonus, label = _pick_adaptation(enemy_stats)
        state["selected_adaptation"] = selected
        state["adaptive_bonus"] = bonus
        return [_event(state, 1, f"適応変換が敵機を解析し、{label}へ移行した", effect_type=f"adapt_{selected}", effect_value=1)]
    return []


def turn_start(state, turn, player_hp, player_max_hp, enemy_hp, enemy_max_hp):
    if not state:
        return []
    lines = []
    key = state["protocol_key"]
    if key == "limit_break":
        active = int(player_hp) * 100 <= int(player_max_hp) * 35
        if active and not state.get("limit_break_active"):
            state["limit_break_active"] = True
            lines.append(_event(state, turn, "限界突破が起動し、攻撃出力が上昇した", effect_type="limit_break_on", effect_value=1))
        elif (not active) and state.get("limit_break_active"):
            state["limit_break_active"] = False
            lines.append(_event(state, turn, "耐久回復により限界突破が停止した", effect_type="limit_break_off", effect_value=1))
    if key == "emergency_reconfiguration" and int(turn) == 4 and int(state.get("activation_count") or 0) <= 0:
        if int(player_hp) * 100 < int(player_max_hp) * 50:
            healing = min(int(player_max_hp) - int(player_hp), max(1, int(round(int(player_max_hp) * 0.08))))
            state["pending_reconfiguration_heal"] = healing
            lines.append(_event(state, turn, "緊急再構成により修復プロトコルへ切り替えた", effect_type="healing", effect_value=healing, healing_amount=healing))
        elif any(item.get("missed") for item in state.get("recent_player_results", [])[-2:]):
            state["pending_guaranteed_hit"] = True
            lines.append(_event(state, turn, "緊急再構成により軌道補正プロトコルへ切り替えた", effect_type="guaranteed_hit", effect_value=1, guaranteed_hit=True))
        elif int(enemy_hp) * 100 < int(enemy_max_hp) * 40:
            state["temporary_bonus"] = {"atk_pct": 0.15}
            state["temporary_bonus_until_turn"] = int(turn) + 1
            lines.append(_event(state, turn, "緊急再構成により攻撃プロトコルへ切り替えた", effect_type="atk_pct", effect_value=15))
        else:
            state["temporary_bonus"] = {"def_pct": 0.10}
            state["temporary_bonus_until_turn"] = int(turn) + 1
            lines.append(_event(state, turn, "緊急再構成により防御プロトコルへ切り替えた", effect_type="def_pct", effect_value=10))
    return lines


def consume_pending_heal(state, player_hp, player_max_hp):
    if not state:
        return int(player_hp), []
    healing = int(state.pop("pending_reconfiguration_heal", 0) or 0)
    if healing <= 0:
        return int(player_hp), []
    actual = min(max(0, int(player_max_hp) - int(player_hp)), healing)
    state["totals"]["healing_amount"] += actual
    return min(int(player_max_hp), int(player_hp) + actual), [f"緊急再構成により耐久を{actual}回復した"]


def effective_speed(state, base_spd, turn):
    spd = int(base_spd)
    if state and state["protocol_key"] == "opening_acceleration" and int(turn) <= 2:
        spd = max(1, int(round(spd * 1.20)))
    if state and state.get("adaptive_bonus", {}).get("spd_pct"):
        spd = max(1, int(round(spd * (1.0 + float(state["adaptive_bonus"]["spd_pct"])))))
    return spd


def apply_attack_modifiers(state, *, atk, acc, cri, force_hit, turn):
    atk = int(atk)
    acc = int(acc)
    cri = int(cri)
    force_hit = bool(force_hit)
    if not state:
        return atk, acc, cri, force_hit, []
    lines = []
    bonus = dict(state.get("adaptive_bonus") or {})
    if bonus.get("atk_pct"):
        atk = max(1, int(round(atk * (1.0 + float(bonus["atk_pct"])))))
    if bonus.get("acc"):
        acc += int(bonus["acc"])
    if state["protocol_key"] == "target_analysis":
        acc += 10
    if state.get("limit_break_active"):
        atk = max(1, int(round(atk * 1.20)))
    if int(turn) <= int(state.get("temporary_bonus_until_turn") or 0):
        temp = state.get("temporary_bonus") or {}
        if temp.get("atk_pct"):
            atk = max(1, int(round(atk * (1.0 + float(temp["atk_pct"])))))
    if state.get("pending_critical_bonus"):
        cri += 15
        state["pending_critical_bonus"] = False
        state["critical_bonus_from_chain"] = True
        state["totals"]["critical_bonus"] += 1
        lines.append("会心連鎖により次撃の会心精度が上昇した")
    else:
        state["critical_bonus_from_chain"] = False
    if state.get("pending_guaranteed_hit") and not force_hit:
        force_hit = True
        state["pending_guaranteed_hit"] = False
        state["totals"]["guaranteed_hit"] += 1
        lines.append("誤差修正により次撃の軌道を固定した")
    return atk, acc, cri, force_hit, lines


def apply_defense_modifiers(state, defense, turn):
    defense = int(defense)
    if not state:
        return max(1, defense)
    bonus = dict(state.get("adaptive_bonus") or {})
    if bonus.get("def_pct"):
        defense = max(1, int(round(defense * (1.0 + float(bonus["def_pct"])))))
    if state.get("limit_break_active"):
        defense = max(1, int(round(defense * 0.90)))
    if int(turn) <= int(state.get("temporary_bonus_until_turn") or 0):
        temp = state.get("temporary_bonus") or {}
        if temp.get("def_pct"):
            defense = max(1, int(round(defense * (1.0 + float(temp["def_pct"])))))
    return max(1, defense)


def after_player_attack(state, *, turn, missed, critical):
    if not state:
        return []
    state.setdefault("recent_player_results", []).append({"turn": int(turn), "missed": bool(missed), "critical": bool(critical)})
    state["recent_player_results"] = state["recent_player_results"][-4:]
    lines = []
    if state["protocol_key"] == "critical_chain" and critical and not state.get("critical_bonus_from_chain") and int(state.get("activation_count") or 0) < 2:
        state["pending_critical_bonus"] = True
        lines.append(_event(state, turn, "会心連鎖が起動し、次撃の会心精度が上昇した", effect_type="critical_bonus", effect_value=15, critical_bonus=True))
    if state["protocol_key"] == "miss_correction" and missed and int(state.get("activation_count") or 0) < 2 and not state.get("pending_guaranteed_hit"):
        state["pending_guaranteed_hit"] = True
        lines.append(_event(state, turn, "誤差修正が完了し、次撃の軌道を固定した", effect_type="guaranteed_hit", effect_value=1, guaranteed_hit=True))
    return lines


def apply_outgoing_damage(state, damage, *, turn, player_max_hp, rng):
    damage = int(damage)
    if not state or damage <= 0:
        return damage, 0, []
    lines = []
    recoil = 0
    if state["protocol_key"] == "unstable_overdrive" and int(state.get("activation_count") or 0) < 2 and rng.random() < 0.20:
        before = damage
        damage = max(1, int(round(damage * 1.5)))
        bonus = max(0, damage - before)
        recoil = max(1, int(math.ceil(int(player_max_hp) * 0.05)))
        state["totals"]["bonus_damage"] += bonus
        state["totals"]["recoil_damage"] += recoil
        lines.append(_event(state, turn, "不安定過駆動が成功し、出力が暴走した", effect_type="damage_multiplier", effect_value=150, bonus_damage=bonus, recoil_damage=recoil))
    return damage, recoil, lines


def apply_incoming_damage(state, damage, *, turn):
    damage = int(damage)
    if not state or damage <= 0:
        return damage, []
    lines = []
    if state["protocol_key"] == "fortress_guard" and int(turn) <= 3:
        before = damage
        damage = max(1, int(math.floor(damage * 0.85)))
        reduced = max(0, before - damage)
        if reduced > 0:
            state["totals"]["damage_reduced"] += reduced
            lines.append(_event(state, turn, "要塞防御が被害を軽減した", effect_type="damage_reduction", effect_value=reduced, damage_reduced=reduced))
    return damage, lines


def after_player_damage(state, *, turn, player_hp, player_max_hp):
    if not state or state["protocol_key"] != "emergency_repair":
        return int(player_hp), []
    if int(state.get("activation_count") or 0) >= 1 or int(player_hp) <= 0:
        return int(player_hp), []
    if int(player_hp) * 100 > int(player_max_hp) * 30:
        return int(player_hp), []
    heal = max(1, int(round(int(player_max_hp) * 0.12)))
    actual = min(max(0, int(player_max_hp) - int(player_hp)), heal)
    state["totals"]["healing_amount"] += actual
    _event(state, turn, "緊急修復が作動し、耐久を回復した", effect_type="healing", effect_value=actual, healing_amount=actual)
    return min(int(player_max_hp), int(player_hp) + actual), [f"緊急修復が作動し、耐久を{actual}回復した"]


def summary(state):
    if not state:
        return None
    events = list(state.get("events") or [])
    totals = dict(state.get("totals") or {})
    effect_parts = []
    if totals.get("damage_reduced"):
        effect_parts.append(f"軽減 {int(totals['damage_reduced'])}")
    if totals.get("healing_amount"):
        effect_parts.append(f"回復 {int(totals['healing_amount'])}")
    if totals.get("bonus_damage"):
        effect_parts.append(f"追加ダメージ {int(totals['bonus_damage'])}")
    if totals.get("recoil_damage"):
        effect_parts.append(f"反動 {int(totals['recoil_damage'])}")
    if totals.get("guaranteed_hit"):
        effect_parts.append(f"必中 {int(totals['guaranteed_hit'])}回")
    if totals.get("critical_bonus"):
        effect_parts.append(f"会心補正 {int(totals['critical_bonus'])}回")
    return {
        "protocol_key": state.get("protocol_key"),
        "protocol_name": state.get("protocol_name"),
        "activation_count": int(state.get("activation_count") or 0),
        "activation_turns": list(state.get("activation_turns") or []),
        "events": events,
        "totals": totals,
        "effect_summary": " / ".join(effect_parts) if effect_parts else "",
        "not_triggered": not bool(events),
        "selected_adaptation": state.get("selected_adaptation"),
    }
