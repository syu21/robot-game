# 運用チェックリスト

最終更新日: 2026-03-30

## 1. 出撃
- [ ] `POST /explore` が成功し8ターン以内で終了
- [ ] CTが導線に依らず一貫
  - 一般40秒
  - 新規20秒
  - 管理者0秒
- [ ] `もう一度出撃` 表示残秒とサーバ判定が一致
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
- [ ] 所持満杯時でもパーツ報酬が消えず `保管` 表示になる
- [ ] 画面が縦長化しすぎない

## 4. 編成/育成
- [ ] `/parts` で `画像 / 部位 / レアリティ / +値 / 6ステ / 装備中表示 / 総合値` が確認できる
- [ ] `/parts` の部位フィルター `すべて / 頭 / 右腕 / 左腕 / 脚` が動く
- [ ] `/parts` のチェック文言が `選択` で統一され、主操作が `見比べる / 破棄` に分かれている
- [ ] `/parts` の `見比べる` で選択した個体だけの比較セクションが出る
- [ ] `/parts` の `次へ` が無反応にならない
  - 進めるときは遷移する
  - 進めないときは disabled 相当の表示になる
- [ ] `旧在庫` など内部都合ラベルが表に出ていない
- [ ] `/home` のパーツ在庫が `所持 X/Y | 保管 Z` で表示される
- [ ] `/parts` に `保管中の個体パーツ` が分離表示され、強化/進化/編成候補に混ざらない
- [ ] `/parts` の `保管中の個体パーツ` から所持へ戻せる
- [ ] 所持枠がいっぱいのときは `所持へ戻す` が押せないか、理由が明示される
- [ ] 装備中個体を選んで `破棄` しても、装備中のまま残る
- [ ] N画像が見つからないときに broken image ではなくプレースホルダへ落ちる
- [ ] `/build` で4部位必須 + DECOR任意
- [ ] `/build` の候補カードで `総合値 / 6ステ` を見ながら選べる
- [ ] 保存枠満杯時に保存ブロック
- [ ] `/parts/strengthen` で候補0件時の案内表示
- [ ] `/parts/strengthen` で保管中個体のため成立していない場合、`/parts` の保管確認導線が出る
- [ ] `/parts/strengthen` の部位フィルターが動く
- [ ] `/parts/strengthen` が `ベース1 + 素材2 -> +1固定` で動作
  - 素材2個消費
  - ベース個体のみ +1
  - 成功率100%
- [ ] `/parts/strengthen` で `強化前 -> 強化後` 差分が6ステで見える
- [ ] `/parts/strengthen` で装備中ベースと消える素材2個が分かる
- [ ] `/parts/strengthen` の失敗時に理由が結果面で分かる
- [ ] `/parts/evolve` でコア不足時に500にならない
- [ ] `/parts/evolve` の部位フィルターが動く
- [ ] `/parts/evolve` が `N + 進化コア1 -> R` で動作
  - N個体消費 / 進化コア1消費 / R個体生成
  - `plus`, `w_hp..w_cri` 引き継ぎ
- [ ] `/parts/evolve` で進化前後の比較が6ステで見える
- [ ] 第2層固定ボス撃破前は基地や個体一覧に進化合成導線が表示されない
- [ ] 第2層固定ボス撃破後は基地に進化合成カードが表示される

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
- [ ] `python3 -m py_compile app.py init_db.py services/stats.py services/fuse.py constants.py`
- [ ] `python3 -m unittest discover -s tests -q`

## 9. 世界競争UI
- [ ] `/home` の `今週のランキング` に `アイコン+小ロボ` が出る
- [ ] `/home` の `今週のMVP` に `アイコン+小ロボ` と機体画像が出る
- [ ] `/world` の `今週のMVP` に `アイコン+小ロボ` と機体画像が出る
- [ ] `/records` の `初達成記録 / 今週の記録 / 話題ロボ` にユーザー表示と機体表示が出る
- [ ] `/ranking` の user系は `アイコン+小ロボ`、robot系は機体サムネで表示される
- [ ] `/ranking` の robot系でプレースホルダ顔のまま残る古い機体画像があれば、自動で再生成される

## 10. 公開運用
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
