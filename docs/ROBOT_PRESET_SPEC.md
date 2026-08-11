# 機体プリセット《戦術セット》v1

最終更新日: 2026-08-12

## 目的
- 通常探索、ボス、高層、異常個体ごとに機体構成を切り替えやすくする。
- 強い装備を配る機能ではなく、所持済み構成を保存・適用する操作補助に留める。

## 保存対象
- 4部位パーツ: `head`, `r_arm`, `l_arm`, `legs`
- 研究モジュール: 最大3個

## 保存対象外
- DECOR
- 見た目調整
- ロボ名
- 称号
- 戦闘中の自動切替

## UI
- ロボ詳細に固定3枠 `SET A/B/C` を表示する。
- 各枠で保存、上書き、適用、名称変更、削除を行う。
- 未保存、現在適用中、使用不可を明確に表示する。
- 異常個体結果画面から戦術セットへ戻れる。

## データ
テーブル: `robot_loadout_presets`

- `user_id`
- `robot_instance_id`
- `preset_slot`
- `display_name`
- `config_json`
- `schema_version`
- `created_at`
- `updated_at`

UNIQUE:
- `robot_instance_id, preset_slot`

## 安全性
- 保存時、POSTされた構成データは使わない。
- サーバー上の現在装備と現在モジュールだけを保存する。
- 適用時は所有者、部位、フレーム、パーツ状態、他機体装備中、モジュール状態を検証する。
- 失敗時は部分適用しない。

## 監査
- `audit.robot.preset.save`
- `audit.robot.preset.apply`
- `audit.robot.preset.rename`
- `audit.robot.preset.delete`

## 管理確認
- `/admin/metrics` で保存済みセット数、保存/適用ユーザー、SET別保存数、直近操作を確認する。

## テスト観点
- 3固定枠が作成される。
- 保存、名称変更、削除ができる。
- 適用でパーツとモジュールが切り替わる。
- 不正構成は拒否され、部分適用されない。
- クライアント送信の構成JSONは保存に使われない。
