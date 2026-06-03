# 研究モジュール仕様

最終更新日: 2026-06-03

## 目的
- 第2・第3層以降の周回価値を増やす
- 第4層攻略の型選択を広げる
- パーツ/DECORとは別枠で、次の出撃だけに使う補正を選べるようにする
- 将来の流通資産として「集めたい」「残したい」「余ったら処分できる」を先に作る
- パーツはロボの身体、研究モジュールは出撃前に差し込む作戦チップとして扱う

## 装備仕様
- ロボ個体には固定装備しない
- `users.active_research_module_instance_id` に、次の出撃で使う `user_research_modules.id` を保存する
- 出撃時に active robot + active research module を読み、戦闘中だけ固定値補正を適用する
- パーツ個体ステータス自体は変更しない
- 補正後の `hp/atk/def/spd/acc/cri` は最低1にclampする

## DB
- `research_modules`
  - `module_key`, `name_ja`, `rarity`, `family`
  - `hp_bonus`, `atk_bonus`, `def_bonus`, `spd_bonus`, `acc_bonus`, `cri_bonus`
  - `description`, `tier`, `trade_policy`, `source_type`, `is_limited`, `npc_sell_price`
  - `is_active`, `created_at`
- `user_research_modules`
  - `user_id`, `module_key`, `status`
  - `is_locked`, `sold_at`
  - `status`: `inventory` / `consumed`
- `user_research_module_catalog`
  - `user_id`, `module_key`, `first_obtained_at`, `first_instance_id`
- `users`
  - `active_research_module_instance_id`
  - `research_module_pity`

## 流通用マスタ項目
- `tier`
  - prototype: `1`
  - complete: `2`
- `trade_policy`
  - `tradable`: 将来取引可能
  - `account_bound`: アカウント固定
  - `event_bound`: イベント固定
- `source_type`
  - `normal_drop`
  - `combine`
  - `event`
  - `admin`
  - `npc_shop`
- `is_limited`
  - 通常モジュールは `0`
- `npc_sell_price`
  - prototype: `300`
  - complete: `1500`

## prototype
- `sniper_prototype`: HP -3 / 命中 +8 / 会心 +3
- `heavy_prototype`: HP +10 / 防御 +6 / 素早さ -5
- `assault_prototype`: 攻撃 +8 / 素早さ +4 / 防御 -4
- `stable_prototype`: 防御 +5 / 命中 +5 / 会心 -3
- `berserk_prototype`: 攻撃 +12 / 会心 +6 / 命中 -8
- `analysis_prototype`: 命中 +6 / 防御 +3 / 攻撃 -3

## complete
- `sniper_complete`: HP -5 / 命中 +12 / 会心 +5
- `heavy_complete`: HP +15 / 防御 +9 / 素早さ -7
- `assault_complete`: 攻撃 +12 / 素早さ +6 / 防御 -6
- `stable_complete`: 防御 +8 / 命中 +8 / 会心 -5
- `berserk_complete`: 攻撃 +18 / 会心 +9 / 命中 -12
- `analysis_complete`: 命中 +10 / 防御 +5 / 攻撃 -5

## ドロップ
- 通常戦勝利時のみ、ボス報酬とは別枠
- `layer_2`: 2%
- `layer_2_mist`: 2.5%
- `layer_2_rush`: 2.5%
- `layer_3`: 3%
- 監査: `audit.module.drop`

## 研究ゲージ
- `users.research_module_pity` で管理
- 通常戦勝利時に加算
  - `layer_2`: +1
  - `layer_2_mist`: +1
  - `layer_2_rush`: +1
  - `layer_3`: +2
  - `layer_4_forge`: +3
  - `layer_4_haze`: +3
  - `layer_4_burst`: +3
- 100到達でランダムなprototype研究モジュールを1個保証付与
- 付与後は `research_module_pity -= 100`
- 監査:
  - `audit.module.pity.progress`
  - `audit.module.pity.grant`

## 同種3個合成
- `POST /modules/combine`
- 条件:
  - 本人所有
  - `status='inventory'`
  - `is_locked=0`
  - 現在選択中ではない
  - 同じ `module_key` のprototype 3個
- 処理:
  - 3個を `consumed` に更新
  - 対応するcompleteを1個付与
- 対応:
  - `sniper_prototype` -> `sniper_complete`
  - `heavy_prototype` -> `heavy_complete`
  - `assault_prototype` -> `assault_complete`
  - `stable_prototype` -> `stable_complete`
  - `berserk_prototype` -> `berserk_complete`
  - `analysis_prototype` -> `analysis_complete`
- 監査: `audit.module.combine`

## モジュール図鑑
- `/modules` で全activeモジュールを表示する
- 未所持でも名前、説明、効果、入手方法、買取価格、`trade_policy` を表示する
- 図鑑率は active な `research_modules` のうち、1回以上入手した `module_key` 数で計算する
- `consumed` / 売却済みでも、`user_research_module_catalog` に登録済みなら図鑑登録済み扱い
- モジュールドロップ、研究ゲージ保証、合成付与時に `INSERT OR IGNORE`
- 監査: `audit.module.catalog.register`

## ロック
- `/modules` で所持モジュールを保護/解除できる
- 対象:
  - 本人所有
  - `status='inventory'`
- ロック中もホームの選択候補には出す
- ロック中は合成素材・NPC買取・将来市場出品に使えない
- 監査:
  - `audit.module.lock`
  - `audit.module.unlock`

## NPC買取
- `/modules/sell/confirm/<id>` で確認画面を挟む
- `POST /modules/sell` で売却する
- 条件:
  - 本人所有
  - `status='inventory'`
  - `is_locked=0`
  - 現在選択中ではない
  - `trade_policy='tradable'`
  - `npc_sell_price > 0`
- 処理:
  - `user_research_modules.status='consumed'`
  - `sold_at` を記録
  - `users.coins += npc_sell_price`
- 監査:
  - `audit.module.sell`
  - `audit.coin.delta`

## UI
- `/home`
  - 出撃機体カードで研究モジュールを選択
  - 研究ゲージ `x/100` を表示
  - 合成可能なprototypeがある場合だけ `/modules` へ導線表示
- `/modules`
  - 現在選択中
  - 研究ゲージ
  - 図鑑率
  - 所持モジュール一覧
  - 保護/保護解除
  - NPC買取
  - モジュール図鑑
  - 効果
  - 合成可能なprototypeの「完成型へ合成」ボタン

## 将来予定
- ユーザー市場
- 出品
- 取引手数料
- 交換
- イベント限定モジュール
- 上位モジュール
