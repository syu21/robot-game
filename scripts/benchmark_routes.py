import json
import platform
import resource
import time

from perf_harness import DEFAULT_ROUTES, common_parser, isolated_app, logged_in_client, parse_route, request_route, response_metric, summarize


def rss_kb():
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if platform.system() == "Darwin":
        return int(value / 1024)
    return value


def main():
    parser = common_parser("Benchmark local Flask routes against an isolated DB copy.")
    args = parser.parse_args()
    routes = [parse_route(route) for route in args.route] if args.route else DEFAULT_ROUTES
    runs = max(1, int(args.runs))
    report = {"runs": runs, "routes": []}
    with isolated_app() as (game_app, user_id, username):
        client = logged_in_client(game_app, user_id, username)
        for method, path in routes:
            timings = []
            sql_counts = []
            sql_totals = []
            render_times = []
            sizes = []
            failures = 0
            mem_before = rss_kb()
            for _ in range(runs):
                started = time.perf_counter()
                response = request_route(client, method, path)
                elapsed_ms = (time.perf_counter() - started) * 1000
                timings.append(response_metric(response, "X-Robolabo-Elapsed-Ms", elapsed_ms))
                sql_counts.append(response_metric(response, "X-Robolabo-Sql-Count", 0))
                sql_totals.append(response_metric(response, "X-Robolabo-Sql-Total-Ms", 0))
                render_times.append(response_metric(response, "X-Robolabo-Render-Ms", 0))
                sizes.append(response_metric(response, "X-Robolabo-Response-Bytes", len(response.get_data())))
                if int(response.status_code) >= 500:
                    failures += 1
            mem_after = rss_kb()
            report["routes"].append(
                {
                    "method": method,
                    "route": path,
                    "status_last": int(response.status_code),
                    "response_ms": summarize(timings),
                    "sql_count": summarize(sql_counts),
                    "sql_total_ms": summarize(sql_totals),
                    "render_ms": summarize(render_times),
                    "response_bytes": summarize(sizes),
                    "failure_count": failures,
                    "memory_rss_delta_kb": int(mem_after - mem_before),
                    "db_lock_wait_ms": 0,
                    "image_generation_ms": 0,
                    "python_processing_ms": 0,
                }
            )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
