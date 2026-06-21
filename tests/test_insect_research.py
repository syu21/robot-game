import os
import tempfile
import time
import unittest

import app as game_app
import init_db


class InsectResearchTests(unittest.TestCase):
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
                VALUES (?, ?, ?, 0, 0, 1)
                """,
                ("insect_user", "x", now),
            )
            self.user_id = db.execute(
                "SELECT id FROM users WHERE username = ?",
                ("insect_user",),
            ).fetchone()["id"]
            game_app.initialize_new_user(db, self.user_id)
            self.robot_id = db.execute(
                "SELECT active_robot_id FROM users WHERE id = ?",
                (self.user_id,),
            ).fetchone()["active_robot_id"]
            db.execute("UPDATE robot_instances SET name = 'Insect Trial', is_public = 1 WHERE id = ?", (self.robot_id,))
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _client(self):
        client = game_app.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
            sess["username"] = "insect_user"
        return client

    def _set_insect_parts(self, count):
        with game_app.app.app_context():
            db = game_app.get_db()
            parts_row = db.execute(
                """
                SELECT head_part_instance_id, r_arm_part_instance_id, l_arm_part_instance_id, legs_part_instance_id
                FROM robot_instance_parts
                WHERE robot_instance_id = ?
                """,
                (int(self.robot_id),),
            ).fetchone()
            slots = [
                ("HEAD", int(parts_row["head_part_instance_id"])),
                ("RIGHT_ARM", int(parts_row["r_arm_part_instance_id"])),
                ("LEFT_ARM", int(parts_row["l_arm_part_instance_id"])),
                ("LEGS", int(parts_row["legs_part_instance_id"])),
            ]
            for idx, (part_type, instance_id) in enumerate(slots):
                if idx >= int(count):
                    continue
                part = db.execute(
                    """
                    SELECT id, COALESCE(series_key, series) AS series_key
                    FROM robot_parts
                    WHERE part_type = ?
                      AND COALESCE(series_key, series, '') LIKE 'insect_%'
                      AND is_active = 1
                    ORDER BY id ASC
                    LIMIT 1
                    """,
                    (part_type,),
                ).fetchone()
                self.assertIsNotNone(part)
                db.execute(
                    "UPDATE part_instances SET part_id = ?, series = ?, updated_at = datetime('now') WHERE id = ?",
                    (int(part["id"]), str(part["series_key"]), int(instance_id)),
                )
            db.commit()

    def test_insect_research_badge_thresholds_and_decor_ignored(self):
        self.assertFalse(game_app._robot_insect_research_view_from_parts([])["is_insect"])
        one = game_app._robot_insect_research_view_from_parts(
            [{"part_type": "HEAD", "series_key": "insect_kabuto"}]
        )
        self.assertFalse(one["is_insect"])
        partial = game_app._robot_insect_research_view_from_parts(
            [
                {"part_type": "HEAD", "series_key": "insect_kabuto"},
                {"part_type": "RIGHT_ARM", "series_key": "insect_bee"},
            ]
        )
        self.assertEqual(partial["label"], "虫型研究機")
        complete = game_app._robot_insect_research_view_from_parts(
            [
                {"part_type": "HEAD", "series_key": "insect_kabuto"},
                {"part_type": "RIGHT_ARM", "series_key": "insect_bee"},
                {"part_type": "LEFT_ARM", "series_key": "insect_ant"},
                {"part_type": "LEGS", "series_key": "insect_batta"},
            ]
        )
        self.assertEqual(complete["label"], "完全虫型研究機")
        decor_only = game_app._robot_insect_research_view_from_parts(
            [{"part_type": "DECORATION", "series_key": "insect_bee"}]
        )
        self.assertFalse(decor_only["is_insect"])

    def test_showcase_insect_filter_and_badge(self):
        self._set_insect_parts(4)
        client = self._client()
        resp = client.get("/showcase?sort=insect")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("虫型", html)
        self.assertIn("完全虫型研究機", html)
        self.assertIn("Insect Trial", html)
        self.assertIn("新着", html)
        self.assertIn("いいね", html)

    def test_home_and_ranking_are_safe_with_insect_metrics(self):
        client = self._client()
        home = client.get("/home")
        self.assertEqual(home.status_code, 200)
        home_html = home.get_data(as_text=True)
        self.assertIn("恐竜発掘キャンペーン", home_html)
        self.assertNotIn("虫型研究 進行中", home_html)

        self._set_insect_parts(2)
        ranking = client.get("/ranking?metric=weekly_insect_parts")
        self.assertEqual(ranking.status_code, 200)
        ranking_html = ranking.get_data(as_text=True)
        self.assertIn("今週の虫型研究ランキング", ranking_html)
        self.assertIn("insect_user", ranking_html)

    def test_complete_insect_robot_world_log_is_once(self):
        self._set_insect_parts(4)
        with game_app.app.app_context():
            db = game_app.get_db()
            game_app._record_insect_robot_completion_if_needed(
                db,
                self.user_id,
                self.robot_id,
                robot_name="Insect Trial",
                request_id="test-request",
                ip="127.0.0.1",
            )
            game_app._record_insect_robot_completion_if_needed(
                db,
                self.user_id,
                self.robot_id,
                robot_name="Insect Trial",
                request_id="test-request-2",
                ip="127.0.0.1",
            )
            db.commit()
            count = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM world_events_log
                WHERE event_type = ?
                  AND entity_type = 'robot_instance'
                  AND entity_id = ?
                """,
                (game_app.AUDIT_EVENT_TYPES["INSECT_ROBOT_COMPLETE"], int(self.robot_id)),
            ).fetchone()["c"]
            self.assertEqual(int(count), 1)


if __name__ == "__main__":
    unittest.main()
