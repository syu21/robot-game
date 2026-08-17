# 今日の研究指令 v2

最終更新日: 2026-08-18

## 目的
- `ログイン -> 今日の用事を見る -> 数回遊ぶ -> 達成 -> 明日また見る` の軽い再訪ループを作る
- 新モードではなく、既存の出撃、パーツ入手、強化、編成、探索傾向を日替わりで遊ばせる
- 戦力インフレ報酬は配らない

## 生成
- JST の `YYYY-MM-DD` をseedにして、同じ日は再起動しても同じ3件を生成する
- `sortie`, `training`, `tendency` から1件ずつ選び、同系統だけ3件にならない
- v2では `user_id`, `max_unlocked_layer`, active robot, 所持パーツ状態をseed/候補に加え、ユーザーごとに達成可能な3件を生成する
- 既に当日分が `daily_research_progress` に保存済みなら、reloadしても内容を変えない

## v2指令候補
- 出撃: 巡回試験、勝利記録試験、定点巡回試験、比較巡回試験
- 育成: 回収試験、機体構成試験、強化試験、進化確認試験
- 型 / 探索傾向: 重装試験、照準試験、過負荷試験、思想比較研究
- 第4層: 装甲耐久試験、照準追従試験、出力限界試験
- 第5層: 安定巡回試験、高速突破試験

## 新規ユーザー保護
- 未解放区画を要求しない
- 傾向系で適切な解放済み区画がなければ、第1層の基礎試験へ代替する
- 第4層、進化、限定要素は解放済み/成立可能なユーザーにだけ候補化する
- 強化候補がないユーザーには強化必須指令を出さない
- active robotがなくても、回収/巡回/基礎思想研究で壊れない
- 第5〜7層到達者には、同じ探索傾向の上位区画を候補にできる
- 第6層到達者の傾向系は `layer_6_rebuild` / `layer_6_core` / `layer_6_final` を使い、未到達者には表示しない

## 報酬
- 各指令: 少量コイン
- 2件達成: `本日の研究完了` 相当の記録のみ
- 3件達成: 小額追加コイン + `daily_research_streak`
- 戦闘補正、強力パーツ、進化コア、限定通貨は付けない

## 表示
- ホームでは Next Action の下に `今日の研究指令 n/3` と3行だけ表示する
- 3件のうち1件だけ `おすすめ研究` として軽く強調する
- 出撃結果、強化結果、編成完了メッセージでは進捗を1行だけ表示する
- モーダルや別画面遷移で周回テンポを止めない

## データ
- `daily_research_progress`
- `daily_research_progress_receipts`
- `daily_research_day_records`
- `users.daily_research_streak`
- `users.daily_research_last_completed_day`

## 監査
- `audit.daily_research.view`
- `audit.daily_research.task.create`
- `audit.daily_research.progress`
- `audit.daily_research.complete`
- `audit.daily_research.reward`
- `audit.daily_research.all_complete`

## 二重加算防止
- `request_id` または元イベントIDを `source_key` 化する
- `user_id, day_key, mission_key, source_key` を一意化する
- ページリロード、POST再送、戻る、二度押しで同じ指令進捗と報酬を二重付与しない

## 定点観測
- 表示人数、1件以上進行、1件完了、2件以上完了、3件完了を維持する
- v2では `表示 -> 進行`, `進行 -> 1件完了`, `1件完了 -> 全完了` の率を人数付きで見る
- 翌日再訪は、当日指令表示者/進行者が翌日 `world_events_log` に活動を残したかで集計する
