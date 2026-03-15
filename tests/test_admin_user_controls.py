import os
import tempfile
import time
import unittest

from werkzeug.security import generate_password_hash

import app as game_app
import init_db


class AdminUserControlsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
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

    def test_normal_login_rejects_admin_protected(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected)
                VALUES (?, ?, ?, 1, 1)
                """,
                ("protected_admin", generate_password_hash("pw"), now),
            )
            db.commit()
        with game_app.app.test_client() as client:
            resp = client.post(
                "/login",
                data={"username": "protected_admin", "password": "pw"},
                follow_redirects=True,
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIn("このアカウントは通常ログインできません。", resp.get_data(as_text=True))

    def test_admin_login_allows_admin_protected_user(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected)
                VALUES (?, ?, ?, 1, 1)
                """,
                ("admin_only", generate_password_hash("pw"), now),
            )
            db.commit()
        with game_app.app.test_client() as client:
            resp = client.post(
                "/admin/login",
                data={"username": "admin_only", "password": "pw"},
                follow_redirects=False,
            )
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/admin", resp.headers.get("Location", ""))

    def test_banned_user_is_forced_logout_on_next_request(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_banned)
                VALUES (?, ?, ?, 1)
                """,
                ("banned_user", generate_password_hash("pw"), now),
            )
            user_id = db.execute("SELECT id FROM users WHERE username = ?", ("banned_user",)).fetchone()["id"]
            db.commit()
        with game_app.app.test_client() as client:
            self._session_login(client, user_id, "banned_user")
            resp = client.get("/home", follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/login", resp.headers.get("Location", ""))

    def test_admin_cannot_ban_self(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected)
                VALUES (?, ?, ?, 1, 1)
                """,
                ("self_admin", generate_password_hash("pw"), now),
            )
            admin_id = db.execute("SELECT id FROM users WHERE username = ?", ("self_admin",)).fetchone()["id"]
            db.commit()
        with game_app.app.test_client() as client:
            self._session_login(client, admin_id, "self_admin")
            resp = client.post(
                "/admin/users",
                data={"action": "ban", "target_user_id": str(admin_id), "reason": "x"},
                follow_redirects=True,
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIn("自分自身をBANできません。", resp.get_data(as_text=True))

    def test_admin_can_hard_delete_user_and_related_rows(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected)
                VALUES (?, ?, ?, 1, 1)
                """,
                ("delete_admin", generate_password_hash("pw"), now),
            )
            admin_id = int(
                db.execute("SELECT id FROM users WHERE username = ?", ("delete_admin",)).fetchone()["id"]
            )
            db.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                ("delete_target", generate_password_hash("pw"), now),
            )
            target_id = int(
                db.execute("SELECT id FROM users WHERE username = ?", ("delete_target",)).fetchone()["id"]
            )
            db.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                ("ref_other", generate_password_hash("pw"), now),
            )
            other_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("ref_other",)).fetchone()["id"])
            db.execute(
                """
                INSERT INTO user_referrals (referrer_user_id, referred_user_id, referral_code, status, created_at)
                VALUES (?, ?, ?, 'pending', ?)
                """,
                (other_id, target_id, "TEST1234", now),
            )
            part_row = db.execute(
                "SELECT id, key FROM robot_parts WHERE part_type = 'HEAD' ORDER BY id ASC LIMIT 1"
            ).fetchone()
            self.assertIsNotNone(part_row)
            db.execute(
                """
                INSERT INTO part_instances
                (part_id, user_id, rarity, element, series, plus, w_hp, w_atk, w_def, w_spd, w_acc, w_cri, status, created_at, part_type)
                VALUES (?, ?, 'N', 'NORMAL', 'core', 0, 0.2, 0.2, 0.2, 0.15, 0.15, 0.1, 'inventory', ?, 'HEAD')
                """,
                (int(part_row["id"]), target_id, now),
            )
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, 'DeleteMeBot', 'active', ?, ?)
                """,
                (target_id, now, now),
            )
            robot_id = int(
                db.execute("SELECT id FROM robot_instances WHERE user_id = ? ORDER BY id DESC LIMIT 1", (target_id,)).fetchone()["id"]
            )
            db.execute(
                """
                INSERT INTO robot_instance_parts (robot_instance_id, head_key, r_arm_key, l_arm_key, legs_key)
                VALUES (?, ?, ?, ?, ?)
                """,
                (robot_id, part_row["key"], part_row["key"], part_row["key"], part_row["key"]),
            )
            db.execute(
                "INSERT INTO world_events_log (created_at, event_type, payload_json, user_id) VALUES (?, 'audit.explore.end', '{}', ?)",
                (now, target_id),
            )
            db.commit()

        with game_app.app.test_client() as client:
            self._session_login(client, admin_id, "delete_admin")
            resp = client.post(
                f"/admin/users/{target_id}/delete",
                data={"confirm_token": "DELETE"},
                follow_redirects=True,
            )
            self.assertEqual(resp.status_code, 200)
            body = resp.get_data(as_text=True)
            self.assertIn("完全削除しました", body)

        with game_app.app.app_context():
            db = game_app.get_db()
            self.assertIsNone(db.execute("SELECT id FROM users WHERE id = ?", (target_id,)).fetchone())
            self.assertEqual(
                int(
                    db.execute("SELECT COUNT(*) AS c FROM robot_instances WHERE user_id = ?", (target_id,)).fetchone()["c"]
                    or 0
                ),
                0,
            )
            self.assertEqual(
                int(db.execute("SELECT COUNT(*) AS c FROM part_instances WHERE user_id = ?", (target_id,)).fetchone()["c"] or 0),
                0,
            )
            self.assertEqual(
                int(db.execute("SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ?", (target_id,)).fetchone()["c"] or 0),
                0,
            )
            deletion_audit = db.execute(
                "SELECT id FROM world_events_log WHERE event_type = ? AND user_id = ? ORDER BY id DESC LIMIT 1",
                (game_app.AUDIT_EVENT_TYPES["ADMIN_USER_DELETE"], admin_id),
            ).fetchone()
            self.assertIsNotNone(deletion_audit)

    def test_admin_cannot_hard_delete_self_or_main_admin(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected)
                VALUES (?, ?, ?, 1, 1)
                """,
                ("main_admin_case", generate_password_hash("pw"), now),
            )
            admin_id = int(
                db.execute("SELECT id FROM users WHERE username = ?", ("main_admin_case",)).fetchone()["id"]
            )
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected)
                VALUES (?, ?, ?, 1, 1)
                """,
                ("admin", generate_password_hash("pw"), now),
            )
            core_admin_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()["id"])
            db.commit()

        with game_app.app.test_client() as client:
            self._session_login(client, admin_id, "main_admin_case")
            resp_self = client.post(
                f"/admin/users/{admin_id}/delete",
                data={"confirm_token": "DELETE"},
                follow_redirects=True,
            )
            self.assertEqual(resp_self.status_code, 200)
            self.assertIn("自分自身は完全削除できません。", resp_self.get_data(as_text=True))

            resp_main = client.post(
                f"/admin/users/{core_admin_id}/delete",
                data={"confirm_token": "DELETE"},
                follow_redirects=True,
            )
            self.assertEqual(resp_main.status_code, 200)
            self.assertIn("メイン管理者アカウントは完全削除できません。", resp_main.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
