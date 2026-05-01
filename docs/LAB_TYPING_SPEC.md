# タイピング射撃試験 v1

## 目的

- 実験室に30秒で遊べる1人用ミニゲームを追加する。
- 本編戦力・層進行・強化バランスには影響させない。
- スコア、コンボ、撃破数、ボス到達を保存し、ランキング接続の土台にする。

## ルート

- `GET /lab/typing`: プレイ画面。
- `POST /lab/typing/result`: 結果保存API。
- `GET /lab/typing/history`: 自分の記録と週間TOP10。

## 保存

- `lab_typing_runs`
- 保存値: `score`, `max_combo`, `typed_count`, `miss_count`, `defeated_count`, `boss_reached`, `boss_defeated`, `remaining_boss_hp`, `duration_ms`, `client_payload_json`

## 監査ログ

- `audit.lab.typing.start`
- `audit.lab.typing.finish`

## v1の制約

- 報酬なし。
- 世界ログ投稿なし。
- 思想補正なし。
- サーバー側は異常値の保存拒否まで。リアルタイム検証はv2以降。
