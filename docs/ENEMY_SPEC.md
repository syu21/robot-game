# 敵仕様（enemy master / 出撃抽選）

最終更新日: 2026-03-08

## 1. 敵マスタ
テーブル: `enemies`

主要列:
- 識別: `id`, `key`, `name_ja`
- 表示: `image_path`
- 基礎: `tier`, `element`, `faction`
- 戦闘: `hp`, `atk`, `def`, `spd`, `acc`, `cri`
- フラグ: `is_boss`, `boss_area_key`, `is_active`, `trait`

## 2. 現行規模
- 通常敵: 30体
- 固定ボス: 3体（layer_1 / layer_2 / layer_3）
- 画像欠損時はプレースホルダ表示

## 3. tier出現方針（現行）
- `layer_1`: tier1中心
- `layer_2`: tier1/tier2混在
- `layer_2_mist`: tier2中心
- `layer_2_rush`: tier2に加えtier3混在
- `layer_3`: tier2/tier3中心

## 4. trait仕様
- `heavy`: 被ダメ軽減
- `fast`: 回避寄り
- `berserk`: 耐久半分以下で攻撃上昇
- `unstable`: 反動挙動

## 5. ボス仕様
- 抽選入口は出撃側（0.5%）
- 固定ボスは `boss_area_key` 一致で抽選
- 報酬は DECOR 系中心
- 監査:
  - `audit.boss.encounter`
  - `audit.boss.defeat`

## 6. NPCボス（v1）
- 既存固定ボスを壊さず追加
- layer_2/3で候補抽選
- 専用画像:
  - `static/enemies/boss/npc_boss_ignis.png`
  - `static/enemies/boss/npc_boss_ventra.png`
  - `static/enemies/boss/npc_boss_aurix.png`
- 監査payloadで `boss_kind` 識別

## 7. 管理運用
- `/admin/enemies`: 一覧/編集/有効化
- `/admin/npc-bosses`: テンプレ有効化管理

