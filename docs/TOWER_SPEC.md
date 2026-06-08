# 観測塔 -ASTRAL SPIRE- 仕様

## 目的

第4層到達者向けの記録型やりこみコンテンツ。
3機小隊で深層を登り、最強1機だけでなく複数機体の育成・役割分担を評価する。

本編進行には必須ではない。

## 解放条件

- `users.max_unlocked_layer >= 4`
- 第4層クリア後限定ではない
- 第1〜第3層ユーザーにはホーム導線を出さない

## ルール v1

- 3機の `robot_instances` を選んで挑戦開始
- 同じ `robot_instance_id` は重複選択不可
- 1階につき1機が戦う
- 戦闘は既存の1対1シミュレーションを再利用
- 使用した機体は冷却中になる
- 3機すべてが1回ずつ戦うと冷却解除
- 敗北した時点で run は `failed`
- 10階突破で run は `completed`
- `reached_floor` と自己最高記録を保存

## ルート

- `GET /tower`
- `POST /tower/start`
- `POST /tower/battle`
- `GET /tower/result/<run_id>`
- `GET /tower/ranking`
- `GET /admin/tower`

## DB

- `tower_runs`
- `tower_run_battles`
- `tower_run_cooling`
- `user_tower_records`
- `tower_weekly_environment`

## 週替わり観測環境

v1では表示と敵抽選の軽い偏りに使う。
強いステータス補正や本編報酬補正は入れない。

- 安定観測週
- 機動観測週
- 暴走観測週
- 重装観測週
- 霧界観測週

## 本編との差分

- `/explore` のCTを使わない
- 通常ドロップを出さない
- ボス警報や層解放を進めない
- 本編報酬量を変更しない
- 敵マスタは再利用するが、観測塔専用にスケールする

## ログ

監査ログ:

- `audit.tower.run.start`
- `audit.tower.battle`
- `audit.tower.run.complete`
- `audit.tower.run.failed`
- `audit.tower.record.update`

世界ログ:

- `TOWER_BEST_FLOOR`
- `TOWER_MILESTONE`

## 報酬方針

v1では戦力インフレ報酬を出さない。
主報酬は記録、ランキング、世界ログ。

将来候補:

- 称号
- バッジ
- DECOR
- 少量コイン

## テスト観点

- 第4層未到達ユーザーは利用不可
- 第4層到達ユーザーのみホーム導線表示
- 3機未満、重複選択を拒否
- run 作成と cooling 作成
- 冷却中ロボの再出撃拒否
- 3機使用後の冷却解除
- 10階突破で `completed`
- 敗北で `failed`
- 記録更新と世界ログ保存
- `/explore` 既存導線が壊れていない
