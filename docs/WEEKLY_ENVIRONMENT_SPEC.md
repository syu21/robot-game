# 週間環境仕様

最終更新日: 2026-03-08

## 1. 概要
- 週単位 (`week_key`) で環境を決め、出撃体験へ軽補正を与える
- 同じ `week_key` を陣営戦集計にも利用する

## 2. データモデル
### 2.1 world_weekly_environment
- `week_key`
- `element`
- `mode`
- `enemy_spawn_bonus`
- `drop_bonus`
- `started_at`, `ends_at`
- `random_seed`
- `influence_ratio`
- `reason`

### 2.2 world_weekly_counters
- `week_key`
- `metric_key`
- `value`

## 3. モード定義（代表）
- `暴走`: 出現率寄り
- `活性`: ドロップ寄り
- `安定`: 変動小
- `静穏`: 低刺激

## 4. 出撃への反映
- 敵出現重み補正
- ドロップ補正
- 一部モードで連戦率やコイン挙動に影響

## 5. ホーム表示方針
- 見出し: `今週の戦況`
- 前面表示:
  - 状態名
  - 短い効果説明
- 非表示（内部保持のみ）:
  - 詳細係数
  - 生カウンタ値

## 6. 陣営戦連携
- 同一 `week_key` で陣営ポイントを集計
- 週締め結果を `world_faction_weekly_result` に保存
- 勝利陣営は次週軽バフ対象

## 7. 運用
- 管理導線: `/admin/world`
- 再抽選・カウンタリセットは監査を残す

