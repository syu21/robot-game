# 実験室レース仕様

最終更新日: 2026-03-28

## 1. 方針
- 観戦レースとエネミーレースは `共通レースエンジン` を使う
- 6体同時
- 観戦が主役
- 半分読めて半分荒れる、予想しやすさ優先
- 強いロボが必ず勝たない

## 2. 共通エンジン
- `services/lab_race_course.py`
  - コース定義
  - 障害物マスタ
  - 特殊区間抽選
- `services/lab_race_simulator.py`
  - 進行シミュレーション
  - フレーム生成
  - イベント生成
  - 順位計算
- `services/lab_race_engine.py`
  - `mode="standard" | "casino"` で共通の race bundle を生成
  - コース生成 + 出走体生成 + 事前シミュレーションを束ねる

## 3. 通常レース参加
- ログイン必須
- 本編の `robot_instances` から1体選択
- 初期版は参加と同時に開催
- 不足枠は `LAB ENEMY` / NPC で補完し、6体固定に揃える

## 4. コース
- 区間数は 10 固定
- `1区間目 = START`
- `10区間目 = GOAL`
- `2〜9区間` から特殊区間を `2〜5個` 抽選
- 抽選の基本分布:
  - `3個`: 60%
  - `4個`: 25%
  - `2個`: 10%
  - `5個`: 5%
- 未採用区間は通常路として扱う
- コース候補:
  - `scrapyard_sprint`
  - `gravity_lane`

### 4.1 障害物マスタ
- `boost_pad`
- `oil_slick`
- `barrier_spin`
- `warp_gate`
- `slow_zone`
- `pitfall`
- `magnet_field`
- `shock_gate`
- `jump_pad`
- `safe_bay`

### 4.2 抽選制約
- 同一レース内で同じ障害物は重複させない
- `boost` 系は最大 1
- `hazard` 系は最大 2
- `chaos` 系は最大 1
- `safe` 系は最大 1
- 3連続の特殊区間は避ける
- 中盤を全区間特殊にしない

## 5. ステータス影響
- `spd`: 基本速度上昇。ただし事故寄り
- `def`: ヒット時の減速・復帰を軽減
- `acc`: スリップ / 誤作動を軽減
- `cri`: 会心ダッシュやワープ成功を伸ばす
- `atk`: 接触時の押し勝ち補正
- `hp`: 事故後の立て直し補助
- `luck`: 荒れ区間での上振れ下振れに影響

## 6. シミュレーション
- seed 固定
- サーバーで事前計算
- `lab_race_frames` または `lab_casino_frames` にフレーム保存
- `course_payload_json` に、そのレースで採用された 10 区間構成を保存
- `lab_race_records` に順位記録保存

## 7. watch 画面
- `/lab/race/watch/<race_id>` はエネミーレースの主導線
- 観戦レースは `/lab/race/legacy/watch/<race_id>` で再生する
- 共通表示:
  - 6レーン
  - 10区間コース
  - ライブ順位
  - イベントログ
  - コンパクト参加者カード
- エネミーレース差分:
  - 予想情報
  - 注目ロボ強調
  - 倍率参照の補助表示

## 8. 公開
- `/lab/race/watch/<race_id>` で再生
- `/lab/race/result/<race_id>` で結果確認
- `/lab/race/history` で予想履歴を確認
- `/lab/race/prizes` で交換所景品を確認
- `/lab/race/rankings` は観戦レースの記録庫として残す

## 9. エネミーレースとの関係
- レース本体は観戦レースと共通
- 倍率計算、予想、払い戻し、lab_coin はレース周辺サービス側で扱う
- 敵6体は固定キャラだが、各レースで `condition` とステータスが揺らぐ
