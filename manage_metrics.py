#!/usr/bin/env python3
import argparse

import app as game_app


def main():
    parser = argparse.ArgumentParser(description="daily_metrics 集計")
    parser.add_argument("--day", default="", help="対象日 (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=7, help="直近日数")
    args = parser.parse_args()

    with game_app.app.app_context():
        db = game_app.get_db()
        if args.day:
            row = game_app._collect_daily_metrics(db, args.day)
            db.commit()
            print(
                f"{row['day_key']} dau={row['dau_count']} new={row['new_users']} explore={row['explore_count']} "
                f"boss_enc={row['boss_encounters']} boss_def={row['boss_defeats']} fuse={row['fuse_count']}"
            )
            return
        rows = game_app._collect_recent_daily_metrics(db, days=args.days)
        db.commit()
        for row in rows:
            print(
                f"{row['day_key']} dau={row['dau_count']} new={row['new_users']} explore={row['explore_count']} "
                f"boss_enc={row['boss_encounters']} boss_def={row['boss_defeats']} fuse={row['fuse_count']}"
            )


if __name__ == "__main__":
    main()
