import random

PERSONALITY_WEIGHTS = [
    ("silent", 36),
    ("cheerful", 36),
    ("analyst", 10),
    ("charger", 8),
    ("showoff", 6),
    ("veteran", 2),
    ("supportive", 1),
    ("cold", 1),
]

PERSONALITY_TEMPLATES = {
    "silent": {
        "start": [
            "{robot}は無言で索敵を開始した。",
            "{robot}は視線だけで敵影を捉えた。",
        ],
        "mid": [
            "{robot}は最短動作で踏み込み、正確に当てた。",
            "{robot}は呼吸を乱さず、次の間合いを取る。",
        ],
        "end_win": [
            "{robot}は最後まで無駄なく処理した。勝利。",
        ],
        "end_other": [
            "{robot}は姿勢を崩さず次の機会を待つ。",
        ],
    },
    "cheerful": {
        "start": [
            "{robot}「よーし、行ってみよう！」",
            "{robot}は勢いよく先制した。",
        ],
        "mid": [
            "{robot}は弾むように連続行動した。",
            "{robot}「まだまだ動けるよ！」",
        ],
        "end_win": [
            "{robot}「やった！ 今日もいい感じ！」",
        ],
        "end_other": [
            "{robot}「次はもっと上手くいく！」",
        ],
    },
    "analyst": {
        "start": [
            "{robot}は交戦前にパターンを解析した。",
            "{robot}は敵の挙動をログ化した。",
        ],
        "mid": [
            "{robot}は最適化ルートで攻撃を実行。",
            "{robot}は誤差を補正しつつ距離を維持。",
        ],
        "end_win": [
            "{robot}「想定誤差内。勝率更新。」",
        ],
        "end_other": [
            "{robot}「データ取得完了。次回に反映。」",
        ],
    },
    "charger": {
        "start": [
            "{robot}は迷わず前進した。",
            "{robot}は突撃姿勢で敵陣へ入った。",
        ],
        "mid": [
            "{robot}は加速しながら一気に押し込む。",
            "{robot}は被弾を許しても前進を止めない。",
        ],
        "end_win": [
            "{robot}「押し切った。これで十分だ。」",
        ],
        "end_other": [
            "{robot}はなお前進の機会を狙っている。",
        ],
    },
    "showoff": {
        "start": [
            "{robot}は見栄えのいい姿勢で登場した。",
            "{robot}「見てろよ、ここからだ。」",
        ],
        "mid": [
            "{robot}は余裕を見せる軌道で攻撃した。",
            "{robot}は演出めいた動きで攪乱した。",
        ],
        "end_win": [
            "{robot}「当然の結果だね。」",
        ],
        "end_other": [
            "{robot}「次はもっと映える形で決める。」",
        ],
    },
}


def pick_personality():
    labels = [x[0] for x in PERSONALITY_WEIGHTS]
    weights = [x[1] for x in PERSONALITY_WEIGHTS]
    return random.choices(labels, weights=weights, k=1)[0]


def _template_for(personality):
    return PERSONALITY_TEMPLATES.get(personality, PERSONALITY_TEMPLATES["analyst"])


def generate_exploration_log(
    robot_name,
    personality,
    enemy_name,
    outcome,
    reward_coin=0,
    reward_exp=0,
    dropped_parts=None,
):
    tpl = _template_for(personality)
    dropped_parts = dropped_parts or []
    turn_count = random.randint(1, 3)
    lines = []

    lines.append(f"【1ターン】{random.choice(tpl['start']).format(robot=robot_name, enemy=enemy_name)}")

    for idx in range(2, turn_count + 1):
        lines.append(f"【{idx}ターン】{random.choice(tpl['mid']).format(robot=robot_name, enemy=enemy_name)}")

    if outcome == "win":
        lines.append(f"【結果】{random.choice(tpl['end_win']).format(robot=robot_name, enemy=enemy_name)}")
    else:
        lines.append(f"【結果】{random.choice(tpl['end_other']).format(robot=robot_name, enemy=enemy_name)}")

    reward_bits = [f"コイン{reward_coin}", f"経験値{reward_exp}"]
    if dropped_parts:
        reward_bits.append("ドロップ:" + ", ".join(dropped_parts))
    lines.append(f"【報酬】{robot_name}は" + " / ".join(reward_bits) + "を獲得した。")

    # 3〜6行に収める
    return lines[:6]


def get_streak_lines(personality: str, robot_name: str, win: bool, win_streak: int, prev_streak: int) -> dict:
    """
    Return streak-related flavor lines.

    keys:
      - streak_hint_line
      - bonus_line
      - streak_break_line
    """
    p = (personality or "").strip().lower()
    rn = robot_name or "探索機"
    out = {"streak_hint_line": None, "bonus_line": None, "streak_break_line": None}

    if p == "calm":
        if win and int(win_streak) == 2:
            out["streak_hint_line"] = f"{rn}「流れは悪くない。」"
        elif win and int(win_streak) == 3:
            out["bonus_line"] = f"{rn}「3連勝か。悪くない結果だ。」"
        elif (not win) and int(prev_streak) >= 2:
            out["streak_break_line"] = f"{rn}「ここで止まるか……。」"
        return out

    if p == "hotblood":
        if win and int(win_streak) == 2:
            out["streak_hint_line"] = f"{rn}「いいぞ！流れが来てる！」"
        elif win and int(win_streak) == 3:
            out["bonus_line"] = f"{rn}「3連勝だ！まだ行ける！」"
        elif (not win) and int(prev_streak) >= 2:
            out["streak_break_line"] = f"{rn}「くそっ…次は負けねぇ！」"
        return out

    if p == "quiet":
        if win and int(win_streak) == 2:
            out["streak_hint_line"] = f"{rn}「……悪くない。」"
        elif win and int(win_streak) == 3:
            out["bonus_line"] = f"{rn}「……3連勝。」"
        elif (not win) and int(prev_streak) >= 2:
            out["streak_break_line"] = f"{rn}「……止まったか。」"
        return out

    return {}


def get_idle_line(personality: str, robot_name: str) -> str:
    """
    Return a home-screen idle line by personality.
    """
    p = (personality or "").strip().lower()
    rn = robot_name or "探索機"
    if p == "calm":
        return f"{rn}「今日も悪くない。」"
    if p == "hotblood":
        return f"{rn}「さあ、行こうぜ！」"
    if p == "quiet":
        return f"{rn}「……待機中。」"
    return f"{rn}「……。」"
