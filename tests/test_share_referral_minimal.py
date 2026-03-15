import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class ShareReferralMinimalTests(unittest.TestCase):
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

    def test_register_with_ref_creates_pending_referral(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin) VALUES (?, ?, ?, 0)",
                ("ref_owner", "x", now),
            )
            owner_id = db.execute("SELECT id FROM users WHERE username = 'ref_owner'").fetchone()["id"]
            code = game_app._ensure_user_invite_code(db, owner_id)
            db.commit()

        with game_app.app.test_client() as client:
            resp = client.post(
                f"/register?ref={code}",
                data={"username": "ref_new", "password": "pw"},
                follow_redirects=False,
            )
            self.assertEqual(resp.status_code, 302)

        with game_app.app.app_context():
            db = game_app.get_db()
            new_user = db.execute("SELECT id FROM users WHERE username = 'ref_new'").fetchone()
            self.assertIsNotNone(new_user)
            referral = db.execute(
                "SELECT status FROM user_referrals WHERE referrer_user_id = ? AND referred_user_id = ?",
                (owner_id, int(new_user["id"])),
            ).fetchone()
            self.assertIsNotNone(referral)
            self.assertEqual(referral["status"], "pending")
            audit = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ? AND user_id = ?",
                (game_app.AUDIT_EVENT_TYPES["REFERRAL_ATTACH"], int(new_user["id"])),
            ).fetchone()
            self.assertGreaterEqual(int(audit["c"] or 0), 1)

    def test_referral_becomes_qualified_on_home_when_conditions_met(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin) VALUES (?, ?, ?, 0)",
                ("ref_parent", "x", now),
            )
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin) VALUES (?, ?, ?, 0)",
                ("ref_child", "x", now - 90000),
            )
            referrer_id = db.execute("SELECT id FROM users WHERE username = 'ref_parent'").fetchone()["id"]
            child_id = db.execute("SELECT id FROM users WHERE username = 'ref_child'").fetchone()["id"]
            code = game_app._ensure_user_invite_code(db, referrer_id)
            db.execute(
                """
                INSERT INTO user_referrals (referrer_user_id, referred_user_id, referral_code, status, created_at)
                VALUES (?, ?, ?, 'pending', ?)
                """,
                (referrer_id, child_id, code, now),
            )
            game_app.initialize_new_user(db, child_id)
            for _ in range(10):
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                    VALUES (?, 'audit.explore.end', '{}', ?)
                    """,
                    (now, child_id),
                )
            db.commit()

        with game_app.app.test_client() as client:
            self._session_login(client, child_id, "ref_child")
            resp = client.get("/home")
            self.assertEqual(resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT status, qualified_at FROM user_referrals WHERE referred_user_id = ?",
                (child_id,),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["status"], "qualified")
            self.assertIsNotNone(row["qualified_at"])
            audit = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE event_type = ? AND user_id = ?",
                (game_app.AUDIT_EVENT_TYPES["REFERRAL_QUALIFIED"], child_id),
            ).fetchone()
            self.assertGreaterEqual(int(audit["c"] or 0), 1)

    def test_battle_template_shows_share_button_only_for_boss_victory(self):
        with game_app.app.test_request_context("/battle"):
            html_boss = game_app.render_template(
                "battle.html",
                state={"enemy_name": "x"},
                summary={"is_area_boss": True, "outcome": "勝利", "enemy_name": "Boss", "reward_coin": 0, "drop_items": []},
                explore_mode=True,
                turn_logs=[],
                active_robot={"id": 1, "name": "Alpha"},
                explore_area_key="layer_1",
                explore_area_label="第1層",
                battle_log_mode="collapsed",
                battle_ritual_overlay_enabled=False,
            )
            html_normal = game_app.render_template(
                "battle.html",
                state={"enemy_name": "x"},
                summary={"is_area_boss": False, "outcome": "勝利", "enemy_name": "Mob", "reward_coin": 0, "drop_items": []},
                explore_mode=True,
                turn_logs=[],
                active_robot={"id": 1, "name": "Alpha"},
                explore_area_key="layer_1",
                explore_area_label="第1層",
                battle_log_mode="collapsed",
                battle_ritual_overlay_enabled=False,
            )
        self.assertIn("Xで共有", html_boss)
        self.assertIn("/share/boss", html_boss)
        self.assertNotIn("Xで共有", html_normal)

    def test_share_post_redirects_to_x_and_writes_audit(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin) VALUES (?, ?, ?, 0)",
                ("share_user", "x", now),
            )
            user_id = db.execute("SELECT id FROM users WHERE username = 'share_user'").fetchone()["id"]
            db.execute(
                """
                INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (user_id, "ShareBot", now, now),
            )
            robot_id = db.execute("SELECT id FROM robot_instances WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()["id"]
            db.commit()

        with game_app.app.test_client() as client:
            self._session_login(client, user_id, "share_user")
            resp = client.post(
                "/share/boss",
                data={
                    "enemy_key": "boss_test",
                    "enemy_name": "テストボス",
                    "area_key": "layer_1",
                    "area_label": "第1層",
                    "robot_id": str(robot_id),
                    "robot_name": "ShareBot",
                },
                follow_redirects=False,
            )
            self.assertIn(resp.status_code, (302, 303))
            self.assertIn("x.com/intent/tweet", resp.headers.get("Location", ""))

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (user_id, game_app.AUDIT_EVENT_TYPES["SHARE_CLICK"]),
            ).fetchone()
            self.assertEqual(int(row["c"] or 0), 1)


if __name__ == "__main__":
    unittest.main()
