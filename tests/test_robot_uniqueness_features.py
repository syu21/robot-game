import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class RobotUniquenessFeatureTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, coins, max_unlocked_layer)
                VALUES (?, ?, ?, 1, 0, 0, 1)
                """,
                ("robot_admin", "x", now),
            )
            self.admin_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("robot_admin",)).fetchone()["id"])
            game_app.initialize_new_user(db, self.admin_id)
            self.robot_id = int(db.execute("SELECT active_robot_id FROM users WHERE id = ?", (self.admin_id,)).fetchone()["active_robot_id"])
            db.execute("UPDATE robot_instances SET name = ?, is_public = 1 WHERE id = ?", ("UniqueBot", self.robot_id))

            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, coins, max_unlocked_layer)
                VALUES (?, ?, ?, 0, 0, 0, 1)
                """,
                ("viewer", "x", now),
            )
            self.viewer_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("viewer",)).fetchone()["id"])
            db.execute(
                """
                INSERT INTO showcase_votes (robot_id, user_id, vote_type, created_at)
                VALUES (?, ?, 'like', ?)
                """,
                (self.robot_id, self.viewer_id, now),
            )
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self, user_id=None, username="robot_admin"):
        client = game_app.app.test_client()
        if user_id:
            with client.session_transaction() as session:
                session["user_id"] = int(user_id)
                session["username"] = username
        return client

    def test_robot_detail_shows_share_link_and_blueprint(self):
        response = self._client(self.admin_id).get(f"/robots/{self.robot_id}")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("画像を共有", html)
        self.assertIn("設計図", html)
        self.assertIn("設計番号:", html)
        self.assertIn("人気ロボに投稿する", html)
        self.assertIn("コンテストを見る", html)
        self.assertIn("head_rotate_degrees", html)
        self.assertIn("head_flip_x", html)

    def test_home_customize_cta_logs_click(self):
        client = self._client(self.admin_id)
        html = client.get("/home").get_data(as_text=True)
        self.assertIn("ロボ調整", html)
        self.assertIn("パーツの位置・大きさ・回転・反転を調整して、自分だけのロボにできます", html)
        self.assertIn("ロボを調整する", html)

        response = client.post(
            "/robots/customize/start",
            data={"robot_id": str(self.robot_id)},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/build", response.headers["Location"])
        with game_app.app.app_context():
            db = game_app.get_db()
            count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
                    (self.admin_id, game_app.AUDIT_EVENT_TYPES["ROBOT_CUSTOMIZE_CTA_CLICK"]),
                ).fetchone()["c"]
            )
            self.assertEqual(count, 1)

    def test_robots_build_result_card_shows_next_actions(self):
        response = self._client(self.admin_id).get(f"/robots?build_result_id={self.robot_id}")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("ロボ完成", html)
        self.assertIn("設計番号:", html)
        self.assertIn("ロボ詳細を見る", html)
        self.assertIn("画像を共有する", html)
        self.assertIn("人気ロボに投稿する", html)
        self.assertIn("コンテストを見る", html)

    def test_popular_robots_uses_weekly_showcase_likes(self):
        response = self._client().get("/robots/popular")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("今週の人気ロボ", html)
        self.assertIn("UniqueBot", html)
        self.assertIn("今週いいね: 1", html)

    def test_default_contest_template_and_home_card(self):
        client = self._client(self.admin_id)
        response = client.post("/robots/contests/create_default", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("第1回 ロボらぼ自由工作杯", html)
        self.assertIn("通常・虫・恐竜パーツを自由に組み合わせて", html)
        self.assertIn("終了日:", html)
        self.assertIn("最初の投稿者になろう", html)
        self.assertIn("投稿する", html)

        home_html = client.get("/home").get_data(as_text=True)
        self.assertIn("開催中コンテスト", home_html)
        self.assertIn("第1回 ロボらぼ自由工作杯", home_html)
        self.assertIn("投稿数: 0", home_html)
        self.assertIn("コンテストを見る", home_html)

        with game_app.app.app_context():
            db = game_app.get_db()
            count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
                    (self.admin_id, game_app.AUDIT_EVENT_TYPES["ROBOT_CONTEST_VIEW"]),
                ).fetchone()["c"]
            )
            self.assertGreaterEqual(count, 1)

    def test_admin_can_create_contest_and_submit_robot(self):
        client = self._client(self.admin_id)
        create = client.post(
            "/robots/contests/create",
            data={"title": "青い研究所", "description": "青色が映えるロボ"},
            follow_redirects=True,
        )
        self.assertEqual(create.status_code, 200)
        self.assertIn("青い研究所", create.get_data(as_text=True))

        submit = client.post(
            "/robots/contests/submit",
            data={"contest_id": "1", "robot_instance_id": str(self.robot_id)},
            follow_redirects=True,
        )
        self.assertEqual(submit.status_code, 200)
        html = submit.get_data(as_text=True)
        self.assertIn("UniqueBot", html)
        self.assertIn("ロボをコンテストへ投稿しました。", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = ?",
                    (self.admin_id, game_app.AUDIT_EVENT_TYPES["ROBOT_CONTEST_SUBMIT"]),
                ).fetchone()["c"]
            )
            self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
