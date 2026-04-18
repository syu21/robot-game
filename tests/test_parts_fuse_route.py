import json
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

    def _clear_part_instances(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("DELETE FROM part_instances WHERE user_id = ?", (self.user_id,))
            db.commit()

    def _active_part_seeds(self, limit=3):
        with game_app.app.app_context():
            db = game_app.get_db()
            return db.execute(
                """
                SELECT rp.id AS part_id, rp.part_type, rp.rarity, rp.element, rp.series
                FROM robot_parts rp
                WHERE rp.is_active = 1
                ORDER BY rp.id ASC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()

    def _seed_part_instances_for_seed(self, seed_row, plus_values, *, statuses=None, created_at_start=1000):
        statuses = statuses or ["inventory"] * len(plus_values)
        with game_app.app.app_context():
            db = game_app.get_db()
            ids = []
            for index, plus in enumerate(plus_values):
                status = statuses[index] if index < len(statuses) else "inventory"
                created_at = int(created_at_start) + index
                cur = db.execute(
                    """
                    INSERT INTO part_instances
                    (part_id, user_id, part_type, rarity, element, series, plus, w_hp, w_atk, w_def, w_spd, w_acc, w_cri, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        int(seed_row["part_id"]),
                        int(self.user_id),
                        seed_row["part_type"],
                        seed_row["rarity"],
                        seed_row["element"],
                        seed_row["series"],
                        int(plus),
                        1.0,
                        1.0,
                        1.0,
                        1.0,
                        1.0,
                        1.0,
                        status,
                        created_at,
                    ),
                )
                ids.append(int(cur.lastrowid))
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

    def test_r_part_accepts_corresponding_n_assist_materials(self):
        with game_app.app.app_context():
            db = game_app.get_db()
            seed = db.execute(
                """
                SELECT
                    id AS part_id,
                    part_type,
                    rarity,
                    element,
                    series
                FROM robot_parts
                WHERE UPPER(COALESCE(rarity, 'N')) = 'N'
                  AND is_active = 1
                ORDER BY id ASC
                LIMIT 1
                """
            ).fetchone()
            self.assertIsNotNone(seed)
            db.execute("DELETE FROM part_instances WHERE user_id = ?", (self.user_id,))
            db.execute("UPDATE users SET coins = 999 WHERE id = ?", (self.user_id,))

            def insert_part(prefix, part_id, part_type, rarity, element, series):
                cur = db.execute(
                    """
                    INSERT INTO part_instances
                    (part_id, user_id, part_type, rarity, element, series, plus, w_hp, w_atk, w_def, w_spd, w_acc, w_cri, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 0, 1, 1, 1, 1, 1, 1, 'inventory', ?, datetime('now'))
                    """,
                    (
                        int(part_id),
                        int(self.user_id),
                        part_type,
                        rarity,
                        element,
                        series,
                        int(time.time()) + int(prefix),
                    ),
                )
                return int(cur.lastrowid)

            base_id = insert_part(
                1,
                seed["part_id"],
                seed["part_type"],
                "R",
                seed["element"],
                seed["series"],
            )
            for offset in (2, 3):
                insert_part(
                    offset,
                    seed["part_id"],
                    seed["part_type"],
                    seed["rarity"],
                    seed["element"],
                    seed["series"],
                )
            db.commit()

            with game_app.app.test_request_context():
                first = game_app._strengthen_parts_selected(db, self.user_id, base_id)
            self.assertTrue(first["ok"])
            self.assertEqual(first["material_mode"], "r_n_assist")
            self.assertEqual(int(first["inc"]), 0)
            base = db.execute("SELECT plus, r_assist_points FROM part_instances WHERE id = ?", (base_id,)).fetchone()
            self.assertEqual(int(base["plus"]), 0)
            self.assertEqual(int(base["r_assist_points"]), 50)

            for offset in (4, 5):
                insert_part(
                    offset,
                    seed["part_id"],
                    seed["part_type"],
                    seed["rarity"],
                    seed["element"],
                    seed["series"],
                )
            db.commit()

            with game_app.app.test_request_context():
                second = game_app._strengthen_parts_selected(db, self.user_id, base_id)
            self.assertTrue(second["ok"])
            self.assertEqual(int(second["inc"]), 1)
            base = db.execute("SELECT plus, r_assist_points FROM part_instances WHERE id = ?", (base_id,)).fetchone()
            self.assertEqual(int(base["plus"]), 1)
            self.assertEqual(int(base["r_assist_points"]), 0)

    def test_fuse_batch_uses_inventory_materials_only(self):
        ids = self._seed_same_part_instances([0, 0, 0, 0, 0])
        base_id = ids[0]
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE part_instances SET status = 'equipped' WHERE id = ?", (base_id,))
            db.commit()

        client = self._client()
        resp = client.post("/parts/fuse", data={"mode": "batch", "base_id": str(base_id)}, follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        result_page = client.get(resp.headers["Location"])
        self.assertEqual(result_page.status_code, 200)
        html = result_page.get_data(as_text=True)
        self.assertIn("まとめ強化", html)
        self.assertIn("2回実行", html)

        with game_app.app.app_context():
            db = game_app.get_db()
            base_row = db.execute(
                "SELECT plus, status FROM part_instances WHERE id = ?",
                (base_id,),
            ).fetchone()
            self.assertEqual(int(base_row["plus"] or 0), 2)
            self.assertEqual(str(base_row["status"]), "equipped")

            inventory_count = db.execute(
                "SELECT COUNT(*) AS c FROM part_instances WHERE user_id = ? AND status = 'inventory'",
                (self.user_id,),
            ).fetchone()
            self.assertEqual(int(inventory_count["c"] or 0), 0)

            audit_row = db.execute(
                """
                SELECT payload_json
                FROM world_events_log
                WHERE user_id = ? AND event_type = 'audit.fuse'
                ORDER BY id DESC
                LIMIT 1
                """,
                (self.user_id,),
            ).fetchone()
            self.assertIsNotNone(audit_row)
            payload = json.loads(audit_row["payload_json"] or "{}")
            self.assertTrue(bool(payload.get("batch_mode")))
            self.assertEqual(int(payload.get("batch_count") or 0), 2)

    def test_warehouse_plan_prefers_equipped_then_oldest_high_plus(self):
        self._clear_part_instances()
        seed = self._active_part_seeds(limit=1)[0]
        ids = self._seed_part_instances_for_seed(seed, [0, 3, 3, 0, 0], created_at_start=2000)

        with game_app.app.app_context():
            db = game_app.get_db()
            with game_app.app.test_request_context():
                plan = game_app._strengthen_warehouse_plan(db, self.user_id)
            self.assertEqual(int(plan["group_count"] or 0), 1)
            self.assertEqual(int(plan["groups"][0]["base_id"] or 0), ids[1])

            db.execute("UPDATE part_instances SET status = 'equipped' WHERE id = ?", (ids[0],))
            db.commit()

            with game_app.app.test_request_context():
                plan = game_app._strengthen_warehouse_plan(db, self.user_id)
            self.assertEqual(int(plan["group_count"] or 0), 1)
            self.assertEqual(int(plan["groups"][0]["base_id"] or 0), ids[0])

    def test_warehouse_preview_and_execute_across_groups(self):
        self._clear_part_instances()
        seeds = self._active_part_seeds(limit=3)
        head_ids = self._seed_part_instances_for_seed(
            seeds[0],
            [0, 0, 0, 0, 0],
            statuses=["equipped", "inventory", "inventory", "inventory", "inventory"],
            created_at_start=3000,
        )
        arm_ids = self._seed_part_instances_for_seed(
            seeds[1],
            [1, 0, 0],
            created_at_start=4000,
        )
        self._seed_part_instances_for_seed(
            seeds[2],
            [0, 0, 0],
            statuses=["inventory", "inventory", "overflow"],
            created_at_start=5000,
        )
        with game_app.app.app_context():
            db = game_app.get_db()
            db.execute("UPDATE users SET coins = 999 WHERE id = ?", (self.user_id,))
            db.commit()
            with game_app.app.test_request_context():
                plan = game_app._strengthen_warehouse_plan(db, self.user_id)
            self.assertEqual(int(plan["group_count"] or 0), 2)
            self.assertEqual(int(plan["fuse_count"] or 0), 3)
            self.assertEqual(int(plan["total_material_count"] or 0), 6)

        client = self._client()
        preview = client.post("/parts/fuse", data={"mode": "warehouse_preview"}, follow_redirects=True)
        self.assertEqual(preview.status_code, 200)
        preview_html = preview.get_data(as_text=True)
        self.assertIn("倉庫整理合成", preview_html)
        self.assertIn("この内容で整理する", preview_html)
        self.assertIn("対象 2種類", preview_html)

        execute = client.post(
            "/parts/fuse",
            data={"mode": "warehouse_execute", "plan_signature": plan["signature"]},
            follow_redirects=False,
        )
        self.assertIn(execute.status_code, (302, 303))
        self.assertIn("mode=warehouse_result", execute.headers.get("Location", ""))

        result_page = client.get(execute.headers["Location"])
        self.assertEqual(result_page.status_code, 200)
        result_html = result_page.get_data(as_text=True)
        self.assertIn("倉庫整理合成の結果", result_html)
        self.assertIn("対象 2種類", result_html)
        self.assertIn("合計強化 3回", result_html)

        with game_app.app.app_context():
            db = game_app.get_db()
            head_row = db.execute(
                "SELECT plus, status FROM part_instances WHERE id = ?",
                (head_ids[0],),
            ).fetchone()
            self.assertEqual(int(head_row["plus"] or 0), 2)
            self.assertEqual(str(head_row["status"]), "equipped")

            arm_plus = db.execute(
                "SELECT plus FROM part_instances WHERE id = ?",
                (arm_ids[0],),
            ).fetchone()
            self.assertEqual(int(arm_plus["plus"] or 0), 2)

            inventory_count = db.execute(
                "SELECT COUNT(*) AS c FROM part_instances WHERE user_id = ? AND status = 'inventory'",
                (self.user_id,),
            ).fetchone()
            self.assertEqual(int(inventory_count["c"] or 0), 3)

            overflow_count = db.execute(
                "SELECT COUNT(*) AS c FROM part_instances WHERE user_id = ? AND status = 'overflow'",
                (self.user_id,),
            ).fetchone()
            self.assertEqual(int(overflow_count["c"] or 0), 1)

            fuse_events = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = 'audit.fuse'",
                (self.user_id,),
            ).fetchone()
            self.assertEqual(int(fuse_events["c"] or 0), 2)

            preview_events = db.execute(
                "SELECT COUNT(*) AS c FROM world_events_log WHERE user_id = ? AND event_type = 'audit.fuse.batch_preview'",
                (self.user_id,),
            ).fetchone()
            self.assertEqual(int(preview_events["c"] or 0), 1)

            execute_event = db.execute(
                """
                SELECT payload_json
                FROM world_events_log
                WHERE user_id = ? AND event_type = 'audit.fuse.batch_execute'
                ORDER BY id DESC
                LIMIT 1
                """,
                (self.user_id,),
            ).fetchone()
            self.assertIsNotNone(execute_event)
            payload = json.loads(execute_event["payload_json"] or "{}")
            self.assertEqual(str(payload.get("mode")), "warehouse_batch")
            self.assertEqual(int(payload.get("group_count") or 0), 2)
            self.assertEqual(int(payload.get("fuse_count") or 0), 3)
            self.assertEqual(int(payload.get("total_material_count") or 0), 6)

            fusion_rows = db.execute(
                "SELECT COUNT(*) AS c FROM fusion_audit_logs WHERE user_id = ? AND mode = 'warehouse_batch'",
                (self.user_id,),
            ).fetchone()
            self.assertEqual(int(fusion_rows["c"] or 0), 2)


if __name__ == "__main__":
    unittest.main()
