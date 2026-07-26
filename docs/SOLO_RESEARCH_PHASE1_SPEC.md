# ソロ研究所 Phase 1 仕様

最終更新日: 2026-07-26

## 目的
- ロボらぼの主軸を `探索 -> 研究 -> 試作 -> 記録更新` に寄せる
- マルチプレイ要素は残しつつ、1人でも進行目標が継続する状態を作る
- Phase 1 は研究タスク、研究Lv、研究ノート、個人記録の最小実装に限定する

## UX
- `/home` に `ソロ研究所` カードを表示する
- 研究タスクは常時3枠
- タスクは期限なしで、完了まで残る
- 1件だけ保留できる
- `/research` で研究ノートを表示する
  - 研究Lv / 研究EXP
  - 進行中タスク
  - 保留中タスク
  - 完了済みタスク
  - 個人記録
- 戦闘結果で研究進行と個人記録更新を短く表示する

## バックエンド
- `services/solo_research.py`
  - 研究プロフィール作成
  - タスク定義seed
  - 3枠ボード生成
  - 戦闘イベントから進捗判定
  - 完了報酬EXP付与
  - タスク保留/復帰
  - 個人記録更新
- `services/audit.py`
  - `audit.explore.end` などの既存イベント後に研究進捗を同期する
  - `battle_id` または `request_id` で二重処理を抑止する
- `/admin/research-tasks`
  - タスク定義の有効/無効を切り替える

## データ構造
- `user_research_profiles`
  - ユーザーごとの研究Lv / EXP / 完了数
- `research_task_definitions`
  - 管理可能な研究タスク定義
- `user_research_tasks`
  - ユーザーごとの進行中 / 完了 / 保留タスク
- `user_personal_records`
  - 個人記録
- `user_discoveries`
  - 将来の図鑑/発見履歴用
- `user_research_event_receipts`
  - 研究進捗の冪等性制御

## 監査ログ
- `audit.research.task.assign`
- `audit.research.task.progress`
- `audit.research.task.complete`
- `audit.research.task.claim`
- `audit.research.task.hold`
- `audit.research.level.up`
- `audit.personal_record.update`

## Phase 1 の非対象
- NPC研究員
- 長時間解析
- 敵図鑑/パーツ図鑑の全面拡張
- 研究レポート生成
- マルチ対戦中心の導線

## 受け入れ条件
- 初回 `/home` で3件の研究タスクが作られる
- 出撃結果で対象タスクが進む
- 完了タスクは研究EXPを付与し、自動で次タスクを補充する
- 同一戦闘イベントを再処理しても二重進行しない
- タスクを1件保留し、空枠へ復帰できる
- 個人記録は改善時だけ更新される
- 管理者がタスク定義を停止できる
