import random


def _clamp(value, low, high):
    return max(low, min(high, value))


def _arch_key(archetype):
    if isinstance(archetype, dict):
        return (archetype.get("key") or "none").lower()
    if isinstance(archetype, str):
        return archetype.lower()
    return "none"


def resolve_attack(
    att_atk,
    att_acc,
    att_cri,
    def_def,
    def_acc,
    rng=None,
    attacker_archetype=None,
    defender_archetype=None,
    attacker_is_first_striker=False,
    crit_multiplier=1.5,
    force_hit=False,
    return_detail=False,
    damage_noise_range=None,
):
    roller = rng or random
    att_key = _arch_key(attacker_archetype)
    def_key = _arch_key(defender_archetype)

    hit_bonus = 0.03 if att_key == "sniper" else 0.0
    hit_chance = _clamp(0.75 + (att_acc - def_acc) * 0.01 + hit_bonus, 0.60, 0.95)
    hit_roll = roller.random()
    missed = (hit_roll > hit_chance) and (not force_hit)
    if missed:
        if return_detail:
            return 0, False, {
                "miss": True,
                "hit_chance": float(hit_chance),
                "hit_roll": float(hit_roll),
                "hit_forced": bool(force_hit),
                "att_acc": int(att_acc),
                "def_acc": int(def_acc),
                "hit_bonus": float(hit_bonus),
                "damage_noise_low": None,
                "damage_noise_high": None,
            }
        return 0, False
    base_damage = max(1, (att_atk - int(def_def * 0.5)) + roller.randint(-1, 1))
    noise_low = None
    noise_high = None
    damage = int(base_damage)
    if (
        isinstance(damage_noise_range, (tuple, list))
        and len(damage_noise_range) == 2
        and damage_noise_range[0] is not None
        and damage_noise_range[1] is not None
    ):
        noise_low = float(damage_noise_range[0])
        noise_high = float(damage_noise_range[1])
        if noise_low > noise_high:
            noise_low, noise_high = noise_high, noise_low
        damage = max(1, int(round(base_damage * roller.uniform(noise_low, noise_high))))
    crit_chance = _clamp(att_cri * 0.01, 0.01, 0.25)
    critical = roller.random() < crit_chance
    if critical:
        damage = max(1, int(damage * float(crit_multiplier)))
    if att_key == "swift" and attacker_is_first_striker:
        damage = max(1, int(damage * 1.10))
    if def_key == "fortress":
        damage = max(1, int(damage * 0.90))
    if return_detail:
        return damage, critical, {
            "miss": False,
            "hit_chance": float(hit_chance),
            "hit_roll": float(hit_roll),
            "hit_forced": bool(force_hit),
            "att_acc": int(att_acc),
            "def_acc": int(def_acc),
            "hit_bonus": float(hit_bonus),
            "damage_noise_low": noise_low,
            "damage_noise_high": noise_high,
        }
    return damage, critical


def simulate_battle(
    player_stats,
    enemy_stats,
    seed=None,
    max_turns=8,
    rng=None,
    player_archetype=None,
    enemy_archetype=None,
    enable_archetype=False,
):
    roller = rng or (random.Random(seed) if seed is not None else random)

    player_hp = max(1, int(player_stats["hp"]))
    player_atk = int(player_stats["atk"])
    player_def = int(player_stats["def"])
    player_spd = int(player_stats["spd"])
    player_acc = int(player_stats["acc"])
    player_cri = int(player_stats["cri"])

    enemy_hp = max(1, int(enemy_stats["hp"]))
    enemy_atk = int(enemy_stats["atk"])
    enemy_def = int(enemy_stats["def"])
    enemy_spd = int(enemy_stats["spd"])
    enemy_acc = int(enemy_stats["acc"])
    enemy_cri = int(enemy_stats["cri"])

    player_damage_total = 0
    enemy_damage_total = 0
    turns = 0
    for turn in range(1, int(max_turns) + 1):
        turns = turn
        player_first = player_spd >= enemy_spd
        if player_first:
            player_damage, _ = resolve_attack(
                player_atk,
                player_acc,
                player_cri,
                enemy_def,
                enemy_acc,
                rng=roller,
                attacker_archetype=player_archetype if enable_archetype else None,
                defender_archetype=enemy_archetype if enable_archetype else None,
                attacker_is_first_striker=True,
            )
            enemy_hp = max(0, enemy_hp - player_damage)
            player_damage_total += player_damage
            if enemy_hp > 0:
                enemy_damage, _ = resolve_attack(
                    enemy_atk,
                    enemy_acc,
                    enemy_cri,
                    player_def,
                    player_acc,
                    rng=roller,
                    attacker_archetype=enemy_archetype if enable_archetype else None,
                    defender_archetype=player_archetype if enable_archetype else None,
                    attacker_is_first_striker=False,
                )
                player_hp = max(0, player_hp - enemy_damage)
                enemy_damage_total += enemy_damage
        else:
            enemy_damage, _ = resolve_attack(
                enemy_atk,
                enemy_acc,
                enemy_cri,
                player_def,
                player_acc,
                rng=roller,
                attacker_archetype=enemy_archetype if enable_archetype else None,
                defender_archetype=player_archetype if enable_archetype else None,
                attacker_is_first_striker=True,
            )
            player_hp = max(0, player_hp - enemy_damage)
            enemy_damage_total += enemy_damage
            if player_hp > 0:
                player_damage, _ = resolve_attack(
                    player_atk,
                    player_acc,
                    player_cri,
                    enemy_def,
                    enemy_acc,
                    rng=roller,
                    attacker_archetype=player_archetype if enable_archetype else None,
                    defender_archetype=enemy_archetype if enable_archetype else None,
                    attacker_is_first_striker=False,
                )
                enemy_hp = max(0, enemy_hp - player_damage)
                player_damage_total += player_damage

        if enemy_hp == 0 or player_hp == 0:
            break

    timeout = enemy_hp > 0 and player_hp > 0 and turns >= int(max_turns)
    return {
        "win": enemy_hp == 0,
        "turns": turns,
        "timeout": timeout,
        "player_damage_total": player_damage_total,
        "enemy_damage_total": enemy_damage_total,
    }
