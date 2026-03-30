import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class PartsFuseRouteTests(unittest.TestCase):
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
                ("fuse_tester", "x", now),
            )
            self.user_id = db.execute("SELECT id FROM users WHERE username = ?", ("fuse_tester",)).fetchone()["id"]
            game_app.initialize_new_user(db, self.user_id)
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
            sess["username"] = "fuse_tester"
        return client

    def _seed_same_part_instances(self, plus_values):
        with game_app.app.app_context():
            db = game_app.get_db()
            seed = db.execute(
                """
                SELECT rp.id AS part_id, rp.part_type, rp.rarity, rp.element, rp.series
                FROM robot_parts rp
                WHERE rp.is_active = 1
                ORDER BY rp.id ASC
                LIMIT 1
                """
            ).fetchone()
            db.execute("DELETE FROM part_instances WHERE user_id = ? AND status = 'inventory'", (self.user_id,))
            now_text = "2026-03-05 00:00:00"
            ids = []
            for plus in plus_values:
                cur = db.execute(
                    """
                    INSERT INTO part_instances
                    (part_id, user_id, part_type, rarity, element, series, plus, w_hp, w_atk, w_def, w_spd, w_acc, w_cri, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'inventory', ?, ?)
                    """,
                    (
                        int(seed["part_id"]),
                        int(self.user_id),
                        seed["part_type"],
                        seed["rarity"],
                        seed["element"],
                        seed["series"],
                        int(plus),
                        1.0,
                        1.0,
                        1.0,
                        1.0,
                        1.0,
                        1.0,
                        int(time.time()),
                        now_text,
                    ),
                )
                ids.append(int(cur.lastrowid))
            db.execute("UPDATE users SET coins = 999 WHERE id = ?", (self.user_id,))
            db.commit()
        return ids

    def test_parts_fuse_select_without_ids_does_not_500(self):
        client = self._client()
        resp = client.post("/parts/fuse?mode=select", data={"mode": "select"}, follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        follow = client.get(resp.headers["Location"])
        self.assertEqual(follow.status_code, 200)

    def test_parts_fuse_writes_audit_and_result_mode_hides_filter(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET coins = 999 WHERE id = ?", (self.user_id,))
            seed = db.execute(
                """
                SELECT part_id, part_type, rarity, element, series, plus, w_hp, w_atk, w_def, w_spd, w_acc, w_cri
                FROM part_instances
                WHERE user_id = ? AND status = 'inventory'
                ORDER BY id ASC
                LIMIT 1
                """,
                (self.user_id,),
            ).fetchone()
            now_text = "2026-03-05 00:00:00"
            for _ in range(2):
                db.execute(
                    """
                    INSERT INTO part_instances
                    (part_id, user_id, part_type, rarity, element, series, plus, w_hp, w_atk, w_def, w_spd, w_acc, w_cri, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'inventory', ?, ?)
                    """,
                    (
                        int(seed["part_id"]),
                        int(self.user_id),
                        seed["part_type"],
                        seed["rarity"],
                        seed["element"],
                        seed["series"],
                        int(seed["plus"]),
                        seed["w_hp"],
                        seed["w_atk"],
                        seed["w_def"],
                        seed["w_spd"],
                        seed["w_acc"],
                        seed["w_cri"],
                        int(time.time()),
                        now_text,
                    ),
                )
            base_id = db.execute(
                """
                SELECT id FROM part_instances
                WHERE user_id = ? AND status = 'inventory' AND part_id = ? AND plus = ?
                ORDER BY id ASC LIMIT 1
                """,
                (self.user_id, int(seed["part_id"]), int(seed["plus"])),
            ).fetchone()["id"]
            db.commit()

        client = self._client()
        resp = client.post("/parts/fuse", data={"mode": "select", "base_id": str(base_id)}, follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        self.assertRegex(resp.headers.get("Location", ""), r"mode=result")
        page = client.get(resp.headers["Location"])
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("もう一度強化する", html)
        self.assertNotIn("生成物を一覧で見る", html)
        self.assertNotIn("fuse-filter-form", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = 'audit.fuse'",
                (self.user_id,),
            ).fetchone()
            self.assertGreaterEqual(int(row["c"] or 0), 1)

    def test_fuse_allows_mixed_plus_same_part_key(self):
        ids = self._seed_same_part_instances([1, 0, 0])
        base_id = ids[0]
        client = self._client()
        resp = client.post("/parts/fuse", data={"mode": "select", "base_id": str(base_id)}, follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT MAX(plus) AS p FROM part_instances WHERE user_id = ? AND status = 'inventory'",
                (self.user_id,),
            ).fetchone()
            self.assertGreaterEqual(int(row["p"] or 0), 2)

    def test_fuse_bonus_cap(self):
        ids = self._seed_same_part_instances([1, 2, 2])
        base_id = ids[0]
        client = self._client()
        resp = client.post("/parts/fuse", data={"mode": "select", "base_id": str(base_id)}, follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT MAX(plus) AS p FROM part_instances WHERE user_id = ? AND status = 'inventory'",
                (self.user_id,),
            ).fetchone()
            self.assertEqual(int(row["p"] or 0), 2)

    def test_fuse_failure_result_shows_reason(self):
        ids = self._seed_same_part_instances([0, 0, 0])
        base_id = ids[0]
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET coins = 0 WHERE id = ?", (self.user_id,))
            db.commit()

        client = self._client()
        resp = client.post("/parts/fuse", data={"mode": "select", "base_id": str(base_id)}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("強化結果", html)
        self.assertIn("失敗", html)
        self.assertIn("コイン不足です", html)
        self.assertNotIn("不明", html)

    def test_fuse_plus_cap_is_five(self):
        ids = self._seed_same_part_instances([5, 2, 2])
        base_id = ids[0]
        client = self._client()
        resp = client.post("/parts/fuse", data={"mode": "select", "base_id": str(base_id)}, follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        with game_app.app.app_context():
            db = game_app.get_db()
            row = db.execute(
                "SELECT MAX(plus) AS p FROM part_instances WHERE user_id = ? AND status = 'inventory'",
                (self.user_id,),
            ).fetchone()
            self.assertEqual(int(row["p"] or 0), int(game_app.MAX_PART_PLUS))


if __name__ == "__main__":
    unittest.main()
