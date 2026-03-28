# 監査ログ仕様（world_events_log）

最終更新日: 2026-03-28

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

### 4.5 実験室
- `audit.lab.submission.create`
- `audit.lab.submission.approve`
- `audit.lab.submission.reject`
- `audit.lab.submission.disable`
- `audit.lab.submission.like`
- `audit.lab.submission.report`
- `audit.lab.race.entry`
- `audit.lab.race.start`
- `audit.lab.race.finish`
- `audit.lab.race.result`
- `audit.lab.casino.daily_grant`
- `audit.lab.casino.bet.place`
- `audit.lab.casino.bet.resolve`
- `audit.lab.casino.race.start`
- `audit.lab.casino.race.finish`
- `audit.lab.casino.prize.claim`

### 4.6 共有/招待/陣営
- `audit.chat.post`
- `audit.share.click`
- `audit.referral.attach`
- `audit.referral.qualified`
- `audit.faction.choose`

### 4.7 決済
- `audit.payment.checkout.create`
- `audit.payment.webhook.received`
- `audit.payment.completed`
- `audit.payment.grant.success`
- `audit.payment.grant.skip_duplicate`
- `audit.payment.grant.failed`
- `audit.explore_boost.grant.success`
- `audit.explore_boost.grant.skip_duplicate`
- `audit.explore_boost.grant.failed`

### 4.8 管理者操作（追加）
- `audit.admin.user.ban`
- `audit.admin.user.unban`
- `audit.admin.user.protect_login`
- `audit.admin.user.unprotect_login`
- `audit.admin.user.delete`
  - payload推奨: `deleted_user_id`, `deleted_username`, `actor_admin_id`

### 4.9 システム
- `audit.system.maintenance_block`
- `FACTION_WAR_RESULT`（世界イベント）
- `RESEARCH_ADVANCE` / `RESEARCH_UNLOCK`（世界イベント）
- `LAB_RACE_WIN` / `LAB_RACE_UPSET` / `LAB_RACE_POPULAR_ENTRY`（実験室公開イベント）

## 5. payload方針
- 表示用テキストだけでなく、再計算可能な値を保持
- 追加は可、既存キーの意味変更は不可
- `audit.chat.post` は少なくとも `room_key / surface / message_length / preview` を保持する
- 実験室系 payload は可能な範囲で以下を保持する
  - race: `race_id / course_key / seed / special_count / features / robot_instance_id / robot_name / finish_time_ms / winner`
  - submission: `submission_id / title / reason / note`
  - casino: `race_id / entry_id / bot_key / amount / odds / payout / condition_key / lab_coin_before / lab_coin_after / prize_key`
- 決済系 payload は可能な範囲で以下を保持する
  - `user_id`
  - `product_key`
  - `stripe_checkout_session_id`
  - `stripe_payment_intent_id`
  - `stripe_event_id`
  - `amount_jpy`
  - `currency`
  - `status`
  - `boost_days`
  - `starts_at`
  - `ends_at`
  - `duplicate_reason`

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
