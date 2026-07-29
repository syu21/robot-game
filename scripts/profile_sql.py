import json

from perf_harness import common_parser, isolated_app, logged_in_client, parse_route, request_route, response_metric


def main():
    parser = common_parser("Profile SQL metrics for one or more local Flask routes.")
    args = parser.parse_args()
    routes = [parse_route(route) for route in args.route] if args.route else [("GET", "/home")]
    report = {"routes": []}
    with isolated_app() as (game_app, user_id, username):
        client = logged_in_client(game_app, user_id, username)
        for method, path in routes:
            response = request_route(client, method, path)
            report["routes"].append(
                {
                    "method": method,
                    "route": path,
                    "status": int(response.status_code),
                    "elapsed_ms": response_metric(response, "X-Robolabo-Elapsed-Ms", 0),
                    "sql_count": response_metric(response, "X-Robolabo-Sql-Count", 0),
                    "sql_total_ms": response_metric(response, "X-Robolabo-Sql-Total-Ms", 0),
                    "slow_sql_count": response_metric(response, "X-Robolabo-Slow-Sql-Count", 0),
                    "render_ms": response_metric(response, "X-Robolabo-Render-Ms", 0),
                    "response_bytes": response_metric(response, "X-Robolabo-Response-Bytes", 0),
                }
            )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
