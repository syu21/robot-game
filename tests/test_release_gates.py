import json
import os
import tempfile
import time
import unittest
from unittest import mock

import app as game_app
import init_db


class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        init_db.main()
        game_app.app.config["TESTING"] = True
        game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = False

        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 0, 0, 20, 5)
                """,
                ("release_user", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("release_user",)).fetchone()["id"])
            game_app.initialize_new_user(db, self.user_id)
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, is_admin_protected, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 1, 1, 20, 5)
                """,
                ("release_admin", "x", now),
            )
            self.admin_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("release_admin",)).fetchone()["id"])
            game_app.initialize_new_user(db, self.admin_id)
            db.commit()

    def tearDown(self):
        game_app.app.config.pop("BYPASS_RELEASE_GATES_IN_TESTS", None)
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self, *, admin=False):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            if admin:
                session["user_id"] = self.admin_id
                session["username"] = "release_admin"
            else:
                session["user_id"] = self.user_id
                session["username"] = "release_user"
        return client

    def test_lab_is_hidden_for_public_until_released(self):
        user_client = self._client()
        admin_client = self._client(admin=True)

        hidden = user_client.get("/lab", follow_redirects=False)
        self.assertEqual(hidden.status_code, 302)
        self.assertIn("/home", hidden.headers.get("Location", ""))

        visible_for_admin = admin_client.get("/lab")
        self.assertEqual(visible_for_admin.status_code, 200)

        home = user_client.get("/home")
        self.assertEqual(home.status_code, 200)
        html = home.get_data(as_text=True)
        self.assertNotIn("実験室", html)

    def test_layer4_and_layer5_are_hidden_until_released(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT id, is_admin, max_unlocked_layer FROM users WHERE id = ?", (self.user_id,)).fetchone()
            admin = db.execute("SELECT id, is_admin, max_unlocked_layer FROM users WHERE id = ?", (self.admin_id,)).fetchone()
            self.assertFalse(game_app._is_area_unlocked(user, "layer_4_forge", db=db))
            self.assertFalse(game_app._is_area_unlocked(user, "layer_5_labyrinth", db=db))
            self.assertTrue(game_app._is_area_unlocked(admin, "layer_4_forge", db=db))
            self.assertTrue(game_app._is_area_unlocked(admin, "layer_5_labyrinth", db=db))

    def test_admin_can_toggle_release_flags_and_dependencies(self):
        admin_client = self._client(admin=True)
        user_client = self._client()

        resp = admin_client.post(
            "/admin/release",
            data={"feature_key": "lab", "state": "public"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("一般公開しました", resp.get_data(as_text=True))
        self.assertEqual(user_client.get("/lab").status_code, 200)

        admin_client.post(
            "/admin/release",
            data={"feature_key": "layer5", "state": "public"},
            follow_redirects=True,
        )
        with game_app.app.app_context():
            db = game_app.get_db()
            flags = {
                row["key"]: int(row["is_public"] or 0)
                for row in db.execute("SELECT key, is_public FROM release_flags").fetchall()
            }
            self.assertEqual(flags.get("layer4"), 1)
            self.assertEqual(flags.get("layer5"), 1)
            user = db.execute("SELECT id, is_admin, max_unlocked_layer FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertTrue(game_app._is_area_unlocked(user, "layer_4_forge", db=db))
            self.assertTrue(game_app._is_area_unlocked(user, "layer_5_labyrinth", db=db))

        admin_client.post(
            "/admin/release",
            data={"feature_key": "layer4", "state": "private"},
            follow_redirects=True,
        )
        with game_app.app.app_context():
            db = game_app.get_db()
            flags = {
                row["key"]: int(row["is_public"] or 0)
                for row in db.execute("SELECT key, is_public FROM release_flags").fetchall()
            }
            self.assertEqual(flags.get("layer4"), 0)
            self.assertEqual(flags.get("layer5"), 0)
            self.assertEqual(flags.get("battle_short_replay"), 0)

    def test_battle_short_replay_is_admin_only_until_released(self):
        user_client = self._client()
        admin_client = self._client(admin=True)

        user_resp = user_client.post("/explore", data={"area_key": "layer_1"})
        self.assertEqual(user_resp.status_code, 200)
        self.assertNotIn('id="battle-short-replay"', user_resp.get_data(as_text=True))

        admin_resp = admin_client.post("/explore", data={"area_key": "layer_1"})
        self.assertEqual(admin_resp.status_code, 200)
        self.assertIn('id="battle-short-replay"', admin_resp.get_data(as_text=True))

        toggle = admin_client.post(
            "/admin/release",
            data={"feature_key": "battle_short_replay", "state": "public"},
            follow_redirects=True,
        )
        self.assertEqual(toggle.status_code, 200)
        self.assertIn("一般公開しました", toggle.get_data(as_text=True))

        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE battle_state SET last_action_at = 0 WHERE user_id = ?", (self.user_id,))
            db.commit()

        user_after = user_client.post("/explore", data={"area_key": "layer_1"})
        self.assertEqual(user_after.status_code, 200)
        self.assertIn('id="battle-short-replay"', user_after.get_data(as_text=True))

    def test_weekly_champion_is_admin_only_until_released(self):
        user_client = self._client()
        admin_client = self._client(admin=True)

        user_home = user_client.get("/home")
        self.assertEqual(user_home.status_code, 200)
        self.assertNotIn("今週のチャンプ機体", user_home.get_data(as_text=True))

        admin_home = admin_client.get("/home")
        self.assertEqual(admin_home.status_code, 200)
        self.assertIn("今週のチャンプ機体", admin_home.get_data(as_text=True))

        hidden = user_client.get("/champion", follow_redirects=False)
        self.assertEqual(hidden.status_code, 302)
        self.assertIn("/home", hidden.headers.get("Location", ""))

        visible_for_admin = admin_client.get("/champion")
        self.assertEqual(visible_for_admin.status_code, 200)
        self.assertIn("今週のチャンプ機体", visible_for_admin.get_data(as_text=True))

        toggle = admin_client.post(
            "/admin/release",
            data={"feature_key": "weekly_champion", "state": "public"},
            follow_redirects=True,
        )
        self.assertEqual(toggle.status_code, 200)
        self.assertIn("一般公開しました", toggle.get_data(as_text=True))

        user_home_after = user_client.get("/home")
        self.assertEqual(user_home_after.status_code, 200)
        self.assertIn("今週のチャンプ機体", user_home_after.get_data(as_text=True))

        user_champion_after = user_client.get("/champion")
        self.assertEqual(user_champion_after.status_code, 200)
        self.assertIn("今週のチャンプ機体", user_champion_after.get_data(as_text=True))

    def test_weekly_champion_public_release_resets_private_test_records(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    now,
                    game_app.AUDIT_EVENT_TYPES["BOSS_DEFEAT"],
                    json.dumps({}, ensure_ascii=False),
                    self.user_id,
                ),
            )
            db.commit()

        admin_client = self._client(admin=True)
        mocked_battle = {
            "win": False,
            "outcome": "敗北",
            "timeout": False,
            "timeout_decision": None,
            "turn_count": 2,
            "turn_logs": [],
            "summary_heading": "今回の崩れ筋",
            "summary_label": "届かなかった",
            "result_label": "LOSE",
            "headline": "チャンプには届かなかった",
            "subline": "今回は届かなかった。もう少し育てて再挑戦しよう。",
            "critical_hits": 0,
        }
        with mock.patch.object(game_app, "run_champion_battle", return_value=mocked_battle):
            with mock.patch.object(game_app, "_battle_short_replay_open_for_viewer", return_value=False):
                resp = admin_client.post("/champion/challenge")
        self.assertEqual(resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            before_battles = int(
                db.execute("SELECT COUNT(*) AS c FROM weekly_champion_battles").fetchone()["c"] or 0
            )
            snapshot = db.execute(
                "SELECT challenge_count, win_count, loss_count FROM weekly_champion_snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertEqual(before_battles, 1)
        self.assertEqual(int(snapshot["challenge_count"] or 0), 1)
        self.assertEqual(int(snapshot["win_count"] or 0), 1)
        self.assertEqual(int(snapshot["loss_count"] or 0), 0)

        toggle = admin_client.post(
            "/admin/release",
            data={"feature_key": "weekly_champion", "state": "public"},
            follow_redirects=True,
        )
        self.assertEqual(toggle.status_code, 200)
        self.assertIn("一般公開しました", toggle.get_data(as_text=True))
        self.assertIn("公開前のチャンプ挑戦 1 件をリセットしました。", toggle.get_data(as_text=True))

        with game_app.app.app_context():
            db = game_app.get_db()
            after_battles = int(
                db.execute("SELECT COUNT(*) AS c FROM weekly_champion_battles").fetchone()["c"] or 0
            )
            snapshot = db.execute(
                "SELECT challenge_count, win_count, loss_count FROM weekly_champion_snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertEqual(after_battles, 0)
        self.assertEqual(int(snapshot["challenge_count"] or 0), 0)
        self.assertEqual(int(snapshot["win_count"] or 0), 0)
        self.assertEqual(int(snapshot["loss_count"] or 0), 0)

    def test_records_hide_unreleased_layer_records(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    now,
                    game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                    json.dumps({"area_key": "layer_4_forge"}, ensure_ascii=False),
                    self.user_id,
                ),
            )
            db.commit()

        user_client = self._client()
        hidden = user_client.get("/records")
        self.assertEqual(hidden.status_code, 200)
        self.assertNotIn("第四層", hidden.get_data(as_text=True))

        admin_client = self._client(admin=True)
        admin_client.post(
            "/admin/release",
            data={"feature_key": "layer4", "state": "public"},
            follow_redirects=True,
        )
        visible = user_client.get("/records")
        self.assertEqual(visible.status_code, 200)
        self.assertIn("第四層", visible.get_data(as_text=True))
