# 監査ログ仕様（world_events_log）

最終更新日: 2026-03-11

## 1. 目的
- ユーザー行動・管理操作・経済変動の追跡
- 障害解析と不正調査の基盤
- 仕様変更後の互換確認

## 2. 記録先
テーブル: `world_events_log`

主要列:
- `created_at`
- `event_type`
- `payload_json`
- `user_id`
- `request_id`
- `ip_hash`
- `action_key`
- `entity_type`
- `entity_id`
- `delta_coins`
- `delta_count`

## 3. request_id方針
- `before_request` で採番
- 同一操作内イベントは同じ `request_id` で追跡

## 4. イベント分類
### 4.1 出撃/戦闘
- `audit.explore.start`
- `audit.explore.end`
- `audit.boss.encounter`
- `audit.boss.attempt`
- `audit.boss.defeat`

### 4.2 経済/在庫
- `audit.coin.delta`
- `audit.streak.bonus`
- `audit.drop`
- `audit.inventory.delta`

### 4.3 育成
- `audit.fuse`
- `audit.part.evolve`
- `audit.core.drop`
- `audit.build.confirm`

### 4.4 機体/展示
- `audit.robot.rename`
- `audit.robot.decompose`
- `audit.robot.share`
- `audit.showcase.expand`
- `audit.showcase.like`

### 4.5 共有/招待/陣営
- `audit.share.click`
- `audit.referral.attach`
- `audit.referral.qualified`
- `audit.faction.choose`

### 4.6 管理者操作（追加）
- `audit.admin.user.ban`
- `audit.admin.user.unban`
- `audit.admin.user.protect_login`
- `audit.admin.user.unprotect_login`
- `audit.admin.user.delete`
  - payload推奨: `deleted_user_id`, `deleted_username`, `actor_admin_id`

### 4.7 システム
- `audit.system.maintenance_block`
- `FACTION_WAR_RESULT`（世界イベント）
- `RESEARCH_ADVANCE` / `RESEARCH_UNLOCK`（世界イベント）

## 5. payload方針
- 表示用テキストだけでなく、再計算可能な値を保持
- 追加は可、既存キーの意味変更は不可

## 6. 管理UI
- `/admin/audit` で検索
- 推奨フィルタ:
  - `user_id`
  - `event_type`
  - `request_id`
  - `after` / `before`

## 7. 禁止事項
- `audit.*` event_type の再利用による意味変更
- 成否が曖昧な payload
- request_id 未設定での重要操作記録
