# ミニロボ培養室 仕様

最終更新日: 2026-05-10

## 目的
- 実験室内で小さなロボを選び、観察・お世話・名前変更を行うサブ機能。
- 本編の強さ、コイン、パーツ、層進行には影響しない。
- 毎日少し触れるための軽い育成・観察コンテンツ。
- 公開は release gate `lab_mini` で制御する。

## 現在できること
- `/lab` から `ミニロボ培養室` へ移動できる。
- 初回は3種類から1体を選ぶ。
- 選んだミニロボの状態、画像、ステータス、最近の反応を確認できる。
- 1日1回だけお世話できる。
- 時間帯に応じた様子を観察できる。
- ミニロボの名前を18文字以内で変更できる。
- `/lab/mini/catalog` で図鑑を確認できる。
- 管理者だけ内部パラメータを `管理者メモ` として確認できる。

## UX
### 実験室トップ
- ルート: `/lab`
- `lab_mini` が公開中、または管理者の場合のみ導線を表示する。
- 所持済みの場合:
  - 現在のミニロボ画像
  - ニックネーム
  - 状態ラベル
  - `小さなロボの様子を見る`
- 未所持の場合:
  - 初期候補画像
  - `ケルベロス、フェニックス、ヒュドラの3体が追加されました。`

### 初回選択
- ルート: `GET /lab/mini`
- 未所持の場合、選択カードを表示する。
- 3体すべての画像、説明、性格の雰囲気を表示する。
- `最初に一緒に過ごすミニロボを1体選びます。ほかのミニロボは、今後の研究で出会えるかもしれません。` を表示する。
- 表示項目:
  - 画像
  - 名前
  - 説明
  - 性格の雰囲気
  - `このミニロボにする` ボタン
- 選択後はユーザーに1体だけ作成される。
- すでに所持している場合、再選択はできない。

### 培養室
- ルート: `GET /lab/mini`
- 所持済みの場合、以下を表示する。
- ミニロボ画像
- 状態バッジ
- ニックネーム
- 種族名
- 成長段階
- ステータス
  - 愛着
  - 元気
  - 安定
  - 機嫌
  - 状態
  - 性格
- 名前変更フォーム
- 今日のお世話
- 今の様子
- 最近の反応
- お世話の記録

### お世話
- ルート: `POST /lab/mini/care`
- 1日1回だけ実行可能。
- 2回目以降は `今日はもうお世話済みです。` を表示し、値を変えない。
- 現在の選択肢:

| action_key | 表示名 | 主な効果 |
| --- | --- | --- |
| `energy` | ごはんをあげる | 元気を大きく上げる |
| `pet` | なでる | 愛着と機嫌を上げる |
| `maintenance` | 整えてあげる | 安定を上げる |

- お世話後は `happy` 表示で培養室へ戻る。
- `care_count` と `consecutive_care_days` を更新する。
- `growth_exp` は最大100まで加算される。

### 観察
- ルート: `POST /lab/mini/observe`
- 時間帯に応じた反応文を表示する。
- 観察は報酬なし。
- コイン、パーツ、ミニロボの育成値は変えない。
- 同じ日・同じ時間帯の観察ログは1件だけ保存する。
- ただし監査ログは観察操作ごとに残る。

### 名前変更
- ルート: `POST /lab/mini/rename`
- `nickname` を更新する。
- 空文字は不可。
- 19文字以上は不可。
- 上限は18文字。

### 図鑑
- ルート: `GET /lab/mini/catalog`
- 全種族を表示する。
- 所持済みの種族だけ詳細を表示する。
- 所持済みの表示項目:
  - 通常画像
  - 表示名
  - 説明文
  - 性格の雰囲気
  - `所持済み` バッジ
- 未所持の種族は存在だけ表示する。
- 未所持の表示項目:
  - 暗めの通常画像
  - 表示名
  - `未所持` バッジ
  - `まだ一緒に過ごしたことがありません。今後の研究で出会えるかもしれません。`
- 未所持では説明文、性格の雰囲気、状態差分を表示しない。

## ミニロボ種族
### ケルベロス
- `species_key`: `cerberus`
- 初期種族キー。
- 表示名: ケルベロス
- 説明: 三つの頭を持つ、元気いっぱいの番犬型ミニロボ。
- 性格表示: よく反応して、少し騒がしいタイプ。
- `type_key`: `guard`

### フェニックス
- `species_key`: `phoenix`
- 表示名: フェニックス
- 説明: 小さな火花をまとった、静かで神秘的なミニロボ。
- 性格表示: 落ち着いていて、あたたかい雰囲気。
- `type_key`: `heat`

### ヒュドラ
- `species_key`: `hydra`
- 表示名: ヒュドラ
- 説明: 複数の頭がそれぞれ違う反応をする、不思議なミニロボ。
- 性格表示: 少し変わっていて、観察しがいがあるタイプ。
- `type_key`: `multi`

## 状態
| state | 表示 | 内容 |
| --- | --- | --- |
| `normal` | いつも通り | 通常表示 |
| `blink` | まばたき | ランダムまたは好きな時間帯の変化 |
| `happy` | ごきげん | お世話直後の反応 |
| `sleep` | ねむり | 夜、眠い性格、またはお世話済み後の表示 |

## 成長段階
| stage | 表示 | 現状 |
| --- | --- | --- |
| `child` | 幼体 | 作成時の固定値 |
| `growth` | 成長体 | ラベル定義のみ |
| `mature` | 成熟体 | ラベル定義のみ |

現状は進化・段階遷移の実装はない。`growth_exp` と内部シードは将来拡張用。

## 内部性格
作成時にランダムで決まる。

| personality_key | 影響 |
| --- | --- |
| `timid` | お世話時に安定が上がり、ストレスが下がりやすい |
| `curious` | お世話時に好奇心が上がる |
| `loyal` | お世話時に信頼が上がりやすい |
| `sleepy` | 眠り状態になりやすい |
| `wild` | 本能が上がり、安定が少し下がる |
| `playful` | 機嫌と好奇心が上がりやすい |

一般ユーザーには `性格: 調査中` と表示する。  
管理者には `管理者メモ` で `personality_key` などを表示する。

## 時間帯
JSTで判定する。

| time_band | 時刻 |
| --- | --- |
| `morning` | 5:00 - 10:59 |
| `day` | 11:00 - 15:59 |
| `evening` | 16:00 - 20:59 |
| `night` | 21:00 - 4:59 |

## 画像
- 配置先: `static/mini_robots/<species>/<state>.png`
- 現在の画像:
  - `static/mini_robots/cerberus/normal.png`
  - `static/mini_robots/cerberus/blink.png`
  - `static/mini_robots/cerberus/happy.png`
  - `static/mini_robots/cerberus/sleep.png`
  - `static/mini_robots/phoenix/normal.png`
  - `static/mini_robots/phoenix/blink.png`
  - `static/mini_robots/phoenix/happy.png`
  - `static/mini_robots/phoenix/sleep.png`
  - `static/mini_robots/hydra/normal.png`
  - `static/mini_robots/hydra/blink.png`
  - `static/mini_robots/hydra/happy.png`
  - `static/mini_robots/hydra/sleep.png`
- 画像がない場合のフォールバック:
  - 対象種族の `normal.png`
  - `cerberus/normal.png`
  - `assets/placeholder_enemy.png`

## バックエンド
### 主要ルート
| method | route | 内容 |
| --- | --- | --- |
| `GET` | `/lab/mini` | 培養室表示 |
| `POST` | `/lab/mini/select` | 初回ミニロボ選択 |
| `POST` | `/lab/mini/care` | お世話 |
| `POST` | `/lab/mini/observe` | 観察 |
| `POST` | `/lab/mini/rename` | 名前変更 |
| `GET` | `/lab/mini/catalog` | 図鑑 |

### 主要関数
| 関数 | 役割 |
| --- | --- |
| `_mini_robot_species_choices` | 選択可能な種族一覧を作る |
| `_create_user_mini_robot` | ユーザーのミニロボを作成する |
| `_get_user_mini_robot` | ユーザーの所持ミニロボを1体取得する |
| `_mini_robot_view` | テンプレート用の表示データを作る |
| `_mini_robot_catalog_rows` | 図鑑表示用データを作る |
| `_mini_robot_state_for_time` | 時間帯・性格・乱数から状態を決める |
| `_mini_robot_display_state` | 表示用状態を決める |
| `_mini_robot_observe_message` | 観察文を選ぶ |
| `_mini_robot_care_message` | お世話反応文を選ぶ |
| `_mini_robot_add_log` | 最近の反応ログを保存する |
| `_mini_robot_open_for_viewer` | release gate と管理者権限から閲覧可否を決める |

## データ構造
### `mini_robot_species`
種族マスタ。

| column | 内容 |
| --- | --- |
| `species_key` | 種族キー |
| `name_ja` | 表示名 |
| `description` | 説明 |
| `type_key` | 種別 |
| `image_normal` | 通常画像 |
| `image_blink` | まばたき画像 |
| `image_happy` | ごきげん画像 |
| `image_sleep` | ねむり画像 |
| `is_active` | 選択可能フラグ |

### `user_mini_robots`
ユーザーごとの所持ミニロボ。

| column | 内容 |
| --- | --- |
| `id` | ミニロボID |
| `user_id` | 所有ユーザーID |
| `species_key` | 種族キー |
| `nickname` | 名前 |
| `stage` | 成長段階 |
| `affection` | 愛着 |
| `stability` | 安定 |
| `energy` | 元気 |
| `mood` | 機嫌 |
| `growth_exp` | 成長度 |
| `current_state` | 現在状態 |
| `last_cared_at` | 最終お世話時刻 |
| `personality_key` | 内部性格 |
| `growth_type` | 成長タイプ |
| `behavior_seed` | 挙動用シード |
| `evolution_seed` | 将来進化用シード |
| `trust` | 信頼 |
| `curiosity` | 好奇心 |
| `instinct` | 本能 |
| `stress` | ストレス |
| `care_count` | お世話回数 |
| `consecutive_care_days` | 連続お世話日数 |
| `last_care_date` | 最終お世話日 |
| `favorite_time_band` | 好きな時間帯 |
| `last_state_reason` | 状態理由 |
| `created_at` | 作成時刻 |

制約:
- `UNIQUE(user_id, species_key)`
- 現在の取得処理はユーザーごとに最初の1体を表示する。
- UI上も1ユーザー1体運用。

### `mini_robot_logs`
最近の反応ログ。

| column | 内容 |
| --- | --- |
| `id` | ログID |
| `user_id` | ユーザーID |
| `mini_robot_id` | ミニロボID |
| `event_type` | `create` / `care` / `observe` / `rename` |
| `message` | 表示文 |
| `payload_json` | 補足JSON |
| `created_at` | 作成時刻 |

保存件数:
- 1体あたり最新10件のみ保持する。
- 11件目以降は古いログを削除する。

## 監査ログ
以下のイベントを `audit_log` 経由で保存する。

| event | タイミング |
| --- | --- |
| `AUDIT_EVENT_TYPES["LAB_MINI_CREATE"]` | ミニロボ作成 |
| `AUDIT_EVENT_TYPES["LAB_MINI_CARE"]` | お世話 |
| `AUDIT_EVENT_TYPES["LAB_MINI_OBSERVE"]` | 観察 |
| `AUDIT_EVENT_TYPES["LAB_MINI_RENAME"]` | 名前変更 |

実験室の世界ログ対象:
- `LAB_MINI_CREATE`
- `LAB_MINI_GROWTH`
- `LAB_MINI_UNLOCK_SPECIES`

現状で実際に発生する主要イベントは `LAB_MINI_CREATE`。  
`LAB_MINI_GROWTH` と `LAB_MINI_UNLOCK_SPECIES` は将来拡張用。

## 公開制御
- release gate: `lab_mini`
- 管理者は非公開中でも閲覧可能。
- 一般ユーザーは `lab_mini` が公開中の場合のみ閲覧可能。
- 非公開中に一般ユーザーが `/lab/mini` へアクセスした場合:
  - `/lab` へリダイレクト
  - `ミニロボ培養室は準備中です。` を表示
  - ミニロボは作成しない
- `/lab` トップの導線も非公開中は表示しない。

公開操作:
- `/admin/release`
- `ミニロボ培養室` を `public` にする。

## バランス影響
- お世話はミニロボ内部値のみ更新する。
- 観察は育成値を更新しない。
- 観察でコイン、パーツ、報酬は付与しない。
- 本編の戦闘、探索、パーツ、進行には影響しない。

## セーフティ
- お世話文はネガティブ表現を避けるテストがある。
- 一般ユーザーには内部性格やシード値を表示しない。
- 管理者メモは `is_admin` の場合のみ表示する。
- 名前は18文字まで。
- 非公開中は一般ユーザーに作成処理を実行させない。

## 受け入れ条件
- 未公開時、一般ユーザーの `/lab` に `ミニロボ培養室` が出ない。
- 未公開時、一般ユーザーが `/lab/mini` にアクセスしてもミニロボが作成されない。
- 管理者は未公開時でも `/lab/mini` を確認できる。
- 公開後、一般ユーザーが `/lab/mini` で3種を選べる。
- 初回選択画面では3種すべての画像、説明、性格の雰囲気が見える。
- 選択後、`user_mini_robots` に1件作成される。
- `/lab/mini/catalog` では所持済みの1体だけ詳細が見える。
- 選ばなかった2体は `未所持` 表示になる。
- 未所持の2体は画像が暗めに表示される。
- 未所持の2体は説明文、性格の雰囲気、状態差分を表示しない。
- 未所持カードには `まだ一緒に過ごしたことがありません。今後の研究で出会えるかもしれません。` を表示する。
- 作成時、`mini_robot_logs` に `create` ログが1件作成される。
- 作成時、内部性格、成長タイプ、挙動シード、進化シード、好きな時間帯が入る。
- お世話1回目で `care_count`、`consecutive_care_days`、内部値が更新される。
- 同日2回目のお世話では値が変わらない。
- 観察は同じ日・同じ時間帯につき表示ログ1件まで。
- 観察ではコイン、パーツ、愛着、元気、信頼、成長度が変わらない。
- 19文字以上の名前は拒否される。
- 一般ユーザーには `管理者メモ` が表示されない。

## テスト
関連テスト:
- `tests/test_lab_mini.py`
- `tests/test_lab_features.py`
- `tests/test_release_gates.py`

確認済みコマンド:

```bash
python3 -m unittest tests.test_lab_mini tests.test_release_gates
```

確認結果:
- 13 tests OK

## 今後の拡張余地
- `growth_exp` による `growth` / `mature` への段階遷移。
- `evolution_seed` を使った進化先分岐。
- `LAB_MINI_GROWTH` の世界ログ発火。
- `LAB_MINI_UNLOCK_SPECIES` による追加種族解放。
- 性格の一般向け表示解放。
- 図鑑の詳細ページ追加。
