import os
import re
import tempfile
import time
import unittest

from werkzeug.security import generate_password_hash

import app as game_app
import init_db


class AnalyticsSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        game_app.AUTH_RATE_LIMIT_BUCKETS.clear()
        init_db.main()
        game_app.app.config["TESTING"] = True

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _session_login(self, client, user_id, username):
        with client.session_transaction() as sess:
            sess["user_id"] = int(user_id)
            sess["username"] = username

    def _csrf_from(self, html):
        match = re.search(r'name="csrf_token" value="([^"]+)"', html)
        self.assertIsNotNone(match)
        return match.group(1)

    def _create_user(self, db, username, *, is_admin=0, analytics_excluded=0, created_at=None):
        now = int(created_at or time.time())
        db.execute(
            """
            INSERT INTO users
            (username, password_hash, created_at, last_seen_at, is_admin, is_admin_protected, analytics_excluded)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                generate_password_hash("pw"),
                now,
                now,
                int(is_admin),
                int(is_admin),
                int(analytics_excluded),
            ),
        )
        return int(db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"])

    def _insert_event(self, db, user_id, event_type, *, created_at=None, payload=None):
        db.execute(
            """
            INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
            VALUES (?, ?, ?, ?)
            """,
            (
                int(created_at or time.time()),
                event_type,
                game_app.json.dumps(payload or {}, ensure_ascii=False),
                int(user_id),
            ),
        )

    def test_analytics_exclusion_columns_exist(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            cols = {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}
            self.assertIn("analytics_excluded", cols)
            self.assertIn("analytics_excluded_at", cols)
            self.assertIn("analytics_excluded_reason", cols)
            self.assertIn("analytics_excluded_by_user_id", cols)

    def test_admin_can_exclude_user_from_analytics_and_audit(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            admin_id = self._create_user(db, "analytics_admin", is_admin=1)
            target_id = self._create_user(db, "normal_player")
            db.commit()

        with game_app.app.test_client() as client:
            self._session_login(client, admin_id, "analytics_admin")
            csrf = self._csrf_from(client.get("/admin/users").get_data(as_text=True))
            resp = client.post(
                "/admin/users",
                data={
                    "csrf_token": csrf,
                    "action": "analytics_exclude",
                    "target_user_id": str(target_id),
                    "reason": "攻撃スキャン",
                },
                follow_redirects=False,
            )
            self.assertEqual(resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            target = db.execute("SELECT * FROM users WHERE id = ?", (target_id,)).fetchone()
            self.assertEqual(int(target["analytics_excluded"]), 1)
            self.assertEqual(target["analytics_excluded_reason"], "攻撃スキャン")
            self.assertEqual(int(target["analytics_excluded_by_user_id"]), admin_id)
            audit = db.execute(
                """
                SELECT id FROM world_events_log
                WHERE event_type = ? AND entity_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (game_app.AUDIT_EVENT_TYPES["ADMIN_ANALYTICS_EXCLUDE"], target_id),
            ).fetchone()
            self.assertIsNotNone(audit)

    def test_admin_users_post_requires_csrf_after_form_view(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            admin_id = self._create_user(db, "csrf_admin", is_admin=1)
            target_id = self._create_user(db, "csrf_target")
            db.commit()

        with game_app.app.test_client() as client:
            self._session_login(client, admin_id, "csrf_admin")
            self.assertEqual(client.get("/admin/users").status_code, 200)
            resp = client.post(
                "/admin/users",
                data={"action": "analytics_exclude", "target_user_id": str(target_id), "reason": "x"},
            )
            self.assertEqual(resp.status_code, 400)

    def test_real_user_metrics_exclude_admin_test_and_marked_users(self):
        now = int(time.time())
        day_key = game_app.datetime.fromtimestamp(now, game_app.JST).strftime("%Y-%m-%d")
        with game_app.app.app_context():
            db = game_app.get_db()
            normal_id = self._create_user(db, "real_player", created_at=now)
            excluded_id = self._create_user(db, "excluded_player", analytics_excluded=1, created_at=now)
            admin_id = self._create_user(db, "metric_admin", is_admin=1, created_at=now)
            test_id = self._create_user(db, "test_metric", created_at=now)
            for uid in (normal_id, excluded_id, admin_id, test_id):
                self._insert_event(db, uid, game_app.AUDIT_EVENT_TYPES["HOME_VIEW"], created_at=now)
                self._insert_event(
                    db,
                    uid,
                    game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                    created_at=now + 1,
                    payload={"area_key": "layer_1", "result": {"win": True}},
                )
            self._insert_event(db, normal_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_START"], created_at=now + 2, payload={"area_key": "layer_1"})
            self._insert_event(db, normal_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_START"], created_at=now + 3, payload={"area_key": "layer_1"})
            self._insert_event(db, normal_id, game_app.AUDIT_EVENT_TYPES["EXPLORE_RETRY_CLICK"], created_at=now + 4, payload={"area_key": "layer_1"})
            self._insert_event(db, normal_id, game_app.AUDIT_EVENT_TYPES["BATTLE_RESULT_VIEW"], created_at=now + 5)
            db.commit()

            daily = game_app._collect_daily_metrics(db, day_key)
            snapshot = game_app._admin_first_experience_snapshot(db, window_days=7)

        self.assertEqual(daily["dau_count"], 1)
        self.assertEqual(daily["new_users"], 1)
        self.assertEqual(daily["explore_count"], 1)
        self.assertEqual(snapshot["registered_count"], 1)
        by_key = {row["key"]: row for row in snapshot["rows"]}
        self.assertEqual(by_key["layer1_first_win"]["count"], 1)
        self.assertEqual(snapshot["retry_10m"]["numerator"], 1)

    def test_registration_input_defense_detects_blocked_payloads(self):
        with self.assertRaises(game_app.AccountInputError):
            game_app.normalize_account_text("<script>alert(1)</script>", field="username")
        with self.assertRaises(game_app.AccountInputError):
            game_app.normalize_account_text("abc\nxyz", field="username")
        reasons = game_app.detect_suspicious_registration({"username": "x' OR 1=1--"}, {})
        self.assertIn("contains_sql_boolean_combo", reasons)


if __name__ == "__main__":
    unittest.main()
