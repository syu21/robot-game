import os
import tempfile
import unittest
from unittest.mock import patch

import app as game_app
import init_db


class TrialModeTests(unittest.TestCase):
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

    def _count_rows(self, table):
        with game_app.app.app_context():
            db = game_app.get_db()
            return int(db.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"])

    def test_register_page_links_trial_start(self):
        client = game_app.app.test_client()
        resp = client.get("/register")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("試験機で体験する", html)
        self.assertIn("/trial/start", html)

    def test_trial_start_home_and_explore_do_not_create_user_or_world_log(self):
        users_before = self._count_rows("users")
        logs_before = self._count_rows("world_events_log")
        client = game_app.app.test_client()

        start_resp = client.get("/trial/start", follow_redirects=True)
        self.assertEqual(start_resp.status_code, 200)
        start_html = start_resp.get_data(as_text=True)
        self.assertIn("お試しプレイ中", start_html)
        self.assertIn("出撃機体", start_html)
        self.assertIn("最初の出撃", start_html)
        self.assertIn("本番のロボ編成と同じ考え方で動きます。", start_html)
        self.assertNotIn("体験ガイド", start_html)
        self.assertIn("アーク・プロト", start_html)
        self.assertIn("robot_composed/trial_", start_html)
        self.assertNotIn("robot_icons/1.png", start_html)
        with client.session_transaction() as sess:
            self.assertTrue(sess.get("is_trial"))
            self.assertNotIn("user_id", sess)

        explore_resp = client.post("/explore", data={"area_key": "layer_1"})
        self.assertEqual(explore_resp.status_code, 200)
        explore_html = explore_resp.get_data(as_text=True)
        self.assertIn("パーツを手に入れた", explore_html)
        self.assertIn("次は強化してみよう", explore_html)
        self.assertIn("battle-short-replay", explore_html)
        self.assertIn("敵情報と詳細ログを見る", explore_html)
        parts_resp = client.get("/parts")
        self.assertEqual(parts_resp.status_code, 200)
        self.assertIn("所持パーツ", parts_resp.get_data(as_text=True))
        self.assertEqual(self._count_rows("users"), users_before)
        self.assertEqual(self._count_rows("world_events_log"), logs_before)

    def test_trial_strengthen_build_and_blocked_routes(self):
        client = game_app.app.test_client()
        client.get("/trial/start")
        client.post("/explore", data={"area_key": "layer_1"})

        strengthen_resp = client.post("/parts/strengthen")
        self.assertEqual(strengthen_resp.status_code, 200)
        strengthen_html = strengthen_resp.get_data(as_text=True)
        self.assertIn("強くなった！", strengthen_html)
        self.assertIn("ロボ編成へ", strengthen_html)

        build_resp = client.post("/build", data={"build_key": "swift"})
        self.assertEqual(build_resp.status_code, 200)
        build_html = build_resp.get_data(as_text=True)
        self.assertIn("組み替え完了", build_html)
        self.assertIn("もう一度出撃してみよう", build_html)
        self.assertIn('action="/explore"', build_html)
        self.assertIn('name="area_key" value="layer_1"', build_html)
        self.assertIn("新規登録してはじめる", build_html)
        self.assertNotIn("体験ループ完了", build_html)
        self.assertNotIn("出撃、強化、編成まで確認できました。", build_html)

        blocked_resp = client.get("/ranking")
        self.assertEqual(blocked_resp.status_code, 302)
        self.assertIn("/home", blocked_resp.headers["Location"])

    def test_trial_finishes_after_three_explores(self):
        client = game_app.app.test_client()
        client.get("/trial/start")
        with patch.object(game_app, "TRIAL_MODE_CT_SECONDS", 0):
            for _ in range(3):
                resp = client.post("/explore", data={"area_key": "layer_1"})
                self.assertEqual(resp.status_code, 200)
        finish_resp = client.get("/home", follow_redirects=True)
        self.assertEqual(finish_resp.status_code, 200)
        self.assertIn("ここまで遊んだ内容は保存されません", finish_resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
