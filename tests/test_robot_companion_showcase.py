import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class RobotCompanionShowcaseTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 1, 0, 1)
                """,
                ("owner_user", "x", now),
            )
            db.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_admin, wins, max_unlocked_layer)
                VALUES (?, ?, ?, 1, 0, 1)
                """,
                ("liker_user", "x", now),
            )
            self.owner_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("owner_user",),
            ).fetchone()["id"]
            self.liker_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("liker_user",),
            ).fetchone()["id"]
            game_app.initialize_new_user(db, self.owner_id)
            game_app.initialize_new_user(db, self.liker_id)
            self.owner_robot_id = db.execute(
                "SELECT active_robot_id FROM users WHERE id = ?",
                (self.owner_id,),
            ).fetchone()["active_robot_id"]
            self.liker_robot_id = db.execute(
                "SELECT active_robot_id FROM users WHERE id = ?",
                (self.liker_id,),
            ).fetchone()["active_robot_id"]
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client_for(self, user_id, username):
        client = game_app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = user_id
            session["username"] = username
        return client

    def _set_robot_weights(self, robot_id, *, name, hp, atk, defe, spd, acc, cri):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE robot_instances SET name = ?, is_public = 1 WHERE id = ?", (name, int(robot_id)))
            parts = db.execute(
                """
                SELECT head_part_instance_id, r_arm_part_instance_id, l_arm_part_instance_id, legs_part_instance_id
                FROM robot_instance_parts
                WHERE robot_instance_id = ?
                """,
                (int(robot_id),),
            ).fetchone()
            for part_instance_id in (
                int(parts["head_part_instance_id"]),
                int(parts["r_arm_part_instance_id"]),
                int(parts["l_arm_part_instance_id"]),
                int(parts["legs_part_instance_id"]),
            ):
                db.execute(
                    """
                    UPDATE part_instances
                    SET w_hp = ?, w_atk = ?, w_def = ?, w_spd = ?, w_acc = ?, w_cri = ?
                    WHERE id = ?
                    """,
                    (float(hp), float(atk), float(defe), float(spd), float(acc), float(cri), part_instance_id),
                )
            db.commit()

    def test_robot_history_updates_once_for_same_submission(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute(
                """
                UPDATE enemies
                SET hp = 1, atk = 0, def = 0, spd = 0, acc = 0, cri = 0
                WHERE is_active = 1 AND is_boss = 0 AND tier = 1
                """
            )
            db.commit()
        client = self._client_for(self.owner_id, "owner_user")
        home = client.get("/home")
        self.assertEqual(home.status_code, 200)
        html = home.get_data(as_text=True)
        marker = 'name="explore_submission_id" value="'
        self.assertIn(marker, html)
        sid = html.split(marker, 1)[1].split('"', 1)[0]
        r1 = client.post("/explore", data={"area_key": "layer_1", "explore_submission_id": sid})
        self.assertEqual(r1.status_code, 200)
        r2 = client.post("/explore", data={"area_key": "layer_1", "explore_submission_id": sid})
        self.assertEqual(r2.status_code, 200)
        with game_app.app.app_context():
            db = game_app.get_db()
            hist = db.execute(
                "SELECT battles_total, wins_total, losses_total FROM robot_history WHERE robot_id = ?",
                (int(self.owner_robot_id),),
            ).fetchone()
            self.assertIsNotNone(hist)
            self.assertEqual(int(hist["battles_total"]), 1)
            self.assertEqual(int(hist["wins_total"]), 1)
            self.assertEqual(int(hist["losses_total"]), 0)

    def test_showcase_like_toggle_does_not_duplicate(self):
        client = self._client_for(self.liker_id, "liker_user")
        first = client.post(f"/showcase/{int(self.owner_robot_id)}/like", data={"sort": "new"})
        self.assertEqual(first.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            count1 = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM showcase_votes
                WHERE robot_id = ? AND user_id = ? AND vote_type = 'like'
                """,
                (int(self.owner_robot_id), int(self.liker_id)),
            ).fetchone()["c"]
            self.assertEqual(int(count1), 1)
        second = client.post(f"/showcase/{int(self.owner_robot_id)}/like", data={"sort": "new"})
        self.assertEqual(second.status_code, 302)
        with game_app.app.app_context():
            db = game_app.get_db()
            count2 = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM showcase_votes
                WHERE robot_id = ? AND user_id = ? AND vote_type = 'like'
                """,
                (int(self.owner_robot_id), int(self.liker_id)),
            ).fetchone()["c"]
            self.assertEqual(int(count2), 0)

    def test_showcase_supports_robot_metric_sort_and_profile_text(self):
        self._set_robot_weights(
            self.owner_robot_id,
            name="Bastion Owner",
            hp=0.42,
            atk=0.04,
            defe=0.36,
            spd=0.07,
            acc=0.07,
            cri=0.04,
        )
        self._set_robot_weights(
            self.liker_robot_id,
            name="Velocity Liker",
            hp=0.04,
            atk=0.12,
            defe=0.05,
            spd=0.58,
            acc=0.13,
            cri=0.08,
        )
        client = self._client_for(self.owner_id, "owner_user")
        resp = client.get("/showcase?sort=fastest")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("最速", html)
        self.assertIn("思想:", html)
        self.assertIn("注目記録:", html)
        self.assertIn("Velocity Liker", html)
        self.assertIn("Bastion Owner", html)
        public_section = html.split("公開ロボ", 1)[1]
        self.assertLess(public_section.index("Velocity Liker"), public_section.index("Bastion Owner"))


if __name__ == "__main__":
    unittest.main()
