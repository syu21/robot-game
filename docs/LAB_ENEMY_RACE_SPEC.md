# エネミーレース仕様

最終更新日: 2026-03-28

## 1. 位置づけ
- 実験室の中にある `見て -> 選んで -> 楽しむ` 寄り道モード
- 本編の `コイン / 強化 / 進化 / 出撃 / 層進行` とは完全分離
- レース本体は観戦レースと同じ `共通レースエンジン` を使う
- 固有要素は `lab_coin / 倍率 / 予想 / 払い戻し / 交換所景品`

## 2. 主要ルート
- `/lab/race`
- `/lab/race/bet`
- `/lab/race/watch/<race_id>`
- `/lab/race/result/<race_id>`
- `/lab/race/history`
- `/lab/race/prizes`
- `/admin/lab/race`

旧 `/lab/casino/*` は互換のため新ルートへリダイレクトする。

## 3. 経済
- 初期 `lab_coin = 1000`
- デイリー補充: `+500`
- 観戦ボーナス: `+20`
- 所持上限: `5000`
- 目的は `増やし続けること` より `遊び続けられること`

## 4. 予想
- 初期版は `単勝のみ`
- 1レース 1 回のみ
- 予想額は `10 / 50 / 100`
- 締切はレース開始前
- 払い戻しは `floor(amount * odds)`
- UI 表示は `倍率` に寄せる

## 5. 出走体
- 固定の敵 6 体を使う
  - ブレイズメック
  - アイスガーディアン
  - スクラップマイン
  - ボルトランナー
  - グラビティコア
  - ミラージュギア
- 名前と性格は固定
- 各レースごとに `condition` とステータスが少し揺れる
- `condition_key` は `excellent / good / normal / bad`

## 6. レース
- 6レーン固定
- 10区間固定
- `1区間目 = START`
- `10区間目 = GOAL`
- 特殊区間は毎レース `2〜5個` 抽選
- `/lab/race/watch/<race_id>` で共通 watch 画面を使う

## 7. 交換所景品
- 本編戦力に直結しない景品を優先
- 例:
  - 実験室称号
  - DECOR
  - 観戦バッジ
  - 軽い試用ブースト

## 8. 監査
- UI 名称は `エネミーレース` に統一したが、監査キーは互換のため既存を継続利用する
- `audit.lab.casino.daily_grant`
- `audit.lab.casino.bet.place`
- `audit.lab.casino.bet.resolve`
- `audit.lab.casino.race.start`
- `audit.lab.casino.race.finish`
- `audit.lab.casino.prize.claim`
