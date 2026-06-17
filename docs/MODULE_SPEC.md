# 研究モジュール仕様

最終更新日: 2026-06-15

## 目的
- パーツは確実な積み上げ育成、研究モジュールはランダム要素付きの作戦チップ育成として分ける。
- ロボ/パーツ本体ステータスは変更しない。
- モジュール補正は従来通り、次の出撃の戦闘中だけ適用する。

## 基本仕様
- 選択中モジュールは `users.active_research_module_instance_id` で管理する。
- 固定モジュールは `research_modules` の補正を使う。
- 研究合成産は `user_research_modules` の個体補正を使う。
- `user_research_modules` 側の補正が `NULL` の場合は `research_modules` にフォールバックする。
- 戦闘適用時は補正後ステータスを最低1に clamp する。

## DB
- `research_modules`
  - 固定マスタ。
  - `synthesized_module` は研究合成産の共通マスタ。
- `user_research_modules`
  - 所持個体。
  - 研究合成産だけ個体補正を持つ。
  - 追加列:
    - `hp_bonus / atk_bonus / def_bonus / spd_bonus / acc_bonus / cri_bonus`
    - `synthesis_grade`
    - `synthesis_family`
    - `synthesis_result_type`
    - `origin_module_a_id`
    - `origin_module_b_id`
    - `generation`
    - `synthesis_score`

## 入手
- 通常戦勝利時に低確率ドロップ。
- 研究ゲージ100到達でprototypeを保証付与。
- 同種prototype 3個でcompleteへ合成。
- `/modules/synthesis` で2個合成により `synthesized_module` 個体を生成。

## 研究合成
- ルート:
  - `GET /modules/synthesis`
  - `POST /modules/synthesis/confirm`
  - `POST /modules/synthesis`
  - `POST /modules/synthesis/equip`
- 素材:
  - 本人所有
  - `status='inventory'`
  - `is_locked=0`
  - 現在選択中ではない
  - 2個は別個体
- 費用:
  - v1は一律500コイン
- 成功時:
  - 素材2個を `consumed` にする。
  - `synthesized_module` を1個 `inventory` で生成する。
  - `audit.coin.delta` を残す。
- 失敗時:
  - コイン不足、素材不正では生成しない。
  - 素材も消費しない。

## 生成ロジック
- 親2個の実効補正の平均を base にする。
- result_type:
  - `normal`: 70%
  - `great`: 25%
  - `anomaly`: 5%
- 上限:
  - normal: 単ステ +14
  - great: 単ステ +18
  - anomaly: 単ステ +24
- anomaly は2ステ以上にマイナス補正を持つ。
- `synthesis_score` はプラス補正合計 - マイナス補正絶対値の半分。

## 表示
- `/modules`
  - 「研究合成」導線を主導線として表示。
  - 既存の同種3個合成、保護、売却、図鑑は維持。
  - `prototype` / `tier1` / `trade_policy` などの内部値は表示しない。
  - 図鑑状態は `未発見` / `発見済み` で表示する。
  - 効果は日本語能力名のチップで表示する。
- `/modules/synthesis`
  - 素材A/B選択。
  - ロック中/選択中は選択不可理由を表示。
  - 素材候補0件/1件時は必要条件と入手導線を表示する。
- 結果画面:
  - 成功 / 大成功 / 異常反応
  - 生成モジュール名
  - 6ステ補正
  - 系統
  - 評価
  - 由来
  - このモジュールを次の出撃で使う
  - このモジュールを保護する
  - おすすめ出撃先
  - 基地へ戻って出撃する
  - モジュール一覧へ

## 実戦導線
- 合成結果画面の「このモジュールを次の出撃で使う」は `users.active_research_module_instance_id` を更新し、`/home?module_equipped=1` に戻す。
- 使用設定は本人所有、`status='inventory'`、未売却のモジュールだけ許可する。
- ロック中モジュールは素材・売却には使えないが、出撃用としては設定できる。
- 出撃結果画面は active module がある場合だけ「今回の作戦」カードを表示する。
- 「今回の作戦」はモジュール名、種別/評価、効果チップ、勝敗コメント、取れる範囲の戦闘メトリクスを表示する。
- 0補正は効果チップから省略する。研究合成産で実効補正が取れない場合は「効果: 合成結果によって変化」と表示する。
- 戦闘ログ形式は変更しない。メトリクスは既存 `turn_logs` から集計する。

## 監査ログ
- `audit.module.synthesis.preview`
- `audit.module.synthesis.create`
- `audit.module.synthesis.consume`
- `audit.module.synthesis.result`
- `audit.module.strategy.apply`
- `audit.module.strategy.result`
- `audit.coin.delta`

payload:
- `user_id`
- `origin_module_a_id`
- `origin_module_b_id`
- `result_module_id`
- `result_type`
- `synthesis_family`
- `hp_bonus / atk_bonus / def_bonus / spd_bonus / acc_bonus / cri_bonus`
- `synthesis_score`
- `cost_coins`
- `coins_before`
- `coins_after`

`audit.module.strategy.apply` payload:
- `user_id`
- `robot_instance_id`
- `module_instance_id`
- `module_key`
- `module_name`
- `area_key`
- `hp_bonus / atk_bonus / def_bonus / spd_bonus / acc_bonus / cri_bonus`

`audit.module.strategy.result` payload:
- `user_id`
- `robot_instance_id`
- `module_instance_id`
- `module_name`
- `area_key`
- `area_label`
- `enemy_key`
- `enemy_name`
- `result_win`
- `turn_count`
- `player_miss_count`
- `player_crit_count`
- `player_max_damage`
- `player_total_damage`
- `player_damage_taken`
- `player_hp_remaining`
- `hp_bonus / atk_bonus / def_bonus / spd_bonus / acc_bonus / cri_bonus`

## 個人ログ
- `audit.module.synthesis.result` は `/comms/personal` に「研究合成」ログとして表示する。
- `audit.module.strategy.result` は `/comms/personal` に「今回の作戦」ログとして表示する。
- 世界ログには公開しない。

## 非対象 v1
- 世界ログ公開。
- ユーザー間取引。
- パーツ/ロボ本体ステータス変更。
