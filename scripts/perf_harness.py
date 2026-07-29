import argparse
import contextlib
import os
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_ROUTES = [
    ("GET", "/register"),
    ("GET", "/home"),
    ("GET", "/explore"),
    ("POST", "/explore"),
    ("GET", "/parts"),
    ("GET", "/parts/strengthen"),
    ("GET", "/parts/evolve"),
    ("GET", "/build"),
    ("GET", "/robots"),
    ("GET", "/ranking"),
    ("GET", "/world"),
    ("GET", "/records"),
    ("GET", "/showcase"),
    ("GET", "/comms"),
    ("GET", "/comms/world"),
    ("GET", "/comms/rooms"),
    ("GET", "/comms/personal"),
    ("GET", "/research"),
    ("GET", "/research/parts"),
    ("GET", "/research/series"),
    ("GET", "/research/enemies"),
    ("GET", "/research/bosses"),
    ("GET", "/research/designs"),
    ("GET", "/research/records"),
    ("GET", "/lab"),
    ("GET", "/lab/race"),
    ("GET", "/admin"),
    ("GET", "/admin/audit"),
]


def parse_route(value):
    value = str(value or "").strip()
    if " " in value:
        method, path = value.split(None, 1)
        return method.upper(), path.strip()
    return "GET", value


def percentile(values, pct):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * (pct / 100.0)))
    return float(ordered[max(0, min(index, len(ordered) - 1))])


def summarize(values):
    if not values:
        return {"min": 0, "median": 0, "p95": 0, "max": 0}
    return {
        "min": round(min(values), 3),
        "median": round(statistics.median(values), 3),
        "p95": round(percentile(values, 95), 3),
        "max": round(max(values), 3),
    }


@contextlib.contextmanager
def isolated_app():
    os.environ.setdefault("PERF_DIAGNOSTICS", "1")
    os.environ.setdefault("PERF_SLOW_REQUEST_MS", "1000000")
    import app as game_app
    import init_db

    original_db_path = game_app.DB_PATH
    original_init_db_path = init_db.DB_PATH
    with tempfile.TemporaryDirectory(prefix="robolabo-perf-") as tmpdir:
        temp_db = Path(tmpdir) / "game.db"
        source_db = Path(original_db_path)
        if source_db.exists():
            src = sqlite3.connect(str(source_db))
            dst = sqlite3.connect(str(temp_db))
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
        else:
            temp_db.touch()
        try:
            game_app.DB_PATH = str(temp_db)
            init_db.DB_PATH = str(temp_db)
            game_app.app.config["TESTING"] = True
            with game_app.app.app_context():
                init_db.main()
                db = game_app.get_db()
                now = int(time.time())
                db.execute(
                    """
                    INSERT OR IGNORE INTO users
                        (username, password_hash, created_at, max_unlocked_layer, lab_level, lab_exp, lab_total_exp, is_admin)
                    VALUES ('perf_bench_user', 'x', ?, 7, 1, 0, 0, 1)
                    """,
                    (now,),
                )
                user = db.execute("SELECT id, username FROM users WHERE username = 'perf_bench_user'").fetchone()
                db.commit()
                user_id = int(user["id"])
                username = str(user["username"])
            yield game_app, user_id, username
        finally:
            game_app.DB_PATH = original_db_path
            init_db.DB_PATH = original_init_db_path


def logged_in_client(game_app, user_id, username):
    client = game_app.app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = int(user_id)
        sess["username"] = username
    return client


def request_route(client, method, path):
    if method.upper() == "POST" and path == "/explore":
        return client.post(path, data={"area_key": "layer_1"}, follow_redirects=False)
    return client.open(path, method=method.upper(), follow_redirects=False)


def response_metric(response, header, default=0.0):
    try:
        return float(response.headers.get(header, default) or default)
    except (TypeError, ValueError):
        return float(default)


def common_parser(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--route", action="append", help="Route path, or 'METHOD /path'. Can be repeated.")
    parser.add_argument("--runs", type=int, default=30)
    return parser
