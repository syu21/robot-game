import random

from services.lab_race_course import LAB_RACE_GOAL


LAB_RACE_FRAME_MS = 320
LAB_RACE_TOTAL_FRAMES = 82


EVENT_LABELS = {
    "boost": "加速",
    "slip": "スリップ",
    "hit_bar": "激突",
    "warp": "ワープ",
    "slow": "減速",
    "reverse": "逆走",
    "pitfall": "落下",
    "finish": "完走",
    "dash": "会心ダッシュ",
    "clash": "接触",
    "recover": "立て直し",
    "run": "巡航",
}


ROLE_RISK = {
    "speed": 0.09,
    "tank": -0.03,
    "chaos": 0.13,
    "balanced": 0.0,
    "heavy": -0.02,
    "miracle": 0.06,
}


ROLE_DASH = {
    "speed": 0.03,
    "tank": -0.01,
    "chaos": 0.05,
    "balanced": 0.0,
    "heavy": -0.01,
    "miracle": 0.06,
}


ROLE_PUSH = {
    "speed": 0.08,
    "tank": 0.02,
    "chaos": 0.12,
    "balanced": 0.04,
    "heavy": 0.06,
    "miracle": 0.02,
}


def _chance(base, *mods):
    value = float(base)
    for mod in mods:
        value += float(mod)
    return max(0.01, min(0.92, value))


def _segment_index_for(progress, course):
    segments = course.get("segments") or ()
    if not segments:
        return 0
    size = float(course.get("segment_size") or (LAB_RACE_GOAL / max(1, len(segments))))
    index = int(max(0.0, float(progress)) / max(0.01, size))
    return max(0, min(len(segments) - 1, index))


def _event_payload(entry_order, event_type, label, *, segment_index=None):
    payload = {"entry_order": int(entry_order), "type": str(event_type), "label": str(label)}
    if segment_index is not None:
        payload["segment_index"] = int(segment_index)
    return payload


def _normalize_entry(entry, lane_index):
    item = dict(entry)
    acc = int(item.get("acc") or 10)
    cri = int(item.get("cri") or 8)
    item["hp"] = int(item.get("hp") or 18)
    item["atk"] = int(item.get("atk") or 10)
    item["def"] = int(item.get("def") or 10)
    item["spd"] = int(item.get("spd") or 10)
    item["acc"] = acc
    item["cri"] = cri
    item["luck"] = int(item.get("luck") or round((acc * 0.6) + (cri * 0.4)))
    item["role_type"] = str(item.get("role_type") or "balanced")
    item["lane_index"] = int(item.get("lane_index") if item.get("lane_index") is not None else lane_index)
    item["entry_order"] = int(item.get("entry_order") or (lane_index + 1))
    item["display_name"] = str(item.get("display_name") or f"Entry-{lane_index + 1}")
    return item


def simulate_race(entries, seed, course, *, mode="standard"):
    roster = [_normalize_entry(item, idx) for idx, item in enumerate(entries or ())]
    if not roster:
        return {"frames": [], "results": [], "summary": {"winner_upset": False}}

    rng = random.Random(f"lab-race-sim:{mode}:{course.get('key', 'course')}:{int(seed)}")
    max_stats = {
        key: max(1, max(int(item.get(key) or 1) for item in roster))
        for key in ("hp", "atk", "def", "spd", "acc", "cri", "luck")
    }
    states = []
    for idx, item in enumerate(roster):
        states.append(
            {
                "entry_order": int(item["entry_order"]),
                "lane_index": int(item["lane_index"]),
                "progress": 0.0,
                "recover": 0,
                "state": "run",
                "last_delta": 0.0,
                "finish_time_ms": None,
                "accident_count": 0,
                "dash_count": 0,
                "best_rank": len(roster),
                "worst_rank": 1,
                "obstacles_done": set(),
            }
        )

    frames = []
    for frame_no in range(LAB_RACE_TOTAL_FRAMES):
        frame_events = []
        order_before = sorted(states, key=lambda row: (-float(row["progress"]), int(row["entry_order"])))
        rank_before = {int(state["entry_order"]): rank for rank, state in enumerate(order_before, start=1)}
        leader_progress = float(order_before[0]["progress"]) if order_before else 0.0
        for rank_index, state in enumerate(order_before, start=1):
            state["best_rank"] = min(int(state["best_rank"]), rank_index)
            state["worst_rank"] = max(int(state["worst_rank"]), rank_index)

        for state, item in zip(states, roster):
            if state["finish_time_ms"] is not None:
                state["state"] = "finish"
                continue

            role_type = str(item.get("role_type") or "balanced")
            hp_factor = float(item["hp"]) / max_stats["hp"]
            atk_factor = float(item["atk"]) / max_stats["atk"]
            def_factor = float(item["def"]) / max_stats["def"]
            spd_factor = float(item["spd"]) / max_stats["spd"]
            acc_factor = float(item["acc"]) / max_stats["acc"]
            cri_factor = float(item["cri"]) / max_stats["cri"]
            luck_factor = float(item["luck"]) / max_stats["luck"]

            progress_before = float(state["progress"])
            rank_now = int(rank_before[int(state["entry_order"])])
            gap_to_leader = max(0.0, leader_progress - progress_before)
            segment_index = _segment_index_for(progress_before, course)
            segment = course["segments"][segment_index]
            effect_params = dict(segment.get("effect_params") or {})

            if int(state["recover"]) > 0:
                state["recover"] = max(0, int(state["recover"]) - 1)
                delta = 0.20 + hp_factor * 0.16 + def_factor * 0.16 + max(0.0, float(effect_params.get("pace", 0.0)) * 0.25)
                state["progress"] += delta
                state["last_delta"] = delta
                state["state"] = "recover"
                continue

            delta = 0.56
            delta += spd_factor * 0.46
            delta += acc_factor * 0.08
            delta += luck_factor * 0.04
            delta -= def_factor * 0.04
            delta += float(effect_params.get("pace", 0.0))
            delta += rng.uniform(-0.16, 0.30 + float(effect_params.get("chaos", 0.0)) * 0.18)

            if frame_no < 18:
                delta += min(0.18, gap_to_leader * 0.04)
                if rank_now == 1:
                    delta -= 0.07
            elif 18 <= frame_no < 56:
                delta += rng.uniform(-0.04, float(effect_params.get("chaos", 0.0)) * 0.22)
            else:
                delta += max(0, rank_now - 2) * 0.025
                delta += cri_factor * float(effect_params.get("dash_bias", 0.0)) * 0.28

            if segment_index >= len(course["segments"]) - 2:
                delta += 0.03 + cri_factor * 0.04 + max(0, rank_now - 3) * 0.02

            dash_chance = _chance(
                0.012,
                cri_factor * 0.05,
                luck_factor * 0.03,
                ROLE_DASH.get(role_type, 0.0),
                float(effect_params.get("dash_bias", 0.0)),
            )
            if rng.random() < dash_chance:
                dash = 0.68 + cri_factor * 0.58 + spd_factor * 0.20 + luck_factor * 0.18 + rng.uniform(0.0, 0.32)
                delta += dash
                state["dash_count"] += 1
                state["state"] = "boost"
                frame_events.append(_event_payload(state["entry_order"], "dash", EVENT_LABELS["dash"], segment_index=segment_index))
            else:
                state["state"] = "run"

            delta = max(0.16, delta)
            state["progress"] += delta
            state["last_delta"] = delta

            for obstacle in course.get("obstacles") or ():
                obstacle_key = f"{obstacle['segment_index']}:{obstacle['feature_key']}"
                if obstacle_key in state["obstacles_done"]:
                    continue
                if float(state["progress"]) < float(obstacle["progress"]):
                    continue
                state["obstacles_done"].add(obstacle_key)
                obstacle_params = dict(obstacle.get("effect_params") or {})
                feature_key = str(obstacle.get("feature_key") or "")
                chaos = float(obstacle_params.get("chaos", 0.0))
                risk_mod = ROLE_RISK.get(role_type, 0.0)
                if feature_key == "boost_pad":
                    gain = 0.84 + cri_factor * 0.48 + acc_factor * 0.16 + rng.uniform(0.0, 0.26)
                    state["progress"] += gain
                    state["state"] = "boost"
                    frame_events.append(_event_payload(state["entry_order"], "boost", "加速床が決まった", segment_index=obstacle["segment_index"]))
                elif feature_key == "oil_slick":
                    if rng.random() < _chance(0.12, chaos * 0.24, spd_factor * 0.09, risk_mod, -acc_factor * 0.18):
                        penalty = 0.86 + rng.uniform(0.1, 0.52)
                        state["progress"] = max(0.0, float(state["progress"]) - penalty)
                        state["recover"] = max(int(state["recover"]), 1)
                        state["state"] = "slip"
                        state["accident_count"] += 1
                        frame_events.append(_event_payload(state["entry_order"], "slip", "オイルで横滑り", segment_index=obstacle["segment_index"]))
                elif feature_key == "barrier_spin":
                    if rng.random() < _chance(0.11, chaos * 0.28, spd_factor * 0.08, risk_mod, -def_factor * 0.18, -acc_factor * 0.06):
                        penalty = 1.00 + rng.uniform(0.16, 0.70)
                        state["progress"] = max(0.0, float(state["progress"]) - penalty)
                        state["recover"] = max(int(state["recover"]), 1 if def_factor > 0.72 else 2)
                        state["state"] = "hit_bar"
                        state["accident_count"] += 1
                        frame_events.append(_event_payload(state["entry_order"], "hit_bar", "回転アームに接触", segment_index=obstacle["segment_index"]))
                elif feature_key == "warp_gate":
                    if rng.random() < _chance(0.08, cri_factor * 0.06, acc_factor * 0.04, ROLE_DASH.get(role_type, 0.0), float(obstacle_params.get("dash_bias", 0.0)) * 0.42):
                        gain = 1.00 + cri_factor * 0.56 + luck_factor * 0.36 + rng.uniform(0.14, 0.44)
                        state["progress"] += gain
                        state["state"] = "warp"
                        frame_events.append(_event_payload(state["entry_order"], "warp", "ワープ成功", segment_index=obstacle["segment_index"]))
                    elif rng.random() < 0.16:
                        state["progress"] = max(0.0, float(state["progress"]) - 0.28)
                        state["state"] = "slow"
                        frame_events.append(_event_payload(state["entry_order"], "slow", "ワープが乱れた", segment_index=obstacle["segment_index"]))
                elif feature_key == "slow_zone":
                    penalty = 0.34 + rng.uniform(0.08, 0.44) - def_factor * 0.08
                    state["progress"] = max(0.0, float(state["progress"]) - max(0.08, penalty))
                    state["state"] = "slow"
                    frame_events.append(_event_payload(state["entry_order"], "slow", "スクラップで減速", segment_index=obstacle["segment_index"]))
                elif feature_key == "pitfall":
                    if rng.random() < _chance(0.06, chaos * 0.22, risk_mod, -def_factor * 0.08, -acc_factor * 0.10):
                        penalty = 1.32 + rng.uniform(0.34, 0.82)
                        state["progress"] = max(0.0, float(state["progress"]) - penalty)
                        state["recover"] = max(int(state["recover"]), 2)
                        state["state"] = "pitfall"
                        state["accident_count"] += 1
                        frame_events.append(_event_payload(state["entry_order"], "pitfall", "落下してバウンド", segment_index=obstacle["segment_index"]))
                elif feature_key == "magnet_field":
                    if rank_now > 1 and gap_to_leader <= 2.2 and rng.random() < 0.54:
                        gain = 0.48 + acc_factor * 0.12 + luck_factor * 0.16 + rng.uniform(0.06, 0.22)
                        state["progress"] += gain
                        state["state"] = "boost"
                        frame_events.append(_event_payload(state["entry_order"], "boost", "磁気流に乗った", segment_index=obstacle["segment_index"]))
                    else:
                        penalty = 0.42 + rng.uniform(0.08, 0.28)
                        state["progress"] = max(0.0, float(state["progress"]) - penalty)
                        state["state"] = "reverse"
                        state["accident_count"] += 1
                        frame_events.append(_event_payload(state["entry_order"], "reverse", "磁気に押し戻された", segment_index=obstacle["segment_index"]))
                elif feature_key == "shock_gate":
                    if rng.random() < _chance(0.16, chaos * 0.16, risk_mod, -acc_factor * 0.10):
                        penalty = 0.56 + rng.uniform(0.08, 0.26)
                        state["progress"] = max(0.0, float(state["progress"]) - penalty)
                        state["recover"] = max(int(state["recover"]), 1)
                        state["state"] = "slow"
                        state["accident_count"] += 1
                        frame_events.append(_event_payload(state["entry_order"], "slow", "ショックで停止", segment_index=obstacle["segment_index"]))
                elif feature_key == "jump_pad":
                    if rng.random() < _chance(0.48, cri_factor * 0.08, acc_factor * 0.12, luck_factor * 0.06):
                        gain = 0.80 + cri_factor * 0.34 + rng.uniform(0.08, 0.24)
                        state["progress"] += gain
                        state["state"] = "boost"
                        frame_events.append(_event_payload(state["entry_order"], "boost", "ジャンプ成功", segment_index=obstacle["segment_index"]))
                    else:
                        penalty = 0.46 + rng.uniform(0.08, 0.24)
                        state["progress"] = max(0.0, float(state["progress"]) - penalty)
                        state["recover"] = max(int(state["recover"]), 1)
                        state["state"] = "pitfall"
                        state["accident_count"] += 1
                        frame_events.append(_event_payload(state["entry_order"], "pitfall", "ジャンプ失敗", segment_index=obstacle["segment_index"]))
                elif feature_key == "safe_bay":
                    state["progress"] += 0.22 + hp_factor * 0.08 + def_factor * 0.08
                    state["state"] = "recover"
                    frame_events.append(_event_payload(state["entry_order"], "recover", "安全地帯で立て直し", segment_index=obstacle["segment_index"]))

            _ = atk_factor

        ordered = sorted(zip(states, roster), key=lambda item: (-float(item[0]["progress"]), int(item[0]["entry_order"])))
        for pair_index in range(len(ordered) - 1):
            left_state, left_item = ordered[pair_index]
            right_state, right_item = ordered[pair_index + 1]
            if left_state["finish_time_ms"] is not None or right_state["finish_time_ms"] is not None:
                continue
            if abs(float(left_state["progress"]) - float(right_state["progress"])) > 0.48:
                continue
            if rng.random() >= 0.10:
                continue
            left_push = ROLE_PUSH.get(str(left_item.get("role_type") or "balanced"), 0.0) + float(left_item["atk"]) / max_stats["atk"]
            right_push = ROLE_PUSH.get(str(right_item.get("role_type") or "balanced"), 0.0) + float(right_item["atk"]) / max_stats["atk"]
            if left_push + rng.uniform(0.0, 0.30) >= right_push + rng.uniform(0.0, 0.30):
                winner_state, loser_state = left_state, right_state
            else:
                winner_state, loser_state = right_state, left_state
            loser_state["progress"] = max(0.0, float(loser_state["progress"]) - (0.32 + rng.uniform(0.06, 0.32)))
            loser_state["state"] = "hit_bar"
            loser_state["recover"] = max(int(loser_state["recover"]), 1)
            if rng.random() < 0.48:
                loser_state["accident_count"] += 1
            winner_state["progress"] += 0.08
            frame_events.append(_event_payload(loser_state["entry_order"], "clash", EVENT_LABELS["clash"], segment_index=_segment_index_for(loser_state["progress"], course)))

        rank_now = sorted(states, key=lambda row: (-float(row["progress"]), int(row["entry_order"])))
        for rank_index, state in enumerate(rank_now, start=1):
            if state["finish_time_ms"] is None and float(state["progress"]) >= LAB_RACE_GOAL:
                overshoot = float(state["progress"]) - LAB_RACE_GOAL
                ref_delta = max(0.16, float(state["last_delta"]))
                frac = max(0.0, min(1.0, 1.0 - (overshoot / ref_delta)))
                state["progress"] = LAB_RACE_GOAL
                state["finish_time_ms"] = int(frame_no * LAB_RACE_FRAME_MS + frac * LAB_RACE_FRAME_MS)
                state["state"] = "finish"
                frame_events.append(_event_payload(state["entry_order"], "finish", EVENT_LABELS["finish"], segment_index=len(course["segments"]) - 1))
            state["best_rank"] = min(int(state["best_rank"]), rank_index)
            state["worst_rank"] = max(int(state["worst_rank"]), rank_index)

        rank_est = {
            int(state["entry_order"]): idx
            for idx, state in enumerate(sorted(states, key=lambda row: (-float(row["progress"]), int(row["entry_order"]))), start=1)
        }
        frames.append(
            {
                "frame_no": frame_no,
                "entries": [
                    {
                        "entry_order": int(state["entry_order"]),
                        "x": round(min(100.0, (float(state["progress"]) / LAB_RACE_GOAL) * 100.0), 2),
                        "lane": int(state["lane_index"]),
                        "lane_index": int(state["lane_index"]),
                        "segment_index": int(_segment_index_for(state["progress"], course)),
                        "state": state["state"],
                        "status": state["state"],
                        "rank_estimate": int(rank_est[int(state["entry_order"])]),
                        "is_finished": bool(state["finish_time_ms"] is not None),
                    }
                    for state in sorted(states, key=lambda row: int(row["entry_order"]))
                ],
                "events": frame_events[:8],
            }
        )
        if all(state["finish_time_ms"] is not None for state in states):
            break

    fallback_base = len(frames) * LAB_RACE_FRAME_MS
    for state in states:
        if state["finish_time_ms"] is None:
            remain = max(0.0, LAB_RACE_GOAL - float(state["progress"]))
            ref_delta = max(0.22, float(state["last_delta"]) or 0.48)
            state["finish_time_ms"] = int(fallback_base + (remain / ref_delta) * LAB_RACE_FRAME_MS)
            state["progress"] = LAB_RACE_GOAL
            state["state"] = "finish"

    ranked = sorted(
        zip(states, roster),
        key=lambda item: (int(item[0]["finish_time_ms"]), -float(item[0]["progress"]), int(item[0]["entry_order"])),
    )
    results = []
    max_accidents = max(int(state["accident_count"]) for state, _ in ranked) if ranked else 0
    for final_rank, (state, item) in enumerate(ranked, start=1):
        comeback_flag = (int(state["worst_rank"]) - int(final_rank)) >= 2
        highlights = []
        if comeback_flag:
            highlights.append("大逆転")
        if int(state["dash_count"]) >= 2:
            highlights.append("会心ダッシュ")
        if int(state["accident_count"]) == int(max_accidents) and int(max_accidents) >= 2:
            highlights.append("転倒王")
        results.append(
            {
                "entry_order": int(state["entry_order"]),
                "display_name": item["display_name"],
                "source_type": item.get("source_type"),
                "user_id": item.get("user_id"),
                "robot_instance_id": item.get("robot_instance_id"),
                "submission_id": item.get("submission_id"),
                "bot_key": item.get("bot_key"),
                "role_type": item.get("role_type"),
                "condition_key": item.get("condition_key"),
                "condition_label": item.get("condition_label"),
                "icon_path": item.get("icon_path"),
                "lane_index": int(item["lane_index"]),
                "hp": int(item["hp"]),
                "atk": int(item["atk"]),
                "def": int(item["def"]),
                "spd": int(item["spd"]),
                "acc": int(item["acc"]),
                "cri": int(item["cri"]),
                "luck": int(item["luck"]),
                "odds": item.get("odds"),
                "final_rank": int(final_rank),
                "finish_time_ms": int(state["finish_time_ms"]),
                "accident_count": int(state["accident_count"]),
                "dash_count": int(state["dash_count"]),
                "best_rank": int(state["best_rank"]),
                "worst_rank": int(state["worst_rank"]),
                "comeback_flag": bool(comeback_flag),
                "highlights": highlights,
            }
        )
    winner = results[0] if results else None
    return {
        "frames": frames,
        "results": results,
        "summary": {
            "winner_upset": bool(winner and winner.get("odds") is not None and float(winner["odds"]) >= 3.6),
            "winner_name": (winner["display_name"] if winner else ""),
            "winner_entry_order": (winner["entry_order"] if winner else None),
            "special_count": int(course.get("special_count") or 0),
        },
    }
