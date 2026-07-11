# 集計除外仕様

最終更新日: 2026-07-11

## 目的
- 攻撃スキャン、テスト登録、管理者を通常プレイヤー指標から除外する。
- アカウント自体は削除せず、監査可能な状態で残す。

## DB
- `users.analytics_excluded`
- `users.analytics_excluded_at`
- `users.analytics_excluded_reason`
- `users.analytics_excluded_by_user_id`

## 除外条件
- `analytics_excluded=1`
- `is_admin=1`
- `username` が `test_` / `bot_` 始まり
- `username='test_user'`

## 管理操作
- `/admin/users` で個別に `集計除外` / `集計対象へ戻す`
- `/admin/users` で不審登録候補を一括除外
- 操作は `audit.admin.analytics.exclude` / `audit.admin.analytics.include` に記録

## 対象集計
- `/admin/metrics` の日次指標
- `/admin/metrics` の行動ファネル
- `/admin/metrics` の新規初回体験ファネル
- コアドロップ観測

## 非対象
- BAN
- ログイン停止
- ユーザー削除
- ランキング全般の仕様変更
