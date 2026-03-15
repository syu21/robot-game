import json

import app as game_app


def main():
    with game_app.app.app_context():
        db = game_app.get_db()
        result = game_app.send_portal_online_count(db=db)
    print(json.dumps(result, ensure_ascii=False))
    # Keep cron/job non-fatal for game operations.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
