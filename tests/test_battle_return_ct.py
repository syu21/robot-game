import os
import tempfile
import time
import unittest
from unittest import mock

import app as game_app
import init_db


class BattleReturnCooldownTests(unittest.TestCase):
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

    def _create_user(self, username, is_admin=0):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            cur = db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins) VALUES (?, ?, ?, ?, 0)",
                (username, "x", now, int(is_admin)),
            )
            user_id = int(cur.lastrowid)
            game_app.initialize_new_user(db, user_id)
            db.commit()
            return user_id

    def _login(self, client, user_id, username):
        with client.session_transaction() as sess:
            sess["user_id"] = int(user_id)
            sess["username"] = username

    def _mark_initial_sprint_complete(self, user_id):
        with game_app.app.app_context():
            db = game_app.get_db()
            for i in range(3):
                db.execute(
                    """
                    INSERT INTO world_events_log (created_at, event_type, payload_json, user_id, action_key)
                    VALUES (?, ?, ?, ?, 'explore')
                    """,
                    (
                        int(time.time()) - (30 - i),
                        game_app.AUDIT_EVENT_TYPES["EXPLORE_END"],
                        '{"area_key":"layer_1","result":{"win":true}}',
                        int(user_id),
                    ),
                )
            db.commit()

    def test_non_admin_sees_explore_return_cooldown(self):
        user_id = self._create_user("ct_user", is_admin=0)
        self._mark_initial_sprint_complete(user_id)
        with game_app.app.test_client() as client:
            self._login(client, user_id, "ct_user")
            with mock.patch.object(game_app, "_has_area_boss_candidates", return_value=False):
                resp = client.post("/explore", data={"area_key": "layer_1"})
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn('id="explore-return-btn"', html)
            self.assertIn("もう一度出撃（あと", html)
            self.assertIn('data-ct-ready-at="', html)
            self.assertIn("入手したパーツを見る", html)
            self.assertIn("勝敗と戦利品は保存済みです。", html)
            self.assertNotIn('class="robo-fixed-nav"', html)
            self.assertIn("disabled", html)

    def test_admin_can_return_to_explore_without_cooldown_lock(self):
        user_id = self._create_user("ct_admin", is_admin=1)
        with game_app.app.test_client() as client:
            self._login(client, user_id, "ct_admin")
            with mock.patch.object(game_app, "_has_area_boss_candidates", return_value=False):
                resp = client.post("/explore", data={"area_key": "layer_1"})
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn('id="explore-return-btn"', html)
            self.assertIn('data-ct-ready-at="0"', html)
            self.assertIn(">もう一度出撃<", html)
            self.assertNotIn("もう一度出撃（あと", html)

    def test_fixed_nav_restore_button_and_ct_metadata(self):
        user_id = self._create_user("nav_user", is_admin=0)
        with game_app.app.test_client() as client:
            self._login(client, user_id, "nav_user")

            visible = client.get("/home")
            self.assertEqual(visible.status_code, 200)
            visible_html = visible.get_data(as_text=True)
            self.assertIn('class="robo-fixed-nav"', visible_html)
            self.assertIn('data-ready-at="', visible_html)
            self.assertIn('data-now="', visible_html)

            hidden = client.post("/settings/fixed-nav/hide", data={"next": "/home"}, follow_redirects=True)
            self.assertEqual(hidden.status_code, 200)
            hidden_html = hidden.get_data(as_text=True)
            self.assertNotIn('class="robo-fixed-nav"', hidden_html)
            self.assertIn('class="robo-fixed-nav-restore"', hidden_html)
            self.assertIn(">メニュー<", hidden_html)

            shown = client.post("/settings/fixed-nav/show", data={"next": "/home"}, follow_redirects=True)
            self.assertEqual(shown.status_code, 200)
            self.assertIn('class="robo-fixed-nav"', shown.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
