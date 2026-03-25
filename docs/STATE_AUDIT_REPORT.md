# 監査状態レポート（STATE_AUDIT_REPORT）

最終更新日: 2026-03-25

## 1. サマリー
- 監査基盤 `world_events_log` は継続運用可能
- 主要導線（出撃・育成・ボス・共有・招待・管理操作）で監査イベントが揃っている
- request_id 付与で追跡性は良好
- 監査ログは内部追跡だけでなく、世界ログ・ランキング・間接競争の土台として運用する

## 1.1 関連方針
- 中長期の運営思想は `docs/GAME_DIRECTION.md` を正本とする
- 監査基盤は `努力値 -> 周回思想 -> 世界競争 -> PvP` のうち、特に `世界競争` を支える基盤として強化する
- そのため、今後の監査追加は次も意識する
  - 周回量の可視化
  - 型/思想の可視化
  - 間接競争に転換しやすい公開ログ構造

## 2. 現在の監査カバレッジ
### 2.1 コアループ
- 出撃開始/終了: `audit.explore.start/end`
- 報酬関連: `audit.drop`, `audit.inventory.delta`, `audit.coin.delta`
- ボス: `audit.boss.encounter/defeat`
- `audit.drop` には探索場所由来の `growth_tendency_key / growth_tendency_label` を保持
  - どの周回先でどんな型が育ちやすいかを後追い分析しやすくした

### 2.2 育成
- 強化: `audit.fuse`
- 進化: `audit.part.evolve`
- コア流入: `audit.core.drop`

### 2.3 ソーシャル
- 共有クリック: `audit.share.click`
- 招待紐付け: `audit.referral.attach`
- 招待条件達成: `audit.referral.qualified`

### 2.4 管理操作
- ユーザーBAN/解除
- 管理者保護ON/OFF
- 監査イベント追加済み

## 3. 互換性チェック
- `turn_logs` 互換: 維持
- 出撃上限8ターン: 維持
- `audit.*` 名称互換: 維持（追加のみ）

## 4. リスクと対策
- リスク: 仕様追加時の docs/実装ズレ
- 対策:
  - 変更PRで docs 同時更新を必須化
  - checklistで監査イベント存在確認

## 5. 次の改善候補
- 管理操作の理由入力の必須化（任意→必須）
- `/admin/audit` の saved filter 機能
- 監査payloadのスキーマ定義（JSON Schema化）
- 型 / 思想ランキングを監査ログ側から再集計しやすい派生ビュー整理

## 6. 白化インシデント詳細記録（2026-03）
### 6.1 発生事象
- `/home` や `/parts/fuse` で画面全体が白/灰色化し、UI操作不能になる事象が断続発生
- 併発症状:
  - `Unexpected end of input`
  - `Invalid or unexpected token`
  - `Missing initializer in const declaration`
- 特徴:
  - `?no_js=1` では正常表示
  - そのため、CSS単独ではなく JavaScript 実行経路が主因

### 6.2 観測された主要エラーシグネチャ
- `home_page_v2.js:163:20` の SyntaxError（環境によって再現）
- `parts_fuse.js?v=0.1.0/0.1.1` の `Unexpected end of input`（配信キャッシュ残骸疑い）
- `base_cleanup.js/base_cleanup_v2.js` 配信切断時の `Unexpected end of script`

### 6.3 根本切り分け結果
- ローカル作業ツリー上の `static/home_page_v2.js` / `static/parts_fuse.js` は `node --check` で通過
- それでもブラウザ側で SyntaxError が出るケースがあり、主因は「配信中の古い/破損キャッシュ混線」の割合が高い
- ただし `/home` 白化自体はレイアウト系JSの影響を受けるため、個別無効化スイッチを導入して再現分離可能にした

### 6.4 実施したコード修正
#### A. ページ専用JSの誤実行防止
- `static/parts_fuse.js`
  - `parts-fuse-root` と body class (`parts-fuse-page` / `parts-strengthen-page`) の両方でページガード
  - 非対象ページでは即 return
- `templates/parts_fuse.html`
  - ルート要素 `id="parts-fuse-root"` を追加

#### B. 破損キャッシュ経路の遮断
- `parts_fuse.js` を `parts_fuse_v2.js` に切替（テンプレ参照先更新）
- `home_page_v2.js` は安全実装に再構成し、script query version を更新

#### C. global error guard の調査モード化
- `static/global_error_guard.js`
  - 画面全体を隠す処理を停止（非致命トーストのみ）
  - `/client-error/js` 送信を拡張（page/path/last_step/DOM状態/script一覧）
  - `window.__clientDiag` を提供し、各ページJSから `init_step` / `caught_exception` を送信
  - `window.onunhandledrejection` を明示実装

#### D. サーバーログの判読性向上
- `/client-error/js` 受信ハンドラでログレベル分離
  - `init_step` -> `INFO`
  - `window.onerror` / `unhandledrejection` / `caught_exception` -> `ERROR`
  - その他診断 -> `WARNING`
- `overlay-scan` はターミナルへ全文出力:
  - `tag`, `id`, `className`, `rect`, `zIndex`, `backgroundColor`
- `home_page_v2.js:163:20` の既知SyntaxErrorは別系統ログ（known）で切り分け

#### E. 基底テンプレの診断スイッチ追加
- `templates/base.html` に以下の query フラグを実装:
  - `?no_js=1` : 全script停止（純HTML/CSS確認）
  - `?no_layout_js=1` : `base_cleanup_v2.js` + `header_scroll.js` 停止
  - `?no_base_cleanup=1` : `base_cleanup_v2.js` のみ停止
  - `?no_header_scroll=1` : `header_scroll.js` のみ停止
  - `?js_diag=1` : 診断送信強化

### 6.5 診断用 URL 手順（再発時）
1. `.../home?no_js=1`
   - 正常表示なら JS原因確定
2. `.../home?js_diag=1`
   - 通常経路で診断ログ取得
3. `.../home?js_diag=1&no_base_cleanup=1`
4. `.../home?js_diag=1&no_header_scroll=1`
5. `.../home?js_diag=1&no_layout_js=1`
   - 3〜5 の比較でレイアウト系JS寄与を分離

### 6.6 現在の安定状態（2026-03-12時点）
- `/home?no_js=1` は正常表示を確認済み（JS主因）
- `parts_fuse` 系は新ファイル名参照に切替済み
- 診断ログは DevTools なしでターミナルのみ追跡可能
- 既存ゲーム仕様（`/parts/strengthen` 正規導線、`/parts/fuse` 互換）は維持

### 6.7 再発防止運用
- ページ専用JS更新時は必須:
  - `node --check <file.js>`
  - 参照テンプレの query version 更新
- 配信不整合疑い時は:
  - 別名JS (`*_v2.js`) への切替を優先
  - まず `?no_js=1` で CSS/JS を1手で切り分け

## 7. VPS 本番化メモ（2026-03-20）
### 7.1 本番稼働状態
- さくらVPS 上で `gunicorn + systemd + nginx` 構成へ移行済み
- systemd service: `robot-game.service`
- 公開確認先: `http://49.212.193.15/login`
- `curl -I http://127.0.0.1:8000/login` -> `200`（gunicorn）
- `curl -I http://127.0.0.1/login` -> `200`（nginx 経由）

### 7.2 今回反映した修正
- 管理画面で敵を無効化しても、起動時シードで `is_active=1` に戻る不具合を修正
- 同系統で DECOR / core 定義の seed も既存 `is_active` を保持する形へ修正
- 管理者ユーザー完全削除の監査イベント `audit.admin.user.delete` を定数へ追加
- `ADMIN_USER_DELETE` 未定義時でも管理画面が 500 にならないよう防御コードを追加
- `tests/test_admin_asset_toggle_persistence.py` を追加し、敵/装飾の有効化トグル保持を回帰確認

### 7.3 VPS 反映時の実運用メモ
- `git pull` 前に VPS 上の手修正 `app.py` は `git stash` が必要だった
- 初回は nginx の `/static/` 直配信で `403` が発生
- 対応として `location /static/ { alias ... }` を外し、静的ファイルも gunicorn 経由に統一
- その後、`/static/style.css` と `avatar_default.png` の `200` を確認し、表示崩れは解消

### 7.4 未完了 / 次アクション
- 2026-03-20 時点では HTTPS は未導入だった
- 当時の次優先は ドメイン取得 -> DNS `A` レコードを VPS へ向ける -> `PUBLIC_GAME_URL` をドメインへ更新 -> `certbot --nginx`
- HTTPS 導入完了までは `.env.production` の `SESSION_COOKIE_SECURE=0` を維持する想定だった
- `SECRET_KEY` が仮値のままなら、本番用ランダム値へ差し替えて `sudo systemctl restart robot-game.service`

### 7.5 2026-03-20 時点のローカル検証結果
- `python3 -m py_compile app.py init_db.py constants.py` は通過
- `python3 -m unittest discover -s tests -q` は `156` 件実行、`11` 件失敗
- 失敗群は主に以下の未整合に残っている
  - `base_cleanup_v2.js` を期待するテストと、実装が `base_cleanup_v3.js` を読む差分
  - `home next action` の DOM / 導線期待値の差分
  - newbie explore boost の CT 文言・表示期待値差分
  - `register` の `password_confirm` 必須化に追従していない starter/referral 系期待値

### 7.6 ローカル作業ツリー注意
- ローカルには `balance_config.py` と静的アセット周辺に未整理差分が残っている
- 本番化作業と無関係なため、別タスクとして整理・コミット方針を切り分けること

## 8. ドメイン / HTTPS / UI 反映メモ（2026-03-21）
### 8.1 公開URLと HTTPS
- 独自ドメイン `https://robolabo.site` で公開確認済み
- 本番確認先:
  - `https://robolabo.site/login`
  - `https://robolabo.site/home`
- `.env.production` は以下へ更新済み
  - `PUBLIC_GAME_URL=https://robolabo.site`
  - `SESSION_COOKIE_SECURE=1`
  - `HEALTHCHECK_URL=https://robolabo.site/healthz`
- `robot-game.service` 再起動直後に一瞬 `502 Bad Gateway` が見えることがあるが、今回ログ上は即復旧し、恒常障害ではなかった

### 8.2 sitemap.xml 追加
- `Flask` 側に `/sitemap.xml` を追加済み
- `Content-Type: application/xml; charset=utf-8` を返す簡易静的 XML 実装
- 含めるURL:
  - `https://robolabo.site/`
  - `https://robolabo.site/login`
  - `https://robolabo.site/register`
  - `https://robolabo.site/home`
- 確認結果:
  - `curl http://127.0.0.1:8000/sitemap.xml` -> `200`
  - `curl https://robolabo.site/sitemap.xml` -> `200`
- 補足:
  - ドメイン運用後は `Host: robolabo.site` 前提の nginx 振り分けになるため、`http://127.0.0.1/sitemap.xml` 直打ちは `404` でも不思議ではない

### 8.3 モバイル UI 調整（本番反映済み）
- スマホでヘッダーの黒帯が居残る問題を緩和
- モバイル時はヘッダーを compact/static 扱いに寄せ、スクロール被りを減らした
- ホームの優先順を調整し、`出撃機体` を `アクション` より上へ移動
- キャッシュ切りのため `APP_VERSION` は `0.1.13` へ更新済み

### 8.4 PC ホームのヘッダースクロール挙動
- 通常ページではヘッダースクロールJSが動作している
- `/home` だけ `header_scroll_v2.js` 読み込みが止まり、黒ヘッダーが消えない不具合を確認した
- 現在のコードでは修正済み:
  - ホームでも `header_scroll_v2.js` を常時読む
  - `tests/test_ops_release_surface.py` に `/home` でスクリプトが載る回帰テストを追加
- 再発時は `header_scroll_v2.js` の読み込み有無と `APP_VERSION` によるキャッシュ切り替えを優先確認する

### 8.5 運用メモ
- `SECRET_KEY` は現在短い暫定値になっているため、長いランダム文字列への差し替えが必要
- `journalctl -u robot-game.service` では `asset.missing key=enemy:enemies/steel_scout.png` の warning を確認
- `steel_scout.png` の実在確認・パス整合は別途実施すること

### 8.6 公開後の追加反映
- `favicon.png` を `static/` 直下へ配置し、`<head>` から参照するよう更新
- `https://robolabo.site/sitemap.xml` は `https://robolabo.site/...` の `loc` を返すことを確認
- `robot-game.service` 再起動後も `gunicorn` / `nginx` の両方で復旧確認済み

### 8.7 法務/問い合わせ導線
- `/terms` と `/privacy` は同一の法務ページへ統合済み
- プライバシーポリシー内の問い合わせ先直接記載は外し、`/contact` 導線へ統一
- Google フォーム問い合わせ先は `https://forms.gle/mmjKJqX6QrPE9GkJ6`

### 8.8 ポチゲーポータル連絡
- 2026-03-21 時点で、ポチゲーポータル側へ掲載相談の連絡を実施
- 正式掲載依頼前の確認事項として、同時接続数送信ジョブ・監視・バックアップ運用の docs 整備を継続
- 2026-03-22 にあるけみすと公式から返信あり
  - 掲載方針は前向き
  - 登録条件は「ゲーム側で測定した同時接続数を 5 分ごとに送信すること」
  - `game_key` は `robolabo`
  - `api_key` は発行済みの秘密情報として `.env.production` のみで管理し、repo へは保存しない
  - ゲーム情報編集ページ: `https://pochi-games.com/pochi-game/portal/edit`
  - 開発者 Discord: `https://discord.gg/HvJD7Jx5`
  - 情報編集完了後に公式へ報告すると、宣伝ツイート対応予定

## 9. ローカル未反映の追加作業（2026-03-21 時点）
### 9.1 ポチゲーポータル / 運用補強
- ローカル作業ツリーには以下の未反映差分あり
  - `send_online_count.py`
  - `manage_portal_online.py`
  - `tests/test_portal_online_count.py`
  - `deploy/systemd/robot-game.env.example`
  - `deploy/nginx/robot-game.conf.example`
  - `docs/VPS_PRODUCTION_SETUP.md`
  - `docs/OPERATIONS_CHECKLIST.md`
- 主目的:
  - ポータル送信運用の補強
  - VPS セットアップ / 運用手順の更新

### 9.2 利用規約 / プライバシー / 問い合わせ導線
- ローカル差分:
  - `templates/contact.html`
  - `templates/login.html`
  - `templates/register.html`
- 公開前の最低限法務・案内文言の整備候補として保持中

### 9.3 バックアップ / 監視 / 補助スクリプト
- 未追跡 / 未反映ファイル:
  - `manage_backups.py`
  - `manage_healthcheck.py`
  - `docs/BACKUP_RESTORE.md`
  - `docs/OPERATIONS_RUNBOOK.md`
  - `deploy/systemd/robot-game-backup.service.example`
  - `deploy/systemd/robot-game-backup.timer.example`
  - `deploy/systemd/robot-game-healthcheck.service.example`
  - `deploy/systemd/robot-game-healthcheck.timer.example`
  - `deploy/systemd/robot-game-portal-online.service.example`
  - `deploy/systemd/robot-game-portal-online.timer.example`
- いずれも本番投入前に、既存の本番反映済み変更と分けてレビュー・コミットするのが安全
