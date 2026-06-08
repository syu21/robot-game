# 敵仕様（enemy master / 出撃抽選）

最終更新日: 2026-03-28

## 1. 敵マスタ
テーブル: `enemies`

主要列:
- 識別: `id`, `key`, `name_ja`
- 表示: `image_path`
- 基礎: `tier`, `element`, `faction`
- 戦闘: `hp`, `atk`, `def`, `spd`, `acc`, `cri`
- フラグ: `is_boss`, `boss_area_key`, `is_active`, `trait`

## 2. 現行規模
- 通常敵: 47体
- 固定ボス: 10体
  - layer_1 / layer_2 / layer_3
  - layer_4_forge / layer_4_haze / layer_4_burst
  - layer_4_final
  - layer_5_labyrinth / layer_5_pinnacle
  - layer_5_final
- 画像欠損時はプレースホルダ表示

## 3. tier出現方針（現行）
- `layer_1`: tier1中心
- `layer_2`: tier1/tier2混在
- `layer_2_mist`: tier2中心
- `layer_2_rush`: tier2に加えtier3混在
- `layer_3`: tier2/tier3中心
- `layer_4_forge`: tier4重装敵のみ。通常敵から `layer_3` 固定ボス級を超える本番帯
- `layer_4_haze`: tier4高速敵のみ。命中不足を咎める本番帯
- `layer_4_burst`: tier4暴走/不安定敵のみ。背水/爆発でも事故る高圧帯
- `layer_5_labyrinth`: tier5観測/重装/高速の混成。安定周回の最前線
- `layer_5_pinnacle`: tier5暴走/不安定の競技寄り。最速/爆発記録の最前線

## 4. trait仕様
- `heavy`: 被ダメ軽減
- `fast`: 回避寄り
- `berserk`: 耐久半分以下で攻撃上昇
- `unstable`: 反動挙動

## 5. ボス仕様
- 抽選入口は出撃側（0.5%）
- 固定ボスは `boss_area_key` 一致で抽選
- 第1層〜第3層のボス戦は8ターン上限を使う
- 第4層以降のボス戦はターン上限なしで、HP決着まで継続する
- 無限ループ防止として内部安全上限を持ち、未決着なら試験継続不能扱いで終了する
- 報酬は DECOR 系中心
- 監査:
  - `audit.boss.encounter`
  - `audit.boss.defeat`
- 第4層ボス:
  - `boss_4_forge_elguard`: 耐久 / 安定向け
  - `boss_4_haze_mirage`: 命中 / 安定向け
  - `boss_4_burst_volterio`: 背水 / 爆発向け
  - `boss_4_final_ark_zero`: 型理解を問う最終試験
- 第4層3サブエリアの固定ボスは `試験警報値` の対象。通常戦勝利でエリア別に進み、30/40/50で出現率上昇、75以上で次回遭遇保証。遭遇時点で該当エリアのみ0に戻る
- 第5層ボス:
  - `boss_5_labyrinth_nyx_array`: 命中 / 安定 / バランス向け
  - `boss_5_pinnacle_ignition_king`: 背水 / 爆発 / 速攻向け
  - `boss_5_final_omega_frame`: 思想完成を問う総決算

## 6. NPCボス（v1）
- 既存固定ボスを壊さず追加
- layer_2/3で候補抽選
- 撃破報酬は `進化コア x1`
- 専用画像:
  - `static/enemies/boss/npc_boss_ignis.png`
  - `static/enemies/boss/npc_boss_ventra.png`
  - `static/enemies/boss/npc_boss_aurix.png`
- 監査payloadで `boss_kind` 識別

## 7. 管理運用
- `/admin/enemies`: 一覧/編集/有効化
- `/admin/npc-bosses`: テンプレ有効化管理
## 観測塔での敵利用

- 観測塔 -ASTRAL SPIRE- では既存 `enemies` マスタを再利用する。
- `/explore` の敵抽選、ボス抽選、報酬処理は変更しない。
- 階数と週替わり観測環境に応じて、観測塔専用に軽いステータススケールをかける。
- 10階ごとにボス枠を使う。
- 新規敵を大量追加せず、既存敵の意味を壊さない。
