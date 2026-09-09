import os
import tempfile
import unittest

import app as game_app
import init_db


class SQLitePerformanceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_db_path = game_app.DB_PATH
        self.old_init_db_path = init_db.DB_PATH
        self.old_testing = game_app.app.config.get("TESTING")
        self.old_bypass = game_app.app.config.get("BYPASS_RELEASE_GATES_IN_TESTS")
        game_app.DB_PATH = os.path.join(self.tmpdir.name, "test_game.db")
        init_db.DB_PATH = game_app.DB_PATH
        game_app.DB_WAL_READY_KEYS.discard(os.path.abspath(game_app.DB_PATH))
        init_db.main()
        game_app.app.config["TESTING"] = True
        game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = True

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        game_app.app.config["TESTING"] = self.old_testing
        game_app.app.config["BYPASS_RELEASE_GATES_IN_TESTS"] = self.old_bypass
        self.tmpdir.cleanup()

    def test_get_db_configures_busy_timeout_and_wal(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            busy_timeout = db.execute("PRAGMA busy_timeout").fetchone()[0]
            journal_mode = db.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(int(busy_timeout), int(game_app.SQLITE_BUSY_TIMEOUT_MS))
        self.assertEqual(str(journal_mode).lower(), "wal")

    def test_get_robot_stats_on_get_does_not_create_tuning_state(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            user_id = 1
            now = game_app._now_ts()
            db.execute(
                """
                INSERT INTO users (id, username, password_hash, created_at, last_seen_at, is_admin, wins, max_unlocked_layer)
                VALUES (?, 'sqlite_perf', 'x', ?, ?, 0, 0, 2)
                """,
                (user_id, now, now),
            )
            game_app.initialize_new_user(db, user_id)
            user = db.execute("SELECT active_robot_id FROM users WHERE id = ?", (user_id,)).fetchone()
            robot_id = int(user["active_robot_id"])
            db.execute("DELETE FROM robot_tuning_states WHERE robot_instance_id = ?", (robot_id,))
            db.commit()
            before_changes = db.total_changes
            with game_app.app.test_request_context("/home", method="GET"):
                stat_obj = game_app._compute_robot_stats_for_instance(db, robot_id)
                row = db.execute(
                    "SELECT 1 FROM robot_tuning_states WHERE robot_instance_id = ?",
                    (robot_id,),
                ).fetchone()
                self.assertIsNotNone(stat_obj)
                self.assertIsNone(row)
                self.assertEqual(db.total_changes, before_changes)


if __name__ == "__main__":
    unittest.main()
