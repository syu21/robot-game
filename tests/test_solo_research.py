import os
import tempfile
import time
import unittest

import app as game_app
import init_db
from services import solo_research


class SoloResearchTests(unittest.TestCase):
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
                INSERT INTO users (username, password_hash, created_at, max_unlocked_layer, lab_level, lab_exp, lab_total_exp)
                VALUES ('solo_research_user', 'x', ?, 2, 1, 0, 0)
                """,
                (now,),
            )
            self.user_id = int(db.execute("SELECT id FROM users WHERE username = 'solo_research_user'").fetchone()["id"])
            db.commit()

    def tearDown(self):
        game_app.DB_PATH = self.old_db_path
        init_db.DB_PATH = self.old_init_db_path
        self.tmpdir.cleanup()

    def _db(self):
        return game_app.get_db()

    def test_board_assigns_three_persistent_tasks(self):
        with game_app.app.app_context():
            db = self._db()
            board = solo_research.ensure_research_board(db, self.user_id)
            db.commit()
            self.assertEqual(len(board), 3)
            self.assertEqual({task["slot_index"] for task in board}, {1, 2, 3})
            self.assertTrue(db.execute("SELECT 1 FROM user_research_profiles WHERE user_id = ?", (self.user_id,)).fetchone())

    def test_explore_progress_completion_reward_and_idempotency(self):
        with game_app.app.app_context():
            db = self._db()
            solo_research.ensure_research_board(db, self.user_id)
            db.execute("DELETE FROM user_research_tasks WHERE user_id = ?", (self.user_id,))
            db.execute(
                """
                INSERT INTO user_research_tasks
                (user_id, task_key, status, slot_index, progress, target, snapshot_json, assigned_at)
                VALUES (?, 'test_fast', 'active', 1, 0, 1, ?, ?)
                """,
                (
                    self.user_id,
                    '{"task_key":"test_fast","category":"special","category_label":"特別研究","title":"短期決戦","description":"","condition_type":"fast_win","condition_payload":{"turns":5},"reward_exp":45,"target":1}',
                    int(time.time()),
                ),
            )
            payload = {
                "area_key": "layer_1",
                "result": {"win": True, "turns": 4, "battle_id": "battle-solo-1"},
                "player": {"series_keys": []},
            }
            updates = solo_research.update_research_tasks_for_event(db, self.user_id, solo_research.EVENT_EXPLORE_END, payload)
            duplicate = solo_research.update_research_tasks_for_event(db, self.user_id, solo_research.EVENT_EXPLORE_END, payload)
            db.commit()
            self.assertTrue(any(item["task_key"] == "test_fast" and item["is_completed"] for item in updates))
            self.assertEqual(duplicate, [])
            user = db.execute("SELECT lab_total_exp FROM users WHERE id = ?", (self.user_id,)).fetchone()
            self.assertEqual(user["lab_total_exp"], 45)

    def test_hold_and_resume_task(self):
        with game_app.app.app_context():
            db = self._db()
            board = solo_research.ensure_research_board(db, self.user_id)
            task_id = board[0]["id"]
            self.assertTrue(solo_research.hold_research_task(db, self.user_id, task_id)["ok"])
            held = solo_research.held_task_view(db, self.user_id)
            self.assertEqual(held["id"], task_id)
            self.assertTrue(solo_research.resume_held_research_task(db, self.user_id, task_id)["ok"])
            db.commit()
            held_after = solo_research.held_task_view(db, self.user_id)
            self.assertNotEqual((held_after or {}).get("id"), task_id)

    def test_personal_record_updates_only_when_better(self):
        with game_app.app.app_context():
            db = self._db()
            payload = {"area_key": "layer_1", "result": {"win": True, "turns": 5, "battle_id": "r1"}}
            first = solo_research.update_personal_records_from_explore(db, self.user_id, payload)
            worse = solo_research.update_personal_records_from_explore(db, self.user_id, {"area_key": "layer_1", "result": {"win": True, "turns": 6, "battle_id": "r2"}})
            better = solo_research.update_personal_records_from_explore(db, self.user_id, {"area_key": "layer_1", "result": {"win": True, "turns": 4, "battle_id": "r3"}})
            db.commit()
            self.assertTrue(first)
            self.assertEqual(worse, [])
            self.assertTrue(better)
            record = db.execute("SELECT best_value FROM user_personal_records WHERE user_id = ?", (self.user_id,)).fetchone()
            self.assertEqual(record["best_value"], 4)


if __name__ == "__main__":
    unittest.main()
