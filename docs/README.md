# ロボらぼ ドキュメント入口

最終更新日: 2026-03-08

このディレクトリは、`ロボらぼ` の実装仕様・運用仕様・監査仕様の正本です。
実装変更時は、関連仕様を必ず同時更新してください。

## 1. ゲーム概要
- ジャンル: ブラウザ型ロボ育成ポチゲー
- コアループ: `基地 -> 出撃 -> 戦利品 -> パーツ強化/進化合成 -> ロボ編成 -> 再出撃`
- 主要方針:
  - 戦力販売をしない
  - ボス報酬は DECOR 中心（戦力差を作らない）
  - 監査ログ `audit.*` を常に残す

## 2. 正本ドキュメント
- 全体: `docs/PROJECT_STATUS.md`
- 出撃: `docs/EXPLORATION_SPEC.md`
- 戦闘設計: `docs/BATTLE_DESIGN_SHEET.md`
- 編成/強化/進化: `docs/COMPOSITION_SPEC.md`
- パーツ計算: `docs/PART_STATS_SPEC.md`
- 敵: `docs/ENEMY_SPEC.md`
- 週間環境: `docs/WEEKLY_ENVIRONMENT_SPEC.md`
- 監査: `docs/AUDIT_LOG_SPEC.md`
- 運用チェック: `docs/OPERATIONS_CHECKLIST.md`
- UGC方針: `docs/UGC_ROADMAP.md`
- 監査状態レポート: `docs/STATE_AUDIT_REPORT.md`
- VPS本番化: `docs/VPS_PRODUCTION_SETUP.md`

## 3. 起動手順
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
make db-init
make dev
```

- 既定URL: `http://127.0.0.1:5050/home`
- DB: SQLite (`game.db`)

## 4. 主要ルート
- 認証:
  - `/register`
  - `/login`
  - `/admin/login`（管理者保護アカウント用）
  - `/logout`
- 基地/進行:
  - `/home`
  - `/map`
- 出撃:
  - `POST /explore`
- 編成/育成:
  - `/build`, `/build/confirm`
  - `/parts/strengthen`（`/parts/fuse` 互換）
  - `/parts/evolve`
- 管理:
  - `/admin`
  - `/admin/users`（BAN/通常ログイン保護）

## 5. 重要互換制約
- 出撃ターン上限: 8ターン固定
- `turn_logs` 互換維持
- 監査イベント体系 `audit.*` の互換維持
- SYSTEMチャット投稿は「ボス撃破時のみ」

## 6. 変更時ルール
1. 実装変更
2. 仕様ドキュメント更新
3. テスト更新
4. `python3 -m unittest discover -s tests -q` 緑確認
