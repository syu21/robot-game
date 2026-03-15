# 運用チェックリスト

最終更新日: 2026-03-11

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
- [ ] 画面が縦長化しすぎない

## 4. 編成/育成
- [ ] `/build` で4部位必須 + DECOR任意
- [ ] 保存枠満杯時に保存ブロック
- [ ] `/parts/strengthen` で候補0件時の案内表示
- [ ] `/parts/strengthen` が `ベース1 + 素材2 -> +1固定` で動作
  - 素材2個消費
  - ベース個体のみ +1
  - 成功率100%
- [ ] `/parts/evolve` でコア不足時に500にならない
- [ ] `/parts/evolve` が `N + 進化コア1 -> R` で動作
  - N個体消費 / 進化コア1消費 / R個体生成
  - `plus`, `w_hp..w_cri` 引き継ぎ
- [ ] 進化コア未所持時は基地に進化合成カードが表示されない

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
