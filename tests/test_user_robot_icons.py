import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class UserRobotIconTests(unittest.TestCase):
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

    def _create_user(self, username, *, initialize=False):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer) VALUES (?, ?, ?, 0, 0, 1)",
                (username, "x", now),
            )
            user_id = int(db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"])
            if initialize:
                game_app.initialize_new_user(db, user_id)
            db.commit()
            return user_id

    def _add_inventory_build_set(self, user_id):
        with game_app.app.app_context():
            db = game_app.get_db()
            slot_values = {}
            for field_name, part_type in (
                ("head_key", "HEAD"),
                ("r_arm_key", "RIGHT_ARM"),
                ("l_arm_key", "LEFT_ARM"),
                ("legs_key", "LEGS"),
            ):
                part = db.execute(
                    "SELECT * FROM robot_parts WHERE part_type = ? AND is_active = 1 ORDER BY id ASC LIMIT 1",
                    (part_type,),
                ).fetchone()
                instance_id = game_app._create_part_instance_from_master(db, user_id, part, plus=0)
                slot_values[field_name] = str(instance_id)
            db.commit()
            return slot_values

    def _client(self, user_id, username):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = user_id
            session["username"] = username
        return client

    def _insert_google_identity(self, user_id, *, avatar_url="https://example.com/google-avatar.png", display_name="Google Pilot"):
        with game_app.app.app_context():
            db = game_app.get_db()
            now = int(time.time())
            db.execute(
                """
                INSERT INTO user_auth_identities
                (user_id, provider, provider_user_id, email, display_name, avatar_url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(user_id),
                    game_app.GOOGLE_OAUTH_PROVIDER,
                    f"google-{user_id}",
                    f"user{user_id}@example.com",
                    display_name,
                    avatar_url,
                    now,
                    now,
                ),
            )
            db.commit()

    def test_build_confirm_generates_icon_for_new_active_robot(self):
        user_id = self._create_user("icon_builder", initialize=True)
        slot_values = self._add_inventory_build_set(user_id)
        client = self._client(user_id, "icon_builder")

        resp = client.post(
            "/build/confirm",
            data={
                "robot_name": "Icon Builder Mk2",
                "combat_mode": "normal",
                **slot_values,
            },
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/robots", resp.headers["Location"])

        with game_app.app.app_context():
            db = game_app.get_db()
            user = db.execute("SELECT active_robot_id FROM users WHERE id = ?", (user_id,)).fetchone()
            self.assertIsNotNone(user["active_robot_id"])
            robot = db.execute(
                "SELECT id, composed_image_path, icon_32_path FROM robot_instances WHERE id = ?",
                (int(user["active_robot_id"]),),
            ).fetchone()
            self.assertEqual(str(robot["icon_32_path"]), f"robot_icons/{int(robot['id'])}.png")
            self.assertTrue(os.path.exists(os.path.join(game_app.STATIC_ROOT, str(robot["composed_image_path"]))))
            self.assertTrue(os.path.exists(os.path.join(game_app.STATIC_ROOT, str(robot["icon_32_path"]))))

    def test_home_uses_current_robot_icon(self):
        user_id = self._create_user("home_icon_user", initialize=True)
        client = self._client(user_id, "home_icon_user")

        with game_app.app.app_context():
            db = game_app.get_db()
            visuals = game_app._user_visuals(db, user_id, {})
            expected_icon = visuals["badge"]
            expected_avatar = visuals["avatar"]

        resp = client.get("/home")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn(expected_icon, html)
        self.assertIn(expected_avatar, html)
        self.assertIn("is-robot-icon", html)
        self.assertIn("user-chip-avatar", html)
        self.assertIn("variant-header", html)
        self.assertNotIn("badge-overlay", html)

    def test_settings_page_explains_auto_icon_generation(self):
        user_id = self._create_user("settings_icon_user", initialize=True)
        client = self._client(user_id, "settings_icon_user")

        with game_app.app.app_context():
            db = game_app.get_db()
            visuals = game_app._user_visuals(db, user_id, {})
            expected_icon = visuals["badge"]
            expected_avatar = visuals["avatar"]

        resp = client.get("/settings")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("機体アイコン", html)
        self.assertIn("小ロボは現在の出撃機体から自動生成され", html)
        self.assertIn("Google画像 → 手動画像 → seed生成", html)
        self.assertIn("ロボ編成を確定すると、小ロボ画像も自動で更新されます。", html)
        self.assertIn(expected_icon, html)
        self.assertIn(expected_avatar, html)
        self.assertNotIn('type="file"', html)

    def test_non_google_user_gets_seed_profile_avatar(self):
        user_id = self._create_user("no_robot_user", initialize=False)
        client = self._client(user_id, "no_robot_user")

        with game_app.app.app_context():
            db = game_app.get_db()
            icon_rel = game_app._user_primary_icon_rel(db, user_id, default_rel=game_app.DEFAULT_AVATAR_REL)
            visuals = game_app._user_visuals(db, user_id, {})

        self.assertEqual(icon_rel, game_app.DEFAULT_AVATAR_REL)
        self.assertTrue(str(visuals["avatar"]).startswith("generated_avatars/user_"))
        self.assertTrue(os.path.exists(os.path.join(game_app.STATIC_ROOT, str(visuals["avatar"]))))
        self.assertTrue(bool(visuals["avatar_is_generated"]))

        resp = client.get("/settings")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn(game_app.DEFAULT_BADGE_REL, html)
        self.assertIn(str(visuals["avatar"]), html)
        self.assertIn("機体未所持のあいだは、初期ノーマルロボ顔を表示します。", html)
        self.assertNotIn('type="file"', html)

    def test_google_identity_avatar_is_used_as_profile_overlay(self):
        user_id = self._create_user("google_robot_user", initialize=True)
        self._insert_google_identity(user_id, avatar_url="https://example.com/google-overlay.png", display_name="Google Overlay")
        client = self._client(user_id, "google_robot_user")

        with game_app.app.app_context():
            db = game_app.get_db()
            visuals = game_app._user_visuals(db, user_id, {})

        self.assertEqual(visuals["avatar_url"], "https://example.com/google-overlay.png")
        self.assertIsNone(visuals["avatar"])
        self.assertFalse(bool(visuals["avatar_is_generated"]))
        self.assertTrue(str(visuals["badge"]).startswith("robot_icons/"))

        resp = client.get("/settings")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("https://example.com/google-overlay.png", html)
        self.assertIn(str(visuals["badge"]), html)
        self.assertIn("Google画像 → 手動画像 → seed生成", html)


if __name__ == "__main__":
    unittest.main()
