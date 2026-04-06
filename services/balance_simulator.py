import csv
import io
import math
import random

from services.balance_templates import BALANCE_FAMILY_LABELS, BALANCE_FAMILY_ORDER
from services.simulate_balance import resolve_attack


DEFAULT_MAX_TURNS = 8
DEFAULT_SERIES_SEED_BASE = 1000
BASE_CRIT_MULTIPLIER = 1.5


def _normalize_build_type(value):
    raw = str(value or "").strip().upper()
    if raw in {"BURST", "BERSERK", "STABLE"}:
        return raw
    return "STABLE"


def _robot_stats(robot):
    data = dict((robot or {}).get("stats") or {})
    return {
        "hp": max(1, int(data.get("hp") or 1)),
        "atk": max(1, int(data.get("atk") or 1)),
        "def": max(1, int(data.get("def") or 1)),
        "spd": max(1, int(data.get("spd") or 1)),
        "acc": max(1, int(data.get("acc") or 1)),
        "cri": max(1, int(data.get("cri") or 1)),
    }


def _robot_meta(robot, fallback_key):
    return {
        "key": str((robot or {}).get("key") or fallback_key),
        "label": str((robot or {}).get("label") or (robot or {}).get("key") or fallback_key),
        "family": str((robot or {}).get("family") or fallback_key),
        "family_label": str(
            (robot or {}).get("family_label")
            or BALANCE_FAMILY_LABELS.get(str((robot or {}).get("family") or fallback_key), str((robot or {}).get("family") or fallback_key))
        ),
        "build_type": _normalize_build_type((robot or {}).get("build_type")),
        "sim_archetype": (robot or {}).get("sim_archetype"),
    }


def _damage_noise_range(build_type):
    if build_type == "BURST":
        return (0.80, 1.25)
    return (0.95, 1.05)


def _crit_multiplier(build_type):
    return BASE_CRIT_MULTIPLIER * 1.15 if build_type == "BURST" else BASE_CRIT_MULTIPLIER


def _hp_max_for_build_type(build_type, base_hp):
    hp = max(1, int(base_hp or 1))
    if build_type == "BERSERK":
        return max(1, int(math.floor(hp * 0.85)))
    return hp


def _berserk_attack_bonus(build_type, hp_current, hp_max):
    if build_type != "BERSERK":
        return 0.0
    hp_max_safe = max(1, int(hp_max or 1))
    missing = max(0.0, 1.0 - (float(max(0, int(hp_current))) / float(hp_max_safe)))
    return min(0.30, missing * 0.60)


def _timeout_judgement(a_hp, a_hp_max, b_hp, b_hp_max):
    a_ratio = float(a_hp) / float(max(1, int(a_hp_max or 1)))
    b_ratio = float(b_hp) / float(max(1, int(b_hp_max or 1)))
    if abs(a_ratio - b_ratio) < 1e-9 and int(a_hp) == int(b_hp):
        winner = "draw"
    elif a_ratio > b_ratio:
        winner = "a"
    elif b_ratio > a_ratio:
        winner = "b"
    else:
        winner = "draw"
    return {
        "winner": winner,
        "a_ratio": a_ratio,
        "b_ratio": b_ratio,
    }


def _empty_side_metrics():
    return {
        "attacks": 0,
        "hits": 0,
        "misses": 0,
        "critical_hits": 0,
        "damage_dealt": 0,
        "damage_taken": 0,
        "berserk_activations": 0,
        "berserk_triggered": False,
    }


def _match_signature(result):
    return {
        "winner": result.get("winner"),
        "turns": int(result.get("turns") or 0),
        "timeout": bool(result.get("timeout")),
        "a_hp_final": int((result.get("a") or {}).get("hp_final") or 0),
        "b_hp_final": int((result.get("b") or {}).get("hp_final") or 0),
        "a_damage": int((result.get("a") or {}).get("damage_dealt") or 0),
        "b_damage": int((result.get("b") or {}).get("damage_dealt") or 0),
        "a_crit": int((result.get("a") or {}).get("critical_hits") or 0),
        "b_crit": int((result.get("b") or {}).get("critical_hits") or 0),
        "a_miss": int((result.get("a") or {}).get("misses") or 0),
        "b_miss": int((result.get("b") or {}).get("misses") or 0),
    }


def _simulate_attack(attacker, defender, *, first_striker, rng):
    att_stats = attacker["stats"]
    def_stats = defender["stats"]
    build_type = attacker["meta"]["build_type"]
    effective_atk = int(att_stats["atk"])
    berserk_bonus = _berserk_attack_bonus(build_type, attacker["hp"], attacker["hp_max"])
    berserk_active = berserk_bonus > 0.0
    if berserk_active:
        effective_atk = max(1, int(round(effective_atk * (1.0 + berserk_bonus))))
        attacker["metrics"]["berserk_activations"] += 1
        attacker["metrics"]["berserk_triggered"] = True

    damage, critical, detail = resolve_attack(
        effective_atk,
        int(att_stats["acc"]),
        int(att_stats["cri"]),
        int(def_stats["def"]),
        int(def_stats["acc"]),
        rng=rng,
        attacker_archetype=attacker["meta"]["sim_archetype"],
        defender_archetype=defender["meta"]["sim_archetype"],
        attacker_is_first_striker=bool(first_striker),
        crit_multiplier=_crit_multiplier(build_type),
        damage_noise_range=_damage_noise_range(build_type),
        return_detail=True,
    )

    attacker["metrics"]["attacks"] += 1
    if detail.get("miss"):
        attacker["metrics"]["misses"] += 1
        damage = 0
    else:
        attacker["metrics"]["hits"] += 1
    if critical:
        attacker["metrics"]["critical_hits"] += 1

    defender["hp"] = max(0, int(defender["hp"]) - int(damage))
    attacker["metrics"]["damage_dealt"] += int(damage)
    defender["metrics"]["damage_taken"] += int(damage)
    return {
        "damage": int(damage),
        "critical": bool(critical),
        "miss": bool(detail.get("miss")),
        "berserk_active": bool(berserk_active),
    }


def simulate_match(robot_a, robot_b, seed=None, max_turns=DEFAULT_MAX_TURNS):
    rng = random.Random(seed) if seed is not None else random.Random()
    a_meta = _robot_meta(robot_a, "robot_a")
    b_meta = _robot_meta(robot_b, "robot_b")
    a_stats = _robot_stats(robot_a)
    b_stats = _robot_stats(robot_b)
    a_hp_max = _hp_max_for_build_type(a_meta["build_type"], a_stats["hp"])
    b_hp_max = _hp_max_for_build_type(b_meta["build_type"], b_stats["hp"])
    state_a = {
        "meta": a_meta,
        "stats": a_stats,
        "hp_max": a_hp_max,
        "hp": int(a_hp_max),
        "metrics": _empty_side_metrics(),
    }
    state_b = {
        "meta": b_meta,
        "stats": b_stats,
        "hp_max": b_hp_max,
        "hp": int(b_hp_max),
        "metrics": _empty_side_metrics(),
    }

    first_striker = "a" if int(a_stats["spd"]) >= int(b_stats["spd"]) else "b"
    turns = 0
    attack_events = []
    for turn in range(1, int(max_turns) + 1):
        turns = turn
        if first_striker == "a":
            event_a = _simulate_attack(state_a, state_b, first_striker=True, rng=rng)
            attack_events.append({"actor": "a", **event_a})
            if state_b["hp"] > 0:
                event_b = _simulate_attack(state_b, state_a, first_striker=False, rng=rng)
                attack_events.append({"actor": "b", **event_b})
        else:
            event_b = _simulate_attack(state_b, state_a, first_striker=True, rng=rng)
            attack_events.append({"actor": "b", **event_b})
            if state_a["hp"] > 0:
                event_a = _simulate_attack(state_a, state_b, first_striker=False, rng=rng)
                attack_events.append({"actor": "a", **event_a})
        if state_a["hp"] == 0 or state_b["hp"] == 0:
            break

    timeout = state_a["hp"] > 0 and state_b["hp"] > 0 and turns >= int(max_turns)
    timeout_decision = None
    if state_b["hp"] == 0 and state_a["hp"] == 0:
        winner = "draw"
    elif state_b["hp"] == 0:
        winner = "a"
    elif state_a["hp"] == 0:
        winner = "b"
    elif timeout:
        timeout_decision = _timeout_judgement(state_a["hp"], state_a["hp_max"], state_b["hp"], state_b["hp_max"])
        winner = str(timeout_decision["winner"])
    else:
        winner = "draw"

    return {
        "seed": seed,
        "winner": winner,
        "turns": int(turns),
        "timeout": bool(timeout),
        "timeout_decision": timeout_decision,
        "first_striker": first_striker,
        "attack_events": attack_events,
        "a": {
            **state_a["meta"],
            **state_a["metrics"],
            "hp_final": int(state_a["hp"]),
            "hp_max": int(state_a["hp_max"]),
        },
        "b": {
            **state_b["meta"],
            **state_b["metrics"],
            "hp_final": int(state_b["hp"]),
            "hp_max": int(state_b["hp_max"]),
        },
    }


def _base_series_record(robot_a, robot_b, n, seed_base):
    a_meta = _robot_meta(robot_a, "robot_a")
    b_meta = _robot_meta(robot_b, "robot_b")
    return {
        "a_template_key": a_meta["key"],
        "a_template_label": a_meta["label"],
        "a_family": a_meta["family"],
        "a_family_label": a_meta["family_label"],
        "b_template_key": b_meta["key"],
        "b_template_label": b_meta["label"],
        "b_family": b_meta["family"],
        "b_family_label": b_meta["family_label"],
        "total_trials": int(n),
        "seed_base": int(seed_base if seed_base is not None else DEFAULT_SERIES_SEED_BASE),
        "a_wins": 0,
        "b_wins": 0,
        "draws": 0,
        "timeouts": 0,
        "total_turns": 0,
        "total_first_strike_a": 0,
        "total_first_strike_b": 0,
        "total_damage_dealt_a": 0,
        "total_damage_dealt_b": 0,
        "total_damage_taken_a": 0,
        "total_damage_taken_b": 0,
        "total_attacks_a": 0,
        "total_attacks_b": 0,
        "total_critical_hits_a": 0,
        "total_critical_hits_b": 0,
        "total_misses_a": 0,
        "total_misses_b": 0,
        "total_berserk_trigger_matches_a": 0,
        "total_berserk_trigger_matches_b": 0,
    }


def _finalize_series_record(record):
    total = max(1, int(record["total_trials"]))
    record["a_win_rate"] = float(record["a_wins"]) / float(total)
    record["b_win_rate"] = float(record["b_wins"]) / float(total)
    record["draw_rate"] = float(record["draws"]) / float(total)
    record["avg_turns"] = float(record["total_turns"]) / float(total)
    record["a_first_strike_rate"] = float(record["total_first_strike_a"]) / float(total)
    record["b_first_strike_rate"] = float(record["total_first_strike_b"]) / float(total)
    record["avg_damage_dealt_a"] = float(record["total_damage_dealt_a"]) / float(total)
    record["avg_damage_dealt_b"] = float(record["total_damage_dealt_b"]) / float(total)
    record["avg_damage_taken_a"] = float(record["total_damage_taken_a"]) / float(total)
    record["avg_damage_taken_b"] = float(record["total_damage_taken_b"]) / float(total)
    record["timeout_rate"] = float(record["timeouts"]) / float(total)
    record["berserk_trigger_rate_a"] = float(record["total_berserk_trigger_matches_a"]) / float(total)
    record["berserk_trigger_rate_b"] = float(record["total_berserk_trigger_matches_b"]) / float(total)

    attacks_a = max(1, int(record["total_attacks_a"]))
    attacks_b = max(1, int(record["total_attacks_b"]))
    record["crit_rate_a"] = float(record["total_critical_hits_a"]) / float(attacks_a)
    record["crit_rate_b"] = float(record["total_critical_hits_b"]) / float(attacks_b)
    record["miss_rate_a"] = float(record["total_misses_a"]) / float(attacks_a)
    record["miss_rate_b"] = float(record["total_misses_b"]) / float(attacks_b)
    return record


def simulate_series(robot_a, robot_b, n=1000, seed_base=DEFAULT_SERIES_SEED_BASE, max_turns=DEFAULT_MAX_TURNS):
    total_trials = max(1, int(n or 1))
    base_seed = int(seed_base if seed_base is not None else DEFAULT_SERIES_SEED_BASE)
    record = _base_series_record(robot_a, robot_b, total_trials, base_seed)
    sample_result = None
    for idx in range(total_trials):
        match_seed = base_seed + idx
        result = simulate_match(robot_a, robot_b, seed=match_seed, max_turns=max_turns)
        if sample_result is None:
            sample_result = result
        if result["winner"] == "a":
            record["a_wins"] += 1
        elif result["winner"] == "b":
            record["b_wins"] += 1
        else:
            record["draws"] += 1
        if result["timeout"]:
            record["timeouts"] += 1
        if result["first_striker"] == "a":
            record["total_first_strike_a"] += 1
        else:
            record["total_first_strike_b"] += 1
        record["total_turns"] += int(result["turns"] or 0)
        record["total_damage_dealt_a"] += int((result["a"] or {}).get("damage_dealt") or 0)
        record["total_damage_dealt_b"] += int((result["b"] or {}).get("damage_dealt") or 0)
        record["total_damage_taken_a"] += int((result["a"] or {}).get("damage_taken") or 0)
        record["total_damage_taken_b"] += int((result["b"] or {}).get("damage_taken") or 0)
        record["total_attacks_a"] += int((result["a"] or {}).get("attacks") or 0)
        record["total_attacks_b"] += int((result["b"] or {}).get("attacks") or 0)
        record["total_critical_hits_a"] += int((result["a"] or {}).get("critical_hits") or 0)
        record["total_critical_hits_b"] += int((result["b"] or {}).get("critical_hits") or 0)
        record["total_misses_a"] += int((result["a"] or {}).get("misses") or 0)
        record["total_misses_b"] += int((result["b"] or {}).get("misses") or 0)
        if (result["a"] or {}).get("berserk_triggered"):
            record["total_berserk_trigger_matches_a"] += 1
        if (result["b"] or {}).get("berserk_triggered"):
            record["total_berserk_trigger_matches_b"] += 1

    verify_seed = base_seed
    record["seed_check"] = {
        "sample_seed": verify_seed,
        "verified": _match_signature(simulate_match(robot_a, robot_b, seed=verify_seed, max_turns=max_turns))
        == _match_signature(simulate_match(robot_a, robot_b, seed=verify_seed, max_turns=max_turns)),
        "sample_result": _match_signature(sample_result) if sample_result else {},
    }
    return _finalize_series_record(record)


def _normalize_template_catalog(robot_templates):
    if isinstance(robot_templates, dict):
        catalog = {}
        for family_key, items in robot_templates.items():
            catalog[str(family_key)] = [dict(item) for item in list(items or [])]
        return catalog

    catalog = {}
    for item in list(robot_templates or []):
        family_key = str((item or {}).get("family") or "unknown")
        catalog.setdefault(family_key, []).append(dict(item))
    return catalog


def _aggregate_series_records(series_rows, *, a_family, b_family):
    aggregate = {
        "a_family": a_family,
        "a_family_label": BALANCE_FAMILY_LABELS.get(a_family, a_family),
        "b_family": b_family,
        "b_family_label": BALANCE_FAMILY_LABELS.get(b_family, b_family),
        "variant_pair_count": len(series_rows),
        "total_trials": 0,
        "seed_base": None,
        "a_wins": 0,
        "b_wins": 0,
        "draws": 0,
        "timeouts": 0,
        "total_turns": 0,
        "total_first_strike_a": 0,
        "total_first_strike_b": 0,
        "total_damage_dealt_a": 0,
        "total_damage_dealt_b": 0,
        "total_damage_taken_a": 0,
        "total_damage_taken_b": 0,
        "total_attacks_a": 0,
        "total_attacks_b": 0,
        "total_critical_hits_a": 0,
        "total_critical_hits_b": 0,
        "total_misses_a": 0,
        "total_misses_b": 0,
        "total_berserk_trigger_matches_a": 0,
        "total_berserk_trigger_matches_b": 0,
    }
    for row in series_rows:
        for key in (
            "total_trials",
            "a_wins",
            "b_wins",
            "draws",
            "timeouts",
            "total_turns",
            "total_first_strike_a",
            "total_first_strike_b",
            "total_damage_dealt_a",
            "total_damage_dealt_b",
            "total_damage_taken_a",
            "total_damage_taken_b",
            "total_attacks_a",
            "total_attacks_b",
            "total_critical_hits_a",
            "total_critical_hits_b",
            "total_misses_a",
            "total_misses_b",
            "total_berserk_trigger_matches_a",
            "total_berserk_trigger_matches_b",
        ):
            aggregate[key] += int(row.get(key) or 0)
    return _finalize_series_record(aggregate)


def summarize_matchup_results(report):
    family_rows = list((report or {}).get("family_matchups") or [])
    rows_by_family = {}
    for row in family_rows:
        rows_by_family.setdefault(str(row.get("a_family")), []).append(row)

    family_overall = []
    for family_key, rows in rows_by_family.items():
        non_self = [row for row in rows if str(row.get("b_family")) != family_key]
        target_rows = non_self or rows
        total_trials = sum(int(row.get("total_trials") or 0) for row in target_rows)
        total_wins = sum(int(row.get("a_wins") or 0) for row in target_rows)
        overall_rate = (float(total_wins) / float(max(1, total_trials))) if target_rows else 0.0
        family_overall.append(
            {
                "family": family_key,
                "family_label": BALANCE_FAMILY_LABELS.get(family_key, family_key),
                "overall_win_rate": overall_rate,
                "best_matchup": max(target_rows, key=lambda row: float(row.get("a_win_rate") or 0.0)) if target_rows else None,
                "worst_matchup": min(target_rows, key=lambda row: float(row.get("a_win_rate") or 0.0)) if target_rows else None,
            }
        )

    danger_matchups = [
        row
        for row in family_rows
        if str(row.get("a_family")) != str(row.get("b_family")) and float(row.get("a_win_rate") or 0.0) >= 0.75
    ]
    dead_families = [row for row in family_overall if float(row.get("overall_win_rate") or 0.0) <= 0.40]
    omni_candidates = []
    role_visible = []
    for row in family_overall:
        family_key = str(row["family"])
        non_self = [item for item in rows_by_family.get(family_key, []) if str(item.get("b_family")) != family_key]
        if not non_self:
            continue
        worst = min(float(item.get("a_win_rate") or 0.0) for item in non_self)
        best = max(float(item.get("a_win_rate") or 0.0) for item in non_self)
        overall = float(row.get("overall_win_rate") or 0.0)
        if overall >= 0.60 and worst >= 0.50:
            omni_candidates.append(row)
        if best >= 0.55 and worst <= 0.45:
            role_visible.append(
                {
                    **row,
                    "best_rate": best,
                    "worst_rate": worst,
                }
            )

    use_case_notes = {
        "tank": "ボス向き・受け性能確認向き。爆発型や背水型を止められるかを見る。",
        "stable": "周回向き。事故率と取りこぼしの少なさを確認する基準。",
        "accuracy": "模擬戦向き。高速・不安定・会心型に役割があるかを見る。",
        "crit": "記録向き。上振れ勝ちがどこまで現実的かを確認する。",
        "burst": "最速突破向き。短期決戦の圧力と耐久相手への弱さを見る。",
        "berserk": "刺さり対面向き。消えすぎず一強でもない位置を狙う。",
        "balance": "初心者向き・汎用向き。万能だが最終最強でないかを確認する。",
    }
    return {
        "danger_matchups": danger_matchups,
        "dead_families": dead_families,
        "omni_candidates": omni_candidates,
        "role_visible_families": role_visible,
        "family_overall": family_overall,
        "use_case_notes": use_case_notes,
    }


def simulate_all_matchups(robot_templates, n=1000, seed_base=DEFAULT_SERIES_SEED_BASE, max_turns=DEFAULT_MAX_TURNS):
    catalog = _normalize_template_catalog(robot_templates)
    family_keys = [key for key in BALANCE_FAMILY_ORDER if key in catalog] + [
        key for key in sorted(catalog.keys()) if key not in BALANCE_FAMILY_ORDER
    ]
    variant_results = []
    family_matchups = []
    matrix = {}
    pair_index = 0
    for a_family in family_keys:
        matrix.setdefault(a_family, {})
        for b_family in family_keys:
            series_rows = []
            for a_variant in catalog.get(a_family, []):
                for b_variant in catalog.get(b_family, []):
                    pair_seed = int(seed_base if seed_base is not None else DEFAULT_SERIES_SEED_BASE) + (pair_index * 100000)
                    pair_index += 1
                    row = simulate_series(
                        a_variant,
                        b_variant,
                        n=n,
                        seed_base=pair_seed,
                        max_turns=max_turns,
                    )
                    variant_results.append(row)
                    series_rows.append(row)
            aggregate = _aggregate_series_records(series_rows, a_family=a_family, b_family=b_family)
            family_matchups.append(aggregate)
            matrix[a_family][b_family] = {
                "a_win_rate": float(aggregate.get("a_win_rate") or 0.0),
                "b_win_rate": float(aggregate.get("b_win_rate") or 0.0),
                "draw_rate": float(aggregate.get("draw_rate") or 0.0),
                "avg_turns": float(aggregate.get("avg_turns") or 0.0),
            }

    report = {
        "n": int(n),
        "seed_base": int(seed_base if seed_base is not None else DEFAULT_SERIES_SEED_BASE),
        "family_order": family_keys,
        "variant_results": variant_results,
        "family_matchups": family_matchups,
        "family_matrix": matrix,
    }
    report["summary"] = summarize_matchup_results(report)
    return report


def export_matchup_matrix(report, format="csv"):
    fmt = str(format or "csv").strip().lower()
    if fmt != "csv":
        raise ValueError("export_matchup_matrix currently supports only csv")
    family_order = list((report or {}).get("family_order") or [])
    matrix = dict((report or {}).get("family_matrix") or {})
    out = io.StringIO()
    writer = csv.writer(out)
    header = ["type"] + [BALANCE_FAMILY_LABELS.get(key, key) for key in family_order]
    writer.writerow(header)
    for row_key in family_order:
        row = [BALANCE_FAMILY_LABELS.get(row_key, row_key)]
        for col_key in family_order:
            cell = ((matrix.get(row_key) or {}).get(col_key) or {})
            row.append(f"{float(cell.get('a_win_rate') or 0.0):.4f}")
        writer.writerow(row)
    return out.getvalue()
