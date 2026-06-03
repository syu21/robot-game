# 研究モジュール仕様

最終更新日: 2026-06-03

## 目的
- 第2・第3層以降の周回価値を増やす
- 第4層攻略の型選択を広げる
- パーツ/DECORとは別枠で、次の出撃だけに使う補正を選べるようにする

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
  - `description`, `is_active`, `created_at`
- `user_research_modules`
  - `user_id`, `module_key`, `status`
  - `status`: `inventory` / `consumed`
- `users`
  - `active_research_module_instance_id`
  - `research_module_pity`

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

## UI
- `/home`
  - 出撃機体カードで研究モジュールを選択
  - 研究ゲージ `x/100` を表示
  - 合成可能なprototypeがある場合だけ `/modules` へ導線表示
- `/modules`
  - 現在選択中
  - 研究ゲージ
  - 所持モジュール一覧
  - 効果
  - 合成可能なprototypeの「完成型へ合成」ボタン
