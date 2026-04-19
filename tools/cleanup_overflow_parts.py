#!/usr/bin/env python3
import argparse
import os
import sys
import uuid


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as game_app  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Sell legacy overflow parts into coins.")
    parser.add_argument("--execute", action="store_true", help="Apply changes. Omit for dry-run.")
    parser.add_argument("--user-id", type=int, default=None, help="Limit cleanup to one user.")
    args = parser.parse_args()

    if args.execute and not game_app.AUTO_SELL_MIGRATION_ENABLED:
        print("AUTO_SELL_MIGRATION_ENABLED=1 is required for --execute.")
        return 2

    with game_app.app.app_context():
        db = game_app.get_db()
        summary = game_app.cleanup_overflow_parts_to_coins(
            db,
            user_id=args.user_id,
            execute=args.execute,
            request_id=f"overflow-cleanup:{uuid.uuid4()}",
        )
        if args.execute:
            db.commit()
        print(
            "execute={execute} users={user_count} parts={sold_count} coins={total_coins}".format(
                **summary
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
