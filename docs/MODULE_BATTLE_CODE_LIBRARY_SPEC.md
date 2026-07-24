# BATTLE CODE LIBRARY v1

最終更新日: 2026-07-24

## 目的
- BATTLE CODEを3枠まで保存し、次回出撃用コードを切り替えられるようにする。
- 既存の単発BATTLE CODE設定は互換維持し、ライブラリ初回表示時にCODE-01へ移行する。

## UX
- `/modules/battle-codes` にライブラリ画面を追加。
- 保存枠は `CODE-01` から `CODE-03`。
- 空きスロットには作成導線を表示。
- 保存済みコードは選択、編集、削除、共有文作成が可能。
- ホームの出撃機体欄から保存済みコードをクイック選択可能。
- 用途ラベル:
  - `unset`: 用途未設定
  - `general`: 通常探索
  - `boss`: ボス攻略
  - `speed`: 高速周回
  - `stable`: 安定重視
  - `comeback`: 逆転狙い
  - `experiment`: 実験中

## バックエンド
- `battle_code_library`: 保存コード本体。削除は `deleted_at` による論理削除。
- `battle_code_stats`: コード別累計統計。
- `battle_code_stat_events`: `battle_result_id` 単位の統計二重加算防止。
- `is_public` はDB/API基盤のみ。v1では公開一覧UIなし。
- 条件/効果を変更する編集は旧レコードを論理削除し、新レコードを作成する。用途ラベルだけの変更はUPDATE。

## 戦闘挙動
- ライブラリ選択済みコードは探索後も維持する。
- 旧単発BATTLE CODEは従来通り探索後に消費クリアする。
- 無効化された保存コードは選択不可。選択中に無効化された場合は自動解除し、fallback監査を残す。

## 監査
- `audit.module.battle_code.library.create`
- `audit.module.battle_code.library.overwrite`
- `audit.module.battle_code.library.delete`
- `audit.module.battle_code.library.select`
- `audit.module.battle_code.library.unselect`
- `audit.module.battle_code.library.label_update`
- `audit.module.battle_code.library.share`
- `audit.module.battle_code.library.migrate`
- `audit.module.battle_code.library.fallback`
- `audit.module.battle_code.library.stats_update`

## 受け入れ条件
- 他ユーザーの保存コードを選択、削除、共有できない。
- 3枠を超えるスロット指定は拒否。
- 統計は同一 `battle_result_id` で二重加算されない。
- 既存の `/modules/battle-code` の保存/消費挙動は維持される。
