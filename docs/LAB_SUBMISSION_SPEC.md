# 実験室投稿仕様

最終更新日: 2026-03-27

## 1. 方針
- 見た目投稿として実装
- 本編戦力には影響しない
- 承認制を必須にする

## 2. 投稿要件
- タイトル必須
- 一言コメント必須
- PNG必須
- 透過必須
- 正方形 96px〜512px
- 最大 1MB

## 3. 保存
- 原本: `static/user_lab_uploads/originals/...`
- サムネ: `static/user_lab_uploads/thumbs/...`
- ファイル名はランダム化

## 4. フロー
1. `/lab/upload` で投稿
2. `pending` 保存
3. `/admin/lab/submissions` で承認 / reject / disable
4. `approved` のみ `/lab/showcase` に公開

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

## 6. 監査
- `audit.lab.submission.create`
- `audit.lab.submission.approve`
- `audit.lab.submission.reject`
- `audit.lab.submission.disable`
- `audit.lab.submission.like`
- `audit.lab.submission.report`
