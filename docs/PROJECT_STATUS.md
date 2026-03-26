# プロジェクト進捗・現行仕様（ロボらぼ）

最終更新日: 2026-03-26

## 1. プロダクト目標
- 現在のロボらぼは `チュートリアルフェーズ` と位置付ける
- 短時間で回せるロボ育成ポチゲーを提供する
- 進行体験を「層解放」「ボス警報」「育成導線」で明確化する
- 競争要素は名誉・可視化中心にし、戦力インフレを避ける
- 探索場所差からロボの `型 / 思想 / 役割` を自然発生させる
- 競争はまず `世界ログ / ランキング / 展示 / 陣営戦` の間接競争で育てる
- `PvP は早期実装しない`
- `PvP は入口ではなくゴール` と位置付ける

### 1.1 判断基準
今後の提案・改善案・新機能は、必ず次の3条件で判断する。
- 周回が気持ちよくなるか
- 競争が自然発生するか
- プレイヤーの語りが生まれるか

### 1.2 参照ドキュメント
- 中長期方針の正本: `docs/GAME_DIRECTION.md`

## 2. コアループ
1. 基地で Next Action を確認
2. 出撃して戦闘・戦利品獲得
3. パーツ強化（+値上昇）または進化合成（N→R）
4. ロボ編成で機体更新
5. ボス戦・層解放を進める

## 3. 現行主要機能
### 3.1 認証・セッション
- `register/login/logout` を実装
- 管理者保護ログイン:
  - 通常 `/login`: `is_admin_protected=1` は拒否
  - `/admin/login`: 管理者保護アカウントでもログイン可
- BAN運用:
  - `is_banned=1` はログイン拒否
  - 既ログイン中でも次リクエストでセッション破棄

### 3.2 基地（/home）
- Next Action を最上段に1枚表示
- `最初のミッション` は閉じる/再表示できる
- `Next Action` はたたむ/開くことができ、ボス警報中は自動で開く
- 前回の出撃先を記憶し、ホーム最上部から再出撃できる
- 出撃先ごとの特徴文を `探索先メモ` として表示
- PC ではスクロールでヘッダーを自動表示/非表示
- モバイルでは `出撃機体 -> アクション` の順に優先表示
- 行動カード（出撃/ロボ編成/パーツ強化/進化合成）
- 行動カードは `育成` と `管理` を分けて整理
- 進化合成カードは第2層固定ボス撃破後に解放
- 解放後は `あと◯勝で進化コア` / `進化コア n個 / 次 x/y` を短く表示
- 週環境・陣営戦・MVP・招待導線を下段配置
- `世界戦況` と `記録庫` への導線を追加
- `今週のランキング` は `アイコン+小ロボ` つきで表示
- `今週のMVP` は `アイコン+小ロボ` と機体画像を併記
- CT状態はリアルタイムカウントダウン表示
  - CT中: `CT状態: クールタイム中 あと mm:ss`
  - 終了: `CT状態: 出撃可能`
  - 非管理者はCT中に出撃ボタンdisabled、0秒で自動活性化
- 行動カード補助文言（統一）
  - ロボ一覧: 組み立てたロボを確認
  - パーツ強化: 素材2つで強化
  - 進化合成: 進化コアで進化
  - ロボ編成: パーツを選んで完成登録
  - 所持パーツ: 個体と在庫を整理
- 出撃機体の `思想` と `注目能力` を短く表示
- 探索先メモで `育成傾向` を短く表示

### 3.3 出撃（/explore）
- 1出撃1戦（暴走時のみ連戦あり）
- ターン上限8
- ボス抽選・通常敵抽選・報酬抽選を実装
- CT:
  - 一般: 40秒
  - 新規ブースト(登録後72h): 20秒
  - 管理者: 0秒
- 探索場所ごとにパーツ個体の重みへ軽い育成傾向差を付与
  - layer_1: 耐久・防御寄り
  - layer_2: 命中・防御寄り
  - layer_2_mist: 命中寄り
  - layer_2_rush: 素早さ・会心寄り
  - layer_3: 攻撃・耐久寄り

### 3.4 育成
- パーツ強化: `/parts/strengthen`（`/parts/fuse`互換）
  - ベース1 + 素材2で +1固定
  - 成功率100%
  - 対象条件: 同名かつ同レアリティ
  - 素材2個は消費、ベース個体は残って +1
- 進化合成: `/parts/evolve`
  - Nパーツ + 進化コア1個 -> 対応Rパーツ
  - `plus` と `w_hp..w_cri` 引き継ぎ
  - 進化状況 / 次の保証 / 候補件数 を上部カードで表示
  - 進化前 / 進化後の比較を一覧上で見やすく表示
- ロボ編成: `/build` + `/build/confirm`

### 3.5 ボス・層進行
- ボス出現率 0.5%（エリア条件あり）
- 固定ボス3体（layer_1/2/3）
- layer_2/3 は NPCボス統合抽選あり
- 固定ボス/エリアボス報酬は DECOR 中心、NPCボスは進化コア報酬あり
- 層解放は `max_unlocked_layer` 管理

### 3.6 管理機能
- `/admin` 管理メニュー
- `/admin/users`:
  - BAN / BAN解除
  - 管理者保護ON/OFF
  - 自己BAN禁止
  - 自己保護OFF禁止（安全側）
  - 完全削除（確認画面つき）
    - 削除前に `user_id / username / ロボ数 / パーツ数 / 監査ログ件数 / 招待・紹介件数` を表示
    - 自己削除禁止
    - メイン管理者（username=`admin`）削除禁止
    - 削除監査: `audit.admin.user.delete`
- `/admin/audit`, `/admin/world`, `/admin/enemies`, `/admin/parts` など

### 3.7 公開/運用導線
- 独自ドメイン `https://robolabo.site` で公開中
- `/feed` の公開世界ログで、ボス撃破 / 進化成功 / パーツ入手 / 強化 / ロボ完成 / 週更新を閲覧可能
- `/feed?type=weekly` で `週更新 / 研究解禁 / 陣営戦決着` を見返せる
- `/ranking` で 勝利数 / 探索数 / 今週探索数 / 今週ボス撃破 / 最速 / 耐久 / 命中 / 爆発 を閲覧可能
- `/ranking` のユーザー系指標は `アイコン+小ロボ`、ロボ系指標は機体サムネで表示
- ホームから `今週のランキング` と `前回の出撃先で出撃` を自然に視認できる
- ロボ一覧 / ロボ個別 / ロボ展示で `思想` と `注目能力` を短く見える
- `/showcase` は 新着 / 今週 / ボス / いいね / 最速 / 耐久 / 命中 / 爆発 で並び替え可能
- `/terms`, `/privacy`, `/commerce` を独立した法務ページとして公開
- `/guide` で `思想 / 型 / 育成 / 世界競争` の基本用語を辞典形式で確認できる
- `/support` で `ロボらぼ支援パック` の Stripe Checkout 購入に進める
- `/payment/success` は「支払い確認中」、付与は webhook 完了後に反映
- `/admin/payments` で支払い履歴を確認できる
- `/world` で `今週の環境 / 熱源 / 陣営戦 / 研究進捗` をまとめて見返せる
- `/records` で `初達成記録 / 今週の記録 / 話題ロボ` を `アイコン+小ロボ` と機体画像つきで見返せる
- ホームの `今週のランキング`、`世界戦況` の MVP、`記録庫` で `アイコン+小ロボ` と機体画像を使った他プレイヤー表示を強化
- `/contact` で問い合わせ導線を提供
  - Google フォーム: `https://forms.gle/mmjKJqX6QrPE9GkJ6`
- `/sitemap.xml` を公開
- `favicon.png` を `head` から参照
- `GET /healthz` で最低限の公開監視に対応

## 4. 主要データモデル
- `users`
  - `active_robot_id`
  - `max_unlocked_layer`
  - `faction`
  - `avatar_path`
  - `invite_code`
  - `is_banned`, `is_admin_protected`, `banned_at`, `banned_reason`, `banned_by_user_id`
- `robot_instances`, `robot_instance_parts`
  - `composed_image_path`, `icon_32_path`
- `robot_parts`（`display_name_ja`, `offset_x/y`）
- `part_instances`（`plus`, `w_*`）
- `core_assets`, `user_core_inventory`
- `enemies`
- `world_weekly_environment`, `world_weekly_counters`
- `world_faction_weekly_scores`, `world_faction_weekly_result`
- `world_events_log`
- `world_events_log.audit.drop.payload`
  - `growth_tendency_key`
  - `growth_tendency_label`
- `payment_orders`
  - `stripe_checkout_session_id` UNIQUE
  - `stripe_event_id` UNIQUE
  - `status` は `created / completed / granted / failed / expired`
  - `boost_days / starts_at / ends_at` を保持
  - Stripe Checkout の生成と webhook 完了処理を追跡
- `users`
  - `explore_boost_until`
  - 出撃ブーストの有効期限を保持

## 5. UI文言方針（運用中）
- ホーム -> 基地
- 探索 -> 出撃
- ロボ組み立て -> ロボ編成
- パーツ進化 -> 進化合成
- 報酬サマリー -> 戦利品
- 公開フィード -> 世界ログ
- Showcase -> ロボ展示

## 6. 既知課題
- 一部画像アセットが欠損（プレースホルダ吸収済み）
- 管理画面の操作確認UI（ダイアログ等）は最小構成
- docsの更新粒度を継続改善中
- `SECRET_KEY` は本番用の長いランダム値へ再設定が必要
- `steel_scout.png` の欠損 warning がサーバーログに出るため、画像実体と参照整合の確認が必要

## 7. 決済サンドボックス状況
- `/support`
  - 支援パックの Stripe Checkout / webhook 付与が動作
- `/shop`
  - 出撃ブースト14日 (`explore_boost_14d`) のサンドボックス購入導線を追加
- 付与は `success_url` ではなく `checkout.session.completed` webhook を正とする
- 出撃CT は `admin 0秒 / 新規ブースト20秒 / 課金ブースト20秒 / 通常40秒`
  - 複数ブーストが同時に効く場合は最短CTを採用
## 8. 中長期の非目標（現時点）
- 早期PvP実装
- 人口が薄い段階での直接対人主導化
- 戦力販売

## 9. リリース品質ゲート
- `py_compile` 成功
- 全テスト緑
- 監査イベントの主要フロー確認
- CT/UI整合確認
