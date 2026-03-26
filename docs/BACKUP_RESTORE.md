# バックアップ/復元メモ

最終更新日: 2026-03-26

## 日次バックアップ

バックアップ作成:

```bash
cd /home/ubuntu/robot-game
source venv/bin/activate
python3 manage_backups.py --keep-latest 7
```

保存先:
- `/home/ubuntu/robot-game/backups/`

命名規則:
- `game-YYYYMMDD-HHMMSS.db`

## 復元手順

1. アプリ停止

```bash
sudo systemctl stop robot-game.service
```

2. 現在 DB を退避

```bash
cd /home/ubuntu/robot-game
cp game.db game.db.restore-bak.$(date +%Y%m%d-%H%M%S)
```

3. バックアップを復元

```bash
cp backups/game-YYYYMMDD-HHMMSS.db game.db
```

4. アプリ再起動

```bash
sudo systemctl start robot-game.service
```

5. 動作確認

```bash
curl -I http://127.0.0.1/login
curl -I http://127.0.0.1/healthz
journalctl -u robot-game.service -n 50 --no-pager
```

## 復元時の注意

- 復元直前に `game.db` を必ず別名退避する
- 復元後はログイン、ホーム、管理画面の順で軽く確認する
- 大きな巻き戻し時は、告知や更新履歴でユーザーへ案内する
