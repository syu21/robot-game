# ロボらぼ ドキュメント入口

最終更新日: 2026-04-02

このディレクトリは、`ロボらぼ` の実装仕様・運用仕様・監査仕様の正本です。
実装変更時は、関連仕様を必ず同時更新してください。

## 1. ゲーム概要
- ジャンル: ブラウザ型ロボ育成ポチゲー
- コアループ: `基地 -> 出撃 -> 戦利品 -> パーツ強化/進化合成 -> ロボ編成 -> 再出撃`
- 主要方針:
  - 戦力販売をしない
  - 固定ボス/エリアボス報酬は DECOR 中心、NPCボスは進化コア報酬あり
  - 監査ログ `audit.*` を常に残す
  - 未ログイン時の `/` は `register` へ流し、登録・Google登録・ログインを同じ認証ゲートで扱う
  - `ホームの今週ランキング / 世界戦況のMVP / 記録庫 / ロボ展示` で他プレイヤーの存在感と研究導線を強める
  - `通信` は `世界ログ / 会議室 / 個人ログ` を役割分担し、世界ログは世界級の出来事と全体発言、個人ログは自分の成長記録を担う
  - 基地内でも `通信` タブから世界ログ・会議室・陣営通信・個人ログをページ内で即時切替できる
  - `通信 / 世界戦況 / 記録庫 / ランキング` では最近の活動人数や presence 表示を使い、少人数でも世界が動いている感じを補強する
  - ホームでは `今週のMVP` の直下に `通信` を置き、右列は `アクション / 今週の戦況 / 陣営戦 / メニュー / 今週のランキング / 表示調整` の順で見る

## 2. 正本ドキュメント
- 運営思想 / 中長期方針: `docs/GAME_DIRECTION.md`
- 実装優先ロードマップ: `docs/IMPLEMENTATION_ROADMAP.md`
- 実況 / 分析カテゴリ整理: `docs/ANALYSIS_TEMPLATE_CATEGORIES.md`
- 決済基盤: `docs/PAYMENT_SPEC.md`
- 全体: `docs/PROJECT_STATUS.md`
- 出撃: `docs/EXPLORATION_SPEC.md`
- 戦闘設計: `docs/BATTLE_DESIGN_SHEET.md`
- 編成/強化/進化: `docs/COMPOSITION_SPEC.md`
- パーツ計算: `docs/PART_STATS_SPEC.md`
- 敵: `docs/ENEMY_SPEC.md`
- 週間環境: `docs/WEEKLY_ENVIRONMENT_SPEC.md`
- 監査: `docs/AUDIT_LOG_SPEC.md`
- 実験室全体: `docs/LAB_SPEC.md`
- 実験室レース: `docs/LAB_RACE_SPEC.md`
- エネミーレース: `docs/LAB_ENEMY_RACE_SPEC.md`
- 実験室投稿: `docs/LAB_SUBMISSION_SPEC.md`
- 決済/ショップ: `docs/PAYMENT_SPEC.md`
- 運用チェック: `docs/OPERATIONS_CHECKLIST.md`
- バックアップ/復元: `docs/BACKUP_RESTORE.md`
- 公開後ランブック: `docs/OPERATIONS_RUNBOOK.md`
- UGC方針: `docs/UGC_ROADMAP.md`
- 監査状態レポート: `docs/STATE_AUDIT_REPORT.md`
- VPS本番化: `docs/VPS_PRODUCTION_SETUP.md`

## 3. 起動手順
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 init_db.py
FLASK_APP=app.py FLASK_ENV=development flask run --host 127.0.0.1 --port 5050
```

- 既定URL: `http://127.0.0.1:5050/home`
- DB: SQLite (`game.db`)
- 公開URL: `https://robolabo.site`
- 本番ヘルス確認:
  - gunicorn 直: `curl -i http://127.0.0.1:8000/healthz`
  - 公開導線: `curl -I https://robolabo.site/healthz`

## 4. 現フェーズの最重要認識
- 現在のロボらぼは `チュートリアルフェーズ`
- 公開入口はまだ `/register` 中心で、`/` は公開LPではなく認証ゲートへの導線として使っている
- 探索・強化・進化・ボス・DECOR取得は基礎体験の提供段階
- 先に作るのは `周回快感` と `型/思想の自然発生`
- 競争はまず `世界ログ / ランキング / 陣営戦` などの間接競争で成立させる
- `現在の出撃機体から作る小ロボ(32x32)` を主役にし、手動 / Google / seed 補助アバターで「他プレイヤーがいる感じ」を出す
- `通信` では最近の活動人数や会議室参加人数を見せて、無人感を減らす
- `/build` では同名・同強化値パーツも個体ごとに並べ、まとめ表示に引っ張られず選べる
- `/admin/metrics` では `進行状況` セクションから、層到達人数 / 停止層 / ボス未撃破 / 最終活動を見返せる
- `PvP は入口ではなくゴール`
- 今後の提案は次の3条件で判断する
  - 周回が気持ちよくなるか
  - 競争が自然発生するか
  - プレイヤーの語りが生まれるか

## 5. 主要ルート
- 認証:
  - `/`（公開入口。未ログイン時は `/register` へ）
  - `/register`
  - `/login`
  - `/admin/login`（管理者保護アカウント用）
  - `/logout`
  - `/guide`
  - `/shop`（サンドボックスの出撃ブースト購入）
  - `/support`
  - `/payment/success`, `/payment/cancel`
  - `/terms`
  - `/privacy`
  - `/commerce`（特定商取引法に基づく表記）
  - `/contact`
- 基地/進行:
  - `/home`
  - `/lab`
  - `/lab/race`
  - `/lab/race/history`
  - `/lab/race/prizes`
  - `/lab/upload`
  - `/lab/showcase`
  - `/map`
  - `/world`
  - `/records`
  - `/comms`
  - `/comms/world`
  - `/comms/rooms`
  - `/comms/faction`
  - `/comms/personal`
  - `/ranking`
  - `/showcase`
  - `/feed`
- 出撃:
  - `POST /explore`
- 編成/育成:
  - `/build`, `/build/confirm`
  - `/parts/strengthen`（`/parts/fuse` 互換）
  - `/parts/evolve`
- 管理:
  - `/admin`
  - `/admin/release`
  - `/admin/users`（BAN/通常ログイン保護）
  - `/admin/payments`
- 決済受信:
  - `/stripe/webhook`
- 公開/運用:
  - `/healthz`
  - `/sitemap.xml`

## 6. 重要互換制約
- 出撃ターン上限: 8ターン固定
- `turn_logs` 