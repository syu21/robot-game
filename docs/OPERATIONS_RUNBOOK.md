# 公開後運用ランブック

最終更新日: 2026-03-26

## まず見る場所

- アプリ: `journalctl -u robot-game.service -n 100 --no-pager`
- アプリ追尾: `journalctl -u robot-game.service -f`
- nginx エラー: `sudo tail -n 100 /var/log/nginx/error.log`
- nginx アクセス: `sudo tail -n 100 /var/log/nginx/access.log`
- ヘルス: `curl -i http://127.0.0.1:8000/healthz`
- 公開ヘルス: `curl -I https://robolabo.site/healthz`

## 更新反映後の最低目視

- ログイン後に `/home` を開き、`今週のランキング` と `今週のMVP` に `アイコン+小ロボ` が出るか確認
- ログイン後に `/world` を開き、MVP に機体画像まで出るか確認
- ログイン後に `/records` を開き、初達成記録 / 今週の記録 / 話題ロボに他プレイヤー表示が出るか確認

## 500 エラー時の見る順番

1. `journalctl -u robot-game.service -n 100 --no-pager`
2. `sudo tail -n 100 /var/log/nginx/error.log`
3. `curl -I http://127.0.0.1/login`
4. `curl -i http://127.0.0.1:8000/healthz`
5. `curl -I https://robolabo.site/healthz`
6. 必要なら `sudo systemctl restart robot-game.service`

## 定期確認

- 5 分ごと: `robot-game-healthcheck.timer`
- 5 分ごと: `robot-game-portal-online.timer`
- 毎日: `robot-game-backup.timer`

## ポータル送信確認

```bash
journalctl -u robot-game-portal-online.service -n 50 --no-pager
sqlite3 /home/ubuntu/robot-game/game.db "SELECT id, online_count, status, attempt_count, last_error FROM portal_online_delivery_queue ORDER BY id DESC LIMIT 10;"
/home/ubuntu/robot-game/venv/bin/python3 /home/ubuntu/robot-game/send_online_count.py --flush-limit 20
```

pending が増え続ける場合:
- `.env.production` の `POCHI_PORTAL_*` を確認
- 推奨値:
  - `POCHI_PORTAL_ENDPOINT=https://games-alchemist.com`
  - `POCHI_PORTAL_GAME_KEY=robolabo`
  - `POCHI_PORTAL_API_KEY=<ポータル発行の秘密値>`
- 送信先疎通を確認
- `python3 send_online_count.py --flush-limit 20` を手動実行

## ポータル掲載の外部作業

- ゲーム情報編集: `https://pochi-games.com/pochi-game/portal/edit`
- 開発者 Discord: `https://discord.gg/HvJD7Jx5`
- 情報編集と送信設定が完了したら、あるけみすと公式へ完了報告を送る
  - 編集完了後に宣伝ツイート対応予定

## 秘密情報の事故防止

- 実キーは `.env.production` だけに入れ、コード・docs・コマンド履歴へ貼らない
- `make install-hooks` を実行すると、`.githooks/pre-commit` が有効になり、`.env.production` や実キーっぽい値のコミットを止める
- `git add .` より `git add app.py send_online_count.py ...` のような明示追加を使う
- コミット前に `git diff --cached --name-only` を見て、想定外ファイルがないか確認する

## バックアップ確認

```bash
journalctl -u robot-game-backup.service -n 20 --no-pager
ls -lt /home/ubuntu/robot-game/backups | head
```

## 最低限の復旧コマンド

```bash
sudo systemctl restart robot-game.service
sudo systemctl reload nginx
```
