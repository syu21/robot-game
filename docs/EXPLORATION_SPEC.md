# 出撃仕様（/explore）

最終更新日: 2026-04-02

## 1. エンドポイント
- 実行: `POST /explore`
- 主入力: `area_key`
- エリア:
  - `layer_1`
  - `layer_2`
  - `layer_2_mist`
  - `layer_2_rush`
  - `layer_3`
  - `layer_4_forge`
  - `layer_4_haze`
  - `layer_4_burst`
  - `layer_4_final`（第4層3ボス撃破後の最終試験）
  - `layer_5_labyrinth`
  - `layer_5_pinnacle`
  - `layer_5_final`（第5層2ボス撃破後の最終試験）

## 2. 前提チェック順序
1. ログイン済み
2. `area_key` 妥当性
3. 層解放状態 (`max_unlocked_layer`)
4. 出撃機体存在（active robot）
5. 共通CT判定

## 3. CT仕様（共通）
- 一般ユーザー: 40秒
- 新規ブースト対象（登録後72時間）: 20秒
- 管理者: 0秒
- 重要: UI表示とサーバ判定は同一ヘルパーで一致させる

## 4. 戦闘仕様
- 実装正本は `docs/BATTLE_SPEC.md`
- ターン上限: 8
- 両者生存のまま8ターン到達時は残HP割合の高い側が勝利
- 残HP割合が同率なら敗北
- 連戦: 週間環境などの条件で発生可
- tier1救済: 通常戦で連続MISS時に救済ヒット
- 敵特性(trait)の軽補正あり

## 5. ボス抽選
- 基本出現率: 0.5%
- エリア対応ボスのみ抽選対象
- layer_2/3 は NPCボス統合抽選（実装時設定に従う）
- layer_4_forge / haze / burst は各エリア専用の固定ボスを持つ
- `layer_4_final` は第4層3ボス撃破後に解放される最終試験エリアで、`アーク=ゼロ` 固定
- `layer_5_labyrinth` / `layer_5_pinnacle` は各エリア専用の固定ボスを持つ
- `layer_5_final` は第5層2ボス撃破後に解放される最終試験エリアで、`オメガフレーム` 固定

## 6. 報酬決定
- コイン: 勝敗・環境補正に応じて加算
- パーツドロップ: 予算制御あり（探索単位で上限）
- 進化コア:
  - 低確率ドロップを維持
  - 勝利ごとの保証進捗を別管理
  - ゲージ満了で保証付与
  - layer_2/3 の NPCボス撃破では追加報酬として `進化コア x1`
  - 監査: `audit.core.drop`
- 第4層の育成傾向:
  - `layer_4_forge`: 耐久・防御寄り
  - `layer_4_haze`: 命中・安定寄り
  - `layer_4_burst`: 攻撃・会心寄り
  - `layer_4_final`: 最終試験（複合）
- 第5層の育成傾向:
  - `layer_5_labyrinth`: 耐久・命中・安定寄り
  - `layer_5_pinnacle`: 攻撃・会心・速攻寄り
  - `layer_5_final`: 最終試験（思想完成）

## 7. 戦利品表示（battle結果）
- 前面は最小表示:
  - 獲得コイン
  - ドロップ結果（なしなら `戦利品なし`）
- `進化コア保証` や `ボス報酬` は短い結果行で区別して表示
- 下部の `次の行動` はカード表示にし、`もう一度出撃 / 入手したパーツを見る / 基地へ戻る` を押しやすく出す
- CT 中の `もう一度出撃` はボタン文言と残り時間表示を同期し、0秒で自動活性化する
- 計算係数は前面非表示

## 8. 監査イベント
- `audit.explore.start`
- `audit.explore.end`
- `audit.boss.encounter`
- `audit.boss.defeat`
- `audit.drop`
- `audit.inventory.delta`
- `audit.core.drop`

## 9. 互換制約
- `turn_logs` 互換維持
- 出撃8ターン上限の維持
- 監査イベントの意味変更禁止
