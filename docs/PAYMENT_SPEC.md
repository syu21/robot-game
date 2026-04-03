# 決済基盤仕様（Stripe / support_pack_founder / support_pack_lab / explore_boost_14d）

最終更新日: 2026-04-03

## 1. 目的
- 商品数を `支援2本 + 利便性1本` に絞り、迷わせない
- 戦力販売ではなく、`見栄 / 応援 / 参加感 / 利便性` で収益化する
- `success_url` ではなく webhook を正として付与する
- 既存の `audit.*` / `world_events_log` 体系に沿って追跡する

## 2. 商品構成
### 2.1 創設支援パック
- `product_key`: `support_pack_founder`
- 表示名: `創設支援パック`
- 価格: `100円`
- 性質: `1回限り`
- 決済: Stripe Checkout
- 特典:
  - `trophy_key`: `supporter_founder`
  - 表示名: `創設支援章`
  - DECOR: `founder_badge_silver`
  - 戦力差はつけない

### 2.2 ラボ維持支援パック
- `product_key`: `support_pack_lab`
- 表示名: `ラボ維持支援パック`
- 価格: `300円`
- 性質: `1回限り`
- 決済: Stripe Checkout
- 特典:
  - `trophy_key`: `supporter_lab`
  - 表示名: `ラボ支援章`
  - DECOR: `lab_badge_gold`
  - 戦力差はつけない

### 2.3 出撃ブースター
- `product_key`: `explore_boost_14d`
- 表示名: `出撃ブースター`
- 価格: `500円`
- 性質: `1回限り`
- 決済: Stripe Checkout
- 効果:
  - `grant_type`: `explore_boost`
  - `boost_days`: `14`
  - `探索CT 40秒 -> 20秒`
  - `周回効率アップ`

## 3. 環境変数
- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_ID_SUPPORT_FOUNDER`
- `STRIPE_PRICE_ID_SUPPORT_LAB`
- `STRIPE_PRICE_ID_EXPLORE_BOOST_14D`
- `PUBLIC_GAME_URL`

互換のため、旧 `STRIPE_PRICE_ID_SUPPORT_PACK` / `STRIPE_PRICE_ID_EXPLORE_BOOST` が残っている場合は読み取りフォールバックを持つが、本番運用では新しい3本を正本とする。

## 4. 主要ルート
- `GET /support`
  - 支援パック専用ページ
  - `創設支援パック 100円` と `ラボ維持支援パック 300円` を表示
  - `ロボらぼの開発を応援できます / 戦力差はつきません / 名前横バッジ / 限定DECOR付き` を案内
- `POST /support/founder/checkout`
  - `support_pack_founder` の Checkout Session を作成
  - `metadata` に `user_id / product_key` を保存
- `POST /support/lab/checkout`
  - `support_pack_lab` の Checkout Session を作成
  - `metadata` に `user_id / product_key` を保存
- `GET /shop`
  - `出撃ブースター 500円` を表示
  - `14日間 出撃しやすくなります / 探索CT 40秒 -> 20秒 / 周回効率アップ` を案内
- `POST /shop/explore-boost/checkout`
  - `explore_boost_14d` の Checkout Session を作成
  - `metadata` に `user_id / product_key / grant_type / boost_days` を保存
- `GET /payment/success`
  - 「支払い確認中」画面
  - 付与は行わない
- `GET /payment/cancel`
  - キャンセルからの戻り画面
- `POST /stripe/webhook`
  - `Stripe-Signature` を raw body で検証
  - `checkout.session.completed` を正として処理
- `GET /admin/payments`
  - 支払い履歴一覧 / 検索

## 5. DB
テーブル:
- `payment_orders`
- `user_trophies`

`payment_orders` 主要列:
- `user_id`
- `product_key`
- `stripe_checkout_session_id`
- `stripe_payment_intent_id`
- `stripe_event_id`
- `amount_jpy`
- `currency`
- `status`
- `grant_type`
- `boost_days`
- `starts_at`
- `ends_at`
- `granted_at`
- `created_at`
- `updated_at`

`user_trophies` 主要列:
- `user_id`
- `trophy_key`
- `granted_at`

制約:
- `stripe_checkout_session_id` UNIQUE
- `stripe_event_id` UNIQUE
- `UNIQUE(user_id, trophy_key)`

状態:
- `created`
- `completed`
- `granted`
- `failed`
- `expired`

## 6. 付与方針
- `success_url` 到達では付与しない
- webhook の `checkout.session.completed` だけで付与する
- クライアントから送られた `product / amount / price_id` は信用しない
- Checkout 作成時はサーバー固定の商品定義だけを使う
- `support_pack_founder` は `user_decor_inventory` と `user_trophies` の両方へ付与する
- `support_pack_lab` も `user_decor_inventory` と `user_trophies` の両方へ付与する
- DECOR 付与は `user_decor_inventory` へ `INSERT OR IGNORE`
- トロフィー付与は `user_trophies` へ `INSERT OR IGNORE`
- 既に同じ DECOR / トロフィーを所持している場合は二重付与せず `skip_duplicate`
- `explore_boost_14d` は `users.explore_boost_until` に期限を保存する
- ブースターは期限加算方式で扱い、既存期限が未来にある場合はそこから `14日` 延長する
- 旧 `support_pack_001` は `support_pack_founder` の互換商品として扱い、既存購入者にも `founder_badge_silver` と `supporter_founder` が揃うよう backfill する

## 7. 出撃CTとの競合整理
- 管理者: `0秒`
- 課金ブースト中: `20秒`
- それ以外: `40秒`
- 将来の短縮要素と重なった場合も、**最も短いCT** を採用する
- 実装では `min(通常CT, 各短縮CT)` の形で一箇所に寄せて判定する

## 8. webhook 処理方針
1. `Stripe-Signature` を検証
2. `audit.payment.webhook.received` を記録
3. `checkout.session.completed` のときだけ完了処理へ進む
4. `payment_orders` を `stripe_checkout_session_id` で特定
5. すでに `stripe_event_id` が同じ、または `status` が完了系なら冪等 skip
6. 商品ごとの付与ロジックへ分岐
   - `support_pack_founder`: `founder_badge_silver` + `supporter_founder`
   - `support_pack_lab`: `lab_badge_gold` + `supporter_lab`
   - `explore_boost_14d`: `explore_boost_until` を 14 日延長
7. 成功 / 重複 / 失敗を監査へ残す

## 9. 監査イベント
- `audit.payment.checkout.create`
- `audit.payment.webhook.received`
- `audit.payment.completed`
- `audit.payment.grant.success`
- `audit.payment.grant.skip_duplicate`
- `audit.payment.grant.failed`
- `audit.trophy.grant.success`
- `audit.trophy.grant.skip_duplicate`
- `audit.trophy.grant.failed`
- `audit.explore_boost.grant.success`
- `audit.explore_boost.grant.skip_duplicate`
- `audit.explore_boost.grant.failed`

payload 推奨キー:
- `user_id`
- `trophy_key`
- `product_key`
- `stripe_checkout_session_id`
- `stripe_payment_intent_id`
- `stripe_event_id`
- `amount_jpy`
- `currency`
- `status`
- `boost_days`
- `starts_at`
- `ends_at`
- `duplicate_reason`

## 10. 購入から付与までの流れ
1. ユーザーが `/support` または `/shop` から購入を開始
2. サーバーが Stripe Checkout Session を新規作成
3. Stripe hosted checkout で決済
4. `success_url` には「支払い確認中」だけを表示
5. Stripe webhook `checkout.session.completed` を受信
6. 署名検証後、`payment_orders` を更新
7. 商品ごとに特典を冪等付与
8. `world_events_log` に決済監査を残す

## 11. ローカル確認
### 11.1 アプリ起動
```bash
export STRIPE_SECRET_KEY=sk_test_xxx
export STRIPE_PUBLISHABLE_KEY=pk_test_xxx
export STRIPE_WEBHOOK_SECRET=whsec_xxx
export STRIPE_PRICE_ID_SUPPORT_FOUNDER=price_xxx
export STRIPE_PRICE_ID_SUPPORT_LAB=price_xxx
export STRIPE_PRICE_ID_EXPLORE_BOOST_14D=price_xxx
export PUBLIC_GAME_URL=http://127.0.0.1:5050
python3 app.py
```

### 11.2 Stripe CLI
```bash
stripe login
stripe listen --forward-to http://127.0.0.1:5050/stripe/webhook
```

Stripe CLI が表示した `Signing secret` を `STRIPE_WEBHOOK_SECRET` に設定する。

### 11.3 動作確認
1. `/support` を開く
2. `支援する（100円）` と `しっかり支援する（300円）` が出ることを確認
3. `/shop` を開き、`購入する（500円）` が出ることを確認
4. Stripe Checkout でテスト決済
5. `/payment/success` は「確認中」表示になる
6. webhook 後に `payment_orders.status=granted` を確認
7. founder 購入では `founder_badge_silver` と `supporter_founder` を確認
8. lab 購入では `lab_badge_gold` と `supporter_lab` を確認
9. ブースター購入では `users.explore_boost_until` が延長されることを確認
10. ヘッダーや `/ranking` などで支援章バッジが見えることを確認

## 12. 本番設定
1. Stripe ダッシュボードで本番用 Price を確認
2. `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` / `STRIPE_WEBHOOK_SECRET` を本番値で設定
3. `STRIPE_PRICE_ID_SUPPORT_FOUNDER` / `STRIPE_PRICE_ID_SUPPORT_LAB` / `STRIPE_PRICE_ID_EXPLORE_BOOST_14D` を設定
4. `PUBLIC_GAME_URL` を `https://robolabo.site` に設定
5. webhook endpoint を `/stripe/webhook` に向ける
6. `/support` `/shop` `/admin/payments` を確認

## 13. 本番移行時の注意
- `success_url` では付与されないため、Webhook 到達確認を必ず行う
- 支援系は 1 回限りなので、手動補填時は `payment_orders` と `user_trophies` / `user_decor_inventory` の両方を確認する
- ブースターは利便性課金であり、戦力差を売らない方針を崩さない
- 旧 `support_pack_001` の購入履歴が残っている環境では backfill 後の founder 特典反映も確認する

## 14. セキュリティ注意
- シークレットは環境変数のみ
- `success_url` では付与しない
- webhook の署名検証を必ず通す
- `price_id` や `amount` はフロントから受け取らない
- webhook 再送で二重付与されないことを前提に設計する
