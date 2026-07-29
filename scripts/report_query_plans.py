import json

from perf_harness import isolated_app


QUERIES = [
    ("home_user_events", "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?", (1, "audit.explore.end")),
    ("world_week_events", "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ? AND created_at >= ? AND created_at < ?", ("audit.explore.end", 0, 4102444800)),
    ("chat_world_recent", "SELECT id, user_id, room_key, message, created_at FROM chat_messages WHERE COALESCE(room_key, ?) = ? AND deleted_at IS NULL ORDER BY created_at DESC, id DESC LIMIT ?", ("world", "world", 50)),
    ("part_inventory", "SELECT pi.id, pi.user_id, pi.status, p.key FROM part_instances pi JOIN robot_parts p ON p.id = pi.part_id WHERE pi.user_id = ? AND pi.status = ? ORDER BY pi.id DESC LIMIT ?", (1, "inventory", 50)),
    ("research_tasks", "SELECT * FROM user_research_tasks WHERE user_id = ? AND status IN ('active', 'completed') ORDER BY slot_index ASC, assigned_at ASC, id ASC", (1,)),
]


def main():
    report = []
    with isolated_app() as (game_app, _user_id, _username):
        with game_app.app.app_context():
            db = game_app.get_db()
            for name, sql, params in QUERIES:
                try:
                    rows = db.execute(f"EXPLAIN QUERY PLAN {sql}", params).fetchall()
                    report.append({"name": name, "plan": [dict(row) for row in rows]})
                except Exception as exc:
                    report.append({"name": name, "error": str(exc)})
    print(json.dumps({"queries": report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
