# 監査状態レポート（STATE_AUDIT_REPORT）

最終更新日: 2026-03-20

## 1. サマリー
- 監査基盤 `world_events_log` は継続運用可能
- 主要導線（出撃・育成・ボス・共有・招待・管理操作）で監査イベントが揃っている
- request_id 付与で追跡性は良好

## 2. 現在の監査カバレッジ
### 2.1 コアループ
- 出撃開始/終了: `audit.explore.start/end`
- 報酬関連: `audit.drop`, `audit.inventory.delta`, `audit.coin.delta`
- ボス: `audit.boss.encounter/defeat`

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
- HTTPS は未導入
- 次の優先はドメイン取得 -> DNS `A` レコードを VPS へ向ける -> `PUBLIC_GAME_URL` をドメインへ更新 -> `certbot --nginx`
- HTTPS 導入完了までは `.env.production` の `SESSION_COOKIE_SECURE=0` を維持
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
