# ロボらぼ

ブラウザ型のロボ育成ゲームです。現在は `基地 -> 出撃 -> 強化/進化 -> 編成` の本編に加えて、`第5層（labyrinth / pinnacle / 最終試験）` までの型学習と思想競争の導線、そして `実験室` という観戦・展示向けの別モードを持ちます。

実験室のレースは `共通レースエンジン` を使い、`エネミーレース` と観戦レースが同じ 6 レーン基盤で動きます。コースは 10 区間固定ですが、特殊障害物は毎レース 2〜5 個だけ抽選され、残りは通常路です。

公開は `段階解放` を前提にしていて、`/admin/release` から `実験室 / 第4層 / 第5層` を個別に一般公開へ切り替えられます。未公開の間は管理者のみアクセスでき、一般ユーザーには導線も表示しません。

## 主要ルート
- `/home`
- `/lab`
- `/lab/race`
- `/lab/race/history`
- `/lab/race/prizes`
- `/lab/upload`
- `/lab/showcase`
- `/ranking`
- `/world`
- `/records`
- `/admin/release`

## ドキュメント
- 全体状況: `docs/PROJECT_STATUS.md`
- 実験室全体: `docs/LAB_SPEC.md`
- 実験室レース: `docs/LAB_RACE_SPEC.md`
- エネミーレース: `docs/LAB_ENEMY_RACE_SPEC.md`
- 実験室投稿: `docs/LAB_SUBMISSION_SPEC.md`
- 監査: `docs/AUDIT_LOG_SPEC.md`
