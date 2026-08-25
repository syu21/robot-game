# 監査ログ仕様（world_events_log）

最終更新日: 2026-08-09

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
- `audit.explore.failed`
- `audit.boss.encounter`
- `audit.boss.attempt`
- `audit.boss.defeat`
- `audit.newbie_protection.boss_alert_guaranteed`
- `audit.newbie_protection.battle_assist`
- `audit.layer1.first_clear`
- `audit.layer1.first_clear.reward`
- `audit.tutorial.layer1_boss_help.set`
- `audit.tutorial.layer1_boss_help.consume`
- `audit.tutorial.layer1_boss_bonus.grant`

COMBAT SIGNAL v1:
- 専用audit eventは追加しない。
- `audit.explore.end` / `audit.battle.result.view` 系payloadの `summary.combat_signal` に、発生した戦術、予兆/発動イベント、発動回数を含める。
- `request_id` は探索操作の既存IDをそのまま使う。

### 4.2 経済/在庫
- `audit.coin.delta`
- `audit.streak.bonus`
- `audit.drop`
  - 通常出撃のパーツドロップ。payload は既存 `area_key / battle_no / drop_type / part_type / part_key / rarity / plus / storage_status / auto_sold / growth_tendency_key / growth_tendency_label` を維持する。
  - 戦利品即時評価として `dropped_part_instance_id`, `compared_equipped_part_instance_id`, `total_delta`, `standout_stat`, `recommendation_key` を追加する。
  - `recommendation_key=update_candidate` は現在装備より総合性能が閾値以上改善する場合のみ。自動装備や報酬付与は行わない。
  - 表示数値インフレ化 v1 以降も `total_delta` は内部値。UI表示用の100倍値は保存しない。
- `audit.inventory.delta`

### 4.3 育成
- `audit.fuse`
- `audit.part.evolve`
- `audit.core.drop`
- `audit.build.confirm`
- `audit.daily_research.view`
- `audit.daily_research.progress`
- `audit.daily_research.complete`
- `audit.daily_research.reward`

### 4.4 機体/展示
- `audit.robot.rename`
- `audit.robot.decompose`
- `audit.robot.share`
- `audit.robot.preset.save`
- `audit.robot.preset.apply`
- `audit.robot.preset.rename`
- `audit.robot.preset.delete`
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
- `audit.faction.change`
  - 初回選択後の陣営変更時に記録する。payload は `before_faction`, `after_faction`, `changed_at`, `cooldown_days` を含める。
- `audit.faction.points.add`
  - 陣営ポイント加算時に記録する。payload は `week_key`, `faction`, `event_type`, `points`, `counters`, `payload`, `log_created` を含める
  - 未所属ユーザーは加算されない
  - 再集計時は二重監査を避けるため、このauditは生成しない
- `audit.faction.weekly_bonus.claim`
  - `/faction` の週次参加特典を受け取った時に記録する。payload は `user_id`, `week_key`, `faction_key`, `activity_score`, `coin_reward`, `badge_key`, `coins_before`, `coins_after` を含める。

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

### 4.8.1 研究モジュール
- `audit.module.drop`
- `audit.module.select`
- `audit.module.pity.progress`
- `audit.module.pity.grant`
- `audit.module.combine`
- `audit.module.catalog.register`
- `audit.module.lock`
- `audit.module.unlock`
- `audit.module.sell`
- `audit.module.synthesis.preview`
- `audit.module.synthesis.consume`
- `audit.module.synthesis.create`
- `audit.module.synthesis.result`
- `audit.module.strategy.apply`
- `audit.module.strategy.result`
- `audit.module.protocol.set`
- `audit.module.protocol.clear`
- `audit.module.protocol.auto_clear`
- `audit.module.protocol.start`
- `audit.module.protocol.trigger`
- `audit.module.protocol.finish`
- `audit.module.battle_code.set`
- `audit.module.battle_code.clear`
- `audit.module.battle_code.start`
- `audit.module.battle_code.condition`
- `audit.module.battle_code.trigger`
- `audit.module.battle_code.consume`
- `audit.module.battle_code.finish`
- `audit.module.battle_code.library.create`
- `audit.module.battle_code.library.overwrite`
- `audit.module.battle_code.library.delete`
- `audit.module.battle_code.library.select`
- `audit.module.battle_code.library.unselect`
- `audit.module.battle_code.library.label_update`
- `audit.module.battle_code.library.share`
- `audit.module.battle_code.library.migrate`
- `audit.module.battle_code.library.fallback`
- `audit.module.battle_code.library.stats_update`
- `audit.module.reroll`

補足:
- `audit.module.strategy.apply` は出撃開始時に active module の実効補正を適用した記録。
- `audit.module.strategy.result` は出撃終了時に active module 使用結果を記録する。
- `audit.module.synthesis.result` と `audit.module.strategy.result` は `/comms/personal` の個人ログ表示対象。
- `audit.module.reroll` はモジュール再調整時に記録する。payload は `user_id`, `module_id`, `rarity`, `cost`, `before_stats`, `after_stats`, `coins_before`, `coins_after` を含める。
- `MODULE_SYNTHESIS_RESULT` / `MODULE_STRATEGY_RESULT` は将来の公開イベント候補だが、現時点では世界ログ公開に使わない。

### 4.8.2 ソロ研究所
- `audit.research.task.assign`
- `audit.research.task.progress`
- `audit.research.task.complete`
- `audit.research.task.claim`
- `audit.research.task.hold`
- `audit.research.level.up`
- `audit.research.discovery`
- `audit.personal_record.update`

補足:
- 研究タスク進行は `battle_id` または `request_id` を receipt として記録し、同一イベントの二重処理を防ぐ。
- `audit.research.task.complete` と `audit.research.task.claim` は Phase 1 では同一処理内で連続記録される。
- `audit.personal_record.update` は改善時だけ記録する。

### 4.8.3 ロボ工場
- `audit.factory.ensure_defaults`
- `audit.factory.claim`
- `audit.factory.upgrade`
- `audit.factory.prize.ensure_defaults`
- `audit.factory.prize.claim`
- `audit.coin.delta`

補足:
- `audit.factory.ensure_defaults` はユーザーの工場施設3件を初期作成した記録。
- `audit.factory.claim` は施設から工場ポイントを回収した記録。payload は `user_id`, `facility_key`, `level_before`, `level_after`, `points_gained`, `factory_points_before`, `factory_points_after` を含める。
- `audit.factory.upgrade` は施設強化時に記録する。payload は `user_id`, `facility_key`, `level_before`, `level_after`, `cost`, `coins_before`, `coins_after` を含める。
- `audit.factory.prize.ensure_defaults` は工場交換所の初期景品を投入した記録。
- `audit.factory.prize.claim` は工場景品交換時に記録する。payload は `user_id`, `prize_key`, `prize_type`, `cost_points`, `factory_points_before`, `factory_points_after`, `grant_key` を含める。
- 工場ポイントは独立ポイントであり、本編戦闘、強化、進化には使わない。

### 4.9 陣営内表彰
- `audit.faction.awards.recalculate`
- `audit.faction.awards.badges.grant`

補足:
- 管理者が `faction_weekly_awards` を手動再集計した記録。
- payload には `week_key`, `created_or_updated_count`, `actor_admin_id` を含める。
- 管理者が表彰バッジを付与した記録では、payload に `week_key`, `granted_count`, `processed_count`, `actor_admin_id` を含める。
- 表彰は `/faction` 内の名誉表示であり、世界ログ公開イベント、陣営勝敗、戦闘補正には使わない。

### 4.10 陣営週間ミッション
- `audit.faction.missions.create_default`
- `audit.faction.missions.recalculate`
- `audit.faction.missions.finalize`
- `FACTION_MISSION_RESULT`（公開世界ログ）

補足:
- `audit.faction.missions.create_default` は管理者が週次ミッションを作成した記録。
- `audit.faction.missions.recalculate` は管理者が進捗を再集計した記録。
- `audit.faction.missions.finalize` は管理者が週次結果を確定した記録。
- payload には `week_key`, `mission_count`, `updated_progress_count`, `actor_admin_id` を含める。
- `FACTION_MISSION_RESULT` は `week_key` ごとに1件だけ作成し、payload に達成陣営の `mission_title`, `faction_key`, `faction_name`, `current_value`, `target_value` を含める。

### 4.11 陣営守護戦
- `audit.faction.guardian.set`
- `audit.faction.guardian.auto_pick`
- `audit.faction.guardian.recalculate`
- `audit.faction.guardian.finalize`
- `FACTION_GUARDIAN_RESULT`（公開世界ログ）

補足:
- 守護機は承認済み `lab_robot_submissions` から週ごと・陣営ごとに選定する。
- `audit.faction.guardian.set` は管理者が投稿を手動で守護機に設定した記録。
- `audit.faction.guardian.auto_pick` は管理者が自動選定した記録。
- `audit.faction.guardian.recalculate` は出撃勝利 / ボス撃破 / 進化成功から解析ダメージを再集計した記録。
- `audit.faction.guardian.finalize` は週次結果を確定した記録。
- payload には `week_key`, `faction_key`, `submission_id`, `attack_count`, `total_damage`, `actor_admin_id` を可能な範囲で含める。
- `FACTION_GUARDIAN_RESULT` は `week_key` ごとに1件だけ作成し、payload に `attacker_faction`, `target_faction`, `guardian_name`, `parsed_percent`, `current_hp`, `max_hp` を含める。
- 守護戦は直接PvP、戦闘補正、報酬配布には使わない。

### 4.12 陣営領土マップ
- `audit.faction.territory.ensure`
- `audit.faction.territory.recalculate`
- `audit.faction.territory.finalize`
- `FACTION_TERRITORY_RESULT`（公開世界ログ）

補足:
- `audit.faction.territory.ensure` は管理者が初期5エリアを作成または確認した記録。
- `audit.faction.territory.recalculate` は管理者が週次領土スコアを再計算した記録。
- `audit.faction.territory.finalize` は管理者が週次領土マップを確定した記録。
- payload には `week_key`, `updated_count`, `changed_areas`, `actor_admin_id` を含める。
- `FACTION_TERRITORY_RESULT` は `week_key` ごとに1件だけ作成し、payload に `area_counts`, `changed_areas` を含める。
- 領土マップは世界戦況の見える化であり、直接PvP、戦闘補正、報酬配布には使わない。

### 4.13 陣営称号・肩書き
- `audit.faction.titles.grant_weekly`
- `audit.faction.titles.grant_manual`
- `FACTION_TITLE_GRANT_RESULT`（公開世界ログ）

補足:
- `audit.faction.titles.grant_weekly` は管理者が週次称号を自動付与した記録。
- `audit.faction.titles.grant_manual` は管理者が特定ユーザーへ称号を手動付与した記録。
- payload には `week_key`, `granted_count`, `titles`, `actor_admin_id` を可能な範囲で含める。
- `FACTION_TITLE_GRANT_RESULT` は `week_key` ごとに1件だけ作成し、payload に `granted_count`, `titles` を含める。
- 称号は名誉・表示・記録用であり、直接PvP、戦闘補正、報酬配布には使わない。

### 4.13.1 陣営イベント週
- 管理者操作:
  - `audit.faction.weekly_event.set`
  - `audit.faction.weekly_event.activate`
  - `audit.faction.weekly_event.finalize`
  - `audit.faction.weekly_event.cancel`
- 公開世界ログ:
  - `FACTION_WEEKLY_EVENT_STARTED`
  - `FACTION_WEEKLY_EVENT_FINALIZED`
- payload には `week_key`, `event_key`, `event_name`, `description`, `effect_summary`, `status`, `actor_admin_id` を可能な範囲で含める。
- 陣営イベント週は既存陣営コンテンツの注目軸。通常出撃、ボス戦、本編ステータス、パーツ性能、コイン報酬には影響させない。

### 4.13.2 陣営ショップ
- 管理者操作:
  - `audit.faction.shop.ensure_defaults`
  - `audit.faction.shop.create`
  - `audit.faction.shop.update`
- ユーザー操作:
  - `audit.faction.shop.purchase`
  - `audit.faction.shop.equip`
- payload には `user_id`, `item_key`, `item_type`, `price_paid_coins`, `coins_after`, `slot_key`, `actor_admin_id` を可能な範囲で含める。
- 陣営ショップは既存コインで表示用記念品を交換する機能。新通貨を作らず、戦闘ステータス、通常出撃、ボス戦、観測塔、報酬には影響させない。

### 4.13.3 陣営クエスト
- 管理者操作:
  - `audit.faction.quest.generate`
  - `audit.faction.quest.finalize`
  - `audit.faction.quest.cancel`
- ユーザー操作:
  - `audit.faction.quest.reward_claim`
- 内部ログ:
  - `audit.faction.quest.progress`
  - `audit.faction.quest.complete`
- 世界イベント:
  - `FACTION_WEEKLY_QUEST_COMPLETED`
  - `FACTION_WEEKLY_QUEST_RESULT`
- payload には `week_key`, `faction_key`, `quest_id`, `quest_key`, `quest_type`, `current_value`, `target_value`, `user_id`, `reward_coins`, `reward_facility_material`, `actor_admin_id` を可能な範囲で含める。
- 陣営クエストは週次の共同目標。報酬は既存コインと施設資材に限定し、戦闘ステータス、通常出撃、ボス戦、観測塔、パーツ性能には影響させない。

### 4.14 管理者操作（追加）
- `audit.admin.user.ban`
- `audit.admin.user.unban`
- `audit.admin.user.protect_login`
- `audit.admin.user.unprotect_login`
- `audit.admin.user.delete`
  - payload推奨: `deleted_user_id`, `deleted_username`, `actor_admin_id`

### 4.15 パーツ保護
- `audit.part.lock`
- `audit.part.unlock`
- payload推奨: `part_instance_id`, `part_key`, `part_name`, `rarity`, `plus`, `locked`

### 4.16 システム
- `audit.system.maintenance_block`
- `FACTION_WAR_RESULT`（世界イベント）
- `audit.faction.report.recalculate`
- `audit.faction.report.finalize`
- `FACTION_WEEKLY_REPORT`（世界イベント）
- `FACTION_MISSION_RESULT`（世界イベント）
- `FACTION_GUARDIAN_RESULT`（世界イベント）
- `FACTION_TERRITORY_RESULT`（世界イベント）
- `FACTION_TITLE_GRANT_RESULT`（世界イベント）
- `FACTION_WEEKLY_EVENT_STARTED`（世界イベント）
- `FACTION_WEEKLY_EVENT_FINALIZED`（世界イベント）
- `FACTION_WEEKLY_QUEST_COMPLETED`（世界イベント）
- `FACTION_WEEKLY_QUEST_RESULT`（世界イベント）
- `RESEARCH_ADVANCE` / `RESEARCH_UNLOCK`（世界イベント）
- `LAB_RACE_WIN` / `LAB_RACE_UPSET` / `LAB_RACE_POPULAR_ENTRY`（実験室公開イベント）

### 4.17 観測塔
- 監査ログ:
  - `audit.tower.run.start`
  - `audit.tower.battle`
  - `audit.tower.run.complete`
  - `audit.tower.run.failed`
  - `audit.tower.run.abandon`
  - `audit.tower.record.update`
  - `audit.tower.reward.grant`
  - `audit.tower.reward.skip_duplicate`
- 公開世界ログ:
  - `TOWER_MILESTONE_REACHED`
  - `TOWER_PERSONAL_BEST`
  - `TOWER_WEEKLY_TOP`
  - `TOWER_ALL_TIME_RECORD`
- 公開世界ログは全バトルではなく、5階/10階/以降10階ごとの節目、5階以上の自己ベスト、週間トップ更新、全ユーザー通算最高更新だけを記録する。

### 陣営代表模擬戦
- 管理者操作:
  - `audit.faction.representative.auto_pick`
  - `audit.faction.representative.set`
  - `audit.faction.representative.matches.generate`
  - `audit.faction.representative.matches.run`
- 公開世界ログ:
  - `FACTION_REPRESENTATIVE_MATCH_RESULT`
- 代表模擬戦は週次の非同期イベント。通常出撃、ボス戦、本編ステータス、報酬には影響させない。

### 守護機演習
- 管理者操作:
  - `audit.faction.guardian_duel.generate`
  - `audit.faction.guardian_duel.run`
- 公開世界ログ:
  - `FACTION_GUARDIAN_DUEL_RESULT`
- 守護機演習は投稿ロボ由来の守護機を使う週次模擬戦。投稿ロボの本編性能、通常出撃、ボス戦、本編ステータス、報酬には影響させない。

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
- 観測塔の公開世界ログ payload は可能な範囲で以下を保持する
  - `user_id`
  - `username`
  - `display_name`
  - `robot_instance_id`
  - `robot_name`
  - `floor`
  - `previous_best_floor`
  - `previous_weekly_top_floor`
  - `previous_all_time_record_floor`
  - `event_label`
  - `tower_run_id`
  - 互換用に `run_id` / `reached_floor` を残してよい

- 陣営週間レポート payload は可能な範囲で以下を保持する
  - `week_key`
  - `top_faction`
  - `top_faction_name`
  - `activity_score`
  - `explore_count`
  - `boss_defeat_count`
  - `evolve_count`

- 第1層試験支援 payload は可能な範囲で以下を保持する
  - `user_id`
  - `robot_instance_id`
  - `boss_key`
  - `protection_applied`
  - `hp_multiplier`
  - `atk_multiplier`
  - `def_multiplier`
  - `acc_multiplier`
  - `player_hp_multiplier`
  - `player_atk_multiplier`
  - `player_acc_multiplier`
  - `alert_guaranteed`
  - `reward_granted`
  - `duplicate_skip_reason`

## 6. 公開世界ログの重複防止
- 観測塔公開世界ログは `user_id + event_type + floor + tower_run_id` で重複投稿を避ける。
- `tower_run_id` がない場合は `user_id + event_type + floor` で重複投稿を避ける。
- 陣営週間レポートの公開世界ログ `FACTION_WEEKLY_REPORT` は `week_key` ごとに1件だけ作成する。
- 陣営週間ミッションの公開世界ログ `FACTION_MISSION_RESULT` は `week_key` ごとに1件だけ作成する。
- 陣営守護戦の公開世界ログ `FACTION_GUARDIAN_RESULT` は `week_key` ごとに1件だけ作成する。
- 陣営代表模擬戦の公開世界ログ `FACTION_REPRESENTATIVE_MATCH_RESULT` は `week_key` ごとに1件だけ作成する。
- 守護機演習の公開世界ログ `FACTION_GUARDIAN_DUEL_RESULT` は `week_key` ごとに1件だけ作成する。
- 陣営領土マップの公開世界ログ `FACTION_TERRITORY_RESULT` は `week_key` ごとに1件だけ作成する。
- 陣営称号の公開世界ログ `FACTION_TITLE_GRANT_RESULT` は `week_key` ごとに1件だけ作成する。
- 陣営イベント週の公開世界ログ `FACTION_WEEKLY_EVENT_STARTED` / `FACTION_WEEKLY_EVENT_FINALIZED` は `week_key` ごとに各1件だけ作成する。
- 陣営クエスト達成ログ `FACTION_WEEKLY_QUEST_COMPLETED` は `quest_id` ごとに1件だけ作成する。
- 陣営クエスト週次結果 `FACTION_WEEKLY_QUEST_RESULT` は `week_key` ごとに1件だけ作成する。

## 7. 管理UI
- `/admin/audit` で検索
- 推奨フィルタ:
  - `user_id`
  - `event_type`
  - `request_id`
  - `after` / `before`

## 8. 集計除外/認証防御
- `audit.admin.analytics.exclude`
  - 管理者がユーザーを通常プレイヤー集計から除外した記録。
  - payload は `target_user_id`, `target_username`, `actor_admin_id`, `reason`, `previous_analytics_excluded`, `new_analytics_excluded` を含める。
- `audit.admin.analytics.include`
  - 管理者がユーザーを通常プレイヤー集計へ戻した記録。
  - payload は `target_user_id`, `target_username`, `actor_admin_id`, `previous_analytics_excluded`, `new_analytics_excluded` を含める。
- `audit.security.registration.suspicious`
  - 登録入力が攻撃スキャン/不審登録候補に該当した記録。
  - payload は `suspicious_reasons`, `target_user_id`, `ip_hash` を可能な範囲で含める。
- `audit.security.registration.rate_limited`
- `audit.security.login.rate_limited`

## 9. 初回体験ファネル
- `audit.onboarding.home.first_view`
- `audit.onboarding.home_ready`
  - 初回ホーム準備状態。payload は `user_id`, `has_active_robot`, `layer1_available`, `explore_ct_seconds`, `next_action_type`, `next_action_visible`, `first_mission_visible`, `first_explore_cta_visible`, `home_session_id`。
- `audit.onboarding.first_explore_cta_view`
  - 第1層初出撃CTA表示。payload は `surface`, `area_key`, `disabled`, `disabled_reason`, `entry_source`, `home_session_id`。
  - 初回出撃フォーカスの surface は `first_sortie_focus`、entry_source は `next_action_first_explore`。
- `audit.onboarding.first_explore_cta_click`
  - 第1層初出撃CTAクリック。payload は `surface`, `area_key`, `entry_source`, `home_session_id`, `seconds_from_home_view`。
- `audit.explore.start`
  - 初回出撃フォーカスCTAは `entry_source=next_action_first_explore` を使う。
  - `entry_source` が空の第1層初回POSTは、直前ホーム表示が確認できる場合のみ `next_action_first_explore` へ補完する。推定不能な流入は `unknown` のまま残す。
- `audit.onboarding.layer1.first_start`
- `audit.onboarding.layer1.first_complete`
- `audit.onboarding.layer1.first_win`
- `audit.battle.result.view`
- `audit.explore.retry.click`
- `audit.onboarding.explore.second_start`
- `audit.onboarding.explore.third_start`
- `audit.onboarding.part.first_drop`
- `audit.onboarding.build.first_complete`

補足:
- `/admin/metrics` の新規初回体験は `build_new_user_onboarding_funnel(...)` を正本にする。
- 登録日コホートと直近行動ファネルを混ぜず、同一画面内のカードと棒グラフは同じ共通ファネル結果を参照する。
- `audit.explore.failed` は正常完了ではない出撃試行の診断用。payload は `area_key`, `stage`, `reason`, `exception_class`, `request_id` を含める。`audit.explore.end` の意味は変更しない。

## 9.1 今日の研究指令
- `audit.daily_research.view`
  - ホームで今日の研究指令3件を表示した記録。payload は `day_key`, `mission_count`, `completed_count`。
- `audit.daily_research.progress`
  - 指令進捗。payload は `day_key`, `mission_key`, `mission_type`, `progress_before`, `progress_after`, `target`, `source`, `reward_coins`。
- `audit.daily_research.complete`
  - 指令または2件達成記録の完了。payload は progress と同形式。
- `audit.daily_research.reward`
  - 指令報酬または3件完了報酬。payload は progress と同形式に加え、全完了時は `streak`。
- `audit.daily_research.task.create`
  - 当日3件の生成。payload は `day_key`, `mission_key`, `category`, `condition_key`, `target_area_key`, `target`, `recommended`。
- `audit.daily_research.all_complete`
  - 3件すべて完了。payload は `day_key`, `mission_key=daily_research_all_complete`, `progress_before`, `progress_after`, `target=3`, `source`, `all_complete`。

二重加算防止:
- `daily_research_progress_receipts` で `user_id, day_key, mission_key, source_key` を一意化する。
- `source_key` は `request_id` 優先、なければ元イベントIDまたはbattle_idを使う。
- 同一操作内のdaily_research auditは元操作と同じ `request_id` を保持する。

## 9.2 週替わり挑戦機《異常個体》
- `audit.anomaly.cycle.create`
  - 週次個体が初回生成された記録。payload は `week_key`, `template_key`, `display_name`, `starts_at`, `ends_at`。
- `ANOMALY_APPEARED`
  - 週次個体の公開世界ログ。週初回生成時のみ。
- `audit.anomaly.view`
  - `/anomaly` 表示。payload は `week_key`, `template_key`, `challenge_class`, `total_explores`。
- `audit.anomaly.attempt`
  - 挑戦結果。payload は `week_key`, `cycle_id`, `template_key`, `challenge_class`, `result`, `turns`, `analysis_rate`, `damage_dealt`, `reward_coins`。
- `audit.anomaly.best`
  - 自己ベスト更新。payload は `analysis_rate_before/after`, `turns_before/after`, `result_before/after`。
- `ANOMALY_CLASS_FIRST_CLEAR`
  - 管理者・テスト・集計除外を除く、級別の週初撃破世界ログ。
- `ANOMALY_FASTEST_RECORD`
  - 管理者・テスト・集計除外を除く、級別最速撃破更新世界ログ。

二重加算防止:
- `anomaly_attempts.request_id` を一意化する。
- `anomaly_weekly_rewards` は `week_key, user_id, challenge_class` を一意化し、週・級ごとの初回撃破報酬を二重付与しない。
- 異常個体挑戦は `audit.anomaly.attempt` と同じ `request_id` で今日の研究指令にも進捗反映する。

## 10. 研究モジュール v2
- `audit.module.synthesis.preview`
  - 研究合成確認。payload に `origin_module_a_id`, `origin_module_b_id`, `research_policy_key`, `cost_coins` を含める。
- `audit.module.synthesis.create` / `audit.module.synthesis.consume` / `audit.module.synthesis.result`
  - 研究合成の消費・生成・結果。payload に `research_policy_key`, `research_policy_label`, `trait_key`, `trait_label`, `trait_value`, `trait_grade`, `synthesis_generation` を含める。
- `audit.module.strategy.apply`
  - 出撃開始時の選択中モジュール適用。payload に `module_instance_id`, `module_key`, `module_name`, 各基礎補正を含める。
- `audit.module.strategy.result`
  - 出撃終了時のモジュール結果。payload に `module_trait_key`, `module_trait_trigger_count` を含める。
- `audit.module.trait.trigger`
  - 作戦特性が発動した戦闘の集約ログ。1戦1件で `trait_key`, `trait_label`, `trigger_count`, `trigger_labels` を含める。
- `audit.module.protocol.set` / `audit.module.protocol.clear` / `audit.module.protocol.auto_clear`
  - ACTIVE PROTOCOL の手動設定、手動解除、OS構成変更による自動解除。
- `audit.module.protocol.start`
  - 出撃開始時のプロトコルスナップショット。payload に `protocol_key`, `protocol_name`, `os_name`, `brand_counts` を含める。
- `audit.module.protocol.trigger`
  - 実際に発動した瞬間だけ記録。payload に `activation_turn`, `effect_type`, `damage_reduced`, `healing_amount`, `bonus_damage`, `recoil_damage`, `guaranteed_hit`, `critical_bonus` を含める。
- `audit.module.protocol.finish`
  - 1出撃1回。payload に `protocol_activation_count`, `protocol_summary_json`, `result_win`, `turn_count` を含める。
- `audit.module.battle_code.set` / `audit.module.battle_code.clear`
  - 次回出撃用BATTLE CODE設定。payload に `condition_key`, `effect_key`, `condition_key_b`, `effect_key_b`, `code_version`, `logic_entries`, `battle_code_name`, `os_name`, `protocol_key` を含める。
- `audit.module.battle_code.start`
  - 出撃開始時のBATTLE CODEスナップショット。
- `audit.module.battle_code.condition`
  - 条件成立。payload に `condition_event_index`, `activation_turn`, `trigger_reason`, `triggered_logic`, `triggered_condition`, `triggered_effect` を含める。
- `audit.module.battle_code.trigger`
  - 実際の効果付与。payload に `activation_index`, `triggered_logic`, `effect_type`, `effect_value`, `duration_turns`, `healing_amount`, `guaranteed_hit` などを含める。
- `audit.module.battle_code.consume`
  - 次撃・次回被弾などの消費。payload に `consume_index`, `trigger_reason` を含める。
- `audit.module.battle_code.finish`
  - 1出撃1回。payload に `battle_code_activation_count`, `battle_code_condition_event_count`, `triggered_logic`, `fallback_success`, `battle_code_summary_json`, `result_win`, `turn_count` を含める。
- `audit.module.battle_code.library.*`
  - 保存ライブラリの作成、上書き、削除、選択、解除、用途更新、共有文作成、旧設定移行、無効コードfallback、統計更新。
  - payload に `battle_code_library_id`, `slot_number`, `condition_key`, `effect_key`, `condition_key_b`, `effect_key_b`, `code_version`, `logic_entries`, `usage_label`, `is_selected`, `is_usable` を含める。

## 11. 第1層 初回体験改善
- `audit.onboarding.first_three_progress`
  - 初回3出撃の進行。payload は `user_id`, `completed_explore_count`, `target`, `area_key`。
- `audit.onboarding.first_three_complete`
  - 初回3出撃完了。payload は `user_id`, `completed_explore_count`, `reward_coins`, `area_key`。
- `audit.onboarding.first_three_reward`
  - 初回3出撃報酬付与。`delta_coins=100`。
- `audit.onboarding.first_upgrade.shown`
  - 初回3出撃後の機体更新導線表示。payload は `user_id`, `source`, `explore_end_count`, `active_robot_id_before`, `recommended_part_instance_id`, `recommended_part_type`, `current_total`, `recommended_total`, `delta_total`, `entry_source`。
- `audit.onboarding.first_upgrade.click`
  - 推奨パーツ/編成導線クリック。payload は `user_id`, `source`, `recommended_part_instance_id`, `recommended_part_type`, `entry_source`。
- `audit.onboarding.first_upgrade.skip`
  - 初回機体更新導線をスキップして出撃した記録。payload は `user_id`, `source`, `area_key`, `active_robot_id_before`。
- `audit.onboarding.first_upgrade.complete`
  - `/build/confirm` で初回機体更新が完了した記録。payload は `robot_instance_id`, `changed_part_type`, `changed_part_types`, `before_part_instance_ids`, `after_part_instance_ids`, `before_total`, `after_total`, `delta_total`, `before_stats`, `after_stats`。
- `audit.build.confirm`
  - 初回機体更新導線では既存payloadに `mode`, `base_robot_id`, `changed_part_types`, `changed_count`, `first_update_flow`, `source` を追加する。
  - `first_update_flow=true` は `guide=first_upgrade`、`mode=modify`、初回更新対象ユーザーのconfirmを表す。
- `audit.explore.start`
  - 初回更新結果画面からの再出撃は `entry_source=first_robot_upgrade_result` を使う。
- `audit.boss.alert.progress`
  - 第1層通常勝利で警報値が進んだ記録。payload は `user_id`, `area_key`, `boss_key`, `before`, `after`, `threshold`, `source`。
- `audit.boss.alert.ready`
  - 第1層ボス警報が満了した記録。
- `audit.boss.alert.consume`
  - 保証遭遇で警報を消費した記録。
- `audit.boss.encounter`
  - 既存イベント。第1層では `encounter_source=random|alert_guarantee` を追加する。

## 12. 第1層ボス再挑戦保証
- `audit.boss.encounter`
  - 第1層では payload に `boss_key`, `boss_source`, `is_first_encounter`, `retry_available`, `attempt_number` を含める。
  - 初回通常遭遇は `boss_source=normal`, `is_first_encounter=true`, `retry_available=true`, `attempt_number=1`。
  - 直接再挑戦は `boss_source=guaranteed_retry`, `is_first_encounter=false` とし、初遭遇人数には含めない。
- `audit.boss.attempt`
  - 再挑戦開始時は `entry_source=boss_retry`, `boss_source=guaranteed_retry`, `attempt_number`, `retry_state` を含める。
- `audit.explore.start`
  - 再挑戦時は `entry_source=boss_retry`, `boss_key`, `boss_source=guaranteed_retry`, `retry_state` を含める。
  - ボス敗北リカバリーから第1層通常戦へ戻る場合は `entry_source=boss_recovery_normal` を使う。
- `audit.boss.retry.result`
  - payload は `boss_key`, `area_key`, `attempt_number`, `result`, `defeated`, `turn_count`, `failure_reason`, `first_encountered_at`, `elapsed_seconds_from_first_encounter`。
- `audit.boss.retry.cta.view` / `audit.boss.retry.cta.click` / `audit.boss.retry.parts_click`
  - payload は `boss_key`, `surface`, `attempt_number`, `ct_remaining_seconds`。
  - `surface` は `home_next_action`、`battle_result`、`parts_return` を想定する。
  - 初敗北リカバリーUI経由の場合は `recovery_key=first_boss_recovery` と `recommended_action=strengthen/build/boss_retry` を含める。
- `audit.onboarding.boss_retry.guide_view` / `audit.onboarding.boss_retry.guide_click`
  - 第1層ボス敗北後の調整ガイド表示/クリック。payload は `boss_key`, `area_key`, `surface`, `attempt_number`, `diagnosis_key`, `recommended_part_instance_id`, `recommended_part_type`。
  - 初敗北リカバリーUI経由の場合は `recovery_key=first_boss_recovery` と `recommended_action=build` を含める。
- `audit.onboarding.boss_retry.adjust_complete`
  - `/build?guide=boss_retry` 経由で1部位以上を調整した記録。payload は `changed_part_types`, `before_part_instance_ids`, `after_part_instance_ids`, `before_stats`, `after_stats`, `delta_total`。
- `audit.onboarding.boss_retry.start` / `audit.onboarding.boss_retry.success`
  - 再挑戦開始と再挑戦経由撃破の記録。payload は `entry_source=boss_retry`, `diagnosis_key`, `turn_count`, `player_hp`, `player_max_hp` など。

## 13. 第2層解放・次目標導線
- `audit.boss.defeat`
  - 第1層固定ボス初撃破時は payload に `boss_key`, `area_key`, `is_first_defeat=true`, `unlocked_layer=2`, `layer_unlock_triggered=true`, `entry_source`, `attempt_number` を含める。
  - 2回目以降や既解放時は `layer_unlock_triggered=false` または `unlocked_layer=null`。
- `audit.layer.unlock`
  - 第2層初解放時に1回記録する。
  - payload は `user_id`, `from_layer=1`, `unlocked_layer=2`, `trigger_type=boss_defeat`, `trigger_boss_key`, `is_first_unlock`。
- `audit.layer.unlock.inconsistent`
  - 第1層ボス未撃破なのに第2層解放済みの不整合を管理監査へ残す。ユーザー画面ではエラーにしない。
- `audit.layer2.unlock_cta.view` / `audit.layer2.unlock_cta.click`
  - payload は `surface`, `entry_source`, `ct_remaining_seconds`, `notice_seen`, `layer2_unlocked_at`。
  - surface は `boss_result`, `home_next_action`, `area_select` を想定する。
- `audit.explore.start`
  - `area_key=layer_2` では `is_first_layer2_explore`, `entry_source`, `seconds_from_layer_unlock`, `layer2_explore_count_before` を含める。
  - 初回のみ `is_first_layer2_explore=true`、2回目以降は false。
  - 結果画面CTA経由は既存 `entry_source=layer2_unlock_result` を使い、新しい同義sourceは追加しない。

## 14. 第6層攻略記録
- 新規イベントは追加しない。v1は既存 `audit.explore.end` と `audit.boss.defeat` を正本にする。
- `audit.explore.end`
  - 第6層通常戦記録は payload の `area_key`, `player.robot_instance_id`, `result.win`, `result.turns`, `result.battle_id`, `result.damage_taken_total` を使用する。
  - `request_id` が同じ探索終了ログは同一操作として扱い、集計時に1件へ重複排除する。
  - `result.is_area_boss=true` または boss payload があるログは通常戦の最短/安定/研究熱から除外する。
- `audit.boss.defeat`
  - `area_key=layer_6_final` を第6層最終試験撃破記録として扱う。
- 管理メトリクス
  - `/admin/metrics` は上記auditから第6層到達者、通常戦出撃、勝率、平均ターン、ボス遭遇/撃破、記録掲載者を算出する。

## 15. パーツ機構特性
- 新規イベントは追加しない。v1は既存イベントのpayload拡張で扱う。
- `audit.explore.end`
  - payload `player.active_trait_keys`: 装備中R以上パーツの有効機構特性key一覧。
  - payload `player.triggered_trait_keys`: その出撃中に発動した機構特性key一覧。
  - payload `player.active_mechanism_traits`: `{key, label, slot}` の表示補助情報。
- `audit.anomaly.attempt`
  - payload `part_mechanism.active_trait_keys`
  - payload `part_mechanism.triggered_trait_keys`
  - payload `part_mechanism.triggered_labels`
  - payload `part_mechanism.enemy_trait_key`
  - payload `part_mechanism.observation_lines`
- `/admin/metrics` は上記payloadからR+装備ユーザー、発動戦闘数、特性別勝率、第6層勝率、異常個体CLEAR率を算出する。
- 特性発動ごとの個別auditは出さない。1出撃/1挑戦の集約payloadを正本にする。

## 16. モジュール研究
- 新規auditイベントは追加しない。既存 `audit.module.synthesis.consume/create/result` と `audit.coin.delta` を維持する。
- 合成成功時の既存payloadへ以下を追加する。
  - `fusion_record_id`: `module_fusion_records.id`
  - `result_module_instance_id`: 合成結果の `user_research_modules.id`
  - `generation`: 既存合成結果の世代
  - `primary_lineage_key`: 結果モジュールの公開主系統key
  - `input_count`: v1では `2`
  - `provenance_version`: 系譜記録snapshot形式の版
- payloadには内部確率、内部重み、乱数seed、継承scoreを追加しない。
