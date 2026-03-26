# 編成・強化・進化仕様

最終更新日: 2026-03-26

## 1. 範囲
- ロボ編成: `/build`, `/build/confirm`
- パーツ強化: `/parts/strengthen`（`/parts/fuse`互換）
- 進化合成: `/parts/evolve`

## 2. ロボ編成
### 2.1 必須・任意
- 必須: `HEAD`, `RIGHT_ARM`, `LEFT_ARM`, `LEGS`
- 任意: `DECORATION`

### 2.2 合成画像
- 画像サイズ: 128x128 PNG
- レイヤー順: `LEGS -> HEAD -> RIGHT_ARM -> LEFT_ARM -> DECORATION`
- オフセット: `robot_parts.offset_x/y` を使用

### 2.3 保存
- `robot_instances` + `robot_instance_parts` に保存
- 保存枠超過時は保存ブロック

### 2.4 小型バッジ画像
- `robot_instances.icon_32_path` に 32x32 の小型ロボ画像を保持する
- 未生成時は `composed_image_path` からオンデマンドで生成する
- 用途:
  - `/ranking` の user系ランキング
  - `/home` の `今週のランキング`
  - `/world` の MVP 表示
  - `/records` のユーザー表示

## 3. DECOR表示方針
- DECORはバッジ的に小型表示（本体中心を隠さない）
- 所有DECORのみ選択可
- `なし` は常時選択可

## 4. パーツ強化
### 4.1 導線
- 正規: `/parts/strengthen`
- 互換: `/parts/fuse`（同処理）

### 4.2 仕様
- ベース1 + 素材2
- 成功率100%
- 上昇量は常に +1固定
- 対象条件は「同名 + 同レアリティ」（+値違い可）
- 強化候補は「成立可能なグループ」のみ表示
- 素材自動選択時は安全制約あり（装備中素材消費禁止など）

### 4.3 監査
- `audit.fuse`
- payloadに成功可否、消費ID、増分などを保持

## 5. 進化合成
### 5.1 仕様
- Nパーツ + 進化コア1個 -> 対応するRパーツ
- 進化先Rマスタ未登録ならエラー復帰

### 5.2 引き継ぎ
- `plus` 維持
- `w_hp..w_cri` 維持

### 5.3 監査
- `audit.part.evolve`

## 6. 表示名
- 優先順位:
  1. `display_name_ja`
  2. 自動生成名
  3. 旧name列
  4. part_key
