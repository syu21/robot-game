import argparse
import json

import app as game_app


def main():
    parser = argparse.ArgumentParser(description="Send online user count to Pochi portal API")
    parser.add_argument(
        "--window-minutes",
        type=int,
        default=None,
        help="Active user window in minutes (default: PORTAL_ONLINE_WINDOW_MINUTES env/app setting)",
    )
    args = parser.parse_args()

    with game_app.app.app_context():
        db = game_app.get_db()
        if args.window_minutes is None:
            result = game_app.send_portal_online_count(db=db)
        else:
            result = game_app.send_portal_online_count(db=db, window_minutes=int(args.window_minutes))

    print(json.dumps(result, ensure_ascii=False))
    # Keep cron/job non-fatal for gameplay operations.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
