# 研究モジュール拡張 Phase 3: BATTLE CODE v1

## 目的

BATTLE CODEは、次回出撃用に `IF 条件コード -> THEN 効果コード` を1構成だけ保存する簡易戦闘命令。

特殊プロトコルとは同時設定可能。BATTLE CODE未設定時は `標準戦闘演算` と表示し、戦闘結果は従来どおり。

## 保存

- `users.selected_battle_code_condition_key`
- `users.selected_battle_code_effect_key`
- `users.selected_battle_code_updated_at`

条件と効果は必ずセット。不正キー、片方のみ、非アクティブ定義は拒否。

出撃開始時に `services.battle_codes.snapshot()` を作成し、戦闘中と結果表示はスナップショットを使用する。出撃後は次回設定をclearする。

## 定義

定義は `constants.py` に集約。

- `BATTLE_CODE_CONDITIONS`
- `BATTLE_CODE_EFFECTS`

条件:

- `battle_start`: 開戦宣言《ファースト・オーダー》
- `low_hp_30`: 崩壊領域《デッドライン》
- `turn_4_start`: 長期戦移行《フォース・フェイズ》
- `after_miss`: 誤差検出《エラー・シグナル》
- `after_critical`: 致命共鳴《クリティカル・シグナル》
- `enemy_low_hp_40`: 終局判定《フィニッシュ・ライン》

効果:

- `attack_up_15`: 殲滅出力《ブレイク・ドライブ》
- `defense_up_15`: 装甲再編《フォートレス・シフト》
- `guaranteed_hit`: 因果固定《フェイト・ロック》
- `heal_8`: 緊急再生《リカバリー・コア》
- `speed_up_15`: 神速駆動《クロノ・ドライブ》
- `critical_up_12`: 臨界照準《デス・ポイント》

名称は `条件prefix + 《英語prefix-効果code》` で自動生成する。

## 戦闘処理

状態処理は `services/battle_codes.py`。

- 条件成立回数と命令発動回数を分離
- 回復は最大HP8%、1戦1回、HP0では不発
- 次撃必中は最大2回、`battle_start` / `turn_4_start` では1回
- ステータス上昇は15%、会心は+12
- `battle_start` / `turn_4_start` のステータス効果は2ターン
- `low_hp_30` のステータス効果はHP30%以下の間だけ
- `enemy_low_hp_40` のステータス効果は初回到達から戦闘終了まで
- 次撃効果は自分の攻撃判定後に消費
- 次回被弾防御は実ダメージを受けた時だけ消費

特殊プロトコルとBATTLE CODEの倍率は、既存実装に合わせて「その時点の有効値へ乗算丸め」で適用する。

必中は特殊プロトコル、BATTLE CODE、tier1救済のいずれかが成立すれば1回の命中判定で必中。BATTLE CODE側の待機フラグは消費履歴を残す。

## UI

`/modules` に `戦闘命令構築 / BATTLE CODE` を表示。

- 条件カード6枚
- 効果カード6枚
- 自動生成名
- 実条件
- 実効果
- 発動回数・効果時間
- 保存CTA
- 初期化CTA

ホーム出撃前表示にはBATTLE CODE名だけを表示。

## 監査

- `audit.module.battle_code.set`
- `audit.module.battle_code.clear`
- `audit.module.battle_code.start`
- `audit.module.battle_code.condition`
- `audit.module.battle_code.trigger`
- `audit.module.battle_code.consume`
- `audit.module.battle_code.finish`

`finish` payloadに `battle_code_summary_json`、条件成立回数、発動回数、勝敗、ターン数を含める。
