import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class BaseVisitTests(unittest.TestCase):
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
            for username in ("viewer_user", "base_user"):
                db.execute(
                    """
                    INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer, coins)
                    VALUES (?, ?, ?, 0, 0, 1, 0)
                    """,
                    (username, "x", now),
                )
            self.viewer_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("viewer_user",)).fetchone()["id"])
            self.base_user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("base_user",)).fetchone()["id"])
            game_app.ensure_factory_cosmetics(db, self.base_user_id)
            game_app.ensure_user_factory_facilities(db, self.base_user_id)
            game_app.ensure_companions(db, self.base_user_id)
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self, user_id=None, username="viewer_user"):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = user_id or self.viewer_id
            session["username"] = username
        return client

    def test_base_visit_shows_other_user_base(self):
        html = self._client().get(f"/base/{self.base_user_id}").get_data(as_text=True)
        self.assertIn("base_user の研究基地", html)
        self.assertIn("通常研究所", html)
        self.assertIn("回収ペットロボ", html)
        self.assertIn("工場概要", html)
        self.assertIn("いいね", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            event = db.execute(
                "SELECT id FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (self.viewer_id, game_app.AUDIT_EVENT_TYPES["BASE_VIEW"]),
            ).fetchone()
            self.assertIsNotNone(event)

    def test_self_base_disables_like(self):
        html = self._client(user_id=self.viewer_id).get(f"/base/{self.viewer_id}").get_data(as_text=True)
        self.assertIn("自分の基地", html)
        response = self._client(user_id=self.viewer_id).post(f"/base/{self.viewer_id}/like", follow_redirects=True)
        self.assertIn("自分の基地にはいいねできません", response.get_data(as_text=True))

    def test_missing_user_shows_not_found_message(self):
        html = self._client().get("/base/999999").get_data(as_text=True)
        self.assertIn("基地が見つかりません", html)

    def test_dispatch_status_is_visible(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            result = game_app.start_companion_dispatch(db, self.base_user_id, "short_patrol")
            self.assertTrue(result["ok"])
        html = self._client().get(f"/base/{self.base_user_id}").get_data(as_text=True)
        self.assertIn("相棒ロボ派遣中", html)

    def test_like_once_and_audit(self):
        client = self._client()
        response = client.post(f"/base/{self.base_user_id}/like", follow_redirects=True)
        html = response.get_data(as_text=True)
        self.assertIn("基地にいいねしました", html)
        self.assertIn("<b>1</b>", html)
        duplicate = client.post(f"/base/{self.base_user_id}/like", follow_redirects=True)
        self.assertIn("この基地はいいね済みです", duplicate.get_data(as_text=True))
        with game_app.app.app_context():
            db = game_app.get_db()
            count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM user_base_likes WHERE base_user_id = ? AND liked_by_user_id = ?",
                    (self.base_user_id, self.viewer_id),
                ).fetchone()["c"]
            )
            self.assertEqual(count, 1)
            event = db.execute(
                "SELECT id FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (self.viewer_id, game_app.AUDIT_EVENT_TYPES["BASE_LIKE"]),
            ).fetchone()
            self.assertIsNotNone(event)


if __name__ == "__main__":
    unittest.main()
