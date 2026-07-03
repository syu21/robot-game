import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class BaseRankingTests(unittest.TestCase):
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
            self.viewer_id = self._create_user(db, "viewer_user", now)
            self.alpha_id = self._create_user(db, "alpha_base", now)
            self.beta_id = self._create_user(db, "beta_base", now)
            self.banned_id = self._create_user(db, "banned_base", now, is_banned=1)
            self.liker_one_id = self._create_user(db, "liker_one", now)
            self.liker_two_id = self._create_user(db, "liker_two", now)
            for user_id in (self.alpha_id, self.beta_id):
                game_app.ensure_companions(db, user_id)
                game_app.ensure_companion_album_photos(db, user_id=user_id)
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _create_user(self, db, username, now, *, is_banned=0):
        db.execute(
            """
            INSERT INTO users (username, password_hash, created_at, is_admin, is_banned, wins, max_unlocked_layer, coins)
            VALUES (?, ?, ?, 0, ?, 0, 1, 0)
            """,
            (username, "x", now, int(is_banned)),
        )
        return int(db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"])

    def _client(self, user_id=None, username="viewer_user"):
        client = game_app.app.test_client()
        if user_id:
            with client.session_transaction() as session:
                session["user_id"] = int(user_id)
                session["username"] = username
        return client

    def _insert_like(self, db, base_user_id, liked_by_user_id, created_at):
        db.execute(
            """
            INSERT INTO user_base_likes (base_user_id, liked_by_user_id, created_at)
            VALUES (?, ?, ?)
            """,
            (int(base_user_id), int(liked_by_user_id), int(created_at)),
        )

    def _seed_likes(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            week_start_ts, _ = game_app._base_ranking_week_start_ts(now)
            old_ts = int(week_start_ts) - 86400
            self._insert_like(db, self.alpha_id, self.viewer_id, now)
            self._insert_like(db, self.alpha_id, self.liker_one_id, now)
            self._insert_like(db, self.beta_id, self.viewer_id, old_ts)
            self._insert_like(db, self.banned_id, self.liker_two_id, now)
            db.commit()

    def test_base_ranking_is_public(self):
        response = self._client().get("/base/ranking")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("基地いいねランキング", html)
        self.assertIn("今週の話題基地", html)
        self.assertIn("累計人気基地", html)

    def test_empty_ranking_message(self):
        html = self._client().get("/base/ranking").get_data(as_text=True)
        self.assertIn("まだ基地いいねはありません", html)
        self.assertIn("気になる基地を見つけていいねしてみよう", html)

    def test_total_and_weekly_rankings_show_base_links(self):
        self._seed_likes()
        html = self._client().get("/base/ranking").get_data(as_text=True)
        self.assertIn("alpha_base", html)
        self.assertIn(f"/base/{self.alpha_id}", html)
        self.assertIn("beta_base", html)
        self.assertIn(f"/base/{self.beta_id}", html)
        self.assertIn("2", html)
        self.assertIn("0 / 5", html)

    def test_navigation_links_point_to_base_ranking(self):
        html = self._client(user_id=self.viewer_id).get("/base/999999").get_data(as_text=True)
        self.assertIn("話題の基地へ", html)
        self.assertIn('/base/ranking', html)
        ranking_html = self._client(user_id=self.viewer_id).get("/ranking").get_data(as_text=True)
        self.assertIn("基地いいね", ranking_html)
        self.assertIn('/base/ranking', ranking_html)

    def test_banned_users_are_excluded(self):
        self._seed_likes()
        html = self._client().get("/base/ranking").get_data(as_text=True)
        self.assertNotIn("banned_base", html)
        self.assertNotIn(f"/base/{self.banned_id}", html)

    def test_weekly_ranking_uses_current_week_only(self):
        self._seed_likes()
        view = self._client().get("/base/ranking").get_data(as_text=True)
        weekly_start = view.index("今週の話題基地")
        total_start = view.index("累計人気基地")
        weekly_html = view[weekly_start:total_start]
        self.assertIn("alpha_base", weekly_html)
        self.assertNotIn("beta_base", weekly_html)

    def test_view_audit_is_recorded(self):
        self._seed_likes()
        self._client(user_id=self.viewer_id).get("/base/ranking")
        with game_app.app.app_context():
            db = game_app.get_db()
            count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
                    (self.viewer_id, game_app.AUDIT_EVENT_TYPES["BASE_RANKING_VIEW"]),
                ).fetchone()["c"]
            )
            self.assertGreaterEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
