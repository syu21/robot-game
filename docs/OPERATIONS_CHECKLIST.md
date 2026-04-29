# 運用チェックリスト

最終更新日: 2026-04-19

## 1. 出撃
- [ ] `POST /explore` が成功し8ターン以内で終了
- [ ] CTが導線に依らず一貫
  - 一般40秒
  - 新規20秒
  - 管理者0秒
- [ ] `もう一度出撃` 表示残秒とサーバ判定が一致
- [ ] battle結果で `pageshow / visibilitychange` 復帰後も CT 表示が古いまま残らない
- [ ] battle結果の `もう一度出撃` が 0秒到達でリロードなしに活性化する
- [ ] 基地のCT状態がリアルタイム更新される
  - CT中: `クールタイム中 あと mm:ss`
  - 0秒到達: `出撃可能`
  - 非管理者はCT中disabled / 管理者は常時出撃可

## 2. ボス
- [ ] 遭遇で `audit.boss.encounter`
- [ ] 撃破で `audit.boss.defeat`
- [ ] SYSTEM投稿は撃破時のみ
- [ ] DECOR重複抑止が有効

## 3. 戦利品UI
- [ ] 前面は `獲得コイン` + `ドロップ結果` のみ
- [ ] ドロップなしで `戦利品なし`
- [ ] 所持満杯時の新規パーツ報酬は消えず `自動売却 +NNコイン` と短く表示される
- [ ] 画面が縦長化しすぎない

## 4. 編成/育成
- [ ] `/home` の `今日の進捗` で `探索 / 獲得パーツ / 戦闘力増分 / ボス撃破 / 進化 / 強化` が見える
- [ ] 今日まだ動いていないときは `まだ動いていません` の空表示になる
- [ ] `/parts` で `画像 / 部位 / レアリティ / +値 / 6ステ / 装備中表示 / 総合値` が確認できる
- [ ] `/parts` の部位フィルター `すべて / 頭 / 右腕 / 左腕 / 脚` が動く
- [ ] `/parts` のソート `おすすめ順 / 新しい順 / 古い順 / 総合値順 / +値順 / レアリティ順 / 部位順` が分かりやすく切り替わる
- [ ] `/parts` のソートが部位フィルターやページ送りと併用しても落ちない
- [ ] `/parts` のチェック文言が `選択` で統一され、主操作が `見比べる / 破棄` に分かれている
- [ ] `/parts` の `見比べる` で選択した個体だけの比較セクションが出る
- [ ] `/parts` の `次へ` が無反応にならない
  - 進めるときは遷移する
  - 進めないときは disabled 相当の表示になる
- [ ] `旧在庫` など内部都合ラベルが表に出ていない
- [ ] `/home` のパーツ在庫が `所持 X/Y` のみで表示される
- [ ] `/parts` に旧保管セクションや `所持へ戻す` 導線が残っていない
- [ ] 所持上限超過の新規戦利品は `audit.part.auto_sell` とコイン加算が残る
- [ ] 旧 `overflow` は一括移行で `audit.part.overflow_cleanup_sell` として売却できる
- [ ] 装備中個体を選んで `破棄` しても、装備中のまま残る
- [ ] N画像が見つからないときに broken image ではなくプレースホルダへ落ちる
- [ ] `/build` で4部位必須 + DECOR任意
- [ ] `/build` の候補カードで `現在装備との差分` が先頭に出て、必要時だけ `詳細を開く` で 6ステ実数を確認できる
- [ ] `/build` のセットボーナス表示で `発動中/未発動 / 同属性パーツ 4部位で発動 / 何が上がるか` が分かる
- [ ] 保存枠満杯時に保存ブロック
- [ ] `/robots/<id>/maintenance` で1部位ずつ差し替え候補を見て整備できる
- [ ] 機体整備後に `composed_image_path / icon_32_path` が更新される
- [ ] `audit.robot.maintenance` が `changed_slots / before_part_ids / after_part_ids / stat_delta / power_delta` つきで残る
- [ ] `/parts/strengthen` で候補0件時の案内表示
- [ ] `/parts/strengthen` に旧保管確認導線が残っていない
- [ ] `/parts/strengthen` の部位フィルターが動く
- [ ] `/parts/strengthen` が `ベース1 + 素材2 -> +1固定` で動作
  - 素材2個消費
  - ベース個体のみ +1
  - 成功率100%
- [ ] `/parts/strengthen` で `強化前 -> 強化後` 差分が6ステで見える
- [ ] `/parts/strengthen` で装備中ベースと消える素材2個が分かる
- [ ] `/parts/strengthen` の失敗時に理由が結果面で分かる
- [ ] `/parts/strengthen` の `まとめて強化` が装備中素材を勝手に消費しない
- [ ] `/parts/strengthen` の `まとめて強化` で `残る個体 / 消える個体数 / 強化後 +値 / 実行回数` が事前に分かる
- [ ] `まとめて強化` 実行後に `batch_mode / batch_count` つきの `audit.fuse` が残る
- [ ] `/parts/strengthen` の `倉庫整理合成` がワンクリック即実行ではなく、必ず一覧プレビューを挟む
- [ ] `/parts/strengthen` の `倉庫整理合成` が装備中 / 売却済み個体を素材に混ぜない
- [ ] `/parts/strengthen` の `倉庫整理合成` で `対象種類数 / 合計強化回数 / 消費素材数 / 合計コイン` が事前に分かる
- [ ] `/parts/strengthen` の `倉庫整理合成` 実行後に `何種類整理したか / 合計何回強化したか / 素材消費数 / 合計コイン` が結果面で分かる
- [ ] `倉庫整理合成` で `装備中ベース優先 -> 高 +値 -> 古い個体` のベース選択が保たれる
- [ ] `/parts/evolve` でコア不足時に500にならない
- [ ] `/parts/evolve` の部位フィルターが動く
- [ ] `/parts/evolve` が `N + 進化コア1 -> R` で動作
  - N個体消費 / 進化コア1消費 / R個体生成
  - `plus`, `w_hp..w_cri` 引き継ぎ
- [ ] `/parts/evolve` で進化前後の比較が6ステで見える
- [ ] 第2層固定ボス撃破前は基地や個体一覧に進化合成導線が表示されない
- [ ] 第2層固定ボス撃破後は基地に進化合成カードが表示される
- [ ] 装備中パーツを進化合成したとき、装備参照キー・合成画像・icon_32 が即時更新される
- [ ] `/guide` に `思想ごとの戦い方` と `セットボーナス一覧` が出る
- [ ] `/home` や `/robots/<id>` で `思想` が短い戦い方説明つきで見える
- [ ] `/home` や `/robots/<id>` でセットボーナスの `条件 / 効果 / 発動有無` が見える

## 5. 認証/管理保護
- [ ] BANユーザーは `/login` 不可
- [ ] `is_admin_protected=1` は通常 `/login` 不可
- [ ] `/admin/login` で管理者保護アカウントがログイン可能
- [ ] 既ログインBANユーザーは次リクエストでログアウト
- [ ] `/admin/users` で自己BAN不可
- [ ] `/admin/users` で自己完全削除不可
- [ ] メイン管理者（username=`admin`）完全削除不可
- [ ] 完全削除確認画面に件数サマリーが表示される

## 6. 監査
- [ ] 主要フローで `request_id` が埋まる
- [ ] `audit.fuse`, `audit.part.evolve`, `audit.core.drop` が残る
- [ ] チャンプ戦で `audit.champ.battle.start`, `audit.champ.battle.end`, `audit.champ.reward.coin` が残る
- [ ] チャンプ初回撃破で `audit.champ.reward.core` と `CHAMP_DEFEAT_FIRST` が残る
- [ ] チャンプ日次撃破で `audit.champ.reward.daily_bonus` と `CHAMP_DEFEAT_DAILY` が残る
- [ ] 不利相性でチャンプ撃破すると `CHAMP_DEFEAT_UPSET` が世界ログに出る
- [ ] `audit.fuse.batch_preview`, `audit.fuse.batch_execute` が `warehouse_batch` payload つきで残る
- [ ] `audit.system.maintenance_block` が `path / method / mode / user_id` つきで残る
- [ ] 管理操作監査が残る
  - `audit.admin.user.ban`
  - `audit.admin.user.unban`
  - `audit.admin.user.protect_login`
  - `audit.admin.user.unprotect_login`
  - `audit.admin.user.delete`

## 7. 共有/招待
- [ ] ボス撃破時のみ共有ボタン表示
- [ ] `audit.share.click` 記録
- [ ] 有効 `ref` 登録で pending 作成
- [ ] 条件達成で qualified 遷移

## 8. リリース前検証
- [ ] `python3 -m py_compile app.py init_db.py services/stats.py services/fuse.py services/champion_battle.py services/battle_affinity.py constants.py`
- [ ] `python3 -m unittest discover -s tests -q`
- [ ] `python3 -m unittest tests.test_battle_affinity tests.test_weekly_champion`
- [ ] `python3 -m unittest tests.test_market tests.test_lab_casino tests.test_explore_drop_budget tests.test_tier_growth_staging tests.test_streak_bonus tests.test_parts_fuse_route`
- [ ] `python3 -m unittest tests.test_trial_mode`
- [ ] `/register` から `試験機で体験する` で `/trial/start` に入れる
- [ ] 体験中の `/home` に `お試しプレイ中`、`アーク・プロト`、`あとN分遊べます`、`あとN回出撃できます` が出る
- [ ] 体験中は `layer_1` だけ出撃でき、出撃結果に戦利品と次アクションが出る
- [ ] 体験中の `/parts`、`/parts/strengthen`、`/build` が session の一時パーツで動く
- [ ] 体験中の出撃・強化・編成が `users`、`world_events_log`、ランキングへ永続保存されない
- [ ] `/admin/release` で `廃品市場` が `admin_only` のままになっている
- [ ] `/market` が非管理者404、管理者200
- [ ] `/admin/market` で購入件数・売却件数・再入荷件数・平均価格が見える
- [ ] 実験室交換所 `/lab/race/prizes` が非管理者に出ていない

## 9. 世界競争UI
- [ ] `/home` の `今週のランキング` で `小ロボ主役 + 補助アバター` になっている
- [ ] `/home` の `今週のMVP` に `小ロボ主役 + 補助アバター` と機体画像が出る
- [ ] `/world` の `今週のMVP` に `小ロボ主役 + 補助アバター` と機体画像が出る
- [ ] `/records` の `初達成記録 / 今週の記録 / 話題ロボ` にユーザー表示と機体表示が出る
- [ ] `/ranking` の user系は `小ロボ主役 + 補助アバター`、robot系は機体サムネで表示される
- [ ] `/ranking` の robot系でプレースホルダ顔のまま残る古い機体画像があれば、自動で再生成される

## 10. 公開運用
- [ ] `MAINTENANCE_MODE=partial` で閲覧は残り、更新系POSTだけがサーバー側で止まる
- [ ] `MAINTENANCE_MODE=partial` 中に全ページ上部へメンテ告知帯が出る
- [ ] `MAINTENANCE_MODE=full` で非管理者はメンテ画面へ案内される
- [ ] `MAINTENANCE_MODE=full` でも管理者は通常確認を続けられる
- [ ] `/admin/release` から `通常運用 / 軽量メンテ / 全面メンテ` を切り替えられる
- [ ] `MAINTENANCE_MODE=partial/full` を入れると、管理画面設定より環境変数が優先される
- [ ] ヘッダー左上の `ロボらぼ` ロゴから、ログイン中は `/home`、未ログイン時は `/register` に戻れる
- [ ] `GET http://127.0.0.1:8000/healthz` が `200`
- [ ] `GET https://robolabo.site/healthz` が `200`
- [ ] `GET /sitemap.xml` が `200` で `application/xml`
- [ ] `https://robolabo.site/terms` が利用規約として表示される
- [ ] `https://robolabo.site/privacy` がプライバシーポリシーとして表示される
- [ ] `https://robolabo.site/commerce` が特定商取引法に基づく表記として表示される
- [ ] `https://robolabo.site/contact` の Google フォーム導線が最新URLを向いている
- [ ] favicon が配信される
  - `GET /static/favicon.png` が `200`
- [ ] `robot-game.service` が active
- [ ] `robot-game-healthcheck.timer` が active
- [ ] `robot-game-backup.timer` が active
- [ ] `robot-game-portal-online.timer` が active
- [ ] `.env.production` に `POCHI_PORTAL_ENDPOINT=https://games-alchemist.com` を設定済み
- [ ] `.env.production` に `POCHI_PORTAL_GAME_KEY=robolabo` を設定済み
- [ ] `.env.production` に発行済み `POCHI_PORTAL_API_KEY` を設定済み
- [ ] `python3 send_online_count.py --flush-limit 20` 手動実行または timer 実行結果を確認済み
- [ ] `backups/` に当日バックアップがある
- [ ] `https://pochi-games.com/pochi-game/portal/edit` のゲーム情報を更新済み
- [ ] 編集完了後の報告をあるけみすと公式へ送信済み
- [ ] ポチゲーポータルへの掲載相談/連絡状況をメモへ残す
