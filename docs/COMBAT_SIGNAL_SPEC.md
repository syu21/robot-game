# COMBAT SIGNAL v1

最終更新日: 2026-08-15

## 目的
- 敵を単なるステータス差ではなく、予兆を読んで構成で対処する攻略対象にする。
- プレイヤーのターン入力は増やさず、既存戦闘ログとBATTLE CODEへ接続する。

## 基本仕様
- 敵特性 `trait` は常時性質、COMBAT SIGNAL はターン指定の一時戦術。
- 必ず `予兆 -> 次ターン発動` の順に出る。
- v1 は敵キーから固定パターンを決定し、戦闘開始時にスナップショット化する。
- 戦闘中にDB参照しない。
- 第1〜3層には付与しない。第5層は一部、第6層を主対象、第7層は管理者確認用の準備枠。

## v1 パターン
- `overcharge`: 2T予兆、3T敵攻撃20%上昇。攻撃後1Tは冷却で敵被ダメージが8%増える。
- `aegis`: 2T予兆、3T敵被ダメージ20%軽減。
- `lock_on`: 2T予兆、3T敵命中+15 / 会心+4。必中・確定会心ではない。
- `phase_shift`: 2T予兆、3T敵速度+10 / 回避側命中補正+14。

## 表示
- 戦闘ログ:
  - 1Tに敵戦術の概要を表示。
  - 2Tに予兆行を表示。
  - 3Tに発動行と効果行を表示。
- 結果画面:
  - 発生した戦術のみ `敵戦術パターン` として要約する。
- 図鑑:
  - 撃破済みの敵だけ戦術を表示。
- 管理:
  - `/admin/enemies` の一覧に戦術列を表示。

## BATTLE CODE 接続
- 予兆ターンに以下の条件を評価する。
  - `enemy_signal_overcharge`
  - `enemy_signal_aegis`
  - `enemy_signal_lock_on`
  - `enemy_signal_phase_shift`
- 発動ターンではなく予兆ターンで条件成立する。
- DUAL LOGIC でも既存の先勝ち解決を使う。

## turn_logs 追加キー
- `enemy_signal_intro_line`
- `enemy_signal_line`
- `enemy_tactic_trigger_line`
- `enemy_signal_key`
- `enemy_signal_label`
- `enemy_signal_phase`
- `enemy_tactic_key`
- `enemy_tactic_triggered`
- `enemy_tactic_effect`

旧ログにこれらが無くても表示・リプレイは動作する。

## リリース
- 新規DB release flag は追加しない。
- 理由: v1 は敵キー固定設定で、既存公開層にだけ作用する小規模戦闘補正。必要時は設定コードを外すことで停止可能。
