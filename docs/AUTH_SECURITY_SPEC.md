# 認証防御仕様

最終更新日: 2026-07-11

## 目的
- 登録/ログインフォームへの攻撃スキャンを抑止する。
- 失敗理由を過度に返さず、監査ログに原因を残す。

## 入力正規化
- `unicodedata.normalize("NFKC", value)`
- 前後空白、改行、タブ、制御文字、NULL文字を拒否
- username は3文字以上、64文字以内
- login_id/email は254文字以内
- HTMLタグ風入力とSQL注入風入力を拒否

## レート制限
- 登録IP: 1分3回、10分8回、1時間15回
- ログインIP: 5分20回
- ログインID: 5分10回
- 超過時は `audit.security.registration.rate_limited` / `audit.security.login.rate_limited`

## CSRF
- `/register`
- `/login`
- `/admin/login`
- `/admin/users`
- フォーム表示でCSRFトークンが発行済みのPOSTはトークン必須。

## 不審登録監査
- `audit.security.registration.suspicious`
- payload:
  - `suspicious_reasons`
  - `target_user_id`
  - `ip_hash`

## 表示方針
- 通常ログイン失敗は `ログイン情報を確認してください。`
- 管理画面ではメールらしき内部IDをマスク表示
