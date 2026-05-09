# 監査ログ仕様（world_events_log）

最終更新日: 2026-05-04

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
- `audit.lab.ai_generate.click`
  - payload は `source=lab_top|lab_upload`, `target=external_gpt_robot_factory`, `url` を含める
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
- `audit.lab.typing.start`
  - payload は `mode=typing_shooting_trial`, `duration_seconds=30` を含める
- `audit.lab.typing.finish`
  - payload は `run_id`, `score`, `max_combo`, `typed_count`, `miss_count`, `defeated_count`, `boss_reached`, `boss_defeated`, `remaining_boss_hp`, `duration_ms` を含める

### 4.6 共有/招待/陣営
- `audit.chat.post`
- `audit.share.click`
  - Xシェア導線では payload に `surface`, `share_target`, `robot_instance_id`, `boost_granted`, `boost_before`, `boost_after`, `reason=daily_x_share` を含める
- `audit.research_boost.grant`
  - 研究ブースト付与時に記録する。payload は `user_id`, `reason`, `amount`, `before`, `after`, `capped`, `day_key` を含める
- `audit.research_boost.consume`
  - 出撃時の自動消費で記録する。payload は `user_id`, `before`, `after`, `used_for=explore`, `area_key` を含める
- `audit.research_boost.toggle`
  - ホームのON/OFF切替で記録する。payload は `before`, `after`, `charges` を含める
- `audit.referral.attach`
- `audit.referral.qualified`
- `audit.faction.choose`
- `audit.faction.points.add`
  - 陣営ポイント加算時に記録する。payload は `week_key`, `faction`, `event_type`, `points`, `counters`, `payload`, `log_created` を含める
  - 未所属ユーザーは加算されない
  - 再集計時は二重監査を避けるため、このauditは生成しない

### 4.7 チャンプ/非同期挑戦
- `audit.champion.select`
- `audit.champion.challenge`
- `audit.champion.defeat`
- `CHAMPION_SELECTED`（世界イベント）
- `CHAMPION_DEFEATED`（世界イベント）

### 4.8 決済
- `audit.payment.checkout.create`
- `audit.payment.webhook.received`
- `audit.payment.completed`
- `audit.payment.grant.success`
- `audit.payment.grant.skip_duplicate`
- `audit.payment.grant.failed`
- `audit.trophy.grant.success`
- `audit.trophy.grant.skip_duplicate`
- `audit.trophy.grant.failed`
- `audit.explore_boost.grant.success`
- `audit.explore_boost.grant.skip_duplicate`
- `audit.explore_boost.grant.failed`
- `audit.lab.small_boost.grant`（旧研究ブースト付与イベント。新規記録は `audit.research_boost.grant`）
- `audit.lab.small_boost.use`（旧時間制研究ブースト使用イベント。新規記録は `audit.research_boost.consume`）

### 4.9 管理者操作（追加）
- `audit.admin.user.ban`
- `audit.admin.user.unban`
- `audit.admin.user.protect_login`
- `audit.admin.user.unprotect_login`
- `audit.admin.user.delete`
  - payload推奨: `deleted_user_id`, `deleted_username`, `actor_admin_id`

### 4.10 パーツ保護
- `audit.part.lock`
- `audit.part.unlock`
- payload推奨: `part_instance_id`, `part_key`, `part_name`, `rarity`, `plus`, `locked`

### 4.11 システム
- `audit.system.maintenance_block`
- `FACTION_WAR_RESULT`（世界イベント）
- `RESEARCH_ADVANCE` / `RESEARCH_UNLOCK`（世界イベント）
- `LAB_RACE_WIN` / `LAB_RACE_UPSET` / `LAB_RACE_POPULAR_ENTRY`（実験室公開イベント）

## 5. payload方針
- 表示用テキストだけでなく、再計算可能な値を保持
- 追加は可、既存キーの意味変更は不可
- `battle-cinematic-v1` の属性レーザーは表示専用。`turn_logs` や表示payloadに `element` が増えても、既存 `audit.*` event_type の意味は変えない
- `audit.chat.post` は少なくとも `room_key / surface / message_length / preview` を保持する
- 実験室系 payload は可能な範囲で以下を保持する
  - race: `race_id / course_key / seed / special_count / features / robot_instance_id / robot_name / finish_time_ms / winner`
  - submission: `submission_id / title / reason / note`
  - casino: `race_id / entry_id / bot_key / amount / odds / payout / condition_key / lab_coin_before / lab_coin_after / prize_key`
- 決済系 payload は可能な範囲で以下を保持する
  - `user_id`
  - `product_key`
  - `trophy_key`
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
- チャンプ系 payload は可能な範囲で以下を保持する
  - `week_key`
  - `champion_snapshot_id`
  - `champion_user_id`
  - `champion_robot_instance_id`
  - `champion_robot_name`
  - `champion_owner_name`
  - `challenger_user_id`
  - `challenger_robot_instance_id`
  - `challenger_robot_name`
  - `result`
  - `turn_count`
  - `timeout`
  - `summary_label`

## 6. 管理UI
- `/admin/audit` で検索
- 推奨フィルタ:
  - `user_id`
  - `event_type`
  - `request_id`
  - `after` / `befo