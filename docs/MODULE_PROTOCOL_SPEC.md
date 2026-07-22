# 研究モジュール特殊プロトコル v1

## 目的

研究モジュールOS構成に、次回出撃だけ有効な `秘匿戦闘命令 / ACTIVE PROTOCOL` を1つ追加する。

## 保存

- 選択状態: `users.selected_module_protocol_key`, `users.selected_module_protocol_at`
- OS構成: 既存の `user_module_loadouts`
- 戦闘時点の状態: `EXPLORE_END` payload と `audit.module.protocol.*` payload

出撃後は既存の次回出撃モジュール仕様に合わせて、OS構成とプロトコル選択を解除する。

## 解放条件

- 同ブランド2個: 基本プロトコル解放
- 同ブランド3個: 基本 + 上位プロトコル解放
- 3ブランド混成: `adaptive_shift` 解放
- NOVA 2個以上: `adaptive_shift` 解放
- NOVA 3個: `emergency_reconfiguration` 解放

使用不可の `protocol_key` がPOSTされてもサーバー側で拒否する。
OS構成変更で条件不足になった場合は自動解除する。

## 定義

定義は `constants.py` の `MODULE_PROTOCOL_DEFINITIONS`。
戦闘中の状態処理は `services/module_protocols.py`。

## プロトコル

- `fortress_guard`: `絶対防衛機構《アイギス・ウォール》`。1〜3ターン目の被ダメージを15%軽減。
- `emergency_repair`: `自己再生機構《リザレクション・ギア》`。HP30%以下で最大HPの12%を1回回復。HP0では発動しない。
- `opening_acceleration`: `零秒加速《クロノ・アクセル》`。1〜2ターン目の行動順用素早さを20%上昇。
- `critical_chain`: `雷光連鎖《ヴォルト・レゾナンス》`。会心後、次の自分の攻撃だけ会心率+15。最大2回。
- `target_analysis`: `未来観測《オラクル・トレース》`。戦闘中、命中判定に+10。
- `miss_correction`: `因果修正《ラプラス・リライト》`。MISS後、次の自分の攻撃だけ必中。最大2回。
- `limit_break`: `崩壊臨界《デッドライン・イグニッション》`。HP35%以下の間、攻撃+20%、防御-10%。ON/OFF時だけログ。
- `unstable_overdrive`: `禁断過駆動《ラグナロク・バースト》`。攻撃時20%で与ダメージ1.5倍、攻撃後に最大HP5%反動。成功最大2回。
- `adaptive_shift`: `万象適応《アカシック・シフト》`。敵傾向で防御/攻撃/命中/素早さ/耐久のいずれかを戦闘中維持。
- `emergency_reconfiguration`: `戦局再編《ノヴァ・リコンストラクト》`。4ターン目にHP、直近MISS、敵HP、その他の優先順で1効果。

## 適用順

基礎ステータス、パーツ補正、成長傾向、モジュール個体補正、ブランドシンクロ補正の後に、戦闘中だけプロトコル補正を適用する。

ダメージは既存命中/会心/trait処理後に、プロトコル与ダメージ倍率、防御側軽減、HP減算、反動/回復の順で扱う。

## 戦闘状態

`protocol_state` は1出撃中だけ保持する。

- 発動回数
- 発動ターン
- 次回攻撃限定効果
- ターン限定効果
- HP閾値ON/OFF
- 直近攻撃結果
- NOVA適応先
- 効果集計

次回出撃へ状態は持ち越さない。

## UI

`/modules` に `秘匿戦闘命令 / ACTIVE PROTOCOL` 領域を追加。

- 使用可能プロトコル
- ロック中プロトコル
- 発動条件
- 効果
- 発動上限
- 選択中表示

ホームは短く `秘匿命令: 名称` を表示する。
戦闘結果は「今回起動した秘匿命令」とdetailsを表示する。未発動時は「秘匿命令は待機状態のまま戦闘を終了しました」と表示する。

## 監査

追加イベント:

- `audit.module.protocol.set`
- `audit.module.protocol.clear`
- `audit.module.protocol.auto_clear`
- `audit.module.protocol.start`
- `audit.module.protocol.trigger`
- `audit.module.protocol.finish`

`trigger` は実際の発動イベントだけ記録する。
`finish` は1出撃1回。

## 集計土台

監査payloadに `protocol_key`, `protocol_name`, `brand_counts`, `os_name`, `activation_turn`, `effect_type`, `damage_reduced`, `healing_amount`, `bonus_damage`, `recoil_damage`, `guaranteed_hit`, `critical_bonus`, `result_win`, `turn_count` を保存する。

## 互換

以下は変更しない。

- モジュール個体値
- パーツ個体値
- 敵抽選
- ボス能力
- ドロップ率
- CT
- 8ターン上限
- tier1連続MISS救済
- 既存trait
- Phase 1のOS構成/シンクロ/消費

## 非対象

自由な条件+効果接続、複数プロトコル同時搭載、熟練度、覚醒、敵ごとの学習、課金プロトコル、PvP対応は未実装。
