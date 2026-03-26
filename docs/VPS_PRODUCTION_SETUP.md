# VPS 本番化手順

最終更新日: 2026-03-26

`ロボらぼ` を VPS 上で常用する場合は、確認用の `flask run` ではなく `gunicorn + systemd + nginx` で起動します。

現行の公開実績:
- 公開URL: `https://robolabo.site`
- 法務ページ: `/terms`, `/privacy`
- お問い合わせ: `/contact`
- 監視/公開確認: `/healthz`, `/sitemap.xml`
- ログイン後の主要見返し面: `/home`, `/world`, `/records`

## 1. 事前準備

```bash
cd /home/ubuntu/robot-game
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 init_db.py
```

補足:
- ローカルで `.venv` を使っていても、VPS 側は `venv` でも問題ありません。
- `SECRET_KEY` は開発用既定値のまま使わず、必ず本番用に差し替えてください。

## 2. 環境変数ファイル

```bash
cp deploy/systemd/robot-game.env.example /home/ubuntu/robot-game/.env.production
nano /home/ubuntu/robot-game/.env.production
```

最低限ここを変更します。
- `SECRET_KEY`
- `PUBLIC_GAME_URL`
- `SESSION_COOKIE_SECURE`
- `HEALTHCHECK_URL`
- `POCHI_PORTAL_ENDPOINT`
- `POCHI_PORTAL_GAME_KEY`
- `POCHI_PORTAL_API_KEY`

運用メモ:
- HTTPS 未導入の間は `SESSION_COOKIE_SECURE=0`
- HTTPS 導入後は `SESSION_COOKIE_SECURE=1`
- 独自ドメイン運用時は以下を推奨:
  - `PUBLIC_GAME_URL=https://robolabo.site`
  - `SESSION_COOKIE_SECURE=1`
  - `HEALTHCHECK_URL=https://robolabo.site/healthz`
- ポチゲーポータル連携は 2026-03-22 の案内に合わせて以下を設定:
  - `POCHI_PORTAL_ENDPOINT=https://games-alchemist.com`
  - `POCHI_PORTAL_GAME_KEY=robolabo`
  - `POCHI_PORTAL_API_KEY` は発行された秘密値を設定し、Git へ入れない

## 3. systemd サービス

```bash
sudo cp deploy/systemd/robot-game.service.example /etc/systemd/system/robot-game.service
sudo nano /etc/systemd/system/robot-game.service
```

確認する項目:
- `User`
- `Group`
- `WorkingDirectory`
- `EnvironmentFile`
- `ExecStart`

反映:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now robot-game.service
sudo systemctl status robot-game.service --no-pager
```

## 4. nginx リバースプロキシ

```bash
sudo cp deploy/nginx/robot-game.conf.example /etc/nginx/sites-available/robot-game.conf
sudo ln -sf /etc/nginx/sites-available/robot-game.conf /etc/nginx/sites-enabled/robot-game.conf
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

必要に応じて `server_name` を IP または独自ドメインに変更してください。
静的ファイルは `nginx` 直配信ではなく `gunicorn` 側へ透過プロキシする構成です。

## 5. 確認コマンド

```bash
curl -I http://127.0.0.1:8000/login
curl -I http://127.0.0.1/login
curl -I https://robolabo.site/login
curl -I https://robolabo.site/sitemap.xml
systemctl status robot-game.service --no-pager
systemctl status nginx.service --no-pager
journalctl -u robot-game.service -n 100 --no-pager
```

期待値:
- `127.0.0.1:8000` は `gunicorn`
- `127.0.0.1` は `nginx`
- `/login` は `200`
- `/home` は未ログインなら `302`
- `/sitemap.xml` は `200` かつ `application/xml`
- `robot-game.service` 再起動直後は一時的に `502` が見えることがあるため、数秒置いて再確認する
- ログイン後は `/home`, `/world`, `/records` を目視し、ランキング/MVP/記録面の他プレイヤー表示が崩れていないか確認する

## 6. ポータル送信の 5 分ジョブ

```bash
sudo cp deploy/systemd/robot-game-portal-online.service.example /etc/systemd/system/robot-game-portal-online.service
sudo cp deploy/systemd/robot-game-portal-online.timer.example /etc/systemd/system/robot-game-portal-online.timer
sudo systemctl daemon-reload
sudo systemctl enable --now robot-game-portal-online.timer
systemctl status robot-game-portal-online.timer --no-pager
journalctl -u robot-game-portal-online.service -n 20 --no-pager
/home/ubuntu/robot-game/venv/bin/python3 /home/ubuntu/robot-game/send_online_count.py --flush-limit 20
sqlite3 /home/ubuntu/robot-game/game.db "SELECT id, online_count, status, attempt_count, last_error FROM portal_online_delivery_queue ORDER BY id DESC LIMIT 10;"
```

補足:
- ポータル側の登録条件は「ゲーム側で測定した同時接続数を 5 分ごとに送信すること」
- 失敗した送信は DB の `portal_online_delivery_queue` に積まれます
- 次回ジョブで古い pending を先に再送します
- `POCHI_PORTAL_ENDPOINT` は `https://games-alchemist.com` のようなベース URL でも、`/api/portal/online-count` 付きでも動く実装です

## 7. 毎日バックアップ

```bash
sudo cp deploy/systemd/robot-game-backup.service.example /etc/systemd/system/robot-game-backup.service
sudo cp deploy/systemd/robot-game-backup.timer.example /etc/systemd/system/robot-game-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable --now robot-game-backup.timer
systemctl status robot-game-backup.timer --no-pager
journalctl -u robot-game-backup.service -n 20 --no-pager
```

補足:
- `backups/` に日次バックアップを作成します
- 最新 7 件だけ残し、それ以前は自動で削除します

## 8. 最低監視

```bash
sudo cp deploy/systemd/robot-game-healthcheck.service.example /etc/systemd/system/robot-game-healthcheck.service
sudo cp deploy/systemd/robot-game-healthcheck.timer.example /etc/systemd/system/robot-game-healthcheck.timer
sudo systemctl daemon-reload
sudo systemctl enable --now robot-game-healthcheck.timer
systemctl status robot-game-healthcheck.timer --no-pager
journalctl -u robot-game-healthcheck.service -n 20 --no-pager
curl -I http://127.0.0.1/healthz
```

`HEALTHCHECK_URL` を独自ドメインにしておくと、外向き URL の監視にも使えます。

## 9. 敵/装飾の有効化フラグ

起動時シードは画像や名称などのマスタ更新だけを行い、`is_active` は既存値を保持します。

そのため:
- 管理画面で敵を無効化しても、次回リクエストや再起動で勝手に有効へ戻りません
- 装飾アセットの有効/無効も同様に保持されます
