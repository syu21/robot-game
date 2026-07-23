# 研究モジュールOS構成 Phase 1

## 目的

研究モジュールは次回出撃だけに有効な個体アイテム。既存の6ステ補正、レアリティ、保護、買取、同種3個合成、図鑑、再調整を維持しつつ、最大3個のOS構成として扱う。

## データ構造

- マスタ: `research_modules`
  - `module_key`, `name_ja`, `rarity`, `family`, `*_bonus`, `tier`, `trade_policy`, `source_type`, `npc_sell_price`
  - Phase 1追加: `brand_key`, `role_key`
- 個体: `user_research_modules`
  - `id` が個体ID、`module_key` がマスタID相当
  - 個体補正列 `*_bonus` がNULLの場合はマスタ補正を使う
  - Phase 1追加: `brand_key`, `role_key`
- 次回出撃構成: `user_module_loadouts`
  - `user_id`, `slot_index`, `module_instance_id`
  - `UNIQUE(user_id, slot_index)`
  - `UNIQUE(user_id, module_instance_id)`

旧 `users.active_research_module_instance_id` はSLOT 1の互換ミラーとして残す。

## ブランド

- `titan`: TITAN HEAVY / 絶対装甲機関《タイタン》 / 重装 / 防衛 / 不沈 / hp, def
- `volt`: VOLT EDGE / 神速演算機関《ヴォルト》 / 高速 / 先制 / 連撃 / spd, cri
- `eden`: EDEN LOGIC / 全知解析機関《エデン》 / 解析 / 精密 / 必中 / acc, def
- `scrap_x`: SCRAP-X / 禁断暴走機関《スクラップ・エクス》 / 暴走 / 背水 / 極限火力 / atk, cri
- `nova`: NOVA LINK / 万象接続機関《ノヴァ》 / 適応 / 混成 / 万能 / 全能力

定義は `constants.py` の `MODULE_BRAND_DEFINITIONS` に集約。

## 役割タグ

- `power`: 殲滅演算 / 攻撃特化
- `guard`: 絶対防衛 / 耐久・防御特化
- `speed`: 神速駆動 / 速度特化
- `precision`: 未来照準 / 命中特化
- `support`: 戦況支配 / 補助・適応型
- `unstable`: 禁忌出力 / 暴走・極端型

Phase 1では追加効果なし。UI表示、分析、将来条件用。

## 補完ルール

既存個体のID、所有者、レアリティ、補正、保護、状態、作成日時は変更しない。未設定の `brand_key` / `role_key` だけ補完する。

- マスタはfamilyから自然割り当て
- 個体は有効補正値から決定的に推定
- 再調整は6ステ補正のみ変更し、ブランド/役割は維持

## 構成制約

- 0〜3個
- 同一個体の重複不可
- 他ユーザー個体不可
- 売却済み・消費済み不可
- 保護中は設定可
- 同名モジュールの複数装着可

## シンクロ

構成から毎回決定的に計算し、DBへ重複加算しない。

- 同ブランド2個: ブランドごとの2個効果
- 同ブランド3個: 2個効果 + 3個追加効果
- 3ブランド混成: 全能力+2 / `複合演算領域《トリニティ・コード》`
- 2個だけ別ブランド: なし
- 1個以下: なし

同ブランド効果と混成制御は重複しない。

表示名:

- `titan` 2: `第一装甲解放《アイアン・ウォール》`
- `titan` 3: `最終装甲解放《アブソリュート・フォートレス》`
- `volt` 2: `第一加速領域《ライトニング・ドライブ》`
- `volt` 3: `最終加速領域《ゼロ・フレーム》`
- `eden` 2: `第一解析領域《オラクル・サイト》`
- `eden` 3: `最終解析領域《ラプラス・コード》`
- `scrap_x` 2: `第一禁忌解放《ブラッド・イグニッション》`
- `scrap_x` 3: `最終禁忌解放《ラグナロク・オーバー》`
- `nova` 2: `第一適応領域《オール・リンク》`
- `nova` 3: `最終適応領域《アカシック・ノヴァ》`

## OS名

構成から再計算する。

- titan 3: `TITAN FORTRESS OS`
- volt 3: `VOLT FLASH OS`
- eden 3: `EDEN ANALYZER OS`
- scrap_x 3: `SCRAP BERSERK OS`
- nova 3: `NOVA ADAPTIVE OS`
- 3ブランド混成: `HYBRID CONTROL OS`
- 同ブランド2個: `<BRAND> SYNC OS`
- その他: `CUSTOM OS`
- 未装着: `NO MODULE OS`

日本語型名は `MODULE_OS_DEFINITIONS` と `MODULE_SYNC_OS_JA_LABELS`。

- `TITAN FORTRESS OS`: `不落絶城型《アブソリュート・タイタン》`
- `VOLT FLASH OS`: `神速殲滅型《クロノ・ブレイカー》`
- `EDEN ANALYZER OS`: `全知必中型《ラプラス・アイ》`
- `SCRAP BERSERK OS`: `終焉暴走型《ラグナロク・ギア》`
- `NOVA ADAPTIVE OS`: `万象適応型《アカシック・ノヴァ》`
- `HYBRID CONTROL OS`: `三位複合型《トリニティ・アンノウン》`
- `<BRAND> SYNC OS`: ブランド別の同期型名
- `CUSTOM OS`: `未定義構築型《アンノウン・コード》`
- `NO MODULE OS`: `無装演算型《ブランク・コア》`

## 戦闘適用順

```text
個体補正合計
+ シンクロ補正
= 最終モジュール補正
```

戦闘ではロボ基礎値へ最終モジュール補正を1回だけ加算する。負補正は中間値として保持し、戦闘用ステータスへ反映する最終段階で最低1に丸める。

## 互換機能

- 保護: 維持。保護中でも装着可、素材不可。
- 買取: ロードアウト中は不可。
- 同種3個合成: ロードアウト中・保護中は素材不可。
- 図鑑: `module_key` ベースを維持。
- 再調整: ブランド/役割は更新しない。
- 研究合成: 生成個体の補正からブランド/役割を保存。

## 監査

追加イベント:

- `audit.module.loadout.set`
- `audit.module.loadout.clear`
- `audit.module.synergy.apply`
- `audit.module.consume`
- `audit.module.protocol.*`

payloadにはOS名、ブランド構成、シンクロ、個体補正、同期補正、最終補正を残す。通常の構成変更は世界ログ表示用途にしない。

## Phase 2

特殊プロトコルv1は `docs/MODULE_PROTOCOL_SPEC.md` を正とする。

BATTLE CODE v1は `docs/MODULE_BATTLE_CODE_SPEC.md` を正とする。

## 非対象

耐久度、修理、容量、オーバークロック、毎ターン回復、反撃、追加攻撃、ドロップ率変更、課金商品、世界限定個体は未実装。
