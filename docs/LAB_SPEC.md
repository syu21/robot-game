# 実験室仕様

最終更新日: 2026-03-28

## 1. 位置づけ
- `基地 = 本編の成長`
- `実験室 = 観戦 / 展示 / 語り`
- 本編の `強さ / コイン / 層進行 / 出撃 / 進化 / 強化` には影響しない

## 2. レース共通基盤
- 実験室のレースは `services/lab_race_engine.py` を中心に共通化する
- `/lab/race` は `エネミーレース` の主導線として `6レーン / 10区間 / 事前シミュレーション` 基盤を使う
- コースは 10 区間固定で、`1区間目 = START`、`10区間目 = GOAL`
- 特殊区間は毎レース `2〜5個` を抽選し、残りは通常路にする
- 予想・lab_coin・払い戻しなどの経済要素はレース周辺サービス側に分離し、レースシミュレーション自体は知らない

## 3. 主要ルート
- `/lab`
- `/lab/race`
- `/lab/race/watch/<race_id>`
- `/lab/race/result/<race_id>`
- `/lab/race/history`
- `/lab/race/prizes`
- `/lab/race/legacy`
- `/lab/race/legacy/watch/<race_id>`
- `/lab/race/results/<race_id>`
- `/lab/race/rankings`
- `/lab/upload`
- `/lab/showcase`
- `/lab/showcase/<submission_id>`
- `/admin/lab`
- `/admin/lab/submissions`

## 4. データモデル
- `lab_robot_submissions`
- `lab_submission_likes`
- `lab_submission_reports`
- `lab_races`
- `lab_race_entries`
- `lab_race_frames`
- `lab_race_records`
- `lab_casino_races`
- `lab_casino_entries`
- `lab_casino_bets`
- `lab_casino_frames`
- `lab_casino_prizes`
- `lab_casino_prize_claims`

## 5. 世界ログ
- `LAB_RACE_WIN`
- `LAB_RACE_UPSET`
- `LAB_RACE_POPULAR_ENTRY`

実験室トップでは上記の話題を `今週の実験室話題` として表示する。

## 6. 監査
- `audit.lab.submission.*`
- `audit.lab.race.*`
- `audit.lab.casino.*`

UI 名称は `エネミーレース` に統一したが、既存 `audit.*` キーは互換維持のため継続利用する。
