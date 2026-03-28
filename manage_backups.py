import argparse
import json

import app as game_app


def main():
    parser = argparse.ArgumentParser(description="Create and prune SQLite backups")
    parser.add_argument("--keep-latest", type=int, default=7, help="How many newest backups to keep")
    args = parser.parse_args()

    backup = game_app.create_db_backup()
    pruned = game_app.prune_db_backups(keep_latest=int(args.keep_latest))
    result = {
        "ok": True,
        "created": backup,
        "pruned_count": len(pruned),
        "pruned": [item["name"] for item in pruned],
        "kept_count": len(game_app.list_db_backups()),
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
