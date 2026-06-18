import json
import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class FactionChangeTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        init_db.main()
        game_app.app.config["TESTING"] = True

        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 0, 0, 1)
                """,
                ("faction_tester", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("faction_tester",)).fetchone()["id"])
            game_app.initialize_new_user(db, self.user_id)
            for idx in range(3):
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        now + idx,
                        game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                        json.dumps({"area_key": "layer_1"}, ensure_ascii=False),
                        self.user_id,
                    ),
                )
            db.execute(
                """
                INSERT INTO world_events_log (created_at, event_type, payload_json, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    now + 10,
                    game_app.AUDIT_EVENT_TYPES["FUSE"],
                    json.dumps({"success": True}, ensure_ascii=False),
                    self.user_id,
                ),
            )
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "faction_tester"
        return client

    def _set_faction(self, faction, changed_at):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                "UPDATE users SET faction = ?, faction_changed_at = ? WHERE id = ?",
                (faction, changed_at, self.user_id),
            )
            db.commit()

    def _user_faction_row(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            return db.execute("SELECT faction, faction_changed_at FROM users WHERE id = ?", (self.user_id,)).fetchone()

    def test_unassigned_user_can_choose_faction_and_timestamp_is_set(self):
        resp = self._client().post("/faction/change", data={"selected_faction": "ignis"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        row = self._user_faction_row()
        self.assertEqual(row["faction"], "ignis")
        self.assertTrue(row["faction_changed_at"])

    def test_user_cannot_change_faction_within_cooldown(self):
        self._set_faction("ignis", game_app.now_str())
        resp = self._client().post("/faction/change", data={"selected_faction": "ventra"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("陣営変更は", resp.get_data(as_text=True))
        self.assertEqual(self._user_faction_row()["faction"], "ignis")

    def test_user_can_change_faction_after_cooldown_and_audit_is_logged(self):
        old_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 8 * 86400))
        self._set_faction("ignis", old_time)
        resp = self._client().post("/faction/change", data={"selected_faction": "ventra"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._user_faction_row()["faction"], "ventra")
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT payload_json FROM world_events_log WHERE event_type = ? AND user_id = ? ORDER BY id DESC LIMIT 1",
                (game_app.AUDIT_EVENT_TYPES["FACTION_CHANGE"], self.user_id),
            ).fetchone()
            self.assertIsNotNone(row)
            payload = json.loads(row["payload_json"])
            self.assertEqual(payload["before_faction"], "ignis")
            self.assertEqual(payload["after_faction"], "ventra")

    def test_same_or_invalid_faction_is_rejected(self):
        old_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 8 * 86400))
        self._set_faction("ignis", old_time)
        client = self._client()
        same = client.post("/faction/change", data={"selected_faction": "ignis"}, follow_redirects=True)
        invalid = client.post("/faction/change", data={"selected_faction": "orix"}, follow_redirects=True)
        self.assertEqual(same.status_code, 200)
        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(self._user_faction_row()["faction"], "ignis")

    def test_faction_counts_and_minority_keys(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute("UPDATE users SET faction = 'ignis' WHERE id = ?", (self.user_id,))
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, faction) VALUES (?, ?, ?, ?)",
                ("ventra_one", "x", now, "ventra"),
            )
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, faction) VALUES (?, ?, ?, ?)",
                ("ventra_two", "x", now, "ventra"),
            )
            db.commit()
            counts = game_app.get_faction_counts(db)
            self.assertEqual(counts["ignis"], 1)
            self.assertEqual(counts["ventra"], 2)
            self.assertEqual(counts["aurix"], 0)
            self.assertEqual(game_app._faction_minority_keys(counts), {"aurix"})
            self.assertEqual(game_app._faction_minority_keys({"ignis": 1, "ventra": 1, "aurix": 1}), set())

    def test_comms_empty_post_uses_custom_message(self):
        client = self._client()
        resp = client.post("/comms/world", data={"message": "   "}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("通信文を入力してください。", resp.get_data(as_text=True))
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute("SELECT COUNT(*) AS c FROM chat_messages WHERE user_id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(row["c"] or 0), 0)
