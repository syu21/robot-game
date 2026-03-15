# プロジェクト進捗・現行仕様（ロボらぼ）

最終更新日: 2026-03-11

## 1. プロダクト目標
- 短時間で回せるロボ育成ポチゲーを提供する
- 進行体験を「層解放」「ボス警報」「育成導線」で明確化する
- 競争要素は名誉・可視化中心にし、戦力インフレを避ける

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
- 行動カード（出撃/ロボ編成/パーツ強化/進化合成）
- 進化合成カードは進化コア所持時のみ表示
- 週環境・陣営戦・MVP・招待導線を下段配置
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

### 3.3 出撃（/explore）
- 1出撃1戦（暴走時のみ連戦あり）
- ターン上限8
- ボス抽選・通常敵抽選・報酬抽選を実装
- CT:
  - 一般: 40秒
  - 新規ブースト(登録後72h): 20秒
  - 管理者: 0秒

### 3.4 育成
- パーツ強化: `/parts/strengthen`（`/parts/fuse`互換）
  - ベース1 + 素材2で +1固定
  - 成功率100%
  - 対象条件: 同名かつ同レアリティ
  - 素材2個は消費、ベース個体は残って +1
- 進化合成: `/parts/evolve`
  - Nパーツ + 進化コア1個 -> 対応Rパーツ
  - `plus` と `w_hp..w_cri` 引き継ぎ
- ロボ編成: `/build` + `/build/confirm`

### 3.5 ボス・層進行
- ボス出現率 0.5%（エリア条件あり）
- 固定ボス3体（layer_1/2/3）
- ボス報酬は DECOR 中心
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

## 4. 主要データモデル
- `users`
  - `active_robot_id`
  - `max_unlocked_layer`
  - `faction`
  - `invite_code`
  - `is_banned`, `is_admin_protected`, `banned_at`, `banned_reason`, `banned_by_user_id`
- `robot_instances`, `robot_instance_parts`
- `robot_parts`（`display_name_ja`, `offset_x/y`）
- `part_instances`（`plus`, `w_*`）
- `core_assets`, `user_core_inventory`
- `enemies`
- `world_weekly_environment`, `world_weekly_counters`
- `world_faction_weekly_scores`, `world_faction_weekly_result`
- `world_events_log`

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

## 7. リリース品質ゲート
- `py_compile` 成功
- 全テスト緑
- 監査イベントの主要フロー確認
- CT/UI整合確認
