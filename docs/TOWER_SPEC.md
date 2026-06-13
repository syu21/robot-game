# 観測塔 -ASTRAL SPIRE- 仕様

## 目的

第4層到達者向けの記録型やりこみコンテンツ。
3機のロボでどこまで登れるか挑戦し、最強1機だけでなく複数機体の育成・役割分担を評価する。

本編進行には必須ではない。

## 解放条件

- 管理者: `release_flags.tower` に関係なく利用可
- 一般ユーザー: `release_flags.tower = public` かつ `users.max_unlocked_layer >= 4`
- 第4層クリア後限定ではない
- 第1〜第3層ユーザーにはホーム導線を出さない
- 初期状態は公開準備中

## ルール v1

- 3機の `robot_instances` を選んで挑戦開始
- 同じ `robot_instance_id` は重複選択不可
- 1階につき1機が戦う
- 戦闘は既存の1対1シミュレーションを再利用
- 使用したロボは休憩中になる
- 3機すべてが1回ずつ戦うと再び出撃できる状態に戻る
- 敗北した時点で run は `failed`
- 10F踏破で run は `completed`
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
- `tower_reward_grants`

`tower_runs` には記録作成時点の `weekly_key`, `environment_key`, `squad_plus_total` を保存する。

## 週替わり観測環境

v1では表示と敵抽選の軽い偏りに使う。
強いステータス補正や本編報酬補正は入れない。

現在週の環境は `tower_weekly_environment` に保存する。
未作成の場合は JST の ISO 週キーから deterministic に生成する。

- 安定の週
- 機動の週
- 暴走の週
- 重装の週
- 霧界の週

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
- `TOWER_WEEKLY_LEADER`
- `TOWER_ALL_TIME_LEADER`

通常挑戦は流さない。
自己最高更新、10階単位、週最高更新、歴代最高更新のみ流す。

## 報酬方針

戦力インフレ報酬を出さない。
主報酬は記録、ランキング、世界ログ。

現在の土台:

- 10階初到達で `tower_floor_10` を `tower_reward_grants` に冪等保存
- `audit.tower.reward.grant`
- `audit.tower.reward.skip_duplicate`

将来候補:

- 称号
- 追加バッジ
- DECOR
- 少量コイン

## 記録庫 / ホーム / 公開管理

- `/admin/release` で `tower` を一般公開/管理者限定に切り替える
- `/records` に観測塔の記録セクションを表示する
- ホーム導線は管理者、または公開済みかつ第4層到達者にだけ表示する

## 特殊ランキング土台

`/tower/ranking` に以下を表示する。

- 今週最高到達階
- 歴代最高到達階
- 低+値チャレンジ 最高到達階

低+値小隊は `squad_plus_total <= 15`。

## テスト観点

- 第4層未到達ユーザーは利用不可
- 第4層到達ユーザーのみホーム導線表示
- 3機未満、重複選択を拒否
- run 作成と cooling 作成
- 休憩中ロボの再出撃拒否
- 3機使用後に再び出撃できる状態へ戻る
- 10F踏破で `completed`
- 敗北で `failed`
- 記録更新と世界ログ保存
- `/explore` 既存導線が壊れていない
