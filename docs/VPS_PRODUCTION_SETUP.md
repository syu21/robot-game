# VPS 本番化手順

最終更新日: 2026-03-20

`ロボらぼ` を VPS 上で常用する場合は、確認用の `flask run` ではなく `gunicorn + systemd + nginx` で起動します。

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

運用メモ:
- HTTPS 未導入の間は `SESSION_COOKIE_SECURE=0`
- HTTPS 導入後は `SESSION_COOKIE_SECURE=1`

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

## 5. 確認コマンド

```bash
curl -I http://127.0.0.1:8000/login
curl -I http://127.0.0.1/login
systemctl status robot-game.service --no-pager
systemctl status nginx.service --no-pager
journalctl -u robot-game.service -n 100 --no-pager
```

期待値:
- `127.0.0.1:8000` は `gunicorn`
- `127.0.0.1` は `nginx`
- `/login` は `200`
- `/home` は未ログインなら `302`

## 6. 敵/装飾の有効化フラグ

起動時シードは画像や名称などのマスタ更新だけを行い、`is_active` は既存値を保持します。

そのため:
- 管理画面で敵を無効化しても、次回リクエストや再起動で勝手に有効へ戻りません
- 装飾アセットの有効/無効も同様に保持されます
