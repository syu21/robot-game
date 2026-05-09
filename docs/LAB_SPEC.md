# 実験室仕様

最終更新日: 2026-05-04

## 1. 位置づけ
- `基地 = 本編の成長`
- `実験室 = 観戦 / 展示 / 語り`
- 本編の `強さ / コイン / 層進行 / 出撃 / 進化 / 強化` には影響しない
- 実験室UGC投稿、展示、採用候補管理の詳細は `docs/LAB_UGC_ADOPTION_SPEC.md` を正本とする
- 本編展示は実戦機の展示、実験室展示は創作ロボ / 試作機の展示として分離する

## 2. レース共通基盤
- 実験室のレースは `services/lab_race_engine.py` を中心に共通化する
- `/lab/race` は `エネミーレース` の主導線として `6レーン / 10区間 / 事前シミュレーション` 基盤を使う
- コースは 10 区間固定で、`1区間目 = START`、`10区間目 = GOAL`
- 特殊区間は毎レース `2〜5個` を抽選し、残りは通常路にする
- 予想・lab_coin・払い戻しなどの経済要素はレース周辺サービス側に分離し、レースシミュレーション自体は知らない

## 3. 主要ルート
現行ルート:

- `/lab`
- `/lab/ai-robot-generate`
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

UGC拡張予定ルート:

- `/lab/my-submissions`
- `/admin/lab/submissions/<id>/approve`
- `/admin/lab/submissions/<id>/reject`
- `/admin/lab/submissions/<id>/disable`
- `/admin/lab/submissions/<id>/feature`
- `/admin/lab/submissions/<id>/adoption-candidate`
- `/admin/lab/submissions/<id>/adoption-update`

## 4. データモデル
- `lab_robot_submissions`
- `lab_submission_likes`
- `lab_submission_reports`
- `lab_submission_adoptions`
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
- `lab_typing_runs`
  - タイピング射撃試験のスコア、最大コンボ、撃破数、ボス到達/撃破を保存する

## 5. 世界ログ
- `LAB_RACE_WIN`
- `LAB_RACE_UPSET`
- `LAB_RACE_POPULAR_ENTRY`
- `LAB_SUBMISSION_APPROVED`
- `LAB_SUBMISSION_FEATURED`
- `LAB_SUBMISSION_ADOPTION_CANDIDATE`
- `LAB_SUBMISSION_ADOPTION_RELEASED`

実験室トップでは上記の話題を `今週の実験室話題` として表示する。
本編世界ログに混ぜすぎず、まずは `/lab` トップに集約する。

## 6. 監査
- `audit.lab.submission.*`
- `audit.lab.ai_generate.click`
- `audit.lab.race.*`
- `audit.lab.casino.*`
- `audit.lab.typing.start`
- `audit.lab.typing.finish`

UI 名称は `エネミーレース` に統一したが、既存 `audit.*` キーは互換維持のため継続利用する。

## 6.1 AIロボ生成導線
- `/lab` と `/lab/upload` から `研究所AI` のロボ生成導線を表示する
- 導線は `/lab/ai-robot-generate?source=lab_top|lab_upload` を新規タブで開き、クリック監査後に外部のロボ生成ページへリダイレクトする
- 生成画像はユーザーが保存し、`/lab/upload` から投稿する
- ゲーム内で画像生成APIは呼ばず、本編の強さ、コイン、層進行、出撃、進化、強化には影響させない

## 7. 景品交換の公開状態
- 2026-04-12 時点では景品交換は準備中
- `/lab/race/prizes` はラボコイン所持数と準備中メッセージを表示する
- 交換POSTは直叩きされても成立させず、ラボコインと交換履歴を変更しない
- 景品内容が確定したら `LAB_CASINO_PRIZE_EXCHANGE_ENABLED` を有効化して公開する
