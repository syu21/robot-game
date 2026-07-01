import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class CompanionAlbumTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer, coins)
                VALUES (?, ?, ?, 0, 0, 1, 777)
                """,
                ("album_user", "x", now),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = ?", ("album_user",)).fetchone()["id"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = "album_user"
        return client

    def _start_rare_photo_dispatch(self):
        db = game_app.get_db()
        game_app.ensure_companions(db, self.user_id)
        start = game_app.start_companion_dispatch(
            db,
            self.user_id,
            "short_patrol",
            event_type_override="rare_photo",
            journal_key_override="old_hangar",
        )
        self.assertTrue(start["ok"])
        db.execute(
            "UPDATE user_companion_dispatches SET completes_at = ? WHERE id = ?",
            (int(time.time()) - 1, int(start["dispatch_id"])),
        )
        db.commit()
        return start

    def test_album_initial_access_seeds_photos_and_shows_locked_cards(self):
        html = self._client().get("/companion/album").get_data(as_text=True)
        self.assertIn("相棒アルバム", html)
        self.assertIn("写真コレクション", html)
        self.assertIn("？？？", html)
        with game_app.app.app_context():
            db = game_app.get_db()
            count = int(db.execute("SELECT COUNT(*) AS c FROM companion_album_photos").fetchone()["c"])
            self.assertEqual(count, 5)

    def test_rare_photo_event_fixes_photo_at_start_and_claim_unlocks_it(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            start = self._start_rare_photo_dispatch()
            dispatch = db.execute("SELECT * FROM user_companion_dispatches WHERE id = ?", (int(start["dispatch_id"]),)).fetchone()
            self.assertEqual(dispatch["event_type"], "rare_photo")
            self.assertTrue(dispatch["event_photo_key"])
            photo_key = dispatch["event_photo_key"]
            claim = game_app.claim_companion_dispatch(db, self.user_id, request_id="album-claim")
            self.assertTrue(claim["ok"])
            self.assertEqual(claim["event_photo_key"], photo_key)
            self.assertIsNotNone(claim["unlocked_photo"])
            owned = db.execute(
                "SELECT * FROM user_companion_album_photos WHERE user_id = ? AND photo_key = ?",
                (self.user_id, photo_key),
            ).fetchone()
            self.assertIsNotNone(owned)
            event = db.execute(
                "SELECT id FROM world_events_log WHERE user_id = ? AND event_type = ?",
                (self.user_id, game_app.AUDIT_EVENT_TYPES["COMPANION_ALBUM_PHOTO_UNLOCK"]),
            ).fetchone()
            self.assertIsNotNone(event)
            second = game_app.claim_companion_dispatch(db, self.user_id)
            self.assertFalse(second["ok"])
            owned_count = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM user_companion_album_photos WHERE user_id = ? AND photo_key = ?",
                    (self.user_id, photo_key),
                ).fetchone()["c"]
            )
            self.assertEqual(owned_count, 1)

    def test_album_view_shows_owned_and_unowned_photos(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            self._start_rare_photo_dispatch()
            claim = game_app.claim_companion_dispatch(db, self.user_id)
            self.assertTrue(claim["ok"])
        html = self._client().get("/companion/album").get_data(as_text=True)
        self.assertIn("1 / 5", html)
        self.assertIn(claim["unlocked_photo"]["name_ja"], html)
        self.assertIn("未発見", html)

    def test_duplicate_photo_when_all_owned_grants_fixed_compensation_only(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app.ensure_companions(db, self.user_id)
            game_app.ensure_companion_album_photos(db, user_id=self.user_id)
            now = int(time.time())
            for row in db.execute("SELECT photo_key FROM companion_album_photos WHERE is_active = 1").fetchall():
                db.execute(
                    """
                    INSERT OR IGNORE INTO user_companion_album_photos
                    (user_id, photo_key, unlocked_at, source_dispatch_id)
                    VALUES (?, ?, ?, NULL)
                    """,
                    (self.user_id, row["photo_key"], now),
                )
            db.commit()
            start = game_app.start_companion_dispatch(
                db,
                self.user_id,
                "short_patrol",
                event_type_override="rare_photo",
                journal_key_override="old_hangar",
            )
            dispatch = db.execute("SELECT * FROM user_companion_dispatches WHERE id = ?", (int(start["dispatch_id"]),)).fetchone()
            base_reward = int(dispatch["base_reward_factory_points"])
            self.assertEqual(int(dispatch["event_bonus_points"]), game_app.COMPANION_ALBUM_PHOTO_DUPLICATE_COMPENSATION_POINTS)
            db.execute(
                "UPDATE user_companion_dispatches SET completes_at = ? WHERE id = ?",
                (int(time.time()) - 1, int(start["dispatch_id"])),
            )
            claim = game_app.claim_companion_dispatch(db, self.user_id)
            self.assertTrue(claim["ok"])
            self.assertTrue(claim["photo_duplicate"])
            self.assertEqual(claim["reward_factory_points"], base_reward + game_app.COMPANION_ALBUM_PHOTO_DUPLICATE_COMPENSATION_POINTS)
            user = db.execute("SELECT factory_points, coins FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(int(user["factory_points"]), claim["reward_factory_points"])
            self.assertEqual(int(user["coins"]), 777)


if __name__ == "__main__":
    unittest.main()
