import math

from constants import BATTLE_CODE_CONDITIONS, BATTLE_CODE_EFFECTS


STAT_EFFECT_TYPES = {"attack_multiplier", "defense_multiplier", "speed_multiplier", "critical_bonus"}
NEXT_ATTACK_EFFECTS = {"attack_multiplier", "critical_bonus", "guaranteed_hit"}


def condition_definition(condition_key):
    definition = BATTLE_CODE_CONDITIONS.get(str(condition_key or ""))
    if not definition or not definition.get("is_active", True):
        return None
    return dict(definition)


def effect_definition(effect_key):
    definition = BATTLE_CODE_EFFECTS.get(str(effect_key or ""))
    if not definition or not definition.get("is_active", True):
        return None
    return dict(definition)


def active_conditions():
    return sorted(
        [dict(item) for item in BATTLE_CODE_CONDITIONS.values() if item.get("is_active", True)],
        key=lambda item: int(item.get("sort_order") or 0),
    )


def active_effects():
    return sorted(
        [dict(item) for item in BATTLE_CODE_EFFECTS.values() if item.get("is_active", True)],
        key=lambda item: int(item.get("sort_order") or 0),
    )


def validate_selection(condition_key, effect_key):
    condition = condition_definition(condition_key)
    effect = effect_definition(effect_key)
    if not condition_key and not effect_key:
        return {"ok": True, "condition": None, "effect": None}
    if not condition_key or not effect_key:
        return {"ok": False, "reason": "条件コードと効果コードはセットで指定してください"}
    if not condition:
        return {"ok": False, "reason": "存在しない条件コードです"}
    if not effect:
        return {"ok": False, "reason": "存在しない効果コードです"}
    return {"ok": True, "condition": condition, "effect": effect}


def validate_dual_selection(condition_key, effect_key, condition_key_b=None, effect_key_b=None):
    first = validate_selection(condition_key, effect_key)
    if not first.get("ok"):
        return first
    condition_key_b = str(condition_key_b or "").strip()
    effect_key_b = str(effect_key_b or "").strip()
    if not condition_key_b and not effect_key_b:
        return {**first, "condition_b": None, "effect_b": None, "is_dual": False}
    second = validate_selection(condition_key_b, effect_key_b)
    if not second.get("ok"):
        return second
    if str(condition_key or "").strip() == condition_key_b:
        return {"ok": False, "reason": "LOGIC A/Bに同じ条件コードは設定できません。"}
    return {
        "ok": True,
        "condition": first.get("condition"),
        "effect": first.get("effect"),
        "condition_b": second.get("condition"),
        "effect_b": second.get("effect"),
        "is_dual": True,
    }


def display_name(condition_key, effect_key):
    condition = condition_definition(condition_key)
    effect = effect_definition(effect_key)
    if not condition or not effect:
        return ""
    return f"{condition['prefix_ja']}《{condition['prefix_en']}-{effect['code_name']}》"


def display_name_dual(condition_key, effect_key, condition_key_b=None, effect_key_b=None):
    if not condition_key_b and not effect_key_b:
        return display_name(condition_key, effect_key)
    condition_a = condition_definition(condition_key)
    condition_b = condition_definition(condition_key_b)
    effect_a = effect_definition(effect_key)
    effect_b = effect_definition(effect_key_b)
    if not condition_a or not condition_b or not effect_a or not effect_b:
        return ""
    return f"二重戦術式《{condition_a['prefix_en']}-{condition_b['prefix_en']}》"


def duration_policy(condition_key, effect_key):
    effect = effect_definition(effect_key) or {}
    effect_type = str(effect.get("effect_type") or "")
    if effect_type == "heal_percent":
        return {"kind": "instant", "max_activations": 1, "label": "1戦闘1回"}
    if effect_type == "guaranteed_hit":
        max_count = 1 if condition_key in {"battle_start", "turn_4_start"} else 2
        return {"kind": "next_attack", "max_activations": max_count, "label": f"次の自分の攻撃1回 / 最大{max_count}回"}
    if condition_key in {"battle_start", "turn_4_start"}:
        start_turn = 1 if condition_key == "battle_start" else 4
        return {"kind": "turn_window", "start_turn": start_turn, "duration_turns": 2, "max_activations": 1, "label": "2ターン有効"}
    if str(condition_key or "").startswith("enemy_"):
        return {"kind": "turn_window", "start_turn": 1, "duration_turns": 2, "max_activations": 1, "label": "2ターン有効"}
    if condition_key == "low_hp_30":
        return {"kind": "hp_threshold", "max_activations": 0, "label": "耐久30%以下の間だけ有効"}
    if condition_key in {"after_miss", "after_critical"}:
        if effect_type == "defense_multiplier":
            return {"kind": "next_hit", "max_activations": 0, "label": "次に受ける攻撃1回"}
        if effect_type == "speed_multiplier":
            return {"kind": "until_next_turn_end", "max_activations": 0, "label": "次ターン終了まで"}
        return {"kind": "next_attack", "max_activations": 0, "label": "次の自分の攻撃1回"}
    if condition_key == "enemy_low_hp_40":
        return {"kind": "battle_end", "max_activations": 1, "label": "初回到達後、戦闘終了まで"}
    return {"kind": "instant", "max_activations": int(effect.get("default_max_activations") or 0), "label": "条件成立時"}


def combination_summary(condition_key, effect_key):
    condition = condition_definition(condition_key)
    effect = effect_definition(effect_key)
    if not condition or not effect:
        return None
    policy = duration_policy(condition_key, effect_key)
    value = effect_value_label(effect)
    return {
        "condition_key": condition_key,
        "effect_key": effect_key,
        "display_name": display_name(condition_key, effect_key),
        "condition_name": condition["name_ja"],
        "effect_name": effect["name_ja"],
        "condition_description": condition["short_description"],
        "effect_description": effect["short_description"],
        "condition_timing": condition["timing_label"],
        "effect_value_label": value,
        "duration_label": policy["label"],
        "specific_description": f"{condition['name_ja']}成立時、{effect['name_ja']}を起動します。{value} / {policy['label']}。",
        "affinity_label": effect.get("affinity_label") or "",
    }


def effect_value_label(effect):
    effect_type = str(effect.get("effect_type") or "")
    value = effect.get("value")
    if effect_type in {"attack_multiplier", "defense_multiplier", "speed_multiplier"}:
        return f"{int(round(float(value) * 100))}%上昇"
    if effect_type == "critical_bonus":
        return f"会心率+{int(value)}"
    if effect_type == "guaranteed_hit":
        return "次撃必中"
    if effect_type == "heal_percent":
        return f"最大HP{int(round(float(value) * 100))}%回復"
    return "効果起動"


def snapshot(condition_key, effect_key):
    summary = combination_summary(condition_key, effect_key)
    if not summary:
        return None
    condition = condition_definition(condition_key)
    effect = effect_definition(effect_key)
    return {
        **summary,
        "code_version": "single",
        "logic_count": 1,
        "logic_entries": [
            {
                "slot": "A",
                "priority": 1,
                "condition_key": condition_key,
                "effect_key": effect_key,
                "condition_name": summary["condition_name"],
                "effect_name": summary["effect_name"],
                "specific_description": summary["specific_description"],
            }
        ],
        "condition": condition,
        "effect": effect,
        "duration": duration_policy(condition_key, effect_key),
    }


def snapshot_dual(condition_key, effect_key, condition_key_b=None, effect_key_b=None):
    validation = validate_dual_selection(condition_key, effect_key, condition_key_b, effect_key_b)
    if not validation.get("ok"):
        return None
    base = snapshot(condition_key, effect_key)
    if not base:
        return None
    if not condition_key_b and not effect_key_b:
        return base
    second = combination_summary(condition_key_b, effect_key_b)
    if not second:
        return None
    display = display_name_dual(condition_key, effect_key, condition_key_b, effect_key_b)
    logic_entries = [
        {
            "slot": "A",
            "priority": 1,
            "condition_key": condition_key,
            "effect_key": effect_key,
            "condition_name": base["condition_name"],
            "effect_name": base["effect_name"],
            "specific_description": base["specific_description"],
        },
        {
            "slot": "B",
            "priority": 2,
            "condition_key": condition_key_b,
            "effect_key": effect_key_b,
            "condition_name": second["condition_name"],
            "effect_name": second["effect_name"],
            "specific_description": second["specific_description"],
        },
    ]
    return {
        **base,
        "condition_key_b": condition_key_b,
        "effect_key_b": effect_key_b,
        "display_name": display,
        "specific_description": "先に成立したロジックを1度だけ実行します。",
        "code_version": "dual",
        "logic_count": 2,
        "logic_entries": logic_entries,
        "logic_a": logic_entries[0],
        "logic_b": logic_entries[1],
    }


def _init_single_state(code_snapshot, *, logic_slot=None):
    if not code_snapshot:
        return None
    condition = dict(code_snapshot["condition"])
    effect = dict(code_snapshot["effect"])
    duration = dict(code_snapshot["duration"])
    return {
        "condition_key": condition["condition_key"],
        "effect_key": effect["effect_key"],
        "display_name": code_snapshot["display_name"],
        "code_version": code_snapshot.get("code_version") or "single",
        "logic_slot": logic_slot,
        "condition_name": condition["name_ja"],
        "effect_name": effect["name_ja"],
        "library_id": code_snapshot.get("library_id"),
        "slot_number": code_snapshot.get("slot_number"),
        "usage_label": code_snapshot.get("usage_label"),
        "usage_label_name": code_snapshot.get("usage_label_name"),
        "condition": condition,
        "effect": effect,
        "duration": duration,
        "activation_count": 0,
        "condition_event_count": 0,
        "max_activations": int(duration.get("max_activations") or 0),
        "activation_turns": [],
        "events": [],
        "condition_events": [],
        "consume_events": [],
        "pending_guaranteed_hit": False,
        "pending_attack_multiplier": False,
        "pending_defense_multiplier": False,
        "pending_critical_bonus": False,
        "turn_window_until": 0,
        "speed_bonus_until_turn": 0,
        "hp_threshold_active": False,
        "battle_end_active": False,
        "enemy_low_hp_triggered": False,
        "effect_totals": {
            "healing_amount": 0,
            "damage_reduced": 0,
            "bonus_damage": 0,
            "guaranteed_hit": 0,
            "critical_bonus": 0,
            "active_turns": 0,
        },
    }


def init_state(code_snapshot):
    if not code_snapshot:
        return None
    logic_entries = list(code_snapshot.get("logic_entries") or [])
    if len(logic_entries) <= 1:
        return _init_single_state(code_snapshot, logic_slot=(logic_entries[0].get("slot") if logic_entries else None))
    logic_states = []
    for entry in logic_entries[:2]:
        snap = snapshot(entry.get("condition_key"), entry.get("effect_key"))
        if not snap:
            continue
        state = _init_single_state(snap, logic_slot=entry.get("slot"))
        state["display_name"] = code_snapshot.get("display_name") or state.get("display_name")
        logic_states.append(state)
    if not logic_states:
        return None
    return {
        "is_dual_logic": True,
        "code_version": "dual",
        "display_name": code_snapshot.get("display_name"),
        "library_id": code_snapshot.get("library_id"),
        "slot_number": code_snapshot.get("slot_number"),
        "usage_label": code_snapshot.get("usage_label"),
        "usage_label_name": code_snapshot.get("usage_label_name"),
        "logic_entries": logic_entries[:2],
        "logic_states": logic_states,
        "activation_count": 0,
        "condition_event_count": 0,
        "activation_turns": [],
        "resolved_logic_slot": None,
    }


def _is_dual_state(state):
    return bool(state and state.get("is_dual_logic") and state.get("logic_states"))


def _active_dual_logic_state(state):
    if not _is_dual_state(state):
        return None
    slot = state.get("resolved_logic_slot")
    if slot:
        for logic_state in state.get("logic_states") or []:
            if logic_state.get("logic_slot") == slot:
                return logic_state
    return None


def _sync_dual_state(state):
    if not _is_dual_state(state):
        return
    state["condition_event_count"] = sum(int(s.get("condition_event_count") or 0) for s in state.get("logic_states") or [])
    triggered = None
    for logic_state in state.get("logic_states") or []:
        if int(logic_state.get("activation_count") or 0) > 0:
            triggered = logic_state
            break
    if triggered:
        state["activation_count"] = 1
        state["resolved_logic_slot"] = triggered.get("logic_slot")
        turns = list(triggered.get("activation_turns") or [])
        state["activation_turns"] = turns[:1]


def _run_dual_hook(state, hook, current_player_hp):
    if int(state.get("activation_count") or 0) > 0:
        return int(current_player_hp), []
    all_lines = []
    result_hp = None
    for logic_state in state.get("logic_states") or []:
        before = int(logic_state.get("activation_count") or 0)
        hp, lines = hook(logic_state)
        result_hp = hp
        all_lines.extend(lines)
        if int(logic_state.get("activation_count") or 0) > before:
            break
    _sync_dual_state(state)
    return int(result_hp if result_hp is not None else current_player_hp), all_lines


def start_lines(state):
    if not state:
        return []
    code = str(state.get("display_name") or "")
    inner = code.split("《", 1)[1].rstrip("》") if "《" in code else code
    if _is_dual_state(state):
        return [f"BATTLE CODE《{inner}》――DUAL LOGIC接続完了。"]
    return [f"BATTLE CODE《{inner}》――接続完了。"]


def _record_condition(state, turn, reason):
    state["condition_event_count"] = int(state.get("condition_event_count") or 0) + 1
    event = {"turn": int(turn), "text": reason, "condition_event_index": int(state["condition_event_count"])}
    if state.get("logic_slot"):
        event["logic_slot"] = state.get("logic_slot")
        event["condition_key"] = state.get("condition_key")
        event["effect_key"] = state.get("effect_key")
    state.setdefault("condition_events", []).append(event)
    return event


def _can_activate(state):
    max_activations = int(state.get("max_activations") or 0)
    return max_activations <= 0 or int(state.get("activation_count") or 0) < max_activations


def _record_trigger(state, turn, text, *, effect_type=None, effect_value=None, **extra):
    state["activation_count"] = int(state.get("activation_count") or 0) + 1
    state.setdefault("activation_turns", []).append(int(turn))
    event = {
        "turn": int(turn),
        "text": text,
        "activation_index": int(state["activation_count"]),
        "effect_type": effect_type or state["effect"].get("effect_type"),
        "effect_value": effect_value if effect_value is not None else state["effect"].get("value"),
    }
    if state.get("logic_slot"):
        event["logic_slot"] = state.get("logic_slot")
        event["condition_key"] = state.get("condition_key")
        event["effect_key"] = state.get("effect_key")
    event.update(extra)
    state.setdefault("events", []).append(event)
    return text


def _record_consume(state, turn, text, **extra):
    event = {"turn": int(turn), "text": text}
    if state.get("logic_slot"):
        event["logic_slot"] = state.get("logic_slot")
        event["condition_key"] = state.get("condition_key")
        event["effect_key"] = state.get("effect_key")
    event.update(extra)
    state.setdefault("consume_events", []).append(event)
    return text


def _activate(state, turn, player_hp, player_max_hp):
    if not state or not _can_activate(state):
        return int(player_hp), []
    effect = state["effect"]
    effect_type = str(effect.get("effect_type") or "")
    value = effect.get("value")
    duration = state["duration"]
    kind = str(duration.get("kind") or "")
    effect_name = str(effect.get("name_ja") or "戦闘命令")
    lines = []
    if effect_type == "heal_percent":
        if int(player_hp) <= 0:
            return int(player_hp), []
        heal = max(1, int(round(int(player_max_hp) * float(value))))
        actual = min(max(0, int(player_max_hp) - int(player_hp)), heal)
        state["effect_totals"]["healing_amount"] += int(actual)
        lines.append(_record_trigger(state, turn, f"{effect_name}が起動し、機体損傷を修復した。", healing_amount=int(actual)))
        return min(int(player_max_hp), int(player_hp) + int(actual)), lines
    if effect_type == "guaranteed_hit":
        if state.get("pending_guaranteed_hit"):
            return int(player_hp), []
        state["pending_guaranteed_hit"] = True
        lines.append(_record_trigger(state, turn, f"誤差を検出。{effect_name}を次撃へ接続した。", guaranteed_hit=True))
        return int(player_hp), lines
    if kind == "turn_window":
        state["turn_window_until"] = int(turn) + int(duration.get("duration_turns") or 1) - 1
        lines.append(_record_trigger(state, turn, f"{state['condition_name'].split('《')[0]}を受理。{effect_name}を起動した。", duration_turns=int(duration.get("duration_turns") or 1)))
    elif kind == "hp_threshold":
        if not state.get("hp_threshold_active"):
            state["hp_threshold_active"] = True
            lines.append(_record_trigger(state, turn, f"崩壊領域へ到達。{effect_name}を解放した。"))
    elif kind == "battle_end":
        if not state.get("battle_end_active"):
            state["battle_end_active"] = True
            lines.append(_record_trigger(state, turn, f"終局判定を受理。{effect_name}を戦闘終了まで接続した。"))
    elif kind == "next_hit":
        if not state.get("pending_defense_multiplier"):
            state["pending_defense_multiplier"] = True
            lines.append(_record_trigger(state, turn, f"{state['condition_name'].split('《')[0]}を検出。{effect_name}を次回被弾へ接続した。"))
    elif kind == "until_next_turn_end":
        state["speed_bonus_until_turn"] = int(turn) + 1
        lines.append(_record_trigger(state, turn, f"{state['condition_name'].split('《')[0]}を検出。{effect_name}を次ターンへ接続した。"))
    elif kind == "next_attack":
        if effect_type == "attack_multiplier" and not state.get("pending_attack_multiplier"):
            state["pending_attack_multiplier"] = True
            lines.append(_record_trigger(state, turn, f"{state['condition_name'].split('《')[0]}を検出。{effect_name}を次撃へ接続した。"))
        elif effect_type == "critical_bonus" and not state.get("pending_critical_bonus"):
            state["pending_critical_bonus"] = True
            lines.append(_record_trigger(state, turn, f"{state['condition_name'].split('《')[0]}を検出。{effect_name}を次撃へ接続した。"))
    return int(player_hp), lines


def _enemy_trait_matches(condition_key, enemy_trait_key):
    condition = condition_definition(condition_key) or {}
    return str(condition.get("trigger_type") or "") == "enemy_trait" and str(condition.get("trigger_value") or "") == str(enemy_trait_key or "")


def battle_start(state, player_hp, player_max_hp, enemy_trait_key=None):
    if _is_dual_state(state):
        return _run_dual_hook(
            state,
            lambda logic_state: battle_start(logic_state, player_hp, player_max_hp, enemy_trait_key=enemy_trait_key),
            player_hp,
        )
    if not state or state["condition_key"] != "battle_start":
        if state and _enemy_trait_matches(state.get("condition_key"), enemy_trait_key):
            _record_condition(state, 1, "敵特性反応を受理。")
            return _activate(state, 1, player_hp, player_max_hp)
        return int(player_hp), []
    _record_condition(state, 1, "開戦宣言を受理。")
    return _activate(state, 1, player_hp, player_max_hp)


def turn_start(state, turn, player_hp, player_max_hp, enemy_hp, enemy_max_hp, enemy_trait_key=None):
    if not state:
        return int(player_hp), []
    if _is_dual_state(state):
        return _run_dual_hook(
            state,
            lambda logic_state: turn_start(
                logic_state,
                turn,
                player_hp,
                player_max_hp,
                enemy_hp,
                enemy_max_hp,
                enemy_trait_key=enemy_trait_key,
            ),
            player_hp,
        )
    lines = []
    if state["condition_key"] == "turn_4_start" and int(turn) == 4:
        _record_condition(state, turn, "長期戦移行を検出。")
        player_hp, trigger_lines = _activate(state, turn, player_hp, player_max_hp)
        lines.extend(trigger_lines)
    if state["condition_key"] == "low_hp_30":
        active = int(player_hp) > 0 and int(player_hp) * 100 <= int(player_max_hp) * 30
        if active and not state.get("hp_threshold_active"):
            _record_condition(state, turn, "崩壊領域へ到達。")
            player_hp, trigger_lines = _activate(state, turn, player_hp, player_max_hp)
            lines.extend(trigger_lines)
        elif (not active) and state.get("hp_threshold_active"):
            state["hp_threshold_active"] = False
            lines.append(_record_consume(state, turn, "耐久回復を確認。崩壊領域用コードを停止した。", consume_type="hp_threshold_off"))
    if state["condition_key"] == "enemy_low_hp_40" and not state.get("enemy_low_hp_triggered"):
        if int(enemy_hp) * 100 <= int(enemy_max_hp) * 40:
            state["enemy_low_hp_triggered"] = True
            _record_condition(state, turn, "敵機の耐久低下を検出。")
            player_hp, trigger_lines = _activate(state, turn, player_hp, player_max_hp)
            lines.extend(trigger_lines)
    return int(player_hp), lines


def effective_speed(state, base_spd, turn):
    spd = int(base_spd)
    if not state:
        return max(1, spd)
    if _is_dual_state(state):
        return effective_speed(_active_dual_logic_state(state), base_spd, turn)
    if _stat_effect_active(state, "speed_multiplier", int(turn)):
        spd = max(1, int(round(spd * (1.0 + float(state["effect"].get("value") or 0)))))
    return max(1, spd)


def _stat_effect_active(state, effect_type, turn):
    if not state or str(state["effect"].get("effect_type") or "") != effect_type:
        return False
    return bool(
        state.get("hp_threshold_active")
        or state.get("battle_end_active")
        or int(turn) <= int(state.get("turn_window_until") or 0)
        or int(turn) <= int(state.get("speed_bonus_until_turn") or 0)
    )


def apply_attack_modifiers(state, *, atk, cri, force_hit, turn):
    atk = int(atk)
    cri = int(cri)
    force_hit = bool(force_hit)
    lines = []
    if not state:
        return atk, cri, force_hit, lines
    if _is_dual_state(state):
        return apply_attack_modifiers(_active_dual_logic_state(state), atk=atk, cri=cri, force_hit=force_hit, turn=turn)
    value = state["effect"].get("value") or 0
    if _stat_effect_active(state, "attack_multiplier", turn):
        before = atk
        atk = max(1, int(round(atk * (1.0 + float(value)))))
        state["effect_totals"]["bonus_damage"] += max(0, atk - before)
    if _stat_effect_active(state, "critical_bonus", turn):
        cri += int(value)
    if state.get("pending_attack_multiplier") and str(state["effect"].get("effect_type")) == "attack_multiplier":
        before = atk
        atk = max(1, int(round(atk * (1.0 + float(value)))))
        state["pending_attack_multiplier"] = False
        state["effect_totals"]["bonus_damage"] += max(0, atk - before)
        lines.append(_record_consume(state, turn, "接続された殲滅出力を次撃へ解放した。", consume_type="next_attack_bonus"))
    if state.get("pending_critical_bonus") and str(state["effect"].get("effect_type")) == "critical_bonus":
        cri += int(value)
        state["pending_critical_bonus"] = False
        state["effect_totals"]["critical_bonus"] += 1
        lines.append(_record_consume(state, turn, "臨界照準が次撃の会心演算を補正した。", consume_type="next_attack_critical"))
    if state.get("pending_guaranteed_hit") and not force_hit:
        force_hit = True
        state["pending_guaranteed_hit"] = False
        state["effect_totals"]["guaranteed_hit"] += 1
        lines.append(_record_consume(state, turn, "固定された因果により、攻撃軌道が確定した。", consume_type="guaranteed_hit", guaranteed_hit=True))
    elif state.get("pending_guaranteed_hit") and force_hit:
        state["pending_guaranteed_hit"] = False
        state["effect_totals"]["guaranteed_hit"] += 1
        lines.append(_record_consume(state, turn, "固定された因果を既存の必中演算へ統合した。", consume_type="guaranteed_hit", guaranteed_hit=True))
    return atk, cri, force_hit, lines


def apply_defense_modifiers(state, defense, turn):
    defense = int(defense)
    if not state:
        return max(1, defense)
    if _is_dual_state(state):
        return apply_defense_modifiers(_active_dual_logic_state(state), defense, turn)
    if _stat_effect_active(state, "defense_multiplier", turn):
        defense = max(1, int(round(defense * (1.0 + float(state["effect"].get("value") or 0)))))
    if state.get("pending_defense_multiplier") and str(state["effect"].get("effect_type")) == "defense_multiplier":
        defense = max(1, int(round(defense * (1.0 + float(state["effect"].get("value") or 0)))))
    return max(1, defense)


def after_incoming_damage(state, *, turn, damage):
    if not state or int(damage) <= 0:
        return []
    if _is_dual_state(state):
        return after_incoming_damage(_active_dual_logic_state(state), turn=turn, damage=damage)
    if not state.get("pending_defense_multiplier"):
        return []
    state["pending_defense_multiplier"] = False
    value = float(state["effect"].get("value") or 0)
    reduced = max(0, int(round(int(damage) * value)))
    state["effect_totals"]["damage_reduced"] += int(reduced)
    return [_record_consume(state, turn, "装甲再編が敵攻撃を受け止め、次回被弾コードを消費した。", consume_type="next_hit_defense", damage_reduced=int(reduced))]


def after_player_attack(state, *, turn, missed, critical, enemy_hp, enemy_max_hp, player_hp, player_max_hp):
    if not state:
        return int(player_hp), []
    if _is_dual_state(state):
        return _run_dual_hook(
            state,
            lambda logic_state: after_player_attack(
                logic_state,
                turn=turn,
                missed=missed,
                critical=critical,
                enemy_hp=enemy_hp,
                enemy_max_hp=enemy_max_hp,
                player_hp=player_hp,
                player_max_hp=player_max_hp,
            ),
            player_hp,
        )
    lines = []
    if state["condition_key"] == "after_miss" and bool(missed):
        _record_condition(state, turn, "攻撃誤差を検出。")
        player_hp, trigger_lines = _activate(state, turn, player_hp, player_max_hp)
        lines.extend(trigger_lines)
    if state["condition_key"] == "after_critical" and bool(critical):
        _record_condition(state, turn, "会心出力を検出。")
        player_hp, trigger_lines = _activate(state, turn, player_hp, player_max_hp)
        lines.extend(trigger_lines)
    if state["condition_key"] == "enemy_low_hp_40" and not state.get("enemy_low_hp_triggered"):
        if int(enemy_hp) * 100 <= int(enemy_max_hp) * 40:
            state["enemy_low_hp_triggered"] = True
            _record_condition(state, turn, "敵機の耐久低下を検出。")
            player_hp, trigger_lines = _activate(state, turn, player_hp, player_max_hp)
            lines.extend(trigger_lines)
    if state["condition_key"] == "low_hp_30":
        player_hp, threshold_lines = turn_start(state, turn, player_hp, player_max_hp, enemy_hp, enemy_max_hp)
        lines.extend(threshold_lines)
    return int(player_hp), lines


def after_player_damage(state, *, turn, player_hp, player_max_hp, enemy_hp, enemy_max_hp):
    if not state:
        return int(player_hp), []
    if _is_dual_state(state):
        return _run_dual_hook(
            state,
            lambda logic_state: after_player_damage(
                logic_state,
                turn=turn,
                player_hp=player_hp,
                player_max_hp=player_max_hp,
                enemy_hp=enemy_hp,
                enemy_max_hp=enemy_max_hp,
            ),
            player_hp,
        )
    return turn_start(state, turn, player_hp, player_max_hp, enemy_hp, enemy_max_hp)


def summary(state):
    if not state:
        return None
    if _is_dual_state(state):
        logic_summaries = []
        events = []
        condition_events = []
        consume_events = []
        totals = {
            "healing_amount": 0,
            "damage_reduced": 0,
            "bonus_damage": 0,
            "guaranteed_hit": 0,
            "critical_bonus": 0,
            "active_turns": 0,
        }
        for logic_state in state.get("logic_states") or []:
            item = summary(logic_state)
            if not item:
                continue
            logic_summaries.append(item)
            events.extend(item.get("events") or [])
            condition_events.extend(item.get("condition_events") or [])
            consume_events.extend(item.get("consume_events") or [])
            for key, value in (item.get("effect_totals") or {}).items():
                totals[key] = int(totals.get(key) or 0) + int(value or 0)
        effect_parts = []
        if totals.get("healing_amount"):
            effect_parts.append(f"実回復 {int(totals['healing_amount'])}")
        if totals.get("guaranteed_hit"):
            effect_parts.append(f"必中適用 {int(totals['guaranteed_hit'])}回")
        if totals.get("critical_bonus"):
            effect_parts.append(f"会心補正 {int(totals['critical_bonus'])}回")
        if totals.get("damage_reduced"):
            effect_parts.append(f"軽減相当 {int(totals['damage_reduced'])}")
        if totals.get("bonus_damage"):
            effect_parts.append(f"追加出力相当 {int(totals['bonus_damage'])}")
        triggered_logic = state.get("resolved_logic_slot")
        triggered_summary = next((item for item in logic_summaries if item.get("logic_slot") == triggered_logic), None)
        return {
            "code_version": "dual",
            "logic_count": 2,
            "display_name": state.get("display_name"),
            "library_id": state.get("library_id"),
            "slot_number": state.get("slot_number"),
            "usage_label": state.get("usage_label"),
            "usage_label_name": state.get("usage_label_name"),
            "logic_entries": list(state.get("logic_entries") or []),
            "logic_summaries": logic_summaries,
            "triggered_logic": triggered_logic,
            "triggered_condition_key": (triggered_summary or {}).get("condition_key"),
            "triggered_effect_key": (triggered_summary or {}).get("effect_key"),
            "activation_count": int(state.get("activation_count") or 0),
            "condition_event_count": sum(int(item.get("condition_event_count") or 0) for item in logic_summaries),
            "activation_turns": list(state.get("activation_turns") or []),
            "events": events,
            "condition_events": condition_events,
            "consume_events": consume_events,
            "effect_totals": totals,
            "effect_summary": " / ".join(effect_parts),
            "not_triggered": int(state.get("activation_count") or 0) <= 0,
            "fallback_success": bool(triggered_logic == "B"),
        }
    totals = dict(state.get("effect_totals") or {})
    effect_parts = []
    if totals.get("healing_amount"):
        effect_parts.append(f"実回復 {int(totals['healing_amount'])}")
    if totals.get("guaranteed_hit"):
        effect_parts.append(f"必中適用 {int(totals['guaranteed_hit'])}回")
    if totals.get("critical_bonus"):
        effect_parts.append(f"会心補正 {int(totals['critical_bonus'])}回")
    if totals.get("damage_reduced"):
        effect_parts.append(f"軽減相当 {int(totals['damage_reduced'])}")
    if totals.get("bonus_damage"):
        effect_parts.append(f"追加出力相当 {int(totals['bonus_damage'])}")
    return {
        "condition_key": state.get("condition_key"),
        "effect_key": state.get("effect_key"),
        "code_version": state.get("code_version") or "single",
        "logic_count": 1,
        "logic_slot": state.get("logic_slot"),
        "display_name": state.get("display_name"),
        "condition_name": state.get("condition_name"),
        "effect_name": state.get("effect_name"),
        "library_id": state.get("library_id"),
        "slot_number": state.get("slot_number"),
        "usage_label": state.get("usage_label"),
        "usage_label_name": state.get("usage_label_name"),
        "activation_count": int(state.get("activation_count") or 0),
        "condition_event_count": int(state.get("condition_event_count") or 0),
        "activation_turns": list(state.get("activation_turns") or []),
        "events": list(state.get("events") or []),
        "condition_events": list(state.get("condition_events") or []),
        "consume_events": list(state.get("consume_events") or []),
        "effect_totals": totals,
        "effect_summary": " / ".join(effect_parts),
        "not_triggered": int(state.get("activation_count") or 0) <= 0,
    }
