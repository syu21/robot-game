import time

from balance_config import FUSE_COST_BY_PLUS
from constants import FUSE_SUCCESS_TABLE


def _fuse_rates(plus):
    return FUSE_SUCCESS_TABLE.get(int(plus), (5, 8))


def _roll_outcome(plus, rand_int, rand_float):
    success_rate, great_rate = _fuse_rates(plus)
    roll = rand_int(1, 100)
    if roll > success_rate:
        return "fail", 0
    if rand_float() < (great_rate / 100.0):
        return "great", 2
    return "success", 1


def _fuse_cost(plus):
    return int(FUSE_COST_BY_PLUS.get(int(plus), 20))


def fuse_parts(db, user_id, part_instance_ids, use_protect_core, rand_int, rand_float):
    valid_ids = [int(x) for x in part_instance_ids if str(x).isdigit()]
    if len(valid_ids) != 3:
        return {
            "ok": False,
            "message": "同条件の個体パーツを3つ選択してください。",
            "consumed_ids": [],
            "created_id": None,
            "refund_id": None,
            "coin_cost": None,
        }

    placeholders = ",".join(["?"] * len(valid_ids))
    rows = db.execute(
        f"""
        SELECT pi.*, rp.part_type, rp.key AS part_key
        FROM part_instances pi
        JOIN robot_parts rp ON rp.id = pi.part_id
        WHERE pi.user_id = ? AND pi.status = 'inventory' AND pi.id IN ({placeholders})
        """,
        [user_id, *valid_ids],
    ).fetchall()
    if len(rows) != 3:
        return {
            "ok": False,
            "message": "対象パーツが見つかりません。",
            "consumed_ids": [],
            "created_id": None,
            "refund_id": None,
            "coin_cost": None,
        }

    part_type = rows[0]["part_type"]
    rarity = rows[0]["rarity"]
    plus = rows[0]["plus"]
    if not all(r["part_type"] == part_type and r["rarity"] == rarity and r["plus"] == plus for r in rows):
        return {
            "ok": False,
            "message": "同part_type・同rarity・同plusのみ合成できます。",
            "consumed_ids": [],
            "created_id": None,
            "refund_id": None,
            "coin_cost": None,
        }

    if use_protect_core:
        core = db.execute(
            "SELECT qty FROM user_items WHERE user_id = ? AND item_key = 'protect_core'",
            (user_id,),
        ).fetchone()
        if not core or core["qty"] <= 0:
            return {
                "ok": False,
                "message": "保護コアが不足しています。",
                "consumed_ids": [],
                "created_id": None,
                "refund_id": None,
                "coin_cost": None,
            }
    fuse_cost = _fuse_cost(plus)
    user = db.execute("SELECT coins FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user or int(user["coins"]) < fuse_cost:
        return {
            "ok": False,
            "message": f"コイン不足です（必要: {fuse_cost}）",
            "consumed_ids": [],
            "created_id": None,
            "refund_id": None,
            "coin_cost": fuse_cost,
        }

    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE users SET coins = coins - ? WHERE id = ?", (fuse_cost, user_id))
        if use_protect_core:
            db.execute(
                "UPDATE user_items SET qty = qty - 1 WHERE user_id = ? AND item_key = 'protect_core' AND qty > 0",
                (user_id,),
            )
        db.execute(f"DELETE FROM part_instances WHERE id IN ({placeholders})", valid_ids)
        outcome, up = _roll_outcome(plus, rand_int, rand_float)
        if outcome == "fail":
            refund_id = None
            if use_protect_core:
                base = rows[0]
                cur = db.execute(
                    """
                    INSERT INTO part_instances
                    (part_id, user_id, part_type, rarity, element, series, plus, w_hp, w_atk, w_def, w_spd, w_acc, w_cri, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, 'inventory', ?)
                    """,
                    (
                        base["part_id"],
                        user_id,
                        base["part_type"],
                        base["rarity"],
                        base["element"],
                        base["series"],
                        base["w_hp"],
                        base["w_atk"],
                        base["w_def"],
                        base["w_spd"],
                        base["w_acc"],
                        base["w_cri"],
                        int(time.time()),
                    ),
                )
                refund_id = cur.lastrowid
            db.commit()
            return {
                "ok": True,
                "message": f"合成失敗。素材は消失しました。（-{fuse_cost} コイン）",
                "outcome": "fail",
                "new_plus": None,
                "base_plus": int(plus),
                "part_type": part_type,
                "rarity": rarity,
                "use_protect_core": bool(use_protect_core),
                "consumed_ids": valid_ids,
                "created_id": None,
                "refund_id": refund_id,
                "coin_cost": fuse_cost,
            }

        base = rows[0]
        new_plus = min(99, int(base["plus"]) + up)
        cur = db.execute(
            """
            INSERT INTO part_instances
            (part_id, user_id, part_type, rarity, element, series, plus, w_hp, w_atk, w_def, w_spd, w_acc, w_cri, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'inventory', ?)
            """,
            (
                base["part_id"],
                user_id,
                base["part_type"],
                base["rarity"],
                base["element"],
                base["series"],
                new_plus,
                base["w_hp"],
                base["w_atk"],
                base["w_def"],
                base["w_spd"],
                base["w_acc"],
                base["w_cri"],
                int(time.time()),
            ),
        )
        db.commit()
        return {
            "ok": True,
            "message": f"合成{('大成功' if outcome == 'great' else '成功')}。+{new_plus} を獲得。（-{fuse_cost} コイン）",
            "outcome": outcome,
            "new_plus": new_plus,
            "base_plus": int(plus),
            "part_type": part_type,
            "rarity": rarity,
            "use_protect_core": bool(use_protect_core),
            "consumed_ids": valid_ids,
            "created_id": cur.lastrowid,
            "refund_id": None,
            "coin_cost": fuse_cost,
        }
    except Exception as exc:
        db.rollback()
        return {
            "ok": False,
            "message": f"合成に失敗しました: {exc}",
            "consumed_ids": [],
            "created_id": None,
            "refund_id": None,
            "coin_cost": None,
        }
