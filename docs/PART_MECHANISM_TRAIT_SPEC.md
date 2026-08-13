# パーツ機構特性 v1

最終更新日: 2026-08-13

## 目的
- パーツ選択に「敵特性への軽い対策」という判断軸を追加する。
- 既存の `w_*` 個体差、強化値、進化引き継ぎ、シリーズ効果は変更しない。
- 戦力インフレではなく、構成を考える理由を増やす。

## データ
- 正本は `robot_parts.mechanism_trait_key`。
- `part_instances` にはコピーしない。
- 同じパーツマスタから作られた個体は同じ機構特性を持つ。
- DECORは対象外。
- Nは非発動。UIでは `機構特性：進化で解放` と表示する。
- R/SR/SSR/URで発動する。効果量はレアリティで変化しない。

## 特性一覧
| 部位 | key | 表示名 | 効果 |
|---|---|---|---|
| HEAD | precision_processor | 精密演算 | 高速機への照準補正 |
| HEAD | defense_processor | 防衛演算 | 戦闘序盤の被害を軽減 |
| RIGHT_ARM | armor_piercer | 装甲穿孔 | 重装機への攻撃性能上昇 |
| RIGHT_ARM | opening_overdrive | 初動過給 | 戦闘序盤の攻撃性能上昇 |
| LEFT_ARM | tracking_array | 追尾補正 | 高速対象への追尾性能上昇 |
| LEFT_ARM | reactive_guard | 反応防壁 | 暴走機からの被害を軽減 |
| LEGS | quickstart_servo | 瞬発駆動 | 戦闘序盤の機動性能上昇 |
| LEGS | stability_drive | 姿勢制御 | 不安定機との戦闘を安定化 |

## 戦闘効果
- 対象敵特性: `heavy`, `fast`, `berserk`, `unstable`。
- 通常戦闘では先制判定、攻撃前、与ダメ、被ダメの各段で薄く補正する。
- 異常個体は専用戦闘関数のため、同じ特性定義から挑戦開始時に軽いstats補正と観測メモを作る。
- 効果目安:
  - 命中補正: +4〜12%上限
  - 攻撃補正: +7〜12%上限
  - 速度補正: +8〜10%上限
  - 与ダメ補正: +7〜15%上限
  - 被ダメ軽減: 4〜15%上限

## UI
- `/parts`: 所持パーツカードに機構特性を表示。
- `/parts/strengthen`: 強化・進化候補と結果に機構特性を表示。
- `/build`: パーツ選択カードと現在装備に機構特性を表示。
- ロボ詳細の戦術セット: 保存セットごとの有効機構を表示。
- 通常戦闘結果: 発動した機構特性を結果とターンログに表示。
- 異常個体結果: 観測された機構特性を短く表示。

## 監査・計測
- `audit.explore.end` の payload `player` に以下を追加する。
  - `active_trait_keys`
  - `triggered_trait_keys`
  - `active_mechanism_traits`
- `audit.anomaly.attempt` payload に `part_mechanism` を追加する。
  - `active_trait_keys`
  - `triggered_trait_keys`
  - `triggered_labels`
  - `enemy_trait_key`
  - `observation_lines`
- `/admin/metrics` で R+特性装備ユーザー、発動戦闘数、特性別勝率、第6層勝率、異常個体CLEAR率を見る。

## 非目標
- シリーズボーナス追加ではない。
- パーツ個体差 `w_*` や plus 成長式は変更しない。
- 強力な専用パーツ、専用通貨、レアリティ別効果量は追加しない。
