import random

from services.simulate_balance import resolve_attack

CHAMPION_FIRST_STRIKE_MODE = "RANDOM_FIRST"
CHAMPION_CRIT_MULTIPLIER = 1.65
CHAMPION_OPENING_CRIT_BONUS = 5


def build_champion_enemy_payload(snapshot_payload):
    payload = dict(snapshot_payload or {})
    stats = dict(payload.get("stats") or {})
    return {
        "name": str(payload.get("robot_name") or "チャンプ機体"),
        "owner_name": str(payload.get("owner_name") or "unknown"),
        "image_url": payload.get("robot_image_url"),
        "signature_label": str(payload.get("signature_label") or "無印"),
        "focus_labels": list(payload.get("focus_labels") or []),
        "focus_label_line": str(payload.get("focus_label_line") or ""),
        "trait_summary": str(payload.get("trait_summary") or ""),
        "style_key": str(payload.get("style_key") or "stable"),
        "focus_line": str(payload.get("focus_line") or ""),
        "robot_instance_id": int(payload.get("robot_instance_id") or 0),
        "user_id": int(payload.get("user_id") or 0),
        "stats": {
            "hp": max(1, int(stats.get("hp") or 1)),
            "atk": max(1, int(stats.get("atk") or 1)),
            "def": max(1, int(stats.get("def") or 1)),
            "spd": max(1, int(stats.get("spd") or 1)),
            "acc": max(1, int(stats.get("acc") or 1)),
            "cri": max(1, int(stats.get("cri") or 1)),
        },
    }


def _battle_timeout_judgement(*, player_hp, player_hp_max, enemy_hp, enemy_hp_max):
    player_ratio = (float(player_hp) / float(max(1, player_hp_max))) if player_hp_max else 0.0
    enemy_ratio = (float(enemy_hp) / float(max(1, enemy_hp_max))) if enemy_hp_max else 0.0
    player_ratio_pct = round(player_ratio * 100.0, 1)
    enemy_ratio_pct = round(enemy_ratio * 100.0, 1)
    player_wins = player_ratio > enemy_ratio
    display_outcome = "判定勝ち" if player_wins else "判定負け"
    result_line = (
        f"8ターン終了。残HP割合 {player_ratio_pct:g}% vs {enemy_ratio_pct:g}% で判定勝ち。"
        if player_wins
        else f"8ターン終了。残HP割合 {player_ratio_pct:g}% vs {enemy_ratio_pct:g}% で判定負け。"
    )
    return {
        "player_wins": bool(player_wins),
        "display_outcome": display_outcome,
        "result_line": result_line,
        "player_ratio_pct": player_ratio_pct,
        "enemy_ratio_pct": enemy_ratio_pct,
    }


def _action_label(*, attacker_name, damage, critical, miss, is_finisher=False):
    if miss:
        return f"{attacker_name}の攻撃はMISS"
    if critical:
        return f"{attacker_name}の会心"
    if is_finisher:
        return f"{attacker_name}の決着打"
    return f"{attacker_name}の攻撃"


def _summary_label(*, win, timeout, player_stats, enemy_stats, critical_hits):
    if timeout and win:
        return "装甲差で競り勝った"
    if timeout and not win:
        return "時間切れ判定で届かなかった"
    if critical_hits >= 2:
        return "爆発力で押し切った" if win else "爆発力を受け切れなかった"
    if int(player_stats.get("acc") or 0) >= int(enemy_stats.get("acc") or 0) + 2:
        return "命中安定で崩した" if win else "命中差を返せなかった"
    if (int(player_stats.get("hp") or 0) + int(player_stats.get("def") or 0)) >= (
        int(enemy_stats.get("hp") or 0) + int(enemy_stats.get("def") or 0)
    ):
        return "体勢維持で受け切った" if win else "削り切る前に崩れた"
    return "主導権を握って押し切った" if win else "主導権を奪い返せなかった"


def _payload_prefers_critical(payload):
    data = dict(payload or {})
    signature = str(data.get("signature_label") or "").strip()
    if "会心" in signature:
        return True
    for label in list(data.get("focus_labels") or []):
        if "会心" in str(label or ""):
            return True
    return False


def _effective_crit(payload, attack_count, base_cri):
    if attack_count <= 0 and _payload_prefers_critical(payload):
        return int(base_cri) + int(CHAMPION_OPENING_CRIT_BONUS)
    return int(base_cri)


def run_champion_battle(player_payload, champion_payload, *, max_turns=8, rng=None):
    roller = rng or random.Random()
    player_name = str(player_payload.get("name") or "あなた")
    enemy_name = str(champion_payload.get("name") or "チャンプ機体")
    player_stats = dict(player_payload.get("stats") or {})
    enemy_stats = dict(champion_payload.get("stats") or {})
    player_hp_max = max(1, int(player_stats.get("hp") or 1))
    enemy_hp_max = max(1, int(enemy_stats.get("hp") or 1))
    player_hp = int(player_hp_max)
    enemy_hp = int(enemy_hp_max)
    critical_hits = 0
    turn_logs = []
    first_turn_striker = None
    player_attack_count = 0
    enemy_attack_count = 0

    for turn in range(1, int(max_turns) + 1):
        enemy_before = int(enemy_hp)
        player_before = int(player_hp)
        player_damage = 0
        enemy_damage = 0
        critical = False
        player_action = "様子を見る"
        enemy_action = "様子を見る"

        player_first = bool(roller.random() < 0.5)
        if int(turn) == 1:
            first_turn_striker = "player" if player_first else "champion"
        if player_first:
            player_damage, critical = resolve_attack(
                int(player_stats.get("atk") or 0),
                int(player_stats.get("acc") or 0),
                _effective_crit(player_payload, player_attack_count, int(player_stats.get("cri") or 0)),
                int(enemy_stats.get("def") or 0),
                int(enemy_stats.get("acc") or 0),
                rng=roller,
                crit_multiplier=CHAMPION_CRIT_MULTIPLIER,
            )
            player_attack_count += 1
            enemy_hp = max(0, enemy_hp - int(player_damage))
            if critical:
                critical_hits += 1
            player_action = _action_label(
                attacker_name=player_name,
                damage=player_damage,
                critical=critical,
                miss=int(player_damage) <= 0,
                is_finisher=enemy_hp == 0,
            )
            if enemy_hp > 0:
                enemy_damage, enemy_critical = resolve_attack(
                    int(enemy_stats.get("atk") or 0),
                    int(enemy_stats.get("acc") or 0),
                    _effective_crit(champion_payload, enemy_attack_count, int(enemy_stats.get("cri") or 0)),
                    int(player_stats.get("def") or 0),
                    int(player_stats.get("acc") or 0),
                    rng=roller,
                    crit_multiplier=CHAMPION_CRIT_MULTIPLIER,
                )
                enemy_attack_count += 1
                player_hp = max(0, player_hp - int(enemy_damage))
                enemy_action = _action_label(
                    attacker_name=enemy_name,
                    damage=enemy_damage,
                    critical=bool(enemy_critical),
                    miss=int(enemy_damage) <= 0,
                    is_finisher=player_hp == 0,
                )
        else:
            enemy_damage, enemy_critical = resolve_attack(
                int(enemy_stats.get("atk") or 0),
                int(enemy_stats.get("acc") or 0),
                _effective_crit(champion_payload, enemy_attack_count, int(enemy_stats.get("cri") or 0)),
                int(player_stats.get("def") or 0),
                int(player_stats.get("acc") or 0),
                rng=roller,
                crit_multiplier=CHAMPION_CRIT_MULTIPLIER,
            )
            enemy_attack_count += 1
            player_hp = max(0, player_hp - int(enemy_damage))
            enemy_action = _action_label(
                attacker_name=enemy_name,
                damage=enemy_damage,
                critical=bool(enemy_critical),
                miss=int(enemy_damage) <= 0,
                is_finisher=player_hp == 0,
            )
            if player_hp > 0:
                player_damage, critical = resolve_attack(
                    int(player_stats.get("atk") or 0),
                    int(player_stats.get("acc") or 0),
                    _effective_crit(player_payload, player_attack_count, int(player_stats.get("cri") or 0)),
                    int(enemy_stats.get("def") or 0),
                    int(enemy_stats.get("acc") or 0),
                    rng=roller,
                    crit_multiplier=CHAMPION_CRIT_MULTIPLIER,
                )
                player_attack_count += 1
                enemy_hp = max(0, enemy_hp - int(player_damage))
                if critical:
                    critical_hits += 1
                player_action = _action_label(
                    attacker_name=player_name,
                    damage=player_damage,
                    critical=critical,
                    miss=int(player_damage) <= 0,
                    is_finisher=enemy_hp == 0,
                )

        result_line = None
        if enemy_hp == 0:
            result_line = f"{enemy_name}を撃破！"
        elif player_hp == 0:
            result_line = f"{player_name}は力尽きた。"
        turn_logs.append(
            {
                "turn": int(turn),
                "battle_no": 1,
                "player_before": int(player_before),
                "player_after": int(player_hp),
                "enemy_before": int(enemy_before),
                "enemy_after": int(enemy_hp),
                "player_damage": int(player_damage),
                "enemy_damage": int(enemy_damage),
                "player_max": int(player_hp_max),
                "enemy_max": int(enemy_hp_max),
                "player_action": player_action,
                "enemy_action": enemy_action,
                "critical": bool(critical),
                "result_line": result_line,
            }
        )
        if enemy_hp == 0 or player_hp == 0:
            break

    timeout = enemy_hp > 0 and player_hp > 0 and len(turn_logs) >= int(max_turns)
    timeout_decision = None
    player_win = enemy_hp == 0
    outcome_display = "勝利" if player_win else "敗北"
    if timeout:
        timeout_decision = _battle_timeout_judgement(
            player_hp=player_hp,
            player_hp_max=player_hp_max,
            enemy_hp=enemy_hp,
            enemy_hp_max=enemy_hp_max,
        )
        player_win = bool(timeout_decision["player_wins"])
        outcome_display = str(timeout_decision["display_outcome"])
        if turn_logs:
            turn_logs[-1]["result_line"] = str(timeout_decision["result_line"])
    summary_heading = "今回の勝ち筋" if player_win else "今回の崩れ筋"
    summary_label = _summary_label(
        win=bool(player_win),
        timeout=bool(timeout),
        player_stats=player_stats,
        enemy_stats=enemy_stats,
        critical_hits=int(critical_hits),
    )
    result_label = "WIN" if player_win else "LOSE"
    return {
        "win": bool(player_win),
        "outcome": outcome_display,
        "timeout": bool(timeout),
        "timeout_decision": timeout_decision,
        "turn_count": len(turn_logs),
        "turn_logs": turn_logs,
        "player_final_hp": int(player_hp),
        "player_max_hp": int(player_hp_max),
        "enemy_final_hp": int(enemy_hp),
        "enemy_max_hp": int(enemy_hp_max),
        "summary_heading": summary_heading,
        "summary_label": summary_label,
        "result_label": result_label,
        "critical_hits": int(critical_hits),
        "first_striker": first_turn_striker,
        "first_strike_mode": CHAMPION_FIRST_STRIKE_MODE,
        "crit_multiplier": float(CHAMPION_CRIT_MULTIPLIER),
    }
