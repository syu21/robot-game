import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class BuildConfirmSlotLimitTests(unittest.TestCase):
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
                "INSERT INTO users (username, password_hash, created_at, is_admin) VALUES (?, ?, ?, 1)",
                ("slot_tester", "x", now),
            )
            self.user_id = db.execute("SELECT id FROM users WHERE username = ?", ("slot_tester",)).fetchone()["id"]
            game_app.initialize_new_user(db, self.user_id)
            user = db.execute("SELECT * FROM users WHERE id = ?", (self.user_id,)).fetchone()
            limits = game_app._effective_limits(db, user)
            active_count = db.execute(
                "SELECT COUNT(*) AS c FROM robot_instances WHERE user_id = ? AND status != 'decomposed'",
                (self.user_id,),
            ).fetchone()["c"]
            while int(active_count) < int(limits["robot_slots"]):
                db.execute(
                    """
                    INSERT INTO robot_instances (user_id, name, status, created_at, updated_at)
                    VALUES (?, ?, 'active', ?, ?)
                    """,
                    (self.user_id, f"Dummy#{active_count}", now, now),
                )
                active_count += 1

            for part_type in ("HEAD", "RIGHT_ARM", "LEFT_ARM", "LEGS"):
                part = db.execute(
                    "SELECT * FROM robot_parts WHERE part_type = ? AND is_active = 1 ORDER BY id ASC LIMIT 1",
                    (part_type,),
                ).fetchone()
                game_app._create_part_instance_from_master(db, self.user_id, part, plus=0)
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
            sess["username"] = "slot_tester"
        return client

    def test_build_confirm_full_slots_blocks_save(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            before = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM robot_instances WHERE user_id = ? AND status != 'decomposed'",
                    (self.user_id,),
                ).fetchone()["c"]
            )
            parts = {}
            for key, part_type in (
                ("head_key", "HEAD"),
                ("r_arm_key", "RIGHT_ARM"),
                ("l_arm_key", "LEFT_ARM"),
                ("legs_key", "LEGS"),
            ):
                row = db.execute(
                    """
                    SELECT pi.id
                    FROM part_instances pi
                    WHERE pi.user_id = ? AND pi.status = 'inventory' AND pi.part_type = ?
                    ORDER BY pi.id ASC
                    LIMIT 1
                    """,
                    (self.user_id, part_type),
                ).fetchone()
                parts[key] = str(row["id"])

        client = self._client()
        resp = client.post(
            "/build/confirm",
            data={
                "robot_name": "Overflow",
                "combat_mode": "normal",
                **parts,
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("保存枠がいっぱいです", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            after = int(
                db.execute(
                    "SELECT COUNT(*) AS c FROM robot_instances WHERE user_id = ? AND status != 'decomposed'",
                    (self.user_id,),
                ).fetchone()["c"]
            )
            self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
