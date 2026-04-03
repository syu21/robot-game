# 決済基盤仕様（Stripe / support_pack_001 / explore_boost_14d）

最終更新日: 2026-04-03

## 1. 目的
- 本格課金の前に、安全な決済土台を先に作る
- 戦力販売ではなく、見た目・参加価値の支援導線から始める
- `success_url` ではなく webhook を正として付与する
- 既存の `audit.*` / `world_events_log` 体系に沿って追跡する

## 2. 対象商品
- `product_key`: `support_pack_001`
- 表示名: `ロボらぼ支援パック`
- 支援額: `100円`
- 決済: Stripe Checkout
- 付与: 初回限定の見た目特典 + 支援者トロフィー
  - `grant_type`: `decor`
  - `grant_key`: `shien_trophy`
  - `trophy_key`: `supporter_founder`
  - 表示名: `創設支援章`
  - 説明: `開発初期を支えた証`
- `product_key`: `explore_boost_14d`
- 表示名: `出撃ブースト`
- 支援額: `500円`
- 決済: Stripe Checkout
- 付与: 14日間の出撃CT短縮
  - `grant_type`: `explore_boost`
  - `boost_days`: `14`
  - 効果: `通常40秒 -> 20秒`
  - 1アカウント1回限定

## 3. 環境変数
- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_ID_SUPPORT_PACK`
- `STRIPE_PRICE_ID_EXPLORE_BOOST`
- `PUBLIC_GAME_URL`

今回のサンドボックス商品は以下を使う:
- `STRIPE_PRICE_ID_EXPLORE_BOOST=price_1TF2saJwvZBQaY3FEzCD3h0S`

## 4. 主要ルート
- `GET /shop`
  - 出撃ブーストのサンドボックス購入ページ
  - ログイン済みなら購入導線と残り期間を表示
- `POST /shop/explore-boost/checkout`
  - 毎回新しい Checkout Session を生成
  - `metadata` に `user_id / product_key / grant_type / boost_days` を保存
- `GET /support`
  - 支援パック説明ページ
  - ログイン済みなら `支援する（100円）` ボタンを表示
- `POST /support/checkout`
  - 毎回新しい Checkout Session を生成
  - `metadata` に `user_id / product_key / grant_type` を保存
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
- クライアントから送られた product/amount は信用しない
- Checkout 作成時はサーバー固定の商品定義だけを使う
- `support_pack_001` は `user_decor_inventory` と `user_trophies` の両方へ付与する
- DECOR 付与は `user_decor_inventory` へ `INSERT OR IGNORE`
- トロフィー付与は `user_trophies` へ `INSERT OR IGNORE`
- DECOR キーは `shien_trophy` を使い、既存の `support_pack_001` 購入済みユーザーにも backfill で揃える
- 既に同じ DECOR を所持している場合は二重付与せず `skip_duplicate`
- 既に同じトロフィーを所持している場合も二重付与せず `skip_duplicate`
- 出撃ブーストは `users.explore_boost_until` に期限を保存する
- 出撃ブーストは 1回限定で、すでに期限が入っている場合は `skip_duplicate`
- `support_pack_001` は表示用の支援者バッジとして `創設支援章` を付けるが、戦力差はつけない

## 7. 出撃CTとの競合整理
- 管理者: `0秒`
- 新規ブースト: `20秒`
- 課金出撃ブースト中: `20秒`
- それ以外: `40秒`
- 新規ブーストと課金出撃ブーストが同時に有効な場合は、**最も短いCTを採用**する
- 今回の実装では `min(通常CT, 新規CT, 課金CT)` の形で一箇所に寄せて判定する

## 8. webhook 処理方針
1. `Stripe-Signature` を検証
2. `audit.payment.webhook.received` を記録
3. `checkout.session.completed` のときだけ完了処理へ進む
4. `payment_orders` を `stripe_checkout_session_id` で特定
5. すでに `stripe_event_id` が同じ、または `status` が完了系なら冪等 skip
6. 商品ごとの付与ロジックへ分岐
   - `support_pack_001`: DECOR + トロフィー付与
   - `explore_boost_14d`: 出撃CT短縮期限を付与
7. 成功/重複/失敗を監査へ残す

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
1. ユーザーが `/shop` または `/support` から購入を開始
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
export STRIPE_PRICE_ID_SUPPORT_PACK=price_xxx
export STRIPE_PRICE_ID_EXPLORE_BOOST=price_1TF2saJwvZBQaY3FEzCD3h0S
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
1. `/shop` を開く
2. 出撃ブースト購入を押す
3. Stripe Checkout でテスト決済
4. `/payment/success` は「確認中」表示になる
5. webhook 後に `payment_orders.status=granted` と `users.explore_boost_until` を確認
6. `/support` でも既存支援パックが同じ webhook 基盤で動くことを確認する
7. 支援完了後、ヘッダーや `/ranking` などで `創設支援章` が見えることを確認する

## 12. サンドボックス設定
1. Stripe ダッシュボードでサンドボックス用 Price を確認
2. `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` / `STRIPE_WEBHOOK_SECRET` をテスト用で設定
3. `STRIPE_PRICE_ID_SUPPORT_PACK` / `STRIPE_PRICE_ID_EXPLORE_BOOST` を設定
4. `PUBLIC_GAME_URL` をローカル確認時は `http://127.0.0.1:5050`、公開確認時は該当URLに設定
5. webhook endpoint を `/stripe/webhook` に向ける
6. `/shop` と `/support` と `/admin/payments` を確認

## 13. 本番移行時の注意
- 今回の出撃ブーストは**サンドボックス前提で導線を追加**している
- 本番公開前に、Price / webhook secret / 商品文言 / 管理画面確認を再点検する
- `success_url` では付与されないため、Webhook 到達確認を必ず行う
- 1回限定商品のため、手動補填時も `explore_boost_until` と `payment_orders` の両方を確認する

## 14. セキュリティ注意
- シークレットは環境変数のみ
- `success_url` では付与しない
- webhook の署名検証を必ず通す
- `price_id` や `amount` はフロントから受け取らない
- webhook 再送で二重付与されないことを前提に設計する
