# 実験室投稿仕様

最終更新日: 2026-04-21

詳細な採用候補化、権利同意、レーダーチャート、採用運用は `docs/LAB_UGC_ADOPTION_SPEC.md` を正本とする。
この文書は、現行の実験室投稿 v1 の実装要点を短く確認するための運用サマリである。

## 1. 方針
- 見た目投稿として実装
- 本編戦力には影響しない
- 承認制を必須にする
- 本編の `/showcase` は実戦機展示として維持し、実験室展示は創作ロボ / 試作機の文化圏として分離する
- 投稿画像は将来的な本編採用候補の原案になりうるが、そのまま本編アセットや商品にはしない

## 2. 投稿要件
- タイトル必須
- 一言コメント必須
- PNG必須
- 透過必須
- 正方形 96px〜512px
- 最大 1MB
- 利用条件への同意必須
- AI生成利用有無または出所説明を保存できるようにする

## 3. 保存
- 原本: `static/user_lab_uploads/originals/...`
- サムネ: `static/user_lab_uploads/thumbs/...`
- ファイル名はランダム化
- 同意バージョン、同意日時、同意本文スナップショットを保持する
- 採用候補フラグや採用種別は投稿テーブル拡張、または `lab_submission_adoptions` で管理する

## 4. フロー
1. 必要なら `/lab` または `/lab/upload` の `研究所AI` 導線からロボ画像を作る
2. 生成画像を保存し、`/lab/upload` で投稿
3. `pending` 保存
4. `/admin/lab/submissions` で承認 / reject / disable
5. `approved` のみ `/lab/showcase` に公開
6. 必要に応じて feature / 採用候補 / 採用種別を管理者が付与
7. 採用時は運営再構成版として本編側へ実装し、原案クレジットを別管理する

## 5. 公開面
- `/lab/showcase`
  - `新着 / 人気 / 話題 / おすすめ`
- `/lab/showcase/<submission_id>`
  - 画像
  - タイトル
  - コメント
  - 投稿者
  - いいね数
  - 通報
- 将来追加
  - タグ
  - 実験室用レーダーチャート
  - 採用候補 / 実装済み原案バッジ
  - マイ投稿状態確認 `/lab/my-submissions`

## 6. 監査
- `audit.lab.ai_generate.click`
- `audit.lab.submission.create`
- `audit.lab.submission.approve`
- `audit.lab.submission.reject`
- `audit.lab.submission.disable`
- `audit.lab.submission.like`
- `audit.lab.submission.report`
- `audit.lab.submission.feature`
- `audit.lab.submission.adoption_candidate`
- `audit.lab.submission.adoption_update`
