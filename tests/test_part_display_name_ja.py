import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class PartDisplayNameJaTests(unittest.TestCase):
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
                "INSERT INTO users (username, password_hash, created_at, is_admin, wins, coins, max_unlocked_layer) VALUES (?, ?, ?, 1, 0, 0, 1)",
                ("parts_admin", "x", now),
            )
            self.user_id = int(
                db.execute("SELECT id FROM users WHERE username = ?", ("parts_admin",)).fetchone()["id"]
            )
            game_app.initialize_new_user(db, self.user_id)
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _login(self, client):
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
            sess["username"] = "parts_admin"

    def test_generate_part_display_name_ja(self):
        self.assertEqual(
            game_app.generate_part_display_name_ja("head_r_fire"),
            "焔頭冠改",
        )
        self.assertEqual(
            game_app.generate_part_display_name_ja("legs_n_wind"),
            "烈風脚部",
        )
        self.assertEqual(
            game_app.generate_part_display_name_ja("unknown_format"),
            "unknown_format",
        )

    def test_build_uses_japanese_display_name_after_backfill(self):
        client = game_app.app.test_client()
        self._login(client)
        resp = client.get("/build")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("無印頭冠", html)

    def test_admin_override_display_name_has_priority(self):
        client = game_app.app.test_client()
        self._login(client)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT id, key, part_type, rarity, element, series, offset_x, offset_y FROM robot_parts WHERE key = 'head_1'"
            ).fetchone()
            self.assertIsNotNone(row)
            part_id = int(row["id"])

        post_data = {
            "edit_part_id": str(part_id),
            "part_type": "HEAD",
            "key": "head_1",
            "rarity": "N",
            "element": "NORMAL",
            "series": "S1",
            "display_name_ja": "試作零式頭冠",
            "offset_x": "0",
            "offset_y": "0",
        }
        resp = client.post("/admin/parts", data=post_data)
        self.assertEqual(resp.status_code, 200)

        with game_app.app.app_context():
            db = game_app.get_db()
            updated = db.execute("SELECT * FROM robot_parts WHERE id = ?", (part_id,)).fetchone()
            self.assertEqual(updated["display_name_ja"], "試作零式頭冠")
            self.assertEqual(game_app._part_display_name_ja(updated), "試作零式頭冠")


if __name__ == "__main__":
    unittest.main()
