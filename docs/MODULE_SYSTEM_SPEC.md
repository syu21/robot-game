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

- `titan`: TITAN HEAVY / 重装・防衛 / hp, def
- `volt`: VOLT EDGE / 高速・先制 / spd, cri
- `eden`: EDEN LOGIC / 解析・精密 / acc, def
- `scrap_x`: SCRAP-X / 暴走・背水 / atk, cri
- `nova`: NOVA LINK / 混成・適応 / 全能力

定義は `constants.py` の `MODULE_BRAND_DEFINITIONS` に集約。

## 役割タグ

- `power`: 攻撃
- `guard`: 防衛
- `speed`: 高速
- `precision`: 精密
- `support`: 補助
- `unstable`: 暴走

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
- 3ブランド混成: 全能力+2 / `混成制御`
- 2個だけ別ブランド: なし
- 1個以下: なし

同ブランド効果と混成制御は重複しない。

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

日本語補助名は `MODULE_OS_JA_LABELS`。

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

## 非対象

耐久度、修理、容量、オーバークロック、毎ターン回復、反撃、追加攻撃、ドロップ率変更、課金商品、世界限定個体は未実装。
